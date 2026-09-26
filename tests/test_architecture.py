"""Booking.status may only change inside apps/bookings/services.py (TASK 3.1)."""

import re
from pathlib import Path

import pytest

from apps.bookings.models import Booking, StatusChangeError
from tests.factories import BookingFactory

ROOT = Path(__file__).resolve().parent.parent
ALLOWED = ROOT / "apps" / "bookings" / "services.py"

# `something.status = ...` (not `==`), or `.update(status=...)` on a queryset.
ASSIGNMENT = re.compile(r"\.status\s*=(?!=)")
QUERYSET_UPDATE = re.compile(r"\.update\([^)]*\bstatus\s*=")


def python_sources():
    for path in (ROOT / "apps").rglob("*.py"):
        if "migrations" not in path.parts:
            yield path


def test_status_is_only_assigned_in_booking_services():
    offenders = []
    for path in python_sources():
        if path == ALLOWED:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if ASSIGNMENT.search(line) or QUERYSET_UPDATE.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
    assert offenders == []


def test_the_scan_actually_finds_assignments():
    assert ASSIGNMENT.search("booking.status = 'confirmed'")
    assert not ASSIGNMENT.search("if booking.status == 'confirmed':")
    assert QUERYSET_UPDATE.search("Booking.objects.filter(pk=1).update(status='cancelled')")


@pytest.mark.django_db
def test_model_refuses_status_change_outside_service():
    booking = BookingFactory()
    fresh = Booking.objects.get(pk=booking.pk)
    fresh.status = Booking.Status.CONFIRMED
    with pytest.raises(StatusChangeError):
        fresh.save()
    assert Booking.objects.get(pk=booking.pk).status == Booking.Status.PENDING


@pytest.mark.django_db
def test_model_allows_saving_other_fields():
    booking = Booking.objects.get(pk=BookingFactory().pk)
    booking.internal_note = "VIP"
    booking.save()


TEXT_SUFFIXES = {".md", ".py", ".html", ".txt", ".yml", ".yaml", ".ps1", ".sh", ".toml", ".css"}
SKIP_DIRS = {".venv", ".tools", ".git", "node_modules", "staticfiles"}


def test_no_stray_control_characters_in_sources():
    """Scripted edits once turned `\b` in `scripts\build-css.ps1` into a backspace byte."""
    offenders = []
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        if SKIP_DIRS & set(rel.parts) or not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        if rel.parts[:2] in {("static", "js"), ("static", "css")}:  # vendored / generated
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if any(ord(ch) < 32 and ch != "\t" for ch in line):
                offenders.append(f"{rel}:{number}")
    assert offenders == []
