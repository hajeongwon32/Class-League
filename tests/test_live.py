"""실시간 갱신 (SSE, classleague/routes/live.py)"""
import re

import pytest

from classleague.routes import live
from conftest import current, questions


OPEN = []  # 시험이 끝나면 열어 둔 스트림을 닫는다


@pytest.fixture(autouse=True)
def fast_stream(monkeypatch):
    # 시험에서는 기다리지 않고 바로 다시 보며, 변화가 없으면 1초 안에 연결을 끝낸다
    monkeypatch.setattr(live, "POLL_SECONDS", 0.01)
    monkeypatch.setattr(live, "HEARTBEAT_SECONDS", 60)
    monkeypatch.setattr(live, "STREAM_SECONDS", 1)
    yield
    while OPEN:
        OPEN.pop().close()


def open_stream(client):
    r = client.get("/leagues/events", buffered=False)
    OPEN.append(r)
    assert r.status_code == 200 and r.mimetype == "text/event-stream"
    chunks = iter(r.response)
    assert next(chunks).decode() == "retry: 3000\n\n"
    ready = next(chunks).decode()
    assert ready.startswith("event: ready\n")
    return chunks, ready


def next_event(chunks):
    for chunk in chunks:
        text = chunk.decode()
        if text.startswith("event:"):
            return text
    return None  # 변화 없이 연결이 끝남


def start(league, clock, n=2):
    admin, students, _ = league(n)
    admin.post("/leagues/start", json={"first_date": "2026-10-26"})
    clock.set(2026, 10, 26, 1, 0)
    return admin, students


def test_login_required(app):
    assert app.test_client().get("/leagues/events").status_code == 401


def test_opponent_completing_questions_sends_change(league, clock):
    admin, (a, b) = start(league, clock)
    chunks, ready = open_stream(a)
    mid = current(b)["match_id"]
    b.post(f"/matches/{mid}/my-questions", json={"action": "complete", "questions": questions()})

    event = next_event(chunks)
    assert event and event.startswith("event: change\n")
    # 알림에는 버전 값만 있고 리그 내용(문제·정답·닉네임)은 없다
    assert re.fullmatch(r"event: change\ndata: [0-9a-f]{12}\n\n", event)


def test_teacher_sees_progress_change_live(league, clock):
    admin, (a, b) = start(league, clock)
    chunks, _ = open_stream(admin)
    a.post(f"/matches/{current(a)['match_id']}/my-questions", json={"action": "complete", "questions": questions()})
    assert next_event(chunks).startswith("event: change\n")


def test_deadline_passing_is_settled_by_the_stream(league, clock):
    admin, (a, b) = start(league, clock)
    mid = current(a)["match_id"]
    a.post(f"/matches/{mid}/my-questions", json={"action": "complete", "questions": questions()})
    chunks, _ = open_stream(admin)

    clock.set(2026, 10, 27, 1, 0)  # 만들기 마감이 지남 (b는 [완성] 안 함)
    assert next_event(chunks).startswith("event: change\n")

    # 아무도 리그 화면을 다시 열지 않았는데, 스트림이 정산해서 이미 몰수 결과가 DB에 있다
    import sqlite3
    from contextlib import closing
    from classleague import db as db_module
    with closing(sqlite3.connect(db_module.DB_PATH)) as conn:
        row = conn.execute("SELECT result, forfeit, forfeit_stage FROM match WHERE id = ?", (mid,)).fetchone()
    assert row == ("p1", 1, "make")


def test_no_change_means_no_event(league, clock):
    admin, (a, b) = start(league, clock)
    chunks, _ = open_stream(a)
    assert next_event(chunks) is None  # 연결 시간이 끝날 때까지 알림 없음


def test_works_without_a_league(new_user):
    c = new_user("stu0001", "민수")
    chunks, ready = open_stream(c)
    assert ready == "event: ready\ndata: none\n\n"

