"""요청 입력 읽기 도우미. 이상한 입력이 와도 멈추지 않게 한다."""

from flask import request


def read_json():
    """요청 본문을 dict로 읽는다. JSON이 아니거나 dict가 아니면 빈 dict."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def text_of(obj, key):
    """obj[key]가 글자면 앞뒤 공백을 지워 돌려주고, 아니면(숫자·목록·없음) 빈 글자."""
    value = obj.get(key) if isinstance(obj, dict) else None
    return value.strip() if isinstance(value, str) else ""
