from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

try:
    import psycopg2
except ImportError:
    psycopg2 = None  # type: ignore[assignment]
from flask import current_app, session
from flask_login import current_user

from ..audit import record_audit_event
from ..constants import (
    AUDIT_ACTION_LABELS,
    AUDIT_ENTITY_LABELS,
    LOGIN_ATTEMPT_WINDOW_MINUTES,
    LOGIN_LOCKOUT_MINUTES,
    LOGIN_MAX_ATTEMPTS,
)


def rollback_db(db):
    db.conn.rollback()

def login_attempt_state():
    now = datetime.now(ZoneInfo("America/Sao_Paulo"))
    lock_until = session.get("login_lock_until")
    failures = session.get("login_failures", [])
    normalized_failures = []
    for item in failures:
        if item:
            try:
                normalized = datetime.fromisoformat(item)
            except (TypeError, ValueError):
                continue
            if now - normalized <= timedelta(minutes=LOGIN_ATTEMPT_WINDOW_MINUTES):
                normalized_failures.append(item)
    if lock_until:
        try:
            locked_until_dt = datetime.fromisoformat(lock_until)
        except ValueError:
            locked_until_dt = None
        if locked_until_dt and locked_until_dt > now:
            return normalized_failures, locked_until_dt
    return normalized_failures, None

def register_login_failure():
    now = datetime.now(ZoneInfo("America/Sao_Paulo"))
    failures, _ = login_attempt_state()
    failures.append(now.isoformat())
    session["login_failures"] = failures
    if len(failures) >= LOGIN_MAX_ATTEMPTS:
        session["login_lock_until"] = (now + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)).isoformat()

def clear_login_failures():
    session.pop("login_failures", None)
    session.pop("login_lock_until", None)

def ensure_user_permissions_column(db):
    if current_app.config.get("USERS_PERMISSIONS_COLUMN_READY"):
        return
    try:
        db.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS permissao_modulos_json TEXT NOT NULL DEFAULT '[]'")
        db.execute("UPDATE usuarios SET permissao_modulos_json = '[]' WHERE permissao_modulos_json IS NULL")
        db.commit()
        current_app.config["USERS_PERMISSIONS_COLUMN_READY"] = True
    except psycopg2.Error:
        rollback_db(db)
        current_app.config["USERS_PERMISSIONS_COLUMN_READY"] = False
        current_app.logger.exception("Failed to ensure usuarios.permissao_modulos_json column.")

def tripulante_audit_payload(data):
    payload = dict(data or {})
    payload.pop("submitted_photo", None)
    if "foto_base64" in payload:
        payload["foto_base64"] = bool(payload["foto_base64"] or payload.get("foto_storage_ref"))
    if "remove_foto" in payload:
        payload["remove_foto"] = bool(payload["remove_foto"])
    return payload

def audit_entity_label(value: str | None) -> str:
    return AUDIT_ENTITY_LABELS.get((value or "").strip(), (value or "Registro").replace("_", " ").title())

def audit_action_label(value: str | None) -> str:
    return AUDIT_ACTION_LABELS.get((value or "").strip(), (value or "ação").replace("_", " ").title())

def build_audit_preview(payload):
    if not payload:
        return ""
    if isinstance(payload, dict):
        for key in ("nome", "email", "email_destinatario", "login", "matricula", "status", "base"):
            value = payload.get(key)
            if value not in (None, ""):
                return f"{key.replace('_', ' ').title()}: {value}"
        if payload:
            first_key = next(iter(payload))
            return f"{first_key.replace('_', ' ').title()}: {payload[first_key]}"
    if isinstance(payload, list) and payload:
        return f"{len(payload)} item(ns)"
    return str(payload)

def build_audit_simple_sentence(item: dict) -> str:
    autor = item.get("realizado_por_nome") or item.get("realizado_por_login") or "Usuário removido"
    entidade = item.get("entidade_label") or audit_entity_label(item.get("entidade"))
    entidade_id = item.get("entidade_id")
    action_key = (item.get("acao") or "").strip().lower()
    action_text_map = {
        "create": "cadastrou",
        "update": "atualizou",
        "delete": "excluiu",
        "status_change": "alterou o status de",
        "move": "movimentou",
    }
    action_text = action_text_map.get(action_key, "executou ação em")
    id_suffix = f" #{entidade_id}" if entidade_id not in (None, "") else ""
    return f"{autor} {action_text} {entidade}{id_suffix}"

def audit_event(db, entidade, entidade_id, acao, anterior=None, novo=None, observacao=None):
    strict_mode = bool(current_app.config.get("AUDIT_STRICT_MODE", False))
    try:
        db.execute("SAVEPOINT audit_event_sp")
        record_audit_event(
            db,
            entidade=entidade,
            entidade_id=entidade_id,
            acao=acao,
            realizado_por=int(current_user.id),
            payload_anterior=anterior,
            payload_novo=novo,
            observacao=observacao,
        )
        db.execute("RELEASE SAVEPOINT audit_event_sp")
    except Exception as exc:
        try:
            db.execute("ROLLBACK TO SAVEPOINT audit_event_sp")
        except Exception:
            db.conn.rollback()
        if strict_mode:
            current_app.logger.exception("Audit event failed and strict mode aborted the main operation.")
            raise RuntimeError("Falha ao persistir auditoria em modo estrito.") from exc
        current_app.logger.exception("Audit event failed but main operation will continue.")


def _configured_database_available() -> bool:
    try:
        return bool((current_app.config.get("DATABASE_URL") or "").strip())
    except RuntimeError:
        return False


def _resolve_audit_db(db=None):
    if db is not None:
        return db
    if not _configured_database_available():
        return None
    from ..db import get_db

    return get_db()


def _numeric_audit_entity_id(value) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, numeric)


def audit_document_generation(
    db=None,
    *,
    policy=None,
    policy_key: str | None = None,
    kind: str | None = None,
    domain: str | None = None,
    renderer: str | None = None,
    filename: str,
    entity_id=None,
    filters: dict | None = None,
    details: dict | None = None,
    commit: bool = False,
) -> bool:
    audit_db = _resolve_audit_db(db)
    if audit_db is None:
        return False
    resolved_policy_key = getattr(policy, "key", None) or policy_key or "documento"
    resolved_kind = getattr(policy, "kind", None) or kind or "document"
    resolved_domain = getattr(policy, "domain", None) or domain or "documentos"
    resolved_renderer = getattr(policy, "renderer", None) or renderer or "unknown"
    payload = {
        "policy_key": resolved_policy_key,
        "kind": resolved_kind,
        "domain": resolved_domain,
        "renderer": resolved_renderer,
        "filename": filename,
        "target_entity_id": entity_id,
        "filters": filters or {},
        **(details or {}),
    }
    audit_event(
        audit_db,
        "documento_gerado",
        _numeric_audit_entity_id(entity_id),
        "document_generate",
        novo=payload,
        observacao=f"policy={resolved_policy_key} domain={resolved_domain}",
    )
    if commit:
        audit_db.commit()
    return True


def audit_relevant_download(
    db=None,
    *,
    entidade: str,
    entidade_id: int,
    policy_key: str,
    action: str,
    filename: str,
    subject_id=None,
    source: str = "",
    commit: bool = False,
) -> bool:
    if (action or "").strip().lower() != "download":
        return False
    audit_db = _resolve_audit_db(db)
    if audit_db is None:
        return False
    audit_event(
        audit_db,
        entidade,
        _numeric_audit_entity_id(entidade_id),
        "download",
        novo={
            "policy_key": policy_key,
            "filename": filename,
            "subject_id": subject_id,
            "source": source,
        },
        observacao=f"download_relevante source={source or '-'} policy={policy_key}",
    )
    if commit:
        audit_db.commit()
    return True
