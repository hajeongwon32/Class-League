"""혼자 체험해 보기 API: 시작 · 다음 단계로 · 예시 문제 채우기 · 선생님/학생 화면 바꾸기 · 체험 끝내기.
체험 리그에서만 동작하고, 진짜 리그에는 아무 영향이 없다 (classleague/demo.py)."""

import json
import secrets

from flask import Blueprint
from flask_login import current_user, login_required, login_user, logout_user

from classleague import clock, demo
from classleague.db import get_db, lock_db
from classleague.engine import refresh_league
from classleague.league_state import active_league_id, league_need
from classleague.routes.auth import User, bcrypt

bp = Blueprint("demo", __name__)


def my_demo_league(db):
    """지금 사용자가 보는 체험 리그 (체험하는 사람이거나 그 리그의 체험 선생님일 때). 아니면 None."""
    if not current_user.is_authenticated:
        return None
    league_id = active_league_id(db, current_user.id)
    if league_id is None:
        return None
    return db.execute(
        "SELECT id, admin_id, demo_owner_id FROM league WHERE id = ? AND demo_owner_id IS NOT NULL", (league_id,)
    ).fetchone()


def unknown_password_hash():
    """아무도 모르는 비밀번호의 해시: 체험용 계정은 이 화면에서만 쓰고 다시 로그인할 수 없다."""
    return bcrypt.generate_password_hash(secrets.token_hex(16)).decode("utf-8")


@bp.post("/demo/start")
def start_demo():
    db = get_db()
    password_hash = unknown_password_hash()  # 해시는 오래 걸려서 잠그기 전에 만든다
    lock_db(db)
    demo.cleanup_stale_demos(db)  # [체험 끝내기]를 안 누르고 떠난 지 하루가 지난 체험 기록 정리
    if current_user.is_authenticated:
        if my_demo_league(db):
            db.commit()
            return {"ok": True}
        if active_league_id(db, current_user.id) is not None:
            return {"error": "지금 들어가 있는 리그가 있어요. 그 리그를 보관(닫기)하거나 나간 뒤에 체험할 수 있어요"}, 409
        owner_id, nickname = current_user.id, current_user.nickname
    else:
        # 로그인하지 않았으면 체험용 계정을 바로 만들어 로그인한다 (회원가입 없이 바로 써 보기)
        username, nickname = "demo" + secrets.token_hex(8), "나"
        cur = db.execute(
            "INSERT INTO user (username, password_hash, nickname, created_at, demo_kind) VALUES (?, ?, ?, ?, 'guest')",
            (username, password_hash, nickname, clock.now_iso()),
        )
        owner_id = cur.lastrowid
        login_user(User(owner_id, username, nickname), remember=True)
    league_id = demo.create_demo_league(db, owner_id, nickname, password_hash)
    db.commit()
    return {"ok": True, "league_id": league_id, "nickname": nickname}, 201


@bp.post("/demo/advance")
@login_required
def advance_demo():
    db = get_db()
    league = my_demo_league(db)
    if league is None:
        return {"error": "체험 리그에서만 쓸 수 있어요"}, 403
    passed = demo.advance(db, league["id"])
    refresh_league(db, league["id"])  # 가상 친구 제출 → 몰수 → 라운드·리그 끝을 지금 바로 정산
    if passed is None:
        return {"ok": True, "passed": None}
    return {"ok": True, "passed": passed}


@bp.post("/demo/fill")
@login_required
def fill_demo_questions():
    """체험하는 사람의 이번 경기 문제 칸을 예시 문제로 채워 임시 저장한다 ([완성]은 직접 누른다)."""
    db = get_db()
    lock_db(db)
    league = my_demo_league(db)
    if league is None or league["demo_owner_id"] != current_user.id:
        return {"error": "체험 리그에서 학생일 때만 쓸 수 있어요"}, 403
    now = clock.now_iso()
    uid = current_user.id
    m = db.execute(
        "SELECT * FROM match WHERE league_id = ? AND result IS NULL AND player2_id IS NOT NULL "
        "AND (player1_id = ? OR player2_id = ?) AND round_start <= ? AND make_deadline > ? ORDER BY week LIMIT 1",
        (league["id"], uid, uid, now, now),
    ).fetchone()
    if m is None:
        return {"error": "지금은 문제를 만드는 단계가 아니에요"}, 409
    me = "p1" if m["player1_id"] == uid else "p2"
    if m[f"{me}_state"] == "done":
        return {"error": "이미 [완성]했어요. 고치려면 [다시 고치기]를 눌러 주세요"}, 409
    need = league_need(db, league["id"])
    db.execute("DELETE FROM question WHERE match_id = ? AND author_id = ?", (m["id"], uid))
    picks = {"수학": iter(demo.MATH_BANK[m["week"] * 3 % len(demo.MATH_BANK):] + demo.MATH_BANK),
             "영어": iter(demo.ENGLISH_BANK[m["week"] % len(demo.ENGLISH_BANK):] + demo.ENGLISH_BANK)}
    for subject, count in need.items():
        for _ in range(count):
            qtype, content, choices, answer, explanation = next(picks[subject])
            db.execute(
                "INSERT INTO question (league_id, match_id, author_id, subject, qtype, content, choices, answer, explanation) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (league["id"], m["id"], uid, subject, qtype, content,
                 json.dumps(choices or [], ensure_ascii=False), str(answer), explanation),
            )
    db.execute(f"UPDATE match SET {me}_state = 'draft', {me}_saved_at = ? WHERE id = ?", (now, m["id"]))
    db.commit()
    return {"ok": True, "match_id": m["id"]}


@bp.post("/demo/switch")
@login_required
def switch_demo_view():
    """체험 리그 안에서 학생 ↔ 체험 선생님 화면을 바꾼다. 그 체험 리그의 두 계정 사이에서만 바꿀 수 있다."""
    db = get_db()
    league = my_demo_league(db)
    if league is None:
        return {"error": "체험 리그에서만 쓸 수 있어요"}, 403
    target = league["demo_owner_id"] if current_user.id == league["admin_id"] else league["admin_id"]
    u = db.execute("SELECT id, username, nickname FROM user WHERE id = ?", (target,)).fetchone()
    login_user(User(u["id"], u["username"], u["nickname"]), remember=True)
    return {"ok": True, "as_teacher": target == league["admin_id"], "nickname": u["nickname"]}


@bp.post("/demo/end")
@login_required
def end_demo():
    """
    체험 리그를 기록째 지운다 (오답 노트에도 남지 않는다).
    - 내 계정으로 체험했으면: 내 계정으로 돌아온다. 그 뒤에는 진짜 리그에 들어가거나 만들 수 있다.
    - 로그인 없이 만든 임시 계정('나')이면: 그 계정도 지우고 로그아웃한다 (다시 로그인할 수 없는 계정이라서).
    """
    db = get_db()
    lock_db(db)
    league = my_demo_league(db)
    if league is None:
        return {"error": "체험 리그에서만 쓸 수 있어요"}, 403
    owner = db.execute("SELECT id, username, nickname, demo_kind FROM user WHERE id = ?",
                       (league["demo_owner_id"],)).fetchone()
    demo.delete_demo_league(db, league["id"])
    if owner["demo_kind"] == "guest":
        db.execute("DELETE FROM user WHERE id = ? AND demo_kind = 'guest'", (owner["id"],))
        db.commit()
        logout_user()
        return {"ok": True, "logged_out": True}
    db.commit()
    if current_user.id != owner["id"]:
        login_user(User(owner["id"], owner["username"], owner["nickname"]), remember=True)
    return {"ok": True, "logged_out": False, "nickname": owner["nickname"]}
