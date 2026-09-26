"""Direct tests of the problem-details handler for branches the API rarely reaches."""

import pytest
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.db import IntegrityError
from django.http import Http404
from rest_framework import exceptions

from apps.common.exceptions import problem_exception_handler


def handle(exc):
    return problem_exception_handler(exc, {})


@pytest.mark.parametrize(
    ("exc", "status", "code"),
    [
        (Http404(), 404, "NOT_FOUND"),
        (DjangoPermissionDenied(), 403, "FORBIDDEN"),
        (exceptions.ParseError(), 400, "BAD_REQUEST"),
        (exceptions.Throttled(wait=None), 429, "THROTTLED"),
        (exceptions.APIException(), 500, "SERVER_ERROR"),
    ],
)
def test_framework_exceptions_become_problems(exc, status, code):
    response = handle(exc)
    assert response.status_code == status
    assert response.data["code"] == code
    assert "errors" not in response.data


def test_throttled_without_wait_has_no_retry_after():
    assert "Retry-After" not in handle(exceptions.Throttled(wait=None))


def test_non_list_validation_detail_is_wrapped():
    response = handle(exceptions.ValidationError("bitta xato"))
    assert response.data["errors"] == {"non_field_errors": ["bitta xato"]}


def test_unknown_integrity_error_is_left_to_django():
    # Not a known business constraint: a real bug, so it must surface as a 500 with traceback.
    assert handle(IntegrityError("duplicate key value violates unique constraint")) is None


def test_non_api_exceptions_are_left_to_django():
    assert handle(ValueError("boom")) is None


def test_generic_authentication_failure_message():
    response = handle(exceptions.AuthenticationFailed("x", code="other"))
    assert response.status_code == 401
    assert response["WWW-Authenticate"] == 'Bearer realm="api"'
