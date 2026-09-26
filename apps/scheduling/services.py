from datetime import datetime, time
from itertools import pairwise

from django.db import transaction

from apps.common.exceptions import DomainError
from apps.providers.models import Provider

from .models import AvailabilityRule, BusinessSettings, TimeOff

SETTINGS_FIELDS = frozenset(
    {
        "name",
        "timezone",
        "currency",
        "slot_step_minutes",
        "min_lead_time_minutes",
        "max_advance_days",
        "cancellation_deadline_hours",
        "auto_confirm",
    }
)


def _lock_provider(provider: Provider) -> Provider:
    # Schedule edits and booking creation both lock the provider row, so a rule change can
    # never interleave with a booking being validated against the old rules.
    return Provider.objects.select_for_update().get(pk=provider.pk)


def _overlaps(rules: list[dict]) -> list[str]:
    problems = []
    labels = dict(AvailabilityRule.Weekday.choices)
    by_day: dict[int, list[tuple[time, time]]] = {}
    for rule in rules:
        by_day.setdefault(rule["weekday"], []).append((rule["start_time"], rule["end_time"]))
    for weekday, windows in sorted(by_day.items()):
        windows.sort()
        # Touching windows (09:00–13:00, 13:00–18:00) are fine: intervals are half-open.
        for (s1, e1), (s2, e2) in pairwise(windows):
            if s2 < e1:
                problems.append(
                    f"{labels[weekday]}: {s1:%H:%M}–{e1:%H:%M} va {s2:%H:%M}–{e2:%H:%M} kesishadi."
                )
    return problems


@transaction.atomic
def replace_availability(*, provider: Provider, rules: list[dict]) -> list[AvailabilityRule]:
    """Replace the provider's whole weekly schedule with `rules` (one PUT = one week)."""
    problems = _overlaps(rules)
    if problems:
        raise DomainError(
            "VALIDATION_ERROR", "Ish vaqti oraliqlari kesishmasin.", errors={"rules": problems}
        )
    provider = _lock_provider(provider)
    AvailabilityRule.objects.filter(provider=provider).delete()
    return AvailabilityRule.objects.bulk_create(
        [
            AvailabilityRule(
                provider=provider,
                weekday=r["weekday"],
                start_time=r["start_time"],
                end_time=r["end_time"],
            )
            for r in sorted(rules, key=lambda r: (r["weekday"], r["start_time"]))
        ]
    )


@transaction.atomic
def add_time_off(
    *, provider: Provider, start_at: datetime, end_at: datetime, reason: str = ""
) -> TimeOff:
    if start_at >= end_at:
        raise DomainError(
            "VALIDATION_ERROR",
            "Kiritilgan maʼlumotlarni tekshiring.",
            errors={"end_at": ["Tugash vaqti boshlanishdan keyin boʻlsin."]},
        )
    provider = _lock_provider(provider)
    return TimeOff.objects.create(
        provider=provider, start_at=start_at, end_at=end_at, reason=reason
    )


def delete_time_off(*, provider: Provider, time_off_id) -> None:
    deleted, _ = TimeOff.objects.filter(provider=provider, pk=time_off_id).delete()
    if not deleted:
        raise DomainError("NOT_FOUND", "Dam olish yozuvi topilmadi.", 404)


def update_settings(**data) -> BusinessSettings:
    obj = BusinessSettings.load()
    changed = [k for k in data if k in SETTINGS_FIELDS]
    for name in changed:
        setattr(obj, name, data[name])
    if changed:
        obj.save(update_fields=[*changed, "updated_at"])
    return obj
