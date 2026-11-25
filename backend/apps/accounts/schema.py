from django.conf import settings
from drf_spectacular.extensions import OpenApiAuthenticationExtension


class SessionScheme(OpenApiAuthenticationExtension):
    target_class = "apps.accounts.authentication.VerifiedSessionAuthentication"
    name = "sessionCookie"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "cookie",
            "name": settings.SESSION_COOKIE_NAME,
            "description": (
                "HttpOnly server-side session. Unsafe methods require X-CSRFToken. "
                "Call /auth/csrf/ before login, and refresh it after login rotates CSRF."
            ),
        }
