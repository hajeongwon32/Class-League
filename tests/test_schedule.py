"""대진표·일정 계산 (SPEC 5. 리그 기간 방식·경기 일정)"""
from datetime import date
from itertools import combinations

import pytest

import app as A


@pytest.mark.parametrize("n", [2, 3, 4, 5, 8, 9, 30])
def test_round_robin_everyone_meets_everyone_once(n):
    players = list(range(1, n + 1))
    rounds = A.make_round_robin(players)

    assert len(rounds) == A.round_count(n) == (n - 1 if n % 2 == 0 else n)
    met = []
    for pairs in rounds:
        in_round = [p for pair in pairs for p in pair if p is not None]
        assert len(in_round) == len(set(in_round)), "한 라운드에 두 번 나오는 학생이 있으면 안 된다"
        assert set(in_round) == set(players)
        met += [frozenset(pair) for pair in pairs if None not in pair]
    assert len(met) == len(set(met)), "같은 상대와 두 번 붙으면 안 된다"
    assert set(met) == {frozenset(p) for p in combinations(players, 2)}


def test_odd_league_each_player_rests_once():
    rounds = A.make_round_robin([1, 2, 3, 4, 5])
    rests = [pair[0] for pairs in rounds for pair in pairs if pair[1] is None]
    assert sorted(rests) == [1, 2, 3, 4, 5]


def test_schedule_round_ends_day_before_next_match_day():
    # 월·목 경기: 1라운드는 월~수, 2라운드는 목~일
    sch = A.build_schedule(date(2026, 10, 26), [0, 3], 3)
    assert [(s["start"], s["last"]) for s in sch] == [
        (date(2026, 10, 26), date(2026, 10, 28)),
        (date(2026, 10, 29), date(2026, 11, 1)),
        (date(2026, 11, 2), date(2026, 11, 4)),
    ]
    for s in sch:
        assert s["start"] <= s["make_last"] < s["last"], "풀기 기간이 최소 하루는 남아야 한다"


def test_short_league_stops_before_end_date():
    first, days = date(2026, 10, 26), [0, 3]
    n = A.rounds_until(first, days, 0, "22:00", date(2026, 11, 5), max_rounds=7)
    sch = A.build_schedule(first, days, n)
    assert n == 3
    assert sch[-1]["last"] <= date(2026, 11, 5)
    # 하루만 늦춰도 더 들어가지 않는 라운드는 넣지 않는다
    assert A.rounds_until(first, days, 0, "22:00", date(2026, 11, 7), max_rounds=7) == 3


def test_deadline_is_kst_stored_as_utc():
    assert A.kst_deadline_utc(date(2026, 10, 26), "22:00") == "2026-10-26T13:00:00+00:00"
    assert A.kst_midnight_utc(date(2026, 10, 26)) == "2026-10-25T15:00:00+00:00"


@pytest.mark.parametrize("days, ok", [([0, 3], True), ([0, 1], False), ([], False), ([0, 2, 4, 6], False), ([7], False)])
def test_match_day_rules(days, ok):
    _, err = A.validate_match_days(days)
    assert (err is None) == ok
