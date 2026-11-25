"""Allowlisted JSON fields; never serialize request bodies, query strings or exceptions."""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_context = ContextVar("request_id", default=None)


class SafeJsonFormatter(logging.Formatter):
    def format(self, record):
        # Third-party messages may contain SQL, URLs, task args or credentials.
        # Only application-owned, fixed event names are emitted verbatim.
        event = record.msg if record.name.startswith("apps.") else "library_event"
        if not isinstance(event, str) or not event.replace("_", "").isalnum():
            event = "application_event"
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": event,
        }
        request_id = request_id_context.get()
        if request_id:
            payload["request_id"] = request_id
        for key in ("status_code", "duration_ms", "method", "route", "dependency"):
            value = getattr(record, key, None)
            if isinstance(value, (str, int, float)):
                payload[key] = value
        if record.exc_info and record.exc_info[0]:
            payload["exception_type"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=True, allow_nan=False)
