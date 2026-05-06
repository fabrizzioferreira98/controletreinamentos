try:
    import psycopg2
except ImportError:
    psycopg2 = None  # type: ignore[assignment]
import json
import time
from collections import deque
from threading import Lock
from typing import Optional, Union

from flask import current_app, flash, g, redirect, render_template, request, session, url_for
from flask_login import current_user, login_user, logout_user
from flask_wtf.csrf import generate_csrf
from werkzeug.security import check_password_hash

from ...auth import MODULE_PERMISSION_GROUPS, resolve_landing_url_for_user
from ...core.audit_utils import (
    clear_login_failures,
    login_attempt_state,
    register_login_failure,
)
from ...core.http_utils import (
    error_payload,
    expects_json_response,
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
    return "json" if expects_json_response() else "html"


def _record_auth_outcome(
    *,
    outcome: str,
    login_value: Optional[str] = None,
    user_id: Optional[Union[str, int]] = None,
    status: Optional[int] = None,
):
    channel = _auth_channel()
    AUTH_EVENTS_TOTAL.labels(outcome, channel).inc()
    current_app.logger.info(
        json.dumps(
            {
                "event": "auth_outcome",
                "request_id": getattr(g, "request_id", None),
                "outcome": outcome,
                "channel": channel,
                "status": status,
                "path": request.path,
                "method": request.method,
                "user_id": user_id,
                "login": (login_value or "")[:120],
            },
            ensure_ascii=False,
        )
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
                "ALERT auth_failure_surge detected. count=%s window_seconds=%s request_id=%s",
                len(_AUTH_FAILURE_TIMESTAMPS),
                window_seconds,
                getattr(g, "request_id", None),
            )


from ...core.errors import _remember_error_event
from ...repositories.user_repository import UserRepository

def _login_next_url(*, user=None) -> str:
    fallback = resolve_landing_url_for_user(user or current_user)
    return safe_next_url(
        request.args.get("next") or request.form.get("next"),
        fallback,
    )


def _render_login(*, status: int = 200):
    if frontend_official_enabled():
        return redirect_to_frontend("#/dashboard"), 302
    return render_template("login.html", login_next=_login_next_url()), status


def _request_payload():
    if request.is_json:
        payload = request.get_json(silent=True)
        if isinstance(payload, dict):
            return payload
    return request.form


def _respond_login_error(
    message: str,
    *,
    html_status: int,
    json_status: int,
    code: str,
    login_value: Optional[str] = None,
):
    status = json_status if expects_json_response() else html_status
    _record_auth_outcome(outcome=code, login_value=login_value, status=status)
    if expects_json_response():
        return error_payload(message, status=json_status, code=code)
    flash(message, "error")
    return _render_login(status=html_status)


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
    _record_auth_outcome(outcome="auth_required", status=401)
    return error_payload(
        "Autenticação obrigatória ou sessão expirada.",
        status=401,
        code="auth_required",
    )


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


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET" and frontend_official_enabled():
        return redirect_to_frontend("#/dashboard")
    if request.method == "GET" and current_user.is_authenticated:
        return redirect(_login_next_url())
    if request.method == "GET":
        auth_issue = (request.args.get("auth_issue", "") or "").strip().lower()
        if auth_issue == "backend_unavailable":
            flash(
                "Sua sessão não pôde ser validada no momento. Faça login novamente.",
                "warning",
            )

    if request.method == "POST":
        login_value = ""
        senha_value = ""
        client_ip = request.remote_addr or "unknown"
        payload = _request_payload()

        try:
            login_value = get_optional_text(payload, "login")
            senha_value = get_required_text(payload, "senha", "Senha")
        except ValueError as exc:
            register_login_failure()
            return _respond_login_error(
                str(exc),
                html_status=400,
                json_status=400,
                code="auth_bad_request",
                login_value=login_value,
            )
        if not login_value or not senha_value:
            register_login_failure()
            return _respond_login_error(
                "Informe login e senha para continuar.",
                html_status=400,
                json_status=400,
                code="auth_missing_credentials",
                login_value=login_value,
            )

        rate_key = f"{client_ip}:{login_value.strip().lower()}"
        if not login_limiter.is_allowed(rate_key):
            return _respond_login_error(
                "Muitas tentativas de login deste endereço para este usuário. Aguarde alguns minutos.",
                html_status=429,
                json_status=429,
                code="auth_rate_limited",
                login_value=login_value,
            )

        _failures, locked_until = login_attempt_state()
        if locked_until:
            return _respond_login_error(
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

            # Persistir evento de erro para rastreabilidade via request_id
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
            return _respond_login_error(
                _login_unavailable_message(kind=failure_kind),
                html_status=503,
                json_status=503,
                code=auth_error_code,
                login_value=login_value,
            )

        if not user:
            register_login_failure()
            return _respond_login_error(
                "Login inválido.",
                html_status=200,
                json_status=401,
                code="auth_invalid_credentials",
                login_value=login_value,
            )

        if int(user.get("ativo") or 0) != 1:
            register_login_failure()
            return _respond_login_error(
                "Usuário inativo. Contate o administrador.",
                html_status=200,
                json_status=403,
                code="auth_user_inactive",
                login_value=login_value,
            )

        password_ok = False
        try:
            password_ok = check_password_hash(user.get("senha_hash") or "", senha_value)
        except (TypeError, ValueError):
            current_app.logger.exception(
                "Formato inválido de senha_hash para usuario_id=%s durante login.",
                user.get("id"),
            )
            return _respond_login_error(
                _login_unavailable_message(kind="database"),
                html_status=503,
                json_status=503,
                code="auth_hash_invalid",
                login_value=login_value,
            )

        if password_ok:
            session.clear()
            session.permanent = True
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
                remember_raw = str(payload.get("remember", "1") or "1").strip().lower()
                remember_login = remember_raw not in {"0", "false", "off", "no"}
                login_user(user_obj, remember=remember_login)
                _persist_auth_session_snapshot(user)
            except (RuntimeError, TypeError, ValueError):
                current_app.logger.exception(
                    "Falha ao construir sessão de usuário no login. request_id=%s user_id=%s login=%s",
                    getattr(g, "request_id", None),
                    user.get("id"),
                    user.get("login"),
                )
                return _respond_login_error(
                    _login_unavailable_message(kind="session"),
                    html_status=503,
                    json_status=503,
                    code="auth_session_error",
                    login_value=login_value,
                )
            clear_login_failures()
            login_limiter.reset(rate_key)
            next_url = _login_next_url(user=user_obj)
            if expects_json_response():
                _record_auth_outcome(
                    outcome="auth_ok",
                    login_value=login_value,
                    user_id=user_obj.id,
                    status=200,
                )
                return {
                    "success": True,
                    "status": 200,
                    "code": "auth_ok",
                    "message": "Autenticação realizada com sucesso.",
                    "next": next_url,
                    "authenticated": True,
                    "user": _serialize_auth_user(user_obj),
                    "capabilities": _serialize_capabilities(user_obj),
                }, 200
            _record_auth_outcome(
                outcome="auth_ok",
                login_value=login_value,
                user_id=user_obj.id,
                status=302,
            )
            return redirect(next_url)

        register_login_failure()
        return _respond_login_error(
            "Login inválido.",
            html_status=200,
            json_status=401,
            code="auth_invalid_credentials",
            login_value=login_value,
        )

    return _render_login()


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    if request.method == "GET" and frontend_official_enabled() and not expects_json_response():
        return redirect_to_frontend_app()
    if request.method == "GET":
        if expects_json_response():
            _record_auth_outcome(outcome="logout_method_not_allowed", status=405)
            return error_payload(
                "Logout exige requisição POST com CSRF válido.",
                status=405,
                code="method_not_allowed",
            )
        if current_user.is_authenticated:
            _record_auth_outcome(
                outcome="logout_method_not_allowed",
                user_id=getattr(current_user, "id", None),
                status=405,
            )
            flash("Por segurança, use o botão Sair para encerrar a sessão.", "warning")
            return redirect(resolve_landing_url_for_user(current_user))
        return redirect(url_for("auth.login"))

    if not current_user.is_authenticated:
        if expects_json_response():
            _record_auth_outcome(outcome="auth_required", status=401)
            return error_payload(
                "Autenticação obrigatória ou sessão expirada.",
                status=401,
                code="auth_required",
            )
        if frontend_official_enabled():
            return redirect_to_frontend_app()
        return redirect(url_for("auth.login"))

    user_id = getattr(current_user, "id", None)
    logout_user()
    # Preserva o marcador "_remember" injetado pelo logout_user() para garantir
    # que o Flask-Login emita o header 'Set-Cookie' deletando o token de "Lembrar de mim".
    # Sem isso, o cookie persistiria e auto-logaria o usuário de volta imediatamente.
    remember_flag = session.get("_remember")
    session.clear()
    if remember_flag == "clear":
        session["_remember"] = "clear"
    if expects_json_response():
        _record_auth_outcome(outcome="logout_ok", user_id=user_id, status=200)
        return {
            "success": True,
            "status": 200,
            "code": "logout_ok",
            "message": "Sessão encerrada com sucesso.",
            "next": url_for("auth.login"),
        }, 200
    _record_auth_outcome(outcome="logout_ok", user_id=user_id, status=302)
    if frontend_official_enabled():
        return redirect_to_frontend_app()
    return redirect(url_for("auth.login"))


@auth_bp.route("/api/v1/session", methods=["GET"])
def api_session_state():
    return _session_state_payload(), 200


@auth_bp.route("/api/v1/session/login", methods=["POST"])
def api_session_login():
    return login()


@auth_bp.route("/api/v1/session/logout", methods=["POST"])
def api_session_logout():
    if not current_user.is_authenticated:
        return _auth_required_json_payload()

    user_id = getattr(current_user, "id", None)
    logout_user()
    remember_flag = session.get("_remember")
    session.clear()
    if remember_flag == "clear":
        session["_remember"] = "clear"
    _record_auth_outcome(outcome="logout_ok", user_id=user_id, status=200)
    return {
        "success": True,
        "status": 200,
        "code": "logout_ok",
        "message": "Sessão encerrada com sucesso.",
        "next": url_for("auth.login"),
        "authenticated": False,
    }, 200


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
