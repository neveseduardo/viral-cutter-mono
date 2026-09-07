"""
Django settings for ViralCutter.

All configuration comes from environment variables / .env (12-factor). See
`infra/.env.example` for the complete list of supported variables.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Allow a custom env file (defaults to repo-root .env or backend/.env)
_env_file = os.environ.get("DJANGO_ENV_FILE")
if _env_file:
    load_dotenv(os.path.abspath(_env_file))
else:
    load_dotenv(BASE_DIR / ".env")
    load_dotenv(BASE_DIR.parent / ".env")

os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "*")


def _bool(value, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _int(value: str | None, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _list(value: str | None, default: list[str] | None = None) -> list[str]:
    if not value:
        return default or []
    return [item.strip() for item in value.split(",") if item.strip()]


# --- Security ---------------------------------------------------------------
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-secret-key")
DEBUG = _bool(os.environ.get("DJANGO_DEBUG"), True)
ALLOWED_HOSTS = _list(os.environ.get("DJANGO_ALLOWED_HOSTS"), ["*"])

# --- Apps -------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "django_filters",
    # ViralCutter
    "apps.accounts",
    "apps.projects",
    "apps.media",
    "apps.ingestion",
    "apps.transcription",
    "apps.analysis",
    "apps.editing",
    "apps.subtitles",
    "apps.rendering",
    "apps.export",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
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

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- Database ----------------------------------------------------------------
DB_ENGINE = os.environ.get("DB_ENGINE", "sqlite").lower()

if DB_ENGINE == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("POSTGRES_DB", "viralcutter"),
            "USER": os.environ.get("POSTGRES_USER", "viralcutter"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "change_me"),
            "HOST": os.environ.get("POSTGRES_HOST", "db"),
            "PORT": _int(os.environ.get("POSTGRES_PORT"), 5432),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# --- Auth -------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
AUTH_DISABLED = _bool(os.environ.get("AUTH_DISABLED"), True)

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("apps.accounts.permissions.LocalFirstPermission",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "EXCEPTION_HANDLER": "apps.accounts.exceptions.viralcutter_exception_handler",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": _int(os.environ.get("JWT_ACCESS_MINUTES"), 60) * 60,
}

CORS_ALLOWED_ORIGINS = _list(os.environ.get("CORS_ORIGINS"), ["http://localhost:5173"])
CORS_ALLOW_ALL_ORIGINS = _bool(os.environ.get("CORS_ALLOW_ALL", False))

# --- Storage ----------------------------------------------------------------
STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", BASE_DIR.parent / "data"))
MAIN_STORAGE_ROOT = STORAGE_ROOT
MEDIA_URL = os.environ.get("MEDIA_URL", "/media/")
STORAGE_QUOTA_MB = _int(os.environ.get("STORAGE_QUOTA_MB"), 10240)

MEDIA_ROOT = STORAGE_ROOT / "media"
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

# --- Celery / Redis ---------------------------------------------------------
REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://127.0.0.1:6379/1")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/2")

CELERY_TASK_ALWAYS_EAGER = _bool(os.environ.get("CELERY_TASK_ALWAYS_EAGER"), False)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TASK_MAX_RETRIES = _int(os.environ.get("CELERY_TASK_MAX_RETRIES"), 3)
CELERY_RETRY_BACKOFF = _int(os.environ.get("CELERY_RETRY_BACKOFF"), 5)
CONCURRENT_JOBS_LIMIT = _int(os.environ.get("CONCURRENT_JOBS_LIMIT"), 2)
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True

# --- GPU / media ------------------------------------------------------------
USE_GPU = _bool(os.environ.get("USE_GPU"), False)
CUDA_DEVICE = _int(os.environ.get("CUDA_DEVICE"), 0)
FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "ffmpeg")
FFPROBE_BIN = os.environ.get("FFPROBE_BIN", "ffprobe")
FFMPEG_ENCODER = os.environ.get("FFMPEG_ENCODER", "")  # vazio = auto (libx264)

# Dynamic router: transcription and rendering only use the `gpu` queue when
# explicitly enabled (USE_GPU=true + FFMPEG_ENCODER=nvenc for encodes).
# Otherwise they fall back to `cpu`, which the default worker consumes
# (AGENTS.md §5.3: "não assumir que toda operação FFmpeg precisa de GPU").
def _vc_task_router(name, args, kwargs, options, task=None, **kw):
    if name.startswith("apps.ingestion."):
        return {"queue": "io"}
    if name.startswith("apps.transcription."):
        return {"queue": "gpu" if USE_GPU else "cpu"}
    if name.startswith("apps.rendering."):
        wants_gpu = USE_GPU and FFMPEG_ENCODER in ("h264_nvenc", "hevc_nvenc")
        return {"queue": "gpu" if wants_gpu else "cpu"}
    if name.startswith("apps.analysis.") or name.startswith("apps.editing.") or name.startswith("apps.export.") or name.startswith("apps.subtitles."):
        return {"queue": "cpu"}
    return None


CELERY_TASK_ROUTES = _vc_task_router
OUTPUT_WIDTH = _int(os.environ.get("OUTPUT_WIDTH"), 1080)
OUTPUT_HEIGHT = _int(os.environ.get("OUTPUT_HEIGHT"), 1920)

# --- Whisper ----------------------------------------------------------------
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "large-v3-turbo")

# --- AI providers (server-side) ---------------------------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1")
LOCAL_LLM_MODELS_DIR = os.environ.get("LOCAL_LLM_MODELS_DIR", "")
AI_FAILOVER = os.environ.get("AI_FAILOVER", "gemini,openai,ollama")
GEMINI_RATE_LIMIT = _int(os.environ.get("GEMINI_RATE_LIMIT"), 30)

# --- Translation ------------------------------------------------------------
TRANSLATION_ENGINE = os.environ.get("TRANSLATION_ENGINE", "deep_translator")
DEEPL_KEY = os.environ.get("DEEPL_KEY", "")

# --- Limits and quotas (§5.9) ----------------------------------------------
MAX_UPLOAD_MB = _int(os.environ.get("MAX_UPLOAD_MB"), 4096)
MAX_VIDEO_DURATION_S = _int(os.environ.get("MAX_VIDEO_DURATION_S"), 7200)
MAX_SEGMENTS = _int(os.environ.get("MAX_SEGMENTS"), 10)

# --- i18n -------------------------------------------------------------------
LANGUAGE_CODE = os.environ.get("LANGUAGE_CODE", "pt-br")
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --- Static files --------------------------------------------------------------
STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Safety
LOGIN_URL = "/api/v1/auth/login"
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "[%(asctime)s] %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}