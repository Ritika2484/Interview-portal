from django.http import JsonResponse
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler


class AccountError(APIException):
    def __init__(self, detail, code, status=400):
        self.status_code = status
        super().__init__(detail, code=code)


def problem_body(request, status, code, detail, errors=None):
    return {
        "type": f"urn:interview-platform:problem:{code.lower().replace('_', '-')}",
        "title": "Request could not be completed",
        "status": status,
        "code": code,
        "detail": detail,
        "request_id": getattr(request, "request_id", None),
        "errors": errors or {},
    }


def account_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None
    status = response.status_code
    code = str(getattr(exc, "default_code", "request_failed")).upper()
    if isinstance(exc, AccountError):
        code = str(exc.detail.code).upper()
    errors = response.data if status == 400 and isinstance(response.data, dict) else {}
    detail = (
        str(exc.detail)
        if isinstance(exc, AccountError)
        else {
            400: "Check the submitted fields.",
            401: "Authentication required or credentials invalid.",
            403: "Permission or CSRF validation failed.",
            404: "Resource not found.",
            429: "Too many requests. Try again later.",
            503: "Authentication is temporarily unavailable.",
        }.get(status, "Request could not be completed.")
    )
    response.data = problem_body(context["request"], status, code, detail, errors)
    response.content_type = "application/problem+json"
    return response


def csrf_failure(request, reason=""):
    response = JsonResponse(
        problem_body(request, 403, "CSRF_FAILED", "CSRF validation failed."),
        status=403,
        content_type="application/problem+json",
    )
    response["Cache-Control"] = "no-store"
    return response
