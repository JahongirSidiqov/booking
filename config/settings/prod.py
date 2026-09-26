from .base import *  # noqa: F403
from .base import env

DEBUG = False
# The container's own health check connects as localhost; public hosts come from the env.
ALLOWED_HOSTS = [*ALLOWED_HOSTS, "localhost", "127.0.0.1"]  # noqa: F405

# Render and Railway announce the public hostname in the environment; trusting it here means
# a fresh deploy works without copying the generated URL into three settings by hand.
PLATFORM_HOST = env("RENDER_EXTERNAL_HOSTNAME", default="") or env(
    "RAILWAY_PUBLIC_DOMAIN", default=""
)
if PLATFORM_HOST:
    ALLOWED_HOSTS.append(PLATFORM_HOST)

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
if PLATFORM_HOST:
    CSRF_TRUSTED_ORIGINS.append(f"https://{PLATFORM_HOST}")
    SITE_URL = env("SITE_URL", default=f"https://{PLATFORM_HOST}").rstrip("/")
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
# Container health checks call plain http://localhost:8000/healthz from inside the box.
SECURE_REDIRECT_EXEMPT = [r"^healthz$"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 30)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# HSTS preload is a near-irreversible commitment for the whole domain (and demo deploys live
# on shared *.onrender.com / *.up.railway.app hosts), so it is a deliberate opt-out.
SILENCED_SYSTEM_CHECKS = ["security.W021"]
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# Behind Render/Railway/Caddy there is exactly one proxy in front of gunicorn; throttling
# must key on the real client IP from X-Forwarded-For, not on the proxy's address.
REST_FRAMEWORK = {**REST_FRAMEWORK, "NUM_PROXIES": env.int("NUM_PROXIES", default=1)}  # noqa: F405

LOGGING = {
    **LOGGING,  # noqa: F405
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "apps": {
            "handlers": ["console"],
            "level": env("LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
    },
}
