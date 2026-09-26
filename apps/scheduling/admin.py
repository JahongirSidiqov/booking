from django.contrib import admin

from .models import AvailabilityRule, BusinessSettings, TimeOff


@admin.register(AvailabilityRule)
class AvailabilityRuleAdmin(admin.ModelAdmin):
    list_display = ("provider", "weekday", "start_time", "end_time")
    list_filter = ("weekday", "provider")


@admin.register(TimeOff)
class TimeOffAdmin(admin.ModelAdmin):
    list_display = ("provider", "start_at", "end_at", "reason")
    list_filter = ("provider",)
    date_hierarchy = "start_at"


@admin.register(BusinessSettings)
class BusinessSettingsAdmin(admin.ModelAdmin):
    list_display = ("name", "timezone", "slot_step_minutes", "auto_confirm")

    def has_add_permission(self, request):
        return not BusinessSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
