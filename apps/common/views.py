from django.http import JsonResponse
from django.views import defaults

from .exceptions import problem


def _is_api(request) -> bool:
    return request.path.startswith("/api/")


def not_found(request, exception=None):
    # Unknown URLs under /api/ never reach DRF; answer them in the same problem format.
    if _is_api(request):
        return JsonResponse(problem("NOT_FOUND", 404, "Bunday API manzili yoʻq."), status=404)
    return defaults.page_not_found(request, exception)


def server_error(request):
    if _is_api(request):
        return JsonResponse(
            problem("SERVER_ERROR", 500, "Kutilmagan xato yuz berdi. Biz allaqachon bilamiz."),
            status=500,
        )
    return defaults.server_error(request)
