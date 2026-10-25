"""한 라운드 전체 흐름: 만들기 → 풀기 → 채점 → 순위 (F7~F14, F18)"""
from conftest import current, questions


def start(admin, clock):
    r = admin.post("/leagues/start", json={"first_date": "2026-10-26"})
    assert r.status_code == 200, r.get_json()
    clock.set(2026, 10, 26, 1, 0)  # 1라운드 월요일 10:00 KST (만들기 마감 22:00)
    return r.get_json()


def make_both(a, b, mid):
    for s in (a, b):
        r = s.post(f"/matches/{mid}/my-questions", json={"action": "complete", "questions": questions()})
        assert r.status_code == 200, r.get_json()


def test_full_round_grades_and_updates_standings(league, clock):
    admin, (a, b), _ = league(2)
    info = start(admin, clock)
    assert info["rounds"] == 1

    mid = current(a)["match_id"]
    assert current(b)["match_id"] == mid
    make_both(a, b, mid)

    # 만들기 마감 전에는 풀 수 없다
    assert a.get(f"/matches/{mid}/questions").status_code == 409

    clock.set(2026, 10, 27, 1, 0)  # 만들기 마감 뒤
    qs = a.get(f"/matches/{mid}/questions").get_json()["questions"]
    for q in qs:
        assert "answer" not in q and "explanation" not in q, "제출 전에는 정답·해설을 보내면 안 된다"

    # a: 둘 다 맞힘 (주관식은 띄어쓰기 무시) / b: 하나만 맞힘
    r = a.post(f"/matches/{mid}/submit", json={"answers": {str(qs[0]["id"]): 1, str(qs[1]["id"]): " 2 "}})
    assert r.get_json()["score"] == 2
    assert a.post(f"/matches/{mid}/submit", json={"answers": {}}).status_code == 409, "두 번 제출할 수 없다"

    qs_b = b.get(f"/matches/{mid}/questions").get_json()["questions"]
    r = b.post(f"/matches/{mid}/submit", json={"answers": {str(qs_b[0]["id"]): 0}})
    assert r.get_json()["score"] == 0, "빈 답은 오답"
    assert r.get_json()["results"][0]["correct_answer"] == "1", "제출하면 정답을 보여 준다"

    table = {row["nickname"]: row for row in a.get("/leagues/mine").get_json()["standings"]}
    assert table["학생0"]["win"] == 1 and table["학생0"]["points"] == 3
    assert table["학생1"]["lose"] == 1 and table["학생1"]["points"] == 0
    assert table["학생0"]["goal_diff"] == 2

    # 틀린 문제는 오답 노트로
    assert b.get("/wrong-notes/count").get_json()["active"] == 2
    item = b.get("/wrong-notes").get_json()["items"][0]
    r = b.post("/wrong-notes/known", json={"key": item["key"], "source": item["source"], "known": True})
    assert r.status_code == 200, r.get_json()
    assert b.get("/wrong-notes/count").get_json()["active"] == 1


def test_draft_is_not_complete_and_forfeits_at_deadline(league, clock):
    admin, (a, b), _ = league(2)
    start(admin, clock)
    mid = current(a)["match_id"]

    # 완성 조건이 안 맞으면 [완성]은 거절, [임시 저장]은 된다
    r = a.post(f"/matches/{mid}/my-questions", json={"action": "complete", "questions": questions()[:1]})
    assert r.status_code == 400
    r = b.post(f"/matches/{mid}/my-questions", json={"action": "draft", "questions": questions()})
    assert r.status_code == 200 and r.get_json()["my_state"] == "draft"
    a.post(f"/matches/{mid}/my-questions", json={"action": "complete", "questions": questions()})

    clock.set(2026, 10, 27, 1, 0)
    # 만들기 마감이 지나면 잠긴다
    assert b.post(f"/matches/{mid}/my-questions", json={"action": "complete", "questions": questions()}).status_code == 409
    table = {row["nickname"]: row for row in a.get("/leagues/mine").get_json()["standings"]}
    assert table["학생0"]["points"] == 3, "임시 저장만 한 상대는 몰수패"
    assert table["학생1"]["points"] == 0
    assert table["학생0"]["goal_diff"] == 0, "몰수 경기는 득실차에 넣지 않는다"


def test_reopen_before_deadline(league, clock):
    admin, (a, b), _ = league(2)
    start(admin, clock)
    mid = current(a)["match_id"]
    a.post(f"/matches/{mid}/my-questions", json={"action": "complete", "questions": questions()})
    # 완성 뒤에는 바로 덮어쓸 수 없고 [다시 고치기]를 거쳐야 한다
    assert a.post(f"/matches/{mid}/my-questions", json={"action": "draft", "questions": questions()}).status_code == 409
    assert a.post(f"/matches/{mid}/reopen").status_code == 200
    assert a.post(f"/matches/{mid}/my-questions", json={"action": "draft", "questions": questions()}).status_code == 200


def test_odd_league_runs_to_the_end_without_anyone_playing(league, clock):
    admin, students, _ = league(3)
    info = start(admin, clock)
    assert info["rounds"] == 3
    clock.set(2027, 1, 1, 0, 0)  # 아무도 아무것도 안 하고 리그가 끝남

    mine = students[0].get("/leagues/mine").get_json()
    assert mine["league"]["status"] == "finished"
    assert all(row["points"] == 0 and row["played"] == 2 for row in mine["standings"]), "둘 다 안 하면 둘 다 패"
    assert mine["final"]["finalized"] is True
