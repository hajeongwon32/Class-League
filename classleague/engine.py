"""리그 진행: 마감 자동 처리(몰수), 채점, 결과 다시 계산, 신고 판정 기한 (F9·F10·F14·F17)."""

from datetime import timedelta

from classleague import clock
from classleague.clock import parse_utc
from classleague.db import lock_db


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
    now = clock.now_utc()
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
    now = clock.now_utc().isoformat()
    pending = db.execute(
        "SELECT COUNT(*) FROM match WHERE league_id = ? AND result IS NULL AND player2_id IS NOT NULL "
        "AND make_deadline IS NOT NULL AND make_deadline <= ?",
        (league_id, now),
    ).fetchone()[0]
    if not pending:
        return
    lock_db(db)  # 여러 사람이 동시에 열어도 한 번만 처리되게
    now_dt = clock.now_utc()
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
    if deadline is None or clock.now_utc() < deadline:
        return
    left = db.execute(
        "SELECT COUNT(*) FROM report WHERE league_id = ? AND status = 'pending'", (league_id,)
    ).fetchone()[0]
    if left:
        db.execute(
            "UPDATE report SET status = 'auto_ok', decided_at = ? WHERE league_id = ? AND status = 'pending'",
            (clock.now_iso(), league_id),
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
        finished = clock.now_utc() >= parse_utc(rows[-1]["sd"])
    if finished:
        db.execute("UPDATE league SET status = 'finished' WHERE id = ?", (league_id,))
        db.commit()


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


# ---------- 문제 신고 이유 (F17) ----------
REPORT_REASONS = {
    "wrong_answer": "정답이 틀렸어요",
    "out_of_scope": "출제 범위를 벗어났어요",
    "unclear": "문제나 보기가 불분명해요",
    "prank": "장난 문제예요",
    "other": "기타",
}
