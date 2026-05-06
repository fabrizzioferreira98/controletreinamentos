from __future__ import annotations

import os

from flask import Response, request


def _normalize_origin(value: str) -> str:
    return (value or "").strip().rstrip("/")


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.replace("\n", ",").split(",") if item.strip()]


def resolve_allowed_origins() -> set[str]:
    origins = {
        _normalize_origin(item)
        for item in _split_csv(os.getenv("FRONTEND_ALLOWED_ORIGINS"))
        if _normalize_origin(item)
    }
    frontend_public_origin = _normalize_origin(os.getenv("FRONTEND_PUBLIC_ORIGIN", ""))
    if frontend_public_origin:
        origins.add(frontend_public_origin)
    return origins


def is_cors_api_request() -> bool:
    path = (request.path or "").strip().lower()
    return path.startswith("/api/")


def is_allowed_origin(origin: str | None, *, allowed_origins: set[str]) -> bool:
    normalized = _normalize_origin(origin or "")
    if not normalized:
        return False
    return normalized in allowed_origins


def _cors_headers(origin: str) -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-CSRFToken, X-Requested-With, X-Request-ID",
        "Access-Control-Expose-Headers": "X-Request-ID, ETag",
        "Vary": "Origin",
    }


def configure_cors(app) -> None:
    allowed_origins = resolve_allowed_origins()
    app.config["FRONTEND_ALLOWED_ORIGINS"] = allowed_origins

    @app.before_request
    def handle_api_preflight():
        origin = request.headers.get("Origin")
        if request.method != "OPTIONS" or not is_cors_api_request():
            return None
        if not is_allowed_origin(origin, allowed_origins=allowed_origins):
            return None
        response = Response(status=204)
        for key, value in _cors_headers(_normalize_origin(origin or "")).items():
            response.headers[key] = value
        return response

    @app.after_request
    def apply_api_cors_headers(response):
        origin = request.headers.get("Origin")
        if not is_cors_api_request():
            return response
        if not is_allowed_origin(origin, allowed_origins=allowed_origins):
            return response
        for key, value in _cors_headers(_normalize_origin(origin or "")).items():
            response.headers.setdefault(key, value)
        return response
