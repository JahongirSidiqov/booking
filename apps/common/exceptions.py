import logging

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.db import IntegrityError, InterfaceError, OperationalError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response

logger = logging.getLogger(__name__)

ERROR_TYPE_BASE = "https://navbat.uz/errors/"

TITLES = {
    "VALIDATION_ERROR": "Maʼlumotlarda xato bor",
    "AUTH_REQUIRED": "Avtorizatsiya talab qilinadi",
    "FORBIDDEN": "Ruxsat yoʻq",
    "NOT_FOUND": "Topilmadi",
    "METHOD_NOT_ALLOWED": "Bu usulga ruxsat yoʻq",
    "BAD_REQUEST": "Notoʻgʻri soʻrov",
    "UNSUPPORTED_MEDIA_TYPE": "Qoʻllab-quvvatlanmaydigan format",
    "THROTTLED": "Soʻrovlar juda koʻp",
    "SERVER_ERROR": "Server xatosi",
    "SERVICE_UNAVAILABLE": "Xizmat vaqtincha ishlamayapti",
    "SLOT_TAKEN": "Bu vaqt band",
    "CUSTOMER_OVERLAP": "Vaqtingiz band",
}

# Database constraints whose violation is a normal business outcome, not a bug.
CONSTRAINT_ERRORS = {
    "no_overlap_per_provider": (
        "SLOT_TAKEN",
        "Tanlangan vaqt boshqa mijoz tomonidan band qilindi. Boshqa vaqtni tanlang.",
    ),
    "no_overlap_per_customer": ("CUSTOMER_OVERLAP", "Sizda shu vaqtga boshqa bron bor."),
}


def constraint_name(exc: IntegrityError) -> str | None:
    diag = getattr(exc.__cause__, "diag", None)
    return getattr(diag, "constraint_name", None)


def _database_error(exc) -> Response | None:
    if isinstance(exc, IntegrityError):
        known = CONSTRAINT_ERRORS.get(constraint_name(exc))
        if known is None:
            return None
        # Any write path that skipped the service checks still ends in the same 409.
        code, detail = known
        return Response(problem(code, 409, detail), status=409)
    if isinstance(exc, OperationalError | InterfaceError):
        # The transaction was rolled back and on_commit hooks never ran: nothing was saved.
        logger.error("Database unavailable: %s", exc)
        body = problem(
            "SERVICE_UNAVAILABLE",
            503,
            "Maʼlumotlar bazasi bilan aloqa uzildi. Hech narsa saqlanmadi, qayta urinib koʻring.",
        )
        return Response(body, status=503, headers={"Retry-After": "5"})
    return None


class DomainError(Exception):
    """Business-rule violation raised by the service layer; API and UI render it identically."""

    def __init__(
        self,
        code: str,
        message: str,
        status: int = status.HTTP_422_UNPROCESSABLE_ENTITY,
        *,
        title: str | None = None,
        errors: dict | None = None,
        extra: dict | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = status
        self.title = title or TITLES.get(code, message)
        self.errors = errors
        self.extra = extra or {}


def problem(
    code: str,
    status_code: int,
    detail: str,
    *,
    title: str | None = None,
    errors: dict | None = None,
    extra: dict | None = None,
) -> dict:
    body = {
        "type": ERROR_TYPE_BASE + code.lower().replace("_", "-"),
        "title": title or TITLES.get(code, detail),
        "status": status_code,
        "code": code,
        "detail": detail,
    }
    if errors is not None:
        body["errors"] = errors
    if extra:
        body.update(extra)
    return body


def _validation_errors(detail) -> dict:
    if isinstance(detail, dict):
        return detail
    return {"non_field_errors": detail if isinstance(detail, list) else [detail]}


def _auth_failed_detail(exc: exceptions.APIException) -> str:
    codes = exc.get_codes()
    if isinstance(codes, dict):
        codes = codes.get("code")
    if codes == "no_active_account":
        return "Email yoki parol notoʻgʻri."
    if codes == "token_not_valid":
        return "Token yaroqsiz yoki muddati oʻtgan. Qaytadan kiring."
    return "Avtorizatsiya maʼlumotlari notoʻgʻri."


def problem_exception_handler(exc, context):
    """DRF EXCEPTION_HANDLER: every error leaves the API in one RFC 9457-style shape."""
    headers = {}

    if isinstance(exc, DomainError):
        body = problem(
            exc.code,
            exc.http_status,
            exc.message,
            title=exc.title,
            errors=exc.errors,
            extra=exc.extra,
        )
        return Response(body, status=exc.http_status)

    database_response = _database_error(exc)
    if database_response is not None:
        return database_response

    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    if not isinstance(exc, exceptions.APIException):
        return None

    if isinstance(exc, exceptions.ValidationError):
        code, status_code = "VALIDATION_ERROR", status.HTTP_422_UNPROCESSABLE_ENTITY
        body = problem(
            code,
            status_code,
            "Kiritilgan maʼlumotlarni tekshiring.",
            errors=_validation_errors(exc.detail),
        )
    elif isinstance(exc, exceptions.NotAuthenticated):
        body = problem("AUTH_REQUIRED", 401, "Bu amal uchun tizimga kiring.")
    elif isinstance(exc, exceptions.AuthenticationFailed):
        body = problem("AUTH_REQUIRED", 401, _auth_failed_detail(exc))
    elif isinstance(exc, exceptions.PermissionDenied):
        body = problem("FORBIDDEN", 403, "Bu amalni bajarishga ruxsatingiz yoʻq.")
    elif isinstance(exc, exceptions.NotFound):
        body = problem("NOT_FOUND", 404, "Soʻralgan obyekt topilmadi.")
    elif isinstance(exc, exceptions.MethodNotAllowed):
        body = problem("METHOD_NOT_ALLOWED", 405, "Bu manzil uchun HTTP usuli notoʻgʻri.")
    elif isinstance(exc, exceptions.UnsupportedMediaType):
        body = problem("UNSUPPORTED_MEDIA_TYPE", 415, "Soʻrov JSON formatida boʻlishi kerak.")
    elif isinstance(exc, exceptions.Throttled):
        wait = int(exc.wait) if exc.wait is not None else None
        detail = "Soʻrovlar juda koʻp. Birozdan keyin qayta urinib koʻring."
        if wait is not None:
            detail = f"Soʻrovlar juda koʻp. {wait} soniyadan keyin qayta urinib koʻring."
            headers["Retry-After"] = str(wait)
        body = problem("THROTTLED", 429, detail)
    elif isinstance(exc, exceptions.ParseError):
        body = problem("BAD_REQUEST", 400, "Soʻrov tanasini oʻqib boʻlmadi (JSON xato).")
    else:
        logger.warning("Unmapped API exception %s: %s", type(exc).__name__, exc.detail)
        body = problem("SERVER_ERROR", exc.status_code, "Kutilmagan xato yuz berdi.")

    # DRF downgrades 401 to 403 on views without an authenticator (e.g. the token endpoint);
    # a failed login is still an authentication failure, so we keep 401 and supply the header.
    if body["status"] == 401:
        headers["WWW-Authenticate"] = getattr(exc, "auth_header", None) or 'Bearer realm="api"'
    return Response(body, status=body["status"], headers=headers)
