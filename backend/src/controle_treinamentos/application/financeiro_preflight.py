from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from ..contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT, serialize_finance_divergence
from ..db import get_db
from ..repositories.financeiro_feriados import verificar_feriado_nacional_por_data
from ..repositories.financeiro_missoes import (
    fetch_competencia_financeira,
    fetch_missao_operacional_detail,
    list_missoes_operacionais,
)
from ..repositories.financeiro_observabilidade import (
    listar_divergencias_financeiras as listar_divergencias_financeiras_rows,
)
from ..repositories.financeiro_observabilidade import (
    listar_eventos_auditoria_financeira as listar_eventos_auditoria_financeira_rows,
)
from ..repositories.financeiro_parametros import (
    listar_parametros_financeiros as listar_parametros_financeiros_rows,
)
from .financeiro_competencias import (
    avaliar_elegibilidade_fechamento_real_snapshot,
    detalhar_competencia_financeira,
)
from .financeiro_categorias import (
    CANONICAL_CATEGORY_A,
    CANONICAL_CATEGORY_B,
    CANONICAL_CATEGORY_TURBOHELICE_PALMAS,
    normalizar_categoria_operacional,
)
from .financeiro_governanca_parametros import (
    GOV_CLASS_DEPRECATED,
    GOV_CLASS_LEGACY,
    GOV_CLASS_QA_SMOKE,
    classificacao_governanca_parametro,
    detectar_divergencias_ativas,
    detectar_sobreposicoes_ativas,
    parametro_elegivel_fechamento_real,
)

_COMPETENCIA_RE = re.compile(r"^[0-9]{4}-(0[1-9]|1[0-2])$")
_RELEASE_ENVIRONMENT = "hml"
_PARAMETER_TYPES_HOURLY = (
    "duracao_hora_noturna_minutos",
    "periodo_diurno_inicio",
    "periodo_diurno_fim",
    "adicional_noturno",
    "domingo_feriado_diurno",
    "domingo_feriado_noturno",
)
_PARAMETER_TYPES_PRODUCTIVITY = (
    "icao_sdea",
    "instrutor",
    "checador",
    "missao_categoria_a",
    "missao_categoria_b",
    "cobertura_base",
    "pernoite_comum_sem_cobertura",
    "garantia_minima",
    "excecao_palmas_turbohelice",
)
_MISSION_REQUIRED_SPECS = (
    {"tipo": "duracao_hora_noturna_minutos", "funcao": None, "categoria": None, "unidade": "minutos"},
    {"tipo": "periodo_diurno_inicio", "funcao": None, "categoria": None, "unidade": "minutos_do_dia"},
    {"tipo": "periodo_diurno_fim", "funcao": None, "categoria": None, "unidade": "minutos_do_dia"},
    {"tipo": "adicional_noturno", "funcao": "comandante", "categoria": None, "unidade": "valor"},
    {"tipo": "domingo_feriado_diurno", "funcao": "comandante", "categoria": None, "unidade": "valor"},
    {"tipo": "domingo_feriado_noturno", "funcao": "comandante", "categoria": None, "unidade": "valor"},
    {"tipo": "adicional_noturno", "funcao": "copiloto", "categoria": None, "unidade": "valor"},
    {"tipo": "domingo_feriado_diurno", "funcao": "copiloto", "categoria": None, "unidade": "valor"},
    {"tipo": "domingo_feriado_noturno", "funcao": "copiloto", "categoria": None, "unidade": "valor"},
)
_ACTIVE_STATUSES = {"ativa", "recalculo_pendente"}
_BLOCKING_DIVERGENCE_SEVERITIES = {"bloqueante", "alta"}


def _resolve_db(db=None):
    return db if db is not None else get_db()


def _resolve_org_id(org_id: str | None) -> str:
    return (org_id or "").strip() or FINANCE_ORG_SCOPE_DEFAULT


def _clean_text(value) -> str:
    return str(value or "").strip()


def _optional_text(value) -> str | None:
    text = _clean_text(value)
    return text or None


def _to_int(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _is_semantically_none(value) -> bool:
    return _optional_text(value) is None


def _vigencia_cobre_data(parameter: dict, *, reference_date: date | None) -> bool:
    if reference_date is None:
        return False
    start = _parse_date(parameter.get("vigencia_inicio"))
    end = _parse_date(parameter.get("vigencia_fim"))
    if start is None:
        return False
    if end is not None and end < start:
        return False
    if start > reference_date:
        return False
    if end is not None and end < reference_date:
        return False
    return True


def _spec_key(spec: dict) -> tuple[str | None, ...]:
    return (
        _optional_text(spec.get("tipo")),
        _optional_text(spec.get("funcao")),
        _optional_text(spec.get("categoria")),
        _optional_text(spec.get("unidade")),
    )


def _block(
    *,
    code: str,
    message: str,
    entity_type: str,
    entity_id: str | int | None,
    field: str,
    next_action: str,
    severity: str = "bloqueante",
) -> dict:
    return {
        "code": code,
        "message": message,
        "severity": severity,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "field": field,
        "next_action": next_action,
    }


def _append_unique(items: list[dict], value: dict) -> None:
    marker = (
        value.get("code"),
        value.get("entity_type"),
        str(value.get("entity_id")),
        value.get("field"),
        value.get("message"),
    )
    for item in items:
        other = (
            item.get("code"),
            item.get("entity_type"),
            str(item.get("entity_id")),
            item.get("field"),
            item.get("message"),
        )
        if marker == other:
            return
    items.append(value)


def _base_response(
    *,
    calculavel: bool,
    fechavel: bool | None,
    competencia_status: str | None,
    missao_status: str | None,
    bloqueios: list[dict],
    avisos: list[dict],
    parametros_faltantes: list[dict],
    parametros_invalidos: list[dict],
    parametros_nao_elegiveis: list[dict],
    parametros_ambiguos: list[dict],
    dados_qa_detectados: list[dict],
    divergencias: list[dict],
    can_execute_actions: dict[str, bool],
) -> dict:
    if bloqueios:
        next_action = bloqueios[0].get("next_action") or "Corrigir bloqueios de preflight antes de executar."
    else:
        next_action = "Nenhum bloqueio encontrado; execucao habilitada."
    return {
        "calculavel": bool(calculavel),
        "fechavel": fechavel if fechavel is not None else False,
        "competencia_status": competencia_status,
        "missao_status": missao_status,
        "bloqueios": bloqueios,
        "avisos": avisos,
        "parametros_faltantes": parametros_faltantes,
        "parametros_invalidos": parametros_invalidos,
        "parametros_nao_elegiveis": parametros_nao_elegiveis,
        "parametros_ambiguos": parametros_ambiguos,
        "dados_qa_detectados": dados_qa_detectados,
        "divergencias": divergencias,
        "next_action": next_action,
        "can_execute_actions": can_execute_actions,
    }


def _parameter_summary(parameter: dict, *, reasons: list[str] | None = None) -> dict:
    summary = {
        "parameter_id": _to_int(parameter.get("id") if "id" in parameter else parameter.get("parameter_id")),
        "tipo": _optional_text(parameter.get("tipo")),
        "funcao": _optional_text(parameter.get("funcao")),
        "categoria": _optional_text(parameter.get("categoria")),
        "unidade": _optional_text(parameter.get("unidade")),
        "valor": parameter.get("valor"),
        "governance_class": classificacao_governanca_parametro(parameter),
    }
    if reasons:
        summary["reasons"] = sorted(set(reasons))
    return summary


def _parameter_reasons(
    *,
    parameter: dict,
    reference_date: date | None,
    overlap_ids: set[int],
    divergence_ids: set[int],
) -> list[str]:
    reasons: list[str] = []
    parameter_id = _to_int(parameter.get("id"))
    governance_class = classificacao_governanca_parametro(parameter)
    if governance_class is None:
        reasons.append("classificacao_ausente")
    if _clean_text(parameter.get("unidade")).upper() == "BRL":
        reasons.append("unidade_brl_legacy")
    if not _vigencia_cobre_data(parameter, reference_date=reference_date):
        reasons.append("vigencia_invalida_ou_fora_da_data")
    if parameter_id is not None and parameter_id in overlap_ids:
        reasons.append("sobreposicao_semantica_ativa")
    if parameter_id is not None and parameter_id in divergence_ids:
        reasons.append("divergencia_semantica_ativa")
    if governance_class in {GOV_CLASS_QA_SMOKE, GOV_CLASS_LEGACY, GOV_CLASS_DEPRECATED}:
        reasons.append(f"classificacao_nao_elegivel:{governance_class}")
    if not parametro_elegivel_fechamento_real(parameter, environment=_RELEASE_ENVIRONMENT):
        reasons.append("nao_elegivel_para_fechamento_real")
    return sorted(set(reasons))


def _matches_spec(parameter: dict, spec: dict, *, check_unit: bool) -> bool:
    if _optional_text(parameter.get("tipo")) != _optional_text(spec.get("tipo")):
        return False
    if _optional_text(parameter.get("funcao")) != _optional_text(spec.get("funcao")):
        return False
    if _optional_text(parameter.get("categoria")) != _optional_text(spec.get("categoria")):
        return False
    if check_unit and _optional_text(parameter.get("unidade")) != _optional_text(spec.get("unidade")):
        return False
    return True


def _load_parameters_for_types(
    db,
    *,
    org_id: str,
    parameter_types: tuple[str, ...],
    vigencia_em: str | None,
) -> list[dict]:
    rows: list[dict] = []
    for parameter_type in sorted(set(parameter_types)):
        rows.extend(
            listar_parametros_financeiros_rows(
                db,
                org_id=org_id,
                tipo=parameter_type,
                status="ativo",
                vigencia_em=vigencia_em,
                limit=10000,
                offset=0,
            )
        )
    return rows


def _analyze_required_specs(
    *,
    specs: list[dict] | tuple[dict, ...],
    active_parameters: list[dict],
    active_vigente_parameters: list[dict],
    reference_date: date | None,
    overlap_ids: set[int],
    divergence_ids: set[int],
    entity_type: str,
    entity_id: int | str | None,
) -> dict:
    bloqueios: list[dict] = []
    faltantes: list[dict] = []
    invalidos: list[dict] = []
    nao_elegiveis: list[dict] = []
    ambiguos: list[dict] = []
    qa_detectados: list[dict] = []

    for spec in specs:
        candidates_all = [item for item in active_parameters if _matches_spec(item, spec, check_unit=False)]
        candidates_vigente = [item for item in active_vigente_parameters if _matches_spec(item, spec, check_unit=False)]
        candidates_exact = [item for item in active_vigente_parameters if _matches_spec(item, spec, check_unit=True)]
        spec_descriptor = {
            "tipo": spec.get("tipo"),
            "funcao": spec.get("funcao"),
            "categoria": spec.get("categoria"),
            "unidade": spec.get("unidade"),
        }

        if not candidates_all:
            faltantes.append(spec_descriptor)
            _append_unique(
                bloqueios,
                _block(
                    code="finance_preflight_parameter_missing",
                    message=(
                        f"Parametro obrigatorio ausente: {spec.get('tipo')} "
                        f"(funcao={spec.get('funcao') or '-'}, categoria={spec.get('categoria') or '-'})."
                    ),
                    entity_type=entity_type,
                    entity_id=entity_id,
                    field="parametros",
                    next_action="Cadastrar parametro canonico com unidade e vigencia corretas.",
                ),
            )
            continue

        if not candidates_vigente:
            invalidos.append({**spec_descriptor, "reason": "fora_da_vigencia"})
            _append_unique(
                bloqueios,
                _block(
                    code="finance_preflight_parameter_not_vigente",
                    message=(
                        f"Parametro sem vigencia aplicavel para a referencia atual: {spec.get('tipo')} "
                        f"(funcao={spec.get('funcao') or '-'}, categoria={spec.get('categoria') or '-'})."
                    ),
                    entity_type=entity_type,
                    entity_id=entity_id,
                    field="parametros.vigencia",
                    next_action="Ajustar vigencia_inicio/vigencia_fim para cobrir o periodo de calculo.",
                ),
            )
            continue

        if not candidates_exact:
            invalidos.append(
                {
                    **spec_descriptor,
                    "reason": "unidade_incorreta",
                    "unidades_encontradas": sorted({_optional_text(item.get("unidade")) for item in candidates_vigente}),
                }
            )
            _append_unique(
                bloqueios,
                _block(
                    code="finance_preflight_parameter_invalid_unit",
                    message=(
                        f"Unidade invalida para {spec.get('tipo')}: esperado {spec.get('unidade')}."
                    ),
                    entity_type=entity_type,
                    entity_id=entity_id,
                    field="parametros.unidade",
                    next_action="Corrigir unidade do parametro conforme matriz canonica.",
                ),
            )
            continue

        if len(candidates_exact) > 1:
            ambiguous_item = {
                **spec_descriptor,
                "parameter_ids": sorted(
                    [
                        parameter_id
                        for item in candidates_exact
                        if (parameter_id := _to_int(item.get("id"))) is not None
                    ]
                ),
            }
            ambiguos.append(ambiguous_item)
            _append_unique(
                bloqueios,
                _block(
                    code="finance_preflight_parameter_ambiguous",
                    message=(
                        f"Ambiguidade de parametro para {spec.get('tipo')} "
                        f"(funcao={spec.get('funcao') or '-'}, categoria={spec.get('categoria') or '-'})."
                    ),
                    entity_type=entity_type,
                    entity_id=entity_id,
                    field="parametros",
                    next_action="Eliminar sobreposicao/duplicidade de regra ativa na mesma chave.",
                ),
            )
            continue

        chosen = candidates_exact[0]
        reasons = _parameter_reasons(
            parameter=chosen,
            reference_date=reference_date,
            overlap_ids=overlap_ids,
            divergence_ids=divergence_ids,
        )
        if reasons:
            summary = _parameter_summary(chosen, reasons=reasons)
            nao_elegiveis.append(summary)
            if any(reason.endswith(GOV_CLASS_QA_SMOKE) for reason in reasons):
                qa_detectados.append(summary)
            _append_unique(
                bloqueios,
                _block(
                    code="finance_preflight_parameter_not_eligible",
                    message=(
                        f"Parametro nao elegivel para release gate: {chosen.get('tipo')} "
                        f"(id={summary.get('parameter_id')}, motivos={', '.join(summary.get('reasons') or [])})."
                    ),
                    entity_type=entity_type,
                    entity_id=entity_id,
                    field="parametros.elegibilidade",
                    next_action=(
                        "Promover apenas parametros canonicos para classe elegivel e remover BRL/QA/legacy/"
                        "deprecated/overlap/divergencia."
                    ),
                ),
            )

    return {
        "bloqueios": bloqueios,
        "parametros_faltantes": faltantes,
        "parametros_invalidos": invalidos,
        "parametros_nao_elegiveis": nao_elegiveis,
        "parametros_ambiguos": ambiguos,
        "dados_qa_detectados": qa_detectados,
    }


def _mission_divergences(rows: list[dict], *, mission_id: int) -> list[dict]:
    selected: list[dict] = []
    for row in rows:
        normalized = serialize_finance_divergence(row)
        mission_ref = _to_int(normalized.get("mission_id"))
        entity_type = _clean_text(normalized.get("entity_type")).lower()
        entity_id = _to_int(normalized.get("entity_id"))
        if mission_ref == mission_id:
            selected.append(normalized)
            continue
        if entity_type in {"finance_mission", "finance_missao", "finance_mission_operational"} and entity_id == mission_id:
            selected.append(normalized)
    return selected


def _valid_missions(rows: list[dict]) -> list[dict]:
    valid: list[dict] = []
    for row in rows:
        status = _clean_text(row.get("status")).lower()
        if status == "cancelada":
            continue
        if _to_int(row.get("comandante_tripulante_id")) is None or _to_int(row.get("copiloto_tripulante_id")) is None:
            continue
        if _is_semantically_none(row.get("horario_apresentacao")) or _is_semantically_none(row.get("horario_abandono")):
            continue
        valid.append(row)
    return valid


def _productivity_required_specs_from_missions(missions: list[dict]) -> list[dict]:
    specs: dict[tuple[str | None, ...], dict] = {}

    def add(tipo: str, *, funcao: str | None, categoria: str | None = None):
        spec = {"tipo": tipo, "funcao": funcao, "categoria": categoria, "unidade": "valor"}
        specs[_spec_key(spec)] = spec

    add("icao_sdea", funcao="comandante")
    add("icao_sdea", funcao="copiloto")
    add("instrutor", funcao=None)
    add("checador", funcao=None)
    add("cobertura_base", funcao="comandante")
    add("cobertura_base", funcao="copiloto")
    has_common_overnight = any(
        not bool(item.get("cobertura_base")) and (_to_int(item.get("quantidade_pernoites")) or 0) > 1
        for item in missions
    )
    if has_common_overnight:
        add("pernoite_comum_sem_cobertura", funcao="comandante")
        add("pernoite_comum_sem_cobertura", funcao="copiloto")

    categories = {normalizar_categoria_operacional(item.get("categoria_financeira_aeronave")) for item in missions}
    if CANONICAL_CATEGORY_A in categories:
        add("missao_categoria_a", funcao="comandante", categoria=CANONICAL_CATEGORY_A)
        add("missao_categoria_a", funcao="copiloto", categoria=CANONICAL_CATEGORY_A)
        add("garantia_minima", funcao="comandante", categoria=CANONICAL_CATEGORY_A)
        add("garantia_minima", funcao="copiloto", categoria=CANONICAL_CATEGORY_A)
    if CANONICAL_CATEGORY_B in categories:
        add("missao_categoria_b", funcao="comandante", categoria=CANONICAL_CATEGORY_B)
        add("missao_categoria_b", funcao="copiloto", categoria=CANONICAL_CATEGORY_B)
        add("garantia_minima", funcao="comandante", categoria=CANONICAL_CATEGORY_B)
        add("garantia_minima", funcao="copiloto", categoria=CANONICAL_CATEGORY_B)
    if CANONICAL_CATEGORY_TURBOHELICE_PALMAS in categories:
        add("excecao_palmas_turbohelice", funcao="comandante", categoria=CANONICAL_CATEGORY_TURBOHELICE_PALMAS)
        add("excecao_palmas_turbohelice", funcao="copiloto", categoria=CANONICAL_CATEGORY_TURBOHELICE_PALMAS)

    return [specs[key] for key in sorted(specs)]


def _audit_rows_available(
    db,
    *,
    org_id: str,
    competencia: str | None,
) -> bool:
    rows = listar_eventos_auditoria_financeira_rows(
        db,
        org_id=org_id,
        competencia=competencia,
        limit=1,
        offset=0,
    )
    return bool(rows)


def preflight_calculo_missao(
    missao_operacional_id: int,
    *,
    org_id: str | None = None,
    db=None,
) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id)
    mission = fetch_missao_operacional_detail(
        resolved_db,
        missao_operacional_id=int(missao_operacional_id),
        org_id=resolved_org_id,
    )
    bloqueios: list[dict] = []
    avisos: list[dict] = []
    parametros_faltantes: list[dict] = []
    parametros_invalidos: list[dict] = []
    parametros_nao_elegiveis: list[dict] = []
    parametros_ambiguos: list[dict] = []
    dados_qa_detectados: list[dict] = []
    divergencias: list[dict] = []

    if not mission:
        bloqueios.append(
            _block(
                code="finance_preflight_mission_not_found",
                message="Missao operacional nao encontrada.",
                entity_type="finance_mission",
                entity_id=missao_operacional_id,
                field="mission_id",
                next_action="Verificar o identificador da missao antes de recalcular.",
            )
        )
        return _base_response(
            calculavel=False,
            fechavel=False,
            competencia_status=None,
            missao_status=None,
            bloqueios=bloqueios,
            avisos=avisos,
            parametros_faltantes=parametros_faltantes,
            parametros_invalidos=parametros_invalidos,
            parametros_nao_elegiveis=parametros_nao_elegiveis,
            parametros_ambiguos=parametros_ambiguos,
            dados_qa_detectados=dados_qa_detectados,
            divergencias=divergencias,
            can_execute_actions={"recalcular_missao": False},
        )

    mission_status = _clean_text(mission.get("status")).lower() or "rascunho"
    competencia = _clean_text(mission.get("competencia"))
    competencia_row = fetch_competencia_financeira(resolved_db, competencia=competencia, org_id=resolved_org_id)
    competencia_status = _clean_text((competencia_row or {}).get("status")).lower() or "aberta"

    if mission_status == "cancelada":
        _append_unique(
            bloqueios,
            _block(
                code="finance_preflight_mission_cancelled",
                message="Missao cancelada nao pode ser recalculada.",
                entity_type="finance_mission",
                entity_id=mission.get("id"),
                field="status",
                next_action="Reativar ou selecionar uma missao ativa para recalculo.",
            ),
        )
    if mission_status not in _ACTIVE_STATUSES:
        _append_unique(
            bloqueios,
            _block(
                code="finance_preflight_mission_not_active",
                message=f"Missao com status '{mission_status}' nao esta apta para recalculo.",
                entity_type="finance_mission",
                entity_id=mission.get("id"),
                field="status",
                next_action="Alterar status da missao para ativa ou recalcule somente missoes aptas.",
            ),
        )
    if competencia_status == "fechada":
        _append_unique(
            bloqueios,
            _block(
                code="finance_preflight_competencia_fechada",
                message=f"Competencia {competencia} esta fechada para mutacoes.",
                entity_type="finance_period",
                entity_id=competencia,
                field="competencia_status",
                next_action="Reabrir competencia com motivo formal antes de recalcular a missao.",
            ),
        )

    participants_by_role = {
        _clean_text(item.get("funcao")).lower(): item
        for item in (mission.get("participantes") or [])
        if _clean_text(item.get("status")).lower() != "cancelado"
    }
    if not participants_by_role.get("comandante"):
        _append_unique(
            bloqueios,
            _block(
                code="finance_preflight_missing_commander",
                message="Comandante da missao nao encontrado.",
                entity_type="finance_mission",
                entity_id=mission.get("id"),
                field="comandante_tripulante_id",
                next_action="Vincular comandante ativo na missao operacional.",
            ),
        )
    if not participants_by_role.get("copiloto"):
        _append_unique(
            bloqueios,
            _block(
                code="finance_preflight_missing_copilot",
                message="Copiloto da missao nao encontrado.",
                entity_type="finance_mission",
                entity_id=mission.get("id"),
                field="copiloto_tripulante_id",
                next_action="Vincular copiloto ativo na missao operacional.",
            ),
        )
    if _to_int(mission.get("aeronave_id")) is None:
        _append_unique(
            bloqueios,
            _block(
                code="finance_preflight_missing_equipment",
                message="Equipamento da missao nao foi informado.",
                entity_type="finance_mission",
                entity_id=mission.get("id"),
                field="aeronave_id",
                next_action="Informar equipamento/categoria financeira antes do recalculo.",
            ),
        )
    if _is_semantically_none(mission.get("categoria_financeira_aeronave")):
        _append_unique(
            bloqueios,
            _block(
                code="finance_preflight_missing_category",
                message="Categoria financeira da aeronave nao informada.",
                entity_type="finance_mission",
                entity_id=mission.get("id"),
                field="categoria_financeira_aeronave",
                next_action="Preencher categoria financeira da aeronave na missao.",
            ),
        )
    if _is_semantically_none(mission.get("horario_apresentacao")) or _is_semantically_none(mission.get("horario_abandono")):
        _append_unique(
            bloqueios,
            _block(
                code="finance_preflight_missing_schedule",
                message="Horario de apresentacao/abandono obrigatorio para recalculo horario.",
                entity_type="finance_mission",
                entity_id=mission.get("id"),
                field="horario_apresentacao",
                next_action="Preencher horarios completos da jornada da missao.",
            ),
        )

    reference_date = _parse_date(mission.get("data_missao"))
    if reference_date is None:
        _append_unique(
            bloqueios,
            _block(
                code="finance_preflight_mission_date_invalid",
                message="Data da missao invalida para resolver vigencia de parametros.",
                entity_type="finance_mission",
                entity_id=mission.get("id"),
                field="data_missao",
                next_action="Corrigir data da missao no formato YYYY-MM-DD.",
            ),
        )
    else:
        if verificar_feriado_nacional_por_data(
            resolved_db,
            data=reference_date.isoformat(),
            org_id=resolved_org_id,
            status="ativo",
        ):
            avisos.append(
                _block(
                    code="finance_preflight_holiday_detected",
                    message=f"Feriado nacional identificado em {reference_date.isoformat()}.",
                    entity_type="finance_holiday",
                    entity_id=reference_date.isoformat(),
                    field="data_missao",
                    next_action="Conferir impacto de domingo/feriado no adicional horario.",
                    severity="informativa",
                )
            )

        active_parameters = _load_parameters_for_types(
            resolved_db,
            org_id=resolved_org_id,
            parameter_types=_PARAMETER_TYPES_HOURLY,
            vigencia_em=None,
        )
        active_vigente_parameters = _load_parameters_for_types(
            resolved_db,
            org_id=resolved_org_id,
            parameter_types=_PARAMETER_TYPES_HOURLY,
            vigencia_em=reference_date.isoformat(),
        )
        overlap_ids = detectar_sobreposicoes_ativas(active_vigente_parameters, include_unit=False)
        divergence_ids = detectar_divergencias_ativas(active_vigente_parameters, include_unit=False)
        analysis = _analyze_required_specs(
            specs=_MISSION_REQUIRED_SPECS,
            active_parameters=active_parameters,
            active_vigente_parameters=active_vigente_parameters,
            reference_date=reference_date,
            overlap_ids=overlap_ids,
            divergence_ids=divergence_ids,
            entity_type="finance_mission",
            entity_id=mission.get("id"),
        )
        bloqueios.extend(analysis["bloqueios"])
        parametros_faltantes.extend(analysis["parametros_faltantes"])
        parametros_invalidos.extend(analysis["parametros_invalidos"])
        parametros_nao_elegiveis.extend(analysis["parametros_nao_elegiveis"])
        parametros_ambiguos.extend(analysis["parametros_ambiguos"])
        dados_qa_detectados.extend(analysis["dados_qa_detectados"])

    divergence_rows = listar_divergencias_financeiras_rows(
        resolved_db,
        org_id=resolved_org_id,
        competencia=competencia or None,
        status=None,
        severidade=None,
        codigo=None,
        limit=500,
        offset=0,
    )
    divergencias = _mission_divergences(divergence_rows, mission_id=int(mission.get("id")))
    if divergencias:
        has_blocking_divergence = any(
            _clean_text(item.get("severity")).lower() in _BLOCKING_DIVERGENCE_SEVERITIES for item in divergencias
        )
        if has_blocking_divergence:
            _append_unique(
                bloqueios,
                _block(
                    code="finance_preflight_mission_divergence_blocking",
                    message="Divergencias bloqueantes/altas encontradas para a missao.",
                    entity_type="finance_divergence",
                    entity_id=mission.get("id"),
                    field="divergencias",
                    next_action="Resolver divergencias antes de recalcular ou fechar competencia.",
                ),
            )
        else:
            avisos.append(
                _block(
                    code="finance_preflight_mission_divergence_warning",
                    message="Divergencias informativas detectadas para a missao.",
                    entity_type="finance_divergence",
                    entity_id=mission.get("id"),
                    field="divergencias",
                    next_action="Revisar divergencias e confirmar se impactam a operacao.",
                    severity="informativa",
                )
            )

    calculavel = not bloqueios
    return _base_response(
        calculavel=calculavel,
        fechavel=False,
        competencia_status=competencia_status,
        missao_status=mission_status,
        bloqueios=bloqueios,
        avisos=avisos,
        parametros_faltantes=parametros_faltantes,
        parametros_invalidos=parametros_invalidos,
        parametros_nao_elegiveis=parametros_nao_elegiveis,
        parametros_ambiguos=parametros_ambiguos,
        dados_qa_detectados=dados_qa_detectados,
        divergencias=divergencias,
        can_execute_actions={"recalcular_missao": calculavel},
    )


def preflight_calculo_competencia(
    competencia: str,
    *,
    org_id: str | None = None,
    db=None,
) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id)
    resolved_competencia = _clean_text(competencia)

    bloqueios: list[dict] = []
    avisos: list[dict] = []
    parametros_faltantes: list[dict] = []
    parametros_invalidos: list[dict] = []
    parametros_nao_elegiveis: list[dict] = []
    parametros_ambiguos: list[dict] = []
    dados_qa_detectados: list[dict] = []

    if not _COMPETENCIA_RE.match(resolved_competencia):
        bloqueios.append(
            _block(
                code="finance_preflight_competencia_invalid",
                message="Competencia deve estar no formato YYYY-MM.",
                entity_type="finance_period",
                entity_id=resolved_competencia or None,
                field="competencia",
                next_action="Informar competencia valida para o preflight.",
            )
        )
        return _base_response(
            calculavel=False,
            fechavel=False,
            competencia_status=None,
            missao_status=None,
            bloqueios=bloqueios,
            avisos=avisos,
            parametros_faltantes=parametros_faltantes,
            parametros_invalidos=parametros_invalidos,
            parametros_nao_elegiveis=parametros_nao_elegiveis,
            parametros_ambiguos=parametros_ambiguos,
            dados_qa_detectados=dados_qa_detectados,
            divergencias=[],
            can_execute_actions={
                "recalcular_competencia": False,
                "fechar_competencia": False,
                "gerar_pdf_previa": False,
                "gerar_pdf_fechamento": False,
            },
        )

    detail = detalhar_competencia_financeira(resolved_competencia, org_id=resolved_org_id, db=resolved_db)
    period = detail.get("period") or {}
    snapshot = detail.get("snapshot") or {}
    divergencias = detail.get("divergences") or []
    competencia_status = _clean_text(period.get("status")).lower() or "aberta"

    competencia_row = fetch_competencia_financeira(
        resolved_db,
        competencia=resolved_competencia,
        org_id=resolved_org_id,
    )
    if competencia_row is None:
        avisos.append(
            _block(
                code="finance_preflight_period_will_initialize",
                message="Competencia ainda nao inicializada; snapshot sera montado sob demanda.",
                entity_type="finance_period",
                entity_id=resolved_competencia,
                field="status",
                next_action="Executar recalculo da competencia para inicializar snapshot em conferencia.",
                severity="informativa",
            )
        )

    if competencia_status == "fechada":
        _append_unique(
            bloqueios,
            _block(
                code="finance_preflight_competencia_fechada",
                message=f"Competencia {resolved_competencia} esta fechada para mutacoes.",
                entity_type="finance_period",
                entity_id=resolved_competencia,
                field="status",
                next_action="Reabrir competencia com motivo formal antes de recalcular.",
            ),
        )

    missions = list_missoes_operacionais(
        resolved_db,
        competencia=resolved_competencia,
        org_id=resolved_org_id,
        status=None,
        limit=10000,
        offset=0,
    )
    valid_missions = _valid_missions(missions)
    if not valid_missions:
        _append_unique(
            bloqueios,
            _block(
                code="finance_preflight_no_valid_missions",
                message="Nenhuma missao valida encontrada para a competencia.",
                entity_type="finance_period",
                entity_id=resolved_competencia,
                field="missoes",
                next_action="Cadastrar/ajustar missoes ativas antes do recalculo de competencia.",
            ),
        )

    reference_date = _parse_date(f"{resolved_competencia}-01")
    required_specs = _productivity_required_specs_from_missions(valid_missions or missions)
    active_parameters = _load_parameters_for_types(
        resolved_db,
        org_id=resolved_org_id,
        parameter_types=_PARAMETER_TYPES_PRODUCTIVITY,
        vigencia_em=None,
    )
    active_vigente_parameters = _load_parameters_for_types(
        resolved_db,
        org_id=resolved_org_id,
        parameter_types=_PARAMETER_TYPES_PRODUCTIVITY,
        vigencia_em=f"{resolved_competencia}-01",
    )
    overlap_ids = detectar_sobreposicoes_ativas(active_vigente_parameters, include_unit=False)
    divergence_ids = detectar_divergencias_ativas(active_vigente_parameters, include_unit=False)
    analysis = _analyze_required_specs(
        specs=required_specs,
        active_parameters=active_parameters,
        active_vigente_parameters=active_vigente_parameters,
        reference_date=reference_date,
        overlap_ids=overlap_ids,
        divergence_ids=divergence_ids,
        entity_type="finance_period",
        entity_id=resolved_competencia,
    )
    bloqueios.extend(analysis["bloqueios"])
    parametros_faltantes.extend(analysis["parametros_faltantes"])
    parametros_invalidos.extend(analysis["parametros_invalidos"])
    parametros_nao_elegiveis.extend(analysis["parametros_nao_elegiveis"])
    parametros_ambiguos.extend(analysis["parametros_ambiguos"])
    dados_qa_detectados.extend(analysis["dados_qa_detectados"])

    release_gate = avaliar_elegibilidade_fechamento_real_snapshot(
        db=resolved_db,
        competencia=resolved_competencia,
        org_id=resolved_org_id,
        snapshot=snapshot,
        strict=False,
    )
    if not release_gate.get("release_eligible"):
        _append_unique(
            bloqueios,
            _block(
                code="finance_preflight_release_gate_blocked",
                message=(
                    f"Release gate bloqueado para {resolved_competencia}: "
                    f"{len(release_gate.get('blocking_parameters') or [])} parametro(s) nao elegivel(is)."
                ),
                entity_type="finance_period",
                entity_id=resolved_competencia,
                field="release_gate",
                next_action=release_gate.get("next_action")
                or "Promover parametros canonicos e eliminar bloqueios de governanca.",
            ),
        )
        for item in release_gate.get("blocking_parameters") or []:
            summary = _parameter_summary(item, reasons=list(item.get("reasons") or []))
            if summary not in parametros_nao_elegiveis:
                parametros_nao_elegiveis.append(summary)
            if GOV_CLASS_QA_SMOKE in _clean_text(summary.get("governance_class")):
                if summary not in dados_qa_detectados:
                    dados_qa_detectados.append(summary)

    if divergencias:
        has_blocking_divergence = any(
            _clean_text(item.get("severity")).lower() in _BLOCKING_DIVERGENCE_SEVERITIES for item in divergencias
        )
        if has_blocking_divergence:
            _append_unique(
                bloqueios,
                _block(
                    code="finance_preflight_competencia_divergence_blocking",
                    message="Competencia possui divergencias bloqueantes/altas.",
                    entity_type="finance_divergence",
                    entity_id=resolved_competencia,
                    field="divergencias",
                    next_action="Resolver divergencias antes de fechar competencia real.",
                ),
            )
        else:
            avisos.append(
                _block(
                    code="finance_preflight_competencia_divergence_warning",
                    message="Competencia possui divergencias informativas.",
                    entity_type="finance_divergence",
                    entity_id=resolved_competencia,
                    field="divergencias",
                    next_action="Revisar divergencias e registrar aceite operacional, se aplicavel.",
                    severity="informativa",
                )
            )

    if not _audit_rows_available(resolved_db, org_id=resolved_org_id, competencia=resolved_competencia):
        avisos.append(
            _block(
                code="finance_preflight_audit_empty",
                message="Sem eventos de auditoria financeira para a competencia no recorte atual.",
                entity_type="finance_audit",
                entity_id=resolved_competencia,
                field="auditoria",
                next_action="Executar operacoes rastreaveis para consolidar trilha de auditoria.",
                severity="informativa",
            )
        )

    calculavel = not bloqueios
    fechavel = bool(calculavel and release_gate.get("release_eligible") and competencia_status != "fechada")
    can_execute_actions = {
        "recalcular_competencia": calculavel and competencia_status != "fechada",
        "fechar_competencia": fechavel,
        "gerar_pdf_previa": True,
        "gerar_pdf_fechamento": fechavel,
    }
    return _base_response(
        calculavel=calculavel and competencia_status != "fechada",
        fechavel=fechavel,
        competencia_status=competencia_status,
        missao_status=None,
        bloqueios=bloqueios,
        avisos=avisos,
        parametros_faltantes=parametros_faltantes,
        parametros_invalidos=parametros_invalidos,
        parametros_nao_elegiveis=parametros_nao_elegiveis,
        parametros_ambiguos=parametros_ambiguos,
        dados_qa_detectados=dados_qa_detectados,
        divergencias=divergencias,
        can_execute_actions=can_execute_actions,
    )
