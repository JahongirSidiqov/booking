"""Who may open which dashboard page. Business rules stay in services; this is only the door."""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.accounts.models import User
from apps.api.permissions import can_manage_provider
from apps.providers.models import Provider

STAFF_ROLES = (User.Role.PROVIDER, User.Role.ADMIN)


def forbidden(request, message="Bu sahifa sizning rolingiz uchun emas."):
    return render(request, "403.html", {"message": message}, status=403)


def staff_required(view):
    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if request.user.role not in STAFF_ROLES:
            return forbidden(request)
        return view(request, *args, **kwargs)

    return wrapper


def admin_required(view):
    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if request.user.role != User.Role.ADMIN:
            return forbidden(request, "Bu boʻlim faqat administrator uchun.")
        return view(request, *args, **kwargs)

    return wrapper


def own_provider(user: User) -> Provider | None:
    """The Provider row linked to a provider-role user (None when not linked yet)."""
    if user.role != User.Role.PROVIDER:
        return None
    return Provider.objects.filter(user=user).first()


def can_manage(user: User, provider: Provider) -> bool:
    return can_manage_provider(user, provider)
