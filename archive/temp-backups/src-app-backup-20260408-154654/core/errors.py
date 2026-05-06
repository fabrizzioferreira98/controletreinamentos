from __future__ import annotations

import json
import time
from collections import defaultdict, deque
from html import escape
from threading import Lock

from flask import Response, flash, g, redirect, request, session, url_for
from flask_login import current_user, logout_user
from flask_wtf.csrf import CSRFError

from ..auth import is_endpoint_permitted
from .http_utils import error_payload, expects_binary_asset_response, expects_json_response

_ERROR_SURGE_LOCK = Lock()
_ERROR_SURGE_EVENTS: dict[str, deque[float]] = defaultdict(deque)
_ERROR_SURGE_LAST_ALERT_AT: dict[str, float] = {}
_ERROR_EVENTS_LOCK = Lock()
_ERROR_EVENTS_HISTORY_MAX = 500
_ERROR_EVENTS_ORDER: deque[str] = deque()
_ERROR_EVENTS_BY_REQUEST_ID: dict[str, dict] = {}


def _safe_int_user_id() -> int | None:
    raw = _safe_current_user_id()
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _safe_current_user_id():
    try:
        if current_user.is_authenticated:
            return getattr(current_user, "id", None)
    except Exception:
        return None
    return None


def _error_signature(status: int, code: str) -> str:
    endpoint = (request.endpoint or "unknown").strip() or "unknown"
    path = (request.path or "").strip() or "-"
    return f"{status}:{code}:{endpoint}:{path}"


def _track_error_surge(app, *, status: int, code: str, request_id: str | None) -> None:
    threshold = max(3, int(app.config.get("ERROR_SURGE_ALERT_THRESHOLD") or 8))
    window_seconds = max(30, int(app.config.get("ERROR_SURGE_ALERT_WINDOW_SECONDS") or 120))
    min_interval_seconds = max(15, int(app.config.get("ERROR_SURGE_ALERT_MIN_INTERVAL_SECONDS") or 60))
    signature = _error_signature(status, code)
    now = time.time()
    with _ERROR_SURGE_LOCK:
        bucket = _ERROR_SURGE_EVENTS[signature]
        bucket.append(now)
        cutoff = now - window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        last_alert_at = _ERROR_SURGE_LAST_ALERT_AT.get(signature, 0.0)
        if len(bucket) >= threshold and (now - last_alert_at) >= min_interval_seconds:
            _ERROR_SURGE_LAST_ALERT_AT[signature] = now
            app.logger.warning(
                "ALERT error_response_surge detected. signature=%s count=%s window_seconds=%s request_id=%s",
                signature,
                len(bucket),
                window_seconds,
                request_id,
            )


def _remember_error_event(
    *,
    request_id: str | None,
    status: int,
    code: str,
    error_type: str,
    error_message: str,
) -> None:
    normalized_request_id = (request_id or "").strip()
    if not normalized_request_id:
        return
    snapshot = {
        "request_id": normalized_request_id,
        "status": int(status),
        "code": code,
        "error_type": error_type,
        "error_message": (error_message or "")[:400],
        "path": request.path,
        "endpoint": request.endpoint,
        "method": request.method,
        "user_id": _safe_current_user_id(),
        "captured_at": int(time.time()),
    }
    with _ERROR_EVENTS_LOCK:
        _ERROR_EVENTS_BY_REQUEST_ID[normalized_request_id] = snapshot
        _ERROR_EVENTS_ORDER.append(normalized_request_id)
        while len(_ERROR_EVENTS_ORDER) > _ERROR_EVENTS_HISTORY_MAX:
            oldest = _ERROR_EVENTS_ORDER.popleft()
            if oldest not in _ERROR_EVENTS_ORDER:
                _ERROR_EVENTS_BY_REQUEST_ID.pop(oldest, None)


def _persist_error_event_db(snapshot: dict) -> None:
    try:
        from ..db import get_db
    except Exception:
        return
    try:
        db = get_db()
        db.execute(
            """
            INSERT INTO request_error_events
            (
                request_id, status, code, error_type, error_message,
                path, endpoint, method, user_id, context_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (request_id) DO UPDATE SET
                status = EXCLUDED.status,
                code = EXCLUDED.code,
                error_type = EXCLUDED.error_type,
                error_message = EXCLUDED.error_message,
                path = EXCLUDED.path,
                endpoint = EXCLUDED.endpoint,
                method = EXCLUDED.method,
                user_id = EXCLUDED.user_id,
                context_json = EXCLUDED.context_json,
                captured_at = CURRENT_TIMESTAMP
            """,
            (
                snapshot.get("request_id"),
                int(snapshot.get("status") or 0),
                snapshot.get("code") or "internal_error",
                snapshot.get("error_type") or "UnknownError",
                (snapshot.get("error_message") or "")[:2000],
                (snapshot.get("path") or "")[:400],
                (snapshot.get("endpoint") or "")[:200],
                (snapshot.get("method") or "")[:20],
                _safe_int_user_id(),
                json.dumps(
                    {
                        "accept": (request.headers.get("Accept", "") or "")[:200],
                        "is_json": bool(expects_json_response()),
                        "is_binary": bool(expects_binary_asset_response()),
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        db.commit()
    except Exception:
        # Persistência de erro nunca pode derrubar o handler principal.
        pass


def _fetch_error_event_db(request_id: str) -> dict | None:
    try:
        from ..db import get_db
        db = get_db()
        row = db.execute(
            """
            SELECT
                request_id, status, code, error_type, error_message,
                path, endpoint, method, user_id,
                EXTRACT(EPOCH FROM captured_at)::BIGINT AS captured_at
            FROM request_error_events
            WHERE request_id = %s
            LIMIT 1
            """,
            (request_id,),
        ).fetchone()
    except Exception:
        return None
    if not row:
        return None
    return {
        "request_id": row.get("request_id"),
        "status": int(row.get("status") or 0),
        "code": row.get("code"),
        "error_type": row.get("error_type"),
        "error_message": row.get("error_message"),
        "path": row.get("path"),
        "endpoint": row.get("endpoint"),
        "method": row.get("method"),
        "user_id": row.get("user_id"),
        "captured_at": int(row.get("captured_at") or 0),
    }


def _list_recent_error_events_db(*, limit: int) -> list[dict]:
    safe_limit = max(1, min(int(limit), 100))
    try:
        from ..db import get_db
        db = get_db()
        rows = db.execute(
            """
            SELECT
                request_id, status, code, error_type, error_message,
                path, endpoint, method, user_id,
                EXTRACT(EPOCH FROM captured_at)::BIGINT AS captured_at
            FROM request_error_events
            ORDER BY captured_at DESC
            LIMIT %s
            """,
            (safe_limit,),
        ).fetchall()
    except Exception:
        return []
    events: list[dict] = []
    for row in rows or []:
        events.append(
            {
                "request_id": row.get("request_id"),
                "status": int(row.get("status") or 0),
                "code": row.get("code"),
                "error_type": row.get("error_type"),
                "error_message": row.get("error_message"),
                "path": row.get("path"),
                "endpoint": row.get("endpoint"),
                "method": row.get("method"),
                "user_id": row.get("user_id"),
                "captured_at": int(row.get("captured_at") or 0),
            }
        )
    return events


def get_error_event_by_request_id(request_id: str) -> dict | None:
    normalized_request_id = (request_id or "").strip()
    if not normalized_request_id:
        return None
    db_event = _fetch_error_event_db(normalized_request_id)
    if db_event is not None:
        return db_event
    with _ERROR_EVENTS_LOCK:
        event = _ERROR_EVENTS_BY_REQUEST_ID.get(normalized_request_id)
        return dict(event) if isinstance(event, dict) else None


def list_recent_error_events(*, limit: int = 20) -> list[dict]:
    safe_limit = max(1, min(int(limit), 100))
    db_events = _list_recent_error_events_db(limit=safe_limit)
    if db_events:
        return db_events
    events: list[dict] = []
    seen: set[str] = set()
    with _ERROR_EVENTS_LOCK:
        for request_id in reversed(_ERROR_EVENTS_ORDER):
            if request_id in seen:
                continue
            seen.add(request_id)
            event = _ERROR_EVENTS_BY_REQUEST_ID.get(request_id)
            if isinstance(event, dict):
                events.append(dict(event))
            if len(events) >= safe_limit:
                break
    return events


def _log_error_event(
    app,
    *,
    status: int,
    code: str,
    error_type: str,
    error_message: str,
    request_id: str | None,
) -> None:
    _remember_error_event(
        request_id=request_id,
        status=status,
        code=code,
        error_type=error_type,
        error_message=error_message,
    )
    _persist_error_event_db(
        {
            "request_id": (request_id or "").strip(),
            "status": int(status),
            "code": code,
            "error_type": error_type,
            "error_message": (error_message or "")[:400],
            "path": request.path,
            "endpoint": request.endpoint,
            "method": request.method,
        }
    )
    app.logger.error(
        json.dumps(
            {
                "event": "error_response",
                "request_id": request_id,
                "status": status,
                "code": code,
                "error_type": error_type,
                "path": request.path,
                "endpoint": request.endpoint,
                "method": request.method,
                "user_id": _safe_current_user_id(),
                "accept": (request.headers.get("Accept", "") or "")[:160],
                "is_json": expects_json_response(),
                "is_binary": expects_binary_asset_response(),
            },
            ensure_ascii=False,
        )
    )
    _track_error_surge(app, status=status, code=code, request_id=request_id)


def _html_error_response(*, status: int, title: str, message: str, request_id: str | None) -> Response:
    escaped_title = escape(title)
    escaped_message = escape(message)
    escaped_request_id = escape(request_id) if request_id else None
    request_id_html = (
        f'<p class="error-meta"><strong>Código de rastreio:</strong> <code>{escaped_request_id}</code></p>'
        if escaped_request_id
        else ""
    )
    html = f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{escaped_title}</title>
  <style>
    :root {{ color-scheme: light; }}
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f4f7fb; color: #1f2937; }}
    .wrap {{ max-width: 720px; margin: 8vh auto; padding: 24px; }}
    .card {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 16px; padding: 24px; box-shadow: 0 10px 26px rgba(15, 23, 42, .08); }}
    h1 {{ margin: 0 0 8px; font-size: 1.4rem; }}
    p {{ margin: 0 0 12px; line-height: 1.45; }}
    .error-meta {{ color: #4b5563; font-size: .92rem; }}
    .actions a {{ color: #0f62fe; text-decoration: none; font-weight: 600; }}
    .actions a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="card">
      <h1>{escaped_title}</h1>
      <p>{escaped_message}</p>
      {request_id_html}
      <p class="actions"><a href="/login">Ir para login</a></p>
    </section>
  </main>
</body>
</html>
"""
    return Response(html, status=status, mimetype="text/html")


def register_error_handlers(app):
    @app.errorhandler(CSRFError)
    def handle_csrf_error(_error):
        if request.endpoint == "auth.logout":
            user_id = _safe_current_user_id()
            if current_user.is_authenticated:
                logout_user()
                remember_flag = session.get("_remember")
                session.clear()
                if remember_flag == "clear":
                    session["_remember"] = "clear"
            if expects_json_response():
                if user_id is None:
                    return error_payload("Autenticação obrigatória ou sessão expirada.", status=401, code="auth_required")
                return {
                    "success": True,
                    "status": 200,
                    "code": "logout_ok",
                    "message": "Sessão encerrada com sucesso.",
                    "next": url_for("auth.login"),
                }, 200
            flash("Sessão encerrada. Faça login novamente para continuar.", "warning")
            return redirect(url_for("auth.login"))
        if expects_json_response():
            endpoint = request.endpoint
            if endpoint and not is_endpoint_permitted(current_user, endpoint):
                if current_user.is_authenticated:
                    return error_payload("Acesso negado para esta operação.", status=403, code="forbidden")
                return error_payload("Autenticação obrigatória ou sessão expirada.", status=401, code="auth_required")
            return error_payload("CSRF inválido ou sessão expirada. Atualize a página e tente novamente.", status=400, code="csrf_error")
        flash("Sua sessão expirou ou a página ficou desatualizada. Recarregue e tente novamente.", "error")
        if current_user.is_authenticated:
            return redirect(request.referrer or url_for("dashboard.dashboard"))
        return redirect(url_for("auth.login"))

    @app.errorhandler(400)
    def handle_bad_request(_error):
        if expects_json_response():
            return error_payload("Requisição inválida.", status=400, code="bad_request")
        flash("Requisição inválida. Revise os dados e tente novamente.", "error")
        return redirect(request.referrer or (url_for("dashboard.dashboard") if current_user.is_authenticated else url_for("auth.login")))

    @app.errorhandler(403)
    def handle_forbidden(_error):
        if expects_json_response():
            return error_payload("Acesso negado para esta operação.", status=403, code="forbidden")
        if expects_binary_asset_response():
            return "", 403
        return _html_error_response(
            status=403,
            title="Acesso negado",
            message="Você não tem permissão para acessar esta funcionalidade.",
            request_id=getattr(g, "request_id", None),
        )

    @app.errorhandler(404)
    def handle_not_found(_error):
        if expects_json_response():
            return error_payload("Recurso não encontrado.", status=404, code="not_found")
        flash("Recurso não encontrado.", "error")
        return redirect(url_for("dashboard.dashboard") if current_user.is_authenticated else url_for("auth.login"))

    @app.errorhandler(409)
    def handle_conflict(_error):
        if expects_json_response():
            return error_payload("Conflito de dados na operação solicitada.", status=409, code="conflict")
        flash("Conflito de dados detectado. Atualize a página e tente novamente.", "error")
        return redirect(request.referrer or (url_for("dashboard.dashboard") if current_user.is_authenticated else url_for("auth.login")))

    @app.errorhandler(422)
    def handle_unprocessable(_error):
        if expects_json_response():
            return error_payload("Dados inválidos para processar a solicitação.", status=422, code="unprocessable_entity")
        flash("Dados inválidos para esta operação.", "error")
        return redirect(request.referrer or (url_for("dashboard.dashboard") if current_user.is_authenticated else url_for("auth.login")))

    @app.errorhandler(503)
    def handle_service_unavailable(_error):
        request_id = getattr(g, "request_id", None)
        _log_error_event(
            app,
            status=503,
            code="service_unavailable",
            error_type=type(_error).__name__,
            error_message=str(_error),
            request_id=request_id,
        )
        if expects_json_response():
            return error_payload("Serviço temporariamente indisponível.", status=503, code="service_unavailable")
        if expects_binary_asset_response():
            return "", 503
        return _html_error_response(
            status=503,
            title="Serviço temporariamente indisponível",
            message="Não foi possível concluir a operação agora. Tente novamente em instantes.",
            request_id=request_id,
        )

    @app.errorhandler(500)
    def handle_internal_error(_error):
        request_id = getattr(g, "request_id", None)
        _log_error_event(
            app,
            status=500,
            code="internal_error",
            error_type=type(_error).__name__,
            error_message=str(_error),
            request_id=request_id,
        )
        app.logger.exception(
            "Unhandled internal error. request_id=%s path=%s endpoint=%s method=%s user_id=%s",
            request_id,
            request.path,
            request.endpoint,
            request.method,
            _safe_current_user_id(),
        )
        if expects_json_response():
            return error_payload("Erro interno do servidor.", status=500, code="internal_error")
        if expects_binary_asset_response():
            return "", 500
        return _html_error_response(
            status=500,
            title="Erro interno do sistema",
            message="Ocorreu uma falha inesperada ao processar sua solicitação.",
            request_id=request_id,
        )
