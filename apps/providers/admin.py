from django.contrib import admin

from .models import Provider, ProviderService


class ProviderServiceInline(admin.TabularInline):
    model = ProviderService
    extra = 0
    autocomplete_fields = ("service",)


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "is_active", "timezone")
    list_filter = ("is_active",)
    search_fields = ("name", "user__email")
    raw_id_fields = ("user",)
    inlines = [ProviderServiceInline]

    def has_delete_permission(self, request, obj=None):
        # Providers are deactivated, never deleted: bookings reference them.
        return False
