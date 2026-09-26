"""Demo data for "Navbat Barbershop": 3 providers, 5 services, weekly schedules, time off and
about 25 bookings in every status, past and upcoming.

Every booking goes through bookings.services (the same validation, locks and history as real
traffic). Past bookings are created by moving the clock back with unittest.mock, so their
history timestamps are believable too. Emails are suppressed while seeding.
"""

import random
from contextlib import contextmanager
from datetime import datetime, time, timedelta
from decimal import Decimal
from unittest import mock
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.test.utils import override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings import services as booking_services
from apps.bookings.models import Booking
from apps.catalog import services as catalog_services
from apps.catalog.models import Service
from apps.common.exceptions import DomainError
from apps.providers import services as provider_services
from apps.providers.models import Provider
from apps.scheduling import selectors as scheduling_selectors
from apps.scheduling import services as scheduling_services
from apps.scheduling.models import BusinessSettings

SERVICES = [
    # name, minutes, price, description, buffer after (cleanup) minutes
    ("Soch olish", 30, "60000", "Klassik yoki zamonaviy soch turmagi, yuvish bilan.", 0),
    ("Soqol oʻldirish", 20, "40000", "Ustara bilan, issiq sochiq bilan.", 0),
    ("Soch va soqol", 45, "90000", "Toʻliq parvarish: soch olish va soqol.", 10),
    ("Bolalar soch olishi", 30, "45000", "12 yoshgacha bolalar uchun.", 0),
    ("Yuz parvarishi", 40, "80000", "Tozalash, niqob va massaj.", 15),
]

# name, colour, bio, services (indexes), weekly windows {weekday: [(start, end), ...]}
PROVIDERS = [
    (
        "Sardor Rahimov",
        "#2563EB",
        "12 yil tajriba, klassik va fade",
        [0, 1, 2, 3],
        {d: [(time(9), time(13)), (time(14), time(18))] for d in range(6)},
    ),
    (
        "Jasur Toshmatov",
        "#16A34A",
        "Soqol va yuz parvarishi ustasi",
        [1, 2, 4],
        {d: [(time(10), time(19))] for d in range(1, 7)},
    ),
    (
        "Dilshod Qodirov",
        "#D97706",
        "Bolalar bilan ishlashni yaxshi koʻradi",
        [0, 3],
        {d: [(time(9), time(17))] for d in range(5)},
    ),
]

CUSTOMERS = [
    ("mijoz@navbat.uz", "Aziza Karimova", "+998901112233"),
    ("bekzod@navbat.uz", "Bekzod Aliyev", "+998931234567"),
    ("malika@navbat.uz", "Malika Yusupova", ""),
    ("timur@navbat.uz", "Timur Nazarov", "+998971002030"),
    ("nodira@navbat.uz", "Nodira Ergasheva", ""),
    ("xushnudbek@navbat.uz", "Xushnudbek Abdurahmonov Jumaniyazov", "+998909998877"),
]

ADMIN_EMAIL = "admin@navbat.uz"
PROVIDER_EMAIL = "sardor@navbat.uz"


@contextmanager
def clock(moment: datetime):
    """Pretend it is `moment`: auto_now fields and services both read timezone.now()."""
    with mock.patch("django.utils.timezone.now", return_value=moment):
        yield


class Command(BaseCommand):
    help = "Create demo data (admin, 3 providers, 5 services, schedules, ~25 bookings)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default=None,
            help="Password for every demo account (default: the DEMO_PASSWORD setting).",
        )

    def handle(self, *args, **options):
        if Service.objects.exists() or Provider.objects.exists() or Booking.objects.exists():
            # Plain ASCII: Windows consoles (cp1252) cannot print the Uzbek letters.
            raise CommandError(
                "Database is not empty. Demo data is only added to a clean database: "
                "run `python manage.py flush --no-input` first."
            )
        password = options["password"] or settings.DEMO_PASSWORD
        self.random = random.Random(2026)  # same demo every time
        with override_settings(EMAIL_BACKEND="django.core.mail.backends.dummy.EmailBackend"):
            with transaction.atomic():
                self._settings()
                users = self._users(password)
                services = self._services()
                providers = self._providers(services, users["provider"])
                self._time_off(providers[2])
            created = self._bookings(services, providers, users)
        self._report(password, created)

    # --- reference data --------------------------------------------------------------------

    def _settings(self):
        scheduling_services.update_settings(
            name="Navbat Barbershop", timezone="Asia/Tashkent", auto_confirm=False
        )

    def _users(self, password):
        admin = User.objects.create_superuser(
            email=ADMIN_EMAIL, password=password, full_name="Navbat Administrator"
        )
        provider = User.objects.create_user(
            email=PROVIDER_EMAIL,
            password=password,
            full_name="Sardor Rahimov",
            role=User.Role.PROVIDER,
        )
        customers = [
            User.objects.create_user(email=email, password=password, full_name=name, phone=phone)
            for email, name, phone in CUSTOMERS
        ]
        return {"admin": admin, "provider": provider, "customers": customers}

    def _services(self):
        return [
            catalog_services.create_service(
                name=name,
                duration_minutes=minutes,
                price=Decimal(price),
                description=description,
                buffer_after_minutes=buffer,
                sort_order=index,
            )
            for index, (name, minutes, price, description, buffer) in enumerate(SERVICES)
        ]

    def _providers(self, services, sardor_user):
        providers = []
        for index, (name, color, bio, service_idx, week) in enumerate(PROVIDERS):
            provider = provider_services.create_provider(
                name=name,
                color=color,
                bio=bio,
                user_id=sardor_user.pk if index == 0 else None,
                service_ids=[services[i].pk for i in service_idx],
            )
            scheduling_services.replace_availability(
                provider=provider,
                rules=[
                    {"weekday": day, "start_time": start, "end_time": end}
                    for day, windows in week.items()
                    for start, end in windows
                ],
            )
            providers.append(provider)
        return providers

    def _time_off(self, provider):
        tz = ZoneInfo(BusinessSettings.load().timezone)
        day = timezone.now().astimezone(tz).date() + timedelta(days=5)
        while day.weekday() >= 5:  # Dilshod works Mon–Fri
            day += timedelta(days=1)
        scheduling_services.add_time_off(
            provider=provider,
            start_at=datetime.combine(day, time(14), tzinfo=tz),
            end_at=datetime.combine(day, time(17), tzinfo=tz),
            reason="Shifokor qabuli",
        )

    # --- bookings --------------------------------------------------------------------------

    def _pick_slot(self, service, provider, day, now):
        tz = BusinessSettings.load().timezone
        slots = scheduling_selectors.day_slots(
            service=service, provider=provider, date_local=day, tz=tz, now=now
        )
        return self.random.choice(slots) if slots else None

    def _book(self, service, provider, customers, day, now, note=""):
        """Create one booking as a real customer would at `now`; returns it or None."""
        slot = self._pick_slot(service, provider, day, now)
        if slot is None:
            return None
        for customer in self.random.sample(customers, len(customers)):
            try:
                with clock(now):
                    return booking_services.create_booking(
                        customer=customer,
                        service_id=service.pk,
                        provider_id=provider.pk,
                        start_at=slot.start_at,
                        note=note,
                        now=now,
                    ).booking
            except DomainError as exc:
                if exc.code != "CUSTOMER_OVERLAP":
                    return None
        return None

    def _move(self, booking, to_status, actor, at, reason=""):
        with clock(at):
            booking_services.transition_booking(
                booking_id=booking.pk, to_status=to_status, actor=actor, reason=reason, now=at
            )

    def _offering(self, services, providers):
        pairs = [(s, p) for p in providers for s in p.services.all()]
        return lambda: self.random.choice(pairs)

    def _bookings(self, services, providers, users):
        tz = ZoneInfo(BusinessSettings.load().timezone)
        real_now = timezone.now()
        today = real_now.astimezone(tz).date()
        customers, admin = users["customers"], users["admin"]
        staff_for = {providers[0].pk: users["provider"]}
        pick = self._offering(services, providers)
        created = []

        # Past 12 days: mostly completed, some cancelled — booked two days ahead, like real life.
        for offset in range(12, 0, -1):
            day = today - timedelta(days=offset)
            booked_at = datetime.combine(day - timedelta(days=2), time(10), tzinfo=tz)
            service, provider = pick()
            booking = self._book(service, provider, customers, day, booked_at)
            if booking is None:
                continue
            staff = staff_for.get(provider.pk, admin)
            if offset % 5 == 0:
                self._move(
                    booking,
                    Booking.Status.CANCELLED,
                    booking.customer,
                    booked_at + timedelta(hours=3),
                    "Rejalar oʻzgardi",
                )
            else:
                self._move(booking, Booking.Status.CONFIRMED, staff, booked_at + timedelta(hours=1))
                self._move(
                    booking,
                    Booking.Status.COMPLETED,
                    staff,
                    booking.end_at + timedelta(minutes=5),
                )
            created.append(booking)

        # Next 7 days: pending, confirmed and a couple of cancellations, booked "an hour ago".
        booked_at = real_now - timedelta(hours=1)
        for offset in range(1, 8):
            day = today + timedelta(days=offset)
            for n in range(2):
                service, provider = pick()
                note = "Iltimos, qisqaroq" if (offset + n) % 4 == 0 else ""
                booking = self._book(service, provider, customers, day, booked_at, note)
                if booking is None:
                    continue
                staff = staff_for.get(provider.pk, admin)
                if (offset + n) % 3 == 0:
                    self._move(booking, Booking.Status.CONFIRMED, staff, booked_at)
                elif offset == 3 and n == 1:
                    self._move(booking, Booking.Status.CANCELLED, staff, booked_at, "Xodim kasal")
                created.append(booking)
        return created

    def _report(self, password, created):
        by_status = {s: 0 for s in Booking.Status.values}
        for booking in Booking.objects.filter(pk__in=[b.pk for b in created]):
            by_status[booking.status] += 1
        # ASCII only: this is read in developer terminals, some of which are still cp1252.
        self.stdout.write(self.style.SUCCESS(f"Demo data ready: {len(created)} bookings"))
        for status, count in by_status.items():
            self.stdout.write(f"  {status}: {count}")
        self.stdout.write("Logins (same password for all):")
        self.stdout.write(f"  admin:    {ADMIN_EMAIL}")
        self.stdout.write(f"  provider: {PROVIDER_EMAIL}")
        self.stdout.write(f"  customer: {CUSTOMERS[0][0]}")
        self.stdout.write(f"  password: {password}")
