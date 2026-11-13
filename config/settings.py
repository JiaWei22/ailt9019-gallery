import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "demo-only-not-for-production"
DEBUG = False
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "reviews",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
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
                "reviews.context_processors.current_reviewer",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {"timeout": 60},
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Hong_Kong"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

PASSWORD_HASHERS = [
    "reviews.hashers.IssuedPasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

STAFF_PASSWORD = os.environ.get("LEGACY_STAFF_PASSWORD") or __import__("secrets").token_urlsafe(32)
SESSION_REVIEWER_KEY = "reviewer_pk"
SESSION_STAFF_KEY = "is_course_staff"
BACKUP_DIR = BASE_DIR / "var" / "backups"
BACKUP_KEEP = 20
BACKUP_MAX_AGE_HOURS = 12
# Local stand-in for mailbox 2FA until SMTP is approved.
SHOW_OTP_ON_PAGE = DEBUG
OTP_OUTBOX_DIR = BASE_DIR / "var" / "otp_outbox"

# The HKU server mounts this app at /review-system. Leave unset for local use.
_script_name = os.environ.get("FORCE_SCRIPT_NAME", "")
if _script_name:
    FORCE_SCRIPT_NAME = _script_name
