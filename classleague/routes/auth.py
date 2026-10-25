"""회원가입·로그인·닉네임 (F1·F2). 비밀번호는 bcrypt, 5번 틀리면 1분 잠금."""

import re
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, jsonify
from flask_bcrypt import Bcrypt
from flask_login import current_user, login_required, login_user, LoginManager, logout_user, UserMixin

from classleague import clock
from classleague.db import get_db, lock_db
from classleague.inputs import read_json, text_of
from classleague.league_state import get_my_membership, nickname_taken_in_league

bp = Blueprint("auth", __name__)


# 로그인을 연달아 틀릴 때 막는 기준 (SPEC 5. 보안·안전)
LOGIN_MAX_FAILS = 5


LOGIN_LOCK_SECONDS = 60


bcrypt = Bcrypt()  # app.py에서 init_app으로 앱에 붙인다


# 없는 아이디로 로그인할 때 검사용으로 쓰는 가짜 해시 (아래 login 참고)
DUMMY_PASSWORD_HASH = bcrypt.generate_password_hash(secrets.token_hex(16)).decode("utf-8")


login_manager = LoginManager()  # app.py에서 init_app으로 앱에 붙인다


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


# ---------- 로그인 상태 확인 ----------
@bp.get("/me")
def me():
    if current_user.is_authenticated:
        return {"logged_in": True, "nickname": current_user.nickname}
    return {"logged_in": False}


# ---------- 회원가입 (F1) ----------
@bp.post("/register")
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
        (username, password_hash, nickname, clock.now_iso()),
    )
    db.commit()
    # 가입하면 바로 로그인 (SPEC 4. 화면: 로그인을 한 번 더 하지 않아도 된다)
    login_user(User(cur.lastrowid, username, nickname), remember=True)
    return {"ok": True, "nickname": nickname}, 201


# ---------- 로그인 (F2) ----------
@bp.post("/login")
def login():
    data = read_json()
    username = text_of(data, "username")
    password = data.get("password") if isinstance(data.get("password"), str) else ""

    # 아이디가 있든 없든, 형식이 맞든 틀리든 똑같이 횟수를 센다
    # (다르게 대답하면 "이 아이디는 있다"는 걸 알려 주는 셈이 되기 때문)
    attempt_key = username[:64]  # 아주 긴 글자가 와도 기록이 커지지 않게

    db = get_db()
    now = clock.now_utc()

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
@bp.post("/me/nickname")
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
@bp.post("/logout")
@login_required
def logout():
    logout_user()
    return {"ok": True}
