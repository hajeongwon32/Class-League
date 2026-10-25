"""관리자 화면: 진행 상황, 과목별 정답률, 학생이 만든 문제 (F16)."""

import json

from flask import Blueprint
from flask_login import login_required

from classleague.db import get_db
from classleague.engine import current_round, refresh_league
from classleague.league_state import admin_league_or_error, league_need, round_scopes
from classleague.standings import total_weeks

bp = Blueprint("admin", __name__)


# ---------- 관리자 화면 (F16·F16-1·F16-2) ----------
@bp.get("/admin/progress")
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


@bp.get("/admin/accuracy")
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


@bp.get("/admin/students/<int:user_id>/questions")
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
