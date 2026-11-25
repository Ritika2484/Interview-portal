import logging
import time
import uuid

from django.conf import settings

from .logging import request_id_context

logger = logging.getLogger(__name__)


class RequestLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            request_id = str(uuid.UUID(request.headers.get("X-Request-ID", "")))
        except ValueError:
            request_id = str(uuid.uuid4())
        request.request_id = request_id
        token = request_id_context.set(request_id)
        started = time.monotonic()
        try:
            response = self.get_response(request)
            response["X-Request-ID"] = request_id
            response["Permissions-Policy"] = "camera=(), microphone=(self), geolocation=()"
            if not settings.DEBUG and not settings.ENABLE_API_DOCS:
                response["Content-Security-Policy"] = (
                    "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
                )
            route = getattr(request.resolver_match, "url_name", None) or "unmatched"
            logger.info(
                "http_response",
                extra={
                    "status_code": response.status_code,
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                    "method": request.method,
                    "route": route,
                },
            )
            return response
        finally:
            request_id_context.reset(token)
