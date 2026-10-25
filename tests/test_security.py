"""권한·정보 보호·이상한 입력 (SPEC 5. 보안·안전)"""
import pytest

from classleague.db import get_db

from conftest import PASSWORD, current, questions


def running_match(league, clock, n=2):
    admin, students, code = league(n)
    admin.post("/leagues/start", json={"first_date": "2026-10-26"})
    clock.set(2026, 10, 26, 1, 0)
    mid = current(students[0])["match_id"]
    for s in students[:2]:
        s.post(f"/matches/{mid}/my-questions", json={"action": "complete", "questions": questions()})
    return admin, students, mid


@pytest.mark.parametrize("method, url", [
    ("get", "/leagues/mine"), ("get", "/matches/current"), ("get", "/wrong-notes"),
    ("post", "/leagues"), ("post", "/leagues/join"), ("get", "/admin/progress"),
])
def test_login_required(app, method, url):
    r = getattr(app.test_client(), method)(url)
    assert r.status_code == 401


def test_password_is_hashed(app, new_user):
    new_user("stu0001", "민수")
    with app.app_context():
        h = get_db().execute("SELECT password_hash FROM user WHERE username='stu0001'").fetchone()[0]
    assert PASSWORD not in h and h.startswith("$2")


def test_login_locks_after_five_fails_even_for_unknown_id(app, new_user):
    new_user("stu0001", "민수")
    c = app.test_client()
    for who in ("stu0001", "nobody99"):
        codes = [c.post("/login", json={"username": who, "password": "wrong-pass"}).status_code for _ in range(5)]
        assert codes == [401, 401, 401, 401, 429]
    # 잠긴 동안은 맞는 비밀번호도 막는다
    assert c.post("/login", json={"username": "stu0001", "password": PASSWORD}).status_code == 429


def test_other_student_cannot_touch_my_match(league, clock):
    admin, (a, b, outsider), mid = running_match(league, clock, n=3)
    # 3명이면 한 명은 쉰다. 쉬는 학생은 다른 경기에 접근할 수 없다
    resting = next(s for s in (a, b, outsider) if current(s)["match_id"] != mid)
    assert resting.get(f"/matches/{mid}/my-questions").status_code in (403, 404)
    assert resting.get(f"/matches/{mid}/questions").status_code in (403, 404)
    assert resting.post(f"/matches/{mid}/submit", json={"answers": {}}).status_code in (403, 404)


def test_admin_cannot_see_running_answers(league, clock):
    admin, students, mid = running_match(league, clock)
    uid = students[0].get("/leagues/mine").get_json()["my_user_id"]
    body = admin.get(f"/admin/students/{uid}/questions").get_data(as_text=True)
    assert "x²=4" not in body, "진행 중인 경기의 문제·정답은 관리자에게도 보이지 않는다"
    assert admin.get(f"/matches/{mid}/questions").status_code in (403, 404)


def test_student_cannot_use_admin_api(league, clock):
    admin, (a, b), mid = running_match(league, clock)
    for url in ("/admin/progress", "/admin/accuracy", "/admin/reports"):
        assert a.get(url).status_code == 403
    assert a.post("/admin/students/1/remove").status_code == 403
    assert a.post("/leagues/delete").status_code in (403, 404)


def test_nickname_unique_in_league_ignoring_case_and_spaces(league, new_user):
    admin, (a, b), code = league(2)
    c = new_user("stu9999", " 학 생 0 ")
    r = c.post("/leagues/join", json={"code": code})
    assert r.status_code == 409 and r.get_json()["reason"] == "dup_nickname"
    assert c.post("/me/nickname", json={"nickname": "새이름"}).status_code == 200
    assert c.post("/leagues/join", json={"code": code}).status_code == 200


WEIRD_BODIES = [None, "not json", "[]", "123", '{"answers": [1,2]}', '{"questions": "x"}',
                '{"username": ["a"], "password": {"x": 1}}', '{"code": 123456}']


@pytest.mark.parametrize("raw", WEIRD_BODIES)
def test_weird_input_never_crashes(league, clock, raw):
    admin, (a, b), mid = running_match(league, clock)
    urls = ["/register", "/login", "/me/nickname", "/leagues/join", "/leagues/settings",
            f"/matches/{mid}/my-questions", f"/matches/{mid}/submit", "/questions/1/report",
            "/admin/reports/1", "/wrong-notes/known"]
    for url in urls:
        for c in (a, admin):
            r = c.post(url, data=raw, content_type="application/json")
            assert r.status_code < 500, (url, raw, r.get_json())
            assert "error" in r.get_json() or r.status_code < 300


def test_too_long_and_html_text(league, clock):
    admin, (a, b), mid = running_match(league, clock)
    a.post(f"/matches/{mid}/reopen")
    long_q = questions()
    long_q[0]["content"] = "가" * 1001
    r = a.post(f"/matches/{mid}/my-questions", json={"action": "draft", "questions": long_q})
    assert r.status_code == 400 and "1000자" in r.get_json()["error"]

    # HTML은 그대로 글자로 저장했다가 화면에서 글자로 보여 준다 (서버는 그대로 돌려줌, 화면이 textContent로 표시)
    html_q = questions()
    html_q[0]["content"] = "<img src=x onerror=alert(1)>"
    assert a.post(f"/matches/{mid}/my-questions", json={"action": "draft", "questions": html_q}).status_code == 200
