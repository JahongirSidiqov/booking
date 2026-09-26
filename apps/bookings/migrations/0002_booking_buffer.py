"""Provider buffer time: bookings keep the provider busy until `blocked_until`.

Hand-written: existing rows need `blocked_until = end_at` (no buffer), which a single column
default cannot express, and the provider exclusion constraint must be rebuilt on the new bound.
"""

import django.contrib.postgres.constraints
import django.contrib.postgres.fields.ranges
from django.db import migrations, models

import apps.bookings.models


def fill_blocked_until(apps, schema_editor):
    Booking = apps.get_model("bookings", "Booking")
    Booking.objects.filter(blocked_until__isnull=True).update(blocked_until=models.F("end_at"))


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0001_initial"),
        ("catalog", "0002_service_buffer"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="buffer_minutes",
            field=models.PositiveSmallIntegerField(default=0, verbose_name="tanaffus (daqiqa)"),
        ),
        migrations.AddField(
            model_name="booking",
            name="blocked_until",
            field=models.DateTimeField(null=True, verbose_name="xodim band (tanaffus bilan)"),
        ),
        migrations.RunPython(fill_blocked_until, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="booking",
            name="blocked_until",
            field=models.DateTimeField(verbose_name="xodim band (tanaffus bilan)"),
        ),
        migrations.RemoveConstraint(
            model_name="booking",
            name="no_overlap_per_provider",
        ),
        migrations.AddConstraint(
            model_name="booking",
            constraint=models.CheckConstraint(
                condition=models.Q(("blocked_until__gte", models.F("end_at"))),
                name="booking_blocked_after_end",
            ),
        ),
        migrations.AddConstraint(
            model_name="booking",
            constraint=django.contrib.postgres.constraints.ExclusionConstraint(
                condition=models.Q(("status__in", ("pending", "confirmed"))),
                expressions=[
                    (models.F("provider"), "="),
                    (
                        apps.bookings.models.TsTzRange(
                            "start_at",
                            "blocked_until",
                            django.contrib.postgres.fields.ranges.RangeBoundary(),
                        ),
                        "&&",
                    ),
                ],
                name="no_overlap_per_provider",
            ),
        ),
    ]
