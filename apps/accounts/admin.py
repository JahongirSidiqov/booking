from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import BaseUserCreationForm
from django.contrib.auth.forms import UserChangeForm as DjangoUserChangeForm

from .models import User


class UserCreationForm(BaseUserCreationForm):
    class Meta(BaseUserCreationForm.Meta):
        model = User
        fields = ("email", "full_name", "role")


class UserChangeForm(DjangoUserChangeForm):
    class Meta(DjangoUserChangeForm.Meta):
        model = User
        fields = "__all__"
        field_classes = {}


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    ordering = ("email",)
    list_display = ("email", "full_name", "role", "is_active", "created_at")
    list_filter = ("role", "is_active", "is_staff")
    search_fields = ("email", "full_name", "phone")
    readonly_fields = ("created_at", "updated_at", "last_login")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profil", {"fields": ("full_name", "phone", "timezone", "role")}),
        (
            "Ruxsatlar",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Vaqtlar", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "full_name", "role", "password1", "password2"),
            },
        ),
    )
