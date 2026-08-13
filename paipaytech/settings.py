from pathlib import Path
import os

from django.core.exceptions import ImproperlyConfigured
import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


IS_VERCEL = os.getenv("VERCEL") == "1"
IS_RAILWAY = bool(os.getenv("RAILWAY_ENVIRONMENT"))
SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-local-only-change-me")
DEBUG = env_bool("DEBUG", not (IS_VERCEL or IS_RAILWAY))

if not DEBUG and SECRET_KEY == "django-insecure-local-only-change-me":
    raise ImproperlyConfigured("Define SECRET_KEY con un valor seguro antes de desplegar.")

ALLOWED_HOSTS = env_list(
    "ALLOWED_HOSTS",
    "localhost,127.0.0.1,.up.railway.app,.vercel.app",
)
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "")

if not DEBUG and "ALLOWED_HOSTS" not in os.environ:
    raise ImproperlyConfigured(
        "Define ALLOWED_HOSTS explícitamente antes de desplegar."
    )

INSTALLED_APPS = [
    "cuentas.apps.CuentasConfig",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "monitoreo.apps.MonitoreoConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "cuentas.middleware.CambioClaveInicialMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "paipaytech.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.jinja2.Jinja2",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "environment": "paipaytech.jinja2.environment",
        },
    },
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "paipaytech.wsgi.application"
ASGI_APPLICATION = "paipaytech.asgi.application"

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if (IS_VERCEL or IS_RAILWAY) and not DATABASE_URL:
    raise ImproperlyConfigured("Define DATABASE_URL con la conexión de Neon antes de desplegar.")

if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=0,
            ssl_require=True,
        )
    }
    DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
    DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            # v1.4 usa un esquema nuevo. El archivo db.sqlite3 del prototipo se
            # conserva sin alterarlo para que la reconstrucción sea reversible.
            "NAME": BASE_DIR / "db_v14.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {
        "NAME": "cuentas.validators.MaximumLengthValidator",
        "OPTIONS": {"max_length": 32},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-ec"
TIME_ZONE = "America/Guayaquil"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "cuentas.Usuario"
LOGIN_URL = "monitoreo:login"
LOGIN_REDIRECT_URL = "monitoreo:dashboard"
LOGOUT_REDIRECT_URL = "monitoreo:login"

# Límites defensivos: no hay carga de archivos en v1.4 y una jornada JSON no
# necesita cuerpos arbitrariamente grandes. El máximo de peces se valida además
# en el serializer para responder 400 antes de tocar la base.
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 3000

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "cuentas.authentication.TokenDispositivoAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
        "cuentas.permissions.ClaveActualizada",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}

# Solo debe activarse cuando la aplicación corre detrás de un proxy controlado
# (Railway). En desarrollo se usa REMOTE_ADDR para impedir suplantar la IP.
TRUST_X_FORWARDED_FOR = env_bool("TRUST_X_FORWARDED_FOR", False)

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SECURE_REDIRECT_EXEMPT = [r"^api/v1/health/$"]
    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
    SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS > 0
