import json
import json
import os
import re
import sqlite3
from datetime import datetime, timezone

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
                user_id INTEGER NOT NULL UNIQUE,
                joined_at TEXT NOT NULL
            )
            """
        )
        # 대진/경기 (F6): 리그, 주차, 두 선수, 결과, 각자 점수
        # result = NULL(아직)/'p1'(선수1 승)/'p2'(선수2 승)/'draw'(무)
        # player2_id가 NULL이면 그 주는 부전승(상대가 없음)
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
                p2_score INTEGER DEFAULT 0
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

        # --- 간단 마이그레이션: 예전에 만든 league 테이블에 subjects 컬럼이 없으면 추가 ---
        cols = [r[1] for r in db.execute("PRAGMA table_info(league)").fetchall()]
        if "subjects" not in cols:
            db.execute(
                "ALTER TABLE league ADD COLUMN subjects TEXT NOT NULL DEFAULT '[]'"
            )


init_db()


def gen_league_code(db):
    """서로 겹치지 않는 6자리 숫자 코드를 만든다 (README 5번)."""
    import random

    for _ in range(100):
        code = f"{random.randint(0, 999999):06d}"
        exists = db.execute(
            "SELECT 1 FROM league WHERE code = ?", (code,)
        ).fetchone()
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


def compute_standings(db, league_id):
    """
    순위표를 계산한다 (F11). 각 선수의 경기수·승·무·패·승점·득점.
    끝난 경기(result가 있는 것)만 센다.
    순위 정렬: 승점 → 득점(맞힌 문제 합) → 닉네임.
    """
    members = db.execute(
        """
        SELECT u.id, u.nickname
        FROM membership m JOIN user u ON u.id = m.user_id
        WHERE m.league_id = ?
        """,
        (league_id,),
    ).fetchall()

    stats = {
        m["id"]: {
            "user_id": m["id"],
            "nickname": m["nickname"],
            "played": 0,
            "win": 0,
            "draw": 0,
            "lose": 0,
            "points": 0,
            "scored": 0,
        }
        for m in members
    }

    matches = db.execute(
        "SELECT player1_id, player2_id, result, p1_score, p2_score "
        "FROM match WHERE league_id = ? AND result IS NOT NULL",
        (league_id,),
    ).fetchall()

    for mt in matches:
        p1, p2 = mt["player1_id"], mt["player2_id"]
        if p2 is None:
            # 부전승(쉬는 주): 승점·경기수 아무것도 세지 않는다 (홀수 인원일 때만 생김)
            continue
        if p1 in stats:
            stats[p1]["played"] += 1
            stats[p1]["scored"] += mt["p1_score"] or 0
        if p2 in stats:
            stats[p2]["played"] += 1
            stats[p2]["scored"] += mt["p2_score"] or 0
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

    table = sorted(
        stats.values(),
        key=lambda s: (-s["points"], -s["scored"], s["nickname"]),
    )
    for i, row in enumerate(table, start=1):
        row["rank"] = i
    return table


def total_weeks(db, league_id):
    """이 리그의 전체 주차 수 (대진표에서 가장 큰 week)."""
    row = db.execute(
        "SELECT MAX(week) AS w FROM match WHERE league_id = ?", (league_id,)
    ).fetchone()
    return row["w"] or 0


def current_week(db, league_id):
    """
    지금 진행 중인 주차. 아직 결과가 안 난 가장 이른 주차.
    모두 끝났으면 마지막 주차.
    """
    row = db.execute(
        "SELECT MIN(week) AS w FROM match WHERE league_id = ? AND result IS NULL",
        (league_id,),
    ).fetchone()
    if row["w"]:
        return row["w"]
    return total_weeks(db, league_id)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


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
    if current_user.is_authenticated:
        return {"logged_in": True, "nickname": current_user.nickname}
    return {"logged_in": False}


# ---------- 회원가입 (F1) ----------
@app.post("/register")
def register():
    data = request.json or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    nickname = (data.get("nickname") or "").strip()

    # 입력 검사 (README F1)
    if not re.fullmatch(r"[A-Za-z0-9]{4,20}", username):
        return {"error": "아이디는 영문·숫자 4~20자여야 해요"}, 400
    if not (8 <= len(password) <= 64):
        return {"error": "비밀번호는 8~64자여야 해요"}, 400
    if not (1 <= len(nickname) <= 10):
        return {"error": "닉네임은 1~10자여야 해요"}, 400

    db = get_db()
    exists = db.execute(
        "SELECT 1 FROM user WHERE username = ?", (username,)
    ).fetchone()
    if exists:
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
    data = request.json or {}
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


# ---------- 리그 만들기 (F3): 만든 사람이 관리자가 된다 ----------
@app.post("/leagues")
@login_required
def create_league():
    data = request.json or {}
    name = (data.get("name") or "").strip()
    if not (1 <= len(name) <= 30):
        return {"error": "리그 이름은 1~30자여야 해요"}, 400

    # 과목 설정 검사 (F4): [{"name":"영어","count":3}, ...]
    raw_subjects = data.get("subjects") or []
    if not isinstance(raw_subjects, list) or len(raw_subjects) == 0:
        return {"error": "과목을 하나 이상 넣어 주세요"}, 400
    subjects = []
    seen_names = set()
    for s in raw_subjects:
        if not isinstance(s, dict):
            return {"error": "과목 형식이 올바르지 않아요"}, 400
        sname = (s.get("name") or "").strip()
        count = s.get("count")
        if not (1 <= len(sname) <= 20):
            return {"error": "과목 이름은 1~20자여야 해요"}, 400
        if sname in seen_names:
            return {"error": "같은 과목 이름이 두 번 들어갔어요"}, 400
        seen_names.add(sname)
        if not isinstance(count, int) or not (1 <= count <= 20):
            return {"error": "과목별 문제 수는 1~20개여야 해요"}, 400
        subjects.append({"name": sname, "count": count})

    db = get_db()
    code = gen_league_code(db)
    cur = db.execute(
        "INSERT INTO league (name, code, admin_id, status, subjects, created_at) "
        "VALUES (?, ?, ?, 'recruiting', ?, ?)",
        (name, code, current_user.id, json.dumps(subjects), now_iso()),
    )
    db.commit()
    return {"ok": True, "league_id": cur.lastrowid, "code": code}, 201


# ---------- 리그 입장 (F5): 6자리 코드로 들어간다. 한 학생은 리그 하나만 ----------
@app.post("/leagues/join")
@login_required
def join_league():
    data = request.json or {}
    code = (data.get("code") or "").strip()
    if not re.fullmatch(r"[0-9]{6}", code):
        return {"error": "리그 코드는 6자리 숫자예요"}, 400

    db = get_db()

    # 이미 리그에 들어가 있으면 막는다 (한 학생은 리그 하나만)
    if get_my_membership(db, current_user.id):
        return {"error": "이미 들어간 리그가 있어요"}, 409

    league = db.execute(
        "SELECT id, status FROM league WHERE code = ?", (code,)
    ).fetchone()
    if league is None:
        return {"error": "그런 코드의 리그가 없어요"}, 404
    if league["status"] != "recruiting":
        return {"error": "이미 시작했거나 끝난 리그예요"}, 409

    db.execute(
        "INSERT INTO membership (league_id, user_id, joined_at) VALUES (?, ?, ?)",
        (league["id"], current_user.id, now_iso()),
    )
    db.commit()
    return {"ok": True, "league_id": league["id"]}


# ---------- 내 리그 정보 보기 (명단 포함) ----------
@app.get("/leagues/mine")
@login_required
def my_league():
    db = get_db()
    mem = get_my_membership(db, current_user.id)
    admin_league = None

    # 내가 관리자인 리그가 있는지도 본다 (관리자는 입장하지 않아도 리그를 가짐)
    if mem is None:
        admin_row = db.execute(
            "SELECT id FROM league WHERE admin_id = ? ORDER BY id DESC LIMIT 1",
            (current_user.id,),
        ).fetchone()
        if admin_row:
            admin_league = admin_row["id"]

    league_id = mem["league_id"] if mem else admin_league
    if league_id is None:
        return {"in_league": False}

    league = db.execute(
        "SELECT id, name, code, admin_id, status, subjects FROM league WHERE id = ?",
        (league_id,),
    ).fetchone()

    members = db.execute(
        """
        SELECT u.id, u.nickname
        FROM membership m JOIN user u ON u.id = m.user_id
        WHERE m.league_id = ?
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
        },
        "members": [{"id": m["id"], "nickname": m["nickname"]} for m in members],
    }

    # 리그가 시작됐으면 순위표·주차·이번 주 상대도 함께 준다
    if league["status"] in ("running", "finished"):
        week = current_week(db, league_id)
        weeks = total_weeks(db, league_id)
        result["week"] = week
        result["total_weeks"] = weeks
        result["standings"] = compute_standings(db, league_id)

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

    # 내가 관리자인 리그 찾기
    league = db.execute(
        "SELECT id, status FROM league WHERE admin_id = ? ORDER BY id DESC LIMIT 1",
        (current_user.id,),
    ).fetchone()
    if league is None:
        return {"error": "관리자인 리그가 없어요"}, 403
    if league["status"] != "recruiting":
        return {"error": "이미 시작했거나 끝난 리그예요"}, 409

    # 참가자 모으기 (들어온 순서대로)
    members = db.execute(
        "SELECT user_id FROM membership WHERE league_id = ? ORDER BY joined_at ASC",
        (league["id"],),
    ).fetchall()
    player_ids = [m["user_id"] for m in members]
    if len(player_ids) < 2:
        return {"error": "학생이 2명 이상 있어야 시작할 수 있어요"}, 400

    # 대진표 자동 생성 (라운드 로빈)
    rounds = make_round_robin(player_ids)
    for week_index, pairs in enumerate(rounds, start=1):
        for p1, p2 in pairs:
            db.execute(
                "INSERT INTO match (league_id, week, player1_id, player2_id) "
                "VALUES (?, ?, ?, ?)",
                (league["id"], week_index, p1, p2),
            )

    db.execute(
        "UPDATE league SET status = 'running' WHERE id = ?", (league["id"],)
    )
    db.commit()
    return {"ok": True, "weeks": len(rounds)}


# ---------- 내가 만든 문제 불러오기 (F7: 다시 열면 그대로) ----------
@app.get("/questions/mine")
@login_required
def my_questions():
    db = get_db()
    mem = get_my_membership(db, current_user.id)
    if mem is None:
        return {"error": "먼저 리그에 들어가세요"}, 403
    league_id = mem["league_id"]

    league = db.execute(
        "SELECT subjects FROM league WHERE id = ?", (league_id,)
    ).fetchone()
    subjects = json.loads(league["subjects"] or "[]")

    rows = db.execute(
        "SELECT id, subject, qtype, content, choices, answer, explanation "
        "FROM question WHERE league_id = ? AND author_id = ? ORDER BY id ASC",
        (league_id, current_user.id),
    ).fetchall()
    questions = [
        {
            "subject": r["subject"],
            "qtype": r["qtype"],
            "content": r["content"],
            "choices": json.loads(r["choices"] or "[]"),
            "answer": r["answer"],
            "explanation": r["explanation"],
        }
        for r in rows
    ]
    return {"subjects": subjects, "questions": questions}


# ---------- 문제 저장 (F7) ----------
@app.post("/questions")
@login_required
def save_questions():
    db = get_db()
    mem = get_my_membership(db, current_user.id)
    if mem is None:
        return {"error": "먼저 리그에 들어가세요"}, 403
    league_id = mem["league_id"]

    league = db.execute(
        "SELECT subjects FROM league WHERE id = ?", (league_id,)
    ).fetchone()
    subjects = json.loads(league["subjects"] or "[]")
    # 과목별로 몇 개 필요한지 (예: {"영어":3})
    need = {s["name"]: s["count"] for s in subjects}

    data = request.json or {}
    items = data.get("questions") or []
    if not isinstance(items, list):
        return {"error": "문제 형식이 올바르지 않아요"}, 400

    # 과목별 개수를 세면서 하나씩 검사한다
    got = {name: 0 for name in need}
    cleaned = []
    for q in items:
        if not isinstance(q, dict):
            return {"error": "문제 형식이 올바르지 않아요"}, 400
        subject = (q.get("subject") or "").strip()
        qtype = q.get("qtype")
        content = (q.get("content") or "").strip()
        explanation = (q.get("explanation") or "").strip()

        if subject not in need:
            return {"error": f"'{subject}'는 이 리그의 과목이 아니에요"}, 400
        if qtype not in ("mc", "sa"):
            return {"error": "문제 유형이 올바르지 않아요"}, 400
        if not (1 <= len(content) <= 1000):
            return {"error": "문제 내용을 넣어 주세요 (1~1000자)"}, 400
        if len(explanation) > 1000:
            return {"error": "해설은 1000자까지예요"}, 400

        if qtype == "mc":
            choices = q.get("choices") or []
            if not isinstance(choices, list) or not (2 <= len(choices) <= 5):
                return {"error": "객관식 보기는 2~5개여야 해요"}, 400
            choices = [(c or "").strip() for c in choices]
            if any(len(c) == 0 for c in choices):
                return {"error": "객관식 보기를 모두 채워 주세요"}, 400
            try:
                ans_idx = int(q.get("answer"))
            except (TypeError, ValueError):
                return {"error": "객관식 정답을 골라 주세요"}, 400
            if not (0 <= ans_idx < len(choices)):
                return {"error": "객관식 정답 번호가 올바르지 않아요"}, 400
            cleaned.append(
                (subject, "mc", content, json.dumps(choices, ensure_ascii=False),
                 str(ans_idx), explanation)
            )
        else:  # 주관식
            answer = (q.get("answer") or "").strip()
            if not (1 <= len(answer) <= 200):
                return {"error": "주관식 정답을 넣어 주세요"}, 400
            cleaned.append(
                (subject, "sa", content, "[]", answer, explanation)
            )

        got[subject] += 1

    # 과목별 개수가 정확히 맞아야 저장 (README 5번)
    for name, cnt in need.items():
        if got.get(name, 0) != cnt:
            return {
                "error": f"'{name}' 과목은 {cnt}문제를 만들어야 해요 (지금 {got.get(name,0)}개)"
            }, 400

    # 기존 문제를 지우고 새로 저장 (다시 저장하면 덮어쓰기)
    db.execute(
        "DELETE FROM question WHERE league_id = ? AND author_id = ?",
        (league_id, current_user.id),
    )
    for (subject, qtype, content, choices, answer, explanation) in cleaned:
        db.execute(
            "INSERT INTO question (league_id, author_id, subject, qtype, content, choices, answer, explanation) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (league_id, current_user.id, subject, qtype, content, choices, answer, explanation),
        )
    db.commit()
    return {"ok": True, "count": len(cleaned)}
