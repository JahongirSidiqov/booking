from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.api.v1.views import accounts, catalog, providers

app_name = "v1"

router = SimpleRouter(trailing_slash=False)
router.register("services", catalog.ServiceViewSet, basename="service")
router.register("providers", providers.ProviderViewSet, basename="provider")

urlpatterns = [
    path("auth/register", accounts.RegisterView.as_view(), name="auth-register"),
    path("auth/token", accounts.TokenObtainView.as_view(), name="auth-token"),
    path("auth/token/refresh", accounts.TokenRefreshRotateView.as_view(), name="auth-refresh"),
    path("auth/logout", accounts.LogoutView.as_view(), name="auth-logout"),
    path("me", accounts.MeView.as_view(), name="me"),
    *router.urls,
]
