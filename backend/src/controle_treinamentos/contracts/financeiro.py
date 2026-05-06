from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

FINANCE_ORG_SCOPE_DEFAULT = "default_single_tenant"

FINANCE_API_ROUTE_PREFIX = "/api/v1/financeiro"

FINANCE_CREW_FUNCTIONS = ("comandante", "copiloto")

FINANCE_MISSION_STATUS = (
    "rascunho",
    "ativa",
    "cancelada",
    "recalculo_pendente",
)

FINANCE_PERIOD_STATUS = (
    "aberta",
    "em_conferencia",
    "fechada",
    "reaberta",
)

FINANCE_PARAMETER_TYPES = (
    "duracao_hora_noturna_minutos",
    "adicional_noturno",
    "domingo_feriado_diurno",
    "domingo_feriado_noturno",
    "periodo_diurno_inicio",
    "periodo_diurno_fim",
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

FINANCE_HOURLY_BONUS_TYPES = (
    "adicional_noturno",
    "domingo_feriado_diurno",
    "domingo_feriado_noturno",
    "pre_jornada",
    "pos_jornada",
)

FINANCE_PRODUCTIVITY_BONUS_TYPES = (
    "icao",
    "instrutor",
    "checador",
    "missoes_categoria_a",
    "missoes_categoria_b",
    "cobertura_base",
    "pernoite_comum_sem_cobertura",
    "excecao_palmas",
    "produtividade",
    "garantia_minima",
)

FINANCE_DIVERGENCE_SEVERITIES = (
    "bloqueante",
    "alta",
    "media",
    "informativa",
)

FINANCE_API_CONTRACT = {
    "status": "registered_runtime",
    "base_path": FINANCE_API_ROUTE_PREFIX,
    "resources": {
        "missoes": {
            "canonical_paths": (
                "/api/v1/financeiro/missoes",
                "/api/v1/financeiro/missoes/preview",
                "/api/v1/financeiro/missoes/<id>",
                "/api/v1/financeiro/missoes/<id> [DELETE]",
                "/api/v1/financeiro/missoes/<id>/preflight-calculo",
                "/api/v1/financeiro/missoes/<id>/recalcular",
                "/api/v1/financeiro/missoes/<id>/cancelar",
            ),
        },
        "bonificacoes": {
            "canonical_paths": (
                "/api/v1/financeiro/bonificacoes/horaria",
                "/api/v1/financeiro/bonificacoes/horaria/<id>",
                "/api/v1/financeiro/bonificacoes/produtividade",
                "/api/v1/financeiro/bonificacoes/produtividade/<tripulante_id>",
            ),
        },
        "produtividade": {
            "canonical_paths": (
                "/api/v1/financeiro/produtividade/consolidado",
            ),
        },
        "lancamentos_jornada": {
            "canonical_paths": (
                "/api/v1/financeiro/lancamentos-jornada",
                "/api/v1/financeiro/lancamentos-jornada/preview",
                "/api/v1/financeiro/lancamentos-jornada/<id>",
                "/api/v1/financeiro/lancamentos-jornada/<id>/recalcular",
                "/api/v1/financeiro/lancamentos-jornada/recalcular-grade",
                "/api/v1/financeiro/lancamentos-jornada.pdf",
            ),
        },
        "relatorios": {
            "canonical_paths": (
                "/api/v1/financeiro/horas-totais-voadas",
                "/api/v1/financeiro/horas-totais-voadas.pdf",
                "/api/v1/financeiro/relatorios/individual.pdf",
                "/api/v1/financeiro/extrato-periodo",
                "/api/v1/financeiro/extrato-periodo.pdf",
            ),
        },
        "competencias": {
            "canonical_paths": (
                "/api/v1/financeiro/competencias/<competencia>",
                "/api/v1/financeiro/competencias/<competencia>/preflight-calculo",
                "/api/v1/financeiro/competencias/<competencia>/recalcular",
                "/api/v1/financeiro/competencias/<competencia>/fechar",
                "/api/v1/financeiro/competencias/<competencia>/reabrir",
            ),
        },
        "parametros": {
            "canonical_paths": (
                "/api/v1/financeiro/parametros",
                "/api/v1/financeiro/parametros/<id>",
                "/api/v1/financeiro/feriados",
                "/api/v1/financeiro/feriados/<id>",
            ),
        },
        "auditoria": {
            "canonical_paths": (
                "/api/v1/financeiro/auditoria",
                "/api/v1/financeiro/divergencias",
            ),
        },
    },
}

# Backward-compatible alias kept to avoid breaking imports while callers migrate.
FINANCE_FUTURE_API_CONTRACT = FINANCE_API_CONTRACT

FINANCE_STUB_API_PATHS: tuple[str, ...] = ()


def _as_text(value) -> str:
    return str(value or "").strip()


def _empty_to_none(value) -> str | None:
    text = _as_text(value)
    return text or None


def _as_int(value, *, default: int = 0) -> int:
    if value is None or value == "":
        return default
    return int(value)


def _as_optional_int(value) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _as_bool(value) -> bool:
    return bool(value)


def _as_decimal_text(value, *, default: str = "0") -> str:
    if value is None or value == "":
        return default
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value).strip()


def _as_iso_date_or_none(value) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return _empty_to_none(value)


def _as_iso_datetime_or_none(value) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return _empty_to_none(value)


def _org_id(row: dict) -> str:
    return _as_text(row.get("org_id")) or FINANCE_ORG_SCOPE_DEFAULT


def _nested_value(value):
    if isinstance(value, dict):
        return {str(key): _nested_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_nested_value(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


def _before_after(row: dict, *keys: str):
    for key in keys:
        if key in row:
            return _nested_value(row.get(key))
    return None


def _serialize_links(base_path: str, item_id: int | None) -> dict:
    if item_id is None:
        return {}
    return {"self": f"{base_path}/{item_id}"}


def _serialize_parameter_reference(item: dict) -> dict:
    return {
        "parameter_id": _as_optional_int(item.get("parameter_id") if "parameter_id" in item else item.get("id")),
        "tipo": _as_text(item.get("tipo")),
        "funcao": _empty_to_none(item.get("funcao")),
        "categoria": _empty_to_none(item.get("categoria")),
        "valor": _as_decimal_text(item.get("valor")),
        "unidade": _as_text(item.get("unidade")),
        "display_value": _empty_to_none(item.get("display_value")),
        "vigencia_inicio": _as_iso_date_or_none(item.get("vigencia_inicio")),
        "vigencia_fim": _as_iso_date_or_none(item.get("vigencia_fim")),
        "applied_at": _as_iso_datetime_or_none(item.get("applied_at")),
    }


def serialize_calculation_memory(memory: dict | None) -> dict:
    source = memory or {}
    participant = source.get("participant") or {}
    return {
        "calculation_version": _as_text(source.get("calculation_version")),
        "org_id": _org_id(source),
        "competencia": _as_text(source.get("competencia")),
        "source": _nested_value(source.get("source") or {}),
        "participant": {
            "tripulante_id": _as_optional_int(participant.get("tripulante_id")),
            "funcao": _as_text(participant.get("funcao")),
        },
        "inputs": _nested_value(source.get("inputs") or {}),
        "parameters": [_serialize_parameter_reference(item) for item in source.get("parameters", [])],
        "calendar_flags": _nested_value(source.get("calendar_flags") or {}),
        "steps": [serialize_calculation_memory_step(item) for item in source.get("steps", [])],
        "totals": _nested_value(source.get("totals") or {}),
        "warnings": [_nested_value(item) for item in source.get("warnings", [])],
        "generated_at": _as_iso_datetime_or_none(source.get("generated_at")),
    }


def serialize_calculation_memory_step(step: dict) -> dict:
    return {
        "rule_key": _as_text(step.get("rule_key")),
        "rule_label": _as_text(step.get("rule_label")),
        "entrada_usada": _nested_value(step.get("entrada_usada") or {}),
        "parametro_usado": (
            _serialize_parameter_reference(step.get("parametro_usado") or {})
            if step.get("parametro_usado") is not None
            else None
        ),
        "formula_conceitual": _as_text(step.get("formula_conceitual")),
        "resultado_intermediario": _nested_value(step.get("resultado_intermediario") or {}),
        "resultado_final": _nested_value(step.get("resultado_final") or {}),
        "notes": [_nested_value(item) for item in step.get("notes", [])],
    }


def serialize_finance_mission(row: dict) -> dict:
    mission_id = _as_optional_int(row.get("id"))
    return {
        "id": mission_id,
        "org_id": _org_id(row),
        "competencia": _as_text(row.get("competencia")),
        "data_missao": _as_iso_date_or_none(row.get("data_missao")),
        "data_final": _as_iso_date_or_none(row.get("data_final") or row.get("data_missao")),
        "cavok_numero_voo": _as_text(row.get("cavok_numero_voo")),
        "contratante": _as_text(row.get("contratante")),
        "chamado": _as_text(row.get("chamado")),
        "aeronave_id": _as_optional_int(row.get("aeronave_id")),
        "aeronave_nome": _as_text(row.get("aeronave_nome")),
        "categoria_financeira_aeronave": _as_text(row.get("categoria_financeira_aeronave")),
        "comandante_tripulante_id": _as_optional_int(row.get("comandante_tripulante_id")),
        "copiloto_tripulante_id": _as_optional_int(row.get("copiloto_tripulante_id")),
        "horario_apresentacao": _as_iso_datetime_or_none(row.get("horario_apresentacao")),
        "horario_abandono": _as_iso_datetime_or_none(row.get("horario_abandono")),
        "pos_exec_min": _as_int(row.get("pos_exec_min")),
        "trecho": _as_text(row.get("trecho")),
        "houve_pernoite": _as_bool(row.get("houve_pernoite")),
        "quantidade_pernoites": _as_int(row.get("quantidade_pernoites")),
        "cobertura_base": _as_bool(row.get("cobertura_base")),
        "operacao_especial": _as_text(row.get("operacao_especial")),
        "justificativa": _as_text(row.get("justificativa")),
        "status": _as_text(row.get("status")) or "rascunho",
        "observacoes": _as_text(row.get("observacoes")),
        "deleted_at": _as_iso_datetime_or_none(row.get("deleted_at")),
        "deleted_by": _as_optional_int(row.get("deleted_by")),
        "delete_reason": _empty_to_none(row.get("delete_reason")),
        "is_deleted": bool(row.get("deleted_at")),
        "links": _serialize_links(f"{FINANCE_API_ROUTE_PREFIX}/missoes", mission_id),
    }


def serialize_finance_mission_participant(row: dict) -> dict:
    return {
        "mission_id": _as_optional_int(row.get("mission_id")),
        "tripulante_id": _as_optional_int(row.get("tripulante_id")),
        "funcao": _as_text(row.get("funcao")),
        "hourly_bonus_calculation_id": _as_optional_int(row.get("hourly_bonus_calculation_id")),
        "calculation_status": _as_text(row.get("calculation_status")) or "pendente",
        "total_calculado": _as_decimal_text(row.get("total_calculado")),
        "calculation_version": _as_text(row.get("calculation_version")),
    }


def serialize_hourly_bonus_calculation(row: dict) -> dict:
    calculation_id = _as_optional_int(row.get("id"))
    mission_id = _as_optional_int(row.get("mission_id") or row.get("missao_operacional_id"))
    tripulante_id = _as_optional_int(row.get("tripulante_id"))
    return {
        "id": calculation_id,
        "org_id": _org_id(row),
        "competencia": _as_text(row.get("competencia")),
        "mission_id": mission_id,
        "missao_operacional_id": mission_id,
        "missao": {
            "id": mission_id,
            "data_missao": _as_iso_date_or_none(row.get("data_missao")),
            "data_final": _as_iso_date_or_none(row.get("data_final") or row.get("data_missao")),
            "cavok_numero_voo": _as_text(row.get("cavok_numero_voo")),
            "contratante": _as_text(row.get("contratante")),
            "chamado": _as_text(row.get("chamado")),
            "aeronave_id": _as_optional_int(row.get("aeronave_id")),
            "aeronave_nome": _as_text(row.get("aeronave_nome")),
            "categoria_financeira_aeronave": _as_text(row.get("categoria_financeira_aeronave")),
            "horario_apresentacao": _as_iso_datetime_or_none(row.get("horario_apresentacao")),
            "horario_abandono": _as_iso_datetime_or_none(row.get("horario_abandono")),
            "pos_exec_min": _as_int(row.get("pos_exec_min")),
            "trecho": _as_text(row.get("trecho")),
            "justificativa": _as_text(row.get("justificativa")),
            "operacao_especial": _as_text(row.get("operacao_especial")),
            "status": _as_text(row.get("missao_status")),
        },
        "tripulante_id": tripulante_id,
        "tripulante": {
            "id": tripulante_id,
            "nome": _as_text(row.get("tripulante_nome")),
            "cpf": _as_text(row.get("tripulante_cpf")),
            "codigo_anac": _as_text(row.get("tripulante_licenca_anac") or row.get("tripulante_codigo_anac")),
        },
        "funcao": _as_text(row.get("funcao")),
        "jornada_total_minutos": _as_int(row.get("jornada_total_minutos")),
        "minutos_diurnos": _as_int(row.get("minutos_diurnos")),
        "minutos_noturnos": _as_int(row.get("minutos_noturnos")),
        "minutos_noturnos_reais": _as_int(row.get("minutos_noturnos_reais", row.get("minutos_noturnos"))),
        "horas_noturnas_convertidas": _as_decimal_text(row.get("horas_noturnas_convertidas")),
        "minutos_pre": _as_int(row.get("minutos_pre")),
        "minutos_pos": _as_int(row.get("minutos_pos")),
        "domingo_feriado": _as_bool(row.get("domingo_feriado")),
        "valor_adicional_noturno": _as_decimal_text(row.get("valor_adicional_noturno")),
        "valor_domingo_feriado_diurno": _as_decimal_text(row.get("valor_domingo_feriado_diurno")),
        "valor_domingo_feriado_noturno": _as_decimal_text(row.get("valor_domingo_feriado_noturno")),
        "valor_pre": _as_decimal_text(row.get("valor_pre")),
        "valor_pos": _as_decimal_text(row.get("valor_pos")),
        "total": _as_decimal_text(row.get("total")),
        "status": _as_text(row.get("status")) or "calculado",
        "memoria_calculo": serialize_calculation_memory(row.get("memoria_calculo")),
        "calculation_version": _as_text(row.get("calculation_version")),
        "parametros_usados": [_serialize_parameter_reference(item) for item in row.get("parametros_usados", [])],
        "links": _serialize_links(f"{FINANCE_API_ROUTE_PREFIX}/bonificacoes/horaria", calculation_id),
    }


def serialize_productivity_bonus_calculation(row: dict) -> dict:
    calculation_id = _as_optional_int(row.get("id"))
    tripulante_id = _as_optional_int(row.get("tripulante_id"))
    memoria_calculo = serialize_calculation_memory(row.get("memoria_calculo"))
    excedente = row.get("excedente")
    if excedente in (None, ""):
        excedente = (memoria_calculo.get("totals") or {}).get("excedente")
    return {
        "id": calculation_id,
        "org_id": _org_id(row),
        "competencia": _as_text(row.get("competencia")),
        "tripulante_id": tripulante_id,
        "tripulante": {
            "id": tripulante_id,
            "nome": _as_text(row.get("tripulante_nome")),
            "cpf": _as_text(row.get("tripulante_cpf")),
            "codigo_anac": _as_text(row.get("tripulante_licenca_anac") or row.get("tripulante_codigo_anac")),
            "categoria_operacional": _as_text(row.get("tripulante_categoria_operacional")),
            "sdea_ativo": _as_bool(row.get("tripulante_sdea_ativo")),
            "sdea_icao_validade": _as_text(row.get("tripulante_sdea_icao_validade")),
            "instrutor_ativo": _as_bool(row.get("tripulante_instrutor_ativo")),
            "instrutor_inicio": _as_text(row.get("tripulante_instrutor_inicio")),
            "instrutor_fim": _as_text(row.get("tripulante_instrutor_fim")),
            "checador_ativo": _as_bool(row.get("tripulante_checador_ativo")),
            "checador_inicio": _as_text(row.get("tripulante_checador_inicio")),
            "checador_fim": _as_text(row.get("tripulante_checador_fim")),
            "checador_carta_designacao": _as_text(row.get("tripulante_checador_carta_designacao")),
        },
        "funcao": _as_text(row.get("funcao")),
        "categoria_aplicavel": _as_text(row.get("categoria_aplicavel")),
        "valor_icao": _as_decimal_text(row.get("valor_icao")),
        "valor_instrutor": _as_decimal_text(row.get("valor_instrutor")),
        "valor_checador": _as_decimal_text(row.get("valor_checador")),
        "valor_missoes_categoria_a": _as_decimal_text(row.get("valor_missoes_categoria_a")),
        "valor_missoes_categoria_b": _as_decimal_text(row.get("valor_missoes_categoria_b")),
        "valor_cobertura_base": _as_decimal_text(row.get("valor_cobertura_base")),
        "valor_pernoite_comum": _as_decimal_text(row.get("valor_pernoite_comum")),
        "valor_excecao_palmas": _as_decimal_text(row.get("valor_excecao_palmas")),
        "produtividade_calculada": _as_decimal_text(row.get("produtividade_calculada")),
        "garantia_minima": _as_decimal_text(row.get("garantia_minima")),
        "excedente": _as_decimal_text(excedente),
        "total_devido": _as_decimal_text(row.get("total_devido")),
        "status": _as_text(row.get("status")) or "calculado",
        "memoria_calculo": memoria_calculo,
        "calculation_version": _as_text(row.get("calculation_version")),
        "parametros_usados": [_serialize_parameter_reference(item) for item in row.get("parametros_usados", [])],
        "links": _serialize_links(f"{FINANCE_API_ROUTE_PREFIX}/bonificacoes/produtividade", tripulante_id),
    }


def serialize_finance_parameter(row: dict) -> dict:
    parameter_id = _as_optional_int(row.get("id"))
    return {
        "id": parameter_id,
        "org_id": _org_id(row),
        "tipo": _as_text(row.get("tipo")),
        "funcao": _empty_to_none(row.get("funcao")),
        "categoria": _empty_to_none(row.get("categoria")),
        "valor": _as_decimal_text(row.get("valor")),
        "unidade": _as_text(row.get("unidade")),
        "vigencia_inicio": _as_iso_date_or_none(row.get("vigencia_inicio")),
        "vigencia_fim": _as_iso_date_or_none(row.get("vigencia_fim")),
        "status": _as_text(row.get("status")) or "ativo",
        "motivo": _as_text(row.get("motivo")),
        "created_by": _as_optional_int(row.get("created_by")),
        "created_at": _as_iso_datetime_or_none(row.get("created_at")),
        "updated_by": _as_optional_int(row.get("updated_by")),
        "updated_at": _as_iso_datetime_or_none(row.get("updated_at")),
        "links": _serialize_links(f"{FINANCE_API_ROUTE_PREFIX}/parametros", parameter_id),
    }


def serialize_finance_holiday(row: dict) -> dict:
    holiday_id = _as_optional_int(row.get("id"))
    return {
        "id": holiday_id,
        "org_id": _org_id(row),
        "data": _as_iso_date_or_none(row.get("data")),
        "nome": _as_text(row.get("nome")),
        "tipo": _as_text(row.get("tipo")) or "nacional",
        "localidade": _empty_to_none(row.get("localidade")),
        "status": _as_text(row.get("status")) or "ativo",
        "created_by": _as_optional_int(row.get("created_by")),
        "created_at": _as_iso_datetime_or_none(row.get("created_at")),
        "updated_by": _as_optional_int(row.get("updated_by")),
        "updated_at": _as_iso_datetime_or_none(row.get("updated_at")),
        "links": _serialize_links(f"{FINANCE_API_ROUTE_PREFIX}/feriados", holiday_id),
    }


def serialize_finance_period(row: dict) -> dict:
    period_id = _as_optional_int(row.get("id"))
    return {
        "id": period_id,
        "org_id": _org_id(row),
        "competencia": _as_text(row.get("competencia")),
        "status": _as_text(row.get("status")) or "aberta",
        "totals": _nested_value(row.get("totals") or {}),
        "snapshot": _nested_value(row.get("snapshot")),
        "closed_by": _as_optional_int(row.get("closed_by")),
        "closed_at": _as_iso_datetime_or_none(row.get("closed_at")),
        "reopen_reason": _empty_to_none(row.get("reopen_reason")),
        "links": {
            "self": f"{FINANCE_API_ROUTE_PREFIX}/competencias/{_as_text(row.get('competencia'))}",
        },
    }


def serialize_finance_audit_event(row: dict) -> dict:
    return {
        "id": _as_optional_int(row.get("id")),
        "org_id": _org_id(row),
        "event_name": _as_text(row.get("event_name") or row.get("acao")),
        "entity_type": _as_text(row.get("entity_type") or row.get("entidade")),
        "entity_id": _as_optional_int(row.get("entity_id") if "entity_id" in row else row.get("entidade_id")),
        "competencia": _as_text(row.get("competencia")),
        "permission": _as_text(row.get("permission")),
        "actor_user_id": _as_optional_int(row.get("actor_user_id") if "actor_user_id" in row else row.get("realizado_por")),
        "before": _before_after(row, "before", "payload_anterior"),
        "after": _before_after(row, "after", "payload_novo"),
        "metadata": _nested_value(row.get("metadata") or {}),
        "created_at": _as_iso_datetime_or_none(row.get("created_at") or row.get("realizado_em")),
    }


def serialize_finance_divergence(row: dict) -> dict:
    divergence_id = _as_optional_int(row.get("id"))
    return {
        "id": divergence_id,
        "org_id": _org_id(row),
        "competencia": _as_text(row.get("competencia")),
        "severity": _as_text(row.get("severity")) or "media",
        "code": _as_text(row.get("code")),
        "message": _as_text(row.get("message")),
        "entity_type": _as_text(row.get("entity_type")),
        "entity_id": _as_optional_int(row.get("entity_id")),
        "mission_id": _as_optional_int(row.get("mission_id")),
        "tripulante_id": _as_optional_int(row.get("tripulante_id")),
        "status": _as_text(row.get("status")) or "aberta",
        "metadata": _nested_value(row.get("metadata") or {}),
        "detected_at": _as_iso_datetime_or_none(row.get("detected_at")),
    }


def serialize_finance_mission_collection(*, items: list[dict], page: int, offset: int, total: int) -> dict:
    return {
        "items": [serialize_finance_mission(item) for item in items],
        "pagination": {
            "page": int(page),
            "offset": int(offset),
            "total": int(total),
        },
    }


def finance_api_paths() -> tuple[str, ...]:
    paths: list[str] = []
    for resource in FINANCE_API_CONTRACT["resources"].values():
        paths.extend(resource["canonical_paths"])
    return tuple(paths)


def finance_stub_api_paths() -> tuple[str, ...]:
    return FINANCE_STUB_API_PATHS


def future_api_paths() -> tuple[str, ...]:
    return finance_api_paths()
