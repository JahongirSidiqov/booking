from functools import lru_cache
from pathlib import Path

from django import template
from django.conf import settings
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.web import text

register = template.Library()

ICON_DIR = Path(settings.BASE_DIR) / "templates" / "icons"

STATUS_BADGES = {
    "pending": ("Kutilmoqda", "badge-pending", "clock"),
    "confirmed": ("Tasdiqlangan", "badge-confirmed", "circle-check"),
    "completed": ("Bajarilgan", "badge-completed", "check-check"),
    "cancelled": ("Bekor qilingan", "badge-cancelled", "circle-x"),
}


@lru_cache(maxsize=64)
def _icon_svg(name: str) -> str:
    raw = (ICON_DIR / f"{name}.svg").read_text(encoding="utf-8")
    # Keep only the shapes: the file starts with a licence comment and an <svg> tag whose
    # size/class attributes the tag below replaces.
    open_tag = raw.index("<svg")
    body = raw[raw.index(">", open_tag) + 1 : raw.rindex("</svg>")]
    return body.strip()


@register.simple_tag
def icon(name: str, size: int = 20, css: str = "", label: str = ""):
    """Inline Lucide icon. Decorative by default; pass label= for a meaningful one."""
    a11y = format_html('role="img" aria-label="{}"', label) if label else 'aria-hidden="true"'
    return format_html(
        '<svg xmlns="http://www.w3.org/2000/svg" width="{0}" height="{0}" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round" class="shrink-0 {1}" {2} focusable="false">{3}</svg>',
        size,
        css,
        mark_safe(a11y),
        mark_safe(_icon_svg(name)),
    )


@register.inclusion_tag("components/badge.html")
def status_badge(status: str):
    label, css, icon_name = STATUS_BADGES[status]
    return {"label": label, "css": css, "icon_name": icon_name}


@register.filter
def money(amount, currency="UZS"):
    return text.money(amount, currency)


@register.filter
def duration(minutes):
    return text.duration(int(minutes))


@register.filter
def local_time(moment, tz):
    return text.local(moment, tz).strftime("%H:%M")


@register.filter
def local_short_day(moment, tz):
    return text.short_day(text.local(moment, tz).date())


@register.filter
def local_long_day(moment, tz):
    return text.long_day(text.local(moment, tz).date())


@register.filter
def short_day(day):
    return text.short_day(day)


@register.filter
def initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


ROLE_LABELS = {
    "customer": "Mijoz",
    "provider": "Xodim",
    "admin": "Administrator",
    "system": "Tizim",
}


@register.filter
def actor_label(entry) -> str:
    return ROLE_LABELS[entry.changed_by.role] if entry.changed_by else ROLE_LABELS["system"]


@register.filter
def status_label(status: str) -> str:
    return STATUS_BADGES[status][0]
