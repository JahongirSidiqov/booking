from django.urls import path

from apps.web.views import (
    account,
    booking_flow,
    customer,
    dashboard_bookings,
    dashboard_catalog,
    dashboard_schedule,
)

app_name = "web"

urlpatterns = [
    path("", customer.home, name="home"),
    path("book/<slug:slug>/", booking_flow.book, name="book"),
    path("book/<slug:slug>/confirm/", booking_flow.confirm, name="book_confirm"),
    path("book/<slug:slug>/done/<uuid:booking_id>/", booking_flow.done, name="book_done"),
    path("bookings/", customer.my_bookings, name="bookings"),
    path("bookings/<uuid:booking_id>/", customer.booking_detail, name="booking_detail"),
    path("bookings/<uuid:booking_id>/cancel/", customer.cancel_booking, name="booking_cancel"),
    path("login/", account.LoginView.as_view(), name="login"),
    path("logout/", account.LogoutView.as_view(), name="logout"),
    path("register/", account.register, name="register"),
    path("profile/", account.profile, name="profile"),
    # --- dashboard (provider + admin) ---
    path("dashboard/", dashboard_bookings.today, name="dashboard"),
    path("dashboard/bookings/", dashboard_bookings.booking_list, name="dashboard_bookings"),
    path(
        "dashboard/bookings/<uuid:booking_id>/",
        dashboard_bookings.booking_detail,
        name="dashboard_booking",
    ),
    path(
        "dashboard/bookings/<uuid:booking_id>/<slug:action>/",
        dashboard_bookings.booking_action,
        name="dashboard_booking_action",
    ),
    path("dashboard/services/", dashboard_catalog.services, name="dashboard_services"),
    path(
        "dashboard/services/<uuid:service_id>/deactivate/",
        dashboard_catalog.service_deactivate,
        name="dashboard_service_deactivate",
    ),
    path("dashboard/providers/", dashboard_catalog.providers, name="dashboard_providers"),
    path(
        "dashboard/providers/<uuid:provider_id>/deactivate/",
        dashboard_catalog.provider_deactivate,
        name="dashboard_provider_deactivate",
    ),
    path(
        "dashboard/providers/<uuid:provider_id>/availability/",
        dashboard_schedule.availability,
        name="dashboard_availability",
    ),
    path(
        "dashboard/providers/<uuid:provider_id>/time-off/",
        dashboard_schedule.time_off_add,
        name="dashboard_time_off_add",
    ),
    path(
        "dashboard/providers/<uuid:provider_id>/time-off/<uuid:time_off_id>/delete/",
        dashboard_schedule.time_off_delete,
        name="dashboard_time_off_delete",
    ),
    path(
        "dashboard/my-schedule/", dashboard_schedule.my_availability, name="dashboard_my_schedule"
    ),
    path("dashboard/settings/", dashboard_schedule.settings_view, name="dashboard_settings"),
]
