import django.db.models.functions.math
import django.db.models.lookups
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="service",
            name="buffer_after_minutes",
            field=models.PositiveSmallIntegerField(default=0, verbose_name="tanaffus (daqiqa)"),
        ),
        migrations.AddConstraint(
            model_name="service",
            constraint=models.CheckConstraint(
                condition=models.Q(("buffer_after_minutes__lte", 120))
                & django.db.models.lookups.Exact(
                    django.db.models.functions.math.Mod(models.F("buffer_after_minutes"), 5), 0
                ),
                name="service_buffer_range_step",
            ),
        ),
    ]
