"""OpenAPI helpers shared by the v1 views."""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse
from rest_framework import serializers


class ProblemSerializer(serializers.Serializer):
    """Error body produced by apps.common.exceptions.problem_exception_handler."""

    type = serializers.URLField(help_text="https://navbat.uz/errors/<code>")
    title = serializers.CharField()
    status = serializers.IntegerField()
    code = serializers.CharField(help_text="Mashina oʻqiydigan kod, masalan SLOT_TAKEN.")
    detail = serializers.CharField(help_text="Foydalanuvchiga koʻrsatiladigan matn.")
    errors = serializers.DictField(
        child=serializers.ListField(child=serializers.CharField()),
        required=False,
        help_text="Faqat 422 VALIDATION_ERROR: maydon → xabarlar.",
    )


UUID_PATH = OpenApiParameter("id", OpenApiTypes.UUID, OpenApiParameter.PATH)
TIME_OFF_PATH = OpenApiParameter("time_off_id", OpenApiTypes.UUID, OpenApiParameter.PATH)

_STATUS_TEXT = {
    400: "Notoʻgʻri soʻrov",
    401: "Avtorizatsiya kerak",
    403: "Ruxsat yoʻq",
    404: "Topilmadi",
    409: "Toʻqnashuv",
    422: "Validatsiya yoki biznes qoidasi xatosi",
    429: "Soʻrovlar juda koʻp",
    503: "Maʼlumotlar bazasi vaqtincha ishlamayapti",
}


def problems(**codes: str) -> dict[int, OpenApiResponse]:
    """problems(s409="SLOT_TAKEN, CUSTOMER_OVERLAP", s422="...") → documented error responses."""
    responses = {}
    for key, codes_text in codes.items():
        status = int(key.lstrip("s"))
        responses[status] = OpenApiResponse(
            ProblemSerializer, description=f"{_STATUS_TEXT.get(status, '')}: {codes_text}"
        )
    return responses
