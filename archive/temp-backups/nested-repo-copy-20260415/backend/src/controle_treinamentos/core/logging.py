"""Structured JSON logging with request_id injection."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Emits log records as single-line JSON for structured log ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if hasattr(record, "request_id"):
            payload["request_id"] = record.request_id
        if record.exc_info and record.exc_info[1]:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class RequestIdFilter(logging.Filter):
    """Injects g.request_id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            from flask import g
            record.request_id = getattr(g, "request_id", None)  # type: ignore[attr-defined]
        except RuntimeError:
            record.request_id = None  # type: ignore[attr-defined]
        return True


def configure_structured_logging(app) -> None:
    """Replace Flask's default handler with JSON structured logging."""
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    handler.addFilter(RequestIdFilter())

    app.logger.handlers.clear()
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
