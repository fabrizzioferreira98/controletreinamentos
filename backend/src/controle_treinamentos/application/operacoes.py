from __future__ import annotations

from flask import current_app, has_app_context

from ..audit import record_audit_event
from ..constants import PERNOITE_TIPO_OPTIONS
from ..core.domain_errors import DomainError, DomainNotFoundError, DomainValidationError
from ..db import get_db
from ..repositories.operacoes import (
    count_pernoites,
    delete_pernoite,
    fetch_pernoite,
    fetch_pernoite_detail,
    fetch_pernoite_list_page,
    insert_pernoite,
    tripulante_exists,
    update_pernoite,
)
from ..services import parse_date

PERNOITE_TIPO_LABELS = {
    "cobertura_base": "Cobertura de base",
    "operacional_comum": "Operacional comum",
}


def _text(payload: dict, key: str, default: str = "") -> str:
    return _clean_text(payload.get(key, default))


def _clean_text(value) -> str:
    return str(value or "").strip()


def _required_text(payload: dict, key: str, label: str) -> str:
    value = _text(payload, key)
    if not value:
        raise DomainValidationError(f"{label} e obrigatorio.")
    return value


def _optional_int(payload: dict, key: str, label: str) -> int | None:
    raw = _text(payload, key)
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise DomainValidationError(f"{label} invalido.") from exc


def _required_int(payload: dict, key: str, label: str) -> int:
    value = _optional_int(payload, key, label)
    if value is None:
        raise DomainValidationError(f"{label} e obrigatorio.")
    return value


def _optional_date(payload: dict, key: str, label: str):
    raw = payload.get(key)
    if raw in (None, ""):
        return None
    value = parse_date(raw)
    if value is None:
        raise DomainValidationError(f"{label} invalida.")
    return value


def _required_date(payload: dict, key: str, label: str):
    value = _optional_date(payload, key, label)
    if value is None:
        raise DomainValidationError(f"{label} e obrigatoria.")
    return value


def _positive_int(value, *, default: int, maximum: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    parsed = max(1, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _optional_filter_int(value) -> int | None:
    raw = _clean_text(value)
    if not raw or not raw.isdigit():
        return None
    return int(raw)


def _date_iso(value) -> str | None:
    if value in (None, ""):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _pernoite_type_options() -> list[dict]:
    return [
        {"value": value, "label": PERNOITE_TIPO_LABELS.get(value, value)}
        for value in PERNOITE_TIPO_OPTIONS
    ]


def _serialize_pernoite_read_item(row: dict) -> dict:
    tipo = _clean_text(row.get("tipo_pernoite"))
    return {
        "id": int(row["id"]),
        "tripulante_id": int(row["tripulante_id"]),
        "tripulante_nome": _clean_text(row.get("tripulante_nome")),
        "data_pernoite": _date_iso(row.get("data_pernoite")),
        "tipo_pernoite": tipo,
        "tipo_label": PERNOITE_TIPO_LABELS.get(tipo, tipo),
        "quantidade": int(row.get("quantidade") or 0),
        "observacoes": row.get("observacoes") or None,
    }


def list_pernoites_read_model(*, tipo: str = "", tripulante: str = "", page=1, per_page=20) -> dict:
    db = get_db()
    normalized_tipo = _clean_text(tipo)
    if normalized_tipo not in PERNOITE_TIPO_OPTIONS:
        normalized_tipo = ""
    tripulante_id = _optional_filter_int(tripulante)
    current_page = _positive_int(page, default=1)
    page_size = _positive_int(per_page, default=20, maximum=100)
    total = count_pernoites(db, tipo=normalized_tipo, tripulante_id=tripulante_id)
    offset = (current_page - 1) * page_size
    rows = fetch_pernoite_list_page(
        db,
        tipo=normalized_tipo,
        tripulante_id=tripulante_id,
        limit=page_size,
        offset=offset,
    )
    total_pages = max(1, (total + page_size - 1) // page_size)
    return {
        "items": [_serialize_pernoite_read_item(row) for row in rows],
        "filters": {
            "tipo": normalized_tipo,
            "tripulante": str(tripulante_id or ""),
        },
        "options": {
            "tipo_pernoite": _pernoite_type_options(),
        },
        "pagination": {
            "page": current_page,
            "per_page": page_size,
            "total": total,
            "total_pages": total_pages,
            "has_next": current_page < total_pages,
            "has_prev": current_page > 1,
        },
    }


def get_pernoite_read_model(*, pernoite_id: int) -> dict:
    db = get_db()
    row = fetch_pernoite_detail(db, pernoite_id)
    if not row:
        raise DomainNotFoundError("Pernoite nao encontrado.", code="operacoes_pernoite_not_found")
    return {"item": _serialize_pernoite_read_item(row)}


def _audit_event(db, *, entidade: str, entidade_id: int, acao: str, realizado_por: int, anterior=None, novo=None) -> None:
    strict_mode = bool(current_app.config.get("AUDIT_STRICT_MODE", False)) if has_app_context() else False
    try:
        db.execute("SAVEPOINT audit_event_operacoes_use_case_sp")
        record_audit_event(
            db,
            entidade=entidade,
            entidade_id=entidade_id,
            acao=acao,
            realizado_por=realizado_por,
            payload_anterior=anterior,
            payload_novo=novo,
        )
        db.execute("RELEASE SAVEPOINT audit_event_operacoes_use_case_sp")
    except Exception as exc:
        try:
            db.execute("ROLLBACK TO SAVEPOINT audit_event_operacoes_use_case_sp")
        except Exception:
            db.conn.rollback()
        if strict_mode:
            raise DomainError("Falha ao persistir auditoria em modo estrito.", status=500, code="audit_failed") from exc
        if has_app_context():
            current_app.logger.exception("Falha ao registrar evento de auditoria em operacoes.")


def _ensure_pernoite_references(db, *, tripulante_id: int) -> None:
    if not tripulante_exists(db, tripulante_id):
        raise DomainValidationError("Tripulante invalido para o pernoite.")


def _pernoite_data(payload: dict) -> dict:
    tipo_pernoite = _required_text(payload, "tipo_pernoite", "Tipo de pernoite")
    if tipo_pernoite not in PERNOITE_TIPO_OPTIONS:
        raise DomainValidationError("Tipo de pernoite invalido.")
    quantidade = _required_int(payload, "quantidade", "Quantidade")
    if quantidade <= 0:
        raise DomainValidationError("A quantidade deve ser maior que zero.")
    return {
        "tripulante_id": _required_int(payload, "tripulante_id", "Tripulante"),
        "data_pernoite": _required_date(payload, "data_pernoite", "Data do pernoite"),
        "tipo_pernoite": tipo_pernoite,
        "quantidade": quantidade,
        "observacoes": _text(payload, "observacoes") or None,
    }


def create_pernoite(payload: dict, *, actor_user_id: int) -> dict:
    db = get_db()
    data = _pernoite_data(payload)
    _ensure_pernoite_references(db, tripulante_id=data["tripulante_id"])
    try:
        created = insert_pernoite(db, data=data)
        _audit_event(db, entidade="pernoite_operacional", entidade_id=created["id"], acao="create", realizado_por=actor_user_id, novo=data)
        db.commit()
    except DomainError:
        db.conn.rollback()
        raise
    except Exception as exc:
        db.conn.rollback()
        if has_app_context():
            current_app.logger.exception("Falha ao salvar pernoite operacional.")
        raise DomainError("Nao foi possivel salvar o pernoite.", status=500, code="pernoite_save_failed") from exc
    return {"pernoite_id": int(created["id"]), "message": "Pernoite registrado com sucesso."}


def update_pernoite_use_case(pernoite_id: int, payload: dict, *, actor_user_id: int) -> dict:
    db = get_db()
    current = fetch_pernoite(db, pernoite_id)
    if not current:
        raise DomainNotFoundError("Pernoite nao encontrado.")
    data = _pernoite_data(payload)
    _ensure_pernoite_references(db, tripulante_id=data["tripulante_id"])
    try:
        update_pernoite(db, pernoite_id=pernoite_id, data=data)
        _audit_event(db, entidade="pernoite_operacional", entidade_id=pernoite_id, acao="update", realizado_por=actor_user_id, anterior=current, novo=data)
        db.commit()
    except DomainError:
        db.conn.rollback()
        raise
    except Exception as exc:
        db.conn.rollback()
        if has_app_context():
            current_app.logger.exception("Falha ao atualizar pernoite operacional.")
        raise DomainError("Nao foi possivel atualizar o pernoite.", status=500, code="pernoite_update_failed") from exc
    return {"pernoite_id": pernoite_id, "message": "Pernoite atualizado com sucesso."}


def delete_pernoite_use_case(pernoite_id: int, *, actor_user_id: int) -> dict:
    db = get_db()
    current = fetch_pernoite(db, pernoite_id)
    if not current:
        raise DomainNotFoundError("Pernoite nao encontrado.")
    try:
        _audit_event(db, entidade="pernoite_operacional", entidade_id=pernoite_id, acao="delete", realizado_por=actor_user_id, anterior=current)
        delete_pernoite(db, pernoite_id=pernoite_id)
        db.commit()
    except DomainError:
        db.conn.rollback()
        raise
    except Exception as exc:
        db.conn.rollback()
        if has_app_context():
            current_app.logger.exception("Falha ao excluir pernoite operacional.")
        raise DomainError("Nao foi possivel excluir o pernoite.", status=500, code="pernoite_delete_failed") from exc
    return {"pernoite_id": pernoite_id, "message": "Pernoite excluido com sucesso."}
