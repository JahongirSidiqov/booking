from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.accounts.models import User
from apps.api.utils import uuid_or_404
from apps.api.v1.serializers.bookings import (
    BookingCreateSerializer,
    booking_payload,
    validate_idempotency_key,
)
from apps.api.v1.views.availability import resolve_tz
from apps.bookings import selectors, services
from apps.bookings.models import Booking
from apps.scheduling.models import BusinessSettings


class IsCustomer(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == User.Role.CUSTOMER)


class BookingCreateThrottle(UserRateThrottle):
    scope = "bookings_create"


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class BookingViewSet(viewsets.ViewSet):
    def get_permissions(self):
        if self.action == "create":
            return [IsCustomer()]
        return [IsAuthenticated()]

    def get_throttles(self):
        throttles = super().get_throttles()
        if self.action == "create":
            throttles.append(BookingCreateThrottle())
        return throttles

    def _render(self, booking: Booking, **kwargs) -> Response:
        body = booking_payload(
            booking, tz=resolve_tz(self.request, None), business=BusinessSettings.load()
        )
        return Response(body, **kwargs)

    def _visible(self, pk) -> Booking:
        booking = selectors.visible_booking(self.request.user, uuid_or_404(pk))
        if booking is None:
            raise NotFound()
        return booking

    def list(self, request):
        bookings = (
            selectors.visible_bookings(request.user)
            .prefetch_related("history__changed_by")
            .order_by("-start_at")
        )
        tz = resolve_tz(request, None)
        business = BusinessSettings.load()
        return Response([booking_payload(b, tz=tz, business=business) for b in bookings])

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
