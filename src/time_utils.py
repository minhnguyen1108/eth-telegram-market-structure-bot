from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from src.config import settings


def app_timezone() -> ZoneInfo:
    return ZoneInfo(settings.timezone)


def local_now_naive() -> datetime:
    return datetime.now(app_timezone()).replace(tzinfo=None)


def utc_to_local_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("UTC"))
    return value.astimezone(app_timezone()).replace(tzinfo=None)
