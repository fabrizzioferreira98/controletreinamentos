"""Structured JSON logging with request_id injection."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any


_RESERVED_LOG_RECORD_KEYS = set(
    logging.LogRecord(
        name="",
        level=0,
        pathname="",
        lineno=0,
        msg="",
        args=(),
        exc_info=None,
    ).__dict__
) | {"asctime", "message", "request_id", "correlation_id"}


def _extra_payload(record: logging.LogRecord) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in record.__dict__.items():
        if key in _RESERVED_LOG_RECORD_KEYS or key.startswith("_"):
            continue
        payload[key] = value
    return payload


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
        if hasattr(record, "correlation_id"):
            payload["correlation_id"] = record.correlation_id
        payload.update(_extra_payload(record))
        if record.exc_info and record.exc_info[1]:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class RequestIdFilter(logging.Filter):
    """Injects Flask trace context into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        explicit_request_id = getattr(record, "request_id", None)
        explicit_correlation_id = getattr(record, "correlation_id", None)
        try:
            from flask import g
            context_request_id = getattr(g, "request_id", None)
            context_correlation_id = getattr(g, "correlation_id", None)
        except RuntimeError:
            context_request_id = None
            context_correlation_id = None
        record.request_id = context_request_id or explicit_request_id  # type: ignore[attr-defined]
        record.correlation_id = context_correlation_id or explicit_correlation_id  # type: ignore[attr-defined]
        return True


def configure_structured_logging(app) -> None:
    """Replace Flask's default handler with JSON structured logging."""
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    handler.addFilter(RequestIdFilter())

    app.logger.handlers.clear()
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
    app.logger.propagate = False


def configure_cli_logger(name: str = "controle_treinamentos") -> logging.Logger:
    """Return a JSON logger for operational scripts that do not create Flask."""
    logger = logging.getLogger(name)
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    handler.addFilter(RequestIdFilter())

    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger
