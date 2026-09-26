from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.api.v1.views import accounts, availability, bookings, catalog, providers, scheduling

app_name = "v1"

router = SimpleRouter(trailing_slash=False)
router.register("services", catalog.ServiceViewSet, basename="service")
router.register("providers", providers.ProviderViewSet, basename="provider")
router.register("bookings", bookings.BookingViewSet, basename="booking")

urlpatterns = [
    path("auth/register", accounts.RegisterView.as_view(), name="auth-register"),
    path("auth/token", accounts.TokenObtainView.as_view(), name="auth-token"),
    path("auth/token/refresh", accounts.TokenRefreshRotateView.as_view(), name="auth-refresh"),
    path("auth/logout", accounts.LogoutView.as_view(), name="auth-logout"),
    path("me", accounts.MeView.as_view(), name="me"),
    path("settings", scheduling.SettingsView.as_view(), name="settings"),
    path("availability/slots", availability.SlotsView.as_view(), name="availability-slots"),
    path("availability/days", availability.DaysView.as_view(), name="availability-days"),
    *router.urls,
]
