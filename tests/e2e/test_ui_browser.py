"""Real-browser checks (TASK 10.6): layout at 360px/1440px and a keyboard-only booking.

Needs Playwright + Chromium (`pip install playwright; python -m playwright install chromium`).
Without them the module is skipped, so the default CI run stays browser-free.
Set NAVBAT_SCREENSHOTS=<dir> to keep full-page screenshots for visual review.
"""

import os
from datetime import time
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

from apps.accounts.models import User  # noqa: E402
from tests.factories import (  # noqa: E402
    DEFAULT_PASSWORD,
    AvailabilityRuleFactory,
    ProviderFactory,
    ServiceFactory,
    UserFactory,
)

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]

WIDTHS = {"mobile": 360, "desktop": 1440}
SHOTS = os.environ.get("NAVBAT_SCREENSHOTS")


@pytest.fixture(scope="module")
def _allow_sync_orm_next_to_playwright():
    # Playwright's sync API keeps an event loop running in this thread for the browser's whole
    # life, and Django then refuses ORM calls (test data, DB flush at teardown). Those calls
    # are ordinary synchronous code, so the guard is lifted exactly while the browser lives.
    previous = os.environ.get("DJANGO_ALLOW_ASYNC_UNSAFE")
    os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
    yield
    if previous is None:
        os.environ.pop("DJANGO_ALLOW_ASYNC_UNSAFE", None)
    else:
        os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = previous


@pytest.fixture
def scenario():
    service = ServiceFactory(name="Soch olish", slug="soch-olish", duration_minutes=30)
    provider = ProviderFactory(
        name="Xushnudbek Abdurahmonov Jumaniyazov", bio="12 yil tajriba", with_services=[service]
    )
    for weekday in range(7):  # real clock in the live server: every day must have slots
        AvailabilityRuleFactory(
            provider=provider, weekday=weekday, start_time=time(8), end_time=time(21)
        )
    customer = UserFactory(role=User.Role.CUSTOMER, email="mijoz@example.com")
    return service, provider, customer


@pytest.fixture(scope="module")
def browser(_allow_sync_orm_next_to_playwright):
    with sync_api.sync_playwright() as p:
        # Full Chromium in headless mode; the separate headless-shell build is not required.
        instance = p.chromium.launch(channel="chromium")
        yield instance
        instance.close()


def shot(page, name):
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"), full_page=True)


def assert_no_horizontal_scroll(page, label):
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 0, f"{label}: page is {overflow}px wider than the viewport"


def login(page, base, user, landing="/"):
    page.goto(f"{base}/login/")
    page.fill("#id_username", user.email)
    page.fill("#id_password", DEFAULT_PASSWORD)
    page.click("main button[type=submit]")
    page.wait_for_url(f"{base}{landing}")


@pytest.mark.parametrize("device", WIDTHS)
def test_pages_fit_the_viewport(browser, live_server, scenario, device):
    service, provider, customer = scenario
    page = browser.new_page(viewport={"width": WIDTHS[device], "height": 800})
    base = live_server.url
    login(page, base, customer)
    pages = {
        "home": "/",
        "step1": f"/book/{service.slug}/",
        "step2": f"/book/{service.slug}/?provider={provider.pk}",
        "bookings": "/bookings/",
        "profile": "/profile/",
    }
    for name, path in pages.items():
        page.goto(base + path)
        assert_no_horizontal_scroll(page, f"{name}@{device}")
        shot(page, f"{device}-{name}")
    page.close()


def focus_next(page, selector, limit=80):
    """Press Tab until the focused element matches `selector` (fails if it never does)."""
    for _ in range(limit):
        page.keyboard.press("Tab")
        if page.evaluate("s => document.activeElement.matches(s)", selector):
            return
    raise AssertionError(f"Tab never reached {selector}")


def test_keyboard_only_booking(browser, live_server, scenario):
    service, _provider, customer = scenario
    page = browser.new_page(viewport={"width": 360, "height": 800})
    base = live_server.url
    login(page, base, customer)

    page.goto(f"{base}/book/{service.slug}/")
    focus_next(page, "input[name=provider]")
    page.keyboard.press("Space")
    focus_next(page, "button[type=submit]")
    page.keyboard.press("Enter")
    page.wait_for_url("**provider=*")

    focus_next(page, "input[name=start]")
    page.keyboard.press("Space")
    shot(page, "mobile-step2-selected")
    focus_next(page, "button[type=submit]")
    assert page.evaluate("() => !document.activeElement.disabled")
    page.keyboard.press("Enter")
    page.wait_for_url("**start=*")
    shot(page, "mobile-step3")

    focus_next(page, "button[type=submit]")
    page.keyboard.press("Enter")
    page.wait_for_url("**/done/**")
    assert "Bron qabul qilindi" in page.content()
    shot(page, "mobile-step4")
    page.close()


def test_htmx_day_switch_keeps_page_and_updates_url(browser, live_server, scenario):
    service, provider, _customer = scenario
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(f"{live_server.url}/book/{service.slug}/?provider={provider.pk}")
    page.evaluate("() => { window.__marker = 'same-page'; }")
    days = page.locator("a.day")
    days.nth(2).click()
    page.wait_for_function("() => location.search.includes('date=')")
    assert page.evaluate("() => window.__marker") == "same-page"  # swapped, not reloaded
    assert page.locator("a.day").nth(2).get_attribute("aria-current") == "date"
    page.close()


# --- dashboard --------------------------------------------------------------------------------


@pytest.fixture
def admin_scenario(scenario):
    from datetime import timedelta

    from django.utils import timezone as dj_timezone

    from tests.factories import BookingFactory

    service, provider, customer = scenario
    admin = UserFactory(role=User.Role.ADMIN, email="admin@example.com", full_name="Admin Adminov")
    start = dj_timezone.now().replace(minute=0, second=0, microsecond=0) + timedelta(hours=2)
    booking = BookingFactory(customer=customer, provider=provider, service=service, start_at=start)
    return service, provider, admin, booking


@pytest.mark.parametrize("device", WIDTHS)
def test_dashboard_pages_fit_the_viewport(browser, live_server, admin_scenario, device):
    _service, provider, admin, booking = admin_scenario
    page = browser.new_page(viewport={"width": WIDTHS[device], "height": 800})
    base = live_server.url
    login(page, base, admin, landing="/dashboard/")
    pages = {
        "dash-today": "/dashboard/",
        "dash-bookings": "/dashboard/bookings/",
        "dash-booking": f"/dashboard/bookings/{booking.pk}/",
        "dash-services": "/dashboard/services/",
        "dash-service-form": "/dashboard/services/?new=1",
        "dash-providers": "/dashboard/providers/",
        "dash-availability": f"/dashboard/providers/{provider.pk}/availability/",
        "dash-settings": "/dashboard/settings/",
    }
    for name, path in pages.items():
        page.goto(base + path)
        assert_no_horizontal_scroll(page, f"{name}@{device}")
        shot(page, f"{device}-{name}")
    page.close()


def test_mobile_drawer_and_modal_are_keyboard_operable(browser, live_server, admin_scenario):
    _service, _provider, admin, booking = admin_scenario
    page = browser.new_page(viewport={"width": 360, "height": 800})
    base = live_server.url
    login(page, base, admin, landing="/dashboard/")

    nav = page.locator("#dashboard-nav")
    assert not nav.is_visible() or nav.bounding_box()["x"] < 0  # off-canvas at first
    page.get_by_role("button", name="Menyu", exact=True).click()
    page.wait_for_timeout(350)
    assert nav.bounding_box()["x"] >= 0
    page.keyboard.press("Escape")
    page.wait_for_timeout(350)
    assert nav.bounding_box()["x"] < 0

    page.goto(f"{base}/dashboard/bookings/{booking.pk}/")
    page.get_by_role("button", name="Bronni bekor qilish").click()
    dialog = page.locator("#cancel-dialog")
    assert dialog.evaluate("d => d.open && d.matches(':modal')")
    page.keyboard.press("Escape")
    assert dialog.evaluate("d => !d.open")
    page.close()


def test_device_timezone_banner_switches_display(browser, live_server, scenario):
    """A visitor whose device is in Dubai sees the banner and one click switches the page."""
    context = browser.new_context(viewport={"width": 360, "height": 800}, timezone_id="Asia/Dubai")
    page = context.new_page()
    page.goto(f"{live_server.url}/")
    banner_button = page.get_by_role("button", name="Qurilma zonasiga oʻtish")
    assert banner_button.is_visible()
    assert "Vaqt zonasi: Asia/Tashkent" in page.content()
    assert_no_horizontal_scroll(page, "banner@mobile")
    shot(page, "mobile-timezone-banner")

    banner_button.click()
    page.wait_for_load_state("networkidle")
    assert "Vaqt zonasi: Asia/Dubai" in page.content()
    assert not page.get_by_role("button", name="Qurilma zonasiga oʻtish").is_visible()
    context.close()
