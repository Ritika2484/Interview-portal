from pathlib import Path

import environ

# Local files never override values explicitly injected into the environment.
environ.Env.read_env(Path(__file__).resolve().parents[3] / ".env", overwrite=False)

from .base import *  # noqa: E402

DEBUG = True
ENABLE_ADMIN = True
ENABLE_API_DOCS = env.bool("DJANGO_ENABLE_API_DOCS", default=True)
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
AUTH_ADMIN_LOGIN_ENABLED = True
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="127.0.0.1")
EMAIL_PORT = env.int("EMAIL_PORT", default=1025)
EMAIL_USE_TLS = False
