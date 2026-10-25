"""오답 노트 (F18)."""

import json

from flask import Blueprint
from flask_login import current_user, login_required

from classleague import clock
from classleague.db import get_db
from classleague.inputs import read_json, text_of

bp = Blueprint("notes", __name__)


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


@bp.get("/wrong-notes")
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


@bp.post("/wrong-notes/known")
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
            (uid, source, key, clock.now_iso()),
        )
    else:
        db.execute(
            "DELETE FROM wrong_note_known WHERE user_id = ? AND source = ? AND qkey = ?",
            (uid, source, key),
        )
    db.commit()
    return {"ok": True, "known": known}


@bp.get("/wrong-notes/count")
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
