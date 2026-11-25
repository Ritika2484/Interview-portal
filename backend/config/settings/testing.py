"""Real PostgreSQL tests. No local .env is read and no SQLite fallback exists."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-key-never-use-for-production-" * 2)
os.environ.setdefault(
    "DATABASE_URL", "postgresql://interview:interview@127.0.0.1:5432/interview_platform"
)
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
os.environ.setdefault("CELERY_BROKER_URL", "redis://127.0.0.1:6379/1")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/2")

from .base import *  # noqa: E402

DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
DATABASES["default"]["CONN_MAX_AGE"] = 0
ENABLE_API_DOCS = True
ENABLE_ADMIN = True
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}
WHITENOISE_AUTOREFRESH = True
