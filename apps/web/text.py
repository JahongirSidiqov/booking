"""Uzbek UI text helpers.

Every oʻ/gʻ in the interface uses U+02BB (MODIFIER LETTER TURNED COMMA). Mixing it with the
ASCII apostrophe breaks search and some fonts, so it lives in one constant and
tests/web/test_text.py rejects ASCII apostrophes inside Uzbek words in templates.
"""

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

OKINA = "ʻ"  # ʻ as in oʻ, gʻ
NBSP = " "

WEEKDAYS_SHORT = ("Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya")
WEEKDAYS = ("dushanba", "seshanba", "chorshanba", "payshanba", "juma", "shanba", "yakshanba")
MONTHS_SHORT = ("yan", "fev", "mar", "apr", "may", "iyn", "iyl", "avg", "sen", "okt", "noy", "dek")
MONTHS = (
    "yanvar",
    "fevral",
    "mart",
    "aprel",
    "may",
    "iyun",
    "iyul",
    "avgust",
    "sentabr",
    "oktabr",
    "noyabr",
    "dekabr",
)
CURRENCY_LABELS = {"UZS": f"so{OKINA}m"}


def money(amount: Decimal | int | float, currency: str = "UZS") -> str:
    """60000 → '60 000 soʻm' (non-breaking thousands separator, no decimals for whole sums)."""
    value = Decimal(amount)
    digits = f"{value:,.0f}" if value == value.to_integral() else f"{value:,.2f}"
    label = CURRENCY_LABELS.get(currency, currency)
    return f"{digits.replace(',', NBSP)}{NBSP}{label}"


def local(moment: datetime, tz: str) -> datetime:
    return moment.astimezone(ZoneInfo(tz))


def short_day(day: date) -> str:
    """'Ch, 1-okt'"""
    return f"{WEEKDAYS_SHORT[day.weekday()]}, {day.day}-{MONTHS_SHORT[day.month - 1]}"


def long_day(day: date) -> str:
    """'1-oktabr, payshanba'"""
    return f"{day.day}-{MONTHS[day.month - 1]}, {WEEKDAYS[day.weekday()]}"


def duration(minutes: int) -> str:
    hours, rest = divmod(minutes, 60)
    if not hours:
        return f"{rest} daq"
    if not rest:
        return f"{hours} soat"
    return f"{hours} soat {rest} daq"


def day_part(moment: datetime) -> str:
    """Slot group for the picker: morning < 12:00 ≤ afternoon < 17:00 ≤ evening (local time)."""
    if moment.hour < 12:
        return "morning"
    if moment.hour < 17:
        return "afternoon"
    return "evening"
