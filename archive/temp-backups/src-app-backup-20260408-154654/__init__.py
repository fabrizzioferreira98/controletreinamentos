import os
import hashlib
from datetime import timedelta
from hmac import compare_digest
from typing import Optional
from urllib.parse import urlparse

try:
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration
except ImportError:
    sentry_sdk = None
    FlaskIntegration = None

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv(*_args, **_kwargs):
        return False
from flask import Flask, jsonify, redirect, request, url_for
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect

try:
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
except ImportError:
    CONTENT_TYPE_LATEST = "text/plain"
    generate_latest = lambda: b""
from werkzeug.middleware.proxy_fix import ProxyFix

from .auth import MODULE_PERMISSION_GROUPS
from .auth import is_endpoint_permitted as is_endpoint_permitted
from .bases import bases_bp
from .core.cors import configure_cors
from .core.errors import (
    get_error_event_by_request_id,
    list_recent_error_events,
    register_error_handlers,
)
from .core.workspace_paths import runtime_instance_root
from .core.http_utils import (
    error_payload,
    expects_binary_asset_response,
    expects_json_response,
    safe_next_url,
)
from .core.security import configure_security_headers
from .db import close_db, init_app
from .services import name_initials

load_dotenv()

ALLOWED_APP_ENVS = {"production", "staging", "homolog", "development", "testing"}
SECURE_APP_ENVS = {"production", "staging", "homolog"}


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value.strip())
    except (TypeError, ValueError):
        return default


def _allow_insecure_http_in_secure_env(*, app_env: str) -> bool:
    if app_env not in SECURE_APP_ENVS:
        return False
    return env_flag("ALLOW_INSECURE_HTTP_IN_SECURE_ENV", default=False)

def _resolve_cookie_samesite() -> str:
    raw = (os.getenv("SESSION_COOKIE_SAMESITE", "") or "").strip().lower()
    if not raw:
        return "Lax"
    mapping = {
        "lax": "Lax",
        "strict": "Strict",
        "none": "None",
    }
    if raw not in mapping:
        raise RuntimeError(
            "SESSION_COOKIE_SAMESITE inválido. Use Strict, Lax ou None."
        )
    return mapping[raw]


def _resolve_cookie_domain(*, is_secure_env: bool) -> Optional[str]:
    raw = (os.getenv("COOKIE_DOMAIN", "") or "").strip()
    if not raw:
        return None
    lowered = raw.lower()
    if any(marker in lowered for marker in ("http://", "https://", "/", " ")):
        raise RuntimeError(
            "COOKIE_DOMAIN inválido. Informe apenas o domínio (ex.: .empresa.com), sem protocolo/caminho."
        )
    if ":" in raw:
        # domínio de cookie não deve incluir porta
        raise RuntimeError(
            "COOKIE_DOMAIN inválido. Não inclua porta no domínio de cookie."
        )
    if is_secure_env and raw in {"localhost", ".localhost"}:
        raise RuntimeError(
            "COOKIE_DOMAIN=localhost não é permitido em ambiente seguro."
        )
    return raw


def _resolve_cookie_path(env_name: str, *, fallback: str) -> str:
    raw = (os.getenv(env_name, "") or "").strip() or fallback
    if not raw.startswith("/"):
        raise RuntimeError(f"{env_name} inválido. O path do cookie deve começar com '/'.")
    if " " in raw:
        raise RuntimeError(f"{env_name} inválido. O path do cookie não pode conter espaços.")
    return raw


def _validate_secret_consistency(secret_key: str, *, is_secure_env: bool) -> str:
    secret_fingerprint = hashlib.sha256(secret_key.encode("utf-8")).hexdigest()[:12]
    expected_fp = (os.getenv("SECRET_KEY_FINGERPRINT", "") or "").strip().lower()
    if expected_fp and expected_fp != secret_fingerprint.lower():
        raise RuntimeError(
            "SECRET_KEY divergente do SECRET_KEY_FINGERPRINT esperado. "
            "Isso pode invalidar sessões entre instâncias."
        )
    if is_secure_env and not expected_fp:
        # Não bloqueia, mas alerta para reduzir risco de drift entre instâncias.
        return secret_fingerprint
    return secret_fingerprint


def _platform_requires_secure_defaults() -> bool:
    return False


def _resolve_app_env() -> str:
    raw = (os.getenv("APP_ENV", "") or "").strip().lower()
    secure_platform = False

    if raw and raw not in ALLOWED_APP_ENVS:
        raise RuntimeError(
            f"APP_ENV inválido: {raw!r}. Valores aceitos: {', '.join(sorted(ALLOWED_APP_ENVS))}."
        )

    if not raw:
                # Ambiente sem APP_ENV explicito cai em development por padrao local.
        return "development"

    return raw


def _validate_secret_key_strength(secret_key: str, *, is_secure_env: bool) -> None:
    if not is_secure_env:
        return
    if len(secret_key) < 16:
        raise RuntimeError(
            "SECRET_KEY muito curta para ambiente seguro. Use ao menos 16 caracteres."
        )
    weak_values = {"secret", "changeme", "dev-insecure-secret-key", "123456"}
    if secret_key.strip().lower() in weak_values:
        raise RuntimeError(
            "SECRET_KEY fraca para ambiente seguro. Defina uma chave criptograficamente forte."
        )


def _is_local_database_host(hostname: str | None) -> bool:
    return (hostname or "").strip().lower() in {"localhost", "127.0.0.1", "::1"}


def _validate_database_url_for_env_legacy(database_url: str, *, app_env: str) -> None:
    if not database_url:
        return
    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgresql", "postgres"}:
        raise RuntimeError(
            "DATABASE_URL inválida. Use esquema postgresql:// ou postgres://."
        )
    if not parsed.hostname:
        raise RuntimeError(
            "DATABASE_URL inválida. Host ausente."
        )
    secure_envs = {"production", "staging", "homolog"}
    if app_env in secure_envs and parsed.hostname in {"localhost", "127.0.0.1"}:
        raise RuntimeError(
            f"DATABASE_URL local não permitida em ambiente seguro ({app_env})."
        )

def _validate_database_url_for_env(database_url: str, *, app_env: str) -> None:
    if not database_url:
        return
    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgresql", "postgres"}:
        raise RuntimeError(
            "DATABASE_URL invÃ¡lida. Use esquema postgresql:// ou postgres://."
        )
    if not parsed.hostname:
        raise RuntimeError(
            "DATABASE_URL invÃ¡lida. Host ausente."
        )
    secure_envs = {"production", "staging", "homolog"}
    if app_env in secure_envs and _is_local_database_host(parsed.hostname):
        allow_local_db = env_flag("ALLOW_LOCAL_DATABASE_IN_SECURE_ENV", default=False)
        if allow_local_db:
            return
        raise RuntimeError(
            "DATABASE_URL local detectada em ambiente seguro. "
            "Para self-hosting no mesmo servidor, habilite explicitamente "
            "ALLOW_LOCAL_DATABASE_IN_SECURE_ENV=1."
        )


def create_app() -> Flask:
    app_env = _resolve_app_env()
    is_secure_env = app_env in SECURE_APP_ENVS
    allow_insecure_http = _allow_insecure_http_in_secure_env(app_env=app_env)
    cookie_secure = is_secure_env and not allow_insecure_http
    secret_key = (os.getenv("SECRET_KEY") or "").strip()
    using_dev_fallback_secret = False

    if not secret_key:
        if is_secure_env:
            raise RuntimeError(
                f"SECRET_KEY ausente em ambiente seguro ({app_env}). "
                "Defina SECRET_KEY antes de iniciar a aplicação."
            )
        secret_key = os.getenv("DEV_FALLBACK_SECRET_KEY", "dev-insecure-secret-key")
        using_dev_fallback_secret = True
    _validate_secret_key_strength(secret_key, is_secure_env=is_secure_env)
    configured_database_url = (os.getenv("DATABASE_URL", "") or "").strip()
    _validate_database_url_for_env(configured_database_url, app_env=app_env)

    training_attachment_mb = max(1, env_int("TRAINING_ATTACHMENT_MAX_MB", 8))
    # Mantém folga para campos do formulário + metadata multipart.
    default_max_content_mb = max(100, training_attachment_mb + 2)
    max_content_mb = max(training_attachment_mb, env_int("MAX_CONTENT_LENGTH_MB", default_max_content_mb))

    if sentry_sdk and os.getenv("SENTRY_DSN"):
        sentry_sdk.init(
            dsn=os.getenv("SENTRY_DSN"),
            integrations=[FlaskIntegration()] if FlaskIntegration else [],
            traces_sample_rate=1.0,
        )

    instance_path = runtime_instance_root().resolve()
    instance_path.mkdir(parents=True, exist_ok=True)
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
        instance_path=str(instance_path),
    )
    session_hours = max(1, env_int("SESSION_HOURS", 8))
    remember_days = max(1, env_int("REMEMBER_COOKIE_DAYS", 7))
    csrf_time_limit = max(300, env_int("WTF_CSRF_TIME_LIMIT_SECONDS", 3600))
    cookie_samesite = _resolve_cookie_samesite()
    cookie_domain = _resolve_cookie_domain(is_secure_env=is_secure_env)
    session_cookie_name = (os.getenv("SESSION_COOKIE_NAME", "") or "").strip() or "controle_treinamentos_session"
    remember_cookie_name = (os.getenv("REMEMBER_COOKIE_NAME", "") or "").strip() or "controle_treinamentos_remember"
    session_cookie_path = _resolve_cookie_path("SESSION_COOKIE_PATH", fallback="/")
    remember_cookie_path = _resolve_cookie_path("REMEMBER_COOKIE_PATH", fallback=session_cookie_path)
    if cookie_samesite == "None" and not is_secure_env:
        raise RuntimeError(
            "SESSION_COOKIE_SAMESITE=None exige ambiente seguro (HTTPS) para evitar inconsistência de sessão."
        )
    app.config.update(
        APP_ENV=app_env,
        SECRET_KEY=secret_key,
        AUDIT_STRICT_MODE=env_flag("AUDIT_STRICT_MODE", default=True),
        WTF_CSRF_TIME_LIMIT=csrf_time_limit,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE=cookie_samesite,
        SESSION_COOKIE_SECURE=cookie_secure,
        SESSION_COOKIE_NAME=session_cookie_name,
        SESSION_COOKIE_PATH=session_cookie_path,
        SESSION_COOKIE_DOMAIN=cookie_domain,
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SAMESITE=cookie_samesite,
        REMEMBER_COOKIE_SECURE=cookie_secure,
        REMEMBER_COOKIE_NAME=remember_cookie_name,
        REMEMBER_COOKIE_PATH=remember_cookie_path,
        REMEMBER_COOKIE_DOMAIN=cookie_domain,
        REMEMBER_COOKIE_DURATION=timedelta(days=remember_days),
        REMEMBER_COOKIE_REFRESH_EACH_REQUEST=True,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=session_hours),
        SESSION_REFRESH_EACH_REQUEST=True,
        AUTH_FAILURE_ALERT_THRESHOLD=max(5, env_int("AUTH_FAILURE_ALERT_THRESHOLD", 20)),
        AUTH_FAILURE_ALERT_WINDOW_SECONDS=max(30, env_int("AUTH_FAILURE_ALERT_WINDOW_SECONDS", 300)),
        AUTH_FAILURE_ALERT_MIN_INTERVAL_SECONDS=max(15, env_int("AUTH_FAILURE_ALERT_MIN_INTERVAL_SECONDS", 60)),
        MAX_CONTENT_LENGTH=max_content_mb * 1024 * 1024,
        PREFERRED_URL_SCHEME="https" if cookie_secure else "http",
        EMIT_HSTS=is_secure_env and not allow_insecure_http,
        TESTING=app_env == "testing",
    )
    if using_dev_fallback_secret:
        app.logger.warning(
            "SECRET_KEY ausente em ambiente não produtivo. "
            "Usando DEV_FALLBACK_SECRET_KEY para desenvolvimento local."
        )
    secret_fingerprint = _validate_secret_consistency(secret_key, is_secure_env=is_secure_env)
    app.logger.info(
        "Config auth/sessao carregada. app_env=%s secure=%s session_hours=%s remember_days=%s cookie_domain=%s cookie_path=%s samesite=%s secret_fp=%s",
        app_env,
        is_secure_env,
        session_hours,
        remember_days,
        cookie_domain or "",
        session_cookie_path,
        cookie_samesite,
        secret_fingerprint,
    )
    if is_secure_env and not (os.getenv("SECRET_KEY_FINGERPRINT", "") or "").strip():
        app.logger.warning(
            "SECRET_KEY_FINGERPRINT ausente em ambiente seguro. "
            "Configure o fingerprint para detectar deriva de SECRET_KEY entre instâncias."
        )

    if allow_insecure_http:
        app.logger.warning(
            "ALLOW_INSECURE_HTTP_IN_SECURE_ENV=1 ativo para app_env=%s. "
            "Cookies Secure e HSTS foram desabilitados explicitamente para operacao HTTP sem TLS.",
            app_env,
        )

    from .core.logging import configure_structured_logging
    configure_structured_logging(app)

    trust_proxy_headers = env_flag("TRUST_PROXY_HEADERS", default=is_secure_env)
    if trust_proxy_headers:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    elif is_secure_env:
        app.logger.warning(
            "TRUST_PROXY_HEADERS desativado em ambiente seguro. "
            "Se houver proxy/reverse proxy HTTPS, cookies Secure podem falhar e causar logout indevido."
        )

        # CSRF globally
    csrf = CSRFProtect()
    csrf.init_app(app)

    # Flask-Login
    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Por favor, faça login para acessar esta página."
    login_manager.login_message_category = "error"
    login_manager.init_app(app)

    @login_manager.unauthorized_handler
    def handle_unauthorized():
        if expects_json_response():
            return error_payload(
                "Autenticação obrigatória ou sessão expirada.",
                status=401,
                code="auth_required",
            )
        if expects_binary_asset_response():
            return "", 401
        next_url = safe_next_url(request.full_path if request.method == "GET" else None, url_for("dashboard.dashboard"))
        return redirect(url_for("auth.login", next=next_url))

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.get(user_id)

    @app.context_processor
    def inject_user():
        def can_access(permission_key: str) -> bool:
            if not current_user.is_authenticated:
                return False
            if hasattr(current_user, "has_permission"):
                return current_user.has_permission(permission_key)
            return False

        if current_user.is_authenticated:
            return {
                "session": {
                    "user_id": current_user.id,
                    "user_name": current_user.nome,
                    "user_role": current_user.perfil
                },
                "can_access": can_access,
                "module_permission_groups": MODULE_PERMISSION_GROUPS,
                "avatar_initials": name_initials,
            }
        return {
            "session": {},
            "can_access": can_access,
            "module_permission_groups": MODULE_PERMISSION_GROUPS,
            "avatar_initials": name_initials,
        }

    from .core.template_filters import register_template_filters
    register_template_filters(app)

    @app.route("/healthz", methods=["GET"])
    def healthz():
        checks = {"status": "ok", "checks": {}}
        try:
            from .db import get_db
            db = get_db()
            db.execute("SELECT 1")
            checks["checks"]["database"] = "ok"
        except Exception:
            checks["status"] = "degraded"
            checks["checks"]["database"] = "unavailable"
            app.logger.exception("Healthcheck database probe failed.")
        status_code = 200 if checks["status"] == "ok" else 503
        return jsonify(checks), status_code

    @app.route("/api/internal/metrics", methods=["GET"])
    def internal_metrics():
        expected = (os.getenv("METRICS_TOKEN", "") or "").strip()
        provided = (request.headers.get("X-Metrics-Token", "") or "").strip()
        if not expected:
            app.logger.error("METRICS_TOKEN ausente. Endpoint de métricas bloqueado por política de segurança.")
            return error_payload(
                "Endpoint de métricas indisponível por configuração de segurança.",
                status=503,
                code="metrics_unconfigured",
            )
        if not provided or not compare_digest(provided, expected):
            return error_payload("Token de métricas inválido.", status=403, code="metrics_forbidden")
        from flask import Response
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

    @app.route("/api/internal/errors/<string:request_id>", methods=["GET"])
    def internal_error_trace(request_id: str):
        expected = (os.getenv("METRICS_TOKEN", "") or "").strip()
        provided = (request.headers.get("X-Metrics-Token", "") or "").strip()
        has_metrics_token = bool(expected and compare_digest(provided, expected))
        has_monitoring_permission = bool(
            current_user.is_authenticated
            and hasattr(current_user, "has_permission")
            and current_user.has_permission("monitoramento:view")
        )
        if not (has_metrics_token or has_monitoring_permission):
            if not current_user.is_authenticated:
                return error_payload(
                    "Autenticação obrigatória ou sessão expirada.",
                    status=401,
                    code="auth_required",
                )
            return error_payload(
                "Acesso negado para esta operação.",
                status=403,
                code="forbidden",
            )

        trace_event = get_error_event_by_request_id((request_id or "").strip())
        if not trace_event:
            return error_payload(
                "Código de rastreio não encontrado na janela de retenção deste processo.",
                status=404,
                code="error_event_not_found",
            )

        return jsonify(
            {
                "success": True,
                "status": 200,
                "code": "error_event_found",
                "event": trace_event,
                "recent": list_recent_error_events(limit=10),
            }
        ), 200

    register_error_handlers(app)
    configure_security_headers(
        app,
        is_secure_env=is_secure_env,
        emit_hsts=bool(app.config.get("EMIT_HSTS", False)),
    )
    configure_cors(app)

    init_app(app)
    app.register_blueprint(bases_bp)

    from .blueprints.admin import admin_bp
    from .blueprints.auth import auth_bp
    from .blueprints.cadastros import cadastros_bp
    from .blueprints.dashboard import dashboard_bp
    from .blueprints.operacoes import operacoes_bp
    from .blueprints.relatorios import relatorios_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(cadastros_bp)
    app.register_blueprint(operacoes_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(relatorios_bp)

    app.teardown_appcontext(close_db)
    return app


