from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.accounts.models import User


def is_admin(user) -> bool:
    return bool(user and user.is_authenticated and user.role == User.Role.ADMIN)


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return is_admin(request.user)


class IsAdminOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS or is_admin(request.user)
