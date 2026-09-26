import pytest
from freezegun import freeze_time
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from apps.accounts.models import User

pytestmark = pytest.mark.django_db

REGISTER = "/api/v1/auth/register"
TOKEN = "/api/v1/auth/token"
REFRESH = "/api/v1/auth/token/refresh"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/me"


def login(client, email, password):
    return client.post(TOKEN, {"email": email, "password": password}, format="json")


def assert_problem(response, status, code):
    assert response.status_code == status, response.content
    body = response.json()
    assert body["status"] == status
    assert body["code"] == code
    assert body["type"].startswith("https://navbat.uz/errors/")
    assert body["title"] and body["detail"]
    return body


# --- register -----------------------------------------------------------------------------


def test_register_creates_customer(api_client):
    response = api_client.post(
        REGISTER,
        {
            "email": "Yangi.Mijoz@Example.com",
            "password": "Kuchli-Parol-77",
            "full_name": "Yangi Mijoz",
            "phone": "+998901234567",
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["email"] == "yangi.mijoz@example.com"
    assert body["role"] == "customer"
    assert body["timezone"] == "Asia/Tashkent"
    assert "password" not in body
    user = User.objects.get(email="yangi.mijoz@example.com")
    assert user.check_password("Kuchli-Parol-77")


def test_register_ignores_role_escalation(api_client):
    response = api_client.post(
        REGISTER,
        {
            "email": "hacker@example.com",
            "password": "Kuchli-Parol-77",
            "full_name": "H",
            "role": "admin",
        },
        format="json",
    )
    assert response.status_code == 201
    assert User.objects.get(email="hacker@example.com").role == User.Role.CUSTOMER


def test_register_duplicate_email_case_insensitive(api_client, customer):
    response = api_client.post(
        REGISTER,
        {"email": customer.email.upper(), "password": "Kuchli-Parol-77", "full_name": "X"},
        format="json",
    )
    body = assert_problem(response, 422, "VALIDATION_ERROR")
    assert "email" in body["errors"]


@pytest.mark.parametrize("password", ["1234567", "12345678", "password", "yangi.mijoz"])
def test_register_rejects_weak_password(api_client, password):
    response = api_client.post(
        REGISTER,
        {"email": "yangi.mijoz@example.com", "password": password, "full_name": "Yangi Mijoz"},
        format="json",
    )
    body = assert_problem(response, 422, "VALIDATION_ERROR")
    assert "password" in body["errors"]


def test_register_validates_shape(api_client):
    response = api_client.post(
        REGISTER,
        {
            "email": "not-an-email",
            "password": "Kuchli-Parol-77",
            "full_name": "x" * 121,
            "phone": "901234567",
        },
        format="json",
    )
    body = assert_problem(response, 422, "VALIDATION_ERROR")
    assert set(body["errors"]) >= {"email", "full_name", "phone"}


# --- login --------------------------------------------------------------------------------


def test_login_returns_token_pair(api_client, customer, password):
    response = login(api_client, customer.email.upper(), password)
    assert response.status_code == 200
    assert {"access", "refresh"} <= set(response.json())


def test_login_wrong_password_is_401(api_client, customer):
    response = login(api_client, customer.email, "notogri-parol")
    body = assert_problem(response, 401, "AUTH_REQUIRED")
    assert body["detail"] == "Email yoki parol notoʻgʻri."
    assert "WWW-Authenticate" in response


def test_login_inactive_user_is_401(api_client, customer, password):
    customer.is_active = False
    customer.save()
    assert_problem(login(api_client, customer.email, password), 401, "AUTH_REQUIRED")


def test_access_token_lifetime_is_15_minutes(api_client, customer, password):
    with freeze_time("2026-10-01 09:00:00"):
        access = login(api_client, customer.email, password).json()["access"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    with freeze_time("2026-10-01 09:14:00"):
        assert api_client.get(ME).status_code == 200
    with freeze_time("2026-10-01 09:16:00"):
        assert_problem(api_client.get(ME), 401, "AUTH_REQUIRED")


# --- refresh rotation ---------------------------------------------------------------------


def test_refresh_rotates_and_blacklists_old_token(api_client, customer, password):
    old = login(api_client, customer.email, password).json()["refresh"]
    response = api_client.post(REFRESH, {"refresh": old}, format="json")
    assert response.status_code == 200
    body = response.json()
    assert body["refresh"] != old
    assert "access" in body
    assert BlacklistedToken.objects.count() == 1


def test_edge_30_refresh_reuse_revokes_whole_family(api_client, customer, password):
    first = login(api_client, customer.email, password).json()["refresh"]
    second = api_client.post(REFRESH, {"refresh": first}, format="json").json()["refresh"]

    # Replaying the rotated token is rejected ...
    assert_problem(
        api_client.post(REFRESH, {"refresh": first}, format="json"), 401, "AUTH_REQUIRED"
    )
    # ... and the newest token of that session dies with it.
    assert_problem(
        api_client.post(REFRESH, {"refresh": second}, format="json"), 401, "AUTH_REQUIRED"
    )


def test_refresh_reuse_does_not_touch_other_sessions(api_client, customer, password):
    phone = login(api_client, customer.email, password).json()["refresh"]
    laptop = login(api_client, customer.email, password).json()["refresh"]
    api_client.post(REFRESH, {"refresh": phone}, format="json")
    api_client.post(REFRESH, {"refresh": phone}, format="json")  # replay on the phone session

    assert api_client.post(REFRESH, {"refresh": laptop}, format="json").status_code == 200


def test_first_token_of_family_is_stored_with_family_claim(api_client, customer, password):
    refresh = login(api_client, customer.email, password).json()["refresh"]
    assert OutstandingToken.objects.get(user=customer).token == refresh


def test_refresh_with_garbage_is_401(api_client):
    assert_problem(
        api_client.post(REFRESH, {"refresh": "abc"}, format="json"), 401, "AUTH_REQUIRED"
    )


def test_refresh_rejects_access_token(api_client, customer, password):
    access = login(api_client, customer.email, password).json()["access"]
    assert_problem(
        api_client.post(REFRESH, {"refresh": access}, format="json"), 401, "AUTH_REQUIRED"
    )


def test_refresh_expires_after_7_days(api_client, customer, password):
    with freeze_time("2026-10-01 09:00:00"):
        refresh = login(api_client, customer.email, password).json()["refresh"]
    with freeze_time("2026-10-08 09:01:00"):
        assert_problem(
            api_client.post(REFRESH, {"refresh": refresh}, format="json"), 401, "AUTH_REQUIRED"
        )


# --- logout -------------------------------------------------------------------------------


def test_logout_blacklists_refresh(api_client, customer, password):
    tokens = login(api_client, customer.email, password).json()
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    assert api_client.post(LOGOUT, {"refresh": tokens["refresh"]}, format="json").status_code == 204
    assert_problem(
        api_client.post(REFRESH, {"refresh": tokens["refresh"]}, format="json"),
        401,
        "AUTH_REQUIRED",
    )


def test_logout_requires_auth(api_client):
    assert_problem(api_client.post(LOGOUT, {"refresh": "x"}, format="json"), 401, "AUTH_REQUIRED")


def test_logout_rejects_someone_elses_token(api_client, customer, admin_user, password):
    victim_refresh = login(api_client, admin_user.email, password).json()["refresh"]
    access = login(api_client, customer.email, password).json()["access"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    assert_problem(
        api_client.post(LOGOUT, {"refresh": victim_refresh}, format="json"), 401, "AUTH_REQUIRED"
    )
    assert api_client.post(REFRESH, {"refresh": victim_refresh}, format="json").status_code == 200


# --- me -----------------------------------------------------------------------------------


def test_me_requires_auth(api_client):
    body = assert_problem(api_client.get(ME), 401, "AUTH_REQUIRED")
    assert "errors" not in body


def test_me_returns_profile(auth_client):
    body = auth_client.get(ME).json()
    assert body["email"] == auth_client.user.email
    assert body["role"] == "customer"


def test_me_patch_updates_profile_but_not_role_or_email(auth_client):
    response = auth_client.patch(
        ME,
        {
            "full_name": "Yangi Ism",
            "timezone": "Asia/Dubai",
            "phone": "+998931112233",
            "role": "admin",
            "email": "boshqa@example.com",
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    auth_client.user.refresh_from_db()
    assert auth_client.user.full_name == "Yangi Ism"
    assert auth_client.user.timezone == "Asia/Dubai"
    assert auth_client.user.role == User.Role.CUSTOMER
    assert auth_client.user.email != "boshqa@example.com"


def test_me_patch_rejects_unknown_timezone(auth_client):
    body = assert_problem(
        auth_client.patch(ME, {"timezone": "Asia/Toshkent"}, format="json"), 422, "VALIDATION_ERROR"
    )
    assert "timezone" in body["errors"]


def test_me_put_not_allowed(auth_client):
    assert_problem(auth_client.put(ME, {}, format="json"), 405, "METHOD_NOT_ALLOWED")


def test_non_json_body_is_415(auth_client):
    response = auth_client.patch(
        ME, "full_name=x", content_type="application/x-www-form-urlencoded"
    )
    assert_problem(response, 415, "UNSUPPORTED_MEDIA_TYPE")


# --- throttling ---------------------------------------------------------------------------


def test_login_throttled_after_10_per_minute(api_client, customer):
    for _ in range(10):
        assert login(api_client, customer.email, "notogri-parol").status_code == 401
    response = login(api_client, customer.email, "notogri-parol")
    assert_problem(response, 429, "THROTTLED")
    assert int(response["Retry-After"]) > 0


def test_login_throttle_is_per_ip(api_client, customer, password):
    for _ in range(10):
        login(api_client, customer.email, "notogri-parol")
    response = api_client.post(
        TOKEN,
        {"email": customer.email, "password": password},
        format="json",
        REMOTE_ADDR="10.0.0.2",
    )
    assert response.status_code == 200
