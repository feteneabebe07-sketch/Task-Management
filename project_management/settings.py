"""
Django settings for project_management project.
Compatible with both local development and production (Render).
"""

from pathlib import Path
import os
import dj_database_url

# --------------------------------------------------
# Base
# --------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# --------------------------------------------------
# Environment
# --------------------------------------------------
# Prefer an explicit DJANGO_ENV (development|production). For backwards
# compatibility `DJANGO_DEBUG` can override when explicitly provided.
# Default to development for local work (safer than defaulting to prod).
DJANGO_ENV = os.environ.get("DJANGO_ENV", "development").lower()
if "DJANGO_DEBUG" in os.environ:
    DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() in ("1", "true", "yes")
else:
    DEBUG = DJANGO_ENV in ("dev", "development", "local")

# Consider the environment production only when explicitly set to prod/production
# and not running with DEBUG on.
IS_PRODUCTION = DJANGO_ENV in ("prod", "production") and not DEBUG

# --------------------------------------------------
# Security
# --------------------------------------------------
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-key-change-in-production"
)

# --------------------------------------------------
# Hosts
# --------------------------------------------------
ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
]

RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

# Optional: allow extra hosts via env
_extra_hosts = os.environ.get("DJANGO_ALLOWED_HOSTS")
if _extra_hosts:
    ALLOWED_HOSTS += [h.strip() for h in _extra_hosts.split(",") if h.strip()]

# --------------------------------------------------
# Proxy / HTTPS (Render)
# --------------------------------------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# --------------------------------------------------
# Cookies & CSRF
# --------------------------------------------------
SESSION_COOKIE_SECURE = IS_PRODUCTION
CSRF_COOKIE_SECURE = IS_PRODUCTION
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# CSRF trusted origins
CSRF_TRUSTED_ORIGINS = []

# Use explicit scheme depending on environment. Allow configuring via env override below.
_scheme = "https" if IS_PRODUCTION else "http"
CSRF_TRUSTED_ORIGINS += [
    f"{_scheme}://{h}" for h in ALLOWED_HOSTS if h not in ("localhost", "127.0.0.1")
]
if not IS_PRODUCTION:
    # be explicit about local dev origins
    CSRF_TRUSTED_ORIGINS += [
        "http://localhost",
        "http://127.0.0.1",
    ]

# Optional override
_csrf_env = os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS")
if _csrf_env:
    CSRF_TRUSTED_ORIGINS = [
        o.strip() for o in _csrf_env.split(",") if o.strip()
    ]

# --------------------------------------------------
# Production Security Hardening
# --------------------------------------------------
if IS_PRODUCTION:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", 3600))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# --------------------------------------------------
# Applications
# --------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.humanize",
    "django.contrib.staticfiles",

    "channels",
    "channels_redis",

    "core",
    "admins",
    "project_manager",
    "employee",
]

AUTH_USER_MODEL = "core.User"

# --------------------------------------------------
# Middleware
# --------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# --------------------------------------------------
# URLs / Templates
# --------------------------------------------------
ROOT_URLCONF = "project_management.urls"

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
                "project_manager.context_processors.pm_context",
            ],
        },
    },
]

WSGI_APPLICATION = "project_management.wsgi.application"
ASGI_APPLICATION = "project_management.asgi.application"

# --------------------------------------------------
# Channels / Redis
# --------------------------------------------------
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [
                os.environ.get("REDIS_URL", "redis://172.25.239.131:6379")
            ],
        },
    },
}

# --------------------------------------------------
# --------------------------------------------------
# Database
# --------------------------------------------------
if DEBUG:
    # Local development → SQLite (NO dj_database_url)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    # Production → Postgres (Render)
    DATABASES = {
        "default": dj_database_url.config(
            default=os.environ.get("DATABASE_URL"),
            conn_max_age=600,
            ssl_require=True,
        )
    }


# --------------------------------------------------
# Auth / Sessions
# --------------------------------------------------
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

SESSION_COOKIE_AGE = 86400
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# --------------------------------------------------
# Password validation
# --------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --------------------------------------------------
# Internationalization
# --------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --------------------------------------------------
# Static & Media
# --------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# --------------------------------------------------
# Default PK
# --------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
