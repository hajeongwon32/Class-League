"""
시험용 공통 준비.
- 시험마다 빈 DB를 새로 만든다 (진짜 app.db는 건드리지 않는다).
- clock으로 '지금 시각'을 바꿔 마감·라운드 진행을 기다리지 않고 확인한다.
"""
import os
import sys
import tempfile
from datetime import datetime, timezone

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["DATABASE_PATH"] = os.path.join(tempfile.mkdtemp(), "import.db")
os.environ.setdefault("SECRET_KEY", "test-secret")

import app as app_module  # noqa: E402
from classleague import clock as clock_module, db as db_module  # noqa: E402
from classleague.routes.auth import bcrypt  # noqa: E402

bcrypt._log_rounds = 4  # 시험에서는 해시를 가볍게 (진짜 서버는 기본값 12)

PASSWORD = "password123"
# 2026-10-25(일) 12:00 KST. 다음 날(월)이 첫 경기 요일이 되도록 고른 시각
START = datetime(2026, 10, 25, 3, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self, now):
        self.now = now

    def set(self, *args):
        self.now = datetime(*args, tzinfo=timezone.utc)


@pytest.fixture
def clock(monkeypatch):
    c = Clock(START)
    # 모든 코드가 clock.now_utc() 하나로 '지금'을 정하므로 여기만 바꾸면 된다 (today_kst도 따라온다)
    monkeypatch.setattr(clock_module, "now_utc", lambda: c.now)
    return c


@pytest.fixture
def app(tmp_path, monkeypatch, clock):
    monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "test.db"))
    db_module.init_db()
    app_module.app.config["TESTING"] = True
    return app_module.app


@pytest.fixture
def new_user(app):
    """가입하고 로그인된 브라우저(test client)를 돌려준다."""
    def make(username, nickname):
        c = app.test_client()
        r = c.post("/register", json={"username": username, "password": PASSWORD, "nickname": nickname})
        assert r.status_code == 201, r.get_json()
        return c
    return make


SUBJECTS = [{"name": "수학", "count": 2, "scope": "이차방정식"}]


def league_settings(**over):
    s = {"name": "2반 리그", "subjects": SUBJECTS, "match_days": [0, 3],  # 월·목
         "deadline_time": "22:00", "make_days": 0, "league_mode": "full",
         "rewards": [{"from": 1, "to": 1, "text": "치킨"}]}
    s.update(over)
    return s


def questions(mc_answer=1, sa_answer="2"):
    return [
        {"subject": "수학", "qtype": "mc", "content": "x²=4의 양의 근은?",
         "choices": ["1", "2", "3"], "answer": mc_answer, "explanation": "x=±2"},
        {"subject": "수학", "qtype": "sa", "content": "x²-1=0의 근의 개수",
         "answer": sa_answer, "explanation": "x=±1"},
    ]


@pytest.fixture
def league(new_user):
    """관리자 1명 + 학생 n명이 들어온 모집 중 리그. (admin, [students], code)"""
    def make(n=2, **over):
        admin = new_user("teacher1", "선생님")
        r = admin.post("/leagues", json=league_settings(**over))
        assert r.status_code == 201, r.get_json()
        code = r.get_json()["code"]
        students = []
        for i in range(n):
            s = new_user(f"stu{i:04d}", f"학생{i}")
            assert s.post("/leagues/join", json={"code": code}).status_code == 200
            students.append(s)
        return admin, students, code
    return make


def current(client):
    return client.get("/matches/current").get_json()
