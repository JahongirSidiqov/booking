from django.urls import path

from apps.api.v1.views import accounts

app_name = "v1"

urlpatterns = [
    path("auth/register", accounts.RegisterView.as_view(), name="auth-register"),
    path("auth/token", accounts.TokenObtainView.as_view(), name="auth-token"),
    path("auth/token/refresh", accounts.TokenRefreshRotateView.as_view(), name="auth-refresh"),
    path("auth/logout", accounts.LogoutView.as_view(), name="auth-logout"),
    path("me", accounts.MeView.as_view(), name="me"),
]
