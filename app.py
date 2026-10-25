"""
Class League 서버 진입점: 앱을 만들고 설정·로그인·화면·API를 한데 붙인다.
실행: flask --app app run

기능 코드는 classleague 폴더에 있다.
- classleague/db.py · clock.py · inputs.py   DB, 시각(KST/UTC), 요청 입력
- classleague/schedule.py · standings.py      대진·일정 계산, 순위 계산
- classleague/engine.py · league_state.py     마감 자동 처리·채점·재계산, 리그 상태 조회
- classleague/security.py                     로그인 쿠키·보안 헤더
- classleague/routes/                         API (로그인·리그·경기·관리자·신고·오답 노트)
"""

import os
import secrets

from dotenv import load_dotenv
from flask import Flask, render_template
from werkzeug.exceptions import HTTPException

from classleague.db import close_db, init_db
from classleague.routes import BLUEPRINTS
from classleague.routes.auth import bcrypt, login_manager
from classleague.security import init_security

load_dotenv()

app = Flask(__name__)
# 세션(로그인 상태)을 지키는 데 쓰는 비밀키. .env의 SECRET_KEY를 쓴다 (코드에 적지 않는다).
_secret = os.environ.get("SECRET_KEY")
if not _secret:
    # .env가 없을 때만 임시 키를 만든다. 이 경우 앱이 다시 켜지면 로그인이 풀린다.
    _secret = secrets.token_hex(32)
    print("경고: .env에 SECRET_KEY가 없어 임시 비밀키를 씁니다")
app.secret_key = _secret
init_security(app)  # 로그인 쿠키·보안 헤더·요청 크기 제한

bcrypt.init_app(app)
login_manager.init_app(app)
app.teardown_appcontext(close_db)  # 요청이 끝나면 DB 연결을 닫는다
for bp in BLUEPRINTS:
    app.register_blueprint(bp)

init_db()


# ---------- 오류가 나도 알아듣기 쉬운 안내를 JSON으로 돌려준다 ----------
HTTP_ERROR_TEXT = {
    400: "요청 형식이 올바르지 않아요",
    404: "없는 주소예요",
    405: "이 주소에서는 할 수 없는 동작이에요",
    413: "보낸 내용이 너무 커요",
    415: "요청 형식이 올바르지 않아요",
}


@app.errorhandler(HTTPException)
def handle_http_error(e):
    return {"error": HTTP_ERROR_TEXT.get(e.code, "요청을 처리하지 못했어요")}, e.code


@app.errorhandler(Exception)
def handle_unexpected_error(e):
    # 생각 못 한 오류: 기록(app.log)은 남기고, 화면에는 쉬운 안내만 보여 준다
    app.logger.exception("처리하지 못한 오류")
    return {"error": "잠시 문제가 생겼어요. 다시 시도해 주세요"}, 500


# ---------- PWA (앱 설치): 서비스 워커는 사이트 전체를 다뤄야 해서 / 에서 준다 ----------
@app.get("/sw.js")
def service_worker():
    res = app.send_static_file("sw.js")
    res.headers["Content-Type"] = "application/javascript; charset=utf-8"
    res.headers["Cache-Control"] = "no-cache"  # 새 버전이 바로 반영되게
    res.headers["Service-Worker-Allowed"] = "/"
    return res


@app.get("/favicon.ico")
def favicon():
    return app.send_static_file("icon-192.png")


# ---------- 화면 ----------
@app.get("/")
def index():
    return render_template("index.html")
