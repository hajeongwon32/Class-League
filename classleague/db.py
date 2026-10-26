"""DB 연결과 표 만들기 (SQLite). 예전 DB에 없는 칸은 켤 때 자동으로 더한다."""

import os
import sqlite3

from flask import g


# 서버를 어느 폴더에서 켜도 같은 DB를 쓰도록 app.py 옆(프로젝트 맨 위 폴더)에 둔다. 시험할 때는 DATABASE_PATH로 바꾼다.
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("DATABASE_PATH") or os.path.join(PROJECT_DIR, "app.db")


def get_db():
    """요청 하나당 DB 연결 하나를 쓴다."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS user (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                nickname TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        # 리그 (F3): 관리자가 만든 리그. status = recruiting(모집 중)/running(진행 중)/finished(끝)
        # subjects: 과목·과목별 문제 수를 담은 JSON 문자열 (예: [{"name":"영어","count":3}])
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS league (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                code TEXT UNIQUE NOT NULL,
                admin_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'recruiting',
                subjects TEXT NOT NULL DEFAULT '[]',
                rewards TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            )
            """
        )
        # 리그 참가 (F5): 어느 학생이 어느 리그에 들어갔는지. 한 학생은 리그 하나만(user_id UNIQUE)
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS membership (
                id INTEGER PRIMARY KEY,
                league_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                joined_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                left_at TEXT
            )
            """
        )
        # 대진/경기 (F6): 리그, 주차, 두 선수, 결과, 각자 점수
        # result = NULL(아직)/'p1'(선수1 승)/'p2'(선수2 승)/'draw'(무)
        # player2_id가 NULL이면 그 주는 부전승(상대가 없음)
        # p1_done/p2_done: 그 선수가 상대 문제를 다 풀어 제출했는지(0/1)
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS match (
                id INTEGER PRIMARY KEY,
                league_id INTEGER NOT NULL,
                week INTEGER NOT NULL,
                player1_id INTEGER NOT NULL,
                player2_id INTEGER,
                result TEXT,
                p1_score INTEGER DEFAULT 0,
                p2_score INTEGER DEFAULT 0,
                p1_done INTEGER DEFAULT 0,
                p2_done INTEGER DEFAULT 0
            )
            """
        )
        # 문제 (F7): 만든 사람, 리그, 과목, 유형, 내용, 보기, 정답, 해설
        # qtype = 'mc'(객관식)/'sa'(주관식)
        # choices: 객관식 보기 JSON 배열 (주관식이면 '[]')
        # answer: 객관식이면 정답 보기 번호(0부터), 주관식이면 정답 글자
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS question (
                id INTEGER PRIMARY KEY,
                league_id INTEGER NOT NULL,
                author_id INTEGER NOT NULL,
                subject TEXT NOT NULL,
                qtype TEXT NOT NULL,
                content TEXT NOT NULL,
                choices TEXT NOT NULL DEFAULT '[]',
                answer TEXT NOT NULL,
                explanation TEXT NOT NULL DEFAULT ''
            )
            """
        )
        # 풀이 (F8/F9): 누가 어느 경기에서 어떤 문제에 무엇을 답했는지, 맞았는지
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS submission (
                id INTEGER PRIMARY KEY,
                match_id INTEGER NOT NULL,
                solver_id INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                given TEXT NOT NULL,
                correct INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        # 라운드별 출제 범위 (F4-2): 따로 정하지 않은 라운드·과목은 리그의 기본 범위를 쓴다
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS round_scope (
                league_id INTEGER NOT NULL,
                round INTEGER NOT NULL,
                subject TEXT NOT NULL,
                scope TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (league_id, round, subject)
            )
            """
        )

        # --- 9단계 마이그레이션: 참가 기록을 활성/보관/내보냄으로 나눈다 ---
        # 예전 표는 user_id가 UNIQUE라서 리그가 끝나도 새 리그에 들어갈 수 없었다.
        # 표를 새로 만들고 예전 기록은 모두 'active'로 옮긴다 (지금 쓰는 사람에게는 바뀌는 것이 없다).
        mcols_m = [r[1] for r in db.execute("PRAGMA table_info(membership)").fetchall()]
        if "status" not in mcols_m:
            db.execute("ALTER TABLE membership RENAME TO membership_old")
            db.execute(
                """
                CREATE TABLE membership (
                    id INTEGER PRIMARY KEY,
                    league_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    joined_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    left_at TEXT
                )
                """
            )
            db.execute(
                "INSERT INTO membership (id, league_id, user_id, joined_at, status) "
                "SELECT id, league_id, user_id, joined_at, 'active' FROM membership_old"
            )
            db.execute("DROP TABLE membership_old")
        # 한 사람은 '활성' 참가 기록을 하나만 가질 수 있다 (보관·내보냄 기록은 여러 개 가능)
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS one_active_membership "
            "ON membership(user_id) WHERE status = 'active'"
        )
        db.execute("CREATE INDEX IF NOT EXISTS membership_league ON membership(league_id, status)")
        lcols = [r[1] for r in db.execute("PRAGMA table_info(league)").fetchall()]
        # 관리자가 끝난 리그를 [리그 닫기]하면 1 → 새 리그를 만들 수 있다 (기록은 남는다)
        if "admin_closed" not in lcols:
            db.execute("ALTER TABLE league ADD COLUMN admin_closed INTEGER NOT NULL DEFAULT 0")
        # 모집 중 [리그 삭제]하면 1 → 코드로 들어올 수 없고 어디에도 보이지 않는다
        if "deleted" not in lcols:
            db.execute("ALTER TABLE league ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0")
        # 학생을 내보내서 1명만 남아 일찍 끝난 경우의 종료 시각 (신고 판정 기한 계산용)
        if "ended_at" not in lcols:
            db.execute("ALTER TABLE league ADD COLUMN ended_at TEXT")
        # 혼자 체험해 보기: 체험 리그면 체험하는 사람의 번호 (진짜 리그는 NULL)
        if "demo_owner_id" not in lcols:
            db.execute("ALTER TABLE league ADD COLUMN demo_owner_id INTEGER")
        # 체험용 계정: 'guest'(로그인 없이 체험 시작한 사람) / 'bot'(가상 친구·체험 선생님) / NULL(보통 계정)
        ucols = [r[1] for r in db.execute("PRAGMA table_info(user)").fetchall()]
        if "demo_kind" not in ucols:
            db.execute("ALTER TABLE user ADD COLUMN demo_kind TEXT")

        # 로그인 실패 기록: 아이디별로 연달아 틀린 횟수와 막힌 시각
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS login_attempt (
                username TEXT PRIMARY KEY,
                fails INTEGER NOT NULL DEFAULT 0,
                locked_until TEXT
            )
            """
        )

        # 오답 노트 정리 (F18): [이제 알아요]로 표시한 문제
        # source = 'league'(리그 경기, qkey는 question.id)
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS wrong_note_known (
                user_id INTEGER NOT NULL,
                source TEXT NOT NULL,
                qkey TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (user_id, source, qkey)
            )
            """
        )

        # --- 간단 마이그레이션: 예전에 만든 league 테이블에 subjects 컬럼이 없으면 추가 ---
        cols = [r[1] for r in db.execute("PRAGMA table_info(league)").fetchall()]
        if "subjects" not in cols:
            db.execute(
                "ALTER TABLE league ADD COLUMN subjects TEXT NOT NULL DEFAULT '[]'"
            )
        # 경기 일정 (F4·F6): 경기 요일(JSON, 월=0 … 일=6)과 첫 경기 날짜(YYYY-MM-DD, 한국 날짜)
        if "match_days" not in cols:
            db.execute("ALTER TABLE league ADD COLUMN match_days TEXT NOT NULL DEFAULT '[]'")
            # 예전에 만든 모집 중 리그는 경기 요일이 없어서 시작할 수 없으므로 '월요일'로 채워 둔다
            db.execute("UPDATE league SET match_days = '[0]' WHERE status = 'recruiting'")
        if "first_date" not in cols:
            db.execute("ALTER TABLE league ADD COLUMN first_date TEXT")
        # 마감 시각(한국 시간 "HH:MM")과 문제 만들기 기간(일, 0 = 자동: 라운드의 절반)
        if "deadline_time" not in cols:
            db.execute("ALTER TABLE league ADD COLUMN deadline_time TEXT NOT NULL DEFAULT '23:59'")
        if "make_days" not in cols:
            db.execute("ALTER TABLE league ADD COLUMN make_days INTEGER NOT NULL DEFAULT 0")
        # 리그 기간 방식 (F4): 'full'(전체 리그) / 'short'(시험 대비 단기 리그)와 종료 희망일(한국 날짜)
        if "league_mode" not in cols:
            db.execute("ALTER TABLE league ADD COLUMN league_mode TEXT NOT NULL DEFAULT 'full'")
        if "end_date" not in cols:
            db.execute("ALTER TABLE league ADD COLUMN end_date TEXT")
        if "rewards" not in cols:
            db.execute(
                "ALTER TABLE league ADD COLUMN rewards TEXT NOT NULL DEFAULT '[]'"
            )
        # match 테이블에 제출여부 컬럼이 없으면 추가
        mcols = [r[1] for r in db.execute("PRAGMA table_info(match)").fetchall()]
        if "p1_done" not in mcols:
            db.execute("ALTER TABLE match ADD COLUMN p1_done INTEGER DEFAULT 0")
        if "p2_done" not in mcols:
            db.execute("ALTER TABLE match ADD COLUMN p2_done INTEGER DEFAULT 0")
        # 문제 상태 (F7): 'draft'(만드는 중) / 'done'(완성). 마지막 임시 저장 시각
        for col, ddl in (("p1_state", "TEXT NOT NULL DEFAULT 'draft'"), ("p2_state", "TEXT NOT NULL DEFAULT 'draft'"),
                         ("p1_saved_at", "TEXT"), ("p2_saved_at", "TEXT")):
            if col not in mcols:
                db.execute(f"ALTER TABLE match ADD COLUMN {col} {ddl}")
        # 몰수 경기 (F14): 1이면 마감을 어겨 끝난 경기. 점수는 순위(맞힌 수·득실차)에 넣지 않는다
        # forfeit_stage: 'make'(만들기 마감) / 'solve'(풀기 마감)
        if "forfeit" not in mcols:
            db.execute("ALTER TABLE match ADD COLUMN forfeit INTEGER NOT NULL DEFAULT 0")
        if "forfeit_stage" not in mcols:
            db.execute("ALTER TABLE match ADD COLUMN forfeit_stage TEXT")
        # 문제는 경기(라운드 상대)마다 새로 만든다 → 어느 경기용인지 기록
        # (예전 리그의 문제는 match_id가 비어 있고, 새 경기에는 쓰이지 않는다)
        qcols = [r[1] for r in db.execute("PRAGMA table_info(question)").fetchall()]
        if "match_id" not in qcols:
            db.execute("ALTER TABLE question ADD COLUMN match_id INTEGER")
        # 무효 문제 (F17): 관리자가 [무효]로 판정하면 1, 이유는 신고 이유
        if "void" not in qcols:
            db.execute("ALTER TABLE question ADD COLUMN void INTEGER NOT NULL DEFAULT 0")
        if "void_reason" not in qcols:
            db.execute("ALTER TABLE question ADD COLUMN void_reason TEXT")
        # 문제 신고 (F17): 한 문제는 푼 학생 한 명만 한 번 신고한다
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS report (
                id INTEGER PRIMARY KEY,
                league_id INTEGER NOT NULL,
                match_id INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                reporter_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                decided_at TEXT,
                UNIQUE (question_id, reporter_id)
            )
            """
        )
        # 라운드 시각 (UTC ISO): 라운드 시작 / 문제 만들기 마감 / 풀기 마감(= 라운드 끝)
        for col in ("round_start", "make_deadline", "solve_deadline"):
            if col not in mcols:
                db.execute(f"ALTER TABLE match ADD COLUMN {col} TEXT")


def lock_db(db):
    """
    '검사하고 저장하기' 사이에 다른 요청이 끼어들지 못하게 DB 쓰기를 잠근다.
    (버튼을 여러 번 빨리 눌러도 두 번 저장되거나 오류가 나지 않게)
    commit하거나 요청이 끝나면 자동으로 풀린다.
    """
    if not db.in_transaction:
        db.execute("BEGIN IMMEDIATE")
