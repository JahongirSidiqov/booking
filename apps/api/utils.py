import uuid

from rest_framework.exceptions import NotFound, ValidationError


def uuid_or_404(value) -> uuid.UUID:
    # A malformed id in the URL is simply "no such object", not a 500 from the UUID cast.
    try:
        return uuid.UUID(str(value))
    except ValueError as exc:
        raise NotFound() from exc


def uuid_query_param(request, name: str) -> uuid.UUID | None:
    raw = request.query_params.get(name)
    if raw in (None, ""):
        return None
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise ValidationError({name: ["UUID koʻrinishida boʻlishi kerak."]}) from exc


def flag_query_param(request, name: str) -> bool:
    return request.query_params.get(name, "").lower() in {"1", "true", "yes"}
