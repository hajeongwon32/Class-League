"""시각 다루기. 화면은 한국 시간(KST), DB는 UTC. '지금 시각'은 now_utc() 하나로만 정한다 (시험에서 바꿀 수 있게)."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")  # 모든 날짜는 한국 시간 기준


def today_kst():
    return now_utc().astimezone(KST).date()


def kst_midnight_utc(d):
    """한국 날짜 d의 0시를 UTC ISO 글자로 (DB 저장용)."""
    return datetime(d.year, d.month, d.day, tzinfo=KST).astimezone(timezone.utc).isoformat()


def kst_deadline_utc(d, hhmm):
    """한국 날짜 d의 마감 시각을 UTC ISO 글자로. '23:59'는 다음 날 0시 직전까지로 본다."""
    if hhmm == "23:59":
        return kst_midnight_utc(d + timedelta(days=1))
    h, m = map(int, hhmm.split(":"))
    return datetime(d.year, d.month, d.day, h, m, tzinfo=KST).astimezone(timezone.utc).isoformat()


def now_utc():
    """지금 시각 (UTC). 시험할 때 시간을 바꿀 수 있게 함수로 둔다."""
    return datetime.now(timezone.utc)


def parse_utc(iso):
    return datetime.fromisoformat(iso) if iso else None


def now_iso():
    return now_utc().isoformat()  # 시각은 모두 now_utc() 하나로 정한다
