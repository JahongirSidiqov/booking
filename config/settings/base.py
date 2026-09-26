from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env", overwrite=False)

SECRET_KEY = env("SECRET_KEY")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "apps.common",
    "apps.accounts",
    "apps.catalog",
    "apps.providers",
    "apps.scheduling",
    "apps.bookings",
    "apps.notifications",
    "apps.web",
]

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "web:login"
LOGIN_REDIRECT_URL = "web:home"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "apps.web.middleware.DisplayTimezoneMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.web.context_processors.site",
            ],
        },
    },
]

# PostgreSQL is mandatory: double-booking protection relies on btree_gist ExclusionConstraint.
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = False
DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=60)
# Without a timeout an unreachable DB makes manage.py and pytest hang instead of failing.
DATABASES["default"].setdefault("OPTIONS", {}).setdefault(
    "connect_timeout", env.int("DB_CONNECT_TIMEOUT", default=5)
)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {
        # Default attributes are username/first_name/last_name; our user has email + full_name.
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
        "OPTIONS": {"user_attributes": ("email", "full_name")},
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "uz"
# Storage and service layer work in UTC only; business/user timezones are applied at the edges.
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
DEFAULT_TZ = env("DEFAULT_TZ", default="Asia/Tashkent")

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=25)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=False)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Navbat <no-reply@navbat.uz>")
# Absolute links in emails (there is no request when an on_commit hook runs).
# Password for `manage.py seed_demo` accounts (demo only, never a real user).
DEMO_PASSWORD = env("DEMO_PASSWORD", default="Navbat-Demo-2026")
SITE_URL = env("SITE_URL", default="http://localhost:8000").rstrip("/")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # JWT first: its WWW-Authenticate header makes unauthenticated API calls 401, not 403.
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "120/min",
        "auth_token": "10/min",
        "bookings_create": "10/min",
    },
    "NUM_PROXIES": env.int("NUM_PROXIES", default=None),
    "EXCEPTION_HANDLER": "apps.common.exceptions.problem_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Navbat API",
    "DESCRIPTION": (
        "Onlayn navbat va bron tizimi API'si. Autentifikatsiya: `Authorization: Bearer <access>` "
        "(`POST /api/v1/auth/token`). Barcha vaqtlar ISO 8601; kirishda offset majburiy, "
        "chiqishda UTC (`Z`). Xatolar RFC 9457 uslubida: `type`, `title`, `status`, `code`, "
        "`detail`, faqat 422 da `errors`."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "ENUM_NAME_OVERRIDES": {
        "BookingStatusEnum": "apps.bookings.models.Booking.Status",
        "UserRoleEnum": "apps.accounts.models.User.Role",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}
