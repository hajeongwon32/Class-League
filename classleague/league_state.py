"""리그·참가자 조회와 상태 정리: 코드 발급, 닉네임 중복, 관리자 리그 찾기, 출제 범위, 최종 결과."""

import json

from flask_login import current_user

from classleague import clock
from classleague.engine import report_deadline


# ---------- 리그 코드·참가자 ----------
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


# ---------- 관리자 리그 찾기 ----------
def admin_running_league(db):
    """내가 관리자인 리그 (없으면 None)."""
    return db.execute(
        "SELECT id, status FROM league WHERE admin_id = ? AND admin_closed = 0 AND deleted = 0 "
        "ORDER BY id DESC LIMIT 1",
        (current_user.id,),
    ).fetchone()


def admin_league_or_error(db):
    """내가 관리자인 시작된 리그 (없으면 오류 응답)."""
    league = admin_running_league(db)
    if league is None:
        return None, ({"error": "관리자만 볼 수 있어요"}, 403)
    if league["status"] == "recruiting":
        return None, ({"error": "리그가 시작되면 볼 수 있어요"}, 409)
    return league, None


# ---------- 리그 상태·최종 결과 (F15) ----------
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
                   (clock.now_iso(), league_id))


# ---------- 과목별 문제 수·출제 범위 (F4-2) ----------
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
