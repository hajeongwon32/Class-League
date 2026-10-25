"""
브라우저 쪽 보안 설정 (SPEC 5. 보안·안전): 로그인 쿠키, 보안 헤더, 요청 크기 제한.
app.py에서 init_security(app)를 한 번 부른다.
"""

import re

from flask import request
from werkzeug.middleware.proxy_fix import ProxyFix

# 문제 50개(과목 5 × 10문제)를 가장 길게 써도 0.5MB 안쪽이다. 그보다 훨씬 큰 요청은 받지 않는다 (413).
MAX_REQUEST_BYTES = 2 * 1024 * 1024

# 우리 사이트의 파일만 쓰게 한다. 누가 문제나 닉네임에 스크립트를 넣어도 실행되지 않는다.
# (화면에는 인라인 스크립트·인라인 style 속성을 두지 않는다. 자바스크립트의 element.style은 괜찮다)
CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self'",
    "img-src 'self' data:",
    "connect-src 'self'",
    "manifest-src 'self'",
    "worker-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",  # 다른 사이트가 우리 앱을 자기 페이지 안에 넣지 못하게
])

SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Frame-Options": "DENY",                # frame-ancestors를 모르는 옛 브라우저용
    "X-Content-Type-Options": "nosniff",      # 파일 종류를 브라우저가 짐작하지 않게
    "Referrer-Policy": "same-origin",         # 다른 사이트로 갈 때 우리 주소를 알려 주지 않게
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",  # 쓰지 않는 기능은 꺼 둔다
}

_SECURE_FLAG = re.compile(r";\s*secure\s*(;|$)", re.IGNORECASE)


class SecureCookiesOnHttps:
    """
    https로 들어온 요청이면 모든 쿠키(로그인 세션·로그인 유지)에 Secure를 붙인다.
    Secure 쿠키는 암호화된 연결로만 오가서 공용 와이파이에서 엿볼 수 없다.
    내 컴퓨터에서 http로 켰을 때는 붙이지 않는다 (붙이면 http에서는 로그인이 안 된다).
    """

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        if environ.get("wsgi.url_scheme") != "https":
            return self.wsgi_app(environ, start_response)

        def start_secure(status, headers, exc_info=None):
            headers = [
                (k, v + "; Secure") if k.lower() == "set-cookie" and not _SECURE_FLAG.search(v) else (k, v)
                for k, v in headers
            ]
            return start_response(status, headers, exc_info)

        return self.wsgi_app(environ, start_secure)


def add_security_headers(response):
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    if request.is_secure:
        # 한 번 https로 들어온 브라우저는 1년 동안 http로 접속하지 않게
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    # API 응답(경기·문제·오답 등)은 기기에 남기지 않는다 (같은 기기를 쓰는 다른 사람에게 보이지 않게)
    if response.mimetype == "application/json":
        response.headers.setdefault("Cache-Control", "no-store")
    return response


def init_security(app):
    app.config.update(
        MAX_CONTENT_LENGTH=MAX_REQUEST_BYTES,
        # 다른 사이트에서 보낸 요청에는 로그인 쿠키를 붙이지 않는다 (몰래 요청 보내기 방지)
        SESSION_COOKIE_SAMESITE="Lax",
        REMEMBER_COOKIE_SAMESITE="Lax",
        # 자바스크립트가 로그인 쿠키를 읽지 못하게 (Flask 세션은 원래 켜져 있다)
        SESSION_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_HTTPONLY=True,
    )
    app.after_request(add_security_headers)
    # 배포 서버 앞의 프록시가 알려 주는 원래 주소(https)를 믿고, 그 기준으로 Secure를 붙인다
    app.wsgi_app = ProxyFix(SecureCookiesOnHttps(app.wsgi_app), x_proto=1)
