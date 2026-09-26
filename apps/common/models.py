import uuid

from django.db import models


class BaseModel(models.Model):
    # UUID keys keep ids non-sequential, so URLs don't reveal how many bookings exist.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
