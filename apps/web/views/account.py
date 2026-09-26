from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.accounts import services as account_services
from apps.common.exceptions import DomainError
from apps.common.utils.time import is_valid_timezone
from apps.web.access import STAFF_ROLES
from apps.web.forms import LoginForm, ProfileForm, RegisterForm
from apps.web.middleware import SESSION_TZ_KEY


def _safe_next(request, default="web:home"):
    target = request.POST.get("next") or request.GET.get("next")
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return default


class LoginView(auth_views.LoginView):
    template_name = "web/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def get_default_redirect_url(self):
        # Staff land on their dashboard; customers on the service list.
        if self.request.user.role in STAFF_ROLES:
            return reverse("web:dashboard")
        return super().get_default_redirect_url()


class LogoutView(auth_views.LogoutView):
    next_page = "web:home"


def register(request):
    if request.user.is_authenticated:
        return redirect("web:home")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            user = account_services.register_customer(
                email=data["email"],
                password=data["password"],
                full_name=data["full_name"],
                phone=data["phone"],
            )
        except DomainError as exc:
            for field, errors in (exc.errors or {}).items():
                for error in errors:
                    form.add_error(field if field in form.fields else None, error)
        else:
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            messages.success(request, "Xush kelibsiz! Akkaunt yaratildi.")
            return redirect(_safe_next(request))
    return render(request, "web/register.html", {"form": form, "next": _safe_next(request, "")})


@login_required
def profile(request):
    user = request.user
    form = ProfileForm(
        request.POST or None,
        initial={"full_name": user.full_name, "phone": user.phone, "timezone": user.timezone},
    )
    if request.method == "POST" and form.is_valid():
        account_services.update_profile(user=user, **form.cleaned_data)
        messages.success(request, "Profil saqlandi.")
        return redirect("web:profile")
    return render(request, "web/profile.html", {"form": form})


@require_POST
def set_timezone(request):
    """Banner button: show dates in the device's zone (profile for users, session otherwise)."""
    tz = request.POST.get("tz", "")
    if not is_valid_timezone(tz):
        messages.error(request, "Vaqt zonasi aniqlanmadi. Profilda qoʻlda tanlang.")
    elif request.user.is_authenticated:
        account_services.update_profile(user=request.user, timezone=tz)
        messages.success(request, f"Vaqtlar endi {tz} zonasida koʻrsatiladi.")
    else:
        request.session[SESSION_TZ_KEY] = tz
        messages.success(request, f"Vaqtlar endi {tz} zonasida koʻrsatiladi.")
    return redirect(_safe_next(request))
