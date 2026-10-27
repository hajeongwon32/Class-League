"""혼자 체험해 보기 (classleague/demo.py, routes/demo.py)"""
import sqlite3
from contextlib import closing

from classleague import db as db_module, demo
from classleague.db import get_db
from conftest import current, questions


def demo_client(app):
    c = app.test_client()
    r = c.post("/demo/start")
    assert r.status_code == 201, r.get_json()
    return c


def mine(c):
    return c.get("/leagues/mine").get_json()


def test_start_without_login_makes_a_running_league_with_three_friends(app):
    c = demo_client(app)
    assert c.get("/me").get_json()["logged_in"] is True, "로그인하지 않아도 체험 계정으로 바로 들어간다"
    data = mine(c)
    assert data["in_league"] and data["league"]["status"] == "running"
    assert len(data["standings"]) == 4 and data["total_weeks"] == 3
    assert data["demo"] == {"as_teacher": False, "guest": True, "next": "1라운드 문제 만들기 마감"}
    st = current(c)
    assert st["phase"] == "make" and st["opp_ready"], "가상 친구는 문제를 미리 [완성]해 둔다"
    # 시작을 또 눌러도 리그가 하나 더 생기지 않는다
    assert c.post("/demo/start").status_code == 200
    assert mine(c)["league"]["id"] == data["league"]["id"]


def test_full_round_with_bots(app):
    c = demo_client(app)
    mid = current(c)["match_id"]
    assert c.post("/demo/fill").status_code == 200, "예시 문제로 채우기"
    filled = c.get(f"/matches/{mid}/my-questions").get_json()["questions"]
    assert len(filled) == 3
    assert c.post(f"/matches/{mid}/my-questions", json={"action": "complete", "questions": filled}).status_code == 200

    r = c.post("/demo/advance").get_json()
    assert r["passed"] == "1라운드 문제 만들기 마감"
    st = current(c)
    assert st["phase"] == "solve" and st["opp_submitted"], "풀기 기간이 되면 가상 친구가 바로 풀어 제출한다"

    qs = c.get(f"/matches/{mid}/questions").get_json()["questions"]
    assert all("answer" not in q for q in qs), "체험에서도 정답은 제출 전에 보이지 않는다"
    r = c.post(f"/matches/{mid}/submit", json={"answers": {str(q["id"]): "" for q in qs}})
    assert r.status_code == 200
    hist = c.get("/matches/history").get_json()["history"]
    assert hist[0]["outcome"] in ("win", "draw", "lose") and not hist[0]["forfeit"]
    assert c.get("/wrong-notes/count").get_json()["active"] == 3, "빈 답은 오답 노트로"
    # 가상 친구끼리의 경기도 끝나 순위에 반영된다
    assert sum(r["played"] for r in mine(c)["standings"]) == 4


def test_not_completing_before_advance_is_a_forfeit(app):
    c = demo_client(app)
    c.post("/demo/advance")
    hist = c.get("/matches/history").get_json()["history"]
    assert hist[0]["forfeit"] and hist[0]["forfeit_stage"] == "make" and hist[0]["outcome"] == "lose"


def test_advance_to_the_end_shows_final_result(app):
    c = demo_client(app)
    for _ in range(6):  # 3라운드 × (만들기 마감, 풀기 마감)
        assert c.post("/demo/advance").get_json()["passed"]
    assert c.post("/demo/advance").get_json()["passed"] is None, "더 넘길 단계가 없다"
    data = mine(c)
    assert data["league"]["status"] == "finished"
    assert data["final"]["finalized"] and data["final"]["awards"][0]["text"] == "우승 메달"
    assert data["demo"]["next"] is None


def test_pending_report_is_settled_by_advance(app):
    c = demo_client(app)
    mid = current(c)["match_id"]
    c.post("/demo/fill")
    c.post(f"/matches/{mid}/my-questions", json={"action": "complete",
                                                  "questions": c.get(f"/matches/{mid}/my-questions").get_json()["questions"]})
    c.post("/demo/advance")
    qs = c.get(f"/matches/{mid}/questions").get_json()["questions"]
    c.post(f"/matches/{mid}/submit", json={"answers": {}})
    assert c.post(f"/questions/{qs[0]['id']}/report", json={"reason": "unclear"}).status_code == 201
    for _ in range(5):
        c.post("/demo/advance")
    assert mine(c)["final"]["finalized"] is False, "리그는 끝났지만 신고 판정 전"
    assert "신고 판정 기한" in c.post("/demo/advance").get_json()["passed"]
    assert mine(c)["final"]["finalized"] is True


def test_switch_to_teacher_and_back(app):
    c = demo_client(app)
    r = c.post("/demo/switch").get_json()
    assert r["as_teacher"] and r["nickname"] == "체험 선생님"
    assert mine(c)["is_admin"] and mine(c)["demo"]["as_teacher"]
    assert c.get("/admin/progress").status_code == 200
    assert c.post("/demo/fill").status_code == 403, "선생님 화면에서는 문제를 만들지 않는다"
    r = c.post("/demo/switch").get_json()
    assert not r["as_teacher"] and r["nickname"] == "나"
    assert not mine(c)["is_admin"]


def lose_first_round(c):
    """체험 1라운드: 예시 문제로 [완성]하고, 상대 문제는 모두 비워 제출한다 (오답 3개)."""
    mid = current(c)["match_id"]
    c.post("/demo/fill")
    mine_q = c.get(f"/matches/{mid}/my-questions").get_json()["questions"]
    c.post(f"/matches/{mid}/my-questions", json={"action": "complete", "questions": mine_q})
    c.post("/demo/advance")
    c.post(f"/matches/{mid}/submit", json={"answers": {}})
    assert c.get("/wrong-notes/count").get_json()["active"] == 3


def db_count(sql, args=()):
    with closing(sqlite3.connect(db_module.DB_PATH)) as conn:
        return conn.execute(sql, args).fetchone()[0]


def test_guest_end_deletes_everything_and_logs_out(app):
    c = demo_client(app)
    league_id = mine(c)["league"]["id"]
    lose_first_round(c)
    c.post("/demo/switch")  # 선생님 화면에서 끝내도 된다
    r = c.post("/demo/end").get_json()
    assert r["ok"] and r["logged_out"] is True
    assert c.get("/me").get_json()["logged_in"] is False, "임시 계정은 다시 로그인할 수 없어서 끝내면 로그아웃한다"
    for table in ("league", "membership", "match", "question", "report", "round_scope"):
        key = "id" if table == "league" else "league_id"
        assert db_count(f"SELECT COUNT(*) FROM {table} WHERE {key} = ?", (league_id,)) == 0, table
    assert db_count("SELECT COUNT(*) FROM submission") == 0, "체험 풀이(오답 노트의 근거)도 지운다"
    assert db_count("SELECT COUNT(*) FROM user WHERE demo_kind IS NOT NULL") == 0, "임시 계정·가상 친구 계정도 지운다"


def test_own_account_end_keeps_account_and_clears_wrong_notes(app, league, new_user):
    admin, students, code = league(2)
    c = new_user("stu9001", "지아")
    assert c.post("/demo/start").status_code == 201
    lose_first_round(c)
    r = c.post("/demo/end").get_json()
    assert r["ok"] and r["logged_out"] is False and r["nickname"] == "지아"
    assert c.get("/me").get_json()["logged_in"] is True, "내 계정은 그대로"
    assert c.get("/wrong-notes/count").get_json() == {"total": 0, "active": 0}, "체험 오답은 오답 노트에 남지 않는다"
    assert c.get("/leagues/past").get_json()["leagues"] == [], "체험 리그는 지난 리그에 남지 않는다"
    assert c.post("/leagues/join", json={"code": code}).status_code == 200, "끝내면 진짜 리그에 들어갈 수 있다"


def test_delete_demo_league_never_touches_real_league(app, league):
    admin, students, code = league(2)
    with app.app_context():
        db = get_db()
        real_id = db.execute("SELECT id FROM league WHERE code = ?", (code,)).fetchone()["id"]
        demo.delete_demo_league(db, real_id)
        db.commit()
    assert students[0].get("/leagues/mine").get_json()["in_league"] is True


def test_real_leagues_are_never_touched(app, league, clock):
    admin, (a, b), code = league(2)
    admin.post("/leagues/start", json={"first_date": "2026-10-26"})
    clock.set(2026, 10, 26, 1, 0)
    before = current(a)
    for c in (admin, a):
        for url in ("/demo/advance", "/demo/fill", "/demo/switch", "/demo/end"):
            assert c.post(url).status_code == 403, url
    assert current(a)["make_deadline"] == before["make_deadline"], "진짜 리그의 마감은 그대로"
    # 진짜 리그에 있는 사람은 체험을 시작할 수 없고, 체험 리그 코드로는 아무도 들어올 수 없다
    assert a.post("/demo/start").status_code == 409
    c = demo_client(app)
    demo_code = mine(c)["league"]["code"]
    outsider = app.test_client()
    outsider.post("/register", json={"username": "outsider1", "password": "password123", "nickname": "밖"})
    assert outsider.post("/leagues/join", json={"code": demo_code}).status_code >= 400
    assert a.post(f"/matches/{before['match_id']}/my-questions", json={"action": "complete", "questions": questions()}).status_code == 200


def test_logged_in_user_can_demo_with_own_nickname(new_user):
    c = new_user("stu0001", "지아")
    assert c.post("/demo/start").status_code == 201
    names = [r["nickname"] for r in mine(c)["standings"]]
    assert "지아" in names and len(set(names)) == 4, "가상 친구 이름은 내 닉네임과 겹치지 않는다"
    assert mine(c)["demo"]["guest"] is False, "내 계정으로 체험하면 임시 계정이 아니다"
