"""Pure slot-engine tests: no database, `now` is always passed explicitly."""

from datetime import UTC, date, datetime, time, timedelta
from types import SimpleNamespace

import pytest

from apps.common.exceptions import DomainError
from apps.scheduling.slot_engine import (
    Rule,
    align_to_step,
    get_available_slots,
    get_day_summary,
    local_day_bounds,
    merge,
    slot_rejection,
    subtract,
)

THU = date(2026, 10, 1)  # Thursday, weekday 3
NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


def utc(*args):
    return datetime(*args, tzinfo=UTC)


def tashkent(h, m=0, day=THU):
    """Asia/Tashkent is UTC+5 all year (no DST)."""
    return datetime.combine(day, time(h, m), tzinfo=UTC) - timedelta(hours=5)


def make_settings(**overrides):
    values = {
        "timezone": "Asia/Tashkent",
        "slot_step_minutes": 15,
        "min_lead_time_minutes": 60,
        "max_advance_days": 30,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def slots_for(
    *,
    rules,
    duration=30,
    day=THU,
    now=NOW,
    time_offs=(),
    busy=(),
    tz=None,
    provider_tz=None,
    **settings,
):
    return get_available_slots(
        service=SimpleNamespace(duration_minutes=duration),
        provider=SimpleNamespace(timezone=provider_tz),
        date_local=day,
        now=now,
        settings=make_settings(**settings),
        rules=rules,
        time_offs=time_offs,
        busy_ranges=busy,
        tz=tz,
    )


def starts(slots):
    return [s.start_at for s in slots]


WORKDAY = [Rule(3, time(9), time(18))]


# --- windows ------------------------------------------------------------------------------


def test_single_window_generates_stepped_slots():
    slots = slots_for(rules=WORKDAY)
    assert slots[0].start_at == tashkent(9)
    assert slots[0].end_at == tashkent(9, 30)
    assert slots[1].start_at == tashkent(9, 15)
    assert slots[-1].start_at == tashkent(17, 30)
    assert len(slots) == 35  # 09:00 … 17:30 every 15 minutes


def test_no_rule_for_weekday_means_no_slots():
    assert slots_for(rules=[Rule(0, time(9), time(18))]) == []


def test_lunch_break_between_two_windows():
    got = starts(slots_for(rules=[Rule(3, time(9), time(13)), Rule(3, time(14), time(18))]))
    assert tashkent(12, 30) in got
    assert tashkent(12, 45) not in got  # would end 13:15, inside the break
    assert tashkent(14) in got


def test_edge_07_service_must_fit_before_window_end():
    got = starts(slots_for(rules=WORKDAY))
    assert tashkent(17, 30) in got
    assert tashkent(17, 45) not in got


def test_long_service_longer_than_window_has_no_slots():
    assert slots_for(rules=[Rule(3, time(9), time(10))], duration=90) == []


def test_overlapping_rules_are_merged_not_duplicated():
    got = starts(slots_for(rules=[Rule(3, time(9), time(12)), Rule(3, time(11), time(13))]))
    assert len(got) == len(set(got))
    assert got[-1] == tashkent(12, 30)


# --- subtraction --------------------------------------------------------------------------


def test_time_off_removes_overlapping_slots():
    got = starts(slots_for(rules=WORKDAY, time_offs=[(tashkent(12), tashkent(13))]))
    assert tashkent(11, 30) in got  # ends exactly at 12:00
    assert tashkent(11, 45) not in got
    assert tashkent(12, 30) not in got
    assert tashkent(13) in got


def test_time_off_covering_whole_day():
    assert slots_for(rules=WORKDAY, time_offs=[(tashkent(0), tashkent(23))]) == []


def test_busy_range_half_open_boundaries():
    got = starts(slots_for(rules=WORKDAY, busy=[(tashkent(10), tashkent(10, 30))]))
    assert tashkent(9, 30) in got  # 09:30–10:00 touches the booking, does not overlap
    assert tashkent(9, 45) not in got
    assert tashkent(10) not in got
    assert tashkent(10, 15) not in got
    assert tashkent(10, 30) in got  # 10:30 starts exactly when the booking ends


def test_edge_34_duration_45_step_15_next_slot_after_booking():
    got = starts(slots_for(rules=WORKDAY, duration=45, busy=[(tashkent(9), tashkent(9, 45))]))
    assert got[0] == tashkent(9, 45)


def test_duration_40_rounds_up_to_next_step_after_booking():
    got = starts(slots_for(rules=WORKDAY, duration=40, busy=[(tashkent(9), tashkent(9, 40))]))
    assert got[0] == tashkent(9, 45)


def test_overlapping_busy_ranges_and_time_offs_combined():
    got = starts(
        slots_for(
            rules=WORKDAY,
            time_offs=[(tashkent(9), tashkent(10))],
            busy=[(tashkent(9, 30), tashkent(11)), (tashkent(10, 30), tashkent(11, 30))],
        )
    )
    assert got[0] == tashkent(11, 30)


def test_subtract_and_merge_primitives():
    w = [(utc(2026, 10, 1, 4), utc(2026, 10, 1, 13))]
    assert subtract(w, []) == w
    assert subtract(w, [(utc(2026, 10, 1, 0), utc(2026, 10, 1, 23))]) == []
    assert subtract(w, [(utc(2026, 10, 1, 6), utc(2026, 10, 1, 7))]) == [
        (utc(2026, 10, 1, 4), utc(2026, 10, 1, 6)),
        (utc(2026, 10, 1, 7), utc(2026, 10, 1, 13)),
    ]
    assert merge(
        [(utc(2026, 1, 1, 1), utc(2026, 1, 1, 2)), (utc(2026, 1, 1, 2), utc(2026, 1, 1, 3))]
    ) == [(utc(2026, 1, 1, 1), utc(2026, 1, 1, 3))]
    assert merge([(utc(2026, 1, 1, 2), utc(2026, 1, 1, 2))]) == []


# --- step alignment -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("step", "expected"), [(5, (9, 10)), (15, (9, 15)), (30, (9, 30)), (60, (10, 0))]
)
def test_window_start_is_aligned_to_local_step_grid(step, expected):
    got = slots_for(rules=[Rule(3, time(9, 10), time(12))], slot_step_minutes=step)
    assert got[0].start_at == tashkent(*expected)


def test_alignment_uses_local_grid_in_quarter_hour_offset_zone():
    # Asia/Kathmandu is UTC+5:45; a UTC grid would produce 09:15/09:45 local.
    got = slots_for(
        rules=[Rule(3, time(9), time(10))],
        provider_tz="Asia/Kathmandu",
        slot_step_minutes=30,
    )
    assert starts(got) == [utc(2026, 10, 1, 3, 15), utc(2026, 10, 1, 3, 45)]


def test_align_to_step_keeps_already_aligned_instant():
    moment = tashkent(9, 30)
    assert align_to_step(moment, "Asia/Tashkent", 15) == moment


# --- time filters -------------------------------------------------------------------------


def test_edge_05_lead_time_hides_near_slots():
    now = tashkent(9, 10)  # lead 60 → earliest 10:10
    got = starts(slots_for(rules=WORKDAY, now=now))
    assert got[0] == tashkent(10, 15)


def test_edge_04_slot_starting_right_now_is_past():
    now = tashkent(11)
    got = starts(slots_for(rules=WORKDAY, now=now, min_lead_time_minutes=0))
    assert tashkent(11) not in got
    assert got[0] == tashkent(11, 15)


def test_past_day_has_no_slots():
    assert slots_for(rules=[Rule(4, time(9), time(18))], day=date(2026, 9, 25)) == []


def test_edge_06_beyond_max_advance_is_empty():
    # now + 30 days = 2026-10-26 12:00Z = 17:00 Tashkent; 2026-10-27 is out of range.
    tuesday = date(2026, 10, 27)
    assert slots_for(rules=[Rule(1, time(9), time(18))], day=tuesday) == []


def test_max_advance_cuts_the_last_day_inclusively():
    monday = date(2026, 10, 26)
    got = starts(slots_for(rules=[Rule(0, time(9), time(18))], day=monday))
    assert got[-1] == tashkent(17, day=monday)


# --- timezones ----------------------------------------------------------------------------


def test_edge_17_customer_in_other_timezone_sees_same_instants():
    in_tashkent = slots_for(rules=WORKDAY)
    in_dubai = slots_for(rules=WORKDAY, tz="Asia/Dubai")
    assert in_dubai == in_tashkent  # Dubai's 1 Oct covers the whole Tashkent workday


def test_edge_38_customer_date_maps_to_previous_provider_evening():
    # Provider (Tashkent) works Wednesday 30 Sep 19:00–23:00 = 14:00–18:00Z,
    # which is 23:00 Wed – 03:00 Thu in Tokyo (+9).
    wednesday_evening = [Rule(2, time(19), time(23))]
    tokyo_thursday = slots_for(rules=wednesday_evening, tz="Asia/Tokyo")
    assert tokyo_thursday[0].start_at == utc(2026, 9, 30, 15)  # Tokyo midnight
    assert tokyo_thursday[-1].start_at == utc(2026, 9, 30, 17, 30)
    assert len(tokyo_thursday) == 11
    # The same rule gives nothing on Thursday for a customer in the provider's zone.
    assert slots_for(rules=wednesday_evening) == []


def test_edge_18_dst_keeps_local_opening_time():
    # Europe/Berlin leaves summer time on Sunday 2026-10-25.
    rules = [Rule(6, time(9), time(12))]
    before = slots_for(
        rules=rules, day=date(2026, 10, 18), provider_tz="Europe/Berlin", max_advance_days=60
    )
    after = slots_for(
        rules=rules, day=date(2026, 10, 25), provider_tz="Europe/Berlin", max_advance_days=60
    )
    assert before[0].start_at == utc(2026, 10, 18, 7)  # 09:00 CEST (+2)
    assert after[0].start_at == utc(2026, 10, 25, 8)  # 09:00 CET (+1)
    assert len(before) == len(after)


def test_local_day_bounds_on_dst_day_is_25_hours():
    start, end = local_day_bounds(date(2026, 10, 25), "Europe/Berlin")
    assert end - start == timedelta(hours=25)


# --- day summary --------------------------------------------------------------------------


def summary(date_from, date_to, rules=WORKDAY, **kwargs):
    return get_day_summary(
        service=SimpleNamespace(duration_minutes=30),
        provider=SimpleNamespace(timezone=None),
        date_from=date_from,
        date_to=date_to,
        now=NOW,
        settings=make_settings(),
        rules=rules,
        **kwargs,
    )


def test_day_summary_counts_per_date():
    result = summary(date(2026, 9, 30), date(2026, 10, 2))
    assert result == [(date(2026, 9, 30), 0), (THU, 35), (date(2026, 10, 2), 0)]


def test_day_summary_applies_time_off():
    result = summary(THU, THU, time_offs=[(tashkent(9), tashkent(18))])
    assert result == [(THU, 0)]


def test_edge_27_range_over_31_days_rejected():
    with pytest.raises(DomainError) as exc:
        summary(date(2026, 10, 1), date(2026, 12, 29))
    assert (exc.value.code, exc.value.http_status) == ("RANGE_TOO_LARGE", 400)


def test_range_of_exactly_31_days_allowed():
    assert len(summary(date(2026, 10, 1), date(2026, 10, 31))) == 31


def test_reversed_range_rejected():
    with pytest.raises(DomainError) as exc:
        summary(date(2026, 10, 2), date(2026, 10, 1))
    assert exc.value.code == "VALIDATION_ERROR"


def test_blocks_outside_window_are_ignored():
    w = [(utc(2026, 10, 1, 4), utc(2026, 10, 1, 13))]
    blocks = [
        (utc(2026, 10, 1, 1), utc(2026, 10, 1, 2)),
        (utc(2026, 10, 1, 14), utc(2026, 10, 1, 15)),
    ]
    assert subtract(w, blocks) == w


def test_align_in_repeated_hour_after_dst_end_does_not_go_backwards():
    # New York falls back on 2026-11-01: 01:30 happens twice; 06:30Z is the second one (EST).
    second_0130 = utc(2026, 11, 1, 6, 30)
    assert align_to_step(second_0130, "America/New_York", 30) == second_0130


# --- slot_rejection (used by create_booking) ------------------------------------------------


def reject(start_at, *, now=NOW, busy=(), time_offs=(), rules=WORKDAY, duration=30):
    return slot_rejection(
        service=SimpleNamespace(duration_minutes=duration),
        provider=SimpleNamespace(timezone=None),
        start_at=start_at,
        now=now,
        settings=make_settings(),
        rules=rules,
        time_offs=time_offs,
        busy_ranges=busy,
    )


@pytest.mark.parametrize(
    ("start_at", "now", "expected"),
    [
        (tashkent(9), NOW, None),
        (utc(2026, 9, 26, 12), NOW, "IN_PAST"),
        (utc(2026, 9, 26, 11), NOW, "IN_PAST"),
        (tashkent(9, 30), tashkent(9), "LEAD_TIME"),
        (tashkent(9, day=date(2026, 10, 29)), NOW, "TOO_FAR_AHEAD"),
        (tashkent(10, 7), NOW, "STEP_MISALIGNED"),
        (tashkent(17, 45), NOW, "SLOT_UNAVAILABLE"),
        (tashkent(9, day=date(2026, 10, 2)), NOW, "SLOT_UNAVAILABLE"),
    ],
)
def test_slot_rejection_reasons(start_at, now, expected):
    assert reject(start_at, now=now) == expected


def test_slot_rejection_distinguishes_time_off_from_taken():
    assert reject(tashkent(9), time_offs=[(tashkent(9), tashkent(10))]) == "SLOT_UNAVAILABLE"
    assert reject(tashkent(9), busy=[(tashkent(9), tashkent(9, 30))]) == "SLOT_TAKEN"
    assert reject(tashkent(9, 30), busy=[(tashkent(9), tashkent(9, 30))]) is None


def test_slot_rejection_agrees_with_listing_for_every_candidate():
    """Every listed slot is bookable and every bookable grid point is listed."""
    busy = [(tashkent(11), tashkent(11, 45))]
    listed = {s.start_at for s in slots_for(rules=WORKDAY, busy=busy)}
    grid = [tashkent(8) + timedelta(minutes=15 * i) for i in range(48)]
    bookable = {t for t in grid if reject(t, busy=busy) is None}
    assert bookable == listed
