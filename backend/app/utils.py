import calendar
import re
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from .config import get_settings

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


# ---------- money (stored as integer paise) ----------
def to_paise(amount: Decimal) -> int:
    return int((Decimal(amount) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def to_rupees(paise) -> float:
    return round(int(paise) / 100, 2)


# ---------- dates ----------
def today() -> date:
    return datetime.now(ZoneInfo(get_settings().timezone)).date()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def current_month() -> str:
    return today().strftime("%Y-%m")


def is_month(value: str) -> bool:
    return bool(MONTH_RE.match(value or ""))


def require_month(value: str | None, field: str = "month") -> str:
    if value is None:
        return current_month()
    if not is_month(value):
        raise HTTPException(422, f"{field} must look like YYYY-MM")
    return value


def add_months(month: str, n: int) -> str:
    y, m = int(month[:4]), int(month[5:7])
    idx = y * 12 + (m - 1) + n
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def month_range(start: str, end: str) -> list[str]:
    out, m = [], start
    while m <= end:
        out.append(m)
        m = add_months(m, 1)
    return out


def days_in_month(month: str) -> int:
    return calendar.monthrange(int(month[:4]), int(month[5:7]))[1]