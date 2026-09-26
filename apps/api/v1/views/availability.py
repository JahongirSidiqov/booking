from zoneinfo import ZoneInfo

from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.v1.serializers.availability import DaysQuerySerializer, SlotsQuerySerializer
from apps.scheduling import selectors
from apps.scheduling.models import BusinessSettings


def resolve_tz(request, explicit: str | None) -> str:
    """Explicit ?tz= wins, then the logged-in user's profile, then the business timezone."""
    if explicit:
        return explicit
    user = request.user
    if user and user.is_authenticated and user.timezone:
        return user.timezone
    return BusinessSettings.load().timezone


def _service_ref(service):
    return {
        "id": str(service.pk),
        "name": service.name,
        "duration_minutes": service.duration_minutes,
        "price": f"{service.price:.2f}",
    }


def _utc_z(moment) -> str:
    return moment.isoformat().replace("+00:00", "Z")


class SlotsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        query = SlotsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        tz = resolve_tz(request, params.get("tz"))
        service, provider = selectors.bookable_pair(
            service_id=params["service"], provider_id=params["provider"]
        )
        slots = selectors.day_slots(
            service=service,
            provider=provider,
            date_local=params["date"],
            tz=tz,
            now=timezone.now(),
        )
        zone = ZoneInfo(tz)
        return Response(
            {
                "date": params["date"].isoformat(),
                "timezone": tz,
                "service": _service_ref(service),
                "provider": {"id": str(provider.pk), "name": provider.name},
                "slots": [
                    {
                        "start_at": _utc_z(s.start_at),
                        "end_at": _utc_z(s.end_at),
                        "start_local": s.start_at.astimezone(zone).strftime("%H:%M"),
                        "end_local": s.end_at.astimezone(zone).strftime("%H:%M"),
                    }
                    for s in slots
                ],
            }
        )


class DaysView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        query = DaysQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        tz = resolve_tz(request, params.get("tz"))
        service, provider = selectors.bookable_pair(
            service_id=params["service"], provider_id=params["provider"]
        )
        summary = selectors.days_summary(
            service=service,
            provider=provider,
            date_from=params["from"],
            date_to=params["to"],
            tz=tz,
            now=timezone.now(),
        )
        return Response(
            {
                "from": params["from"].isoformat(),
                "to": params["to"].isoformat(),
                "timezone": tz,
                "service": _service_ref(service),
                "provider": {"id": str(provider.pk), "name": provider.name},
                "days": [{"date": d.isoformat(), "available": n} for d, n in summary],
            }
        )
