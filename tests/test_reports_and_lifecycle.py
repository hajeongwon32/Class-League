"""신고·무효 재계산 (F17), 리그 생명주기: 삭제·내보내기·보관·단기 리그 (F15)"""
from conftest import current, questions


def finished_round(league, clock, n=2):
    """1라운드를 끝까지 치른 리그. a는 전부 맞히고 b는 전부 틀린다."""
    admin, students, code = league(n)
    admin.post("/leagues/start", json={"first_date": "2026-10-26"})
    clock.set(2026, 10, 26, 1, 0)
    a, b = students[0], students[1]
    mid = current(a)["match_id"]
    for s in (a, b):
        s.post(f"/matches/{mid}/my-questions", json={"action": "complete", "questions": questions()})
    clock.set(2026, 10, 27, 1, 0)
    qa = a.get(f"/matches/{mid}/questions").get_json()["questions"]
    a.post(f"/matches/{mid}/submit", json={"answers": {str(qa[0]["id"]): 1, str(qa[1]["id"]): "2"}})
    qb = b.get(f"/matches/{mid}/questions").get_json()["questions"]
    b.post(f"/matches/{mid}/submit", json={"answers": {str(qb[0]["id"]): 0, str(qb[1]["id"]): "9"}})
    return admin, students, mid, qa, qb


def points(client):
    return {r["nickname"]: r for r in client.get("/leagues/mine").get_json()["standings"]}


def test_void_report_gives_point_and_recomputes(league, clock):
    admin, (a, b), mid, qa, qb = finished_round(league, clock)
    assert points(a)["학생1"]["scored"] == 0
    assert b.get("/wrong-notes/count").get_json()["active"] == 2

    # 이유 없이 '기타'는 안 되고, 같은 문제는 한 번만 신고
    assert b.post(f"/questions/{qb[0]['id']}/report", json={"reason": "other"}).status_code == 400
    assert b.post(f"/questions/{qb[0]['id']}/report", json={"reason": "wrong_answer"}).status_code == 201
    assert b.post(f"/questions/{qb[0]['id']}/report", json={"reason": "wrong_answer"}).status_code == 409
    # 풀지 않은 문제(내가 만든 문제)는 신고할 수 없다
    own_id = qa[0]["id"]  # a가 푼 문제 = b가 만든 문제
    assert b.post(f"/questions/{own_id}/report", json={"reason": "wrong_answer"}).status_code >= 400

    rep = admin.get("/admin/reports").get_json()["items"][0]
    assert rep["correct_answer"] == "1", "신고된 문제는 관리자가 판정하려고 정답을 볼 수 있다"
    assert admin.post(f"/admin/reports/{rep['id']}", json={"decision": "void"}).status_code == 200
    assert admin.post(f"/admin/reports/{rep['id']}", json={"decision": "ok"}).status_code == 409, "판정은 바꿀 수 없다"

    assert points(a)["학생1"]["scored"] == 1, "무효 문제는 푼 학생에게 1점"
    assert b.get("/wrong-notes/count").get_json()["active"] == 1, "무효 문제는 오답 노트에서 빠진다"


def test_unjudged_report_becomes_ok_after_three_days(league, clock):
    admin, (a, b), mid, qa, qb = finished_round(league, clock)
    b.post(f"/questions/{qb[0]['id']}/report", json={"reason": "out_of_scope"})
    clock.set(2026, 10, 29, 0, 0)  # 리그는 끝났지만 판정 기한 전
    final = a.get("/leagues/mine").get_json()["final"]
    assert final["finalized"] is False and final["pending_reports"] == 1
    assert a.post("/leagues/archive").status_code == 409, "결과 확정 전에는 보관할 수 없다"

    clock.set(2026, 11, 5, 0, 0)  # 마지막 풀기 마감 + 3일이 지남
    final = a.get("/leagues/mine").get_json()["final"]
    assert final["finalized"] is True and final["winner"] == "학생0"
    assert points(a)["학생1"]["scored"] == 0, "자동 판정은 '문제없음'이라 점수가 바뀌지 않는다"


def test_archive_and_close_then_new_league(league, clock, new_user):
    admin, (a, b), mid, qa, qb = finished_round(league, clock)
    clock.set(2026, 11, 5, 0, 0)
    assert admin.post("/leagues/close").status_code == 200
    assert a.post("/leagues/archive").status_code == 200
    past = a.get("/leagues/past").get_json()["leagues"]
    assert past[0]["my_rank"] == 1 and past[0]["winner"] == "학생0"
    # 보관한 뒤에는 새 리그를 만들 수 있다
    r = a.post("/leagues", json={"name": "새 리그", "subjects": [{"name": "영어", "count": 1}],
                                 "match_days": [0], "deadline_time": "23:59"})
    assert r.status_code == 201, r.get_json()


def test_delete_only_while_recruiting(league, clock, new_user):
    admin, (a, b), code = league(2)
    assert admin.post("/leagues/delete").status_code == 200
    assert a.get("/leagues/mine").get_json()["in_league"] is False
    late = new_user("stu7777", "늦은학생")
    assert late.post("/leagues/join", json={"code": code}).status_code >= 400


def test_remove_student_mid_league_keeps_standings_fair(league, clock):
    admin, students, code = league(4)
    admin.post("/leagues/start", json={"first_date": "2026-10-26"})
    clock.set(2026, 10, 26, 1, 0)
    gone = students[3]
    gone_id = gone.get("/leagues/mine").get_json()["my_user_id"]
    r = admin.post(f"/admin/students/{gone_id}/remove")
    assert r.status_code == 200 and r.get_json()["league_status"] == "running"

    table = points(students[0])
    assert "학생3" not in table and len(table) == 3
    # 내보낸 학생은 바로 다른 리그에 들어갈 수 있다
    assert gone.get("/leagues/mine").get_json()["in_league"] is False
    # 상대를 잃은 학생은 이번 라운드가 쉬는 라운드가 된다
    assert sum(1 for s in students[:3] if current(s).get("bye")) == 1


def test_students_cannot_leave_running_league(league, clock):
    admin, (a, b), code = league(2)
    admin.post("/leagues/start", json={"first_date": "2026-10-26"})
    assert a.post("/leagues/leave").status_code == 409


def test_short_league_never_repeats_opponent(league, clock):
    admin, students, code = league(6, league_mode="short", end_date="2026-11-08")
    info = admin.post("/leagues/start", json={"first_date": "2026-10-26"}).get_json()
    assert info["rounds"] < 5 and info["end"] <= "2026-11-08"
    clock.set(2027, 1, 1, 0, 0)
    for s in students:
        hist = s.get("/matches/history").get_json()["history"]
        opps = [h["opponent"] for h in hist if not h.get("bye")]
        assert len(opps) == len(set(opps)) == info["rounds"], "6명(짝수)이면 모두 같은 수의 경기를 한다"
    assert students[0].get("/leagues/mine").get_json()["league"]["league_mode"] == "short"


def test_league_is_full_at_thirty_students(league, new_user):
    admin, students, code = league(30)
    late = new_user("stu9999", "늦은학생")
    r = late.post("/leagues/join", json={"code": code})
    assert r.status_code == 409 and "30명" in r.get_json()["error"], "31명째는 참가할 때 바로 막는다"
