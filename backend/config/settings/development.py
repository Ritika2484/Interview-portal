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
