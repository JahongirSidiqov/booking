from django.utils import timezone

from apps.scheduling.models import BusinessSettings

SKIP_PREFIXES = ("/api/", "/healthz")


class DisplayTimezoneMiddleware:
    """Pages render dates in the viewer's timezone (profile, else the business zone).

    Deliberately skipped for /api/: DRF would otherwise serialise datetimes with the viewer's
    offset instead of UTC 'Z', and the API contract is UTC out (ADR-009). Skipped for
    /healthz too: it must answer 503 when the database is down, not crash on the settings
    lookup below before the health view even runs.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(SKIP_PREFIXES):
            return self.get_response(request)
        user = getattr(request, "user", None)
        tz = user.timezone if user is not None and user.is_authenticated else None
        request.display_tz = tz or BusinessSettings.load().timezone
        timezone.activate(request.display_tz)
        try:
            return self.get_response(request)
        finally:
            timezone.deactivate()
