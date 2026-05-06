from __future__ import annotations

from datetime import date

from ..audit import record_audit_event
from ..contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT, serialize_finance_holiday
from ..core.domain_errors import DomainConflictError, DomainError, DomainNotFoundError, DomainValidationError
from ..db import get_db
from ..financeiro_audit_events import FINANCE_AUDIT_EVENTS_BY_NAME
from ..repositories.financeiro_feriados import atualizar_feriado_nacional as atualizar_feriado_nacional_row
from ..repositories.financeiro_feriados import criar_feriado_nacional as criar_feriado_nacional_row
from ..repositories.financeiro_feriados import (
    detalhar_feriado_nacional,
    verificar_duplicidade_feriado_nacional,
    verificar_feriado_nacional_por_data,
)
from ..repositories.financeiro_feriados import listar_feriados_nacionais as listar_feriados_nacionais_rows

_HOLIDAY_PATCH_ALLOWED_FIELDS = {"data", "nome", "tipo", "localidade", "status"}


class FeriadoFinanceiroInvalidoErro(DomainValidationError):
    def __init__(self, message: str, *, code: str = "feriado_financeiro_invalido"):
        super().__init__(message, code=code, status=400)


class FeriadoFinanceiroDuplicadoErro(DomainConflictError):
    def __init__(self, message: str = "Feriado nacional ativo ja cadastrado para esta data."):
        super().__init__(message, code="feriado_financeiro_duplicado", status=409)


class FeriadoFinanceiroNaoEncontradoErro(DomainNotFoundError):
    def __init__(self, message: str = "Feriado financeiro nacional nao encontrado."):
        super().__init__(message, code="feriado_financeiro_nao_encontrado", status=404)


def _resolve_db(db=None):
    return db if db is not None else get_db()


def _resolve_org_id(org_id: str | None) -> str:
    return (org_id or "").strip() or FINANCE_ORG_SCOPE_DEFAULT


def _clean_text(value) -> str:
    return str(value or "").strip()


def _required_text(payload: dict, key: str, label: str) -> str:
    value = _clean_text(payload.get(key))
    if not value:
        raise FeriadoFinanceiroInvalidoErro(f"{label} e obrigatorio.", code="feriado_financeiro_campo_obrigatorio")
    return value


def _parse_date(value, *, label: str) -> date:
    if value in (None, ""):
        raise FeriadoFinanceiroInvalidoErro(
            f"{label} e obrigatoria.",
            code="feriado_financeiro_campo_obrigatorio",
        )
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise FeriadoFinanceiroInvalidoErro(
            f"{label} deve estar no formato YYYY-MM-DD.",
            code="feriado_financeiro_campo_invalido",
        ) from exc


def _validate_tipo_nacional(tipo: str) -> None:
    if tipo != "nacional":
        raise FeriadoFinanceiroInvalidoErro(
            "Nesta fase, somente feriados nacionais sao aceitos.",
            code="feriado_financeiro_tipo_invalido",
        )


def _validate_status(status: str) -> None:
    if status not in {"ativo", "inativo"}:
        raise FeriadoFinanceiroInvalidoErro(
            "Status de feriado financeiro invalido.",
            code="feriado_financeiro_status_invalido",
        )


def _holiday_payload(payload: dict, *, org_id: str, actor_user_id: int | None = None) -> dict:
    tipo = _required_text(payload, "tipo", "Tipo")
    _validate_tipo_nacional(tipo)
    status = _clean_text(payload.get("status")) or "ativo"
    _validate_status(status)
    return {
        "org_id": org_id,
        "data": _parse_date(payload.get("data"), label="Data").isoformat(),
        "nome": _required_text(payload, "nome", "Nome"),
        "tipo": "nacional",
        # Decisao de fase: localidade enviada para feriado nacional e normalizada para null.
        "localidade": None,
        "status": status,
        "created_by": actor_user_id,
        "updated_by": actor_user_id,
    }


def _holiday_update_payload(before: dict, payload: dict, *, org_id: str, actor_user_id: int | None = None) -> dict:
    if not isinstance(payload, dict) or not payload:
        raise DomainValidationError(
            "Payload de atualizacao de feriado vazio ou invalido.",
            code="finance_holiday_patch_empty_or_invalid",
            status=400,
            details={"allowed_fields": sorted(_HOLIDAY_PATCH_ALLOWED_FIELDS)},
        )

    invalid_fields = sorted(key for key in payload if key not in _HOLIDAY_PATCH_ALLOWED_FIELDS)
    if invalid_fields:
        raise DomainValidationError(
            "Payload de atualizacao de feriado contem campos nao permitidos.",
            code="finance_holiday_patch_empty_or_invalid",
            status=400,
            details={
                "allowed_fields": sorted(_HOLIDAY_PATCH_ALLOWED_FIELDS),
                "invalid_fields": invalid_fields,
            },
        )

    submitted = {key: value for key, value in payload.items() if key in _HOLIDAY_PATCH_ALLOWED_FIELDS}
    if not submitted:
        raise DomainValidationError(
            "Payload de atualizacao de feriado vazio ou invalido.",
            code="finance_holiday_patch_empty_or_invalid",
            status=400,
            details={"allowed_fields": sorted(_HOLIDAY_PATCH_ALLOWED_FIELDS)},
        )

    merged = {**dict(before), **submitted, "org_id": org_id}
    data = _holiday_payload(merged, org_id=org_id, actor_user_id=actor_user_id)
    update_payload = {key: value for key, value in data.items() if key in submitted or key == "updated_by"}

    effective_fields = [key for key in update_payload if key != "updated_by"]
    before_serialized = serialize_finance_holiday(before)
    after_serialized = serialize_finance_holiday({**dict(before), **update_payload})
    changed_fields = [key for key in effective_fields if before_serialized.get(key) != after_serialized.get(key)]
    if not changed_fields:
        raise DomainValidationError(
            "Payload de atualizacao de feriado sem alteracoes efetivas.",
            code="finance_holiday_patch_empty_or_invalid",
            status=400,
            details={
                "allowed_fields": sorted(_HOLIDAY_PATCH_ALLOWED_FIELDS),
                "submitted_fields": sorted(submitted),
            },
        )

    return update_payload


def _ensure_no_duplicate(db, *, data: dict, exclude_id: int | None = None) -> None:
    if data.get("status") != "ativo":
        return
    duplicate = verificar_duplicidade_feriado_nacional(
        db,
        org_id=data["org_id"],
        data=data["data"],
        exclude_id=exclude_id,
    )
    if duplicate:
        raise FeriadoFinanceiroDuplicadoErro()


def _changed_fields(before: dict, after: dict) -> list[str]:
    ignored = {"updated_at"}
    before_payload = serialize_finance_holiday(before)
    after_payload = serialize_finance_holiday(after)
    return sorted(
        field
        for field in after_payload
        if field in before_payload and field not in ignored and before_payload.get(field) != after_payload.get(field)
    )


def _audit_payload(holiday: dict, *, event_name: str, actor_user_id: int, changed_fields: list[str] | None = None) -> dict:
    event = FINANCE_AUDIT_EVENTS_BY_NAME[event_name]
    return {
        "holiday": holiday,
        "audit_metadata": {
            "event_name": event_name,
            "org_id": holiday.get("org_id"),
            "actor_user_id": actor_user_id,
            "entity_type": "finance_holiday",
            "entity_id": holiday.get("id"),
            "permission": event["permission"],
            "tipo": holiday.get("tipo"),
            "data": holiday.get("data"),
            "vigencia_inicio": holiday.get("data"),
            "vigencia_fim": holiday.get("data"),
            "changed_fields": changed_fields or [],
            "reason": None,
        },
    }


def _record_finance_holiday_audit(
    db,
    *,
    event_name: str,
    holiday_id: int,
    actor_user_id: int,
    before: dict | None = None,
    after: dict | None = None,
    changed_fields: list[str] | None = None,
) -> None:
    event = FINANCE_AUDIT_EVENTS_BY_NAME[event_name]
    allowed_entity_types = set(event.get("allowed_entity_types") or (event["entity_type"],))
    if "finance_holiday" not in allowed_entity_types:
        raise DomainError(
            "Catalogo de auditoria financeira nao permite feriados.",
            status=500,
            code="finance_holiday_audit_catalog_invalid",
        )
    reference = after or before or {}
    record_audit_event(
        db,
        entidade="finance_holiday",
        entidade_id=holiday_id,
        acao=event_name,
        realizado_por=actor_user_id,
        payload_anterior=(
            _audit_payload(before, event_name=event_name, actor_user_id=actor_user_id, changed_fields=changed_fields)
            if before
            else None
        ),
        payload_novo=(
            _audit_payload(after, event_name=event_name, actor_user_id=actor_user_id, changed_fields=changed_fields)
            if after
            else None
        ),
        observacao=f"org_id={reference.get('org_id')}; data={reference.get('data')}; tipo=nacional",
    )


def criar_feriado_nacional(payload: dict, *, actor_user_id: int, org_id: str | None = None, db=None) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id or payload.get("org_id"))
    data = _holiday_payload(payload, org_id=resolved_org_id, actor_user_id=actor_user_id)
    try:
        _ensure_no_duplicate(resolved_db, data=data)
        created = criar_feriado_nacional_row(resolved_db, data=data, org_id=resolved_org_id)
        serialized = serialize_finance_holiday(created)
        _record_finance_holiday_audit(
            resolved_db,
            event_name="finance.parameter.created",
            holiday_id=created["id"],
            actor_user_id=actor_user_id,
            after=serialized,
        )
        resolved_db.commit()
        return serialized
    except DomainError:
        resolved_db.conn.rollback()
        raise
    except Exception as exc:
        resolved_db.conn.rollback()
        raise DomainError(
            "Nao foi possivel criar o feriado nacional.",
            status=500,
            code="feriado_financeiro_create_failed",
        ) from exc


def listar_feriados_nacionais(
    *,
    org_id: str | None = None,
    status: str | None = None,
    ano: int | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None,
    page: int = 1,
    offset: int = 0,
    limit: int = 100,
    db=None,
) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id)
    start = _parse_date(data_inicio, label="Data inicial").isoformat() if data_inicio else None
    end = _parse_date(data_fim, label="Data final").isoformat() if data_fim else None
    rows = listar_feriados_nacionais_rows(
        resolved_db,
        org_id=resolved_org_id,
        status=_clean_text(status) or None,
        ano=ano,
        data_inicio=start,
        data_fim=end,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [serialize_finance_holiday(row) for row in rows],
        "pagination": {
            "page": int(page),
            "offset": int(offset),
            "total": len(rows),
        },
    }


def atualizar_feriado_nacional(
    feriado_id: int,
    payload: dict,
    *,
    actor_user_id: int,
    org_id: str | None = None,
    db=None,
) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id or payload.get("org_id"))
    before_row = detalhar_feriado_nacional(resolved_db, feriado_id=feriado_id, org_id=resolved_org_id)
    if not before_row:
        raise FeriadoFinanceiroNaoEncontradoErro()
    data = _holiday_update_payload(before_row, payload, org_id=resolved_org_id, actor_user_id=actor_user_id)
    effective_data = {**dict(before_row), **data, "org_id": resolved_org_id, "tipo": "nacional", "localidade": None}
    try:
        _ensure_no_duplicate(resolved_db, data=effective_data, exclude_id=feriado_id)
        updated = atualizar_feriado_nacional_row(
            resolved_db,
            feriado_id=feriado_id,
            data=data,
            org_id=resolved_org_id,
        )
        if not updated:
            raise FeriadoFinanceiroNaoEncontradoErro()
        before = serialize_finance_holiday(before_row)
        after = serialize_finance_holiday(updated)
        changed = _changed_fields(dict(before_row), dict(updated))
        _record_finance_holiday_audit(
            resolved_db,
            event_name="finance.parameter.updated",
            holiday_id=feriado_id,
            actor_user_id=actor_user_id,
            before=before,
            after=after,
            changed_fields=changed,
        )
        resolved_db.commit()
        return after
    except DomainError:
        resolved_db.conn.rollback()
        raise
    except Exception as exc:
        resolved_db.conn.rollback()
        raise DomainError(
            "Nao foi possivel atualizar o feriado nacional.",
            status=500,
            code="feriado_financeiro_update_failed",
        ) from exc


def verificar_feriado_nacional(
    *,
    data: str,
    org_id: str | None = None,
    db=None,
) -> dict | None:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id)
    checked_date = _parse_date(data, label="Data")
    row = verificar_feriado_nacional_por_data(
        resolved_db,
        org_id=resolved_org_id,
        data=checked_date.isoformat(),
    )
    return serialize_finance_holiday(row) if row else None
