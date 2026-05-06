from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal

from flask import current_app, has_app_context

from ..audit import record_audit_event
from ..contracts.financeiro import (
    FINANCE_ORG_SCOPE_DEFAULT,
    serialize_finance_divergence,
    serialize_finance_mission,
    serialize_finance_parameter,
    serialize_finance_period,
    serialize_hourly_bonus_calculation,
    serialize_productivity_bonus_calculation,
)
from ..core.domain_errors import DomainConflictError, DomainNotFoundError, DomainValidationError
from ..db import get_db
from ..financeiro_audit_events import FINANCE_AUDIT_EVENTS_BY_NAME
from ..repositories.financeiro_parametros import (
    listar_parametros_financeiros as listar_parametros_financeiros_rows,
)
from ..repositories.financeiro_parametros import listar_parametros_financeiros_por_ids
from ..repositories.financeiro_calculos_horarios import listar_calculos_horarios
from ..repositories.financeiro_calculos_produtividade import listar_calculos_produtividade
from ..repositories.financeiro_competencias import (
    fechar_competencia_financeira as fechar_competencia_row,
)
from ..repositories.financeiro_competencias import (
    fetch_competencia_financeira,
    listar_divergencias_competencia,
    upsert_competencia_em_conferencia,
)
from ..repositories.financeiro_competencias import (
    reabrir_competencia_financeira as reabrir_competencia_row,
)
from ..repositories.financeiro_missoes import list_missoes_operacionais
from .financeiro_governanca_parametros import (
    classificacao_governanca_parametro,
    detectar_divergencias_ativas,
    detectar_sobreposicoes_ativas,
    parametro_elegivel_fechamento_real,
)
from .financeiro_bonificacoes import recalcular_produtividade_competencia

PERIOD_SNAPSHOT_VERSION = "finance-period-snapshot-v1"


class CompetenciaFinanceiraNaoEncontradaErro(DomainNotFoundError):
    def __init__(self, message: str = "Competencia financeira nao encontrada."):
        super().__init__(message, code="competencia_financeira_nao_encontrada", status=404)


class CompetenciaFinanceiraJaFechadaErro(DomainConflictError):
    def __init__(self, competencia: str):
        super().__init__(
            f"Competencia {competencia} ja esta fechada.",
            code="competencia_financeira_ja_fechada",
            status=409,
        )


class CompetenciaFinanceiraNaoFechadaErro(DomainConflictError):
    def __init__(self, competencia: str):
        super().__init__(
            f"Competencia {competencia} precisa estar fechada para reabertura.",
            code="competencia_financeira_nao_fechada",
            status=409,
        )


class MotivoReaberturaObrigatorioErro(DomainValidationError):
    def __init__(self):
        super().__init__(
            "Motivo de reabertura e obrigatorio.",
            code="competencia_financeira_reopen_reason_required",
            status=400,
        )


class ConfirmacaoFechamentoObrigatoriaErro(DomainValidationError):
    def __init__(self):
        super().__init__(
            "Confirmacao de fechamento e obrigatoria.",
            code="competencia_financeira_close_confirm_required",
            status=400,
        )


class ParametrosNaoElegiveisFechamentoRealErro(DomainConflictError):
    def __init__(
        self,
        *,
        competencia: str,
        environment: str,
        blocking_parameters: list[dict],
    ):
        super().__init__(
            (
                f"Fechamento real bloqueado para a competencia {competencia}: "
                f"{len(blocking_parameters)} parametro(s) nao elegivel(is) para release no ambiente {environment}."
            ),
            code="finance_parameters_not_release_eligible",
            status=409,
            details={
                "competencia": competencia,
                "environment": environment,
                "blocking_parameters": blocking_parameters,
                "next_action": (
                    "Promova somente parametros canonicos para release, remova elegibilidade de QA/BRL/legacy, "
                    "elimine overlap/divergencia e recalcule a competencia antes de fechar."
                ),
            },
        )


def _resolve_db(db=None):
    return db if db is not None else get_db()


def _resolve_org_id(org_id: str | None) -> str:
    return (org_id or "").strip() or FINANCE_ORG_SCOPE_DEFAULT


def _clean_text(value) -> str:
    return str(value or "").strip()


def _status(row: dict | None) -> str:
    return _clean_text((row or {}).get("status")) or "aberta"


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "on", "yes", "sim"}


def _money(value) -> Decimal:
    return Decimal(str(value or "0")).quantize(Decimal("0.01"))


def _sum_money(items: list[dict], key: str) -> str:
    total = sum((_money(item.get(key)) for item in items), Decimal("0.00"))
    return format(total.quantize(Decimal("0.01")), "f")


def _serialize_hourly(row: dict) -> dict:
    payload = dict(row)
    payload["mission_id"] = payload.get("mission_id") or payload.get("missao_operacional_id")
    payload["minutos_noturnos_reais"] = payload.get("minutos_noturnos_reais", payload.get("minutos_noturnos"))
    return serialize_hourly_bonus_calculation(payload)


def _serialize_productivity(row: dict) -> dict:
    return serialize_productivity_bonus_calculation(dict(row))


def _parameter_key(parameter: dict) -> tuple:
    return (
        parameter.get("parameter_id") or parameter.get("id"),
        parameter.get("tipo"),
        parameter.get("funcao"),
        parameter.get("categoria"),
        parameter.get("unidade"),
        parameter.get("valor"),
    )


def _collect_used_parameters(hourly: list[dict], productivity: list[dict]) -> list[dict]:
    collected: dict[tuple, dict] = {}
    for calculation in [*hourly, *productivity]:
        for parameter in calculation.get("parametros_usados", []) or []:
            collected[_parameter_key(parameter)] = parameter
    return list(collected.values())


def _resolve_finance_release_environment(environment: str | None = None) -> str:
    raw = _clean_text(environment).lower()
    if not raw and has_app_context():
        raw = _clean_text(current_app.config.get("APP_ENV")).lower()
    if not raw:
        raw = _clean_text(os.getenv("APP_ENV")).lower()
    if raw in {"prod", "production", "producao"}:
        return "production"
    return "hml"


def _parse_date_or_none(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _vigencia_valida(parameter: dict) -> bool:
    start = _parse_date_or_none(parameter.get("vigencia_inicio"))
    end = _parse_date_or_none(parameter.get("vigencia_fim"))
    if not start:
        return False
    if end and end < start:
        return False
    return True


def _resolve_parameter_id(parameter: dict) -> int | None:
    value = parameter.get("parameter_id") if "parameter_id" in parameter else parameter.get("id")
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _format_blocking_parameter(*, parameter: dict, persisted: dict | None, reasons: list[str]) -> dict:
    source = persisted or {}
    return {
        "parameter_id": _resolve_parameter_id(parameter),
        "tipo": parameter.get("tipo") or source.get("tipo"),
        "funcao": parameter.get("funcao") or source.get("funcao"),
        "categoria": parameter.get("categoria") or source.get("categoria"),
        "unidade": parameter.get("unidade") or source.get("unidade"),
        "valor": parameter.get("valor") if parameter.get("valor") is not None else source.get("valor"),
        "governance_class": classificacao_governanca_parametro(source) if source else None,
        "reasons": sorted(set(reasons)),
    }


def avaliar_elegibilidade_fechamento_real_snapshot(
    *,
    db,
    competencia: str,
    org_id: str,
    snapshot: dict,
    environment: str | None = None,
    strict: bool = True,
) -> dict:
    resolved_environment = _resolve_finance_release_environment(environment)
    used_parameters = snapshot.get("parametros_usados") or []
    used_ids = sorted({parameter_id for item in used_parameters if (parameter_id := _resolve_parameter_id(item)) is not None})
    active_parameters = snapshot.get("parametros_vigentes") or listar_parametros_financeiros_rows(
        db,
        org_id=org_id,
        status="ativo",
        vigencia_em=f"{competencia}-01",
        limit=10000,
        offset=0,
    )
    overlapping = detectar_sobreposicoes_ativas(active_parameters, include_unit=False)
    divergent = detectar_divergencias_ativas(active_parameters, include_unit=False)

    persisted_by_id: dict[int, dict] = {}
    if used_ids:
        persisted_by_id = {
            int(item["id"]): item
            for item in listar_parametros_financeiros_por_ids(
                db,
                org_id=org_id,
                parameter_ids=used_ids,
            )
        }

    blocking_parameters: list[dict] = []
    for parameter in used_parameters:
        parameter_id = _resolve_parameter_id(parameter)
        if parameter_id is None:
            blocking_parameters.append(
                _format_blocking_parameter(
                    parameter=parameter,
                    persisted=None,
                    reasons=["parameter_id_ausente_no_snapshot"],
                )
            )
            continue
        persisted = persisted_by_id.get(parameter_id)
        if persisted is None:
            blocking_parameters.append(
                _format_blocking_parameter(
                    parameter=parameter,
                    persisted=None,
                    reasons=["parameter_nao_encontrado"],
                )
            )
            continue

        reasons: list[str] = []
        governance_class = classificacao_governanca_parametro(persisted)
        if not governance_class:
            reasons.append("classificacao_ausente")
        if str(persisted.get("unidade") or "").strip().upper() == "BRL":
            reasons.append("unidade_brl_legacy")
        if str(persisted.get("status") or "").strip().lower() != "ativo":
            reasons.append("status_nao_ativo")
        if not _vigencia_valida(persisted):
            reasons.append("vigencia_invalida")
        if parameter_id in overlapping:
            reasons.append("sobreposicao_semantica_ativa")
        if parameter_id in divergent:
            reasons.append("divergencia_semantica_ativa")
        if governance_class in {"qa-smoke", "legacy", "deprecated"}:
            reasons.append(f"classificacao_nao_elegivel:{governance_class}")
        if not parametro_elegivel_fechamento_real(persisted, environment=resolved_environment):
            if not reasons:
                reasons.append("nao_elegivel_para_fechamento_real")

        if reasons:
            blocking_parameters.append(
                _format_blocking_parameter(
                    parameter=parameter,
                    persisted=persisted,
                    reasons=reasons,
                )
            )

    evaluation = {
        "environment": resolved_environment,
        "release_eligible": not blocking_parameters,
        "used_parameter_ids": used_ids,
        "blocking_parameters": blocking_parameters,
        "next_action": (
            "Promover parametros canonicos para classe elegivel no ambiente e eliminar QA/BRL/overlap/divergencia."
        ),
    }
    if strict and blocking_parameters:
        raise ParametrosNaoElegiveisFechamentoRealErro(
            competencia=competencia,
            environment=resolved_environment,
            blocking_parameters=blocking_parameters,
        )
    return evaluation


def _totals(
    *,
    missions: list[dict],
    hourly: list[dict],
    productivity: list[dict],
    divergences: list[dict],
) -> dict:
    total_horario = _sum_money(hourly, "total")
    total_produtividade = _sum_money(productivity, "total_devido")
    total_geral = _money(total_horario) + _money(total_produtividade)
    return {
        "mission_count": len(missions),
        "hourly_calculation_count": len(hourly),
        "productivity_calculation_count": len(productivity),
        "divergence_count": len(divergences),
        "total_horario": total_horario,
        "total_produtividade": total_produtividade,
        "total_geral": format(total_geral.quantize(Decimal("0.01")), "f"),
    }


def _build_period_snapshot(
    db,
    *,
    competencia: str,
    org_id: str,
    actor_user_id: int | None = None,
    status_before: str = "aberta",
) -> dict:
    missions = [
        serialize_finance_mission(row)
        for row in list_missoes_operacionais(
            db,
            competencia=competencia,
            org_id=org_id,
            limit=10000,
            offset=0,
        )
    ]
    hourly = [
        _serialize_hourly(row)
        for row in listar_calculos_horarios(
            db,
            competencia=competencia,
            org_id=org_id,
            status="calculado",
            limit=10000,
            offset=0,
        )
    ]
    productivity = [
        _serialize_productivity(row)
        for row in listar_calculos_produtividade(
            db,
            competencia=competencia,
            org_id=org_id,
            status="calculado",
            limit=10000,
            offset=0,
        )
    ]
    divergences = [
        serialize_finance_divergence(
            {
                **row,
                "severity": row.get("severidade"),
                "code": row.get("codigo"),
                "message": row.get("mensagem"),
                "entity_type": row.get("entidade_tipo"),
                "entity_id": row.get("entidade_id"),
                "metadata": row.get("detalhes"),
                "detected_at": row.get("created_at"),
            }
        )
        for row in listar_divergencias_competencia(db, competencia=competencia, org_id=org_id)
    ]
    parameters_used = _collect_used_parameters(hourly, productivity)
    active_parameters = [
        serialize_finance_parameter(row)
        for row in listar_parametros_financeiros_rows(
            db,
            org_id=org_id,
            status="ativo",
            vigencia_em=f"{competencia}-01",
            limit=10000,
            offset=0,
        )
    ]
    totals = _totals(missions=missions, hourly=hourly, productivity=productivity, divergences=divergences)
    return {
        "snapshot_version": PERIOD_SNAPSHOT_VERSION,
        "org_id": org_id,
        "competencia": competencia,
        "status_before": status_before,
        "generated_at": datetime.utcnow().replace(microsecond=0).isoformat(),
        "generated_by": actor_user_id,
        "missoes_operacionais": missions,
        "calculos_horarios": hourly,
        "calculos_produtividade": productivity,
        "parametros_usados": parameters_used,
        "parametros_vigentes": active_parameters,
        "divergencias": divergences,
        "totals": totals,
    }


def _period_payload(row: dict | None, *, competencia: str, org_id: str, snapshot: dict | None = None) -> dict:
    source = dict(row or {})
    source.setdefault("org_id", org_id)
    source.setdefault("competencia", competencia)
    source.setdefault("status", "aberta")
    if snapshot is not None:
        source["totals"] = snapshot.get("totals") or source.get("totals_snapshot") or {}
        source["snapshot"] = source.get("fechamento_snapshot") or snapshot
    else:
        source["totals"] = source.get("totals_snapshot") or {}
        source["snapshot"] = source.get("fechamento_snapshot")
    return serialize_finance_period(source)


def _audit_payload(period: dict, *, event_name: str, actor_user_id: int, reason: str | None = None) -> dict:
    event = FINANCE_AUDIT_EVENTS_BY_NAME[event_name]
    snapshot = period.get("snapshot") or {}
    totals = period.get("totals") or snapshot.get("totals") or {}
    return {
        "period": period,
        "audit_metadata": {
            "event_name": event_name,
            "org_id": period.get("org_id"),
            "actor_user_id": actor_user_id,
            "entity_type": event["entity_type"],
            "entity_id": period.get("id") or 0,
            "permission": event["permission"],
            "competencia": period.get("competencia"),
            "snapshot_id": period.get("id") or period.get("competencia"),
            "previous_snapshot_id": period.get("id") or period.get("competencia"),
            "closed_at": period.get("closed_at"),
            "total_geral": totals.get("total_geral"),
            "reason": reason,
        },
    }


def _record_period_audit(
    db,
    *,
    event_name: str,
    actor_user_id: int,
    before: dict | None,
    after: dict | None,
    reason: str | None = None,
) -> None:
    event = FINANCE_AUDIT_EVENTS_BY_NAME[event_name]
    period = after or before or {}
    record_audit_event(
        db,
        entidade=event["entity_type"],
        entidade_id=int(period.get("id") or 0),
        acao=event_name,
        realizado_por=actor_user_id,
        payload_anterior=_audit_payload(before, event_name=event_name, actor_user_id=actor_user_id, reason=reason)
        if before
        else None,
        payload_novo=_audit_payload(after, event_name=event_name, actor_user_id=actor_user_id, reason=reason)
        if after
        else None,
        observacao=f"org_id={period.get('org_id')}; competencia={period.get('competencia')}",
    )


def detalhar_competencia_financeira(competencia: str, *, org_id: str | None = None, db=None) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id)
    resolved_competencia = _clean_text(competencia)
    row = fetch_competencia_financeira(resolved_db, competencia=resolved_competencia, org_id=resolved_org_id)
    snapshot = row.get("fechamento_snapshot") if row and row.get("fechamento_snapshot") else None
    if snapshot is None:
        snapshot = _build_period_snapshot(
            resolved_db,
            competencia=resolved_competencia,
            org_id=resolved_org_id,
            status_before=_status(row),
        )
    snapshot["release_gate"] = avaliar_elegibilidade_fechamento_real_snapshot(
        db=resolved_db,
        competencia=resolved_competencia,
        org_id=resolved_org_id,
        snapshot=snapshot,
        strict=False,
    )
    period = _period_payload(row, competencia=resolved_competencia, org_id=resolved_org_id, snapshot=snapshot)
    return {
        "period": period,
        "snapshot": period.get("snapshot"),
        "totals": period.get("totals") or snapshot.get("totals") or {},
        "divergences": snapshot.get("divergencias", []),
    }


def recalcular_competencia_financeira(
    competencia: str,
    *,
    actor_user_id: int,
    org_id: str | None = None,
    db=None,
) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id)
    resolved_competencia = _clean_text(competencia)
    result = recalcular_produtividade_competencia(
        resolved_competencia,
        actor_user_id=actor_user_id,
        org_id=resolved_org_id,
        db=resolved_db,
    )
    snapshot = _build_period_snapshot(
        resolved_db,
        competencia=resolved_competencia,
        org_id=resolved_org_id,
        actor_user_id=actor_user_id,
        status_before="em_conferencia",
    )
    snapshot["release_gate"] = avaliar_elegibilidade_fechamento_real_snapshot(
        db=resolved_db,
        competencia=resolved_competencia,
        org_id=resolved_org_id,
        snapshot=snapshot,
        strict=False,
    )
    row = upsert_competencia_em_conferencia(
        resolved_db,
        competencia=resolved_competencia,
        org_id=resolved_org_id,
        totals=snapshot["totals"],
    )
    resolved_db.commit()
    period = _period_payload(row, competencia=resolved_competencia, org_id=resolved_org_id, snapshot=snapshot)
    return {
        "period": period,
        "items": result["items"],
        "totals": snapshot["totals"],
        "divergences": snapshot["divergencias"],
        "calculation_memory": {
            "snapshot_version": PERIOD_SNAPSHOT_VERSION,
            "competencia": resolved_competencia,
            "productivity_calculations": len(result["items"]),
        },
    }


def fechar_competencia_financeira(
    competencia: str,
    payload: dict,
    *,
    actor_user_id: int,
    org_id: str | None = None,
    db=None,
) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id)
    resolved_competencia = _clean_text(competencia)
    if not _as_bool(payload.get("confirm")):
        raise ConfirmacaoFechamentoObrigatoriaErro()

    before_row = fetch_competencia_financeira(resolved_db, competencia=resolved_competencia, org_id=resolved_org_id)
    if _status(before_row) == "fechada":
        raise CompetenciaFinanceiraJaFechadaErro(resolved_competencia)

    try:
        snapshot = _build_period_snapshot(
            resolved_db,
            competencia=resolved_competencia,
            org_id=resolved_org_id,
            actor_user_id=actor_user_id,
            status_before=_status(before_row),
        )
        release_gate = avaliar_elegibilidade_fechamento_real_snapshot(
            db=resolved_db,
            competencia=resolved_competencia,
            org_id=resolved_org_id,
            snapshot=snapshot,
            strict=True,
        )
        snapshot["release_gate"] = {
            **release_gate,
            "validated_at": datetime.utcnow().replace(microsecond=0).isoformat(),
            "mode": "fechamento",
        }
        closed_row = fechar_competencia_row(
            resolved_db,
            competencia=resolved_competencia,
            org_id=resolved_org_id,
            totals=snapshot["totals"],
            snapshot=snapshot,
            closed_by=actor_user_id,
        )
        before = _period_payload(
            before_row,
            competencia=resolved_competencia,
            org_id=resolved_org_id,
            snapshot=snapshot if before_row else None,
        )
        after = _period_payload(closed_row, competencia=resolved_competencia, org_id=resolved_org_id, snapshot=snapshot)
        _record_period_audit(
            resolved_db,
            event_name="finance.period.closed",
            actor_user_id=actor_user_id,
            before=before,
            after=after,
            reason=payload.get("motivo") or payload.get("reason"),
        )
        resolved_db.commit()
        return {
            "period": after,
            "snapshot": snapshot,
            "totals": snapshot["totals"],
        }
    except Exception:
        resolved_db.conn.rollback()
        raise


def reabrir_competencia_financeira(
    competencia: str,
    payload: dict,
    *,
    actor_user_id: int,
    org_id: str | None = None,
    db=None,
) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id)
    resolved_competencia = _clean_text(competencia)
    reason = _clean_text(payload.get("motivo") or payload.get("reason"))
    if not reason:
        raise MotivoReaberturaObrigatorioErro()

    before_row = fetch_competencia_financeira(resolved_db, competencia=resolved_competencia, org_id=resolved_org_id)
    if not before_row:
        raise CompetenciaFinanceiraNaoEncontradaErro()
    if _status(before_row) != "fechada":
        raise CompetenciaFinanceiraNaoFechadaErro(resolved_competencia)

    try:
        reopened_row = reabrir_competencia_row(
            resolved_db,
            competencia=resolved_competencia,
            org_id=resolved_org_id,
            motivo=reason,
            reopened_by=actor_user_id,
        )
        before = _period_payload(before_row, competencia=resolved_competencia, org_id=resolved_org_id)
        after = _period_payload(reopened_row, competencia=resolved_competencia, org_id=resolved_org_id)
        _record_period_audit(
            resolved_db,
            event_name="finance.period.reopened",
            actor_user_id=actor_user_id,
            before=before,
            after=after,
            reason=reason,
        )
        resolved_db.commit()
        return {"period": after}
    except Exception:
        resolved_db.conn.rollback()
        raise
