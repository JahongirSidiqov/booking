import uuid

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework_simplejwt.state import token_backend
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common.exceptions import DomainError

from .models import User, normalize_email

FAMILY_CLAIM = "fam"
PROFILE_FIELDS = frozenset({"full_name", "phone", "timezone"})


def register_customer(*, email: str, password: str, full_name: str, phone: str = "") -> User:
    try:
        with transaction.atomic():
            return User.objects.create_user(
                email=normalize_email(email),
                password=password,
                full_name=full_name,
                phone=phone,
                role=User.Role.CUSTOMER,
            )
    except IntegrityError as exc:
        # The serializer already checks uniqueness; this covers two simultaneous sign-ups.
        raise DomainError(
            "VALIDATION_ERROR",
            "Kiritilgan maʼlumotlarni tekshiring.",
            errors={"email": ["Bu email bilan akkaunt allaqachon mavjud."]},
        ) from exc


def update_profile(*, user: User, **fields) -> User:
    changed = [name for name in fields if name in PROFILE_FIELDS]
    for name in changed:
        setattr(user, name, fields[name])
    if changed:
        user.save(update_fields=[*changed, "updated_at"])
    return user


def issue_tokens(user: User) -> RefreshToken:
    """Start a new refresh-token family (one per login)."""
    refresh = RefreshToken.for_user(user)
    refresh[FAMILY_CLAIM] = uuid.uuid4().hex
    # for_user() stored the token before the family claim existed; keep the stored copy in
    # sync so revoke_token_family() can also find the first member of the family.
    OutstandingToken.objects.filter(jti=refresh["jti"]).update(token=str(refresh))
    return refresh


def revoke_token_family(*, user_id, family: str) -> int:
    """Blacklist every live refresh token of one login session.

    Called when an already-rotated refresh token is presented again: the token has leaked,
    and we cannot tell whether the attacker or the owner holds the newest one, so the whole
    chain dies and the owner logs in again.
    """
    revoked = 0
    live = OutstandingToken.objects.filter(
        user_id=user_id, expires_at__gt=timezone.now(), blacklistedtoken__isnull=True
    )
    for outstanding in live:
        payload = token_backend.decode(outstanding.token, verify=False)
        if payload.get(FAMILY_CLAIM) == family:
            BlacklistedToken.objects.get_or_create(token=outstanding)
            revoked += 1
    return revoked


def logout(*, refresh: RefreshToken) -> None:
    refresh.blacklist()
