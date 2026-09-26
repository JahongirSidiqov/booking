from apps.scheduling.models import BusinessSettings


def site(request):
    business = BusinessSettings.load()
    return {
        "business": business,
        "display_tz": getattr(request, "display_tz", business.timezone),
    }
