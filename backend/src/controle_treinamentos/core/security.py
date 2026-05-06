import os
import re
import time
from uuid import uuid4

try:
    import sentry_sdk
except ImportError:
    sentry_sdk = None

try:
    from prometheus_client import Counter, Histogram
except ImportError:
    class MockMetric:
        def __init__(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self
        def inc(self, *args, **kwargs): pass
        def observe(self, *args, **kwargs): pass
    Counter = Histogram = MockMetric

from flask import abort, flash, g, redirect, request, session, url_for
from flask_login import current_user

REQUESTS_TOTAL = Counter("http_requests_total", "Total HTTP Requests", ["method", "endpoint", "status"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "HTTP Request Latency", ["method", "endpoint"])

from ..auth import is_endpoint_permitted  # noqa: E402
from .auth_contract import (  # noqa: E402
    AuthBackendUnavailableError,
    AuthRequiredError,
    AuthSessionExpiredError,
    AuthSessionInvalidError,
    AuthUserInactiveError,
    clear_auth_session,
    expire_auth_session_if_needed,
    touch_auth_session,
)
from .cors import is_allowed_origin, is_cors_api_request  # noqa: E402
from .domain_errors import DomainForbiddenError  # noqa: E402
from .http_utils import (  # noqa: E402
    domain_error_payload,
    expects_binary_asset_response,
    expects_json_response,
    safe_next_url,
)


API_SESSION_SELF_SERVICE_ENDPOINTS = {"auth.api_session_login", "auth.api_session_logout"}
SESSION_SELF_SERVICE_ENDPOINTS = API_SESSION_SELF_SERVICE_ENDPOINTS | {"auth.login", "auth.logout"}
_TRACE_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, minimum: int = 0) -> int:
    raw = (os.getenv(name, "") or "").strip()
    if not raw:
        return max(minimum, default)
    try:
        return max(minimum, int(raw))
    except ValueError:
        return max(minimum, default)


def _should_emit_http_request_log(status_code: int, duration_ms: int | None) -> bool:
    if _env_flag("HTTP_ACCESS_LOG_ENABLED", default=False):
        return True
    if int(status_code or 0) >= 500:
        return True
    if duration_ms is None:
        return False
    slow_threshold_ms = _env_int("HTTP_ACCESS_LOG_SLOW_MS", 1000, minimum=1)
    return duration_ms >= slow_threshold_ms


def _safe_trace_id(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw or not _TRACE_ID_RE.match(raw):
        return ""
    return raw


def _auth_session_metadata_is_expired() -> bool:
    if not session.get("_user_id"):
        return False
    try:
        expires_at = int(session.get("auth_session_expires_at") or 0)
    except (TypeError, ValueError):
        return False
    return expires_at > 0 and expires_at <= int(time.time())


def configure_security_headers(app, *, is_secure_env: bool = True, emit_hsts: bool | None = None):
    if emit_hsts is None:
        emit_hsts = is_secure_env

    @app.before_request
    def attach_request_context():
        g.request_started_at = time.monotonic()
        incoming_request_id = _safe_trace_id(request.headers.get("X-Request-ID", ""))
        incoming_correlation_id = _safe_trace_id(request.headers.get("X-Correlation-ID", ""))
        g.request_id = incoming_request_id or uuid4().hex
        g.correlation_id = incoming_correlation_id or g.request_id
        if sentry_sdk:
            sentry_sdk.set_tag("request_id", g.request_id)
            sentry_sdk.set_tag("correlation_id", g.correlation_id)
        if (
            sentry_sdk
            and request.endpoint not in SESSION_SELF_SERVICE_ENDPOINTS
            and not _auth_session_metadata_is_expired()
            and current_user
            and current_user.is_authenticated
        ):
            sentry_sdk.set_user({"id": current_user.id, "email": getattr(current_user, "email", None)})

    @app.before_request
    def enforce_endpoint_permissions():
        endpoint = request.endpoint
        if not endpoint or endpoint == "static":
            return None
        if endpoint in API_SESSION_SELF_SERVICE_ENDPOINTS:
            return None
        if expire_auth_session_if_needed():
            error = AuthSessionExpiredError()
            if endpoint not in {"auth.login", "auth.logout"} and expects_json_response():
                return domain_error_payload(error)
            if expects_binary_asset_response():
                return "", error.status
            flash(error.message, "warning")
            return redirect(url_for("auth.login", auth_issue="session_expired"))
        if (
            request.method == "OPTIONS"
            and request.headers.get("Access-Control-Request-Method")
            and is_cors_api_request()
            and is_allowed_origin(
                request.headers.get("Origin"),
                allowed_origins=app.config.get("FRONTEND_ALLOWED_ORIGINS", set()),
            )
        ):
            return None
        if endpoint in {"auth.login", "auth.logout"}:
            return None
        _ = current_user.is_authenticated
        if getattr(g, "auth_user_inactive", False):
            error = AuthUserInactiveError()
            clear_auth_session()
            if expects_json_response():
                return domain_error_payload(error)
            if expects_binary_asset_response():
                return "", error.status
            flash(error.message, "error")
            return redirect(url_for("auth.login", auth_issue="user_inactive"))
        if getattr(g, "auth_backend_unavailable", False):
            error = AuthBackendUnavailableError()
            if expects_json_response():
                return domain_error_payload(error)
            if expects_binary_asset_response():
                return "", 503
            next_url = safe_next_url(
                request.full_path if request.method == "GET" else None,
                url_for("dashboard.dashboard"),
            )
            return redirect(url_for("auth.login", next=next_url, auth_issue="backend_unavailable"))
        if getattr(g, "auth_session_invalid", False):
            error = AuthSessionInvalidError()
            clear_auth_session()
            if expects_json_response():
                return domain_error_payload(error)
            if expects_binary_asset_response():
                return "", error.status
            flash(error.message, "warning")
            return redirect(url_for("auth.login", auth_issue="session_invalid"))
        if not is_endpoint_permitted(current_user, endpoint):
            if expects_json_response():
                if current_user.is_authenticated:
                    return domain_error_payload(
                        DomainForbiddenError("Acesso negado para esta operação.", code="forbidden")
                    )
                return domain_error_payload(AuthRequiredError())
            if expects_binary_asset_response():
                if current_user.is_authenticated:
                    return "", 403
                return "", 401
            if current_user.is_authenticated:
                abort(403)
            next_url = safe_next_url(
                request.full_path if request.method == "GET" else None,
                url_for("dashboard.dashboard"),
            )
            return redirect(url_for("auth.login", next=next_url))
        return None

    @app.after_request
    def apply_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: https://*.tile.openstreetmap.org https://tile.openstreetmap.org; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; "
            "base-uri 'self'; frame-ancestors 'self'; form-action 'self'",
        )
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if response.mimetype == "text/html":
            response.headers.setdefault("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            response.headers.setdefault("Pragma", "no-cache")
            response.headers.setdefault("Expires", "0")
        if emit_hsts and request.is_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

        request_id = getattr(g, "request_id", None)
        if request_id:
            response.headers.setdefault("X-Request-ID", request_id)
        correlation_id = getattr(g, "correlation_id", None)
        if correlation_id:
            response.headers.setdefault("X-Correlation-ID", correlation_id)
        release_id = (app.config.get("APP_RELEASE_ID") or "").strip()
        if release_id:
            response.headers.setdefault("X-Release-ID", release_id)
        release_instance_id = (app.config.get("APP_RELEASE_INSTANCE_ID") or "").strip()
        if release_instance_id:
            response.headers.setdefault("X-Release-Instance-ID", release_instance_id)

        started_at = getattr(g, "request_started_at", None)
        duration_ms = int((time.monotonic() - started_at) * 1000) if started_at else None

        endpoint = request.endpoint or "not_found"
        method = request.method
        status = str(response.status_code)

        REQUESTS_TOTAL.labels(method, endpoint, status).inc()
        if duration_ms is not None:
            REQUEST_LATENCY.labels(method, endpoint).observe(duration_ms / 1000.0)

        authenticated_for_session_touch = False
        user_id_for_log = None
        if request.endpoint not in SESSION_SELF_SERVICE_ENDPOINTS and not _auth_session_metadata_is_expired():
            authenticated_for_session_touch = current_user.is_authenticated
            if authenticated_for_session_touch:
                user_id_for_log = getattr(current_user, "id", None)

        if _should_emit_http_request_log(response.status_code, duration_ms):
            app.logger.info(
                "HTTP request completed.",
                extra={
                    "event": "http_request",
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                    "release_id": app.config.get("APP_RELEASE_ID") or "",
                    "method": request.method,
                    "path": request.path,
                    "endpoint": request.endpoint,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                    "user_id": user_id_for_log,
                },
            )
        if (
            authenticated_for_session_touch
            and not getattr(g, "auth_backend_unavailable", False)
            and not getattr(g, "auth_session_snapshot_used", False)
        ):
            touch_auth_session()
        return response
