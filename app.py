import json
import os
import random
import re
import sqlite3
from datetime import date, datetime, time, timedelta, timezone

from dotenv import load_dotenv
from flask import Flask, g, jsonify, render_template, request
from flask_bcrypt import Bcrypt
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)

load_dotenv()

app = Flask(__name__)
# 세션(로그인 상태)을 지키는 데 쓰는 비밀키. .env의 SECRET_KEY를 쓴다.
app.secret_key = os.environ.get("SECRET_KEY", "study-league-dev-key-change-me")

bcrypt = Bcrypt(app)
login_manager = LoginManager(app)

# 어느 폴더에서 실행해도 같은 DB를 쓰도록 app.py 옆에 둔다
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.db")

# 한국 시간 (서머타임이 없어서 +9시간 고정)
KST = timezone(timedelta(hours=9))


# ---------- 오류 응답 ----------
class ApiError(Exception):
    """어디서든 raise ApiError("메시지", 400) 하면 {"error": 메시지}로 응답한다."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


@app.errorhandler(ApiError)
def handle_api_error(e):
    return jsonify({"error": e.message}), e.status


# ---------- 시간 도우미 ----------
# 시각은 모두 UTC "YYYY-MM-DDTHH:MM:SSZ" 문자열로 저장한다 (글자 비교 = 시간 비교)
def now_utc():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_iso():
    return iso(now_utc())


def today_kst():
    return now_utc().astimezone(KST).date()


# ---------- DB 준비 ----------
def get_db():
    """요청 하나당 DB 연결 하나를 쓴다."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def add_missing_columns(db, table, columns):
    """예전에 만든 테이블에 새 컬럼이 없으면 추가한다 (간단 마이그레이션)."""
    have = [r[1] for r in db.execute(f"PRAGMA table_info({table})").fetchall()]
    for name, ddl in columns.items():
        if name not in have:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def init_db():
    with sqlite3.connect(DB_PATH) as db:
        db.row_factory = sqlite3.Row
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS user (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                nickname TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        # 리그 (F3/F4): 관리자가 만든 리그. status = recruiting(모집 중)/running(진행 중)/finished(끝)
        # subjects: 과목·과목별 문제 수 JSON (예: [{"name":"영어","count":3}])
        # rewards: 순위별 상품·벌칙 JSON (예: [{"from":1,"to":1,"kind":"reward","text":"치킨"}])
        # 일정: start_date(첫 경기 날, 한국 날짜) / round_days(한 경기 기간, 일)
        #       make_days(그중 문제 만드는 기간, 일) / deadline_time(마감 시각, 한국 시간 "HH:MM")
        # legs: 1이면 모두 한 번씩, 2면 두 번씩(홈·원정) 붙는다
        # pts_*: 승·무·패 승점 / max_members: 인원 제한(0 = 제한 없음) / notice: 학생에게 보이는 안내
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS league (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                code TEXT UNIQUE NOT NULL,
                admin_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'recruiting',
                subjects TEXT NOT NULL DEFAULT '[]',
                rewards TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            )
            """
        )
        add_missing_columns(
            db,
            "league",
            {
                "subjects": "TEXT NOT NULL DEFAULT '[]'",
                "rewards": "TEXT NOT NULL DEFAULT '[]'",
                "notice": "TEXT NOT NULL DEFAULT ''",
                "start_date": "TEXT",
                "round_days": "INTEGER NOT NULL DEFAULT 7",
                "make_days": "INTEGER NOT NULL DEFAULT 3",
                "deadline_time": "TEXT NOT NULL DEFAULT '22:00'",
                "legs": "INTEGER NOT NULL DEFAULT 1",
                "pts_win": "INTEGER NOT NULL DEFAULT 3",
                "pts_draw": "INTEGER NOT NULL DEFAULT 1",
                "pts_lose": "INTEGER NOT NULL DEFAULT 0",
                "max_members": "INTEGER NOT NULL DEFAULT 0",
            },
        )
        # 리그 참가 (F5): 어느 학생이 어느 리그에 들어갔는지. 한 학생은 리그 하나만(user_id UNIQUE)
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS membership (
                id INTEGER PRIMARY KEY,
                league_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL UNIQUE,
                joined_at TEXT NOT NULL
            )
            """
        )
        # 주차 일정 (F6): 주차마다 시작·문제 만들기 마감·문제 풀기 마감 시각 (UTC)
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS round (
                id INTEGER PRIMARY KEY,
                league_id INTEGER NOT NULL,
                week INTEGER NOT NULL,
                start_at TEXT NOT NULL,
                make_deadline TEXT NOT NULL,
                solve_deadline TEXT NOT NULL,
                UNIQUE (league_id, week)
            )
            """
        )
        # 대진/경기 (F6): 리그, 주차, 두 선수, 결과, 각자 점수
        # result = NULL(아직)/'p1'(선수1 승)/'p2'(선수2 승)/'draw'(무)/'both_lose'(둘 다 기권)/'bye'(쉬는 주)
        # player2_id가 NULL이면 그 주는 player1이 쉬는 주
        # p1_done/p2_done: 그 선수가 상대 문제를 다 풀어 제출했는지(0/1)
        # forfeit: 문제를 마감까지 안 만들어 기권한 쪽 ('p1'/'p2'/'both')
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS match (
                id INTEGER PRIMARY KEY,
                league_id INTEGER NOT NULL,
                week INTEGER NOT NULL,
                player1_id INTEGER NOT NULL,
                player2_id INTEGER,
                result TEXT,
                p1_score INTEGER DEFAULT 0,
                p2_score INTEGER DEFAULT 0,
                p1_done INTEGER DEFAULT 0,
                p2_done INTEGER DEFAULT 0
            )
            """
        )
        add_missing_columns(
            db,
            "match",
            {
                "p1_done": "INTEGER DEFAULT 0",
                "p2_done": "INTEGER DEFAULT 0",
                "forfeit": "TEXT",
            },
        )
        # 문제 (F7): 만든 사람, 리그, 주차, 과목, 유형, 내용, 보기, 정답, 해설
        # 주차마다 그 주 상대를 위해 새로 만든다 (같은 문제가 여러 상대에게 새지 않게)
        # qtype = 'mc'(객관식)/'sa'(주관식)
        # answer: 객관식이면 정답 보기 번호(0부터), 주관식이면 정답 글자
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS question (
                id INTEGER PRIMARY KEY,
                league_id INTEGER NOT NULL,
                author_id INTEGER NOT NULL,
                subject TEXT NOT NULL,
                qtype TEXT NOT NULL,
                content TEXT NOT NULL,
                choices TEXT NOT NULL DEFAULT '[]',
                answer TEXT NOT NULL,
                explanation TEXT NOT NULL DEFAULT ''
            )
            """
        )
        add_missing_columns(db, "question", {"week": "INTEGER NOT NULL DEFAULT 0"})
        # 풀이 (F8/F9): 누가 어느 경기에서 어떤 문제에 무엇을 답했는지, 맞았는지
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS submission (
                id INTEGER PRIMARY KEY,
                match_id INTEGER NOT NULL,
                solver_id INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                given TEXT NOT NULL,
                correct INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        # 예전 방식(일정 없이)으로 시작한 리그는 오늘부터 일정을 새로 붙여 준다
        old = db.execute(
            "SELECT l.* FROM league l WHERE l.status = 'running' "
            "AND NOT EXISTS (SELECT 1 FROM round r WHERE r.league_id = l.id)"
        ).fetchall()
        for lg in old:
            weeks = db.execute(
                "SELECT MAX(week) FROM match WHERE league_id = ?", (lg["id"],)
            ).fetchone()[0] or 0
            for week, s, m, e in build_rounds(
                today_kst(), weeks, lg["round_days"], lg["make_days"], lg["deadline_time"]
            ):
                db.execute(
                    "INSERT INTO round (league_id, week, start_at, make_deadline, solve_deadline) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (lg["id"], week, s, m, e),
                )
            db.execute(
                "UPDATE match SET result = 'bye' WHERE league_id = ? AND player2_id IS NULL",
                (lg["id"],),
            )


# ---------- 리그 규칙 도우미 ----------
def gen_league_code(db):
    """서로 겹치지 않는 6자리 숫자 코드를 만든다 (README 5번)."""
    for _ in range(100):
        code = f"{random.randint(0, 999999):06d}"
        exists = db.execute("SELECT 1 FROM league WHERE code = ?", (code,)).fetchone()
        if not exists:
            return code
    raise RuntimeError("리그 코드를 만들지 못했어요")


def get_my_membership(db, user_id):
    """내가 들어간 리그 참가 정보를 돌려준다 (없으면 None)."""
    return db.execute(
        "SELECT league_id FROM membership WHERE user_id = ?", (user_id,)
    ).fetchone()


def make_round_robin(player_ids):
    """
    모두가 서로 한 번씩 붙는 대진표를 만든다 (라운드 로빈).
    돌려주는 값: [[(a, b), (c, d), ...], ...]  (주차별 경기 목록)
    사람이 홀수면 매주 한 명씩 돌아가며 쉰다 (상대가 None).
    """
    players = list(player_ids)
    if len(players) < 2:
        return []

    # 홀수면 가짜 선수(None)를 넣어 짝을 맞춘다. 이 선수와 만나면 쉬는 주.
    if len(players) % 2 == 1:
        players.append(None)

    n = len(players)
    rounds = []
    # 표준 라운드 로빈: 맨 앞은 고정, 나머지를 회전시킨다
    arr = players[:]
    for _ in range(n - 1):
        pairs = []
        for i in range(n // 2):
            a = arr[i]
            b = arr[n - 1 - i]
            if a is None or b is None:
                real = a if a is not None else b
                pairs.append((real, None))
            else:
                pairs.append((a, b))
        rounds.append(pairs)
        arr = [arr[0]] + [arr[-1]] + arr[1:-1]
    return rounds


def build_rounds(first_day, n_rounds, round_days, make_days, deadline_time):
    """
    주차별 시각을 계산한다. 돌려주는 값: [(주차, 시작, 만들기 마감, 풀기 마감), ...]
    예) 월요일 시작, 7일, 만들기 3일, 22:00 →
        월 0시 시작 / 수 22:00 문제 만들기 마감 / 일 22:00 문제 풀기 마감
    """
    hh, mm = map(int, deadline_time.split(":"))
    out = []
    for k in range(n_rounds):
        day0 = first_day + timedelta(days=k * round_days)
        start = datetime.combine(day0, time(0, 0), KST)
        make = datetime.combine(day0 + timedelta(days=make_days - 1), time(hh, mm), KST)
        solve = datetime.combine(day0 + timedelta(days=round_days - 1), time(hh, mm), KST)
        out.append((k + 1, iso(start), iso(make), iso(solve)))
    return out


def round_phase(r, now):
    """주차의 지금 단계: upcoming(시작 전)/make(문제 만들기)/solve(문제 풀기)/done(끝)."""
    if now < r["start_at"]:
        return "upcoming"
    if now < r["make_deadline"]:
        return "make"
    if now < r["solve_deadline"]:
        return "solve"
    return "done"


def focus_round(db, league_id):
    """
    지금 신경 써야 할 주차: 풀기 마감이 아직 안 지난 가장 이른 주차.
    다 끝났으면 마지막 주차. 일정이 없으면 None.
    """
    r = db.execute(
        "SELECT * FROM round WHERE league_id = ? AND solve_deadline > ? "
        "ORDER BY week ASC LIMIT 1",
        (league_id, now_iso()),
    ).fetchone()
    if r is None:
        r = db.execute(
            "SELECT * FROM round WHERE league_id = ? ORDER BY week DESC LIMIT 1",
            (league_id,),
        ).fetchone()
    return r


def questions_needed(league):
    """한 경기에 만들어야 하는 문제 수 (과목별 문제 수의 합)."""
    return sum(s["count"] for s in json.loads(league["subjects"] or "[]"))


def made_count(db, league_id, author_id, week):
    return db.execute(
        "SELECT COUNT(*) FROM question WHERE league_id = ? AND author_id = ? AND week = ?",
        (league_id, author_id, week),
    ).fetchone()[0]


def finalize_match(db, league, m, by_deadline):
    """
    경기 결과를 정한다 (F10).
    - 둘 다 풀어서 제출했으면 바로 판정
    - 풀기 마감이 지났으면: 안 푼 사람은 0점, 문제를 안 만든 사람은 기권패
    """
    if m["result"] is not None or m["player2_id"] is None:
        return
    if not by_deadline and not (m["p1_done"] and m["p2_done"]):
        return

    need = questions_needed(league)
    made1 = made_count(db, league["id"], m["player1_id"], m["week"]) >= need
    made2 = made_count(db, league["id"], m["player2_id"], m["week"]) >= need
    s1, s2 = m["p1_score"] or 0, m["p2_score"] or 0

    forfeit = None
    if made1 and made2:
        result = "p1" if s1 > s2 else "p2" if s2 > s1 else "draw"
    elif made1:
        result, forfeit = "p1", "p2"
    elif made2:
        result, forfeit = "p2", "p1"
    else:
        result, forfeit = "both_lose", "both"
    db.execute(
        "UPDATE match SET result = ?, forfeit = ? WHERE id = ?",
        (result, forfeit, m["id"]),
    )


def settle_league(db, league_id):
    """
    풀기 마감이 지난 경기들을 처리하고, 마지막 주가 끝났으면 리그를 끝낸다.
    리그 정보를 읽을 때마다 부른다 (따로 예약 작업이 없어도 마감이 처리됨).
    """
    league = db.execute("SELECT * FROM league WHERE id = ?", (league_id,)).fetchone()
    if league is None or league["status"] != "running":
        return
    now = now_iso()
    pending = db.execute(
        "SELECT m.* FROM match m JOIN round r ON r.league_id = m.league_id AND r.week = m.week "
        "WHERE m.league_id = ? AND m.result IS NULL AND r.solve_deadline <= ?",
        (league_id, now),
    ).fetchall()
    for m in pending:
        finalize_match(db, league, m, by_deadline=True)

    last = db.execute(
        "SELECT MAX(solve_deadline) FROM round WHERE league_id = ?", (league_id,)
    ).fetchone()[0]
    if last and last <= now:
        left = db.execute(
            "SELECT COUNT(*) FROM match WHERE league_id = ? AND result IS NULL", (league_id,)
        ).fetchone()[0]
        if left == 0:
            db.execute("UPDATE league SET status = 'finished' WHERE id = ?", (league_id,))
    db.commit()


def compute_standings(db, league):
    """
    순위표를 계산한다 (F11). 각 선수의 경기수·승·무·패·득점·실점·승점.
    순위 정렬: 승점 → 득실차 → 득점(맞힌 문제 합) → 닉네임.
    쉬는 주는 아무것도 세지 않는다.
    """
    members = db.execute(
        "SELECT u.id, u.nickname FROM membership m JOIN user u ON u.id = m.user_id "
        "WHERE m.league_id = ?",
        (league["id"],),
    ).fetchall()
    pts = {"win": league["pts_win"], "draw": league["pts_draw"], "lose": league["pts_lose"]}

    stats = {
        m["id"]: {
            "user_id": m["id"],
            "nickname": m["nickname"],
            "played": 0, "win": 0, "draw": 0, "lose": 0,
            "scored": 0, "conceded": 0, "points": 0,
        }
        for m in members
    }

    def add(uid, outcome, scored, conceded):
        s = stats.get(uid)
        if s is None:
            return
        s["played"] += 1
        s[outcome] += 1
        s["points"] += pts[outcome]
        s["scored"] += scored
        s["conceded"] += conceded

    matches = db.execute(
        "SELECT player1_id, player2_id, result, p1_score, p2_score FROM match "
        "WHERE league_id = ? AND result IS NOT NULL AND result != 'bye'",
        (league["id"],),
    ).fetchall()
    for mt in matches:
        p1, p2 = mt["player1_id"], mt["player2_id"]
        s1, s2 = mt["p1_score"] or 0, mt["p2_score"] or 0
        r = mt["result"]
        o1 = {"p1": "win", "p2": "lose", "draw": "draw", "both_lose": "lose"}[r]
        o2 = {"p1": "lose", "p2": "win", "draw": "draw", "both_lose": "lose"}[r]
        add(p1, o1, s1, s2)
        add(p2, o2, s2, s1)

    table = sorted(
        stats.values(),
        key=lambda s: (-s["points"], -(s["scored"] - s["conceded"]), -s["scored"], s["nickname"]),
    )
    for i, row in enumerate(table, start=1):
        row["rank"] = i
        row["diff"] = row["scored"] - row["conceded"]
    return table


def normalize_sa(text):
    """주관식 비교용: 띄어쓰기 모두 제거 + 소문자로 (README 규칙)."""
    return "".join((text or "").split()).lower()


def grade_one(question_row, given):
    """문제 하나 채점. 맞으면 True."""
    if question_row["qtype"] == "mc":
        try:
            return int(given) == int(question_row["answer"])
        except (TypeError, ValueError):
            return False
    return normalize_sa(given) == normalize_sa(question_row["answer"])


# ---------- 리그 설정 검사 (만들기·수정 공통) ----------
def parse_int(value, lo, hi, message):
    if isinstance(value, bool):
        raise ApiError(message)
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ApiError(message)
    if not (lo <= n <= hi):
        raise ApiError(message)
    return n


def parse_league_settings(data):
    """리그 만들기/수정 요청을 검사해 DB에 넣을 값으로 바꾼다. 문제가 있으면 ApiError."""
    name = (data.get("name") or "").strip()
    if not (1 <= len(name) <= 30):
        raise ApiError("리그 이름은 1~30자여야 해요")

    notice = (data.get("notice") or "").strip()
    if len(notice) > 300:
        raise ApiError("안내 문구는 300자까지예요")

    # 과목 (F4): [{"name":"영어","count":3}, ...]
    raw_subjects = data.get("subjects") or []
    if not isinstance(raw_subjects, list) or len(raw_subjects) == 0:
        raise ApiError("과목을 하나 이상 넣어 주세요")
    if len(raw_subjects) > 10:
        raise ApiError("과목은 10개까지 넣을 수 있어요")
    subjects = []
    seen = set()
    for s in raw_subjects:
        if not isinstance(s, dict):
            raise ApiError("과목 형식이 올바르지 않아요")
        sname = (s.get("name") or "").strip()
        if not (1 <= len(sname) <= 20):
            raise ApiError("과목 이름은 1~20자여야 해요")
        if sname in seen:
            raise ApiError("같은 과목 이름이 두 번 들어갔어요")
        seen.add(sname)
        count = parse_int(s.get("count"), 1, 20, "과목별 문제 수는 1~20개여야 해요")
        subjects.append({"name": sname, "count": count})

    # 일정 (F4)
    start_raw = (data.get("start_date") or "").strip()
    try:
        start_date = date.fromisoformat(start_raw)
    except ValueError:
        raise ApiError("첫 경기 날짜를 골라 주세요")
    if start_date < today_kst():
        raise ApiError("첫 경기 날짜는 오늘이나 그 뒤여야 해요")
    round_days = parse_int(data.get("round_days"), 2, 14, "한 경기 기간은 2~14일이에요")
    make_days = parse_int(
        data.get("make_days"), 1, round_days - 1,
        "문제 만드는 기간은 1일 이상, 한 경기 기간보다 짧아야 해요",
    )
    deadline_time = (data.get("deadline_time") or "").strip()
    if not re.fullmatch(r"(0[1-9]|1\d|2[0-3]):[0-5]\d", deadline_time):
        raise ApiError("마감 시각은 01:00~23:59 사이로 정해 주세요")
    legs = parse_int(data.get("legs"), 1, 2, "몇 번씩 붙을지(1번/2번) 골라 주세요")

    # 승점
    points = data.get("points") or {}
    if not isinstance(points, dict):
        raise ApiError("승점 형식이 올바르지 않아요")
    pw = parse_int(points.get("win"), 0, 10, "승점은 0~10점이에요")
    pd = parse_int(points.get("draw"), 0, 10, "승점은 0~10점이에요")
    pl = parse_int(points.get("lose"), 0, 10, "승점은 0~10점이에요")
    if not (pw > pl and pw >= pd >= pl):
        raise ApiError("승점은 승 > 패, 승 ≥ 무 ≥ 패 순서여야 해요")

    max_members = parse_int(
        data.get("max_members") or 0, 0, 60, "인원 제한은 2~60명(없으면 0)이에요"
    )
    if max_members == 1:
        raise ApiError("인원 제한은 2~60명(없으면 0)이에요")

    # 상품·벌칙 (선택): [{"from":1,"to":1,"kind":"reward","text":"치킨"}, ...]
    raw_rewards = data.get("rewards") or []
    if not isinstance(raw_rewards, list):
        raise ApiError("상품·벌칙 형식이 올바르지 않아요")
    rewards = []
    for r in raw_rewards:
        if not isinstance(r, dict):
            raise ApiError("상품·벌칙 형식이 올바르지 않아요")
        rfrom = parse_int(r.get("from"), 1, 60, "상품·벌칙 등수는 1~60등이에요")
        rto = parse_int(r.get("to"), 1, 60, "상품·벌칙 등수는 1~60등이에요")
        if rto < rfrom:
            raise ApiError("상품·벌칙 등수 범위가 거꾸로예요")
        kind = r.get("kind") if r.get("kind") in ("reward", "penalty") else "reward"
        text = (r.get("text") or "").strip()
        if not (1 <= len(text) <= 100):
            raise ApiError("상품·벌칙 내용은 1~100자예요")
        rewards.append({"from": rfrom, "to": rto, "kind": kind, "text": text})

    return {
        "name": name,
        "notice": notice,
        "subjects": json.dumps(subjects, ensure_ascii=False),
        "rewards": json.dumps(rewards, ensure_ascii=False),
        "start_date": start_date.isoformat(),
        "round_days": round_days,
        "make_days": make_days,
        "deadline_time": deadline_time,
        "legs": legs,
        "pts_win": pw,
        "pts_draw": pd,
        "pts_lose": pl,
        "max_members": max_members,
    }


def get_league_or_404(db, league_id):
    league = db.execute("SELECT * FROM league WHERE id = ?", (league_id,)).fetchone()
    if league is None:
        raise ApiError("리그를 찾을 수 없어요", 404)
    return league


def require_admin(db, league_id):
    league = get_league_or_404(db, league_id)
    if league["admin_id"] != current_user.id:
        raise ApiError("이 리그의 관리자만 할 수 있어요", 403)
    return league


def require_my_league(db):
    """학생으로 들어간 리그를 돌려준다 (마감 처리도 먼저 해 둔다)."""
    mem = get_my_membership(db, current_user.id)
    if mem is None:
        raise ApiError("먼저 리그에 들어가세요", 403)
    settle_league(db, mem["league_id"])
    return get_league_or_404(db, mem["league_id"])


def my_side(m, uid):
    """경기에서 내가 선수1인지, 상대 id는 누구인지."""
    is_p1 = m["player1_id"] == uid
    return is_p1, (m["player2_id"] if is_p1 else m["player1_id"])


def nickname_map(db, league_id):
    rows = db.execute(
        "SELECT u.id, u.nickname FROM user u WHERE u.id IN ("
        " SELECT player1_id FROM match WHERE league_id = ?"
        " UNION SELECT player2_id FROM match WHERE league_id = ?"
        " UNION SELECT user_id FROM membership WHERE league_id = ?)",
        (league_id, league_id, league_id),
    ).fetchall()
    return {r["id"]: r["nickname"] for r in rows}


def league_settings_json(league):
    return {
        "start_date": league["start_date"],
        "round_days": league["round_days"],
        "make_days": league["make_days"],
        "deadline_time": league["deadline_time"],
        "legs": league["legs"],
        "points": {
            "win": league["pts_win"],
            "draw": league["pts_draw"],
            "lose": league["pts_lose"],
        },
        "max_members": league["max_members"],
    }


# ---------- 로그인 설정 ----------
class User(UserMixin):
    def __init__(self, id, username, nickname):
        self.id = id
        self.username = username
        self.nickname = nickname


@login_manager.user_loader
def load_user(user_id):
    row = get_db().execute(
        "SELECT id, username, nickname FROM user WHERE id = ?", (user_id,)
    ).fetchone()
    if row is None:
        return None
    return User(row["id"], row["username"], row["nickname"])


# 로그인 안 한 사람이 보호된 요청을 하면 리다이렉트 대신 401을 준다 (API라서)
@login_manager.unauthorized_handler
def unauthorized():
    return jsonify({"error": "로그인이 필요합니다"}), 401


# ---------- 화면 ----------
@app.get("/")
def index():
    return render_template("index.html")


# ---------- 로그인 상태 확인 ----------
@app.get("/me")
def me():
    if not current_user.is_authenticated:
        return {"logged_in": False}
    mem = get_my_membership(get_db(), current_user.id)
    return {
        "logged_in": True,
        "user_id": current_user.id,
        "nickname": current_user.nickname,
        "student_league_id": mem["league_id"] if mem else None,
    }


# ---------- 회원가입 (F1) ----------
@app.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    nickname = (data.get("nickname") or "").strip()

    if not re.fullmatch(r"[A-Za-z0-9]{4,20}", username):
        return {"error": "아이디는 영문·숫자 4~20자여야 해요"}, 400
    if not (8 <= len(password) <= 64):
        return {"error": "비밀번호는 8~64자여야 해요"}, 400
    if not (1 <= len(nickname) <= 10):
        return {"error": "닉네임은 1~10자여야 해요"}, 400

    db = get_db()
    if db.execute("SELECT 1 FROM user WHERE username = ?", (username,)).fetchone():
        return {"error": "이미 쓰고 있는 아이디예요"}, 409

    password_hash = bcrypt.generate_password_hash(password).decode("utf-8")
    db.execute(
        "INSERT INTO user (username, password_hash, nickname, created_at) VALUES (?, ?, ?, ?)",
        (username, password_hash, nickname, now_iso()),
    )
    db.commit()
    return {"ok": True}, 201


# ---------- 로그인 (F2) ----------
@app.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    row = get_db().execute(
        "SELECT id, username, nickname, password_hash FROM user WHERE username = ?",
        (username,),
    ).fetchone()
    if row is None or not bcrypt.check_password_hash(row["password_hash"], password):
        return {"error": "아이디나 비밀번호가 맞지 않아요"}, 401

    login_user(User(row["id"], row["username"], row["nickname"]), remember=True)
    return {"ok": True, "nickname": row["nickname"]}


# ---------- 로그아웃 (F2) ----------
@app.post("/logout")
@login_required
def logout():
    logout_user()
    return {"ok": True}


# ---------- 관리자: 내가 만든 리그 목록 ----------
@app.get("/admin/leagues")
@login_required
def admin_leagues():
    db = get_db()
    rows = db.execute(
        "SELECT id FROM league WHERE admin_id = ? ORDER BY id DESC", (current_user.id,)
    ).fetchall()
    leagues = []
    for r in rows:
        settle_league(db, r["id"])
        lg = get_league_or_404(db, r["id"])
        count = db.execute(
            "SELECT COUNT(*) FROM membership WHERE league_id = ?", (lg["id"],)
        ).fetchone()[0]
        leagues.append(
            {
                "id": lg["id"],
                "name": lg["name"],
                "code": lg["code"],
                "status": lg["status"],
                "member_count": count,
            }
        )
    return {"leagues": leagues}


# ---------- 리그 만들기 (F3/F4): 만든 사람이 관리자가 된다 ----------
@app.post("/leagues")
@login_required
def create_league():
    s = parse_league_settings(request.get_json(silent=True) or {})
    db = get_db()
    code = gen_league_code(db)
    cols = list(s.keys())
    cur = db.execute(
        f"INSERT INTO league (code, admin_id, status, created_at, {', '.join(cols)}) "
        f"VALUES (?, ?, 'recruiting', ?, {', '.join('?' for _ in cols)})",
        (code, current_user.id, now_iso(), *s.values()),
    )
    db.commit()
    return {"ok": True, "league_id": cur.lastrowid, "code": code}, 201


# ---------- 리그 설정 수정 (F4): 모집 중일 때만 ----------
@app.post("/leagues/<int:league_id>/settings")
@login_required
def update_league(league_id):
    db = get_db()
    league = require_admin(db, league_id)
    if league["status"] != "recruiting":
        raise ApiError("리그가 시작된 뒤에는 설정을 바꿀 수 없어요", 409)
    s = parse_league_settings(request.get_json(silent=True) or {})
    count = db.execute(
        "SELECT COUNT(*) FROM membership WHERE league_id = ?", (league_id,)
    ).fetchone()[0]
    if s["max_members"] and count > s["max_members"]:
        raise ApiError(f"이미 {count}명이 들어와 있어요. 인원 제한을 더 크게 해 주세요")
    db.execute(
        f"UPDATE league SET {', '.join(f'{k} = ?' for k in s)} WHERE id = ?",
        (*s.values(), league_id),
    )
    db.commit()
    return {"ok": True}


# ---------- 리그 삭제: 모집 중일 때만 ----------
@app.post("/leagues/<int:league_id>/delete")
@login_required
def delete_league(league_id):
    db = get_db()
    league = require_admin(db, league_id)
    if league["status"] != "recruiting":
        raise ApiError("시작한 리그는 지울 수 없어요", 409)
    db.execute("DELETE FROM membership WHERE league_id = ?", (league_id,))
    db.execute("DELETE FROM question WHERE league_id = ?", (league_id,))
    db.execute("DELETE FROM league WHERE id = ?", (league_id,))
    db.commit()
    return {"ok": True}


# ---------- 학생 내보내기: 모집 중일 때만 ----------
@app.post("/leagues/<int:league_id>/kick")
@login_required
def kick_member(league_id):
    db = get_db()
    league = require_admin(db, league_id)
    if league["status"] != "recruiting":
        raise ApiError("리그가 시작된 뒤에는 내보낼 수 없어요", 409)
    user_id = (request.get_json(silent=True) or {}).get("user_id")
    db.execute(
        "DELETE FROM membership WHERE league_id = ? AND user_id = ?", (league_id, user_id)
    )
    db.commit()
    return {"ok": True}


# ---------- 리그 입장 (F5): 6자리 코드로 들어간다. 한 학생은 리그 하나만 ----------
@app.post("/leagues/join")
@login_required
def join_league():
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip()
    if not re.fullmatch(r"[0-9]{6}", code):
        return {"error": "리그 코드는 6자리 숫자예요"}, 400

    db = get_db()
    if get_my_membership(db, current_user.id):
        return {"error": "이미 들어간 리그가 있어요"}, 409

    league = db.execute("SELECT * FROM league WHERE code = ?", (code,)).fetchone()
    if league is None:
        return {"error": "그런 코드의 리그가 없어요"}, 404
    if league["status"] != "recruiting":
        return {"error": "이미 시작했거나 끝난 리그예요"}, 409
    if league["max_members"]:
        count = db.execute(
            "SELECT COUNT(*) FROM membership WHERE league_id = ?", (league["id"],)
        ).fetchone()[0]
        if count >= league["max_members"]:
            return {"error": "리그 인원이 다 찼어요"}, 409

    db.execute(
        "INSERT INTO membership (league_id, user_id, joined_at) VALUES (?, ?, ?)",
        (league["id"], current_user.id, now_iso()),
    )
    db.commit()
    return {"ok": True, "league_id": league["id"]}


# ---------- 리그 나가기: 모집 중일 때만 ----------
@app.post("/leagues/leave")
@login_required
def leave_league():
    db = get_db()
    mem = get_my_membership(db, current_user.id)
    if mem is None:
        raise ApiError("들어간 리그가 없어요")
    league = get_league_or_404(db, mem["league_id"])
    if league["status"] != "recruiting":
        raise ApiError("리그가 시작된 뒤에는 나갈 수 없어요", 409)
    db.execute("DELETE FROM membership WHERE user_id = ?", (current_user.id,))
    db.commit()
    return {"ok": True}


# ---------- 리그 자세히 보기: 설정·명단·전체 일정·순위표 ----------
@app.get("/leagues/<int:league_id>")
@login_required
def league_detail(league_id):
    db = get_db()
    settle_league(db, league_id)
    league = get_league_or_404(db, league_id)
    is_admin = league["admin_id"] == current_user.id
    mem = get_my_membership(db, current_user.id)
    is_member = mem is not None and mem["league_id"] == league_id
    if not (is_admin or is_member):
        raise ApiError("이 리그에 들어간 사람만 볼 수 있어요", 403)

    members = db.execute(
        "SELECT u.id, u.nickname FROM membership m JOIN user u ON u.id = m.user_id "
        "WHERE m.league_id = ? ORDER BY m.joined_at ASC",
        (league_id,),
    ).fetchall()

    result = {
        "is_admin": is_admin,
        "is_member": is_member,
        "my_user_id": current_user.id,
        "now": now_iso(),
        "league": {
            "id": league["id"],
            "name": league["name"],
            "code": league["code"],
            "status": league["status"],
            "notice": league["notice"],
            "subjects": json.loads(league["subjects"] or "[]"),
            "rewards": json.loads(league["rewards"] or "[]"),
            "settings": league_settings_json(league),
            "questions_per_match": questions_needed(league),
        },
        "members": [{"id": m["id"], "nickname": m["nickname"]} for m in members],
    }
    if league["status"] == "recruiting":
        return result

    # 전체 일정 (주차별 경기·쉬는 사람·진행 상황)
    now = now_iso()
    names = nickname_map(db, league_id)
    made = {
        (r["author_id"], r["week"]): r["n"]
        for r in db.execute(
            "SELECT author_id, week, COUNT(*) AS n FROM question WHERE league_id = ? "
            "GROUP BY author_id, week",
            (league_id,),
        ).fetchall()
    }
    need = questions_needed(league)
    matches_by_week = {}
    for m in db.execute(
        "SELECT * FROM match WHERE league_id = ? ORDER BY week, id", (league_id,)
    ).fetchall():
        matches_by_week.setdefault(m["week"], []).append(m)

    rounds = []
    for r in db.execute(
        "SELECT * FROM round WHERE league_id = ? ORDER BY week", (league_id,)
    ).fetchall():
        phase = round_phase(r, now)
        games, bye = [], None
        for m in matches_by_week.get(r["week"], []):
            p1 = {"id": m["player1_id"], "nickname": names.get(m["player1_id"], "?")}
            if m["player2_id"] is None:
                bye = p1
                continue
            p2 = {"id": m["player2_id"], "nickname": names.get(m["player2_id"], "?")}
            finished = m["result"] is not None
            games.append(
                {
                    "id": m["id"],
                    "p1": p1,
                    "p2": p2,
                    "result": m["result"],
                    "forfeit": m["forfeit"],
                    # 점수는 경기가 끝난 뒤에만 공개
                    "p1_score": m["p1_score"] if finished else None,
                    "p2_score": m["p2_score"] if finished else None,
                    "p1_made": made.get((m["player1_id"], r["week"]), 0) >= need,
                    "p2_made": made.get((m["player2_id"], r["week"]), 0) >= need,
                    "p1_done": bool(m["p1_done"]),
                    "p2_done": bool(m["p2_done"]),
                }
            )
        rounds.append(
            {
                "week": r["week"],
                "start_at": r["start_at"],
                "make_deadline": r["make_deadline"],
                "solve_deadline": r["solve_deadline"],
                "phase": phase,
                "matches": games,
                "bye": bye,
            }
        )

    focus = focus_round(db, league_id)
    result["rounds"] = rounds
    result["total_weeks"] = len(rounds)
    result["focus_week"] = focus["week"] if focus else None
    result["standings"] = compute_standings(db, league)
    return result


# ---------- 리그 시작 (F6): 대진표·주차 일정 자동 생성 ----------
@app.post("/leagues/<int:league_id>/start")
@login_required
def start_league(league_id):
    db = get_db()
    league = require_admin(db, league_id)
    if league["status"] != "recruiting":
        raise ApiError("이미 시작했거나 끝난 리그예요", 409)

    player_ids = [
        m["user_id"]
        for m in db.execute(
            "SELECT user_id FROM membership WHERE league_id = ?", (league_id,)
        ).fetchall()
    ]
    if len(player_ids) < 2:
        raise ApiError("학생이 2명 이상 있어야 시작할 수 있어요")

    # 대진 추첨: 순서를 섞은 뒤 라운드 로빈. 2번씩이면 자리 바꿔 한 바퀴 더.
    random.shuffle(player_ids)
    rounds = make_round_robin(player_ids)
    if league["legs"] == 2:
        rounds += [[(b, a) if b is not None else (a, None) for a, b in r] for r in rounds]

    # 첫 경기 날짜가 이미 지났으면 오늘부터. 오늘 문제 만들기 마감이 지났으면 내일부터.
    first_day = today_kst()
    if league["start_date"]:
        first_day = max(first_day, date.fromisoformat(league["start_date"]))
    args = (len(rounds), league["round_days"], league["make_days"], league["deadline_time"])
    times = build_rounds(first_day, *args)
    while times[0][2] <= now_iso():
        first_day += timedelta(days=1)
        times = build_rounds(first_day, *args)

    for (week, s, mk, sv), pairs in zip(times, rounds):
        db.execute(
            "INSERT INTO round (league_id, week, start_at, make_deadline, solve_deadline) "
            "VALUES (?, ?, ?, ?, ?)",
            (league_id, week, s, mk, sv),
        )
        for p1, p2 in pairs:
            db.execute(
                "INSERT INTO match (league_id, week, player1_id, player2_id, result) "
                "VALUES (?, ?, ?, ?, ?)",
                (league_id, week, p1, p2, "bye" if p2 is None else None),
            )
    db.execute("UPDATE league SET status = 'running' WHERE id = ?", (league_id,))
    db.commit()
    return {"ok": True, "weeks": len(rounds), "first_day": first_day.isoformat()}


# ---------- 관리자: 이번 주차 단계를 바로 넘기기 ----------
# start_now: 시작 전 → 지금 시작 / open_solve: 문제 만들기 마감 → 풀기 시작 / close: 풀기 마감
@app.post("/leagues/<int:league_id>/advance")
@login_required
def advance_round(league_id):
    db = get_db()
    league = require_admin(db, league_id)
    settle_league(db, league_id)
    league = get_league_or_404(db, league_id)
    if league["status"] != "running":
        raise ApiError("진행 중인 리그가 아니에요", 409)
    r = focus_round(db, league_id)
    now = now_iso()
    phase = round_phase(r, now)
    action = (request.get_json(silent=True) or {}).get("action")

    if action == "start_now" and phase == "upcoming":
        # 이번 주차와 뒤 주차들을 하루 단위로 앞당긴다 (마감 시각은 그대로 유지).
        # 앞당긴 만들기 마감이 벌써 지나 버리면 하루씩 덜 당긴다.
        start_day = datetime.strptime(r["start_at"], "%Y-%m-%dT%H:%M:%SZ")
        start_day = start_day.replace(tzinfo=timezone.utc).astimezone(KST).date()
        days = (start_day - today_kst()).days
        make_dt = datetime.strptime(r["make_deadline"], "%Y-%m-%dT%H:%M:%SZ")
        make_dt = make_dt.replace(tzinfo=timezone.utc)
        while days > 0 and iso(make_dt - timedelta(days=days)) <= now:
            days -= 1
        if days > 0:
            shift = f"-{days} days"
            for col in ("start_at", "make_deadline", "solve_deadline"):
                db.execute(
                    f"UPDATE round SET {col} = strftime('%Y-%m-%dT%H:%M:%SZ', {col}, ?) "
                    "WHERE league_id = ? AND week >= ?",
                    (shift, league_id, r["week"]),
                )
        db.execute(
            "UPDATE round SET start_at = MIN(start_at, ?) WHERE id = ?", (now, r["id"])
        )
    elif action == "open_solve" and phase == "make":
        db.execute("UPDATE round SET make_deadline = ? WHERE id = ?", (now, r["id"]))
    elif action == "close" and phase == "solve":
        db.execute("UPDATE round SET solve_deadline = ? WHERE id = ?", (now, r["id"]))
    else:
        raise ApiError("지금 단계에서는 할 수 없어요. 새로고침해 주세요", 409)
    db.commit()
    settle_league(db, league_id)
    return {"ok": True}


# ---------- 이번 주 내 경기 (F8/F12) ----------
@app.get("/matches/current")
@login_required
def current_match():
    db = get_db()
    league = require_my_league(db)
    if league["status"] == "recruiting":
        return {"state": "recruiting"}

    r = focus_round(db, league["id"])
    now = now_iso()
    phase = round_phase(r, now)
    total_weeks = db.execute(
        "SELECT COUNT(*) FROM round WHERE league_id = ?", (league["id"],)
    ).fetchone()[0]
    base = {
        "state": league["status"],
        "week": r["week"],
        "total_weeks": total_weeks,
        "start_at": r["start_at"],
        "make_deadline": r["make_deadline"],
        "solve_deadline": r["solve_deadline"],
        "phase": phase,
        "now": now,
    }

    uid = current_user.id
    m = db.execute(
        "SELECT * FROM match WHERE league_id = ? AND week = ? "
        "AND (player1_id = ? OR player2_id = ?)",
        (league["id"], r["week"], uid, uid),
    ).fetchone()
    if m is None or m["player2_id"] is None:
        return {**base, "bye": True}

    is_p1, opp_id = my_side(m, uid)
    need = questions_needed(league)
    opp = db.execute("SELECT nickname FROM user WHERE id = ?", (opp_id,)).fetchone()
    i_done = bool(m["p1_done"] if is_p1 else m["p2_done"])
    finished = m["result"] is not None
    return {
        **base,
        "bye": False,
        "match_id": m["id"],
        "opponent": {"id": opp_id, "nickname": opp["nickname"]},
        "total": need,
        "my_made": made_count(db, league["id"], uid, r["week"]) >= need,
        "opp_made": made_count(db, league["id"], opp_id, r["week"]) >= need,
        "i_solved": i_done,
        "opp_solved": bool(m["p2_done"] if is_p1 else m["p1_done"]),
        "my_score": (m["p1_score"] if is_p1 else m["p2_score"]) if i_done else None,
        "opp_score": (m["p2_score"] if is_p1 else m["p1_score"]) if finished else None,
        "result": m["result"],
        "outcome": outcome_for(m, is_p1),
        "forfeit": m["forfeit"],
    }


def outcome_for(m, is_p1):
    """경기 결과를 내 입장에서: win/lose/draw/None(아직)."""
    r = m["result"]
    if r is None or r == "bye":
        return None
    if r == "draw":
        return "draw"
    if r == "both_lose":
        return "lose"
    return "win" if (r == "p1") == is_p1 else "lose"


# ---------- 이번 주 내가 만든 문제 불러오기 (F7) ----------
@app.get("/questions/mine")
@login_required
def my_questions():
    db = get_db()
    league = require_my_league(db)
    if league["status"] == "recruiting":
        raise ApiError("리그가 시작되면 문제를 만들 수 있어요", 409)
    r = focus_round(db, league["id"])
    uid = current_user.id
    m = db.execute(
        "SELECT * FROM match WHERE league_id = ? AND week = ? "
        "AND (player1_id = ? OR player2_id = ?)",
        (league["id"], r["week"], uid, uid),
    ).fetchone()
    if m is None or m["player2_id"] is None:
        raise ApiError("이번 주는 쉬는 주라 문제를 만들지 않아요", 409)
    _, opp_id = my_side(m, uid)
    opp = db.execute("SELECT nickname FROM user WHERE id = ?", (opp_id,)).fetchone()

    rows = db.execute(
        "SELECT subject, qtype, content, choices, answer, explanation FROM question "
        "WHERE league_id = ? AND author_id = ? AND week = ? ORDER BY id ASC",
        (league["id"], uid, r["week"]),
    ).fetchall()
    return {
        "week": r["week"],
        "opponent": opp["nickname"],
        "make_deadline": r["make_deadline"],
        "editable": now_iso() < r["make_deadline"],
        "subjects": json.loads(league["subjects"] or "[]"),
        "questions": [
            {
                "subject": q["subject"],
                "qtype": q["qtype"],
                "content": q["content"],
                "choices": json.loads(q["choices"] or "[]"),
                "answer": q["answer"],
                "explanation": q["explanation"],
            }
            for q in rows
        ],
    }


# ---------- 문제 저장 (F7): 문제 만들기 마감 전까지 몇 번이든 고칠 수 있다 ----------
@app.post("/questions")
@login_required
def save_questions():
    db = get_db()
    league = require_my_league(db)
    if league["status"] != "running":
        raise ApiError("진행 중인 리그에서만 문제를 만들 수 있어요", 409)
    r = focus_round(db, league["id"])
    if now_iso() >= r["make_deadline"]:
        raise ApiError("이번 주 문제 만들기 마감이 지났어요", 409)
    uid = current_user.id
    m = db.execute(
        "SELECT * FROM match WHERE league_id = ? AND week = ? "
        "AND (player1_id = ? OR player2_id = ?)",
        (league["id"], r["week"], uid, uid),
    ).fetchone()
    if m is None or m["player2_id"] is None:
        raise ApiError("이번 주는 쉬는 주라 문제를 만들지 않아요", 409)

    subjects = json.loads(league["subjects"] or "[]")
    need = {s["name"]: s["count"] for s in subjects}

    items = (request.get_json(silent=True) or {}).get("questions") or []
    if not isinstance(items, list):
        raise ApiError("문제 형식이 올바르지 않아요")

    got = {name: 0 for name in need}
    cleaned = []
    for q in items:
        if not isinstance(q, dict):
            raise ApiError("문제 형식이 올바르지 않아요")
        subject = (q.get("subject") or "").strip()
        qtype = q.get("qtype")
        content = (q.get("content") or "").strip()
        explanation = (q.get("explanation") or "").strip()

        if subject not in need:
            raise ApiError(f"'{subject}'는 이 리그의 과목이 아니에요")
        if qtype not in ("mc", "sa"):
            raise ApiError("문제 유형이 올바르지 않아요")
        if not (1 <= len(content) <= 1000):
            raise ApiError(f"[{subject}] 문제 내용을 넣어 주세요 (1~1000자)")
        if len(explanation) > 1000:
            raise ApiError("해설은 1000자까지예요")

        if qtype == "mc":
            choices = q.get("choices") or []
            if not isinstance(choices, list) or not (2 <= len(choices) <= 5):
                raise ApiError("객관식 보기는 2~5개여야 해요")
            choices = [str(c or "").strip() for c in choices]
            if any(len(c) == 0 or len(c) > 200 for c in choices):
                raise ApiError(f"[{subject}] 객관식 보기를 모두 채워 주세요 (200자까지)")
            try:
                ans_idx = int(q.get("answer"))
            except (TypeError, ValueError):
                raise ApiError("객관식 정답을 골라 주세요")
            if not (0 <= ans_idx < len(choices)):
                raise ApiError("객관식 정답 번호가 올바르지 않아요")
            cleaned.append(
                (subject, "mc", content, json.dumps(choices, ensure_ascii=False),
                 str(ans_idx), explanation)
            )
        else:
            answer = str(q.get("answer") or "").strip()
            if not (1 <= len(answer) <= 200):
                raise ApiError(f"[{subject}] 주관식 정답을 넣어 주세요")
            cleaned.append((subject, "sa", content, "[]", answer, explanation))
        got[subject] += 1

    # 과목별 개수가 정확히 맞아야 저장 (README 5번)
    for name, cnt in need.items():
        if got.get(name, 0) != cnt:
            raise ApiError(f"'{name}' 과목은 {cnt}문제를 만들어야 해요 (지금 {got.get(name, 0)}개)")

    # 이번 주 문제를 지우고 새로 저장 (풀기는 만들기 마감 뒤에 열리니 안전)
    db.execute(
        "DELETE FROM question WHERE league_id = ? AND author_id = ? AND week = ?",
        (league["id"], uid, r["week"]),
    )
    for subject, qtype, content, choices, answer, explanation in cleaned:
        db.execute(
            "INSERT INTO question (league_id, author_id, week, subject, qtype, content, "
            "choices, answer, explanation) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (league["id"], uid, r["week"], subject, qtype, content, choices, answer, explanation),
        )
    db.commit()
    return {"ok": True, "count": len(cleaned)}


def load_my_match_for_solving(db, match_id):
    """풀기용으로 내 경기를 확인한다. (경기, 리그, 내가 선수1인지, 상대 id)"""
    m = db.execute("SELECT * FROM match WHERE id = ?", (match_id,)).fetchone()
    if m is None:
        raise ApiError("경기를 찾을 수 없어요", 404)
    uid = current_user.id
    if uid not in (m["player1_id"], m["player2_id"]):
        raise ApiError("내 경기가 아니에요", 403)
    settle_league(db, m["league_id"])
    m = db.execute("SELECT * FROM match WHERE id = ?", (match_id,)).fetchone()
    league = get_league_or_404(db, m["league_id"])
    is_p1, opp_id = my_side(m, uid)
    if opp_id is None:
        raise ApiError("쉬는 주예요")
    return m, league, is_p1, opp_id


def check_can_solve(db, m, league, is_p1, opp_id):
    if m["p1_done"] if is_p1 else m["p2_done"]:
        raise ApiError("이미 푼 경기예요", 409)
    r = db.execute(
        "SELECT * FROM round WHERE league_id = ? AND week = ?", (league["id"], m["week"])
    ).fetchone()
    phase = round_phase(r, now_iso())
    if phase in ("upcoming", "make"):
        raise ApiError("문제 만들기 마감 뒤에 풀 수 있어요", 409)
    if phase == "done" or m["result"] is not None:
        raise ApiError("문제 풀기 마감이 지났어요", 409)
    if made_count(db, league["id"], opp_id, m["week"]) < questions_needed(league):
        raise ApiError("상대가 문제를 만들지 않아 풀 문제가 없어요 (상대 기권)", 409)


# ---------- 상대 문제 불러오기 (풀기용, 정답 숨김) (F8) ----------
@app.get("/matches/<int:match_id>/questions")
@login_required
def match_questions(match_id):
    db = get_db()
    m, league, is_p1, opp_id = load_my_match_for_solving(db, match_id)
    check_can_solve(db, m, league, is_p1, opp_id)
    rows = db.execute(
        "SELECT id, subject, qtype, content, choices FROM question "
        "WHERE league_id = ? AND author_id = ? AND week = ? ORDER BY id ASC",
        (league["id"], opp_id, m["week"]),
    ).fetchall()
    r = db.execute(
        "SELECT solve_deadline FROM round WHERE league_id = ? AND week = ?",
        (league["id"], m["week"]),
    ).fetchone()
    # 정답·해설은 보내지 않는다 (채점 후에만 보여 줌)
    return {
        "solve_deadline": r["solve_deadline"],
        "questions": [
            {
                "id": q["id"],
                "subject": q["subject"],
                "qtype": q["qtype"],
                "content": q["content"],
                "choices": json.loads(q["choices"] or "[]"),
            }
            for q in rows
        ],
    }


def graded_results(db, match_id, solver_id):
    """제출한 답과 정답·해설을 함께 돌려준다."""
    rows = db.execute(
        "SELECT q.id, q.subject, q.qtype, q.content, q.choices, q.answer, q.explanation, "
        "s.given, s.correct FROM submission s JOIN question q ON q.id = s.question_id "
        "WHERE s.match_id = ? AND s.solver_id = ? ORDER BY q.id ASC",
        (match_id, solver_id),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "subject": r["subject"],
            "qtype": r["qtype"],
            "content": r["content"],
            "choices": json.loads(r["choices"] or "[]"),
            "correct_answer": r["answer"],
            "given": r["given"],
            "is_correct": bool(r["correct"]),
            "explanation": r["explanation"],
        }
        for r in rows
    ]


# ---------- 답안 제출 + 자동 채점 (F8/F9) ----------
@app.post("/matches/<int:match_id>/submit")
@login_required
def submit_answers(match_id):
    db = get_db()
    m, league, is_p1, opp_id = load_my_match_for_solving(db, match_id)
    check_can_solve(db, m, league, is_p1, opp_id)

    answers = (request.get_json(silent=True) or {}).get("answers", {})
    if not isinstance(answers, dict):
        raise ApiError("답안 형식이 올바르지 않아요")

    # 두 번 눌러도 한 번만 들어가도록, '아직 안 냄'일 때만 제출 표시를 바꾼다
    done_col = "p1_done" if is_p1 else "p2_done"
    cur = db.execute(
        f"UPDATE match SET {done_col} = 1 WHERE id = ? AND {done_col} = 0", (match_id,)
    )
    if cur.rowcount != 1:
        db.rollback()
        raise ApiError("이미 제출했어요", 409)

    questions = db.execute(
        "SELECT id, qtype, answer FROM question "
        "WHERE league_id = ? AND author_id = ? AND week = ? ORDER BY id ASC",
        (league["id"], opp_id, m["week"]),
    ).fetchall()
    score = 0
    for q in questions:
        given = str(answers.get(str(q["id"]), ""))[:200]
        ok = grade_one(q, given)
        score += 1 if ok else 0
        db.execute(
            "INSERT INTO submission (match_id, solver_id, question_id, given, correct, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (match_id, current_user.id, q["id"], given, 1 if ok else 0, now_iso()),
        )
    score_col = "p1_score" if is_p1 else "p2_score"
    db.execute(f"UPDATE match SET {score_col} = ? WHERE id = ?", (score, match_id))

    # 둘 다 끝났으면 승·무·패 판정
    m = db.execute("SELECT * FROM match WHERE id = ?", (match_id,)).fetchone()
    finalize_match(db, league, m, by_deadline=False)
    db.commit()

    return {
        "ok": True,
        "score": score,
        "total": len(questions),
        "results": graded_results(db, match_id, current_user.id),
    }


# ---------- 내가 푼 경기 다시 보기 (정답·해설) ----------
@app.get("/matches/<int:match_id>/review")
@login_required
def review_match(match_id):
    db = get_db()
    m = db.execute("SELECT * FROM match WHERE id = ?", (match_id,)).fetchone()
    if m is None or current_user.id not in (m["player1_id"], m["player2_id"]):
        raise ApiError("내 경기가 아니에요", 403)
    results = graded_results(db, match_id, current_user.id)
    if not results:
        raise ApiError("아직 풀지 않은 경기예요", 404)
    return {
        "score": sum(1 for r in results if r["is_correct"]),
        "total": len(results),
        "results": results,
    }


init_db()


if __name__ == "__main__":
    app.run(debug=True)
