from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.accounts.models import User
from apps.api.pagination import PagePagination
from apps.api.schema import UUID_PATH, problems
from apps.api.utils import uuid_or_404
from apps.api.v1.serializers.bookings import (
    BookingCreateSerializer,
    BookingFilterSerializer,
    BookingSerializer,
    ReasonSerializer,
    validate_idempotency_key,
)
from apps.api.v1.views.availability import resolve_tz
from apps.bookings import ical, selectors, services
from apps.bookings.models import Booking
from apps.scheduling.models import BusinessSettings
from apps.scheduling.slot_engine import local_day_bounds


class IsCustomer(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == User.Role.CUSTOMER)


class BookingCreateThrottle(UserRateThrottle):
    scope = "bookings_create"


TRANSITION_ERRORS = problems(
    s401="AUTH_REQUIRED",
    s403="FORBIDDEN (bu rol bu oʻtishni bajara olmaydi)",
    s404="NOT_FOUND (bron yoʻq yoki sizga koʻrinmaydi)",
    s409="INVALID_TRANSITION",
)


def _transition_schema(summary: str, description: str, extra_errors=None):
    return extend_schema(
        summary=summary,
        description=description,
        parameters=[UUID_PATH],
        request=ReasonSerializer,
        responses={200: BookingSerializer, **TRANSITION_ERRORS, **(extra_errors or {})},
    )


@extend_schema_view(
    list=extend_schema(
        summary="Bronlar roʻyxati",
        description="Mijoz — oʻz bronlari, xodim — oʻziga yozilganlar, admin — hammasi. "
        "`from`/`to` — `tz` zonasidagi kunlar (inklyuziv).",
        parameters=[BookingFilterSerializer],
        responses={200: BookingSerializer(many=True), **problems(s401="AUTH_REQUIRED")},
    ),
    retrieve=extend_schema(
        summary="Bron tafsiloti (status tarixi bilan)",
        parameters=[UUID_PATH],
        responses={200: BookingSerializer, **problems(s401="AUTH_REQUIRED", s404="NOT_FOUND")},
    ),
    create=extend_schema(
        summary="Bron yaratish (mijoz)",
        description="Double booking DB darajasida taqiqlangan (ADR-003). `Idempotency-Key` bilan "
        "takroriy soʻrov oʻsha bronni `200` + `Idempotent-Replayed: true` bilan qaytaradi.",
        parameters=[
            OpenApiParameter(
                "Idempotency-Key",
                OpenApiTypes.STR,
                OpenApiParameter.HEADER,
                description="1–64 belgi; tavsiya: UUID.",
            )
        ],
        request=BookingCreateSerializer,
        responses={
            201: BookingSerializer,
            200: BookingSerializer,
            **problems(
                s401="AUTH_REQUIRED",
                s403="FORBIDDEN (faqat mijoz)",
                s404="NOT_FOUND",
                s409="SLOT_TAKEN, CUSTOMER_OVERLAP, IDEMPOTENCY_MISMATCH",
                s422="VALIDATION_ERROR, IN_PAST, LEAD_TIME, TOO_FAR_AHEAD, STEP_MISALIGNED, "
                "SLOT_UNAVAILABLE, PROVIDER_NOT_OFFERING_SERVICE, INACTIVE_RESOURCE",
                s429="THROTTLED (10/daq)",
                s503="SERVICE_UNAVAILABLE",
            ),
        },
    ),
    confirm=_transition_schema(
        "Tasdiqlash (xodim/admin)", "`pending → confirmed`, faqat uchrashuv boshlanmasdan."
    ),
    cancel=_transition_schema(
        "Bekor qilish",
        "Mijoz — `can_cancel_until` gacha; xodim/admin — istalgan vaqtda, `reason` majburiy.",
        problems(s422="CANCELLATION_DEADLINE_PASSED, VALIDATION_ERROR"),
    ),
    ical=extend_schema(
        summary="Bronni kalendarga eksport qilish (.ics)",
        description="Faqat bron egasi (mijoz) uchun; boshqalarga 404. Bekor qilingan bron "
        "`STATUS:CANCELLED` bilan qaytadi, shunda kalendar voqeani oʻchiradi.",
        parameters=[UUID_PATH],
        responses={
            (200, "text/calendar"): OpenApiTypes.STR,
            **problems(s401="AUTH_REQUIRED", s404="NOT_FOUND"),
        },
    ),
    complete=_transition_schema(
        "Bajarildi deb belgilash (xodim/admin)", "`confirmed → completed`, boshlanganidan keyin."
    ),
)
@extend_schema(tags=["bookings"])
class BookingViewSet(viewsets.ViewSet):
    pagination_class = PagePagination

    def get_permissions(self):
        if self.action == "create":
            return [IsCustomer()]
        return [IsAuthenticated()]

    def get_throttles(self):
        throttles = super().get_throttles()
        if self.action == "create":
            throttles.append(BookingCreateThrottle())
        return throttles

    def _context(self, tz: str | None = None) -> dict:
        return {"tz": resolve_tz(self.request, tz), "business": BusinessSettings.load()}

    def _render(self, booking: Booking, **kwargs) -> Response:
        return Response(BookingSerializer(booking, context=self._context()).data, **kwargs)

    def _visible(self, pk) -> Booking:
        booking = selectors.visible_booking(self.request.user, uuid_or_404(pk))
        if booking is None:
            raise NotFound()
        return booking

    def list(self, request):
        query = BookingFilterSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        context = self._context(params.get("tz"))
        # Dates are calendar days in the viewer's timezone, like everywhere else in the API.
        starts_from = (
            local_day_bounds(params["from"], context["tz"])[0] if "from" in params else None
        )
        starts_before = local_day_bounds(params["to"], context["tz"])[1] if "to" in params else None
        bookings = selectors.filter_bookings(
            selectors.visible_bookings(request.user).prefetch_related("history__changed_by"),
            statuses=params.get("status"),
            provider_id=params.get("provider"),
            service_id=params.get("service"),
            starts_from=starts_from,
            starts_before=starts_before,
            upcoming_after=timezone.now() if params["upcoming"] else None,
        )
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(bookings, request, view=self)
        return paginator.get_paginated_response(
            BookingSerializer(page, many=True, context=context).data
        )

    def retrieve(self, request, pk=None):
        return self._render(self._visible(pk))

    def create(self, request):
        serializer = BookingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        key = validate_idempotency_key(request.headers.get("Idempotency-Key"))
        data = serializer.validated_data
        result = services.create_booking(
            customer=request.user,
            service_id=data["service_id"],
            provider_id=data["provider_id"],
            start_at=data["start_at"],
            note=data["note"],
            idempotency_key=key,
        )
        booking = selectors.booking_with_history(pk=result.booking.pk)
        if result.replayed:
            return self._render(
                booking, status=status.HTTP_200_OK, headers={"Idempotent-Replayed": "true"}
            )
        return self._render(booking, status=status.HTTP_201_CREATED)

    def _transition(self, request, pk, to_status):
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = services.transition_booking(
            booking_id=uuid_or_404(pk),
            to_status=to_status,
            actor=request.user,
            reason=serializer.validated_data["reason"],
        )
        return self._render(selectors.booking_with_history(pk=booking.pk))

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        return self._transition(request, pk, Booking.Status.CONFIRMED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._transition(request, pk, Booking.Status.CANCELLED)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        return self._transition(request, pk, Booking.Status.COMPLETED)

    @action(detail=True, methods=["get"])
    def ical(self, request, pk=None):
        booking = self._visible(pk)
        if booking.customer_id != request.user.pk:
            raise NotFound()
        filename, body = ical.calendar_file(booking)
        response = HttpResponse(body, content_type="text/calendar; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
