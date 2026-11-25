import json
import logging
import uuid

from apps.common.logging import SafeJsonFormatter, request_id_context


def test_logging_omits_untrusted_payloads_and_exception_messages():
    record = logging.LogRecord(
        "django.request", logging.ERROR, __file__, 1, "password=secret", (), None
    )
    record.request = {"password": "secret"}
    record.exc_info = (ValueError, ValueError("secret-provider-key"), None)
    output = SafeJsonFormatter().format(record)
    parsed = json.loads(output)
    assert parsed["exception_type"] == "ValueError"
    assert "secret" not in output
    assert "request" not in parsed


def test_request_id_is_validated_and_context_is_cleared(client):
    response = client.get("/health/live/?token=secret", HTTP_X_REQUEST_ID="unsafe\nsecret")
    uuid.UUID(response["X-Request-ID"])
    assert request_id_context.get() is None
    supplied = str(uuid.uuid4())
    response = client.get("/health/live/", HTTP_X_REQUEST_ID=supplied)
    assert response["X-Request-ID"] == supplied
