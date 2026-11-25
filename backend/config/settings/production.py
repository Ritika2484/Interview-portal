"""Fail-closed production defaults. Supply environment from a secret manager."""

import ssl
from urllib.parse import parse_qs, urlsplit

from django.core.exceptions import ImproperlyConfigured

from .base import *

if (
    len(SECRET_KEY) < 50
    or len(set(SECRET_KEY)) < 5
    or SECRET_KEY.startswith(("django-insecure-", "replace-"))
):
    raise ImproperlyConfigured("Production requires a strong, independently generated SECRET_KEY.")
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("Production requires explicit DJANGO_ALLOWED_HOSTS.")
for origin in CSRF_TRUSTED_ORIGINS + CORS_ALLOWED_ORIGINS:
    if not origin.startswith("https://") or "*" in origin:
        raise ImproperlyConfigured("Production CORS/CSRF origins must be explicit HTTPS origins.")
for url in (REDIS_URL, CELERY_BROKER_URL, CELERY_RESULT_BACKEND):
    if urlsplit(url).scheme != "rediss":
        raise ImproperlyConfigured("Production Redis connections require rediss:// TLS URLs.")
    query = parse_qs(urlsplit(url).query)
    if query.get("ssl_cert_reqs", ["required"])[0].lower() != "required":
        raise ImproperlyConfigured("Production Redis TLS must verify server certificates.")

CELERY_BROKER_USE_SSL = {"ssl_cert_reqs": ssl.CERT_REQUIRED}
CELERY_REDIS_BACKEND_USE_SSL = {"ssl_cert_reqs": ssl.CERT_REQUIRED}

DEBUG = False
ENABLE_ADMIN = False  # Remains unavailable until staff MFA/access controls are implemented.
ENABLE_API_DOCS = False
DATABASES["default"]["OPTIONS"]["sslmode"] = env("DATABASE_SSLMODE", default="verify-full")
if DATABASES["default"]["OPTIONS"]["sslmode"] not in {"verify-ca", "verify-full"}:
    raise ImproperlyConfigured("Production database TLS must verify the server certificate.")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
# Set true only when a trusted ingress strips and overwrites client-supplied headers.
if env.bool("DJANGO_TRUST_PROXY_SSL_HEADER", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = True
