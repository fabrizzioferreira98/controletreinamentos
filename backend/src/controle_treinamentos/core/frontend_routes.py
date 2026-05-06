from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlencode

from flask import has_request_context, redirect, request


def frontend_public_origin() -> str:
    return (os.getenv("FRONTEND_PUBLIC_ORIGIN", "") or "").strip().rstrip("/")


def frontend_local_origin() -> str:
    return (os.getenv("FRONTEND_LOCAL_ORIGIN", "") or "").strip().rstrip("/")


def _request_host_parts() -> tuple[str, str]:
    if not has_request_context():
        return "", ""
    host = (request.host or "").strip().lower()
    if not host:
        return "", ""
    if ":" in host:
        return host.rsplit(":", 1)
    return host, ""


def _request_origin() -> str:
    if not has_request_context():
        return ""
    scheme = (request.scheme or "").strip().lower()
    host = (request.host or "").strip()
    if not scheme or not host:
        return ""
    return f"{scheme}://{host}".rstrip("/")


def _request_targets_local_surface() -> bool:
    hostname, _port = _request_host_parts()
    if not hostname:
        return False
    if hostname in {"127.0.0.1", "localhost"}:
        return True
    try:
        return ipaddress.ip_address(hostname).is_private
    except ValueError:
        return False


def _request_targets_direct_backend() -> bool:
    hostname, port = _request_host_parts()
    if not hostname:
        return False
    if port not in {"8101", "8102"}:
        return False
    return _request_targets_local_surface()


def _request_targets_same_origin_frontend() -> bool:
    request_origin = _request_origin()
    hostname, _port = _request_host_parts()
    if not request_origin or not hostname:
        return False
    return hostname != "localhost" and not _request_targets_direct_backend()


def frontend_redirect_origin() -> str:
    local_origin = frontend_local_origin()
    if local_origin and _request_targets_direct_backend():
        return local_origin
    request_origin = _request_origin()
    hostname, _port = _request_host_parts()
    # When the request already arrived through Caddy on a valid host
    # (public domain or private LAN IP without the backend port),
    # keep the user on that same origin instead of forcing a stale public one.
    if request_origin and hostname and hostname != "localhost" and not _request_targets_direct_backend():
        return request_origin
    return frontend_public_origin() or local_origin or request_origin


def frontend_official_enabled() -> bool:
    return bool(frontend_public_origin() or frontend_local_origin() or _request_targets_same_origin_frontend())


def frontend_compat_enabled() -> bool:
    if not frontend_official_enabled():
        return False
    raw = (os.getenv("FRONTEND_COMPAT_REDIRECTS", "1") or "").strip().lower()
    return raw not in {"0", "false", "off", "no"}


def build_frontend_url(hash_path: str, *, query: dict | None = None) -> str:
    origin = frontend_redirect_origin()
    if not origin:
        raise RuntimeError("FRONTEND_PUBLIC_ORIGIN nao configurado.")
    normalized_hash = (hash_path or "").strip()
    if not normalized_hash.startswith("#/"):
        raise ValueError("Hash route invalida para frontend.")
    encoded_query = urlencode(
        [(key, value) for key, value in (query or {}).items() if value not in ("", None)],
        doseq=True,
    )
    return f"{origin}/{normalized_hash}{f'?{encoded_query}' if encoded_query else ''}"


def redirect_to_frontend(hash_path: str, *, query: dict | None = None):
    return redirect(build_frontend_url(hash_path, query=query))


def redirect_to_frontend_app():
    origin = frontend_redirect_origin()
    if not origin:
        raise RuntimeError("FRONTEND_PUBLIC_ORIGIN nao configurado.")
    return redirect(f"{origin}/")
