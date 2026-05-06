from __future__ import annotations

import os
import time
from uuid import uuid4

from flask import current_app, g, has_request_context, session
from flask_login import logout_user

from .domain_errors import DomainError


AUTH_REQUIRED_MESSAGE = "Autenticação obrigatória ou sessão expirada."
AUTH_USER_INACTIVE_MESSAGE = "Usuário inativo. Contate o administrador."
AUTH_BACKEND_UNAVAILABLE_MESSAGE = "Autenticação indisponível por falha temporária no backend de sessão."
CSRF_ERROR_MESSAGE = "CSRF inválido ou sessão expirada. Atualize a página e tente novamente."


AUTH_SESSION_EXPIRED_MESSAGE = "Sessao expirada. Entre novamente para continuar."
AUTH_SESSION_INVALID_MESSAGE = "Sessao invalida ou revogada. Entre novamente para continuar."

AUTH_SESSION_META_KEYS = {
    "auth_session_id",
    "auth_session_created_at",
    "auth_session_last_seen_at",
    "auth_session_expires_at",
    "auth_session_mode",
    "auth_session_remember",
}


class AuthRequiredError(DomainError):
    status = 401
    code = "auth_required"

    def __init__(self, message: str = AUTH_REQUIRED_MESSAGE):
        super().__init__(message, status=self.status, code=self.code)


class AuthUserInactiveError(DomainError):
    status = 403
    code = "auth_user_inactive"

    def __init__(self, message: str = AUTH_USER_INACTIVE_MESSAGE):
        super().__init__(message, status=self.status, code=self.code)


class AuthBackendUnavailableError(DomainError):
    status = 503
    code = "auth_backend_unavailable"

    def __init__(self, message: str = AUTH_BACKEND_UNAVAILABLE_MESSAGE):
        super().__init__(message, status=self.status, code=self.code)


class AuthSessionExpiredError(DomainError):
    status = 401
    code = "auth_session_expired"

    def __init__(self, message: str = AUTH_SESSION_EXPIRED_MESSAGE):
        super().__init__(message, status=self.status, code=self.code)


class AuthSessionInvalidError(DomainError):
    status = 401
    code = "auth_session_invalid"

    def __init__(self, message: str = AUTH_SESSION_INVALID_MESSAGE):
        super().__init__(message, status=self.status, code=self.code)


class CsrfSemanticError(DomainError):
    status = 400
    code = "csrf_error"

    def __init__(self, message: str = CSRF_ERROR_MESSAGE):
        super().__init__(message, status=self.status, code=self.code)


def _now_ts() -> int:
    return int(time.time())


def _session_lifetime_seconds() -> int:
    raw_lifetime = current_app.config.get("PERMANENT_SESSION_LIFETIME") if has_request_context() else None
    try:
        return max(60, int(raw_lifetime.total_seconds()))
    except AttributeError:
        try:
            return max(60, int(raw_lifetime))
        except (TypeError, ValueError):
            return 8 * 60 * 60


def _session_touch_interval_seconds() -> int:
    raw_interval = (
        current_app.config.get("AUTH_SESSION_TOUCH_INTERVAL_SECONDS")
        if has_request_context()
        else None
    )
    if raw_interval is None:
        raw_interval = os.getenv("AUTH_SESSION_TOUCH_INTERVAL_SECONDS", "30")
    try:
        return max(0, int(raw_interval))
    except (TypeError, ValueError):
        return 30


def _coerce_ts(value) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def establish_auth_session(*, remember_requested: bool) -> None:
    now = _now_ts()
    lifetime = _session_lifetime_seconds()
    session.permanent = bool(remember_requested)
    session["auth_session_id"] = uuid4().hex
    session["auth_session_created_at"] = now
    session["auth_session_last_seen_at"] = now
    session["auth_session_expires_at"] = now + lifetime
    session["auth_session_mode"] = "permanent" if remember_requested else "browser"
    session["auth_session_remember"] = bool(remember_requested)


def touch_auth_session() -> None:
    if not has_request_context() or not session.get("_user_id"):
        return
    now = _now_ts()
    lifetime = _session_lifetime_seconds()
    touch_interval = _session_touch_interval_seconds()
    last_seen_at = _coerce_ts(session.get("auth_session_last_seen_at"))
    expires_at = _coerce_ts(session.get("auth_session_expires_at"))
    if (
        touch_interval > 0
        and last_seen_at is not None
        and now - last_seen_at < touch_interval
        and (expires_at is None or expires_at - now > touch_interval)
    ):
        return
    if not session.get("auth_session_id"):
        session["auth_session_id"] = uuid4().hex
    session.setdefault("auth_session_created_at", now)
    session.setdefault("auth_session_mode", "permanent" if session.permanent else "browser")
    session.setdefault("auth_session_remember", bool(session.permanent))
    session["auth_session_last_seen_at"] = now
    session["auth_session_expires_at"] = now + lifetime


def expire_auth_session_if_needed() -> bool:
    if not has_request_context() or not session.get("_user_id"):
        return False
    expires_at = _coerce_ts(session.get("auth_session_expires_at"))
    if expires_at is None or expires_at > _now_ts():
        return False
    g.auth_session_expired = True
    clear_auth_session()
    return True


def auth_session_payload(*, authenticated: bool) -> dict:
    expired = bool(getattr(g, "auth_session_expired", False)) if has_request_context() else False
    invalid = bool(getattr(g, "auth_session_invalid", False)) if has_request_context() else False
    snapshot_used = bool(getattr(g, "auth_session_snapshot_used", False)) if has_request_context() else False
    state = "authenticated" if authenticated else "anonymous"
    if expired:
        state = "expired"
    elif invalid:
        state = "invalid"

    return {
        "state": state,
        "mode": session.get("auth_session_mode") if authenticated else None,
        "remember": bool(session.get("auth_session_remember")) if authenticated else False,
        "permanent": bool(session.permanent) if authenticated else False,
        "created_at": _coerce_ts(session.get("auth_session_created_at")) if authenticated else None,
        "last_seen_at": _coerce_ts(session.get("auth_session_last_seen_at")) if authenticated else None,
        "expires_at": _coerce_ts(session.get("auth_session_expires_at")) if authenticated else None,
        "backend_verified": bool(authenticated and not snapshot_used),
        "snapshot": {
            "used": snapshot_used,
            "age_seconds": getattr(g, "auth_session_snapshot_age_seconds", None) if snapshot_used else None,
        },
    }


def clear_auth_session(*, clear_remember: bool = True) -> None:
    try:
        logout_user()
    except Exception:
        pass
    session.clear()
    if clear_remember:
        session["_remember"] = "clear"
