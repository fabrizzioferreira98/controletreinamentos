import json
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

from flask import abort, g, redirect, request, url_for
from flask_login import current_user

REQUESTS_TOTAL = Counter("http_requests_total", "Total HTTP Requests", ["method", "endpoint", "status"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "HTTP Request Latency", ["method", "endpoint"])

from ..auth import is_endpoint_permitted  # noqa: E402
from .http_utils import (  # noqa: E402
    error_payload,
    expects_binary_asset_response,
    expects_json_response,
    safe_next_url,
)


def configure_security_headers(app, *, is_secure_env: bool = True, emit_hsts: bool | None = None):
    if emit_hsts is None:
        emit_hsts = is_secure_env

    @app.before_request
    def attach_request_context():
        g.request_started_at = time.monotonic()
        incoming_request_id = (request.headers.get("X-Request-ID", "") or "").strip()
        g.request_id = incoming_request_id or uuid4().hex
        if sentry_sdk:
            sentry_sdk.set_tag("request_id", g.request_id)
        if sentry_sdk and current_user and current_user.is_authenticated:
            sentry_sdk.set_user({"id": current_user.id, "email": getattr(current_user, "email", None)})

    @app.before_request
    def enforce_endpoint_permissions():
        endpoint = request.endpoint
        if not endpoint or endpoint == "static":
            return None
        if endpoint in {"auth.login", "auth.logout"}:
            return None
        _ = current_user.is_authenticated
        if getattr(g, "auth_backend_unavailable", False):
            if expects_json_response():
                return error_payload(
                    "Autenticação indisponível por falha temporária no backend de sessão.",
                    status=503,
                    code="auth_backend_unavailable",
                )
            if expects_binary_asset_response():
                return "", 503
            next_url = safe_next_url(
                request.full_path if request.method == "GET" else None,
                url_for("dashboard.dashboard"),
            )
            return redirect(url_for("auth.login", next=next_url, auth_issue="backend_unavailable"))
        if not is_endpoint_permitted(current_user, endpoint):
            if expects_json_response():
                if current_user.is_authenticated:
                    return error_payload("Acesso negado para esta operação.", status=403, code="forbidden")
                return error_payload("Autenticação obrigatória ou sessão expirada.", status=401, code="auth_required")
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
            "style-src 'self' 'unsafe-inline' https://unpkg.com; "
            "script-src 'self' 'unsafe-inline' https://unpkg.com; "
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

        started_at = getattr(g, "request_started_at", None)
        duration_ms = int((time.monotonic() - started_at) * 1000) if started_at else None

        endpoint = request.endpoint or "not_found"
        method = request.method
        status = str(response.status_code)

        REQUESTS_TOTAL.labels(method, endpoint, status).inc()
        if duration_ms is not None:
            REQUEST_LATENCY.labels(method, endpoint).observe(duration_ms / 1000.0)

        app.logger.info(
            json.dumps(
                {
                    "event": "http_request",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.path,
                    "endpoint": request.endpoint,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                    "user_id": getattr(current_user, "id", None) if current_user.is_authenticated else None,
                },
                ensure_ascii=False,
            )
        )
        return response
