import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from apps.web import text

ROOT = Path(__file__).resolve().parents[2]

# oʻ / gʻ written with an ASCII apostrophe or a typographic quote instead of U+02BB.
WRONG_OKINA = re.compile(r"[oOgG]['‘’`][a-zA-Z]")


def uzbek_sources():
    yield from (ROOT / "templates").rglob("*.html")
    for path in (ROOT / "apps").rglob("*.py"):
        if "migrations" not in path.parts:
            yield path


def test_uzbek_text_uses_a_single_apostrophe():
    offenders = []
    for path in uzbek_sources():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if WRONG_OKINA.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
    assert offenders == []


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (Decimal("60000.00"), "60 000 soʻm"),
        (Decimal("1580"), "1 580 soʻm"),
        (Decimal("0"), "0 soʻm"),
        (Decimal("99.50"), "99.50 soʻm"),
    ],
)
def test_money(amount, expected):
    assert text.money(amount) == expected


def test_dates():
    assert text.short_day(date(2026, 10, 1)) == "Pa, 1-okt"
    assert text.long_day(date(2026, 10, 1)) == "1-oktabr, payshanba"


@pytest.mark.parametrize(
    ("minutes", "expected"), [(30, "30 daq"), (60, "1 soat"), (90, "1 soat 30 daq")]
)
def test_duration(minutes, expected):
    assert text.duration(minutes) == expected
