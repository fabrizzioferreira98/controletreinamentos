from __future__ import annotations

import os
import logging
import sys
from pathlib import Path

from waitress import serve

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from backend.src.controle_treinamentos import create_app


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = (os.getenv(name, "") or "").strip()
    if not raw:
        return max(minimum, default)
    try:
        return max(minimum, int(raw))
    except ValueError:
        return max(minimum, default)


def _trusted_proxy_headers() -> set[str]:
    raw = (os.getenv("WAITRESS_TRUSTED_PROXY_HEADERS", "") or "").replace(",", " ")
    headers = {item.strip().lower() for item in raw.split() if item.strip()}
    if headers:
        return headers
    return {
        "x-forwarded-for",
        "x-forwarded-host",
        "x-forwarded-proto",
        "x-forwarded-port",
    }


def _configure_waitress_queue_logger(app) -> None:
    raw_level = (os.getenv("WAITRESS_QUEUE_LOG_LEVEL", "") or "").strip().upper() or "WARNING"
    level = getattr(logging, raw_level, None)
    if not isinstance(level, int):
        level = logging.WARNING
        raw_level = "WARNING"
    logging.getLogger("waitress.queue").setLevel(level)
    app.logger.info(
        "Waitress queue logger configured.",
        extra={
            "event": "logger_configured",
            "component": "waitress.queue",
            "configured_level": raw_level,
        },
    )


def main() -> int:
    app = create_app()
    _configure_waitress_queue_logger(app)
    host = (os.getenv("WAITRESS_HOST", "") or "").strip() or "127.0.0.1"
    port = _env_int("PORT", 8100, minimum=1)
    kwargs = {
        "host": host,
        "port": port,
        "threads": _env_int("WAITRESS_THREADS", 8, minimum=2),
        "connection_limit": _env_int("WAITRESS_CONNECTION_LIMIT", 100, minimum=10),
        "channel_timeout": _env_int("WAITRESS_CHANNEL_TIMEOUT", 120, minimum=30),
        "cleanup_interval": _env_int("WAITRESS_CLEANUP_INTERVAL", 30, minimum=5),
        "ident": (os.getenv("WAITRESS_IDENT", "") or "").strip() or "controle-treinamentos",
        "clear_untrusted_proxy_headers": _env_flag("WAITRESS_CLEAR_UNTRUSTED_PROXY_HEADERS", default=True),
        "log_untrusted_proxy_headers": _env_flag("WAITRESS_LOG_UNTRUSTED_PROXY_HEADERS", default=False),
    }

    trusted_proxy = (os.getenv("WAITRESS_TRUSTED_PROXY", "") or "").strip()
    if trusted_proxy:
        kwargs["trusted_proxy"] = trusted_proxy
        kwargs["trusted_proxy_count"] = _env_int("WAITRESS_TRUSTED_PROXY_COUNT", 1, minimum=1)
        kwargs["trusted_proxy_headers"] = _trusted_proxy_headers()

    app.logger.info(
        "Waitress server starting.",
        extra={
            "event": "server_startup",
            "component": "waitress",
            "host": host,
            "port": port,
            "threads": kwargs["threads"],
            "connection_limit": kwargs["connection_limit"],
            "trusted_proxy": trusted_proxy or "",
            "pid": os.getpid(),
        },
    )
    exit_code = 0
    try:
        serve(app, **kwargs)
        return exit_code
    except Exception:
        exit_code = 1
        app.logger.exception(
            "Waitress server stopped unexpectedly.",
            extra={
                "event": "server_unexpected_shutdown",
                "component": "waitress",
                "host": host,
                "port": port,
                "pid": os.getpid(),
            },
        )
        raise
    finally:
        app.logger.info(
            "Waitress server stopped.",
            extra={
                "event": "server_shutdown",
                "component": "waitress",
                "host": host,
                "port": port,
                "exit_code": exit_code,
                "pid": os.getpid(),
            },
        )


if __name__ == "__main__":
    raise SystemExit(main())
