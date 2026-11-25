import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings
from django.test import Client
from rest_framework.permissions import IsAuthenticated
from rest_framework.settings import api_settings

ROOT = Path(__file__).resolve().parents[1]


def production_environment():
    return {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.production",
        "DJANGO_SECRET_KEY": "test-only-production-validation-0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        "DJANGO_ALLOWED_HOSTS": "api.example.com",
        "DJANGO_CSRF_TRUSTED_ORIGINS": "https://app.example.com",
        "DJANGO_CORS_ALLOWED_ORIGINS": "https://app.example.com",
        "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
        "REDIS_URL": "rediss://localhost:6379/0",
        "CELERY_BROKER_URL": "rediss://localhost:6379/1",
        "CELERY_RESULT_BACKEND": "rediss://localhost:6379/2",
        "AUTH_PUBLIC_BASE_URL": "https://app.example.com",
        "EMAIL_HOST": "smtp.example.com",
        "DEFAULT_FROM_EMAIL": "no-reply@example.com",
    }


def import_production(changes=None, expression="print(s.DEBUG)"):
    return subprocess.run(
        [sys.executable, "-c", f"import config.settings.production as s; {expression}"],
        env={**production_environment(), **(changes or {})},
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"DJANGO_SECRET_KEY": "replace-unsafe"},
        {"DJANGO_ALLOWED_HOSTS": "*"},
        {"DJANGO_ALLOWED_HOSTS": ""},
        {"DJANGO_CSRF_TRUSTED_ORIGINS": "http://app.example.com"},
        {"DJANGO_CORS_ALLOWED_ORIGINS": "https://*.example.com"},
        {"REDIS_URL": "redis://localhost:6379/0"},
        {"CELERY_BROKER_URL": "redis://localhost:6379/1"},
        {"CELERY_RESULT_BACKEND": "rediss://localhost:6379/2?ssl_cert_reqs=none"},
        {"DATABASE_SSLMODE": "disable"},
        {"DATABASE_URL": "sqlite:///local.sqlite3"},
        {"AUTH_PUBLIC_BASE_URL": "http://app.example.com"},
        {"DEFAULT_FROM_EMAIL": "no-reply@example.invalid"},
    ],
)
def test_production_rejects_unsafe_configuration(changes):
    result = import_production(changes)
    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr


def test_production_flags_and_disabled_surfaces():
    result = import_production(
        expression=(
            "import json; print(json.dumps([s.DEBUG, s.SESSION_COOKIE_SECURE, "
            "s.CSRF_COOKIE_SECURE, s.SECURE_SSL_REDIRECT, s.ENABLE_ADMIN, "
            "s.ENABLE_API_DOCS, hasattr(s, 'SECURE_PROXY_SSL_HEADER')]))"
        )
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [False, True, True, True, False, False, False]


def test_production_deployment_checks():
    result = subprocess.run(
        [sys.executable, "manage.py", "check", "--deploy", "--fail-level", "WARNING"],
        env=production_environment(),
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_api_defaults_are_private_and_json_only():
    assert api_settings.DEFAULT_PERMISSION_CLASSES == [IsAuthenticated]
    assert settings.SESSION_ENGINE == "django.contrib.sessions.backends.db"
    assert settings.CORS_ALLOW_ALL_ORIGINS is False
    assert "django.middleware.csrf.CsrfViewMiddleware" in settings.MIDDLEWARE
    assert settings.CELERY_ACCEPT_CONTENT == ["json"]


def test_admin_login_post_enforces_csrf():
    client = Client(enforce_csrf_checks=True)
    response = client.post("/admin/login/", {"username": "someone", "password": "nope"})
    assert response.status_code == 403


def test_disallowed_cors_origin_is_not_reflected(client):
    response = client.options(
        "/api/v1/schema/",
        HTTP_ORIGIN="https://untrusted.example",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
    )
    assert "Access-Control-Allow-Origin" not in response


def test_api_only_mode_sets_restrictive_content_policy(client, settings):
    settings.DEBUG = False
    settings.ENABLE_API_DOCS = False
    response = client.get("/health/live/")
    assert "default-src 'none'" in response["Content-Security-Policy"]


def test_explicit_cors_origin_is_allowed(client, settings):
    settings.CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]
    response = client.options(
        "/api/v1/schema/",
        HTTP_ORIGIN="http://localhost:5173",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
    )
    assert response["Access-Control-Allow-Origin"] == "http://localhost:5173"
