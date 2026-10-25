"""문제 신고와 관리자 판정 (F17)."""

import json

from flask import Blueprint
from flask_login import current_user, login_required

from classleague import clock
from classleague.db import get_db, lock_db
from classleague.engine import recompute_match, refresh_league, report_deadline, REPORT_REASONS
from classleague.inputs import read_json, text_of
from classleague.league_state import admin_league_or_error, round_scopes

bp = Blueprint("reports", __name__)


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


@bp.post("/questions/<int:question_id>/report")
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
        (m["league_id"], m["id"], question_id, current_user.id, reason, detail, clock.now_iso()),
    )
    db.commit()
    return {"ok": True, "status": "pending"}, 201


@bp.get("/admin/reports")
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


@bp.post("/admin/reports/<int:report_id>")
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
    if deadline and clock.now_utc() >= deadline:
        return {"error": "판정 기한이 지났어요"}, 409
    db.execute("UPDATE report SET status = ?, decided_at = ? WHERE id = ?",
               ("void" if decision == "void" else "ok", clock.now_iso(), report_id))
    if decision == "void":
        db.execute("UPDATE question SET void = 1, void_reason = ? WHERE id = ?",
                   (REPORT_REASONS.get(r["reason"], "기타"), r["question_id"]))
        # 무효 문제는 오답 노트·정답률에서 빠진다
        recompute_match(db, r["match_id"])
    db.commit()
    return {"ok": True, "status": "void" if decision == "void" else "ok"}
