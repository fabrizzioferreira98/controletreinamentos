from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from ..audit import record_audit_event
from ..contracts.financeiro import (
    FINANCE_CREW_FUNCTIONS,
    FINANCE_ORG_SCOPE_DEFAULT,
    FINANCE_PARAMETER_TYPES,
    serialize_finance_parameter,
)
from ..core.domain_errors import DomainConflictError, DomainError, DomainNotFoundError, DomainValidationError
from ..db import get_db
from ..financeiro_audit_events import FINANCE_AUDIT_EVENTS_BY_NAME
from ..repositories.financeiro_parametros import (
    atualizar_parametro_financeiro as atualizar_parametro_financeiro_row,
)
from ..repositories.financeiro_parametros import (
    buscar_parametro_vigente as buscar_parametro_vigente_row,
)
from ..repositories.financeiro_parametros import (
    criar_parametro_financeiro as criar_parametro_financeiro_row,
)
from ..repositories.financeiro_parametros import (
    detalhar_parametro_financeiro,
    verificar_sobreposicao_vigencia,
)
from ..repositories.financeiro_parametros import (
    listar_parametros_financeiros as listar_parametros_financeiros_rows,
)

DAY_PERIOD_PARAMETER_TYPES = {"periodo_diurno_inicio", "periodo_diurno_fim"}
DAY_PERIOD_UNIT = "minutos_do_dia"
GLOBAL_HOURLY_PARAMETER_TYPES = {"duracao_hora_noturna_minutos"} | DAY_PERIOD_PARAMETER_TYPES
REQUIRED_CREW_FUNCTION_PARAMETER_TYPES = {"pernoite_comum_sem_cobertura"}

_PARAMETER_PATCH_ALLOWED_FIELDS = {
    "tipo",
    "funcao",
    "categoria",
    "valor",
    "unidade",
    "vigencia_inicio",
    "vigencia_fim",
    "status",
    "motivo",
    "reason",
}


class ParametroFinanceiroInvalidoErro(DomainValidationError):
    def __init__(self, message: str, *, code: str = "parametro_financeiro_invalido"):
        super().__init__(message, code=code, status=400)


class ParametroFinanceiroSobrepostoErro(DomainConflictError):
    def __init__(self, message: str = "Parametro financeiro ativo sobrepoe vigencia existente."):
        super().__init__(message, code="parametro_financeiro_sobreposto", status=409)


class ParametroFinanceiroNaoEncontradoErro(DomainNotFoundError):
    def __init__(self, message: str = "Parametro financeiro nao encontrado."):
        super().__init__(message, code="parametro_financeiro_nao_encontrado", status=404)


def _resolve_db(db=None):
    return db if db is not None else get_db()


def _resolve_org_id(org_id: str | None) -> str:
    return (org_id or "").strip() or FINANCE_ORG_SCOPE_DEFAULT


def _clean_text(value) -> str:
    return str(value or "").strip()


def _optional_text(value) -> str | None:
    text = _clean_text(value)
    return text or None


def _optional_funcao(value) -> str | None:
    text = _optional_text(value)
    return text.lower() if text else None


def _normalize_funcao_for_parameter(*, tipo: str, funcao_value) -> str | None:
    if tipo in GLOBAL_HOURLY_PARAMETER_TYPES:
        return None
    funcao = _optional_funcao(funcao_value)
    if funcao and funcao not in FINANCE_CREW_FUNCTIONS:
        raise ParametroFinanceiroInvalidoErro(
            "Funcao operacional invalida para parametro financeiro.",
            code="parametro_financeiro_funcao_invalida",
        )
    if tipo in REQUIRED_CREW_FUNCTION_PARAMETER_TYPES and not funcao:
        raise ParametroFinanceiroInvalidoErro(
            "Funcao operacional e obrigatoria para parametro de pernoite comum sem cobertura.",
            code="parametro_financeiro_funcao_obrigatoria",
        )
    return funcao


def _required_text(payload: dict, key: str, label: str) -> str:
    value = _clean_text(payload.get(key))
    if not value:
        raise ParametroFinanceiroInvalidoErro(f"{label} e obrigatorio.", code="parametro_financeiro_campo_obrigatorio")
    return value


def _parse_decimal(value, *, label: str) -> Decimal:
    if value in (None, ""):
        raise ParametroFinanceiroInvalidoErro(f"{label} e obrigatorio.", code="parametro_financeiro_campo_obrigatorio")
    try:
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError) as exc:
        raise ParametroFinanceiroInvalidoErro(f"{label} invalido.", code="parametro_financeiro_campo_invalido") from exc


def _validate_day_period_value(*, tipo: str, valor: Decimal, unidade: str) -> None:
    if tipo not in DAY_PERIOD_PARAMETER_TYPES:
        return
    if unidade != DAY_PERIOD_UNIT:
        raise ParametroFinanceiroInvalidoErro(
            "Periodo diurno deve usar unidade minutos_do_dia.",
            code="parametro_financeiro_unidade_invalida",
        )
    if valor != valor.to_integral_value():
        raise ParametroFinanceiroInvalidoErro(
            "Periodo diurno deve usar minuto inteiro desde 00:00.",
            code="parametro_financeiro_valor_invalido",
        )
    minute = int(valor)
    if minute < 0 or minute > 1439:
        raise ParametroFinanceiroInvalidoErro(
            "Periodo diurno deve estar entre 0 e 1439 minutos desde 00:00.",
            code="parametro_financeiro_valor_invalido",
        )
    if 0 < minute < 60:
        raise ParametroFinanceiroInvalidoErro(
            "Use minutos desde 00:00 para periodo diurno; exemplo: 360 para 06:00.",
            code="parametro_financeiro_valor_invalido",
        )


def _parse_date(value, *, label: str, required: bool = True) -> date | None:
    if value in (None, ""):
        if required:
            raise ParametroFinanceiroInvalidoErro(
                f"{label} e obrigatoria.",
                code="parametro_financeiro_campo_obrigatorio",
            )
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise ParametroFinanceiroInvalidoErro(
            f"{label} deve estar no formato YYYY-MM-DD.",
            code="parametro_financeiro_campo_invalido",
        ) from exc


def _validate_parameter_type(tipo: str) -> None:
    if tipo not in FINANCE_PARAMETER_TYPES:
        raise ParametroFinanceiroInvalidoErro(
            "Tipo de parametro financeiro invalido.",
            code="parametro_financeiro_tipo_invalido",
        )


def _validate_status(status: str) -> None:
    if status not in {"ativo", "inativo", "substituido"}:
        raise ParametroFinanceiroInvalidoErro(
            "Status de parametro financeiro invalido.",
            code="parametro_financeiro_status_invalido",
        )


def _parameter_payload(payload: dict, *, org_id: str, actor_user_id: int | None = None) -> dict:
    tipo = _required_text(payload, "tipo", "Tipo")
    _validate_parameter_type(tipo)
    status = _clean_text(payload.get("status")) or "ativo"
    _validate_status(status)
    vigencia_inicio = _parse_date(payload.get("vigencia_inicio"), label="Vigencia inicial")
    vigencia_fim = _parse_date(payload.get("vigencia_fim"), label="Vigencia final", required=False)
    if vigencia_fim and vigencia_fim < vigencia_inicio:
        raise ParametroFinanceiroInvalidoErro(
            "Vigencia final nao pode ser anterior a vigencia inicial.",
            code="parametro_financeiro_vigencia_invalida",
        )
    valor = _parse_decimal(payload.get("valor"), label="Valor")
    unidade = _required_text(payload, "unidade", "Unidade")
    _validate_day_period_value(tipo=tipo, valor=valor, unidade=unidade)
    return {
        "org_id": org_id,
        "tipo": tipo,
        "funcao": _normalize_funcao_for_parameter(tipo=tipo, funcao_value=payload.get("funcao")),
        "categoria": _optional_text(payload.get("categoria")),
        "valor": valor,
        "unidade": unidade,
        "vigencia_inicio": vigencia_inicio.isoformat(),
        "vigencia_fim": vigencia_fim.isoformat() if vigencia_fim else None,
        "status": status,
        "motivo": _optional_text(payload.get("motivo") or payload.get("reason")),
        "created_by": actor_user_id,
        "updated_by": actor_user_id,
    }


def _parameter_update_payload(before: dict, payload: dict, *, org_id: str, actor_user_id: int | None = None) -> dict:
    if not isinstance(payload, dict) or not payload:
        raise DomainValidationError(
            "Payload de atualizacao de parametro vazio ou invalido.",
            code="finance_parameter_patch_empty_or_invalid",
            status=400,
            details={"allowed_fields": sorted(_PARAMETER_PATCH_ALLOWED_FIELDS)},
        )

    invalid_fields = sorted(key for key in payload if key not in _PARAMETER_PATCH_ALLOWED_FIELDS)
    if invalid_fields:
        raise DomainValidationError(
            "Payload de atualizacao de parametro contem campos nao permitidos.",
            code="finance_parameter_patch_empty_or_invalid",
            status=400,
            details={
                "allowed_fields": sorted(_PARAMETER_PATCH_ALLOWED_FIELDS),
                "invalid_fields": invalid_fields,
            },
        )

    submitted = {key: value for key, value in payload.items() if key in _PARAMETER_PATCH_ALLOWED_FIELDS}
    if not submitted:
        raise DomainValidationError(
            "Payload de atualizacao de parametro vazio ou invalido.",
            code="finance_parameter_patch_empty_or_invalid",
            status=400,
            details={"allowed_fields": sorted(_PARAMETER_PATCH_ALLOWED_FIELDS)},
        )

    merged = {**dict(before), **submitted, "org_id": org_id}
    data = _parameter_payload(merged, org_id=org_id, actor_user_id=actor_user_id)
    update_payload = {
        key: value
        for key, value in data.items()
        if key in submitted or key == "updated_by" or (key == "motivo" and ("reason" in submitted or "motivo" in submitted))
    }

    effective_fields = [key for key in update_payload if key != "updated_by"]
    before_serialized = serialize_finance_parameter(before)
    after_serialized = serialize_finance_parameter({**dict(before), **update_payload})
    changed_fields = [key for key in effective_fields if before_serialized.get(key) != after_serialized.get(key)]
    if not changed_fields:
        raise DomainValidationError(
            "Payload de atualizacao de parametro sem alteracoes efetivas.",
            code="finance_parameter_patch_empty_or_invalid",
            status=400,
            details={
                "allowed_fields": sorted(_PARAMETER_PATCH_ALLOWED_FIELDS),
                "submitted_fields": sorted(submitted),
            },
        )

    return update_payload


def _ensure_no_overlap(db, *, data: dict, exclude_id: int | None = None) -> None:
    if data.get("status") != "ativo":
        return
    overlap = verificar_sobreposicao_vigencia(
        db,
        org_id=data["org_id"],
        tipo=data["tipo"],
        funcao=data.get("funcao"),
        categoria=data.get("categoria"),
        unidade=data["unidade"],
        vigencia_inicio=data["vigencia_inicio"],
        vigencia_fim=data.get("vigencia_fim"),
        exclude_id=exclude_id,
    )
    if overlap:
        raise ParametroFinanceiroSobrepostoErro()


def _changed_fields(before: dict, after: dict) -> list[str]:
    ignored = {"updated_at"}
    return sorted(
        field
        for field, value in after.items()
        if field in before and field not in ignored and serialize_finance_parameter(before).get(field) != serialize_finance_parameter(after).get(field)
    )


def _audit_payload(parameter: dict, *, event_name: str, actor_user_id: int, changed_fields: list[str] | None = None) -> dict:
    event = FINANCE_AUDIT_EVENTS_BY_NAME[event_name]
    return {
        "parameter": parameter,
        "audit_metadata": {
            "event_name": event_name,
            "org_id": parameter.get("org_id"),
            "actor_user_id": actor_user_id,
            "entity_type": event["entity_type"],
            "entity_id": parameter.get("id"),
            "permission": event["permission"],
            "tipo": parameter.get("tipo"),
            "vigencia_inicio": parameter.get("vigencia_inicio"),
            "vigencia_fim": parameter.get("vigencia_fim"),
            "changed_fields": changed_fields or [],
            "reason": parameter.get("motivo") or None,
        },
    }


def _record_finance_parameter_audit(
    db,
    *,
    event_name: str,
    parameter_id: int,
    actor_user_id: int,
    before: dict | None = None,
    after: dict | None = None,
    changed_fields: list[str] | None = None,
) -> None:
    event = FINANCE_AUDIT_EVENTS_BY_NAME[event_name]
    reference = after or before or {}
    record_audit_event(
        db,
        entidade=event["entity_type"],
        entidade_id=parameter_id,
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
        observacao=f"org_id={reference.get('org_id')}; tipo={reference.get('tipo')}",
    )


def criar_parametro_financeiro(payload: dict, *, actor_user_id: int, org_id: str | None = None, db=None) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id or payload.get("org_id"))
    data = _parameter_payload(payload, org_id=resolved_org_id, actor_user_id=actor_user_id)

    try:
        _ensure_no_overlap(resolved_db, data=data)
        created = criar_parametro_financeiro_row(resolved_db, data=data, org_id=resolved_org_id)
        serialized = serialize_finance_parameter(created)
        _record_finance_parameter_audit(
            resolved_db,
            event_name="finance.parameter.created",
            parameter_id=created["id"],
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
            "Nao foi possivel criar o parametro financeiro.",
            status=500,
            code="parametro_financeiro_create_failed",
        ) from exc


def listar_parametros_financeiros(
    *,
    org_id: str | None = None,
    tipo: str | None = None,
    status: str | None = None,
    funcao: str | None = None,
    categoria: str | None = None,
    unidade: str | None = None,
    vigencia_em: str | None = None,
    page: int = 1,
    offset: int = 0,
    limit: int = 100,
    db=None,
) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id)
    rows = listar_parametros_financeiros_rows(
        resolved_db,
        org_id=resolved_org_id,
        tipo=_optional_text(tipo),
        status=_optional_text(status),
        funcao=funcao,
        categoria=categoria,
        unidade=_optional_text(unidade),
        vigencia_em=_parse_date(vigencia_em, label="Data de vigencia", required=False).isoformat() if vigencia_em else None,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [serialize_finance_parameter(row) for row in rows],
        "pagination": {
            "page": int(page),
            "offset": int(offset),
            "total": len(rows),
        },
    }


def atualizar_parametro_financeiro(
    parametro_id: int,
    payload: dict,
    *,
    actor_user_id: int,
    org_id: str | None = None,
    db=None,
) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id or payload.get("org_id"))
    before_row = detalhar_parametro_financeiro(resolved_db, parametro_id=parametro_id, org_id=resolved_org_id)
    if not before_row:
        raise ParametroFinanceiroNaoEncontradoErro()
    data = _parameter_update_payload(before_row, payload, org_id=resolved_org_id, actor_user_id=actor_user_id)
    effective_data = {**dict(before_row), **data, "org_id": resolved_org_id}

    try:
        _ensure_no_overlap(resolved_db, data=effective_data, exclude_id=parametro_id)
        updated = atualizar_parametro_financeiro_row(
            resolved_db,
            parametro_id=parametro_id,
            data=data,
            org_id=resolved_org_id,
        )
        if not updated:
            raise ParametroFinanceiroNaoEncontradoErro()
        before = serialize_finance_parameter(before_row)
        after = serialize_finance_parameter(updated)
        changed = _changed_fields(dict(before_row), dict(updated))
        _record_finance_parameter_audit(
            resolved_db,
            event_name="finance.parameter.updated",
            parameter_id=parametro_id,
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
            "Nao foi possivel atualizar o parametro financeiro.",
            status=500,
            code="parametro_financeiro_update_failed",
        ) from exc


def buscar_parametro_vigente(
    *,
    tipo: str,
    vigencia_em: str,
    org_id: str | None = None,
    funcao: str | None = None,
    categoria: str | None = None,
    unidade: str | None = None,
    db=None,
) -> dict | None:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id)
    clean_tipo = _clean_text(tipo)
    _validate_parameter_type(clean_tipo)
    effective_date = _parse_date(vigencia_em, label="Data de vigencia")
    row = buscar_parametro_vigente_row(
        resolved_db,
        org_id=resolved_org_id,
        tipo=clean_tipo,
        vigencia_em=effective_date.isoformat(),
        funcao=funcao,
        categoria=categoria,
        unidade=unidade,
    )
    return serialize_finance_parameter(row) if row else None
