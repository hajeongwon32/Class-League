"""
혼자 체험해 보기: 가상 친구 3명과 체험 리그 한 판.

- 체험 리그는 league.demo_owner_id(체험하는 사람)가 있는 리그다. 코드로 들어올 수 없고 지난 리그에도 남지 않는다.
- 가상 친구(user.demo_kind='bot')는 자기 경기 문제를 미리 만들어 두고, 풀기 기간이 되면 알아서 풀어 제출한다.
- [다음 단계로]는 체험 리그의 시각만 앞당겨 다음 마감이 바로 지나게 한다. 진짜 리그는 절대 건드리지 않는다.
"""

import json
import secrets
from datetime import timedelta

from classleague import clock
from classleague.clock import parse_utc
from classleague.db import lock_db
from classleague.engine import finalize_match_if_ready, grade_one, report_deadline
from classleague.league_state import gen_league_code, same_nickname
from classleague.schedule import make_round_robin

BOT_NAMES = ["민수", "지아", "하준", "서연", "도윤"]
DEMO_SUBJECTS = [{"name": "수학", "count": 2, "scope": "이차방정식"}, {"name": "영어", "count": 1, "scope": "Lesson 3"}]
DEMO_REWARDS = [{"from": 1, "to": 1, "kind": "reward", "text": "우승 메달"},
                {"from": 2, "to": 3, "kind": "reward", "text": "아이스크림"}]
ROUND_DAYS = 2  # 체험 리그 한 라운드: 만들기 1일 + 풀기 1일 (앞당기기 전 기준)

# 가상 친구가 내는 문제: (유형, 내용, 보기, 정답, 해설). 객관식 정답은 보기 번호(0부터)
MATH_BANK = [
    ("mc", "x² − 5x + 6 = 0의 두 근의 합은?", ["2", "3", "5", "6"], 2, "근과 계수의 관계: 두 근의 합 = 5"),
    ("sa", "x² = 9의 양의 근을 쓰세요.", None, "3", "x = ±3 중 양수는 3"),
    ("mc", "이차방정식 x² − 4 = 0의 근은?", ["x = 2", "x = ±2", "x = 4", "x = ±4"], 1, "x² = 4 → x = ±2"),
    ("sa", "x² + 2x + 1 = 0의 근을 쓰세요.", None, "-1", "(x + 1)² = 0 → x = −1 (중근)"),
    ("mc", "x² − 7x + 12 = 0의 근이 아닌 것은?", ["3", "4", "7"], 2, "(x − 3)(x − 4) = 0 → 3, 4"),
    ("sa", "x² = 16의 음의 근을 쓰세요.", None, "-4", "x = ±4 중 음수는 −4"),
    ("mc", "x² + 5x + 6 = 0의 두 근의 곱은?", ["5", "6", "−5", "−6"], 1, "근과 계수의 관계: 두 근의 곱 = 6"),
    ("sa", "x² − 2x = 0의 0이 아닌 근을 쓰세요.", None, "2", "x(x − 2) = 0 → x = 0, 2"),
    ("mc", "(x − 1)² = 0의 근은?", ["x = 1 (중근)", "x = −1", "x = ±1"], 0, "완전제곱식 = 0 → 중근 x = 1"),
]
ENGLISH_BANK = [
    ("sa", "‘도서관’을 영어로 쓰세요.", None, "library", "library: 도서관"),
    ("mc", "Lesson 3: ‘borrow’의 뜻은?", ["빌려주다", "빌리다", "돌려주다"], 1, "borrow = 빌리다, lend = 빌려주다"),
    ("mc", "Lesson 3: ‘actually’와 뜻이 가장 가까운 것은?", ["really", "never", "maybe"], 0, "actually = 사실은, 실제로"),
    ("sa", "‘사과’를 영어로 쓰세요.", None, "apple", "p를 두 번 써요: apple"),
    ("mc", "‘library’의 복수형은?", ["librarys", "libraries", "libraryes"], 1, "자음 + y → ies"),
]


def is_demo_league(db, league_id):
    row = db.execute("SELECT demo_owner_id FROM league WHERE id = ?", (league_id,)).fetchone()
    return bool(row and row["demo_owner_id"])


def _new_bot(db, nickname, password_hash):
    cur = db.execute(
        "INSERT INTO user (username, password_hash, nickname, created_at, demo_kind) VALUES (?, ?, ?, ?, 'bot')",
        ("bot" + secrets.token_hex(8), password_hash, nickname, clock.now_iso()),
    )
    return cur.lastrowid


def create_demo_league(db, owner_id, owner_nickname, password_hash):
    """체험 리그를 만들고 바로 1라운드 문제 만들기 단계로 시작한다. 만든 리그 번호를 돌려준다.
    password_hash: 가상 계정에 넣을 해시 (아무도 모르는 비밀번호라 로그인할 수 없다)."""
    now = clock.now_utc()
    admin_id = _new_bot(db, "체험 선생님", password_hash)
    names = [n for n in BOT_NAMES if not same_nickname(n, owner_nickname)][:3]
    bot_ids = [_new_bot(db, n, password_hash) for n in names]

    cur = db.execute(
        "INSERT INTO league (name, code, admin_id, status, subjects, rewards, match_days, first_date, "
        "deadline_time, make_days, league_mode, created_at, demo_owner_id) "
        "VALUES (?, ?, ?, 'running', ?, ?, ?, ?, '23:59', 1, 'full', ?, ?)",
        ("🎮 체험 리그", gen_league_code(db), admin_id, json.dumps(DEMO_SUBJECTS, ensure_ascii=False),
         json.dumps(DEMO_REWARDS, ensure_ascii=False), json.dumps([clock.today_kst().weekday()]),
         clock.today_kst().isoformat(), now.isoformat(), owner_id),
    )
    league_id = cur.lastrowid
    players = [owner_id] + bot_ids
    for i, uid in enumerate(players):  # 들어온 순서가 대진 순서
        db.execute("INSERT INTO membership (league_id, user_id, joined_at) VALUES (?, ?, ?)",
                   (league_id, uid, (now + timedelta(microseconds=i)).isoformat()))

    # 대진표: 라운드마다 [시작 → 만들기 마감(1일) → 풀기 마감(2일)]. 1라운드는 지금 막 시작
    base = now - timedelta(minutes=1)
    bank_turn = 0
    for rnd, pairs in enumerate(make_round_robin(players), start=1):
        start = base + timedelta(days=ROUND_DAYS * (rnd - 1))
        times = (start.isoformat(), (start + timedelta(days=1)).isoformat(),
                 (start + timedelta(days=ROUND_DAYS)).isoformat())
        for p1, p2 in pairs:
            cur = db.execute(
                "INSERT INTO match (league_id, week, player1_id, player2_id, round_start, make_deadline, solve_deadline) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)", (league_id, rnd, p1, p2) + times)
            match_id = cur.lastrowid
            # 가상 친구는 자기 문제를 미리 [완성]해 둔다
            for me, uid in (("p1", p1), ("p2", p2)):
                if uid in bot_ids:
                    _write_bot_questions(db, league_id, match_id, uid, bank_turn)
                    bank_turn += 1
                    db.execute(f"UPDATE match SET {me}_state = 'done', {me}_saved_at = ? WHERE id = ?",
                               (now.isoformat(), match_id))
    return league_id


def _write_bot_questions(db, league_id, match_id, author_id, turn):
    picks = [("수학", MATH_BANK[(turn * 2) % len(MATH_BANK)]), ("수학", MATH_BANK[(turn * 2 + 1) % len(MATH_BANK)]),
             ("영어", ENGLISH_BANK[turn % len(ENGLISH_BANK)])]
    for subject, (qtype, content, choices, answer, explanation) in picks:
        db.execute(
            "INSERT INTO question (league_id, match_id, author_id, subject, qtype, content, choices, answer, explanation) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (league_id, match_id, author_id, subject, qtype, content,
             json.dumps(choices or [], ensure_ascii=False), str(answer), explanation),
        )


def bots_act(db, league_id):
    """풀기 기간이 된 경기에서 가상 친구가 아직 안 풀었으면 풀어 제출한다 (engine.refresh_league가 부른다)."""
    now = clock.now_iso()
    todo_sql = (
        "SELECT m.* FROM match m WHERE m.league_id = ? AND m.result IS NULL AND m.player2_id IS NOT NULL "
        "AND m.make_deadline <= ? AND m.p1_state = 'done' AND m.p2_state = 'done' AND ("
        "(m.p1_done = 0 AND m.player1_id IN (SELECT id FROM user WHERE demo_kind = 'bot')) OR "
        "(m.p2_done = 0 AND m.player2_id IN (SELECT id FROM user WHERE demo_kind = 'bot')))"
    )
    if not db.execute(todo_sql, (league_id, now)).fetchall():
        return
    lock_db(db)  # 여러 화면이 동시에 열어도 한 번만 제출하게, 잠근 뒤 다시 읽는다
    bots = {r[0] for r in db.execute("SELECT id FROM user WHERE demo_kind = 'bot'").fetchall()}
    for m in db.execute(todo_sql, (league_id, now)).fetchall():
        for me, solver, author in (("p1", m["player1_id"], m["player2_id"]), ("p2", m["player2_id"], m["player1_id"])):
            if solver not in bots or m[f"{me}_done"]:
                continue
            score = 0
            for q in db.execute("SELECT * FROM question WHERE match_id = ? AND author_id = ? ORDER BY id",
                                (m["id"], author)).fetchall():
                given = _bot_answer(q, solver)
                ok = grade_one(q, given)
                score += 1 if ok else 0
                db.execute("INSERT INTO submission (match_id, solver_id, question_id, given, correct, created_at) "
                           "VALUES (?, ?, ?, ?, ?, ?)", (m["id"], solver, q["id"], given, 1 if ok else 0, now))
            db.execute(f"UPDATE match SET {me}_done = 1, {me}_score = ? WHERE id = ?", (score, m["id"]))
        finalize_match_if_ready(db, m["id"])
    db.commit()


def _bot_answer(q, solver_id):
    """가상 친구의 답: 대략 세 문제 중 두 문제를 맞힌다 (늘 같은 결과가 나오게 번호로 정한다)."""
    if (q["id"] + solver_id) % 3:
        return q["answer"]
    if q["qtype"] == "mc":
        return str((int(q["answer"]) + 1) % max(len(json.loads(q["choices"] or "[]")), 1))
    return "모르겠어요"


def _deadlines(db, league_id):
    rows = db.execute("SELECT week, make_deadline, solve_deadline FROM match WHERE league_id = ?", (league_id,)).fetchall()
    out = []
    for r in rows:
        out.append((parse_utc(r["make_deadline"]), r["week"], "make"))
        out.append((parse_utc(r["solve_deadline"]), r["week"], "solve"))
    return sorted(set(out))


def next_step(db, league_id):
    """[다음 단계로]를 누르면 지나갈 마감: {"at": 시각, "label": 설명} 또는 None (더 앞당길 것 없음)."""
    now = clock.now_utc()
    for at, week, kind in _deadlines(db, league_id):
        if at > now:
            label = f"{week}라운드 문제 만들기 마감" if kind == "make" else f"{week}라운드 문제 풀기 마감"
            return {"at": at, "label": label}
    pending = db.execute("SELECT COUNT(*) FROM report WHERE league_id = ? AND status = 'pending'", (league_id,)).fetchone()[0]
    deadline = report_deadline(db, league_id)
    if pending and deadline and deadline > now:
        return {"at": deadline, "label": "신고 판정 기한 (판정 안 한 신고는 '문제없음'으로 확정)"}
    return None


def advance(db, league_id):
    """체험 리그의 모든 시각을 앞당겨 다음 마감이 바로 지나게 한다. 지나간 마감 설명을 돌려준다."""
    lock_db(db)
    step = next_step(db, league_id)
    if step is None:
        db.commit()
        return None
    shift = step["at"] - clock.now_utc() + timedelta(seconds=1)
    for m in db.execute("SELECT id, round_start, make_deadline, solve_deadline FROM match WHERE league_id = ?",
                        (league_id,)).fetchall():
        moved = [(parse_utc(m[k]) - shift).isoformat() if m[k] else None
                 for k in ("round_start", "make_deadline", "solve_deadline")]
        db.execute("UPDATE match SET round_start = ?, make_deadline = ?, solve_deadline = ? WHERE id = ?",
                   moved + [m["id"]])
    row = db.execute("SELECT ended_at FROM league WHERE id = ?", (league_id,)).fetchone()
    if row["ended_at"]:
        db.execute("UPDATE league SET ended_at = ? WHERE id = ?",
                   ((parse_utc(row["ended_at"]) - shift).isoformat(), league_id))
    db.commit()
    return step["label"]


def info(db, league_id, user_id):
    """리그 홈에 보여 줄 체험 안내: 선생님 화면인지, [다음 단계로]를 누르면 지나갈 마감."""
    row = db.execute("SELECT admin_id FROM league WHERE id = ?", (league_id,)).fetchone()
    step = next_step(db, league_id)
    return {"as_teacher": row["admin_id"] == user_id, "next": step["label"] if step else None}
