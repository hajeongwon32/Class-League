"""대진표와 경기 일정 계산 (SPEC 5. 리그 기간 방식·경기 일정). DB를 쓰지 않는 계산만 둔다."""

from datetime import datetime, timedelta
from itertools import pairwise

from classleague import clock
from classleague.clock import kst_deadline_utc


def make_round_robin(player_ids):
    """
    모두가 서로 한 번씩 붙는 대진표를 만든다 (라운드 로빈).
    돌려주는 값: [[(a, b), (c, d), ...], ...]  (주차별 경기 목록)
    사람이 홀수면 한 명은 그 주 부전승(상대가 None).
    """
    players = list(player_ids)
    if len(players) < 2:
        return []

    # 홀수면 가짜 선수(None)를 넣어 짝을 맞춘다. 이 선수와 만나면 부전승.
    if len(players) % 2 == 1:
        players.append(None)

    n = len(players)
    rounds = []
    # 표준 라운드 로빈: 맨 앞은 고정, 나머지를 회전시킨다
    arr = players[:]
    for _ in range(n - 1):
        pairs = []
        for i in range(n // 2):
            a = arr[i]
            b = arr[n - 1 - i]
            if a is None or b is None:
                # 부전승: 실제 선수를 player1로 두고 상대는 None
                real = a if a is not None else b
                if real is not None:
                    pairs.append((real, None))
            else:
                pairs.append((a, b))
        rounds.append(pairs)
        # 회전: 맨 앞(arr[0])은 고정, 나머지를 한 칸씩 돌린다
        arr = [arr[0]] + [arr[-1]] + arr[1:-1]
    return rounds


# ---------- 경기 일정 계산 (SPEC 5. 경기 일정) ----------
WEEKDAY_NAMES = ["월", "화", "수", "목", "금", "토", "일"]


# 오늘 바로 시작할 때, 1라운드 문제 만들기 마감까지 최소로 남아 있어야 하는 시간
TODAY_MIN_MAKE_HOURS = 3


FIRST_DATE_MAX_DAYS = 60  # 너무 먼 날은 못 고르게 (약 두 달)


# 관리자가 고를 수 있는 마감 시각 (문제 만들기·풀기 마감에 똑같이 쓴다)
DEADLINE_TIMES = ["18:00", "19:00", "20:00", "21:00", "22:00", "23:00", "23:59"]


def validate_match_days(raw):
    """경기 요일 검사. 맞으면 (정렬된 목록, None), 틀리면 (None, 안내 글)."""
    if not isinstance(raw, list) or not raw:
        return None, "경기 요일을 하나 이상 골라 주세요"
    if any(not isinstance(d, int) or isinstance(d, bool) or not 0 <= d <= 6 for d in raw):
        return None, "경기 요일 형식이 올바르지 않아요"
    days = sorted(set(raw))
    if len(days) > 3:
        return None, "경기 요일은 1주일에 3번까지 고를 수 있어요"
    # 경기 요일끼리 하루 이상 띄우기 (일요일 다음은 월요일이라 한 바퀴 돌려서도 본다)
    if len(days) > 1:
        gaps = [b - a for a, b in pairwise(days)] + [days[0] + 7 - days[-1]]
        if min(gaps) < 2:
            return None, "경기 요일끼리는 하루 이상 띄워 주세요 (예: 월·화는 안 돼요)"
    return days, None


def shortest_round_days(days):
    """경기 요일로 생기는 라운드 중 가장 짧은 라운드의 날 수 (요일 하나면 7일)."""
    if len(days) == 1:
        return 7
    return min([b - a for a, b in pairwise(days)] + [days[0] + 7 - days[-1]])


def validate_make_days(raw, days):
    """문제 만들기 기간 검사. 0 = 자동. 풀기 기간이 하루는 남아야 한다."""
    if raw is None:
        return 0, None
    if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
        return None, "문제 만들기 기간 형식이 올바르지 않아요"
    longest = shortest_round_days(days) - 1
    if raw > longest:
        return None, f"이 경기 요일이면 문제 만들기 기간은 {longest}일까지 고를 수 있어요 (풀기 기간이 하루는 있어야 해요)"
    return raw, None


SCOPE_MAX = 100        # 출제 범위 글자 수


END_DATE_MAX_DAYS = 365  # 종료 희망일은 1년 안


def clean_scope(raw):
    """출제 범위 글자 검사. 맞으면 (정리된 글자, None), 틀리면 (None, 안내 글)."""
    if not isinstance(raw, str):
        return None, "출제 범위를 적어 주세요 (제한하지 않으려면 '자유 출제')"
    text = " ".join(raw.split())  # 줄바꿈·여러 칸 띄어쓰기를 한 칸으로
    if not (1 <= len(text) <= SCOPE_MAX):
        return None, f"출제 범위는 1~{SCOPE_MAX}자로 적어 주세요 (제한하지 않으려면 '자유 출제')"
    return text, None


def rounds_until(first, days, make_days, deadline_time, end_date, max_rounds):
    """
    시험 대비 단기 리그: end_date(종료 희망일, 그날 마감 시각까지) 안에 완전히 끝나는 라운드 수.
    전체 라운드 수(max_rounds)보다 많아질 수는 없다 (같은 상대와 두 번 붙지 않게).
    """
    if end_date is None or first > end_date:
        return 0
    limit = datetime.fromisoformat(kst_deadline_utc(end_date, deadline_time))
    sched = build_schedule(first, days, max_rounds, make_days)
    n = 0
    for r in sched:
        if datetime.fromisoformat(kst_deadline_utc(r["last"], deadline_time)) <= limit:
            n += 1
        else:
            break
    return n


def round_count(n_players):
    """N명이면 짝수일 때 N-1라운드, 홀수일 때 N라운드."""
    if n_players < 2:
        return 0
    return n_players - 1 if n_players % 2 == 0 else n_players


def match_dates_from(first, days, count):
    """first부터 시작해 경기 요일인 날짜를 count개 모은다."""
    out, d = [], first
    while len(out) < count:
        if d.weekday() in days:
            out.append(d)
        d += timedelta(days=1)
    return out


def build_schedule(first, days, n_rounds, make_days=0):
    """
    라운드별 날짜 (모두 한국 날짜).
    start: 라운드 시작일(0시), make_last: 만들기 마지막 날, last: 라운드 마지막 날 (= 다음 경기 요일 전날)
    make_days가 0이면 라운드 앞쪽 절반(버림, 최소 1일)이 만들기, 아니면 그 날 수만큼.
    """
    if n_rounds <= 0:
        return []
    # 마지막 라운드 끝을 알려고 하나 더. 첫날이 경기 요일이 아니면(오늘 바로 시작) 그날이 1라운드 시작
    starts = match_dates_from(first, days, n_rounds + 1)
    if first.weekday() not in days:
        starts = [first] + starts[:n_rounds]
    rounds = []
    for i in range(n_rounds):
        start, nxt = starts[i], starts[i + 1]
        length = (nxt - start).days
        make = make_days if make_days > 0 else max(1, length // 2)
        make = min(make, length - 1)  # 풀기 기간이 하루는 남게
        rounds.append({"round": i + 1, "start": start,
                       "make_last": start + timedelta(days=make - 1),
                       "last": nxt - timedelta(days=1)})
    return rounds


def can_start_today(days, make_days=0, deadline_time="23:59"):
    """
    오늘 바로 시작할 수 있는지 (경기 요일이 아니어도 된다).
    1라운드에 만들기·풀기가 하루씩은 있어야 하고, 만들기 마감까지 몇 시간은 남아야 한다.
    """
    today = clock.today_kst()
    rnd = build_schedule(today, days, 1, make_days)[0]
    if (rnd["last"] - rnd["start"]).days + 1 < 2:
        return False
    make_end = datetime.fromisoformat(kst_deadline_utc(rnd["make_last"], deadline_time))
    return make_end - clock.now_utc() >= timedelta(hours=TODAY_MIN_MAKE_HOURS)


def first_date_choices(days, make_days=0, deadline_time="23:59"):
    """첫 경기로 고를 수 있는 날짜들. 오늘(가능하면) + 내일 이후 경기 요일 8개. 첫 번째가 기본값."""
    today = clock.today_kst()
    limit = today + timedelta(days=FIRST_DATE_MAX_DAYS)
    later = [d for d in match_dates_from(today + timedelta(days=1), days, 8) if d <= limit]
    return ([today] if can_start_today(days, make_days, deadline_time) else []) + later
