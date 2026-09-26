from django.contrib import admin

from .models import Booking, BookingStatusHistory


class HistoryInline(admin.TabularInline):
    model = BookingStatusHistory
    extra = 0
    can_delete = False
    fields = ("created_at", "from_status", "to_status", "changed_by", "reason")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    """Read-only: every status change must go through bookings.services (dashboard / API)."""

    list_display = ("start_at", "service_name", "provider", "customer", "status", "price")
    list_filter = ("status", "provider")
    search_fields = ("customer__email", "customer__full_name", "service_name")
    date_hierarchy = "start_at"
    inlines = [HistoryInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
