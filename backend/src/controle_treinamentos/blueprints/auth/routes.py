try:
    import psycopg2
except ImportError:
    psycopg2 = None  # type: ignore[assignment]
import time
from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Optional, Union

from flask import current_app, flash, g, redirect, render_template, request, session, url_for
from flask_login import current_user, login_user
from flask_wtf.csrf import generate_csrf
from werkzeug.security import check_password_hash

from ...auth import MODULE_PERMISSION_GROUPS, resolve_landing_url_for_user
from ...core.audit_utils import (
    clear_login_failures,
    login_attempt_state,
    register_login_failure,
)
from ...core.domain_errors import DomainError
from ...core.auth_contract import (
    AuthBackendUnavailableError,
    AuthRequiredError,
    auth_session_payload,
    clear_auth_session,
    establish_auth_session,
    touch_auth_session,
)
from ...core.http_utils import (
    domain_error_payload,
    get_optional_text,
    get_required_text,
    safe_next_url,
)
from ...core.frontend_routes import frontend_official_enabled, redirect_to_frontend, redirect_to_frontend_app
from ...core.rate_limit import login_limiter
from ...db import (
    DatabaseConfigurationError,
    DatabasePoolExhaustedError,
    DatabaseUnavailableError,
    get_db,
)
from . import auth_bp


class _NoopMetric:
    def labels(self, *_args, **_kwargs):
        return self

    def inc(self, *_args, **_kwargs):
        return None

try:
    from prometheus_client import Counter, REGISTRY
except ImportError:
    class _MockMetric:
        def __init__(self, *_args, **_kwargs):
            return None

        def labels(self, *_args, **_kwargs):
            return self

        def inc(self, *_args, **_kwargs):
            return None

    Counter = _MockMetric  # type: ignore[misc,assignment]
    REGISTRY = None  # type: ignore[assignment]


def _build_auth_events_counter():
    try:
        return Counter(
            "auth_events_total",
            "Total auth flow outcomes",
            ["outcome", "channel"],
        )
    except ValueError:
        if REGISTRY is not None:
            existing = getattr(REGISTRY, "_names_to_collectors", {}).get("auth_events_total")
            if existing is not None:
                return existing
        return _NoopMetric()


AUTH_EVENTS_TOTAL = _build_auth_events_counter()

_AUTH_FAILURE_TIMESTAMPS: deque[float] = deque()
_AUTH_FAILURE_LOCK = Lock()
_LAST_AUTH_ALERT_AT = 0.0


def _login_unavailable_message(*, kind: str = "infrastructure") -> str:
    _messages = {
        "configuration": "Autenticação indisponível por erro de configuração do ambiente. Contate o administrador.",
        "database": "Autenticação indisponível por falha de banco de dados. Tente novamente em instantes.",
        "session": "Autenticação indisponível por falha de sessão. Tente novamente em instantes.",
        "pool_exhausted": "Autenticação indisponível por sobrecarga momentânea. Tente novamente em instantes.",
        "connection_timeout": "Autenticação indisponível por lentidão na conexão. Tente novamente em instantes.",
    }
    message = _messages.get(kind, "Falha temporária na autenticação. Tente novamente em instantes.")
    request_id = getattr(g, "request_id", None)
    if request_id:
        return f"{message} Código: {request_id}"
    return message


def _auth_channel() -> str:
    return "html"


def _record_auth_outcome(
    *,
    outcome: str,
    login_value: Optional[str] = None,
    user_id: Optional[Union[str, int]] = None,
    status: Optional[int] = None,
    channel: Optional[str] = None,
):
    resolved_channel = channel or _auth_channel()
    AUTH_EVENTS_TOTAL.labels(outcome, resolved_channel).inc()
    current_app.logger.info(
        "Authentication outcome recorded.",
        extra={
            "event": "auth_outcome",
            "request_id": getattr(g, "request_id", None),
            "outcome": outcome,
            "channel": resolved_channel,
            "status": status,
            "path": request.path,
            "method": request.method,
            "user_id": user_id,
            "login": (login_value or "")[:120],
        },
    )
    if outcome in {
        "auth_invalid_credentials",
        "auth_user_inactive",
        "auth_backend_unavailable",
        "auth_backend_misconfigured",
        "auth_database_error",
        "auth_session_error",
        "auth_pool_exhausted",
        "auth_connection_timeout",
    }:
        _track_auth_failure_surge()


def _track_auth_failure_surge() -> None:
    global _LAST_AUTH_ALERT_AT
    now = time.time()
    threshold = max(5, int((current_app.config.get("AUTH_FAILURE_ALERT_THRESHOLD") or 20)))
    window_seconds = max(30, int((current_app.config.get("AUTH_FAILURE_ALERT_WINDOW_SECONDS") or 300)))
    min_alert_interval_seconds = max(
        15, int((current_app.config.get("AUTH_FAILURE_ALERT_MIN_INTERVAL_SECONDS") or 60))
    )
    with _AUTH_FAILURE_LOCK:
        _AUTH_FAILURE_TIMESTAMPS.append(now)
        cutoff = now - window_seconds
        while _AUTH_FAILURE_TIMESTAMPS and _AUTH_FAILURE_TIMESTAMPS[0] < cutoff:
            _AUTH_FAILURE_TIMESTAMPS.popleft()
        if len(_AUTH_FAILURE_TIMESTAMPS) >= threshold and (now - _LAST_AUTH_ALERT_AT) >= min_alert_interval_seconds:
            _LAST_AUTH_ALERT_AT = now
            current_app.logger.warning(
                "ALERT auth_failure_surge detected.",
                extra={
                    "event": "auth_failure_surge",
                    "count": len(_AUTH_FAILURE_TIMESTAMPS),
                    "window_seconds": window_seconds,
                    "request_id": getattr(g, "request_id", None),
                },
            )


def auth_failure_surge_snapshot(*, now: float | None = None) -> dict:
    current_time = time.time() if now is None else float(now)
    threshold = max(5, int((current_app.config.get("AUTH_FAILURE_ALERT_THRESHOLD") or 20)))
    window_seconds = max(30, int((current_app.config.get("AUTH_FAILURE_ALERT_WINDOW_SECONDS") or 300)))
    min_alert_interval_seconds = max(
        15, int((current_app.config.get("AUTH_FAILURE_ALERT_MIN_INTERVAL_SECONDS") or 60))
    )
    attention_threshold = max(3, threshold // 2)
    with _AUTH_FAILURE_LOCK:
        cutoff = current_time - window_seconds
        while _AUTH_FAILURE_TIMESTAMPS and _AUTH_FAILURE_TIMESTAMPS[0] < cutoff:
            _AUTH_FAILURE_TIMESTAMPS.popleft()
        count = len(_AUTH_FAILURE_TIMESTAMPS)
        last_alert_at = float(_LAST_AUTH_ALERT_AT or 0.0)

    if count >= threshold:
        status_key = "degraded"
        message = f"Surto de falhas de autenticacao: {count}/{threshold} em {window_seconds}s."
    elif count >= attention_threshold:
        status_key = "attention"
        message = f"Falhas de autenticacao em atencao: {count}/{threshold} em {window_seconds}s."
    else:
        status_key = "operational"
        message = f"Falhas recentes de autenticacao dentro do esperado: {count}/{threshold} em {window_seconds}s."

    return {
        "count": count,
        "threshold": threshold,
        "attention_threshold": attention_threshold,
        "window_seconds": window_seconds,
        "min_alert_interval_seconds": min_alert_interval_seconds,
        "last_alert_at": last_alert_at,
        "last_alert_age_seconds": current_time - last_alert_at if last_alert_at else None,
        "status_key": status_key,
        "message": message,
    }


from ...core.errors import _remember_error_event
from ...repositories.user_repository import UserRepository

def _login_next_url(*, user=None) -> str:
    fallback = resolve_landing_url_for_user(user or current_user)
    return safe_next_url(
        request.args.get("next") or request.form.get("next"),
        fallback,
    )


def _frontend_login_query() -> dict[str, str]:
    query: dict[str, str] = {}
    next_url = safe_next_url(request.args.get("next") or request.form.get("next"), "")
    if next_url:
        query["next"] = next_url
    auth_issue = (request.args.get("auth_issue", "") or "").strip().lower()
    if auth_issue in {"session_expired", "session_invalid", "user_inactive", "backend_unavailable"}:
        query["auth_issue"] = auth_issue
    return query


def _render_login(*, status: int = 200):
    if frontend_official_enabled():
        return redirect_to_frontend("#/login", query=_frontend_login_query()), 302
    return render_template("login.html", login_next=_login_next_url()), status


def _request_payload():
    if request.is_json:
        payload = request.get_json(silent=True)
        if isinstance(payload, dict):
            return payload
    return request.form


def _remember_login_requested(payload) -> bool:
    raw = str(payload.get("remember", "") or "").strip().lower()
    return raw in {"1", "true", "on", "yes"}


@dataclass(frozen=True)
class _AuthLoginSuccess:
    user: object
    login_value: str
    next_url: str


class _AuthLoginError(DomainError):
    def __init__(
        self,
        message: str,
        *,
        html_status: int,
        json_status: int,
        code: str,
        login_value: Optional[str] = None,
    ):
        super().__init__(message, status=json_status, code=code)
        self.html_status = html_status
        self.login_value = login_value or ""


def _api_login_success_response(result: _AuthLoginSuccess):
    _record_auth_outcome(
        outcome="auth_ok",
        login_value=result.login_value,
        user_id=getattr(result.user, "id", None),
        status=200,
        channel="api",
    )
    return {
        "success": True,
        "status": 200,
        "code": "auth_ok",
        "message": "Autenticação realizada com sucesso.",
        "next": result.next_url,
        "authenticated": True,
        "session": auth_session_payload(authenticated=True),
        "user": _serialize_auth_user(result.user),
        "capabilities": _serialize_capabilities(result.user),
    }, 200


def _html_login_success_response(result: _AuthLoginSuccess):
    _record_auth_outcome(
        outcome="auth_ok",
        login_value=result.login_value,
        user_id=getattr(result.user, "id", None),
        status=302,
        channel="html",
    )
    return redirect(result.next_url)


def _api_login_error_response(exc: _AuthLoginError):
    _record_auth_outcome(outcome=exc.code, login_value=exc.login_value, status=exc.status, channel="api")
    return domain_error_payload(exc)


def _html_login_error_response(exc: _AuthLoginError):
    _record_auth_outcome(outcome=exc.code, login_value=exc.login_value, status=exc.html_status, channel="html")
    flash(exc.message, "error")
    return _render_login(status=exc.html_status)


def _serialize_auth_user(user) -> dict:
    return {
        "id": str(getattr(user, "id", "")),
        "nome": getattr(user, "nome", "") or "",
        "login": getattr(user, "login", "") or "",
        "email": getattr(user, "email", "") or "",
        "perfil": getattr(user, "perfil", "") or "",
    }


def _serialize_capabilities(user) -> dict:
    granted_permissions = sorted(getattr(user, "granted_permissions", set()) or set())
    return {
        "granted_permissions": granted_permissions,
        "groups": [
            {
                "key": group["key"],
                "label": group["label"],
                "items": [
                    {
                        "key": item_key,
                        "label": item_label,
                        "granted": item_key in granted_permissions,
                    }
                    for item_key, item_label in group["items"]
                ],
            }
            for group in MODULE_PERMISSION_GROUPS
        ],
        "landing_url": resolve_landing_url_for_user(user),
    }


def _session_state_payload() -> dict:
    authenticated = bool(getattr(current_user, "is_authenticated", False))
    payload = {
        "success": True,
        "status": 200,
        "code": "session_state_ok",
        "authenticated": authenticated,
        "session": auth_session_payload(authenticated=authenticated),
        "csrf_token": generate_csrf(),
        "login_url": url_for("auth.login"),
        "logout_url": url_for("auth.logout"),
        "user": None,
        "capabilities": None,
    }
    if authenticated:
        payload["user"] = _serialize_auth_user(current_user)
        payload["capabilities"] = _serialize_capabilities(current_user)
    return payload


def _auth_required_json_payload():
    _record_auth_outcome(outcome="auth_required", status=401, channel="api")
    return domain_error_payload(AuthRequiredError())


def _persist_auth_session_snapshot(user_row) -> None:
    """
    Snapshot mínimo de identidade/permissões para amortecer falhas transitórias
    no recarregamento do usuário autenticado.
    """
    try:
        snapshot = {
            "id": str(user_row.get("id")),
            "nome": user_row.get("nome") or "",
            "login": user_row.get("login") or "",
            "email": user_row.get("email") or "",
            "perfil": user_row.get("perfil") or "",
            "ativo": int(user_row.get("ativo") or 0),
            "permissao_modulos_json": user_row.get("permissao_modulos_json", "[]"),
            "captured_at": int(time.time()),
        }
    except (TypeError, ValueError, AttributeError):
        current_app.logger.exception(
            "Falha ao montar snapshot de sessão autenticada. request_id=%s",
            getattr(g, "request_id", None),
        )
        return
    session["auth_user_snapshot"] = snapshot
    session["auth_user_snapshot_ts"] = snapshot["captured_at"]


def _authenticate_login_payload(payload, *, client_ip: str) -> _AuthLoginSuccess:
    login_value = ""
    senha_value = ""

    try:
        login_value = get_optional_text(payload, "login")
        senha_value = get_required_text(payload, "senha", "Senha")
    except ValueError as exc:
        register_login_failure()
        raise _AuthLoginError(
            str(exc),
            html_status=400,
            json_status=400,
            code="auth_bad_request",
            login_value=login_value,
        ) from exc
    if not login_value or not senha_value:
        register_login_failure()
        raise _AuthLoginError(
            "Informe login e senha para continuar.",
            html_status=400,
            json_status=400,
            code="auth_missing_credentials",
            login_value=login_value,
        )

    rate_key = f"{client_ip}:{login_value.strip().lower()}"
    if not login_limiter.is_allowed(rate_key):
        raise _AuthLoginError(
            "Muitas tentativas de login deste endereço para este usuário. Aguarde alguns minutos.",
            html_status=429,
            json_status=429,
            code="auth_rate_limited",
            login_value=login_value,
        )

    _failures, locked_until = login_attempt_state()
    if locked_until:
        raise _AuthLoginError(
            "Muitas tentativas de login nesta sessão. Aguarde alguns minutos antes de tentar novamente.",
            html_status=429,
            json_status=429,
            code="auth_session_locked",
            login_value=login_value,
        )

    _login_retryable_exceptions = (RuntimeError,)
    if psycopg2 is not None:
        _login_retryable_exceptions = (RuntimeError, psycopg2.Error)
    try:
        user = UserRepository.get_by_login(login_value)
    except _login_retryable_exceptions as exc:
        failure_kind = getattr(exc, "auth_failure_kind", "infrastructure")
        _req_id = getattr(g, "request_id", None)
        _exc_type = type(exc).__name__
        _exc_msg = str(exc)[:200]

        _remember_error_event(
            request_id=_req_id,
            status=503,
            code=f"auth_{failure_kind}",
            error_type=_exc_type,
            error_message=_exc_msg,
        )

        _kind_to_code = {
            "configuration": "auth_backend_misconfigured",
            "database": "auth_database_error",
            "pool_exhausted": "auth_pool_exhausted",
            "connection_timeout": "auth_connection_timeout",
        }
        auth_error_code = _kind_to_code.get(failure_kind, "auth_backend_unavailable")

        current_app.logger.exception(
            "Login indisponível por falha de infraestrutura. "
            "request_id=%s login=%s kind=%s exc_type=%s exc_msg=%s",
            _req_id,
            login_value,
            failure_kind,
            _exc_type,
            _exc_msg,
        )
        raise _AuthLoginError(
            _login_unavailable_message(kind=failure_kind),
            html_status=503,
            json_status=503,
            code=auth_error_code,
            login_value=login_value,
        ) from exc

    if not user:
        register_login_failure()
        raise _AuthLoginError(
            "Login inválido.",
            html_status=200,
            json_status=401,
            code="auth_invalid_credentials",
            login_value=login_value,
        )

    if int(user.get("ativo") or 0) != 1:
        register_login_failure()
        raise _AuthLoginError(
            "Usuário inativo. Contate o administrador.",
            html_status=200,
            json_status=403,
            code="auth_user_inactive",
            login_value=login_value,
        )

    password_ok = False
    try:
        password_ok = check_password_hash(user.get("senha_hash") or "", senha_value)
    except (TypeError, ValueError) as exc:
        current_app.logger.exception(
            "Formato inválido de senha_hash para usuario_id=%s durante login.",
            user.get("id"),
        )
        raise _AuthLoginError(
            _login_unavailable_message(kind="database"),
            html_status=503,
            json_status=503,
            code="auth_hash_invalid",
            login_value=login_value,
        ) from exc

    if not password_ok:
        register_login_failure()
        raise _AuthLoginError(
            "Login inválido.",
            html_status=200,
            json_status=401,
            code="auth_invalid_credentials",
            login_value=login_value,
        )

    remember_login = _remember_login_requested(payload)
    session.clear()
    establish_auth_session(remember_requested=remember_login)
    try:
        from ...models import User

        user_obj = User(
            user["id"],
            user["nome"],
            user["login"],
            user["email"],
            user["perfil"],
            user["ativo"],
            user.get("permissao_modulos_json", "[]"),
        )
        login_user(user_obj, remember=remember_login)
        if not remember_login:
            session["_remember"] = "clear"
        _persist_auth_session_snapshot(user)
    except (RuntimeError, TypeError, ValueError) as exc:
        current_app.logger.exception(
            "Falha ao construir sessão de usuário no login. request_id=%s user_id=%s login=%s",
            getattr(g, "request_id", None),
            user.get("id"),
            user.get("login"),
        )
        raise _AuthLoginError(
            _login_unavailable_message(kind="session"),
            html_status=503,
            json_status=503,
            code="auth_session_error",
            login_value=login_value,
        ) from exc

    clear_login_failures()
    login_limiter.reset(rate_key)
    return _AuthLoginSuccess(
        user=user_obj,
        login_value=login_value,
        next_url=_login_next_url(user=user_obj),
    )


def _handle_api_login():
    try:
        result = _authenticate_login_payload(
            _request_payload(),
            client_ip=request.remote_addr or "unknown",
        )
    except _AuthLoginError as exc:
        return _api_login_error_response(exc)
    return _api_login_success_response(result)


def _handle_html_login():
    try:
        result = _authenticate_login_payload(
            _request_payload(),
            client_ip=request.remote_addr or "unknown",
        )
    except _AuthLoginError as exc:
        return _html_login_error_response(exc)
    return _html_login_success_response(result)


def _api_logout_response(*, message: str, user_id=None, already_anonymous: bool = False):
    outcome = "logout_already_anonymous" if already_anonymous else "logout_ok"
    _record_auth_outcome(outcome=outcome, user_id=user_id, status=200, channel="api")
    return {
        "success": True,
        "status": 200,
        "code": "logout_ok",
        "message": message,
        "next": url_for("auth.login"),
        "authenticated": False,
        "session": {"state": "terminated", "remember": False, "permanent": False, "backend_verified": False},
    }, 200


def _handle_api_logout(*, anonymous_ok: bool):
    user_id = session.get("_user_id")
    if not user_id:
        clear_auth_session()
        if anonymous_ok:
            return _api_logout_response(message="Sessão já encerrada.", already_anonymous=True)
        return _auth_required_json_payload()

    clear_auth_session()
    return _api_logout_response(message="Sessão encerrada com sucesso.", user_id=user_id)


def _handle_html_logout():
    user_id = session.get("_user_id")
    if not user_id:
        clear_auth_session()
        if frontend_official_enabled():
            return redirect_to_frontend_app()
        return redirect(url_for("auth.login"))

    clear_auth_session()
    _record_auth_outcome(outcome="logout_ok", user_id=user_id, status=302, channel="html")
    if frontend_official_enabled():
        return redirect_to_frontend_app()
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET" and frontend_official_enabled():
        return redirect_to_frontend("#/login", query=_frontend_login_query())
    if request.method == "GET":
        if current_user.is_authenticated:
            return redirect(_login_next_url())
        if getattr(g, "auth_session_invalid", False):
            clear_auth_session()
            flash("Sua sessao anterior nao e mais valida. Entre novamente para continuar.", "warning")
        elif getattr(g, "auth_session_expired", False):
            flash("Sua sessao expirou. Entre novamente para continuar.", "warning")
        auth_issue = (request.args.get("auth_issue", "") or "").strip().lower()
        if auth_issue == "backend_unavailable":
            flash(
                "Sua sessão não pôde ser validada no momento. Faça login novamente.",
                "warning",
            )
        elif auth_issue == "user_inactive":
            flash("Usuário inativo. Contate o administrador.", "error")

    if request.method == "POST":
        return _handle_html_login()

    return _render_login()


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    if request.method == "GET" and frontend_official_enabled():
        return redirect_to_frontend_app()
    if request.method == "GET":
        if current_user.is_authenticated:
            _record_auth_outcome(
                outcome="logout_method_not_allowed",
                user_id=getattr(current_user, "id", None),
                status=405,
            )
            flash("Por segurança, use o botão Sair para encerrar a sessão.", "warning")
            return redirect(resolve_landing_url_for_user(current_user))
        return redirect(url_for("auth.login"))

    return _handle_html_logout()


@auth_bp.route("/api/v1/session", methods=["GET"])
def api_session_state():
    _ = current_user.is_authenticated
    if getattr(g, "auth_session_snapshot_used", False):
        return domain_error_payload(AuthBackendUnavailableError())
    if current_user.is_authenticated:
        touch_auth_session()
    return _session_state_payload(), 200


@auth_bp.route("/api/v1/session/login", methods=["POST"])
def api_session_login():
    return _handle_api_login()


@auth_bp.route("/api/v1/session/logout", methods=["POST"])
def api_session_logout():
    return _handle_api_logout(anonymous_ok=True)


@auth_bp.route("/api/v1/me", methods=["GET"])
def api_me():
    if not current_user.is_authenticated:
        return _auth_required_json_payload()
    return {
        "success": True,
        "status": 200,
        "code": "me_ok",
        "user": _serialize_auth_user(current_user),
    }, 200


@auth_bp.route("/api/v1/capabilities", methods=["GET"])
def api_capabilities():
    if not current_user.is_authenticated:
        return _auth_required_json_payload()
    return {
        "success": True,
        "status": 200,
        "code": "capabilities_ok",
        "capabilities": _serialize_capabilities(current_user),
    }, 200
