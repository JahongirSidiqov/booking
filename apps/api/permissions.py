from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.accounts.models import User


def is_admin(user) -> bool:
    return bool(user and user.is_authenticated and user.role == User.Role.ADMIN)


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return is_admin(request.user)


def can_manage_provider(user, provider) -> bool:
    # A provider without a linked user can only be managed by the admin (edge case #35).
    if is_admin(user):
        return True
    return bool(
        user
        and user.is_authenticated
        and user.role == User.Role.PROVIDER
        and provider.user_id is not None
        and provider.user_id == user.pk
    )


class IsProviderOwnerOrAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        return can_manage_provider(request.user, obj)


class IsAdminOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS or is_admin(request.user)
