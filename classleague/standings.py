"""순위표 계산 (SPEC 5. 순위). 전체 리그와 시험 대비 단기 리그의 기준이 다르다."""

def compute_standings(db, league_id):
    """
    순위표 계산 (F11).
    - 전체 리그: 총 승점 → 총 득실차 → 맞힌 문제 수 → 닉네임
    - 시험 대비 단기 리그: 경기당 평균 승점 → 경기당 평균 득실차 → 정답률 → 닉네임
    몰수 경기는 경기 수·승패에는 포함하지만 점수와 득실차는 0:0으로 본다.
    """
    league = db.execute(
        "SELECT league_mode FROM league WHERE id = ?", (league_id,)
    ).fetchone()
    mode = league["league_mode"] if league and league["league_mode"] in ("full", "short") else "full"
    members = db.execute(
        """
        SELECT u.id, u.nickname
        FROM membership m JOIN user u ON u.id = m.user_id
        WHERE m.league_id = ? AND m.status != 'removed'
        """,
        (league_id,),
    ).fetchall()

    stats = {
        m["id"]: {
            "user_id": m["id"], "nickname": m["nickname"],
            "played": 0, "win": 0, "draw": 0, "lose": 0,
            "points": 0, "scored": 0, "against": 0, "goal_diff": 0,
            "correct": 0, "attempted": 0, "accuracy": 0.0,
            "points_per_game": 0.0, "goal_diff_per_game": 0.0,
        }
        for m in members
    }

    matches = db.execute(
        "SELECT player1_id, player2_id, result, p1_score, p2_score, forfeit "
        "FROM match WHERE league_id = ? AND result IS NOT NULL",
        (league_id,),
    ).fetchall()
    for mt in matches:
        p1, p2 = mt["player1_id"], mt["player2_id"]
        if p2 is None:
            continue  # 쉬는 라운드는 경기 수·승점에 영향 없음
        if p1 not in stats or p2 not in stats:
            continue  # 내보낸 학생과의 경기는 양쪽 모두 순위에서 뺀다 (기록 지우기 방식)
        s1 = 0 if mt["forfeit"] else (mt["p1_score"] or 0)
        s2 = 0 if mt["forfeit"] else (mt["p2_score"] or 0)
        if p1 in stats:
            stats[p1]["played"] += 1
            stats[p1]["scored"] += s1
            stats[p1]["against"] += s2
        if p2 in stats:
            stats[p2]["played"] += 1
            stats[p2]["scored"] += s2
            stats[p2]["against"] += s1
        if mt["result"] == "p1":
            if p1 in stats:
                stats[p1]["win"] += 1; stats[p1]["points"] += 3
            if p2 in stats:
                stats[p2]["lose"] += 1
        elif mt["result"] == "p2":
            if p2 in stats:
                stats[p2]["win"] += 1; stats[p2]["points"] += 3
            if p1 in stats:
                stats[p1]["lose"] += 1
        elif mt["result"] == "draw":
            if p1 in stats:
                stats[p1]["draw"] += 1; stats[p1]["points"] += 1
            if p2 in stats:
                stats[p2]["draw"] += 1; stats[p2]["points"] += 1
        elif mt["result"] == "both_lose":
            for p in (p1, p2):
                if p in stats:
                    stats[p]["lose"] += 1

    # 정답률: 정상 경기에서 실제 제출한 문제만 센다. 몰수 경기는 제외한다.
    answers = db.execute(
        "SELECT s.solver_id, COUNT(*) AS attempted, SUM(s.correct) AS correct "
        "FROM submission s JOIN match mt ON mt.id = s.match_id JOIN question q ON q.id = s.question_id "
        "WHERE mt.league_id = ? AND mt.result IS NOT NULL AND mt.forfeit = 0 AND q.void = 0 "
        "AND NOT EXISTS (SELECT 1 FROM membership r WHERE r.league_id = mt.league_id "
        "AND r.status = 'removed' AND r.user_id IN (mt.player1_id, mt.player2_id)) "
        "GROUP BY s.solver_id",
        (league_id,),
    ).fetchall()
    for row in answers:
        uid = row["solver_id"]
        if uid in stats:
            stats[uid]["attempted"] = row["attempted"] or 0
            stats[uid]["correct"] = row["correct"] or 0

    for row in stats.values():
        row["goal_diff"] = row["scored"] - row["against"]
        if row["played"]:
            row["points_per_game"] = row["points"] / row["played"]
            row["goal_diff_per_game"] = row["goal_diff"] / row["played"]
        if row["attempted"]:
            row["accuracy"] = row["correct"] / row["attempted"]

    if mode == "short":
        key = lambda r: (-r["points_per_game"], -r["goal_diff_per_game"],
                         -r["accuracy"], r["nickname"])
    else:
        key = lambda r: (-r["points"], -r["goal_diff"], -r["scored"], r["nickname"])
    table = sorted(stats.values(), key=key)
    for i, row in enumerate(table, start=1):
        row["rank"] = i
    return table


def total_weeks(db, league_id):
    """이 리그의 전체 주차 수 (대진표에서 가장 큰 week)."""
    row = db.execute(
        "SELECT MAX(week) AS w FROM match WHERE league_id = ?", (league_id,)
    ).fetchone()
    return row["w"] or 0
