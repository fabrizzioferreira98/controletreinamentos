from __future__ import annotations

from decimal import Decimal

from ..audit import record_audit_event
from ..contracts.financeiro import (
    FINANCE_ORG_SCOPE_DEFAULT,
    serialize_hourly_bonus_calculation,
    serialize_productivity_bonus_calculation,
)
from ..core.domain_errors import DomainNotFoundError
from ..db import get_db
from ..financeiro_audit_events import FINANCE_AUDIT_EVENTS_BY_NAME
from ..repositories.financeiro_calculos_horarios import (
    detalhar_calculo_horario,
    listar_calculos_horarios,
)
from ..repositories.financeiro_calculos_produtividade import (
    detalhar_calculo_produtividade_por_tripulante,
    listar_calculos_produtividade,
    listar_participacoes_produtividade_por_competencia,
    listar_tripulantes_elegiveis_produtividade,
    salvar_calculo_produtividade,
)
from ..repositories.financeiro_parametros import listar_parametros_financeiros as listar_parametros_financeiros_rows
from .financeiro_bonificacao_produtividade import MONETARY_PARAMETER_UNIT, calcular_bonificacao_produtividade
from .financeiro_missoes import validar_competencia_aberta_para_mutacao


class BonificacaoHorariaNaoEncontradaErro(DomainNotFoundError):
    def __init__(self, message: str = "Bonificacao horaria nao encontrada."):
        super().__init__(message, code="bonificacao_horaria_nao_encontrada", status=404)


class BonificacaoProdutividadeNaoEncontradaErro(DomainNotFoundError):
    def __init__(self, message: str = "Bonificacao por funcao/produtividade nao encontrada."):
        super().__init__(message, code="bonificacao_produtividade_nao_encontrada", status=404)


def _resolve_db(db=None):
    return db if db is not None else get_db()


def _resolve_org_id(org_id: str | None) -> str:
    return (org_id or "").strip() or FINANCE_ORG_SCOPE_DEFAULT


def _clean_text(value) -> str:
    return str(value or "").strip()


def _serialize(row: dict) -> dict:
    payload = dict(row)
    payload["mission_id"] = payload.get("mission_id") or payload.get("missao_operacional_id")
    payload["minutos_noturnos_reais"] = payload.get("minutos_noturnos_reais", payload.get("minutos_noturnos"))
    return serialize_hourly_bonus_calculation(payload)


def _serialize_productivity(row: dict) -> dict:
    return serialize_productivity_bonus_calculation(dict(row))


def _competencia_vigencia_date(competencia: str) -> str:
    return f"{_clean_text(competencia)}-01"


def _tripulante_from_participation(row: dict, *, org_id: str) -> dict:
    return {
        "id": row.get("tripulante_id"),
        "tripulante_id": row.get("tripulante_id"),
        "org_id": org_id,
        "nome": row.get("tripulante_nome"),
        "categoria_operacional": row.get("tripulante_categoria_operacional"),
        "sdea_ativo": row.get("tripulante_sdea_ativo"),
        "sdea_icao_validade": row.get("tripulante_sdea_icao_validade"),
        "instrutor_ativo": row.get("tripulante_instrutor_ativo"),
        "instrutor_inicio": row.get("tripulante_instrutor_inicio"),
        "instrutor_fim": row.get("tripulante_instrutor_fim"),
        "checador_ativo": row.get("tripulante_checador_ativo"),
        "checador_inicio": row.get("tripulante_checador_inicio"),
        "checador_fim": row.get("tripulante_checador_fim"),
        "checador_carta_designacao": row.get("tripulante_checador_carta_designacao"),
    }


def _mission_from_participation(row: dict) -> dict:
    return {
        "id": row.get("missao_operacional_id"),
        "missao_operacional_id": row.get("missao_operacional_id"),
        "data_missao": row.get("data_missao"),
        "data_final": row.get("data_final"),
        "cavok_numero_voo": row.get("cavok_numero_voo"),
        "contratante": row.get("contratante"),
        "chamado": row.get("chamado"),
        "aeronave_id": row.get("aeronave_id"),
        "categoria_financeira_aeronave": row.get("categoria_financeira_aeronave"),
        "trecho": row.get("trecho"),
        "houve_pernoite": row.get("houve_pernoite"),
        "quantidade_pernoites": row.get("quantidade_pernoites"),
        "cobertura_base": row.get("cobertura_base"),
        "operacao_especial": row.get("operacao_especial"),
        "justificativa": row.get("justificativa"),
    }


def _group_participations(rows: list[dict], *, org_id: str) -> list[dict]:
    grouped: dict[tuple[int, str], dict] = {}
    for row in rows:
        key = (int(row["tripulante_id"]), _clean_text(row["funcao"]))
        if key not in grouped:
            grouped[key] = {
                "tripulante": _tripulante_from_participation(row, org_id=org_id),
                "funcao": _clean_text(row["funcao"]),
                "missoes": [],
            }
        grouped[key]["missoes"].append(_mission_from_participation(row))
    return list(grouped.values())


def _seed_floor_groups_without_missions(groups: list[dict], tripulantes: list[dict], *, org_id: str) -> list[dict]:
    grouped = {(int(group["tripulante"]["tripulante_id"]), _clean_text(group["funcao"])): group for group in groups}
    for row in tripulantes:
        tripulante_id = int(row["tripulante_id"])
        funcao = _clean_text(row.get("funcao"))
        if not funcao:
            continue
        key = (tripulante_id, funcao)
        if key in grouped:
            continue
        grouped[key] = {
            "tripulante": {
                "id": tripulante_id,
                "tripulante_id": tripulante_id,
                "org_id": org_id,
                "nome": row.get("tripulante_nome"),
                "categoria_operacional": row.get("tripulante_categoria_operacional"),
                "sdea_ativo": row.get("tripulante_sdea_ativo"),
                "sdea_icao_validade": row.get("tripulante_sdea_icao_validade"),
                "instrutor_ativo": row.get("tripulante_instrutor_ativo"),
                "instrutor_inicio": row.get("tripulante_instrutor_inicio"),
                "instrutor_fim": row.get("tripulante_instrutor_fim"),
                "checador_ativo": row.get("tripulante_checador_ativo"),
                "checador_inicio": row.get("tripulante_checador_inicio"),
                "checador_fim": row.get("tripulante_checador_fim"),
                "checador_carta_designacao": row.get("tripulante_checador_carta_designacao"),
            },
            "funcao": funcao,
            "missoes": [],
        }
    return list(grouped.values())


def _fetch_productivity_parameters(db, *, competencia: str, org_id: str) -> list[dict]:
    return listar_parametros_financeiros_rows(
        db,
        org_id=org_id,
        status="ativo",
        unidade=MONETARY_PARAMETER_UNIT,
        vigencia_em=_competencia_vigencia_date(competencia),
        limit=1000,
        offset=0,
    )


def _sum_money_text(items: list[dict], key: str) -> str:
    total = sum((Decimal(str(item.get(key) or "0")) for item in items), Decimal("0.00"))
    return format(total.quantize(Decimal("0.01")), "f")


def _productivity_audit_payload(
    calculation: dict,
    *,
    event_name: str,
    actor_user_id: int,
    competencia: str,
    org_id: str,
    totals: dict | None = None,
) -> dict:
    event = FINANCE_AUDIT_EVENTS_BY_NAME[event_name]
    metadata = {
        "event_name": event_name,
        "org_id": org_id,
        "actor_user_id": actor_user_id,
        "entity_type": event["entity_type"],
        "entity_id": calculation.get("id") or calculation.get("tripulante_id") or 0,
        "permission": event["permission"],
        "competencia": competencia,
        "tripulante_id": calculation.get("tripulante_id"),
        "calculation_version": calculation.get("calculation_version"),
    }
    if totals:
        metadata.update(totals)
    return {
        "calculation": calculation,
        "audit_metadata": metadata,
    }


def _record_productivity_calculated_audit(db, *, calculation: dict, actor_user_id: int, org_id: str) -> None:
    event_name = "finance.productivity.calculated"
    event = FINANCE_AUDIT_EVENTS_BY_NAME[event_name]
    record_audit_event(
        db,
        entidade=event["entity_type"],
        entidade_id=int(calculation.get("id") or calculation.get("tripulante_id") or 0),
        acao=event_name,
        realizado_por=actor_user_id,
        payload_anterior=None,
        payload_novo=_productivity_audit_payload(
            calculation,
            event_name=event_name,
            actor_user_id=actor_user_id,
            competencia=calculation.get("competencia"),
            org_id=org_id,
        ),
        observacao=f"org_id={org_id}; competencia={calculation.get('competencia')}; tripulante_id={calculation.get('tripulante_id')}",
    )


def _has_common_overnight_missing_parameter(calculation: dict) -> bool:
    memory = calculation.get("memoria_calculo") or {}
    warnings = memory.get("warnings") if isinstance(memory, dict) else []
    if isinstance(warnings, dict):
        warnings = [warnings]
    if not isinstance(warnings, list):
        return False
    return any(
        isinstance(item, dict) and item.get("code") == "pernoite_comum_parametro_ausente"
        for item in warnings
    )


def _record_period_recalculated_audit(
    db,
    *,
    competencia: str,
    actor_user_id: int,
    org_id: str,
    calculations: list[dict],
    mission_count: int,
) -> None:
    event_name = "finance.period.recalculated"
    event = FINANCE_AUDIT_EVENTS_BY_NAME[event_name]
    calculation_version = calculations[0].get("calculation_version") if calculations else "finance-productivity-v1"
    totals = {
        "calculation_version": calculation_version,
        "participant_count": len(calculations),
        "mission_count": mission_count,
        "total_devido": _sum_money_text(calculations, "total_devido"),
    }
    payload = {
        "competencia": competencia,
        "calculations": calculations,
        "audit_metadata": {
            "event_name": event_name,
            "org_id": org_id,
            "actor_user_id": actor_user_id,
            "entity_type": event["entity_type"],
            "entity_id": 0,
            "permission": event["permission"],
            "competencia": competencia,
            **totals,
        },
    }
    record_audit_event(
        db,
        entidade=event["entity_type"],
        entidade_id=0,
        acao=event_name,
        realizado_por=actor_user_id,
        payload_anterior={"competencia": competencia, "org_id": org_id},
        payload_novo=payload,
        observacao=f"org_id={org_id}; competencia={competencia}; participant_count={len(calculations)}",
    )


def listar_bonificacoes_horarias(
    *,
    org_id: str | None = None,
    competencia: str | None = None,
    missao_operacional_id: int | None = None,
    tripulante_id: int | None = None,
    funcao: str | None = None,
    status: str | None = None,
    page: int = 1,
    offset: int = 0,
    limit: int = 100,
    db=None,
) -> dict:
    resolved_db = _resolve_db(db)
    rows = listar_calculos_horarios(
        resolved_db,
        org_id=_resolve_org_id(org_id),
        competencia=_clean_text(competencia) or None,
        missao_operacional_id=missao_operacional_id,
        tripulante_id=tripulante_id,
        funcao=_clean_text(funcao) or None,
        status=_clean_text(status) or None,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [_serialize(row) for row in rows],
        "pagination": {
            "page": int(page),
            "offset": int(offset),
            "total": len(rows),
        },
    }


def detalhar_bonificacao_horaria(calculo_horario_id: int, *, org_id: str | None = None, db=None) -> dict:
    resolved_db = _resolve_db(db)
    row = detalhar_calculo_horario(
        resolved_db,
        calculo_horario_id=calculo_horario_id,
        org_id=_resolve_org_id(org_id),
    )
    if not row:
        raise BonificacaoHorariaNaoEncontradaErro()
    return _serialize(row)


def listar_bonificacoes_produtividade(
    *,
    org_id: str | None = None,
    competencia: str | None = None,
    tripulante_id: int | None = None,
    funcao: str | None = None,
    status: str | None = None,
    page: int = 1,
    offset: int = 0,
    limit: int = 100,
    db=None,
) -> dict:
    resolved_db = _resolve_db(db)
    rows = listar_calculos_produtividade(
        resolved_db,
        org_id=_resolve_org_id(org_id),
        competencia=_clean_text(competencia) or None,
        tripulante_id=tripulante_id,
        funcao=_clean_text(funcao) or None,
        status=_clean_text(status) or None,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [_serialize_productivity(row) for row in rows],
        "pagination": {
            "page": int(page),
            "offset": int(offset),
            "total": len(rows),
        },
    }


def detalhar_bonificacao_produtividade_por_tripulante(
    tripulante_id: int,
    *,
    org_id: str | None = None,
    competencia: str | None = None,
    funcao: str | None = None,
    db=None,
) -> dict:
    resolved_db = _resolve_db(db)
    row = detalhar_calculo_produtividade_por_tripulante(
        resolved_db,
        tripulante_id=tripulante_id,
        org_id=_resolve_org_id(org_id),
        competencia=_clean_text(competencia) or None,
        funcao=_clean_text(funcao) or None,
    )
    if not row:
        raise BonificacaoProdutividadeNaoEncontradaErro()
    return _serialize_productivity(row)


def recalcular_produtividade_competencia(
    competencia: str,
    *,
    actor_user_id: int,
    org_id: str | None = None,
    db=None,
) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id)
    resolved_competencia = _clean_text(competencia)

    try:
        validar_competencia_aberta_para_mutacao(
            resolved_db,
            competencia=resolved_competencia,
            org_id=resolved_org_id,
        )
        participations = listar_participacoes_produtividade_por_competencia(
            resolved_db,
            competencia=resolved_competencia,
            org_id=resolved_org_id,
        )
        floor_tripulantes = listar_tripulantes_elegiveis_produtividade(
            resolved_db,
            org_id=resolved_org_id,
        )
        parametros = _fetch_productivity_parameters(
            resolved_db,
            competencia=resolved_competencia,
            org_id=resolved_org_id,
        )
        saved_calculations = []
        groups = _seed_floor_groups_without_missions(
            _group_participations(participations, org_id=resolved_org_id),
            floor_tripulantes,
            org_id=resolved_org_id,
        )
        for group in groups:
            calculation = calcular_bonificacao_produtividade(
                competencia=resolved_competencia,
                tripulante=group["tripulante"],
                funcao=group["funcao"],
                missoes_operacionais=group["missoes"],
                parametros_vigentes=parametros,
            )
            calculation["org_id"] = resolved_org_id
            calculation["status"] = (
                "recalculo_pendente"
                if _has_common_overnight_missing_parameter(calculation)
                else "calculado"
            )
            saved = salvar_calculo_produtividade(
                resolved_db,
                data=calculation,
                org_id=resolved_org_id,
            )
            serialized = _serialize_productivity(saved)
            saved_calculations.append(serialized)
            _record_productivity_calculated_audit(
                resolved_db,
                calculation=serialized,
                actor_user_id=actor_user_id,
                org_id=resolved_org_id,
            )

        _record_period_recalculated_audit(
            resolved_db,
            competencia=resolved_competencia,
            actor_user_id=actor_user_id,
            org_id=resolved_org_id,
            calculations=saved_calculations,
            mission_count=len({row["missao_operacional_id"] for row in participations}),
        )
        resolved_db.commit()
        return {
            "competencia": resolved_competencia,
            "items": saved_calculations,
            "totals": {
                "participant_count": len(saved_calculations),
                "total_devido": _sum_money_text(saved_calculations, "total_devido"),
            },
        }
    except Exception:
        resolved_db.conn.rollback()
        raise
