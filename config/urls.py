from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.common.views import healthz

urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path("django-admin/", admin.site.urls),
    path("api/v1/", include("apps.api.v1.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger"),
    path("", include("apps.web.urls")),
]

handler404 = "apps.common.views.not_found"
handler500 = "apps.common.views.server_error"
