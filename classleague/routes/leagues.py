"""리그 만들기·설정·참가·시작·보관·삭제·내보내기 (F3~F6, F15)."""

import json
import re
from datetime import date, timedelta

from flask import Blueprint
from flask_login import current_user, login_required

from classleague import clock
from classleague.clock import kst_deadline_utc, kst_midnight_utc, parse_utc
from classleague.db import get_db, lock_db
from classleague.engine import current_round, refresh_league, round_rows
from classleague.inputs import read_json, text_of
from classleague.league_state import admin_running_league, final_summary, finish_if_too_few, gen_league_code, get_admin_league, get_my_membership, league_need, league_status, nickname_taken_in_league, pending_report_count, round_scopes
from classleague.schedule import build_schedule, clean_scope, DEADLINE_TIMES, END_DATE_MAX_DAYS, first_date_choices, make_round_robin, round_count, rounds_until, validate_make_days, validate_match_days
from classleague.standings import compute_standings, total_weeks

bp = Blueprint("leagues", __name__)


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
        today = clock.today_kst()
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
@bp.post("/leagues/settings")
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
@bp.get("/leagues/scopes")
@login_required
def list_round_scopes():
    """전체 라운드의 출제 범위와 잠금 여부. 시작한 라운드는 잠겨 있다."""
    db = get_db()
    league = admin_running_league(db)
    if league is None:
        return {"error": "관리자인 리그가 없어요"}, 403
    if league["status"] == "recruiting":
        return {"error": "리그를 시작하면 라운드별 범위를 정할 수 있어요. 지금은 기본 범위만 고칠 수 있어요"}, 409
    now = clock.now_utc()
    rounds = []
    for r in round_rows(db, league["id"]):
        start = parse_utc(r["rs"])
        rounds.append({
            "round": r["week"], "start": r["rs"], "make_deadline": r["md"], "solve_deadline": r["sd"],
            "locked": start is None or now >= start,
            "scopes": round_scopes(db, league["id"], r["week"]),
        })
    return {"rounds": rounds, "current": current_round(db, league["id"])}


@bp.post("/leagues/scopes")
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
    if row["rs"] is None or clock.now_utc() >= parse_utc(row["rs"]):
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
                (league["id"], rnd, subject, text, clock.now_iso()),
            )
    db.commit()
    return {"ok": True, "round": rnd, "scopes": round_scopes(db, league["id"], rnd)}


# ---------- 리그 만들기 (F3): 만든 사람이 관리자가 된다 ----------
@bp.post("/leagues")
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
         settings["league_mode"], settings["end_date"], clock.now_iso()),
    )
    db.commit()
    return {"ok": True, "league_id": cur.lastrowid, "code": code}, 201


# ---------- 리그 입장 (F5): 6자리 코드로 들어간다. 한 학생은 리그 하나만 ----------
@bp.post("/leagues/join")
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
        (league["id"], current_user.id, clock.now_iso()),
    )
    db.commit()
    return {"ok": True, "league_id": league["id"]}


# ---------- 리그 나가기 (F5): 모집 중일 때만 ----------
@bp.post("/leagues/leave")
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
@bp.post("/leagues/archive")
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
        (clock.now_iso(), current_user.id),
    )
    db.commit()
    return {"ok": True}


@bp.post("/leagues/close")
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


@bp.post("/leagues/delete")
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


@bp.post("/admin/students/<int:user_id>/remove")
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
    db.execute("UPDATE membership SET status = 'removed', left_at = ? WHERE id = ?", (clock.now_iso(), mem["id"]))
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
        (clock.now_iso(), league["id"], user_id),
    )
    finish_if_too_few(db, league["id"])
    db.commit()
    return {"ok": True, "league_status": league_status(db, league["id"])}


@bp.get("/leagues/past")
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


@bp.get("/leagues/past/<int:league_id>")
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
@bp.get("/leagues/mine")
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
        result["today"] = clock.today_kst().isoformat()
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
@bp.post("/leagues/start")
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
