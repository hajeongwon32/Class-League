"""실시간 갱신 (SSE): 리그에 변화가 생기면 열어 둔 화면에 바로 알린다.

- 상대가 [완성]·제출하거나, 마감이 지나 몰수·다음 라운드가 되거나, 신고가 들어오면 알린다.
- 이 스트림에는 리그의 '버전'(짧은 값)만 담고 내용은 담지 않는다.
  알림을 받은 화면은 기존 API로 다시 받아 오므로, 권한 검사도 기존 API가 그대로 한다.
- 보는 사람이 있는 동안에는 마감이 지나는 즉시 정산한다 (engine.refresh_league).
"""

import hashlib
import sqlite3
import time

from flask import Blueprint, Response
from flask_login import current_user, login_required

from classleague import clock, db as db_module
from classleague.engine import refresh_league
from classleague.league_state import active_league_id

bp = Blueprint("live", __name__)

POLL_SECONDS = 2        # 리그 상태를 다시 보는 간격
HEARTBEAT_SECONDS = 15  # 아무 일이 없어도 연결이 끊기지 않게 보내는 신호 간격
STREAM_SECONDS = 300    # 연결 하나는 5분까지. 끊기면 브라우저(EventSource)가 알아서 다시 연결한다


def league_version(db, league_id):
    """리그 화면에 보이는 것이 바뀌면 달라지는 짧은 값."""
    now = clock.now_iso()
    queries = [
        ("SELECT status, admin_closed, deleted FROM league WHERE id = ?", (league_id,)),
        ("SELECT id, player1_id, player2_id, p1_state, p2_state, p1_done, p2_done, "
         "p1_score, p2_score, result, forfeit FROM match WHERE league_id = ? ORDER BY id", (league_id,)),
        # 시간이 지나 단계가 바뀐 것(라운드 시작·만들기 마감·풀기 마감)도 변화로 본다
        ("SELECT SUM(round_start <= ?), SUM(make_deadline <= ?), SUM(solve_deadline <= ?) "
         "FROM match WHERE league_id = ?", (now, now, now, league_id)),
        ("SELECT m.user_id, m.status, u.nickname FROM membership m JOIN user u ON u.id = m.user_id "
         "WHERE m.league_id = ? ORDER BY m.user_id", (league_id,)),
        ("SELECT id, status FROM report WHERE league_id = ? ORDER BY id", (league_id,)),
        ("SELECT COUNT(*) FROM submission s JOIN match m ON m.id = s.match_id WHERE m.league_id = ?", (league_id,)),
        ("SELECT round, subject, scope FROM round_scope WHERE league_id = ? ORDER BY round, subject", (league_id,)),
    ]
    rows = [[tuple(r) for r in db.execute(sql, args).fetchall()] for sql, args in queries]
    return hashlib.sha1(repr(rows).encode("utf-8")).hexdigest()[:12]


def check_league(user_id):
    """밀린 마감을 정산한 뒤 지금 버전을 돌려준다. 요청마다 쓰는 DB 연결과 따로, 볼 때마다 새로 연결한다."""
    db = sqlite3.connect(db_module.DB_PATH)
    db.row_factory = sqlite3.Row
    try:
        league_id = active_league_id(db, user_id)
        if league_id is None:
            return "none"
        refresh_league(db, league_id)
        return league_version(db, league_id)
    finally:
        db.close()


@bp.get("/leagues/events")
@login_required
def league_events():
    user_id = current_user.id

    def stream():
        yield "retry: 3000\n\n"  # 끊기면 3초 뒤 다시 연결
        last = check_league(user_id)
        yield f"event: ready\ndata: {last}\n\n"
        started = beat = time.monotonic()
        while time.monotonic() - started < STREAM_SECONDS:
            time.sleep(POLL_SECONDS)
            version = check_league(user_id)
            if version != last:
                last = version
                beat = time.monotonic()
                yield f"event: change\ndata: {version}\n\n"
            elif time.monotonic() - beat >= HEARTBEAT_SECONDS:
                beat = time.monotonic()
                yield ": keep-alive\n\n"

    return Response(
        stream(),  # 요청 정보 없이 돈다: 사용자 번호만 미리 받아 두고 DB도 따로 연결한다
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},  # 중간 프록시가 모아 두지 않게
    )
