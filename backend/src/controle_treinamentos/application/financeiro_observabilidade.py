from __future__ import annotations

import re

from ..contracts.financeiro import (
    FINANCE_ORG_SCOPE_DEFAULT,
    serialize_finance_audit_event,
    serialize_finance_divergence,
)
from ..core.domain_errors import DomainValidationError
from ..db import get_db
from ..repositories.financeiro_observabilidade import (
    listar_divergencias_financeiras as listar_divergencias_financeiras_rows,
)
from ..repositories.financeiro_observabilidade import (
    listar_eventos_auditoria_financeira as listar_eventos_auditoria_financeira_rows,
)

_COMPETENCIA_RE = re.compile(r"^[0-9]{4}-(0[1-9]|1[0-2])$")
_DIVERGENCE_STATUSES = {"aberta", "resolvida", "ignorada"}
_DIVERGENCE_SEVERITIES = {"bloqueante", "alta", "media", "informativa"}
_MAX_LIMIT = 100
_DEFAULT_LIMIT = 50


class ObservabilidadeFinanceiraInvalidaErro(DomainValidationError):
    def __init__(self, message: str, *, code: str = "finance_observability_invalid_filter"):
        super().__init__(message, code=code, status=400)


def _resolve_db(db=None):
    return db if db is not None else get_db()


def _resolve_org_id(org_id: str | None) -> str:
    return (org_id or "").strip() or FINANCE_ORG_SCOPE_DEFAULT


def _clean_text(value) -> str:
    return str(value or "").strip()


def _optional_text(value) -> str | None:
    text = _clean_text(value)
    return text or None


def _parse_limit(value) -> int:
    if value in (None, ""):
        return _DEFAULT_LIMIT
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ObservabilidadeFinanceiraInvalidaErro(
            "Filtro limit invalido.",
            code="finance_observability_limit_invalid",
        ) from exc
    if parsed < 1:
        raise ObservabilidadeFinanceiraInvalidaErro(
            "Filtro limit deve ser maior que zero.",
            code="finance_observability_limit_invalid",
        )
    return min(parsed, _MAX_LIMIT)


def _parse_offset(value) -> int:
    if value in (None, ""):
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ObservabilidadeFinanceiraInvalidaErro(
            "Filtro offset invalido.",
            code="finance_observability_offset_invalid",
        ) from exc
    if parsed < 0:
        raise ObservabilidadeFinanceiraInvalidaErro(
            "Filtro offset nao pode ser negativo.",
            code="finance_observability_offset_invalid",
        )
    return parsed


def _parse_entity_id(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ObservabilidadeFinanceiraInvalidaErro(
            "Filtro entity_id invalido.",
            code="finance_observability_entity_id_invalid",
        ) from exc
    if parsed < 0:
        raise ObservabilidadeFinanceiraInvalidaErro(
            "Filtro entity_id nao pode ser negativo.",
            code="finance_observability_entity_id_invalid",
        )
    return parsed


def _parse_competencia(value) -> str | None:
    text = _optional_text(value)
    if not text:
        return None
    if not _COMPETENCIA_RE.match(text):
        raise ObservabilidadeFinanceiraInvalidaErro(
            "Filtro competencia deve estar no formato YYYY-MM.",
            code="finance_observability_competencia_invalid",
        )
    return text


def _parse_event_name(value) -> str | None:
    text = _optional_text(value)
    if not text:
        return None
    if not text.startswith("finance."):
        raise ObservabilidadeFinanceiraInvalidaErro(
            "Filtro event_name deve iniciar com finance.",
            code="finance_observability_event_name_invalid",
        )
    return text


def _parse_divergence_status(value) -> str | None:
    text = _optional_text(value)
    if not text:
        return None
    normalized = text.lower()
    if normalized not in _DIVERGENCE_STATUSES:
        raise ObservabilidadeFinanceiraInvalidaErro(
            "Filtro status de divergencia invalido.",
            code="finance_divergence_status_invalid",
        )
    return normalized


def _parse_divergence_severity(value) -> str | None:
    text = _optional_text(value)
    if not text:
        return None
    normalized = text.lower()
    if normalized not in _DIVERGENCE_SEVERITIES:
        raise ObservabilidadeFinanceiraInvalidaErro(
            "Filtro severidade de divergencia invalido.",
            code="finance_divergence_severity_invalid",
        )
    return normalized


def _page_from_offset(*, offset: int, limit: int) -> int:
    return (offset // max(1, limit)) + 1


def listar_eventos_auditoria_financeira(
    *,
    org_id: str | None = None,
    competencia: str | None = None,
    entity_type: str | None = None,
    entity_id: int | str | None = None,
    event_name: str | None = None,
    limit: int | str | None = None,
    offset: int | str | None = None,
    db=None,
) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id)
    resolved_limit = _parse_limit(limit)
    resolved_offset = _parse_offset(offset)
    rows = listar_eventos_auditoria_financeira_rows(
        resolved_db,
        org_id=resolved_org_id,
        competencia=_parse_competencia(competencia),
        entity_type=_optional_text(entity_type),
        entity_id=_parse_entity_id(entity_id),
        event_name=_parse_event_name(event_name),
        limit=resolved_limit,
        offset=resolved_offset,
    )
    return {
        "items": [serialize_finance_audit_event(row) for row in rows],
        "pagination": {
            "page": _page_from_offset(offset=resolved_offset, limit=resolved_limit),
            "offset": resolved_offset,
            "limit": resolved_limit,
            "total": len(rows),
        },
    }


def listar_divergencias_financeiras(
    *,
    org_id: str | None = None,
    competencia: str | None = None,
    status: str | None = None,
    severidade: str | None = None,
    codigo: str | None = None,
    limit: int | str | None = None,
    offset: int | str | None = None,
    db=None,
) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id)
    resolved_limit = _parse_limit(limit)
    resolved_offset = _parse_offset(offset)
    rows = listar_divergencias_financeiras_rows(
        resolved_db,
        org_id=resolved_org_id,
        competencia=_parse_competencia(competencia),
        status=_parse_divergence_status(status),
        severidade=_parse_divergence_severity(severidade),
        codigo=_optional_text(codigo),
        limit=resolved_limit,
        offset=resolved_offset,
    )
    return {
        "items": [serialize_finance_divergence(row) for row in rows],
        "pagination": {
            "page": _page_from_offset(offset=resolved_offset, limit=resolved_limit),
            "offset": resolved_offset,
            "limit": resolved_limit,
            "total": len(rows),
        },
    }
