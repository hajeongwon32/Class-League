"""권한·정보 보호·이상한 입력 (SPEC 5. 보안·안전)"""
import pytest

from classleague.db import get_db

from conftest import PASSWORD, current, league_settings, questions


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


# ---------- 브라우저 쪽 보안 설정 (classleague/security.py) ----------
def test_security_headers_on_pages_and_api(app):
    c = app.test_client()
    for url in ("/", "/me", "/static/js/01-core.js"):
        with c.get(url) as r:  # 파일 응답은 닫아야 파일도 닫힌다
            h = r.headers
        csp = h["Content-Security-Policy"]
        assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
        assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
        assert h["X-Frame-Options"] == "DENY"
        assert h["X-Content-Type-Options"] == "nosniff"
        assert h["Referrer-Policy"] == "same-origin"
    assert c.get("/me").headers["Cache-Control"] == "no-store", "API 응답은 기기에 남기지 않는다"


def test_html_has_no_inline_script_or_style():
    """보안 정책(CSP)이 막지 않도록 화면 파일에 인라인 스크립트·style 속성을 두지 않는다."""
    import os
    import re
    import glob
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    paths = glob.glob(os.path.join(root, "templates", "**", "*.html"), recursive=True)
    paths.append(os.path.join(root, "static", "offline.html"))
    assert len(paths) > 2, "화면 조각(templates/partials)도 검사해야 한다"
    for path in paths:
        with open(path, encoding="utf-8") as f:
            html = f.read()
        assert not re.search(r"\sstyle=\"", html), path
        assert not re.search(r"\son[a-z]+=\"", html), path
        assert not re.search(r"<script(?![^>]*\bsrc=)", html), path
        assert "<style" not in html, path


def test_page_loads_every_file_it_needs(app):
    """화면(HTML·CSS·JS)을 여러 파일로 나눴으니, 첫 화면과 서비스 워커가 부르는 파일이 모두 있어야 한다."""
    import re
    c = app.test_client()
    page = c.get("/").get_data(as_text=True)
    refs = re.findall(r'(?:href|src)="(/static/[^"]+)"', page)
    assert any("/static/css/" in r for r in refs) and any("/static/js/" in r for r in refs)
    with c.get("/sw.js") as r:
        sw = r.get_data(as_text=True)
    shell = re.findall(r'"(/static/[^"]+)"', sw)
    with c.get("/static/offline.html") as r:
        offline = r.get_data(as_text=True)
    refs += shell + re.findall(r'(?:href|src)="(/static/[^"]+)"', offline)
    for url in sorted(set(refs)):
        with c.get(url) as r:
            assert r.status_code == 200, url
    # 서비스 워커는 첫 화면이 부르는 CSS·JS를 모두 저장해 둬야 오프라인 안내가 제대로 보인다
    for url in refs:
        if url.endswith((".css", ".js")) and "offline" not in url:
            assert url in shell, f"서비스 워커 목록에 없음: {url}"


def _cookies(response):
    return response.headers.getlist("Set-Cookie")


def test_login_cookies_are_samesite_httponly_and_secure_on_https(app, new_user):
    new_user("stu0001", "민수")
    body = {"username": "stu0001", "password": PASSWORD}

    https = app.test_client()
    cookies = _cookies(https.post("/login", json=body, base_url="https://localhost"))
    assert cookies, "로그인하면 세션·로그인 유지 쿠키가 생긴다"
    for ck in cookies:
        assert "SameSite=Lax" in ck and "HttpOnly" in ck and "Secure" in ck, ck
    resp = https.get("/me", base_url="https://localhost")
    assert resp.get_json()["logged_in"] is True
    assert "Strict-Transport-Security" in resp.headers

    # 내 컴퓨터에서 http로 켰을 때는 Secure를 붙이지 않아야 로그인이 된다
    http = app.test_client()
    for ck in _cookies(http.post("/login", json=body)):
        assert "Secure" not in ck, ck
    assert http.get("/me").get_json()["logged_in"] is True


def test_https_behind_proxy_also_gets_secure_cookie(app, new_user):
    new_user("stu0001", "민수")
    r = app.test_client().post("/login", json={"username": "stu0001", "password": PASSWORD},
                               headers={"X-Forwarded-Proto": "https"})
    assert all("Secure" in ck for ck in _cookies(r))


def test_too_big_request_is_refused_kindly(app):
    r = app.test_client().post("/register", data="x" * (3 * 1024 * 1024), content_type="application/json")
    assert r.status_code == 413 and "error" in r.get_json()


def test_prize_rank_is_limited_to_thirty(new_user):
    """아주 큰 등수(예: 1~10억등)를 보내도 서버가 그만큼 계산하지 않고 바로 거절한다."""
    admin = new_user("teacher1", "선생님")
    huge = league_settings(rewards=[{"from": 1, "to": 10**9, "text": "상품"}])
    r = admin.post("/leagues", json=huge)
    assert r.status_code == 400 and "30등" in r.get_json()["error"]
    ok = league_settings(rewards=[{"from": 1, "to": 30, "text": "참가상"}])
    assert admin.post("/leagues", json=ok).status_code == 201
