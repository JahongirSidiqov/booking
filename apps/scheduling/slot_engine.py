"""Slot engine: pure functions, no database and no clock.

Everything the engine needs (rules, time offs, busy ranges, `now`) is passed in, so the same
function answers "which slots are free?" for the API listing and "is this exact slot still
free?" inside create_booking — one source of truth, trivially unit-testable.

Conventions:
- every datetime in and out is timezone-aware UTC;
- every interval is half-open [start, end), so 10:00–10:30 and 10:30–11:00 do not collide;
- availability rules are local wall-clock times in the provider's timezone.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from apps.common.exceptions import DomainError

MAX_RANGE_DAYS = 31

Interval = tuple[datetime, datetime]


class RuleLike(Protocol):
    weekday: int
    start_time: time
    end_time: time


class ServiceLike(Protocol):
    duration_minutes: int


class ProviderLike(Protocol):
    timezone: str | None


class SettingsLike(Protocol):
    timezone: str
    slot_step_minutes: int
    min_lead_time_minutes: int
    max_advance_days: int


@dataclass(frozen=True, order=True)
class Slot:
    start_at: datetime
    end_at: datetime


@dataclass(frozen=True)
class Rule:
    weekday: int
    start_time: time
    end_time: time


def as_zone(tz: str | ZoneInfo) -> ZoneInfo:
    return tz if isinstance(tz, ZoneInfo) else ZoneInfo(tz)


def local_day_bounds(day: date, tz: str | ZoneInfo) -> Interval:
    """UTC instants of local midnight → next local midnight (23 or 25 hours on DST days)."""
    zone = as_zone(tz)
    start = datetime.combine(day, time.min, tzinfo=zone).astimezone(UTC)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC)
    return start, end


def merge(intervals: Iterable[Interval]) -> list[Interval]:
    merged: list[Interval] = []
    for start, end in sorted(i for i in intervals if i[0] < i[1]):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def subtract(windows: Iterable[Interval], blocks: Iterable[Interval]) -> list[Interval]:
    """Remove every block from every window; blocks may overlap each other or the edges."""
    blocks = merge(blocks)
    result: list[Interval] = []
    for w_start, w_end in merge(windows):
        cursor = w_start
        for b_start, b_end in blocks:
            if b_end <= cursor or b_start >= w_end:
                continue
            if b_start > cursor:
                result.append((cursor, b_start))
            cursor = max(cursor, b_end)
            if cursor >= w_end:
                break
        if cursor < w_end:
            result.append((cursor, w_end))
    return result


def rule_windows(rules: Iterable[RuleLike], day: date, tz: str | ZoneInfo) -> list[Interval]:
    """Working windows of one provider-local date, converted to UTC for that exact date.

    Converting per date (not once per rule) is what keeps "09:00 local" correct on both
    sides of a DST change.
    """
    zone = as_zone(tz)
    windows = []
    for rule in rules:
        if rule.weekday != day.weekday():
            continue
        start = datetime.combine(day, rule.start_time, tzinfo=zone).astimezone(UTC)
        end = datetime.combine(day, rule.end_time, tzinfo=zone).astimezone(UTC)
        windows.append((start, end))
    return windows


def align_to_step(moment: datetime, tz: str | ZoneInfo, step_minutes: int) -> datetime:
    """First instant >= moment whose local wall-clock minute-of-day is a multiple of step.

    The grid is anchored to local midnight rather than to UTC so that customers always see
    09:00, 09:15, ... even in zones with :30 or :45 offsets (India, Nepal).
    """
    zone = as_zone(tz)
    local = moment.astimezone(zone)
    midnight = datetime.combine(local.date(), time.min)
    elapsed = local.replace(tzinfo=None) - midnight
    step = timedelta(minutes=step_minutes)
    steps = -(-elapsed // step)  # ceiling division on timedelta
    candidate = (midnight + steps * step).replace(tzinfo=zone).astimezone(UTC)
    while candidate < moment:
        candidate += step
    return candidate


def _provider_zone(provider: ProviderLike, settings: SettingsLike) -> ZoneInfo:
    return as_zone(provider.timezone or settings.timezone)


def get_available_slots(
    *,
    service: ServiceLike,
    provider: ProviderLike,
    date_local: date,
    now: datetime,
    settings: SettingsLike,
    rules: Iterable[RuleLike],
    time_offs: Iterable[Interval] = (),
    busy_ranges: Iterable[Interval] = (),
    tz: str | ZoneInfo | None = None,
) -> list[Slot]:
    """Free slots whose start falls on `date_local` as seen in timezone `tz`.

    `tz` is the customer's timezone (defaults to the provider's). A customer's calendar day
    may span two provider-local dates, so rules of every provider date touching that day are
    considered, and the result is cut back to the customer's day.
    """
    provider_zone = _provider_zone(provider, settings)
    day_start, day_end = local_day_bounds(date_local, tz or provider_zone)

    earliest = now + timedelta(minutes=settings.min_lead_time_minutes)
    latest = now + timedelta(days=settings.max_advance_days)
    if earliest >= day_end or latest < day_start:
        return []

    rules = list(rules)
    first = day_start.astimezone(provider_zone).date()
    last = (day_end - timedelta(microseconds=1)).astimezone(provider_zone).date()
    windows: list[Interval] = []
    day = first
    while day <= last:
        windows.extend(rule_windows(rules, day, provider_zone))
        day += timedelta(days=1)

    free = subtract(subtract(windows, time_offs), busy_ranges)

    duration = timedelta(minutes=service.duration_minutes)
    step = timedelta(minutes=settings.slot_step_minutes)
    slots: list[Slot] = []
    for w_start, w_end in free:
        start = align_to_step(w_start, provider_zone, settings.slot_step_minutes)
        # A slot only exists if the whole service fits before the window closes (edge #7).
        while start + duration <= w_end:
            if (
                day_start <= start < day_end
                and start > now  # "right now" already counts as the past (edge #4)
                and start >= earliest
                and start <= latest
            ):
                slots.append(Slot(start, start + duration))
            start += step
    return sorted(set(slots))


def slot_rejection(
    *,
    service: ServiceLike,
    provider: ProviderLike,
    start_at: datetime,
    now: datetime,
    settings: SettingsLike,
    rules: Iterable[RuleLike],
    time_offs: Iterable[Interval] = (),
    busy_ranges: Iterable[Interval] = (),
) -> str | None:
    """Why `start_at` cannot be booked, as an error code — or None if it can.

    The verdict comes from get_available_slots itself (the same function that renders the
    picker); the cheaper checks before it only decide *which* error code to report.
    """
    if start_at <= now:
        return "IN_PAST"
    if start_at < now + timedelta(minutes=settings.min_lead_time_minutes):
        return "LEAD_TIME"
    if start_at > now + timedelta(days=settings.max_advance_days):
        return "TOO_FAR_AHEAD"
    provider_zone = _provider_zone(provider, settings)
    if align_to_step(start_at, provider_zone, settings.slot_step_minutes) != start_at:
        return "STEP_MISALIGNED"

    wanted = Slot(start_at, start_at + timedelta(minutes=service.duration_minutes))
    common = {
        "service": service,
        "provider": provider,
        "date_local": start_at.astimezone(provider_zone).date(),
        "now": now,
        "settings": settings,
        "rules": list(rules),
        "time_offs": list(time_offs),
        "tz": provider_zone,
    }
    if wanted not in get_available_slots(**common):
        return "SLOT_UNAVAILABLE"
    if wanted not in get_available_slots(**common, busy_ranges=busy_ranges):
        return "SLOT_TAKEN"
    return None


def uncovered(
    intervals: Iterable[Interval], rules: Iterable[RuleLike], tz: str | ZoneInfo
) -> list[Interval]:
    """Intervals that do not fit entirely inside the working windows defined by `rules`.

    Used before narrowing a schedule: a booking left outside the new hours is a conflict.
    """
    zone = as_zone(tz)
    rules = list(rules)
    result = []
    for start, end in intervals:
        first = start.astimezone(zone).date()
        last = (end - timedelta(microseconds=1)).astimezone(zone).date()
        windows: list[Interval] = []
        day = first
        while day <= last:
            windows.extend(rule_windows(rules, day, zone))
            day += timedelta(days=1)
        if not any(w_start <= start and end <= w_end for w_start, w_end in merge(windows)):
            result.append((start, end))
    return result


def validate_range(date_from: date, date_to: date) -> None:
    if date_to < date_from:
        raise DomainError(
            "VALIDATION_ERROR",
            "Kiritilgan maʼlumotlarni tekshiring.",
            errors={"to": ["'to' sanasi 'from' dan oldin boʻlmasin."]},
        )
    if (date_to - date_from).days + 1 > MAX_RANGE_DAYS:
        raise DomainError(
            "RANGE_TOO_LARGE",
            f"Sana oraligʻi {MAX_RANGE_DAYS} kundan oshmasin.",
            400,
            title="Oraliq juda katta",
        )


def get_day_summary(
    *,
    service: ServiceLike,
    provider: ProviderLike,
    date_from: date,
    date_to: date,
    now: datetime,
    settings: SettingsLike,
    rules: Iterable[RuleLike],
    time_offs: Iterable[Interval] = (),
    busy_ranges: Iterable[Interval] = (),
    tz: str | ZoneInfo | None = None,
) -> list[tuple[date, int]]:
    """Number of free slots per customer-local date, inclusive range, at most 31 days."""
    validate_range(date_from, date_to)
    rules, time_offs, busy_ranges = list(rules), list(time_offs), list(busy_ranges)
    summary = []
    day = date_from
    while day <= date_to:
        slots = get_available_slots(
            service=service,
            provider=provider,
            date_local=day,
            now=now,
            settings=settings,
            rules=rules,
            time_offs=time_offs,
            busy_ranges=busy_ranges,
            tz=tz,
        )
        summary.append((day, len(slots)))
        day += timedelta(days=1)
    return summary
