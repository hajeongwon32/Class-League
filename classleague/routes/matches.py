"""경기: 이번 경기, 문제 만들기·완성, 풀기·채점, 지난 경기 (F7~F13)."""

import json

from flask import Blueprint, request
from flask_login import current_user, login_required

from classleague import clock
from classleague.clock import parse_utc
from classleague.db import get_db, lock_db
from classleague.engine import current_round, finalize_match_if_ready, grade_one, refresh_league, REPORT_REASONS
from classleague.inputs import read_json, text_of
from classleague.league_state import get_my_membership, league_need, round_scopes

bp = Blueprint("matches", __name__)


# ---------- 경기 하나의 상태 (F7·F8·F12) ----------
# 문제는 경기(라운드 상대)마다 새로 만든다. [임시 저장]은 'draft', [완성]은 'done'.
# 만들기 마감 전까지는 완성했어도 언제든 고칠 수 있고, 만들기 마감이 지나면 잠기고 풀기 기간이 시작된다.
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

    now = clock.now_utc()
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
@bp.get("/matches/current")
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
@bp.get("/matches/<int:match_id>/my-questions")
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
@bp.post("/matches/<int:match_id>/my-questions")
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
    saved_at = clock.now_iso()
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
@bp.post("/matches/<int:match_id>/reopen")
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


@bp.get("/matches/<int:match_id>/questions")
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
@bp.post("/matches/<int:match_id>/submit")
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
            (match_id, uid, q["id"], given, 1 if ok else 0, clock.now_iso()),
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
@bp.get("/matches/history")
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
            ended = (sd and clock.now_utc() >= parse_utc(sd)) or (not sd and status == "finished")
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


@bp.get("/matches/<int:match_id>/review")
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
        if m["solve_deadline"] and clock.now_utc() < parse_utc(m["solve_deadline"]):
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
