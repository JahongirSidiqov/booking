from django.core.management.base import BaseCommand

from apps.bookings import services


class Command(BaseCommand):
    help = "Cancel pending bookings whose start time has passed (reason: expired)."

    def handle(self, *args, **options):
        count = services.expire_stale_bookings()
        self.stdout.write(f"expired: {count}")
