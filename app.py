import json
import os
import re
import secrets
import sqlite3
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from flask import Flask, g, jsonify, render_template, request
from flask_bcrypt import Bcrypt
from werkzeug.exceptions import HTTPException

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
# 세션(로그인 상태)을 지키는 데 쓰는 비밀키. .env의 SECRET_KEY를 쓴다 (코드에 적지 않는다).
_secret = os.environ.get("SECRET_KEY")
if not _secret:
    # .env가 없을 때만 임시 키를 만든다. 이 경우 앱이 다시 켜지면 로그인이 풀린다.
    _secret = secrets.token_hex(32)
    print("경고: .env에 SECRET_KEY가 없어 임시 비밀키를 씁니다")
app.secret_key = _secret

# 로그인을 연달아 틀릴 때 막는 기준 (SPEC 5. 보안·안전)
LOGIN_MAX_FAILS = 5
LOGIN_LOCK_SECONDS = 60

bcrypt = Bcrypt(app)
# 없는 아이디로 로그인할 때 검사용으로 쓰는 가짜 해시 (아래 login 참고)
DUMMY_PASSWORD_HASH = bcrypt.generate_password_hash(secrets.token_hex(16)).decode("utf-8")
login_manager = LoginManager(app)

DB_PATH = "app.db"


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


def init_db():
    with sqlite3.connect(DB_PATH) as db:
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
        # 리그 (F3): 관리자가 만든 리그. status = recruiting(모집 중)/running(진행 중)/finished(끝)
        # subjects: 과목·과목별 문제 수를 담은 JSON 문자열 (예: [{"name":"영어","count":3}])
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
        # 리그 참가 (F5): 어느 학생이 어느 리그에 들어갔는지. 한 학생은 리그 하나만(user_id UNIQUE)
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS membership (
                id INTEGER PRIMARY KEY,
                league_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                joined_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                left_at TEXT
            )
            """
        )
        # 대진/경기 (F6): 리그, 주차, 두 선수, 결과, 각자 점수
        # result = NULL(아직)/'p1'(선수1 승)/'p2'(선수2 승)/'draw'(무)
        # player2_id가 NULL이면 그 주는 부전승(상대가 없음)
        # p1_done/p2_done: 그 선수가 상대 문제를 다 풀어 제출했는지(0/1)
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
        # 문제 (F7): 만든 사람, 리그, 과목, 유형, 내용, 보기, 정답, 해설
        # qtype = 'mc'(객관식)/'sa'(주관식)
        # choices: 객관식 보기 JSON 배열 (주관식이면 '[]')
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

        # 라운드별 출제 범위 (F4-2): 따로 정하지 않은 라운드·과목은 리그의 기본 범위를 쓴다
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS round_scope (
                league_id INTEGER NOT NULL,
                round INTEGER NOT NULL,
                subject TEXT NOT NULL,
                scope TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (league_id, round, subject)
            )
            """
        )

        # --- 9단계 마이그레이션: 참가 기록을 활성/보관/내보냄으로 나눈다 ---
        # 예전 표는 user_id가 UNIQUE라서 리그가 끝나도 새 리그에 들어갈 수 없었다.
        # 표를 새로 만들고 예전 기록은 모두 'active'로 옮긴다 (지금 쓰는 사람에게는 바뀌는 것이 없다).
        mcols_m = [r[1] for r in db.execute("PRAGMA table_info(membership)").fetchall()]
        if "status" not in mcols_m:
            db.execute("ALTER TABLE membership RENAME TO membership_old")
            db.execute(
                """
                CREATE TABLE membership (
                    id INTEGER PRIMARY KEY,
                    league_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    joined_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    left_at TEXT
                )
                """
            )
            db.execute(
                "INSERT INTO membership (id, league_id, user_id, joined_at, status) "
                "SELECT id, league_id, user_id, joined_at, 'active' FROM membership_old"
            )
            db.execute("DROP TABLE membership_old")
        # 한 사람은 '활성' 참가 기록을 하나만 가질 수 있다 (보관·내보냄 기록은 여러 개 가능)
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS one_active_membership "
            "ON membership(user_id) WHERE status = 'active'"
        )
        db.execute("CREATE INDEX IF NOT EXISTS membership_league ON membership(league_id, status)")
        lcols = [r[1] for r in db.execute("PRAGMA table_info(league)").fetchall()]
        # 관리자가 끝난 리그를 [리그 닫기]하면 1 → 새 리그를 만들 수 있다 (기록은 남는다)
        if "admin_closed" not in lcols:
            db.execute("ALTER TABLE league ADD COLUMN admin_closed INTEGER NOT NULL DEFAULT 0")
        # 모집 중 [리그 삭제]하면 1 → 코드로 들어올 수 없고 어디에도 보이지 않는다
        if "deleted" not in lcols:
            db.execute("ALTER TABLE league ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0")
        # 학생을 내보내서 1명만 남아 일찍 끝난 경우의 종료 시각 (신고 판정 기한 계산용)
        if "ended_at" not in lcols:
            db.execute("ALTER TABLE league ADD COLUMN ended_at TEXT")

        # 로그인 실패 기록: 아이디별로 연달아 틀린 횟수와 막힌 시각
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS login_attempt (
                username TEXT PRIMARY KEY,
                fails INTEGER NOT NULL DEFAULT 0,
                locked_until TEXT
            )
            """
        )

        # 오답 노트 정리 (F18): [이제 알아요]로 표시한 문제
        # source = 'league'(리그 경기, qkey는 question.id)
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS wrong_note_known (
                user_id INTEGER NOT NULL,
                source TEXT NOT NULL,
                qkey TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (user_id, source, qkey)
            )
            """
        )

        # --- 간단 마이그레이션: 예전에 만든 league 테이블에 subjects 컬럼이 없으면 추가 ---
        cols = [r[1] for r in db.execute("PRAGMA table_info(league)").fetchall()]
        if "subjects" not in cols:
            db.execute(
                "ALTER TABLE league ADD COLUMN subjects TEXT NOT NULL DEFAULT '[]'"
            )
        # 경기 일정 (F4·F6): 경기 요일(JSON, 월=0 … 일=6)과 첫 경기 날짜(YYYY-MM-DD, 한국 날짜)
        if "match_days" not in cols:
            db.execute("ALTER TABLE league ADD COLUMN match_days TEXT NOT NULL DEFAULT '[]'")
            # 예전에 만든 모집 중 리그는 경기 요일이 없어서 시작할 수 없으므로 '월요일'로 채워 둔다
            db.execute("UPDATE league SET match_days = '[0]' WHERE status = 'recruiting'")
        if "first_date" not in cols:
            db.execute("ALTER TABLE league ADD COLUMN first_date TEXT")
        # 마감 시각(한국 시간 "HH:MM")과 문제 만들기 기간(일, 0 = 자동: 라운드의 절반)
        if "deadline_time" not in cols:
            db.execute("ALTER TABLE league ADD COLUMN deadline_time TEXT NOT NULL DEFAULT '23:59'")
        if "make_days" not in cols:
            db.execute("ALTER TABLE league ADD COLUMN make_days INTEGER NOT NULL DEFAULT 0")
        # 리그 기간 방식 (F4): 'full'(전체 리그) / 'short'(시험 대비 단기 리그)와 종료 희망일(한국 날짜)
        if "league_mode" not in cols:
            db.execute("ALTER TABLE league ADD COLUMN league_mode TEXT NOT NULL DEFAULT 'full'")
        if "end_date" not in cols:
            db.execute("ALTER TABLE league ADD COLUMN end_date TEXT")
        if "rewards" not in cols:
            db.execute(
                "ALTER TABLE league ADD COLUMN rewards TEXT NOT NULL DEFAULT '[]'"
            )
        # match 테이블에 제출여부 컬럼이 없으면 추가
        mcols = [r[1] for r in db.execute("PRAGMA table_info(match)").fetchall()]
        if "p1_done" not in mcols:
            db.execute("ALTER TABLE match ADD COLUMN p1_done INTEGER DEFAULT 0")
        if "p2_done" not in mcols:
            db.execute("ALTER TABLE match ADD COLUMN p2_done INTEGER DEFAULT 0")
        # 문제 상태 (F7): 'draft'(만드는 중) / 'done'(완성). 마지막 임시 저장 시각
        for col, ddl in (("p1_state", "TEXT NOT NULL DEFAULT 'draft'"), ("p2_state", "TEXT NOT NULL DEFAULT 'draft'"),
                         ("p1_saved_at", "TEXT"), ("p2_saved_at", "TEXT")):
            if col not in mcols:
                db.execute(f"ALTER TABLE match ADD COLUMN {col} {ddl}")
        # 몰수 경기 (F14): 1이면 마감을 어겨 끝난 경기. 점수는 순위(맞힌 수·득실차)에 넣지 않는다
        # forfeit_stage: 'make'(만들기 마감) / 'solve'(풀기 마감)
        if "forfeit" not in mcols:
            db.execute("ALTER TABLE match ADD COLUMN forfeit INTEGER NOT NULL DEFAULT 0")
        if "forfeit_stage" not in mcols:
            db.execute("ALTER TABLE match ADD COLUMN forfeit_stage TEXT")
        # 문제는 경기(라운드 상대)마다 새로 만든다 → 어느 경기용인지 기록
        # (예전 리그의 문제는 match_id가 비어 있고, 새 경기에는 쓰이지 않는다)
        qcols = [r[1] for r in db.execute("PRAGMA table_info(question)").fetchall()]
        if "match_id" not in qcols:
            db.execute("ALTER TABLE question ADD COLUMN match_id INTEGER")
        # 무효 문제 (F17): 관리자가 [무효]로 판정하면 1, 이유는 신고 이유
        if "void" not in qcols:
            db.execute("ALTER TABLE question ADD COLUMN void INTEGER NOT NULL DEFAULT 0")
        if "void_reason" not in qcols:
            db.execute("ALTER TABLE question ADD COLUMN void_reason TEXT")
        # 문제 신고 (F17): 한 문제는 푼 학생 한 명만 한 번 신고한다
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS report (
                id INTEGER PRIMARY KEY,
                league_id INTEGER NOT NULL,
                match_id INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                reporter_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                decided_at TEXT,
                UNIQUE (question_id, reporter_id)
            )
            """
        )
        # 라운드 시각 (UTC ISO): 라운드 시작 / 문제 만들기 마감 / 풀기 마감(= 라운드 끝)
        for col in ("round_start", "make_deadline", "solve_deadline"):
            if col not in mcols:
                db.execute(f"ALTER TABLE match ADD COLUMN {col} TEXT")


init_db()


def gen_league_code(db):
    """서로 겹치지 않는 6자리 숫자 코드를 만든다 (SPEC 5번)."""
    import random

    for _ in range(100):
        code = f"{random.randint(0, 999999):06d}"
        exists = db.execute(
            "SELECT 1 FROM league WHERE code = ?", (code,)
        ).fetchone()
        if not exists:
            return code
    raise RuntimeError("리그 코드를 만들지 못했어요")


def get_admin_league(db, user_id):
    """내가 관리자인 '지금' 리그 (닫거나 삭제한 리그는 빼고, 없으면 None)."""
    return db.execute(
        "SELECT id FROM league WHERE admin_id = ? AND admin_closed = 0 AND deleted = 0 "
        "ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()


def same_nickname(a, b):
    """닉네임이 같은지 (대소문자·띄어쓰기는 무시). '김민준'과 '김 민준'도 같다고 본다."""
    return "".join(a.split()).lower() == "".join(b.split()).lower()


def nickname_taken_in_league(db, league_id, nickname, except_user_id):
    """그 리그에 같은 닉네임을 쓰는 다른 학생이 있으면 True."""
    rows = db.execute(
        "SELECT u.id, u.nickname FROM membership m JOIN user u ON u.id = m.user_id "
        "WHERE m.league_id = ? AND m.status != 'removed'",
        (league_id,),
    ).fetchall()
    return any(
        r["id"] != except_user_id and same_nickname(r["nickname"], nickname)
        for r in rows
    )


def get_my_membership(db, user_id):
    """내가 들어간 리그 참가 정보를 돌려준다 (없으면 None)."""
    return db.execute(
        "SELECT league_id FROM membership WHERE user_id = ? AND status = 'active'", (user_id,)
    ).fetchone()


def make_round_robin(player_ids):
    """
    모두가 서로 한 번씩 붙는 대진표를 만든다 (라운드 로빈).
    돌려주는 값: [[(a, b), (c, d), ...], ...]  (주차별 경기 목록)
    사람이 홀수면 한 명은 그 주 부전승(상대가 None).
    """
    players = list(player_ids)
    if len(players) < 2:
        return []

    # 홀수면 가짜 선수(None)를 넣어 짝을 맞춘다. 이 선수와 만나면 부전승.
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
                # 부전승: 실제 선수를 player1로 두고 상대는 None
                real = a if a is not None else b
                if real is not None:
                    pairs.append((real, None))
            else:
                pairs.append((a, b))
        rounds.append(pairs)
        # 회전: 맨 앞(arr[0])은 고정, 나머지를 한 칸씩 돌린다
        arr = [arr[0]] + [arr[-1]] + arr[1:-1]
    return rounds


# ---------- 경기 일정 계산 (SPEC 5. 경기 일정) ----------
KST = ZoneInfo("Asia/Seoul")  # 모든 날짜는 한국 시간 기준
WEEKDAY_NAMES = ["월", "화", "수", "목", "금", "토", "일"]
# 오늘 바로 시작할 때, 1라운드 문제 만들기 마감까지 최소로 남아 있어야 하는 시간
TODAY_MIN_MAKE_HOURS = 3
FIRST_DATE_MAX_DAYS = 60  # 너무 먼 날은 못 고르게 (약 두 달)
# 관리자가 고를 수 있는 마감 시각 (문제 만들기·풀기 마감에 똑같이 쓴다)
DEADLINE_TIMES = ["18:00", "19:00", "20:00", "21:00", "22:00", "23:00", "23:59"]


def today_kst():
    return datetime.now(KST).date()


def validate_match_days(raw):
    """경기 요일 검사. 맞으면 (정렬된 목록, None), 틀리면 (None, 안내 글)."""
    if not isinstance(raw, list) or not raw:
        return None, "경기 요일을 하나 이상 골라 주세요"
    if any(not isinstance(d, int) or isinstance(d, bool) or not 0 <= d <= 6 for d in raw):
        return None, "경기 요일 형식이 올바르지 않아요"
    days = sorted(set(raw))
    if len(days) > 3:
        return None, "경기 요일은 1주일에 3번까지 고를 수 있어요"
    # 경기 요일끼리 하루 이상 띄우기 (일요일 다음은 월요일이라 한 바퀴 돌려서도 본다)
    if len(days) > 1:
        gaps = [b - a for a, b in zip(days, days[1:])] + [days[0] + 7 - days[-1]]
        if min(gaps) < 2:
            return None, "경기 요일끼리는 하루 이상 띄워 주세요 (예: 월·화는 안 돼요)"
    return days, None


def shortest_round_days(days):
    """경기 요일로 생기는 라운드 중 가장 짧은 라운드의 날 수 (요일 하나면 7일)."""
    if len(days) == 1:
        return 7
    return min([b - a for a, b in zip(days, days[1:])] + [days[0] + 7 - days[-1]])


def validate_make_days(raw, days):
    """문제 만들기 기간 검사. 0 = 자동. 풀기 기간이 하루는 남아야 한다."""
    if raw is None:
        return 0, None
    if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
        return None, "문제 만들기 기간 형식이 올바르지 않아요"
    longest = shortest_round_days(days) - 1
    if raw > longest:
        return None, f"이 경기 요일이면 문제 만들기 기간은 {longest}일까지 고를 수 있어요 (풀기 기간이 하루는 있어야 해요)"
    return raw, None


SCOPE_MAX = 100        # 출제 범위 글자 수
END_DATE_MAX_DAYS = 365  # 종료 희망일은 1년 안


def clean_scope(raw):
    """출제 범위 글자 검사. 맞으면 (정리된 글자, None), 틀리면 (None, 안내 글)."""
    if not isinstance(raw, str):
        return None, "출제 범위를 적어 주세요 (제한하지 않으려면 '자유 출제')"
    text = " ".join(raw.split())  # 줄바꿈·여러 칸 띄어쓰기를 한 칸으로
    if not (1 <= len(text) <= SCOPE_MAX):
        return None, f"출제 범위는 1~{SCOPE_MAX}자로 적어 주세요 (제한하지 않으려면 '자유 출제')"
    return text, None


def rounds_until(first, days, make_days, deadline_time, end_date, max_rounds):
    """
    시험 대비 단기 리그: end_date(종료 희망일, 그날 마감 시각까지) 안에 완전히 끝나는 라운드 수.
    전체 라운드 수(max_rounds)보다 많아질 수는 없다 (같은 상대와 두 번 붙지 않게).
    """
    if end_date is None or first > end_date:
        return 0
    limit = datetime.fromisoformat(kst_deadline_utc(end_date, deadline_time))
    sched = build_schedule(first, days, max_rounds, make_days)
    n = 0
    for r in sched:
        if datetime.fromisoformat(kst_deadline_utc(r["last"], deadline_time)) <= limit:
            n += 1
        else:
            break
    return n


def round_count(n_players):
    """N명이면 짝수일 때 N-1라운드, 홀수일 때 N라운드."""
    if n_players < 2:
        return 0
    return n_players - 1 if n_players % 2 == 0 else n_players


def match_dates_from(first, days, count):
    """first부터 시작해 경기 요일인 날짜를 count개 모은다."""
    out, d = [], first
    while len(out) < count:
        if d.weekday() in days:
            out.append(d)
        d += timedelta(days=1)
    return out


def build_schedule(first, days, n_rounds, make_days=0):
    """
    라운드별 날짜 (모두 한국 날짜).
    start: 라운드 시작일(0시), make_last: 만들기 마지막 날, last: 라운드 마지막 날 (= 다음 경기 요일 전날)
    make_days가 0이면 라운드 앞쪽 절반(버림, 최소 1일)이 만들기, 아니면 그 날 수만큼.
    """
    if n_rounds <= 0:
        return []
    # 마지막 라운드 끝을 알려고 하나 더. 첫날이 경기 요일이 아니면(오늘 바로 시작) 그날이 1라운드 시작
    starts = match_dates_from(first, days, n_rounds + 1)
    if first.weekday() not in days:
        starts = [first] + starts[:n_rounds]
    rounds = []
    for i in range(n_rounds):
        start, nxt = starts[i], starts[i + 1]
        length = (nxt - start).days
        make = make_days if make_days > 0 else max(1, length // 2)
        make = min(make, length - 1)  # 풀기 기간이 하루는 남게
        rounds.append({"round": i + 1, "start": start,
                       "make_last": start + timedelta(days=make - 1),
                       "last": nxt - timedelta(days=1)})
    return rounds


def kst_midnight_utc(d):
    """한국 날짜 d의 0시를 UTC ISO 글자로 (DB 저장용)."""
    return datetime(d.year, d.month, d.day, tzinfo=KST).astimezone(timezone.utc).isoformat()


def kst_deadline_utc(d, hhmm):
    """한국 날짜 d의 마감 시각을 UTC ISO 글자로. '23:59'는 다음 날 0시 직전까지로 본다."""
    if hhmm == "23:59":
        return kst_midnight_utc(d + timedelta(days=1))
    h, m = map(int, hhmm.split(":"))
    return datetime(d.year, d.month, d.day, h, m, tzinfo=KST).astimezone(timezone.utc).isoformat()


def can_start_today(days, make_days=0, deadline_time="23:59"):
    """
    오늘 바로 시작할 수 있는지 (경기 요일이 아니어도 된다).
    1라운드에 만들기·풀기가 하루씩은 있어야 하고, 만들기 마감까지 몇 시간은 남아야 한다.
    """
    today = today_kst()
    rnd = build_schedule(today, days, 1, make_days)[0]
    if (rnd["last"] - rnd["start"]).days + 1 < 2:
        return False
    make_end = datetime.fromisoformat(kst_deadline_utc(rnd["make_last"], deadline_time))
    return make_end - now_utc() >= timedelta(hours=TODAY_MIN_MAKE_HOURS)


def first_date_choices(days, make_days=0, deadline_time="23:59"):
    """첫 경기로 고를 수 있는 날짜들. 오늘(가능하면) + 내일 이후 경기 요일 8개. 첫 번째가 기본값."""
    today = today_kst()
    limit = today + timedelta(days=FIRST_DATE_MAX_DAYS)
    later = [d for d in match_dates_from(today + timedelta(days=1), days, 8) if d <= limit]
    return ([today] if can_start_today(days, make_days, deadline_time) else []) + later


def compute_standings(db, league_id):
    """
    순위표 계산 (F11).
    - 전체 리그: 총 승점 → 총 득실차 → 맞힌 문제 수 → 닉네임
    - 시험 대비 단기 리그: 경기당 평균 승점 → 경기당 평균 득실차 → 정답률 → 닉네임
    몰수 경기는 경기 수·승패에는 포함하지만 점수와 득실차는 0:0으로 본다.
    """
    league = db.execute(
        "SELECT league_mode FROM league WHERE id = ?", (league_id,)
    ).fetchone()
    mode = league["league_mode"] if league and league["league_mode"] in ("full", "short") else "full"
    members = db.execute(
        """
        SELECT u.id, u.nickname
        FROM membership m JOIN user u ON u.id = m.user_id
        WHERE m.league_id = ? AND m.status != 'removed'
        """,
        (league_id,),
    ).fetchall()

    stats = {
        m["id"]: {
            "user_id": m["id"], "nickname": m["nickname"],
            "played": 0, "win": 0, "draw": 0, "lose": 0,
            "points": 0, "scored": 0, "against": 0, "goal_diff": 0,
            "correct": 0, "attempted": 0, "accuracy": 0.0,
            "points_per_game": 0.0, "goal_diff_per_game": 0.0,
        }
        for m in members
    }

    matches = db.execute(
        "SELECT player1_id, player2_id, result, p1_score, p2_score, forfeit "
        "FROM match WHERE league_id = ? AND result IS NOT NULL",
        (league_id,),
    ).fetchall()
    for mt in matches:
        p1, p2 = mt["player1_id"], mt["player2_id"]
        if p2 is None:
            continue  # 쉬는 라운드는 경기 수·승점에 영향 없음
        if p1 not in stats or p2 not in stats:
            continue  # 내보낸 학생과의 경기는 양쪽 모두 순위에서 뺀다 (기록 지우기 방식)
        s1 = 0 if mt["forfeit"] else (mt["p1_score"] or 0)
        s2 = 0 if mt["forfeit"] else (mt["p2_score"] or 0)
        if p1 in stats:
            stats[p1]["played"] += 1
            stats[p1]["scored"] += s1
            stats[p1]["against"] += s2
        if p2 in stats:
            stats[p2]["played"] += 1
            stats[p2]["scored"] += s2
            stats[p2]["against"] += s1
        if mt["result"] == "p1":
            if p1 in stats:
                stats[p1]["win"] += 1; stats[p1]["points"] += 3
            if p2 in stats:
                stats[p2]["lose"] += 1
        elif mt["result"] == "p2":
            if p2 in stats:
                stats[p2]["win"] += 1; stats[p2]["points"] += 3
            if p1 in stats:
                stats[p1]["lose"] += 1
        elif mt["result"] == "draw":
            if p1 in stats:
                stats[p1]["draw"] += 1; stats[p1]["points"] += 1
            if p2 in stats:
                stats[p2]["draw"] += 1; stats[p2]["points"] += 1
        elif mt["result"] == "both_lose":
            for p in (p1, p2):
                if p in stats:
                    stats[p]["lose"] += 1

    # 정답률: 정상 경기에서 실제 제출한 문제만 센다. 몰수 경기는 제외한다.
    answers = db.execute(
        "SELECT s.solver_id, COUNT(*) AS attempted, SUM(s.correct) AS correct "
        "FROM submission s JOIN match mt ON mt.id = s.match_id JOIN question q ON q.id = s.question_id "
        "WHERE mt.league_id = ? AND mt.result IS NOT NULL AND mt.forfeit = 0 AND q.void = 0 "
        "AND NOT EXISTS (SELECT 1 FROM membership r WHERE r.league_id = mt.league_id "
        "AND r.status = 'removed' AND r.user_id IN (mt.player1_id, mt.player2_id)) "
        "GROUP BY s.solver_id",
        (league_id,),
    ).fetchall()
    for row in answers:
        uid = row["solver_id"]
        if uid in stats:
            stats[uid]["attempted"] = row["attempted"] or 0
            stats[uid]["correct"] = row["correct"] or 0

    for row in stats.values():
        row["goal_diff"] = row["scored"] - row["against"]
        if row["played"]:
            row["points_per_game"] = row["points"] / row["played"]
            row["goal_diff_per_game"] = row["goal_diff"] / row["played"]
        if row["attempted"]:
            row["accuracy"] = row["correct"] / row["attempted"]

    if mode == "short":
        key = lambda r: (-r["points_per_game"], -r["goal_diff_per_game"],
                         -r["accuracy"], r["nickname"])
    else:
        key = lambda r: (-r["points"], -r["goal_diff"], -r["scored"], r["nickname"])
    table = sorted(stats.values(), key=key)
    for i, row in enumerate(table, start=1):
        row["rank"] = i
    return table

def total_weeks(db, league_id):
    """이 리그의 전체 주차 수 (대진표에서 가장 큰 week)."""
    row = db.execute(
        "SELECT MAX(week) AS w FROM match WHERE league_id = ?", (league_id,)
    ).fetchone()
    return row["w"] or 0


def now_utc():
    """지금 시각 (UTC). 시험할 때 시간을 바꿀 수 있게 함수로 둔다."""
    return datetime.now(timezone.utc)


def parse_utc(iso):
    return datetime.fromisoformat(iso) if iso else None


def round_rows(db, league_id):
    return db.execute(
        "SELECT week, MIN(round_start) AS rs, MIN(make_deadline) AS md, MIN(solve_deadline) AS sd "
        "FROM match WHERE league_id = ? GROUP BY week ORDER BY week",
        (league_id,),
    ).fetchall()


def current_round(db, league_id):
    """
    지금 라운드 번호. 날짜가 있는 리그는 시간으로 정한다:
    풀기 마감이 아직 안 지난 첫 라운드 (첫 라운드 시작 전이면 1, 모두 지났으면 마지막).
    날짜가 없는 예전 리그는 결과가 안 난 첫 라운드 (쉬는 경기는 빼고 센다).
    """
    rows = round_rows(db, league_id)
    if not rows:
        return 0
    if rows[0]["rs"] is None:
        r = db.execute(
            "SELECT MIN(week) AS w FROM match WHERE league_id = ? "
            "AND result IS NULL AND player2_id IS NOT NULL",
            (league_id,),
        ).fetchone()
        return r["w"] or rows[-1]["week"]
    now = now_utc()
    for r in rows:
        if now < parse_utc(r["sd"]):
            return r["week"]
    return rows[-1]["week"]


def settle_deadlines(db, league_id):
    """
    마감 자동 처리 (F14). 마감이 지났는데 결과가 안 난 경기를 규칙대로 끝낸다.
    - 만들기 마감까지 [완성]을 안 누른 쪽 몰수패 (둘 다면 둘 다 패)
    - 풀기 마감까지 제출 안 한 쪽 몰수패 (둘 다면 둘 다 패)
    사람이 버튼을 누르지 않아도, 누군가 리그 화면을 열 때마다 확인한다.
    날짜가 없는 예전 리그의 경기는 건드리지 않는다.
    """
    now = now_utc().isoformat()
    pending = db.execute(
        "SELECT COUNT(*) FROM match WHERE league_id = ? AND result IS NULL AND player2_id IS NOT NULL "
        "AND make_deadline IS NOT NULL AND make_deadline <= ?",
        (league_id, now),
    ).fetchone()[0]
    if not pending:
        return
    lock_db(db)  # 여러 사람이 동시에 열어도 한 번만 처리되게
    now_dt = now_utc()
    rows = db.execute(
        "SELECT * FROM match WHERE league_id = ? AND result IS NULL AND player2_id IS NOT NULL "
        "AND make_deadline IS NOT NULL",
        (league_id,),
    ).fetchall()
    for m in rows:
        if now_dt < parse_utc(m["make_deadline"]):
            continue
        ok1, ok2 = m["p1_state"] == "done", m["p2_state"] == "done"
        stage = None
        if not (ok1 and ok2):
            stage = "make"
        elif now_dt >= parse_utc(m["solve_deadline"]):
            ok1, ok2 = bool(m["p1_done"]), bool(m["p2_done"])
            if ok1 and ok2:
                finalize_match_if_ready(db, m["id"])  # 둘 다 냈으면 원래대로 점수로 판정
                continue
            stage = "solve"
        if stage is None:
            continue
        result = "p1" if ok1 and not ok2 else "p2" if ok2 and not ok1 else "both_lose"
        db.execute(
            "UPDATE match SET result = ?, forfeit = 1, forfeit_stage = ? WHERE id = ? AND result IS NULL",
            (result, stage, m["id"]),
        )
    db.commit()


REPORT_JUDGE_DAYS = 3  # 리그가 끝난 뒤 관리자가 신고를 판정할 수 있는 기간 (일)


def league_end_time(db, league_id):
    """리그가 끝난 시각 (UTC): 일찍 끝났으면 그 시각, 아니면 마지막 라운드 풀기 마감. 날짜가 없는 예전 리그는 None."""
    row = db.execute("SELECT ended_at FROM league WHERE id = ?", (league_id,)).fetchone()
    if row and row["ended_at"]:
        return parse_utc(row["ended_at"])
    rows = round_rows(db, league_id)
    return parse_utc(rows[-1]["sd"]) if rows and rows[-1]["sd"] else None


def report_deadline(db, league_id):
    """신고 판정 마감 = 리그가 끝난 뒤 3일. 이때까지 판정하지 않은 신고는 자동으로 '문제없음'."""
    end = league_end_time(db, league_id)
    return end + timedelta(days=REPORT_JUDGE_DAYS) if end else None


def settle_reports(db, league_id):
    """판정 기한이 지나면 남은 신고를 '문제없음(자동)'으로 닫는다. 점수는 바뀌지 않는다."""
    deadline = report_deadline(db, league_id)
    if deadline is None or now_utc() < deadline:
        return
    left = db.execute(
        "SELECT COUNT(*) FROM report WHERE league_id = ? AND status = 'pending'", (league_id,)
    ).fetchone()[0]
    if left:
        db.execute(
            "UPDATE report SET status = 'auto_ok', decided_at = ? WHERE league_id = ? AND status = 'pending'",
            (now_iso(), league_id),
        )
        db.commit()


def recompute_match(db, match_id):
    """
    무효 문제를 반영해 두 학생의 점수와 결과를 다시 계산한다.
    무효 문제는 푼 학생이 맞힌 것으로 친다 (1점 인정). 몰수 경기는 0:0이라 결과가 바뀌지 않는다.
    """
    m = db.execute("SELECT * FROM match WHERE id = ?", (match_id,)).fetchone()
    if m is None or m["player2_id"] is None:
        return
    for me, solver, author in (("p1", m["player1_id"], m["player2_id"]),
                               ("p2", m["player2_id"], m["player1_id"])):
        if not m[f"{me}_done"]:
            continue
        score = db.execute(
            "SELECT COUNT(*) FROM question q JOIN submission s "
            "ON s.question_id = q.id AND s.match_id = q.match_id AND s.solver_id = ? "
            "WHERE q.match_id = ? AND q.author_id = ? AND (s.correct = 1 OR q.void = 1)",
            (solver, match_id, author),
        ).fetchone()[0]
        db.execute(f"UPDATE match SET {me}_score = ? WHERE id = ?", (score, match_id))
    m = db.execute("SELECT * FROM match WHERE id = ?", (match_id,)).fetchone()
    if m["result"] is not None and not m["forfeit"] and m["p1_done"] and m["p2_done"]:
        s1, s2 = m["p1_score"], m["p2_score"]
        result = "p1" if s1 > s2 else "p2" if s2 > s1 else "draw"
        db.execute("UPDATE match SET result = ? WHERE id = ?", (result, match_id))


def refresh_league(db, league_id):
    """마감 처리를 하고, 진행 중인 리그가 끝났는지 보고 끝났으면 상태를 '끝'으로 바꾼다 (요청이 올 때마다 확인)."""
    league = db.execute("SELECT status FROM league WHERE id = ?", (league_id,)).fetchone()
    if league is not None and league["status"] == "finished":
        settle_reports(db, league_id)
        return
    if league is None or league["status"] != "running":
        return
    settle_deadlines(db, league_id)
    rows = round_rows(db, league_id)
    if not rows:
        return
    if rows[0]["rs"] is None:
        left = db.execute(
            "SELECT COUNT(*) FROM match WHERE league_id = ? AND result IS NULL AND player2_id IS NOT NULL",
            (league_id,),
        ).fetchone()[0]
        finished = left == 0
    else:
        finished = now_utc() >= parse_utc(rows[-1]["sd"])
    if finished:
        db.execute("UPDATE league SET status = 'finished' WHERE id = ?", (league_id,))
        db.commit()


def now_iso():
    return now_utc().isoformat()  # 시각은 모두 now_utc() 하나로 정한다


# ---------- 입력 받기 도우미 (이상한 입력이 와도 멈추지 않게) ----------
def read_json():
    """요청 본문을 dict로 읽는다. JSON이 아니거나 dict가 아니면 빈 dict."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def text_of(obj, key):
    """obj[key]가 글자면 앞뒤 공백을 지워 돌려주고, 아니면(숫자·목록·없음) 빈 글자."""
    value = obj.get(key) if isinstance(obj, dict) else None
    return value.strip() if isinstance(value, str) else ""


def lock_db(db):
    """
    '검사하고 저장하기' 사이에 다른 요청이 끼어들지 못하게 DB 쓰기를 잠근다.
    (버튼을 여러 번 빨리 눌러도 두 번 저장되거나 오류가 나지 않게)
    commit하거나 요청이 끝나면 자동으로 풀린다.
    """
    if not db.in_transaction:
        db.execute("BEGIN IMMEDIATE")


def normalize_sa(text):
    """주관식 비교용: 띄어쓰기 모두 제거 + 소문자로 (SPEC 규칙)."""
    return "".join((text or "").split()).lower()


def grade_one(question_row, given):
    """문제 하나 채점. 맞으면 True."""
    if question_row["qtype"] == "mc":
        try:
            return int(given) == int(question_row["answer"])
        except (TypeError, ValueError):
            return False
    else:  # 주관식
        return normalize_sa(given) == normalize_sa(question_row["answer"])


def finalize_match_if_ready(db, match_id):
    """
    두 선수가 모두 제출했으면 승·무·패를 정하고 result를 채운다 (F10).
    한쪽만 제출했으면 아무것도 안 한다.
    """
    m = db.execute(
        "SELECT player1_id, player2_id, p1_done, p2_done, p1_score, p2_score, result "
        "FROM match WHERE id = ?",
        (match_id,),
    ).fetchone()
    if m is None or m["result"] is not None:
        return
    if m["player2_id"] is None:
        return  # 부전승(쉬는 주)은 결과 없음
    if not (m["p1_done"] and m["p2_done"]):
        return  # 아직 둘 다 안 끝남

    s1, s2 = m["p1_score"], m["p2_score"]
    if s1 > s2:
        result = "p1"
    elif s2 > s1:
        result = "p2"
    else:
        result = "draw"
    db.execute("UPDATE match SET result = ? WHERE id = ?", (result, match_id))


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


# ---------- 오류가 나도 알아듣기 쉬운 안내를 JSON으로 돌려준다 ----------
HTTP_ERROR_TEXT = {
    400: "요청 형식이 올바르지 않아요",
    404: "없는 주소예요",
    405: "이 주소에서는 할 수 없는 동작이에요",
    413: "보낸 내용이 너무 커요",
    415: "요청 형식이 올바르지 않아요",
}


@app.errorhandler(HTTPException)
def handle_http_error(e):
    return {"error": HTTP_ERROR_TEXT.get(e.code, "요청을 처리하지 못했어요")}, e.code


@app.errorhandler(Exception)
def handle_unexpected_error(e):
    # 생각 못 한 오류: 기록(app.log)은 남기고, 화면에는 쉬운 안내만 보여 준다
    app.logger.exception("처리하지 못한 오류")
    return {"error": "잠시 문제가 생겼어요. 다시 시도해 주세요"}, 500


# ---------- PWA (앱 설치): 서비스 워커는 사이트 전체를 다뤄야 해서 / 에서 준다 ----------
@app.get("/sw.js")
def service_worker():
    res = app.send_static_file("sw.js")
    res.headers["Content-Type"] = "application/javascript; charset=utf-8"
    res.headers["Cache-Control"] = "no-cache"  # 새 버전이 바로 반영되게
    res.headers["Service-Worker-Allowed"] = "/"
    return res


@app.get("/favicon.ico")
def favicon():
    return app.send_static_file("icon-192.png")


# ---------- 화면 ----------
@app.get("/")
def index():
    return render_template("index.html")


# ---------- 로그인 상태 확인 ----------
@app.get("/me")
def me():
    if current_user.is_authenticated:
        return {"logged_in": True, "nickname": current_user.nickname}
    return {"logged_in": False}


# ---------- 회원가입 (F1) ----------
@app.post("/register")
def register():
    data = read_json()
    username = text_of(data, "username")
    password = data.get("password") if isinstance(data.get("password"), str) else ""
    nickname = text_of(data, "nickname")

    # 입력 검사 (SPEC F1)
    if not re.fullmatch(r"[A-Za-z0-9]{4,20}", username):
        return {"error": "아이디는 영문·숫자 4~20자여야 해요"}, 400
    if not (8 <= len(password) <= 64):
        return {"error": "비밀번호는 8~64자여야 해요"}, 400
    if not (1 <= len(nickname) <= 10):
        return {"error": "닉네임은 1~10자여야 해요"}, 400

    # 해시 만들기는 시간이 걸려서 DB를 잠그기 전에 한다
    password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    db = get_db()
    lock_db(db)
    exists = db.execute(
        "SELECT 1 FROM user WHERE username = ?", (username,)
    ).fetchone()
    if exists:
        return {"error": "이미 쓰고 있는 아이디예요"}, 409

    cur = db.execute(
        "INSERT INTO user (username, password_hash, nickname, created_at) VALUES (?, ?, ?, ?)",
        (username, password_hash, nickname, now_iso()),
    )
    db.commit()
    # 가입하면 바로 로그인 (SPEC 4. 화면: 로그인을 한 번 더 하지 않아도 된다)
    login_user(User(cur.lastrowid, username, nickname), remember=True)
    return {"ok": True, "nickname": nickname}, 201


# ---------- 로그인 (F2) ----------
@app.post("/login")
def login():
    data = read_json()
    username = text_of(data, "username")
    password = data.get("password") if isinstance(data.get("password"), str) else ""

    # 아이디가 있든 없든, 형식이 맞든 틀리든 똑같이 횟수를 센다
    # (다르게 대답하면 "이 아이디는 있다"는 걸 알려 주는 셈이 되기 때문)
    attempt_key = username[:64]  # 아주 긴 글자가 와도 기록이 커지지 않게

    db = get_db()
    now = datetime.now(timezone.utc)

    # 지금 막혀 있는 아이디인지 확인 (5번 연달아 틀리면 1분)
    attempt = db.execute(
        "SELECT fails, locked_until FROM login_attempt WHERE username = ?", (attempt_key,)
    ).fetchone()
    if attempt and attempt["locked_until"]:
        until = datetime.fromisoformat(attempt["locked_until"])
        if until > now:
            wait = int((until - now).total_seconds()) + 1
            return {
                "error": f"비밀번호를 {LOGIN_MAX_FAILS}번 틀려서 잠시 막았어요. {wait}초 뒤에 다시 해 주세요"
            }, 429

    row = db.execute(
        "SELECT id, username, nickname, password_hash FROM user WHERE username = ?",
        (username,),
    ).fetchone()
    # 아이디가 없어도 가짜 해시로 똑같이 검사한다.
    # 그래야 대답 속도로 "있는 아이디인지" 알아낼 수 없다.
    hash_to_check = row["password_hash"] if row else DUMMY_PASSWORD_HASH
    password_ok = bcrypt.check_password_hash(hash_to_check, password) and row is not None
    if not password_ok:
        # 틀린 횟수 +1, 기준에 닿으면 1분 막고 횟수는 처음부터
        fails = (attempt["fails"] if attempt else 0) + 1
        locked_until = None
        if fails >= LOGIN_MAX_FAILS:
            locked_until = (now + timedelta(seconds=LOGIN_LOCK_SECONDS)).isoformat()
            fails = 0
        db.execute(
            "INSERT INTO login_attempt (username, fails, locked_until) VALUES (?, ?, ?) "
            "ON CONFLICT(username) DO UPDATE SET fails = excluded.fails, "
            "locked_until = excluded.locked_until",
            (attempt_key, fails, locked_until),
        )
        db.commit()
        if locked_until:
            return {
                "error": f"비밀번호를 {LOGIN_MAX_FAILS}번 틀려서 {LOGIN_LOCK_SECONDS}초 동안 막았어요"
            }, 429
        left = LOGIN_MAX_FAILS - fails
        return {"error": f"아이디나 비밀번호가 맞지 않아요 (남은 기회 {left}번)"}, 401

    # 맞았으면 틀린 기록을 지운다
    db.execute("DELETE FROM login_attempt WHERE username = ?", (attempt_key,))
    db.commit()
    login_user(User(row["id"], row["username"], row["nickname"]), remember=True)
    return {"ok": True, "nickname": row["nickname"]}


# ---------- 닉네임 바꾸기 (F2-1) ----------
@app.post("/me/nickname")
@login_required
def change_nickname():
    data = read_json()
    nickname = text_of(data, "nickname")
    if not (1 <= len(nickname) <= 10):
        return {"error": "닉네임은 1~10자여야 해요"}, 400

    db = get_db()
    lock_db(db)
    mem = get_my_membership(db, current_user.id)
    if mem is not None:
        league = db.execute(
            "SELECT status FROM league WHERE id = ?", (mem["league_id"],)
        ).fetchone()
        # 리그가 시작되면 순위표·지난 경기 기록이 헷갈리지 않게 바꿀 수 없다
        if league and league["status"] != "recruiting":
            return {"error": "리그가 시작된 뒤에는 닉네임을 바꿀 수 없어요"}, 409
        if nickname_taken_in_league(db, mem["league_id"], nickname, current_user.id):
            return {"error": "이 리그에 같은 닉네임을 쓰는 친구가 있어요"}, 409

    db.execute("UPDATE user SET nickname = ? WHERE id = ?", (nickname, current_user.id))
    db.commit()
    return {"ok": True, "nickname": nickname}


# ---------- 로그아웃 (F2) ----------
@app.post("/logout")
@login_required
def logout():
    logout_user()
    return {"ok": True}


# ---------- 리그 설정 검사 (F4): 만들기·고치기에서 같이 쓴다 ----------
def parse_league_settings(data):
    """맞으면 (DB에 넣을 값 dict, None), 틀리면 (None, 안내 글)."""
    name = text_of(data, "name")
    if not (1 <= len(name) <= 30):
        return None, "리그 이름은 1~30자여야 해요"

    # 과목 설정: [{"name":"영어","count":3}, ...]
    raw_subjects = data.get("subjects") or []
    if not isinstance(raw_subjects, list) or len(raw_subjects) == 0:
        return None, "과목을 하나 이상 넣어 주세요"
    if len(raw_subjects) > 5:
        return None, "과목은 5개까지 넣을 수 있어요"
    subjects, seen = [], set()
    for sub in raw_subjects:
        if not isinstance(sub, dict):
            return None, "과목 형식이 올바르지 않아요"
        sname = text_of(sub, "name")
        count = sub.get("count")
        if not (1 <= len(sname) <= 20):
            return None, "과목 이름은 1~20자여야 해요"
        if sname in seen:
            return None, "같은 과목 이름이 두 번 들어갔어요"
        seen.add(sname)
        # bool(True/False)도 파이썬에서는 int라서 따로 막는다
        if not isinstance(count, int) or isinstance(count, bool) or not (1 <= count <= 10):
            return None, "과목별 문제 수는 1~10개여야 해요"
        scope, err = clean_scope(sub.get("scope", "자유 출제"))
        if err:
            return None, f"'{sname}' {err}"
        subjects.append({"name": sname, "count": count, "scope": scope})

    # 경기 요일·마감 시각·만들기 기간
    match_days, err = validate_match_days(data.get("match_days"))
    if err:
        return None, err
    deadline_time = data.get("deadline_time", "23:59")
    if deadline_time not in DEADLINE_TIMES:
        return None, "마감 시각을 목록에서 골라 주세요"
    make_days, err = validate_make_days(data.get("make_days", 0), match_days)
    if err:
        return None, err

    # 리그 기간 방식: 전체 리그 / 시험 대비 단기 리그(종료 희망일 필요)
    league_mode = data.get("league_mode", "full")
    if league_mode not in ("full", "short"):
        return None, "리그 기간 방식을 골라 주세요"
    end_date = None
    if league_mode == "short":
        try:
            end_date = date.fromisoformat(text_of(data, "end_date"))
        except ValueError:
            return None, "시험 대비 단기 리그는 리그 종료 희망일을 골라 주세요"
        today = today_kst()
        if end_date <= today:
            return None, "리그 종료 희망일은 내일 이후로 골라 주세요"
        if end_date > today + timedelta(days=END_DATE_MAX_DAYS):
            return None, "리그 종료 희망일은 1년 안으로 골라 주세요"

    # 상품 (선택): [{"from":1,"to":1,"text":"치킨"}, ...]
    # 벌칙은 공부를 즐겁게 하려고 두지 않는다. 예전 리그에 남은 벌칙(kind=penalty)은 무시한다.
    rewards = []
    taken_ranks = set()  # 한 등수는 상품 하나만 (1~2등과 1~3등이 겹치면 1·2등이 두 번 받게 되므로 막는다)
    raw_rewards = data.get("rewards") or []
    if isinstance(raw_rewards, list):
        for r in raw_rewards:
            if not isinstance(r, dict):
                continue
            if r.get("kind") == "penalty":
                continue
            try:
                rfrom, rto = int(r.get("from")), int(r.get("to"))
            except (TypeError, ValueError):
                continue
            text = text_of(r, "text")[:100]
            if rfrom < 1 or rto < rfrom or not text:
                continue
            ranks = set(range(rfrom, rto + 1))
            if ranks & taken_ranks:
                return None, "상품을 주는 등수가 서로 겹쳐요. 한 등수에는 상품을 하나만 정할 수 있어요"
            taken_ranks |= ranks
            rewards.append({"from": rfrom, "to": rto, "kind": "reward", "text": text})

    return {
        "name": name,
        "subjects": json.dumps(subjects, ensure_ascii=False),
        "rewards": json.dumps(rewards, ensure_ascii=False),
        "match_days": json.dumps(match_days),
        "deadline_time": deadline_time,
        "make_days": make_days,
        "league_mode": league_mode,
        "end_date": end_date.isoformat() if end_date else None,
    }, None


# ---------- 리그 설정 고치기 (F4): 모집 중일 때만 ----------
@app.post("/leagues/settings")
@login_required
def update_league_settings():
    db = get_db()
    lock_db(db)
    league = db.execute(
        "SELECT id, status FROM league WHERE admin_id = ? AND admin_closed = 0 AND deleted = 0 "
        "ORDER BY id DESC LIMIT 1",
        (current_user.id,),
    ).fetchone()
    if league is None:
        return {"error": "관리자인 리그가 없어요"}, 403
    if league["status"] != "recruiting":
        return {"error": "리그가 시작된 뒤에는 설정을 고칠 수 없어요"}, 409
    settings, err = parse_league_settings(read_json())
    if err:
        return {"error": err}, 400
    db.execute(
        "UPDATE league SET name = ?, subjects = ?, rewards = ?, match_days = ?, "
        "deadline_time = ?, make_days = ?, league_mode = ?, end_date = ? WHERE id = ?",
        (settings["name"], settings["subjects"], settings["rewards"], settings["match_days"],
         settings["deadline_time"], settings["make_days"], settings["league_mode"],
         settings["end_date"], league["id"]),
    )
    db.commit()
    return {"ok": True}


# ---------- 라운드별 출제 범위 (F4-2): 관리자만, 아직 시작하지 않은 라운드만 ----------
def admin_running_league(db):
    """내가 관리자인 리그 (없으면 None)."""
    return db.execute(
        "SELECT id, status FROM league WHERE admin_id = ? AND admin_closed = 0 AND deleted = 0 "
        "ORDER BY id DESC LIMIT 1",
        (current_user.id,),
    ).fetchone()


@app.get("/leagues/scopes")
@login_required
def list_round_scopes():
    """전체 라운드의 출제 범위와 잠금 여부. 시작한 라운드는 잠겨 있다."""
    db = get_db()
    league = admin_running_league(db)
    if league is None:
        return {"error": "관리자인 리그가 없어요"}, 403
    if league["status"] == "recruiting":
        return {"error": "리그를 시작하면 라운드별 범위를 정할 수 있어요. 지금은 기본 범위만 고칠 수 있어요"}, 409
    now = now_utc()
    rounds = []
    for r in round_rows(db, league["id"]):
        start = parse_utc(r["rs"])
        rounds.append({
            "round": r["week"], "start": r["rs"], "make_deadline": r["md"], "solve_deadline": r["sd"],
            "locked": start is None or now >= start,
            "scopes": round_scopes(db, league["id"], r["week"]),
        })
    return {"rounds": rounds, "current": current_round(db, league["id"])}


@app.post("/leagues/scopes")
@login_required
def save_round_scopes():
    """
    한 라운드의 과목별 범위 저장. {"round": 3, "scopes": {"수학": "이차함수", "영어": ""}}
    빈 글자는 '기본 범위로 되돌리기'. 시작한 라운드는 바꿀 수 없다.
    """
    db = get_db()
    lock_db(db)
    league = admin_running_league(db)
    if league is None:
        return {"error": "관리자인 리그가 없어요"}, 403
    if league["status"] != "running":
        return {"error": "진행 중인 리그에서만 라운드별 범위를 정할 수 있어요"}, 409
    data = read_json()
    rnd = data.get("round")
    scopes = data.get("scopes")
    if not isinstance(rnd, int) or isinstance(rnd, bool) or not isinstance(scopes, dict):
        return {"error": "요청 형식이 올바르지 않아요"}, 400
    row = next((r for r in round_rows(db, league["id"]) if r["week"] == rnd), None)
    if row is None:
        return {"error": "없는 라운드예요"}, 404
    if row["rs"] is None or now_utc() >= parse_utc(row["rs"]):
        return {"error": "이미 시작한 라운드라 출제 범위를 바꿀 수 없어요"}, 409
    names = list(league_need(db, league["id"]).keys())
    cleaned = {}
    for subject, raw in scopes.items():
        if subject not in names:
            return {"error": f"'{subject}'는 이 리그의 과목이 아니에요"}, 400
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            cleaned[subject] = None  # 기본 범위로 되돌리기
            continue
        text, err = clean_scope(raw)
        if err:
            return {"error": f"'{subject}' {err}"}, 400
        cleaned[subject] = text
    for subject, text in cleaned.items():
        if text is None:
            db.execute("DELETE FROM round_scope WHERE league_id = ? AND round = ? AND subject = ?",
                       (league["id"], rnd, subject))
        else:
            db.execute(
                "INSERT INTO round_scope (league_id, round, subject, scope, updated_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(league_id, round, subject) DO UPDATE SET scope = excluded.scope, "
                "updated_at = excluded.updated_at",
                (league["id"], rnd, subject, text, now_iso()),
            )
    db.commit()
    return {"ok": True, "round": rnd, "scopes": round_scopes(db, league["id"], rnd)}


# ---------- 관리자 화면 (F16·F16-1·F16-2) ----------
def admin_league_or_error(db):
    """내가 관리자인 시작된 리그 (없으면 오류 응답)."""
    league = admin_running_league(db)
    if league is None:
        return None, ({"error": "관리자만 볼 수 있어요"}, 403)
    if league["status"] == "recruiting":
        return None, ({"error": "리그가 시작되면 볼 수 있어요"}, 409)
    return league, None


@app.get("/admin/progress")
@login_required
def admin_progress():
    """
    이번 라운드 경기마다 두 학생의 [완성]·제출 여부 (F16).
    문제 내용·정답은 주지 않는다 (진행 중인 경기의 정답은 관리자도 볼 수 없다).
    """
    db = get_db()
    league, err = admin_league_or_error(db)
    if err:
        return err
    refresh_league(db, league["id"])
    rnd = current_round(db, league["id"])
    rows = db.execute(
        "SELECT m.*, u1.nickname AS n1, u2.nickname AS n2 FROM match m "
        "JOIN user u1 ON u1.id = m.player1_id LEFT JOIN user u2 ON u2.id = m.player2_id "
        "WHERE m.league_id = ? AND m.week = ? ORDER BY m.id",
        (league["id"], rnd),
    ).fetchall()
    matches, byes = [], []
    todo = {"make": 0, "solve": 0}
    for m in rows:
        if m["player2_id"] is None:
            byes.append(m["n1"])
            continue
        def side(p):
            done, sub = m[f"{p}_state"] == "done", bool(m[f"{p}_done"])
            return {"made": done, "submitted": sub}
        a, b = side("p1"), side("p2")
        if m["result"] is None:
            todo["make"] += (not a["made"]) + (not b["made"])
            todo["solve"] += (not a["submitted"]) + (not b["submitted"])
        matches.append({
            "p1": {"nickname": m["n1"], **a}, "p2": {"nickname": m["n2"], **b},
            "finished": m["result"] is not None, "forfeit": bool(m["forfeit"]),
        })
    first = rows[0] if rows else None
    return {
        "round": rnd, "total_rounds": total_weeks(db, league["id"]),
        "status": league["status"],
        "make_deadline": first["make_deadline"] if first else None,
        "solve_deadline": first["solve_deadline"] if first else None,
        "matches": matches, "byes": byes, "todo": todo,
    }


@app.get("/admin/accuracy")
@login_required
def admin_accuracy():
    """
    과목별 정답률 (F16-1). 끝난 정상 경기(몰수 제외)의 제출된 풀이만 센다.
    리그 전체와 학생별. 학생이 실제로 쓴 답은 주지 않는다.
    """
    db = get_db()
    league, err = admin_league_or_error(db)
    if err:
        return err
    refresh_league(db, league["id"])
    subjects = list(league_need(db, league["id"]).keys())
    rows = db.execute(
        "SELECT s.solver_id, q.subject, COUNT(*) AS n, SUM(s.correct) AS ok "
        "FROM submission s JOIN match m ON m.id = s.match_id JOIN question q ON q.id = s.question_id "
        "WHERE m.league_id = ? AND m.result IS NOT NULL AND m.forfeit = 0 AND q.void = 0 "
        "AND NOT EXISTS (SELECT 1 FROM membership r WHERE r.league_id = m.league_id "
        "AND r.status = 'removed' AND r.user_id IN (m.player1_id, m.player2_id)) "
        "GROUP BY s.solver_id, q.subject",
        (league["id"],),
    ).fetchall()
    members = db.execute(
        "SELECT u.id, u.nickname FROM membership mb JOIN user u ON u.id = mb.user_id "
        "WHERE mb.league_id = ? AND mb.status != 'removed' ORDER BY u.nickname",
        (league["id"],),
    ).fetchall()
    per = {m["id"]: {} for m in members}
    total = {sub: [0, 0] for sub in subjects}
    for r in rows:
        if r["solver_id"] in per:
            per[r["solver_id"]][r["subject"]] = [r["ok"] or 0, r["n"]]
        if r["subject"] in total:
            total[r["subject"]][0] += r["ok"] or 0
            total[r["subject"]][1] += r["n"]
    def rate(pair):
        return None if not pair or not pair[1] else round(pair[0] / pair[1], 4)
    return {
        "subjects": subjects,
        "league": [{"subject": sub, "correct": total[sub][0], "total": total[sub][1],
                    "rate": rate(total[sub])} for sub in subjects],
        "students": [
            {"user_id": m["id"], "nickname": m["nickname"],
             "subjects": [{"subject": sub, "correct": (per[m["id"]].get(sub) or [0, 0])[0],
                           "total": (per[m["id"]].get(sub) or [0, 0])[1],
                           "rate": rate(per[m["id"]].get(sub))} for sub in subjects]}
            for m in members
        ],
    }


@app.get("/admin/students/<int:user_id>/questions")
@login_required
def admin_student_questions(user_id):
    """
    학생이 라운드별로 만든 문제 (F16-2).
    - 끝난 경기만 내용·정답·해설·상대가 맞혔는지를 준다. 진행 중이면 잠금 표시만.
    - 상대에게 공개되지 않은 문제(만들기 몰수로 미완성)는 주지 않는다.
    - 푼 학생이 실제로 쓴 답은 주지 않는다.
    """
    db = get_db()
    league, err = admin_league_or_error(db)
    if err:
        return err
    student = db.execute(
        "SELECT u.id, u.nickname FROM membership mb JOIN user u ON u.id = mb.user_id "
        "WHERE mb.league_id = ? AND mb.user_id = ? AND mb.status != 'removed'",
        (league["id"], user_id),
    ).fetchone()
    if student is None:
        return {"error": "이 리그의 학생이 아니에요"}, 404
    refresh_league(db, league["id"])
    matches = db.execute(
        "SELECT * FROM match WHERE league_id = ? AND (player1_id = ? OR player2_id = ?) ORDER BY week",
        (league["id"], user_id, user_id),
    ).fetchall()
    rounds = []
    for m in matches:
        is_p1 = m["player1_id"] == user_id
        opp_id = m["player2_id"] if is_p1 else m["player1_id"]
        entry = {"round": m["week"], "bye": opp_id is None}
        if opp_id is None:
            rounds.append(entry)
            continue
        opp = db.execute("SELECT nickname FROM user WHERE id = ?", (opp_id,)).fetchone()
        me = "p1" if is_p1 else "p2"
        entry.update(opponent=opp["nickname"], finished=m["result"] is not None,
                     forfeit=bool(m["forfeit"]), made=m[f"{me}_state"] == "done")
        if m["result"] is None:
            entry["locked"] = True  # 🔒 경기가 끝나면 볼 수 있어요
            entry["questions"] = []
        elif m[f"{me}_state"] != "done":
            entry["locked"] = False
            entry["questions"] = []  # 완성하지 않아 상대에게 공개되지 않은 문제
            entry["note"] = "만들기 마감까지 [완성]하지 않아 상대에게 공개되지 않았어요"
        else:
            entry["locked"] = False
            qs = db.execute(
                "SELECT q.id, q.subject, q.qtype, q.content, q.choices, q.answer, q.explanation, "
                "q.void, q.void_reason, s.correct "
                "FROM question q LEFT JOIN submission s "
                "ON s.question_id = q.id AND s.match_id = q.match_id AND s.solver_id = ? "
                "WHERE q.match_id = ? AND q.author_id = ? ORDER BY q.id",
                (opp_id, m["id"], user_id),
            ).fetchall()
            entry["questions"] = [
                {"subject": q["subject"], "qtype": q["qtype"], "content": q["content"],
                 "choices": json.loads(q["choices"] or "[]"), "correct_answer": q["answer"],
                 "explanation": q["explanation"],
                 # 상대 결과: ⭕/❌, 제출 안 했으면 None (실제 답은 주지 않는다)
                 "opponent_correct": None if q["correct"] is None else bool(q["correct"]),
                 "void": bool(q["void"]), "void_reason": q["void_reason"]}
                for q in qs
            ]
            entry["scopes"] = round_scopes(db, league["id"], m["week"])
        rounds.append(entry)
    return {"student": {"user_id": student["id"], "nickname": student["nickname"]}, "rounds": rounds}


# ---------- 리그 만들기 (F3): 만든 사람이 관리자가 된다 ----------
@app.post("/leagues")
@login_required
def create_league():
    db = get_db()
    lock_db(db)
    # 계정 하나는 리그 하나에만 속한다 (SPEC 2번)
    if get_my_membership(db, current_user.id):
        return {"error": "이미 학생으로 들어간 리그가 있어요"}, 409
    own = get_admin_league(db, current_user.id)
    if own:
        if league_status(db, own["id"]) == "finished":
            return {"error": "지금 리그가 끝났어요. 관리자 화면에서 [리그 닫기]를 누르면 새 리그를 만들 수 있어요"}, 409
        return {"error": "이미 만든 리그가 있어요"}, 409

    settings, err = parse_league_settings(read_json())
    if err:
        return {"error": err}, 400

    code = gen_league_code(db)
    cur = db.execute(
        "INSERT INTO league (name, code, admin_id, status, subjects, rewards, match_days, "
        "deadline_time, make_days, league_mode, end_date, created_at) "
        "VALUES (?, ?, ?, 'recruiting', ?, ?, ?, ?, ?, ?, ?, ?)",
        (settings["name"], code, current_user.id, settings["subjects"], settings["rewards"],
         settings["match_days"], settings["deadline_time"], settings["make_days"],
         settings["league_mode"], settings["end_date"], now_iso()),
    )
    db.commit()
    return {"ok": True, "league_id": cur.lastrowid, "code": code}, 201


# ---------- 리그 입장 (F5): 6자리 코드로 들어간다. 한 학생은 리그 하나만 ----------
@app.post("/leagues/join")
@login_required
def join_league():
    data = read_json()
    code = text_of(data, "code")
    if not re.fullmatch(r"[0-9]{6}", code):
        return {"error": "리그 코드는 6자리 숫자예요"}, 400

    db = get_db()
    lock_db(db)

    # 이미 리그에 들어가 있으면 막는다 (한 학생은 리그 하나만)
    mem = get_my_membership(db, current_user.id)
    if mem:
        if league_status(db, mem["league_id"]) == "finished":
            return {"error": "지금 리그가 끝났어요. 리그 홈에서 [지난 리그로 보관]을 누르면 새 리그에 들어갈 수 있어요"}, 409
        return {"error": "이미 들어간 리그가 있어요"}, 409
    if get_admin_league(db, current_user.id):
        return {"error": "리그를 만든 관리자는 학생으로 들어갈 수 없어요"}, 409

    league = db.execute(
        "SELECT id, status FROM league WHERE code = ? AND deleted = 0", (code,)
    ).fetchone()
    if league is None:
        return {"error": "그런 코드의 리그가 없어요"}, 404
    if league["status"] != "recruiting":
        return {"error": "이미 시작했거나 끝난 리그예요"}, 409

    # 같은 리그 안에서는 닉네임이 겹치면 안 된다 (순위표·대진표에서 누군지 헷갈리므로)
    if nickname_taken_in_league(db, league["id"], current_user.nickname, current_user.id):
        return {
            "error": f"이 리그에 이미 같은 닉네임('{current_user.nickname}')을 쓰는 친구가 있어요. 닉네임을 바꾸면 바로 들어가요",
            "reason": "dup_nickname",
        }, 409

    db.execute(
        "INSERT INTO membership (league_id, user_id, joined_at) VALUES (?, ?, ?)",
        (league["id"], current_user.id, now_iso()),
    )
    db.commit()
    return {"ok": True, "league_id": league["id"]}


# ---------- 리그 나가기 (F5): 모집 중일 때만 ----------
@app.post("/leagues/leave")
@login_required
def leave_league():
    db = get_db()
    lock_db(db)
    mem = get_my_membership(db, current_user.id)
    if mem is None:
        return {"error": "들어간 리그가 없어요"}, 404
    league = db.execute(
        "SELECT status FROM league WHERE id = ?", (mem["league_id"],)
    ).fetchone()
    if league is None or league["status"] != "recruiting":
        return {"error": "리그가 시작된 뒤에는 나갈 수 없어요"}, 409
    # 모집 중에는 아직 문제도 경기도 없으니 참가 기록만 지우면 된다
    db.execute("DELETE FROM membership WHERE user_id = ? AND status = 'active'", (current_user.id,))
    db.commit()
    return {"ok": True}


# ---------- 리그 생명주기 (F15): 보관·닫기·삭제·내보내기 ----------
def league_status(db, league_id):
    row = db.execute("SELECT status FROM league WHERE id = ?", (league_id,)).fetchone()
    return row["status"] if row else None


def pending_report_count(db, league_id):
    return db.execute(
        "SELECT COUNT(*) FROM report WHERE league_id = ? AND status = 'pending'", (league_id,)
    ).fetchone()[0]


def final_summary(db, league_id, table, rewards):
    """끝난 리그의 최종 결과 (지금 리그·지난 리그 화면에서 같이 쓴다)."""
    pending = pending_report_count(db, league_id)
    deadline = report_deadline(db, league_id)
    return {
        "winner": table[0]["nickname"] if table else None,
        "my_rank": next((r["rank"] for r in table if r["user_id"] == current_user.id), None),
        # 처리하지 않은 신고가 있으면 아직 확정이 아니다 (판정 기한이 지나면 자동으로 확정)
        "finalized": pending == 0,
        "pending_reports": pending,
        "report_deadline": deadline.isoformat() if deadline else None,
        "awards": [
            {**rw, "recipients": [r["nickname"] for r in table if rw["from"] <= r["rank"] <= rw["to"]]}
            for rw in rewards
        ],
    }


def finish_if_too_few(db, league_id):
    """활동 중인 학생이 1명 이하가 되면 리그를 바로 끝낸다."""
    left = db.execute(
        "SELECT COUNT(*) FROM membership WHERE league_id = ? AND status = 'active'", (league_id,)
    ).fetchone()[0]
    if left <= 1:
        db.execute("UPDATE league SET status = 'finished', ended_at = ? WHERE id = ? AND status = 'running'",
                   (now_iso(), league_id))


@app.post("/leagues/archive")
@login_required
def archive_league():
    """학생: 끝나고 확정된 리그를 '지난 리그'로 보관 → 새 리그에 들어갈 수 있다. 기록은 그대로 남는다."""
    db = get_db()
    lock_db(db)
    mem = get_my_membership(db, current_user.id)
    if mem is None:
        return {"error": "보관할 리그가 없어요"}, 404
    refresh_league(db, mem["league_id"])
    if league_status(db, mem["league_id"]) != "finished":
        return {"error": "리그가 끝난 뒤에 보관할 수 있어요"}, 409
    if pending_report_count(db, mem["league_id"]):
        return {"error": "신고 판정이 끝나면 보관할 수 있어요 (최종 결과가 확정된 뒤)"}, 409
    db.execute(
        "UPDATE membership SET status = 'archived', left_at = ? WHERE user_id = ? AND status = 'active'",
        (now_iso(), current_user.id),
    )
    db.commit()
    return {"ok": True}


@app.post("/leagues/close")
@login_required
def close_league():
    """관리자: 끝나고 확정된 리그를 닫기 → 새 리그를 만들 수 있다. 기록은 그대로 남는다."""
    db = get_db()
    lock_db(db)
    league = get_admin_league(db, current_user.id)
    if league is None:
        return {"error": "닫을 리그가 없어요"}, 404
    refresh_league(db, league["id"])
    if league_status(db, league["id"]) != "finished":
        return {"error": "리그가 끝난 뒤에 닫을 수 있어요. 모집 중이면 [리그 삭제]를 쓸 수 있어요"}, 409
    if pending_report_count(db, league["id"]):
        return {"error": "처리하지 않은 신고가 있어요. 판정을 끝낸 뒤 닫아 주세요"}, 409
    db.execute("UPDATE league SET admin_closed = 1 WHERE id = ?", (league["id"],))
    db.commit()
    return {"ok": True}


@app.post("/leagues/delete")
@login_required
def delete_league():
    """관리자: 모집 중인 리그만 삭제. 들어와 있던 학생은 리그에서 빠진다 (아직 경기 기록이 없다)."""
    db = get_db()
    lock_db(db)
    league = get_admin_league(db, current_user.id)
    if league is None:
        return {"error": "삭제할 리그가 없어요"}, 404
    if league_status(db, league["id"]) != "recruiting":
        return {"error": "리그가 시작된 뒤에는 삭제할 수 없어요 (학생들의 경기 기록이 지워지기 때문이에요)"}, 409
    db.execute("DELETE FROM membership WHERE league_id = ?", (league["id"],))
    db.execute("UPDATE league SET deleted = 1 WHERE id = ?", (league["id"],))
    db.commit()
    return {"ok": True}


@app.post("/admin/students/<int:user_id>/remove")
@login_required
def remove_student(user_id):
    """
    관리자: 학생 내보내기 (전학 등).
    - 모집 중: 참가 기록만 지운다 (학생이 나가기를 한 것과 같다)
    - 진행 중: 그 학생은 순위표에서 빠지고, 그 학생과의 경기는 양쪽 모두 순위에 들어가지 않는다.
      아직 끝나지 않은 경기는 상대에게 쉬는 라운드가 된다. 남은 학생이 1명이면 리그가 끝난다.
    """
    db = get_db()
    lock_db(db)
    league = get_admin_league(db, current_user.id)
    if league is None:
        return {"error": "관리자만 할 수 있어요"}, 403
    mem = db.execute(
        "SELECT id FROM membership WHERE league_id = ? AND user_id = ? AND status = 'active'",
        (league["id"], user_id),
    ).fetchone()
    if mem is None:
        return {"error": "이 리그에서 활동 중인 학생이 아니에요"}, 404
    refresh_league(db, league["id"])
    status = league_status(db, league["id"])
    if status == "finished":
        return {"error": "끝난 리그에서는 내보낼 수 없어요"}, 409
    if status == "recruiting":
        db.execute("DELETE FROM membership WHERE id = ?", (mem["id"],))
        db.commit()
        return {"ok": True}
    db.execute("UPDATE membership SET status = 'removed', left_at = ? WHERE id = ?", (now_iso(), mem["id"]))
    # 아직 결과가 안 난 경기: 상대만 남겨 쉬는 라운드로 바꾼다
    for m in db.execute(
        "SELECT id, player1_id, player2_id FROM match WHERE league_id = ? AND result IS NULL "
        "AND (player1_id = ? OR player2_id = ?)",
        (league["id"], user_id, user_id),
    ).fetchall():
        other = m["player2_id"] if m["player1_id"] == user_id else m["player1_id"]
        if other is None:
            # 내보낸 학생 자신의 쉬는 라운드는 지운다
            db.execute("DELETE FROM match WHERE id = ?", (m["id"],))
        else:
            db.execute("UPDATE match SET player1_id = ?, player2_id = NULL WHERE id = ?", (other, m["id"]))
    # 내보낸 학생의 처리 안 된 신고는 판정할 필요가 없다
    db.execute(
        "UPDATE report SET status = 'ok', decided_at = ? WHERE league_id = ? AND reporter_id = ? AND status = 'pending'",
        (now_iso(), league["id"], user_id),
    )
    finish_if_too_few(db, league["id"])
    db.commit()
    return {"ok": True, "league_status": league_status(db, league["id"])}


@app.get("/leagues/past")
@login_required
def past_leagues():
    """지난 리그 목록: 학생은 보관한 리그, 관리자는 닫은 리그."""
    db = get_db()
    uid = current_user.id
    out = []
    for r in db.execute(
        "SELECT l.id, l.name, l.league_mode, l.first_date, m.left_at FROM membership m "
        "JOIN league l ON l.id = m.league_id WHERE m.user_id = ? AND m.status = 'archived' "
        "ORDER BY m.left_at DESC",
        (uid,),
    ).fetchall():
        table = compute_standings(db, r["id"])
        me = next((x for x in table if x["user_id"] == uid), None)
        out.append({"league_id": r["id"], "name": r["name"], "role": "student",
                    "league_mode": r["league_mode"], "first_date": r["first_date"],
                    "players": len(table), "my_rank": me["rank"] if me else None,
                    "winner": table[0]["nickname"] if table else None})
    for r in db.execute(
        "SELECT id, name, league_mode, first_date FROM league WHERE admin_id = ? AND admin_closed = 1 "
        "AND deleted = 0 ORDER BY id DESC",
        (uid,),
    ).fetchall():
        table = compute_standings(db, r["id"])
        out.append({"league_id": r["id"], "name": r["name"], "role": "admin",
                    "league_mode": r["league_mode"], "first_date": r["first_date"],
                    "players": len(table), "my_rank": None,
                    "winner": table[0]["nickname"] if table else None})
    return {"leagues": out}


@app.get("/leagues/past/<int:league_id>")
@login_required
def past_league_detail(league_id):
    """지난 리그의 최종 순위·상품·벌칙 (내가 보관한 리그 또는 내가 닫은 리그만)."""
    db = get_db()
    uid = current_user.id
    is_student = db.execute(
        "SELECT 1 FROM membership WHERE league_id = ? AND user_id = ? AND status = 'archived'", (league_id, uid)
    ).fetchone() is not None
    league = db.execute(
        "SELECT id, name, admin_id, admin_closed, rewards, league_mode, first_date FROM league "
        "WHERE id = ? AND deleted = 0",
        (league_id,),
    ).fetchone()
    is_admin = league is not None and league["admin_id"] == uid and league["admin_closed"] == 1
    if league is None or not (is_student or is_admin):
        return {"error": "볼 수 있는 지난 리그가 아니에요"}, 403
    table = compute_standings(db, league_id)
    rewards = json.loads(league["rewards"] or "[]")
    return {
        "league": {"id": league["id"], "name": league["name"], "league_mode": league["league_mode"],
                   "first_date": league["first_date"], "rewards": rewards},
        "role": "student" if is_student else "admin",
        "my_user_id": uid,
        "standings": table,
        "final": final_summary(db, league_id, table, rewards),
    }


# ---------- 내 리그 정보 보기 (명단 포함) ----------
@app.get("/leagues/mine")
@login_required
def my_league():
    db = get_db()
    mem = get_my_membership(db, current_user.id)
    admin_league = None

    # 내가 관리자인 리그가 있는지도 본다 (관리자는 입장하지 않아도 리그를 가짐)
    if mem is None:
        admin_row = get_admin_league(db, current_user.id)
        if admin_row:
            admin_league = admin_row["id"]

    league_id = mem["league_id"] if mem else admin_league
    if league_id is None:
        return {"in_league": False}

    refresh_league(db, league_id)
    league = db.execute(
        "SELECT id, name, code, admin_id, status, subjects, rewards, match_days, first_date, "
        "deadline_time, make_days, league_mode, end_date FROM league WHERE id = ?",
        (league_id,),
    ).fetchone()

    members = db.execute(
        """
        SELECT u.id, u.nickname
        FROM membership m JOIN user u ON u.id = m.user_id
        WHERE m.league_id = ? AND m.status != 'removed'
        ORDER BY m.joined_at ASC
        """,
        (league_id,),
    ).fetchall()

    result = {
        "in_league": True,
        "is_admin": league["admin_id"] == current_user.id,
        "my_user_id": current_user.id,
        "league": {
            "id": league["id"],
            "name": league["name"],
            "code": league["code"],
            "status": league["status"],
            "subjects": json.loads(league["subjects"] or "[]"),
            "rewards": json.loads(league["rewards"] or "[]"),
            "match_days": json.loads(league["match_days"] or "[]"),
            "first_date": league["first_date"],
            "deadline_time": league["deadline_time"],
            "make_days": league["make_days"],
            "league_mode": league["league_mode"],
            "end_date": league["end_date"],
        },
        "members": [{"id": m["id"], "nickname": m["nickname"]} for m in members],
    }

    # 모집 중이면 관리자에게 첫 경기로 고를 수 있는 날짜를 준다 (서버가 정한 '오늘' 기준)
    if league["status"] == "recruiting" and result["is_admin"]:
        days = result["league"]["match_days"]
        result["first_date_choices"] = [
            d.isoformat() for d in first_date_choices(days, league["make_days"], league["deadline_time"])
        ] if days else []
        result["today"] = today_kst().isoformat()
        # 단기 리그: 고를 수 있는 첫 날짜마다 몇 라운드까지 되는지 (화면 미리 보기와 같은 계산을 서버도 한다)
        if league["league_mode"] == "short" and days:
            n_max = round_count(len(members))
            end = date.fromisoformat(league["end_date"])
            result["short_rounds"] = {
                d: rounds_until(date.fromisoformat(d), days, league["make_days"],
                                league["deadline_time"], end, n_max)
                for d in result["first_date_choices"]
            }

    # 리그가 시작됐으면 라운드별 날짜 (전체 공통)
    if league["status"] in ("running", "finished"):
        rows = db.execute(
            "SELECT week, MIN(round_start) AS rs, MIN(make_deadline) AS md, MIN(solve_deadline) AS sd "
            "FROM match WHERE league_id = ? GROUP BY week ORDER BY week",
            (league_id,),
        ).fetchall()
        result["rounds"] = [
            {"round": r["week"], "start": r["rs"], "make_deadline": r["md"], "solve_deadline": r["sd"]}
            for r in rows
        ]

    # 리그가 시작됐으면 순위표·주차·이번 주 상대도 함께 준다
    if league["status"] in ("running", "finished"):
        week = current_round(db, league_id)
        weeks = total_weeks(db, league_id)
        result["week"] = week
        result["total_weeks"] = weeks
        result["standings"] = compute_standings(db, league_id)
        if league["status"] == "finished":
            result["final"] = final_summary(db, league_id, result["standings"], result["league"]["rewards"])

        # 이번 주 내 경기(상대) 찾기 — 학생일 때만 의미 있음
        if mem is not None:
            my_match = db.execute(
                "SELECT player1_id, player2_id FROM match "
                "WHERE league_id = ? AND week = ? AND (player1_id = ? OR player2_id = ?)",
                (league_id, week, current_user.id, current_user.id),
            ).fetchone()
            opponent = None
            if my_match:
                opp_id = (
                    my_match["player2_id"]
                    if my_match["player1_id"] == current_user.id
                    else my_match["player1_id"]
                )
                if opp_id is None:
                    opponent = {"bye": True}  # 이번 주는 부전승(상대 없음)
                else:
                    opp = db.execute(
                        "SELECT nickname FROM user WHERE id = ?", (opp_id,)
                    ).fetchone()
                    opponent = {"bye": False, "id": opp_id, "nickname": opp["nickname"]}
            result["my_opponent"] = opponent

            # 내 전체 일정 (주차별 상대, 쉬는 주 포함)
            my_matches = db.execute(
                "SELECT week, player1_id, player2_id FROM match "
                "WHERE league_id = ? AND (player1_id = ? OR player2_id = ?) "
                "ORDER BY week ASC",
                (league_id, current_user.id, current_user.id),
            ).fetchall()
            schedule = []
            for mt in my_matches:
                opp_id = (
                    mt["player2_id"]
                    if mt["player1_id"] == current_user.id
                    else mt["player1_id"]
                )
                if opp_id is None:
                    schedule.append({"week": mt["week"], "bye": True})
                else:
                    opp = db.execute(
                        "SELECT nickname FROM user WHERE id = ?", (opp_id,)
                    ).fetchone()
                    schedule.append(
                        {"week": mt["week"], "bye": False, "nickname": opp["nickname"]}
                    )
            result["schedule"] = schedule

    return result


# ---------- 리그 시작 (F6): 대진표 자동 생성 ----------
@app.post("/leagues/start")
@login_required
def start_league():
    db = get_db()
    lock_db(db)  # 시작 버튼을 두 번 눌러도 대진표가 두 번 생기지 않게

    # 내가 관리자인 리그 찾기
    league = db.execute(
        "SELECT id, status, match_days, deadline_time, make_days, league_mode, end_date FROM league "
        "WHERE admin_id = ? AND admin_closed = 0 AND deleted = 0 ORDER BY id DESC LIMIT 1",
        (current_user.id,),
    ).fetchone()
    if league is None:
        return {"error": "관리자인 리그가 없어요"}, 403
    if league["status"] != "recruiting":
        return {"error": "이미 시작했거나 끝난 리그예요"}, 409

    # 첫 경기 날짜 (F6): 경기 요일 중에서, 고를 수 있는 기간 안이어야 한다
    days = json.loads(league["match_days"] or "[]")
    if not days:
        return {"error": "리그에 경기 요일이 없어요"}, 400
    raw_first = text_of(read_json(), "first_date")
    try:
        first = date.fromisoformat(raw_first)
    except ValueError:
        return {"error": "첫 경기 날짜를 골라 주세요"}, 400
    if first not in first_date_choices(days, league["make_days"], league["deadline_time"]):
        # 날짜가 지났거나(화면을 오래 열어 둔 경우) 경기 요일이 아닌 경우
        return {"error": "고를 수 없는 날짜예요. 화면을 새로고침한 뒤 다시 골라 주세요"}, 400

    # 참가자 모으기 (들어온 순서대로)
    members = db.execute(
        "SELECT user_id FROM membership WHERE league_id = ? AND status = 'active' ORDER BY joined_at ASC",
        (league["id"],),
    ).fetchall()
    player_ids = [m["user_id"] for m in members]
    if len(player_ids) < 2:
        return {"error": "학생이 2명 이상 있어야 시작할 수 있어요"}, 400
    if len(player_ids) > 30:
        return {"error": "학생은 30명까지 참가할 수 있어요"}, 400

    # 대진표 자동 생성 (라운드 로빈) + 라운드별 날짜
    rounds = make_round_robin(player_ids)
    if league["league_mode"] == "short":
        # 시험 대비 단기 리그: 종료 희망일까지 끝나는 라운드만, 전체 대진표의 앞부분을 쓴다
        n = rounds_until(first, days, league["make_days"], league["deadline_time"],
                         date.fromisoformat(league["end_date"]), len(rounds))
        if n < 1:
            return {"error": "종료 희망일까지 끝낼 수 있는 라운드가 없어요. 첫 경기 날짜를 앞당기거나 [⚙️ 리그 설정 고치기]에서 종료 희망일을 늦춰 주세요"}, 400
        rounds = rounds[:n]
    schedule = build_schedule(first, days, len(rounds), league["make_days"])
    dt = league["deadline_time"]
    for pairs, sch in zip(rounds, schedule):
        times = (kst_midnight_utc(sch["start"]), kst_deadline_utc(sch["make_last"], dt),
                 kst_deadline_utc(sch["last"], dt))
        for p1, p2 in pairs:
            db.execute(
                "INSERT INTO match (league_id, week, player1_id, player2_id, "
                "round_start, make_deadline, solve_deadline) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (league["id"], sch["round"], p1, p2) + times,
            )

    db.execute(
        "UPDATE league SET status = 'running', first_date = ? WHERE id = ?",
        (first.isoformat(), league["id"]),
    )
    db.commit()
    return {"ok": True, "rounds": len(rounds),
            "start": schedule[0]["start"].isoformat(),
            "end": schedule[-1]["last"].isoformat()}


# ---------- 경기 하나의 상태 (F7·F8·F12) ----------
# 문제는 경기(라운드 상대)마다 새로 만든다. [임시 저장]은 'draft', [완성]은 'done'.
# 만들기 마감 전까지는 완성했어도 언제든 고칠 수 있고, 만들기 마감이 지나면 잠기고 풀기 기간이 시작된다.
def league_need(db, league_id):
    """과목별로 몇 문제를 만들어야 하는지 {과목: 개수} (순서 유지)."""
    row = db.execute("SELECT subjects FROM league WHERE id = ?", (league_id,)).fetchone()
    return {sub["name"]: sub["count"] for sub in json.loads(row["subjects"] or "[]")}


def round_scopes(db, league_id, rnd):
    """
    그 라운드의 과목별 출제 범위 목록 [{subject, count, scope, custom}] (과목 순서 유지).
    관리자가 라운드별로 정한 범위가 있으면 그것, 없으면 리그의 기본 범위.
    """
    row = db.execute("SELECT subjects FROM league WHERE id = ?", (league_id,)).fetchone()
    custom = {
        r["subject"]: r["scope"]
        for r in db.execute(
            "SELECT subject, scope FROM round_scope WHERE league_id = ? AND round = ?",
            (league_id, rnd),
        ).fetchall()
    }
    out = []
    for sub in json.loads(row["subjects"] or "[]"):
        default = sub.get("scope") or "자유 출제"
        out.append({"subject": sub["name"], "count": sub["count"],
                    "scope": custom.get(sub["name"], default),
                    "default": default, "custom": sub["name"] in custom})
    return out


def question_rows(db, match_id, author_id):
    return db.execute(
        "SELECT id, subject, qtype, content, choices, answer, explanation FROM question "
        "WHERE match_id = ? AND author_id = ? ORDER BY id ASC",
        (match_id, author_id),
    ).fetchall()


def row_to_item(r):
    """DB의 문제 한 줄 → 화면/검사용 dict."""
    return {
        "subject": r["subject"], "qtype": r["qtype"], "content": r["content"],
        "choices": json.loads(r["choices"] or "[]"),
        "answer": r["answer"], "explanation": r["explanation"],
    }


def check_question(q, need):
    """
    문제 하나 검사. strict=완성 기준.
    돌려주는 값: (정리된 값 tuple 또는 None, 완성 기준 안내 글 또는 None, 형식 오류 글 또는 None)
    형식 오류는 임시 저장도 막는다 (이상한 요청). 완성 기준은 [완성]만 막는다.
    """
    if not isinstance(q, dict):
        return None, None, "문제 형식이 올바르지 않아요"
    subject = text_of(q, "subject")
    qtype = q.get("qtype")
    if subject not in need:
        return None, None, f"'{subject}'는 이 리그의 과목이 아니에요"
    if qtype not in ("mc", "sa"):
        return None, None, "문제 유형이 올바르지 않아요"
    content = text_of(q, "content")
    explanation = text_of(q, "explanation")
    if len(content) > 1000:
        return None, None, "문제 내용은 1000자까지예요"
    if len(explanation) > 1000:
        return None, None, "해설은 1000자까지예요"
    problem = None if content else "문제 내용을 넣어 주세요"

    if qtype == "mc":
        choices = q.get("choices") or []
        if not isinstance(choices, list) or len(choices) > 5:
            return None, None, "객관식 보기는 5개까지예요"
        choices = [c.strip() if isinstance(c, str) else "" for c in choices]
        if any(len(c) > 200 for c in choices):
            return None, None, "객관식 보기는 200자까지예요"
        raw_ans = q.get("answer")
        try:
            ans = int(raw_ans) if raw_ans not in (None, "") and not isinstance(raw_ans, bool) else None
        except (TypeError, ValueError):
            ans = None
        if ans is not None and not (0 <= ans < len(choices)):
            ans = None
        if problem is None:
            if len(choices) < 2:
                problem = "객관식 보기는 2개 이상이어야 해요"
            elif any(not c for c in choices):
                problem = "객관식 보기를 모두 채워 주세요"
            elif len(set(choices)) != len(choices):
                problem = "같은 보기를 두 번 쓸 수 없어요"
            elif ans is None:
                problem = "객관식 정답을 골라 주세요"
        cleaned = (subject, "mc", content, json.dumps(choices, ensure_ascii=False),
                   "" if ans is None else str(ans), explanation)
    else:
        answer = text_of(q, "answer")
        if len(answer) > 200:
            return None, None, "주관식 정답은 200자까지예요"
        if problem is None and not answer:
            problem = "주관식 정답을 넣어 주세요"
        cleaned = (subject, "sa", content, "[]", answer, explanation)
    return cleaned, problem, None


def check_question_set(items, need):
    """
    문제 목록 전체 검사.
    돌려주는 값: (정리된 목록, 완성 기준 안내 {"index","error"} 또는 None, 형식 오류 글 또는 None)
    """
    if not isinstance(items, list):
        return None, None, "문제 형식이 올바르지 않아요"
    got = {name: 0 for name in need}
    cleaned, first_problem = [], None
    for i, q in enumerate(items):
        c, problem, fatal = check_question(q, need)
        if fatal:
            return None, None, fatal
        got[c[0]] += 1
        if got[c[0]] > need[c[0]]:
            return None, None, f"'{c[0]}' 과목은 {need[c[0]]}문제까지만 만들 수 있어요"
        cleaned.append(c)
        if problem and first_problem is None:
            first_problem = {"index": i, "error": f"{i + 1}번째 문제: {problem}"}
    if first_problem is None:
        for name, cnt in need.items():
            if got[name] != cnt:
                first_problem = {"index": None,
                                 "error": f"'{name}' 과목은 {cnt}문제를 만들어야 해요 (지금 {got[name]}개)"}
                break
    return cleaned, first_problem, None


def match_status(db, m, uid):
    """
    내 입장에서 본 경기 상태. 화면 표시와 서버 검사에 같이 쓴다.
    phase: bye / upcoming / make / wait_opp / solve / wait_result / result / closed
    """
    me = "p1" if m["player1_id"] == uid else "p2"
    op = "p2" if me == "p1" else "p1"
    opp_id = m["player2_id"] if me == "p1" else m["player1_id"]
    info = {
        "match_id": m["id"], "round": m["week"], "bye": opp_id is None,
        "round_start": m["round_start"], "make_deadline": m["make_deadline"],
        "solve_deadline": m["solve_deadline"],
        "my_state": m[f"{me}_state"], "opp_state": m[f"{op}_state"],
        "my_saved_at": m[f"{me}_saved_at"],
        "i_submitted": bool(m[f"{me}_done"]), "opp_submitted": bool(m[f"{op}_done"]),
        "result": m["result"], "opp_id": opp_id, "me": me,
    }
    if opp_id is None:
        info.update(phase="bye", can_edit=False, can_reopen=False, solve_open=False, locked=False)
        return info

    now = now_utc()
    rs, md, sd = parse_utc(m["round_start"]), parse_utc(m["make_deadline"]), parse_utc(m["solve_deadline"])
    started = rs is None or now >= rs
    make_over = md is not None and now >= md
    closed = sd is not None and now >= sd
    # 문제는 만들기 마감에 잠긴다 (날짜가 없는 예전 리그만 '둘 다 완성'을 기준으로 둔다)
    both_done = m["p1_state"] == "done" and m["p2_state"] == "done"
    locked = make_over if md is not None else both_done

    need = league_need(db, m["league_id"])
    # [완성]을 눌러야만 완성으로 친다. 임시 저장은 '아직 다 만들지 않았다'는 뜻이라
    # 칸이 다 채워져 있어도 마감까지 [완성]을 누르지 않으면 다 못 만든 것으로 본다
    my_ready = m[f"{me}_state"] == "done"
    opp_ready = m[f"{op}_state"] == "done"

    can_edit = started and not locked and info["my_state"] == "draft"
    can_reopen = started and not locked and info["my_state"] == "done"
    solve_open = started and locked and not closed and my_ready and opp_ready and not info["i_submitted"]

    if m["result"] is not None:
        phase = "result"
    elif not started:
        phase = "upcoming"
    elif info["i_submitted"]:
        phase = "wait_result"
    elif solve_open:
        phase = "solve"
    elif can_edit:
        phase = "make"
    elif can_reopen:
        phase = "wait_opp"
    else:
        phase = "closed"  # 마감이 지났는데 결과가 안 난 경우 (마감 처리는 5단계)
    info.update(phase=phase, can_edit=can_edit, can_reopen=can_reopen, solve_open=solve_open,
                locked=locked, my_ready=my_ready, opp_ready=opp_ready, need_total=sum(need.values()))
    return info


def my_match_or_error(db, match_id):
    """내 경기면 (경기 줄, None), 아니면 (None, 오류 응답)."""
    m = db.execute("SELECT * FROM match WHERE id = ?", (match_id,)).fetchone()
    if m is None:
        return None, ({"error": "경기를 찾을 수 없어요"}, 404)
    if current_user.id not in (m["player1_id"], m["player2_id"]):
        return None, ({"error": "내 경기가 아니에요"}, 403)
    return m, None


def public_status(st):
    """화면에 보내도 되는 상태 값만 (상대 id 등은 빼고)."""
    return {k: v for k, v in st.items() if k not in ("opp_id", "me")}


# ---------- 이번 경기 (F12): 상대, 지금 할 일, 마감 ----------
@app.get("/matches/current")
@login_required
def current_match():
    db = get_db()
    mem = get_my_membership(db, current_user.id)
    if mem is None:
        return {"error": "먼저 리그에 들어가세요"}, 403
    league_id = mem["league_id"]
    refresh_league(db, league_id)

    rnd = current_round(db, league_id)
    m = db.execute(
        "SELECT * FROM match WHERE league_id = ? AND week = ? AND (player1_id = ? OR player2_id = ?)",
        (league_id, rnd, current_user.id, current_user.id),
    ).fetchone()
    if m is None:
        return {"has_match": False}
    st = match_status(db, m, current_user.id)
    out = {"has_match": True, "week": rnd, **public_status(st),
           "scopes": round_scopes(db, league_id, m["week"])}
    if not st["bye"]:
        opp = db.execute("SELECT nickname FROM user WHERE id = ?", (st["opp_id"],)).fetchone()
        out["opponent"] = {"nickname": opp["nickname"]}
        if st["i_submitted"]:
            out["my_score"] = m[f"{st['me']}_score"]
        if m["result"] is not None:
            op = "p2" if st["me"] == "p1" else "p1"
            out["opp_score"] = m[f"{op}_score"]
            res = m["result"]
            out["outcome"] = ("draw" if res == "draw" else "both_lose" if res == "both_lose"
                              else "win" if res == st["me"] else "lose")
            out["forfeit"] = bool(m["forfeit"])
            out["forfeit_stage"] = m["forfeit_stage"]
    return out


# ---------- 내 문제 불러오기 (F7: 다시 열면 그대로) ----------
@app.get("/matches/<int:match_id>/my-questions")
@login_required
def my_questions(match_id):
    db = get_db()
    m, err = my_match_or_error(db, match_id)
    if err:
        return err
    st = match_status(db, m, current_user.id)
    if st["bye"]:
        return {"error": "쉬는 라운드라 문제를 만들지 않아요"}, 400
    if st["phase"] == "upcoming":
        return {"error": "아직 라운드가 시작되지 않았어요"}, 409
    need = league_need(db, m["league_id"])
    opp = db.execute("SELECT nickname FROM user WHERE id = ?", (st["opp_id"],)).fetchone()
    return {
        "subjects": [{"name": k, "count": v} for k, v in need.items()],
        "questions": [row_to_item(r) for r in question_rows(db, match_id, current_user.id)],
        "opponent": opp["nickname"],
        "scopes": round_scopes(db, m["league_id"], m["week"]),
        **public_status(st),
    }


# ---------- 문제 저장 (F7): 임시 저장 / 완성 ----------
@app.post("/matches/<int:match_id>/my-questions")
@login_required
def save_questions(match_id):
    db = get_db()
    lock_db(db)
    m, err = my_match_or_error(db, match_id)
    if err:
        return err
    st = match_status(db, m, current_user.id)
    if st["bye"]:
        return {"error": "쉬는 라운드라 문제를 만들지 않아요"}, 400
    if not st["can_edit"]:
        if st["my_state"] == "done" and st["can_reopen"]:
            return {"error": "완성한 문제예요. 고치려면 [다시 고치기]를 눌러 주세요"}, 409
        if st["phase"] == "upcoming":
            return {"error": "아직 라운드가 시작되지 않았어요"}, 409
        return {"error": "만들기 마감이 지나서 문제가 잠겼어요"}, 409

    data = read_json()
    action = data.get("action")
    if action not in ("draft", "complete"):
        return {"error": "요청 형식이 올바르지 않아요"}, 400
    need = league_need(db, m["league_id"])
    cleaned, problem, fatal = check_question_set(data.get("questions"), need)
    if fatal:
        return {"error": fatal}, 400
    if action == "complete" and problem:
        # 완성 기준에 안 맞으면 저장도 하지 않는다 (임시 저장을 먼저 누르라고 안내)
        return {"error": problem["error"], "index": problem["index"]}, 400

    me = st["me"]
    db.execute("DELETE FROM question WHERE match_id = ? AND author_id = ?", (match_id, current_user.id))
    for (subject, qtype, content, choices, answer, explanation) in cleaned:
        db.execute(
            "INSERT INTO question (league_id, match_id, author_id, subject, qtype, content, choices, answer, explanation) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (m["league_id"], match_id, current_user.id, subject, qtype, content, choices, answer, explanation),
        )
    saved_at = now_iso()
    new_state = "done" if action == "complete" else "draft"
    db.execute(f"UPDATE match SET {me}_state = ?, {me}_saved_at = ? WHERE id = ?",
               (new_state, saved_at, match_id))
    db.commit()
    m = db.execute("SELECT * FROM match WHERE id = ?", (match_id,)).fetchone()
    out = public_status(match_status(db, m, current_user.id))
    out["ok"] = True
    if action == "draft" and problem:
        out["notice"] = "임시 저장했어요. 완성하려면: " + problem["error"]
    return out


# ---------- 다시 고치기 (F7): 완성 → 만드는 중 ----------
@app.post("/matches/<int:match_id>/reopen")
@login_required
def reopen_questions(match_id):
    db = get_db()
    lock_db(db)
    m, err = my_match_or_error(db, match_id)
    if err:
        return err
    st = match_status(db, m, current_user.id)
    if not st["can_reopen"]:
        return {"error": "만들기 마감이 지나서 다시 고칠 수 없어요"}, 409
    db.execute(f"UPDATE match SET {st['me']}_state = 'draft' WHERE id = ?", (match_id,))
    db.commit()
    m = db.execute("SELECT * FROM match WHERE id = ?", (match_id,)).fetchone()
    return {"ok": True, **public_status(match_status(db, m, current_user.id))}


# ---------- 상대 문제 불러오기 (풀기용, 정답 숨김) (F8) ----------
def solve_block_reason(st):
    if st["bye"]:
        return "쉬는 라운드예요", 400
    if st["i_submitted"]:
        return "이미 제출했어요", 409
    if st["phase"] == "closed":
        return "마감이 지났어요", 409
    if not st["solve_open"]:
        return "아직 풀 수 없어요. 만들기 마감이 지나면 풀기 기간이 시작돼요", 409
    return None, None


@app.get("/matches/<int:match_id>/questions")
@login_required
def match_questions(match_id):
    db = get_db()
    m, err = my_match_or_error(db, match_id)
    if err:
        return err
    st = match_status(db, m, current_user.id)
    reason, code = solve_block_reason(st)
    if reason:
        return {"error": reason}, code
    # 정답·해설은 보내지 않는다 (채점 후에만 보여 줌)
    return {
        "questions": [
            {"id": r["id"], "subject": r["subject"], "qtype": r["qtype"],
             "content": r["content"], "choices": json.loads(r["choices"] or "[]")}
            for r in question_rows(db, match_id, st["opp_id"])
        ],
        "solve_deadline": st["solve_deadline"],
    }


# ---------- 답안 제출 + 자동 채점 (F8/F9) ----------
@app.post("/matches/<int:match_id>/submit")
@login_required
def submit_answers(match_id):
    db = get_db()
    lock_db(db)  # 제출을 두 번 눌러도 한 번만 채점되게
    m, err = my_match_or_error(db, match_id)
    if err:
        return err
    uid = current_user.id
    st = match_status(db, m, uid)
    reason, code = solve_block_reason(st)
    if reason:
        return {"error": reason}, code

    data = read_json()
    answers = data.get("answers")  # {question_id: given}
    # 형식이 틀린 요청이 '빈 답 제출'로 처리되면 안 되므로 answers가 꼭 dict여야 한다
    if not isinstance(answers, dict):
        return {"error": "답안 형식이 올바르지 않아요"}, 400

    questions = question_rows(db, match_id, st["opp_id"])
    if not questions:
        return {"error": "상대 문제가 없어요"}, 409

    score, results = 0, []
    for q in questions:
        given = answers.get(str(q["id"]), "")
        # 글자·숫자가 아닌 답(목록 등)은 빈 답으로, 너무 긴 답은 200자까지만
        given = str(given)[:200] if isinstance(given, (str, int, float)) and not isinstance(given, bool) else ""
        ok = grade_one(q, given)
        score += 1 if ok else 0
        db.execute(
            "INSERT INTO submission (match_id, solver_id, question_id, given, correct, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (match_id, uid, q["id"], given, 1 if ok else 0, now_iso()),
        )
        results.append({
            "id": q["id"], "subject": q["subject"], "qtype": q["qtype"], "content": q["content"],
            "choices": json.loads(q["choices"] or "[]"), "correct_answer": q["answer"],
            "given": given, "is_correct": ok, "explanation": q["explanation"],
        })

    me = st["me"]
    db.execute(f"UPDATE match SET {me}_done = 1, {me}_score = ? WHERE id = ?", (score, match_id))
    finalize_match_if_ready(db, match_id)  # 둘 다 냈으면 승·무·패 판정
    db.commit()
    return {"ok": True, "score": score, "total": len(questions), "results": results}


# ---------- 지난 경기 기록 (F13) ----------
@app.get("/matches/history")
@login_required
def match_history():
    db = get_db()
    uid = current_user.id
    past = request.args.get("league_id", type=int)
    if past is not None:
        # 지난 리그(보관한 리그)의 경기 기록: 내가 참가했던 리그만
        if not db.execute(
            "SELECT 1 FROM membership WHERE league_id = ? AND user_id = ? AND status = 'archived'",
            (past, uid),
        ).fetchone():
            return {"error": "내가 참가한 지난 리그가 아니에요"}, 403
        mem = {"league_id": past}
    else:
        mem = get_my_membership(db, uid)
    if mem is None:
        return {"error": "먼저 리그에 들어가세요"}, 403
    league_id = mem["league_id"]
    refresh_league(db, league_id)
    status = db.execute("SELECT status FROM league WHERE id = ?", (league_id,)).fetchone()["status"]
    # 아직 오지 않은 라운드는 '지난 경기'가 아니므로 뺀다 (끝난 리그는 모두)
    upto = current_round(db, league_id) if status == "running" else 10**6

    rows = db.execute(
        "SELECT * FROM match WHERE league_id = ? AND week <= ? "
        "AND (player1_id = ? OR player2_id = ?) ORDER BY week ASC",
        (league_id, upto, uid, uid),
    ).fetchall()

    history = []
    for m in rows:
        is_p1 = m["player1_id"] == uid
        opp_id = m["player2_id"] if is_p1 else m["player1_id"]
        if opp_id is None:
            # 아직 끝나지 않은 현재 쉬는 라운드는 '지난 경기'에 넣지 않는다
            # (학생을 내보내 리그가 일찍 끝나도, 실제로 오지 않은 라운드의 쉬는 경기는 보여 주지 않는다)
            sd = m["solve_deadline"]
            ended = (sd and now_utc() >= parse_utc(sd)) or (not sd and status == "finished")
            if ended:
                history.append({"match_id": m["id"], "week": m["week"], "bye": True})
            continue
        if m["result"] is None:
            continue  # 진행 중인 경기는 이번 경기 카드에서 보고, 지난 경기에는 넣지 않는다
        opp = db.execute(
            "SELECT nickname FROM user WHERE id = ?", (opp_id,)
        ).fetchone()
        my_score = m["p1_score"] if is_p1 else m["p2_score"]
        opp_score = m["p2_score"] if is_p1 else m["p1_score"]
        excluded = db.execute(
            "SELECT 1 FROM membership WHERE league_id = ? AND user_id = ? AND status = 'removed'",
            (league_id, opp_id),
        ).fetchone() is not None

        outcome = None  # win/lose/draw/pending
        if m["result"] is None:
            outcome = "pending"
        elif m["result"] == "draw":
            outcome = "draw"
        elif m["result"] == "both_lose":
            outcome = "lose"
        else:
            won = (m["result"] == "p1" and is_p1) or (m["result"] == "p2" and not is_p1)
            outcome = "win" if won else "lose"

        history.append(
            {
                "match_id": m["id"],
                "week": m["week"],
                "bye": False,
                "opponent": opp["nickname"],
                "my_score": my_score,
                "opp_score": opp_score,
                "outcome": outcome,
                "forfeit": bool(m["forfeit"]),
                "forfeit_stage": m["forfeit_stage"],
                "voids": db.execute("SELECT COUNT(*) FROM question WHERE match_id = ? AND void = 1",
                                    (m["id"],)).fetchone()[0],
                # 상대가 리그에서 나가(내보내져) 순위에 들어가지 않는 경기
                "excluded": excluded,
            }
        )
    return {"history": history}


# ---------- 지난 경기 상세 다시 보기 (F13) ----------
def outcome_for(m, is_p1):
    if m["result"] == "draw":
        return "draw"
    if m["result"] == "both_lose":
        return "both_lose"
    won = (m["result"] == "p1" and is_p1) or (m["result"] == "p2" and not is_p1)
    return "win" if won else "lose"


def forfeit_reason_for(m, is_p1):
    """내 입장에서 이해하기 쉬운 몰수 이유."""
    if not m["forfeit"]:
        return None
    me, op = ("p1", "p2") if is_p1 else ("p2", "p1")
    stage = "문제 만들기 마감까지 [완성]하지 않음" if m["forfeit_stage"] == "make" else "문제 풀기 마감까지 제출하지 않음"
    if m["result"] == "both_lose":
        return f"두 사람 모두 {stage} · 둘 다 패"
    if m["result"] == me:
        return f"상대가 {stage} · 내 몰수승"
    return f"내가 {stage} · 내 몰수패"


@app.get("/matches/<int:match_id>/review")
@login_required
def review_match(match_id):
    """끝난 내 경기의 상대 문제·내 답·정답·해설. 관리자와 다른 학생은 접근할 수 없다."""
    db = get_db()
    m, err = my_match_or_error(db, match_id)
    if err:
        return err
    uid = current_user.id
    is_p1 = m["player1_id"] == uid
    opp_id = m["player2_id"] if is_p1 else m["player1_id"]
    if opp_id is None:
        if m["solve_deadline"] and now_utc() < parse_utc(m["solve_deadline"]):
            return {"error": "아직 끝나지 않은 쉬는 라운드예요"}, 409
        return {"match_id": match_id, "week": m["week"], "bye": True, "questions": []}
    if m["result"] is None:
        return {"error": "아직 끝나지 않은 경기예요"}, 409

    opp = db.execute("SELECT nickname FROM user WHERE id = ?", (opp_id,)).fetchone()
    # 상대가 [완성]한 문제만. 만들기 몰수로 미완성인 임시 저장 문제는 공개하지 않는다.
    opp_side = "p2" if is_p1 else "p1"
    rows = []
    if m[f"{opp_side}_state"] == "done":
        rows = db.execute(
            "SELECT q.id, q.subject, q.qtype, q.content, q.choices, q.answer, q.explanation, "
            "q.void, q.void_reason, s.given, s.correct, r.status AS report_status, r.reason AS report_reason "
            "FROM question q "
            "LEFT JOIN submission s ON s.question_id = q.id AND s.match_id = q.match_id AND s.solver_id = ? "
            "LEFT JOIN report r ON r.question_id = q.id AND r.reporter_id = ? "
            "WHERE q.match_id = ? AND q.author_id = ? ORDER BY q.id",
            (uid, uid, match_id, opp_id),
        ).fetchall()
    league_status = db.execute("SELECT status FROM league WHERE id = ?", (m["league_id"],)).fetchone()["status"]
    questions = [
        {
            "id": r["id"], "subject": r["subject"], "qtype": r["qtype"],
            "content": r["content"], "choices": json.loads(r["choices"] or "[]"),
            "correct_answer": r["answer"], "given": r["given"] if r["given"] is not None else "",
            "is_correct": bool(r["correct"]) if r["correct"] is not None else False,
            "submitted": r["given"] is not None, "explanation": r["explanation"],
            "void": bool(r["void"]), "void_reason": r["void_reason"],
            "report_status": r["report_status"],
            "report_reason": REPORT_REASONS.get(r["report_reason"]) if r["report_reason"] else None,
            "can_report": r["given"] is not None and not r["void"] and r["report_status"] is None
                          and league_status == "running",
        }
        for r in rows
    ]
    # 내가 낸 문제 중 무효 처리된 것도 알려 준다 (어떤 문제를 왜 무효로 했는지)
    my_voids = [
        {"content": v["content"], "reason": v["void_reason"]}
        for v in db.execute(
            "SELECT content, void_reason FROM question WHERE match_id = ? AND author_id = ? AND void = 1",
            (match_id, uid),
        ).fetchall()
    ]
    my_score = m["p1_score"] if is_p1 else m["p2_score"]
    opp_score = m["p2_score"] if is_p1 else m["p1_score"]
    return {
        "match_id": match_id, "week": m["week"], "bye": False,
        "opponent": opp["nickname"], "outcome": outcome_for(m, is_p1),
        "forfeit": bool(m["forfeit"]), "forfeit_stage": m["forfeit_stage"],
        "forfeit_reason": forfeit_reason_for(m, is_p1),
        "my_score": 0 if m["forfeit"] else my_score,
        "opp_score": 0 if m["forfeit"] else opp_score,
        "questions": questions,
        "my_voids": my_voids,
        "scopes": round_scopes(db, m["league_id"], m["week"]),
    }


# ---------- 문제 신고·무효 (F17) ----------
REPORT_REASONS = {
    "wrong_answer": "정답이 틀렸어요",
    "out_of_scope": "출제 범위를 벗어났어요",
    "unclear": "문제나 보기가 불분명해요",
    "prank": "장난 문제예요",
    "other": "기타",
}
REPORT_DETAIL_MAX = 200


def solved_question(db, question_id, uid):
    """내가 제출해서 푼 상대 문제면 (문제 줄, 경기 줄), 아니면 (None, None)."""
    q = db.execute("SELECT * FROM question WHERE id = ?", (question_id,)).fetchone()
    if q is None or q["match_id"] is None or q["author_id"] == uid:
        return None, None
    m = db.execute("SELECT * FROM match WHERE id = ?", (q["match_id"],)).fetchone()
    if m is None or uid not in (m["player1_id"], m["player2_id"]):
        return None, None
    sub = db.execute(
        "SELECT 1 FROM submission WHERE question_id = ? AND solver_id = ? AND match_id = ?",
        (question_id, uid, m["id"]),
    ).fetchone()
    return (q, m) if sub else (None, None)


@app.post("/questions/<int:question_id>/report")
@login_required
def report_question(question_id):
    db = get_db()
    lock_db(db)  # 두 번 눌러도 한 번만
    q, m = solved_question(db, question_id, current_user.id)
    if q is None:
        return {"error": "내가 푼 문제만 신고할 수 있어요"}, 403
    refresh_league(db, m["league_id"])
    league = db.execute("SELECT status FROM league WHERE id = ?", (m["league_id"],)).fetchone()
    if league["status"] != "running":
        return {"error": "리그가 끝나서 더 신고할 수 없어요"}, 409
    if q["void"]:
        return {"error": "이미 무효 처리된 문제예요"}, 409
    data = read_json()
    reason = data.get("reason")
    if reason not in REPORT_REASONS:
        return {"error": "신고 이유를 골라 주세요"}, 400
    detail = " ".join(text_of(data, "detail").split())
    if len(detail) > REPORT_DETAIL_MAX:
        return {"error": f"자세한 이유는 {REPORT_DETAIL_MAX}자까지예요"}, 400
    if reason == "other" and not detail:
        return {"error": "'기타'를 고르면 이유를 짧게 적어 주세요"}, 400
    exists = db.execute(
        "SELECT 1 FROM report WHERE question_id = ? AND reporter_id = ?", (question_id, current_user.id)
    ).fetchone()
    if exists:
        return {"error": "이미 신고한 문제예요. 관리자 판정을 기다려 주세요"}, 409
    db.execute(
        "INSERT INTO report (league_id, match_id, question_id, reporter_id, reason, detail, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (m["league_id"], m["id"], question_id, current_user.id, reason, detail, now_iso()),
    )
    db.commit()
    return {"ok": True, "status": "pending"}, 201


@app.get("/admin/reports")
@login_required
def admin_reports():
    """신고 목록. 신고된 문제는 진행 중 경기라도 내용·정답·해설·범위를 볼 수 있다."""
    db = get_db()
    league, err = admin_league_or_error(db)
    if err:
        return err
    refresh_league(db, league["id"])
    rows = db.execute(
        "SELECT r.*, q.subject, q.qtype, q.content, q.choices, q.answer, q.explanation, q.void, "
        "m.week, ua.nickname AS author, ur.nickname AS reporter "
        "FROM report r JOIN question q ON q.id = r.question_id JOIN match m ON m.id = r.match_id "
        "JOIN user ua ON ua.id = q.author_id JOIN user ur ON ur.id = r.reporter_id "
        "WHERE r.league_id = ? ORDER BY (r.status = 'pending') DESC, r.created_at DESC",
        (league["id"],),
    ).fetchall()
    scopes_cache = {}
    items = []
    for r in rows:
        if r["week"] not in scopes_cache:
            scopes_cache[r["week"]] = round_scopes(db, league["id"], r["week"])
        scope = next((x["scope"] for x in scopes_cache[r["week"]] if x["subject"] == r["subject"]), "")
        items.append({
            "id": r["id"], "status": r["status"], "reason": r["reason"],
            "reason_text": REPORT_REASONS.get(r["reason"], r["reason"]), "detail": r["detail"],
            "round": r["week"], "author": r["author"], "reporter": r["reporter"],
            "subject": r["subject"], "scope": scope, "qtype": r["qtype"], "content": r["content"],
            "choices": json.loads(r["choices"] or "[]"), "correct_answer": r["answer"],
            "explanation": r["explanation"], "created_at": r["created_at"], "decided_at": r["decided_at"],
        })
    deadline = report_deadline(db, league["id"])
    league_now = db.execute("SELECT status FROM league WHERE id = ?", (league["id"],)).fetchone()
    return {
        "items": items,
        "pending": sum(1 for it in items if it["status"] == "pending"),
        "deadline": deadline.isoformat() if deadline else None,
        "league_status": league_now["status"],
    }


@app.post("/admin/reports/<int:report_id>")
@login_required
def judge_report(report_id):
    """[무효] 또는 [문제없음]. 무효면 문제를 무효로 만들고 경기 점수·결과를 다시 계산한다."""
    db = get_db()
    lock_db(db)
    league, err = admin_league_or_error(db)
    if err:
        return err
    decision = read_json().get("decision")
    if decision not in ("void", "ok"):
        return {"error": "[무효] 또는 [문제없음]을 골라 주세요"}, 400
    r = db.execute("SELECT * FROM report WHERE id = ? AND league_id = ?", (report_id, league["id"])).fetchone()
    if r is None:
        return {"error": "신고를 찾을 수 없어요"}, 404
    refresh_league(db, league["id"])
    r = db.execute("SELECT * FROM report WHERE id = ?", (report_id,)).fetchone()
    if r["status"] != "pending":
        return {"error": "이미 처리된 신고예요 (판정 기한이 지나면 자동으로 '문제없음'이 돼요)"}, 409
    deadline = report_deadline(db, league["id"])
    if deadline and now_utc() >= deadline:
        return {"error": "판정 기한이 지났어요"}, 409
    db.execute("UPDATE report SET status = ?, decided_at = ? WHERE id = ?",
               ("void" if decision == "void" else "ok", now_iso(), report_id))
    if decision == "void":
        db.execute("UPDATE question SET void = 1, void_reason = ? WHERE id = ?",
                   (REPORT_REASONS.get(r["reason"], "기타"), r["question_id"]))
        # 무효 문제는 오답 노트·정답률에서 빠진다
        recompute_match(db, r["match_id"])
    db.commit()
    return {"ok": True, "status": "void" if decision == "void" else "ok"}


# ---------- 오답 노트 (F18) ----------
def graded_result(q, given, ok):
    """채점된 문제 한 줄 (리그 결과 화면과 같은 모양이라 화면 코드를 같이 쓴다)."""
    return {
        "id": q["id"],
        "subject": q["subject"],
        "qtype": q["qtype"],
        "content": q["content"],
        "choices": q.get("choices", []),
        "correct_answer": str(q["answer"]),
        "given": given,
        "is_correct": ok,
        "explanation": q.get("explanation", ""),
    }


@app.get("/wrong-notes")
@login_required
def wrong_notes():
    """내가 틀린 문제 모음 (나만 볼 수 있음). 최근에 틀린 것부터."""
    db = get_db()
    uid = current_user.id
    known = {
        (r["source"], r["qkey"])
        for r in db.execute(
            "SELECT source, qkey FROM wrong_note_known WHERE user_id = ?", (uid,)
        ).fetchall()
    }
    items = []

    # 리그 경기: 내가 제출한 풀이 중 틀린 것 (내 풀이이므로 정답을 보여 줘도 된다)
    rows = db.execute(
        "SELECT s.given, s.created_at, q.id, q.subject, q.qtype, q.content, q.choices, "
        "q.answer, q.explanation, m.week, u.nickname AS opp "
        "FROM submission s "
        "JOIN question q ON q.id = s.question_id "
        "JOIN match m ON m.id = s.match_id "
        "JOIN user u ON u.id = q.author_id "
        "WHERE s.solver_id = ? AND s.correct = 0 AND q.void = 0 ORDER BY s.created_at DESC",
        (uid,),
    ).fetchall()
    for r in rows:
        q = {
            "id": r["id"], "subject": r["subject"], "qtype": r["qtype"],
            "content": r["content"], "choices": json.loads(r["choices"] or "[]"),
            "answer": r["answer"], "explanation": r["explanation"],
        }
        key = str(r["id"])
        item = graded_result(q, r["given"], False)
        item.update(source="league", key=key, where=f"{r['week']}라운드 · vs {r['opp']}",
                    at=r["created_at"], known=("league", key) in known)
        items.append(item)

    items.sort(key=lambda it: it["at"] or "", reverse=True)
    return {"items": items}


@app.post("/wrong-notes/known")
@login_required
def mark_known():
    """[이제 알아요] 켜기/끄기. 숨기기만 하고 지우지 않는다."""
    data = read_json()
    source = data.get("source")
    key = text_of(data, "key")
    known = data.get("known")
    if source != "league" or not key or not isinstance(known, bool):
        return {"error": "요청 형식이 올바르지 않아요"}, 400

    db = get_db()
    uid = current_user.id
    # 내가 실제로 틀린 문제만 표시할 수 있다
    mine = key.isdigit() and db.execute(
        "SELECT 1 FROM submission WHERE solver_id = ? AND question_id = ? AND correct = 0 LIMIT 1",
        (uid, int(key)),
    ).fetchone()
    if not mine:
        return {"error": "오답 노트에 없는 문제예요"}, 404

    if known:
        db.execute(
            "INSERT OR IGNORE INTO wrong_note_known (user_id, source, qkey, created_at) VALUES (?, ?, ?, ?)",
            (uid, source, key, now_iso()),
        )
    else:
        db.execute(
            "DELETE FROM wrong_note_known WHERE user_id = ? AND source = ? AND qkey = ?",
            (uid, source, key),
        )
    db.commit()
    return {"ok": True, "known": known}


@app.get("/wrong-notes/count")
@login_required
def wrong_note_count():
    """내 오답 전체 개수와 아직 [이제 알아요]로 정리하지 않은 개수 (홈 숫자 배지용)."""
    db = get_db()
    row = db.execute(
        """
        WITH wrong AS (
            SELECT DISTINCT s.question_id
            FROM submission s JOIN question q ON q.id = s.question_id
            WHERE s.solver_id = ? AND s.correct = 0 AND q.void = 0
        )
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN k.qkey IS NULL THEN 1 ELSE 0 END) AS active
        FROM wrong w
        LEFT JOIN wrong_note_known k
          ON k.user_id = ? AND k.source = 'league'
         AND k.qkey = CAST(w.question_id AS TEXT)
        """,
        (current_user.id, current_user.id),
    ).fetchone()
    return {"total": row["total"] or 0, "active": row["active"] or 0}
