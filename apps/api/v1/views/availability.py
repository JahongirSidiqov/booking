from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.schema import problems
from apps.api.v1.serializers.availability import (
    DaysQuerySerializer,
    DaysResponseSerializer,
    SlotsQuerySerializer,
    SlotsResponseSerializer,
)
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


PAIR_ERRORS = problems(
    s404="NOT_FOUND (xizmat yoki xodim)",
    s422="VALIDATION_ERROR, INACTIVE_RESOURCE, PROVIDER_NOT_OFFERING_SERVICE",
)


class SlotsView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["availability"],
        summary="Bir kunning boʻsh slotlari",
        parameters=[SlotsQuerySerializer],
        responses={200: SlotsResponseSerializer, **PAIR_ERRORS},
    )
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
        data = {
            "date": params["date"],
            "timezone": tz,
            "service": service,
            "provider": provider,
            "slots": slots,
        }
        return Response(SlotsResponseSerializer(data, context={"tz": tz}).data)


class DaysView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["availability"],
        summary="Kunlar boʻyicha boʻsh slotlar soni (sana chizigʻi uchun)",
        parameters=[DaysQuerySerializer],
        responses={
            200: DaysResponseSerializer,
            **problems(s400="RANGE_TOO_LARGE (31 kundan koʻp)"),
            **PAIR_ERRORS,
        },
    )
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
        data = {
            "date_from": params["from"],
            "date_to": params["to"],
            "timezone": tz,
            "service": service,
            "provider": provider,
            "days": [{"date": d, "available": n} for d, n in summary],
        }
        return Response(DaysResponseSerializer(data).data)
