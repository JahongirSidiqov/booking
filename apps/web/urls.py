from django.urls import path

from apps.web.views import account, booking_flow, customer

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
]
