from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from backend.src.controle_treinamentos.contracts.financeiro import (
    FINANCE_CREW_FUNCTIONS,
    FINANCE_DIVERGENCE_SEVERITIES,
    FINANCE_ORG_SCOPE_DEFAULT,
    FINANCE_PARAMETER_TYPES,
    finance_api_paths,
    serialize_calculation_memory,
    serialize_finance_audit_event,
    serialize_finance_divergence,
    serialize_finance_holiday,
    serialize_finance_mission,
    serialize_finance_mission_collection,
    serialize_finance_mission_participant,
    serialize_finance_parameter,
    serialize_finance_period,
    serialize_hourly_bonus_calculation,
    serialize_productivity_bonus_calculation,
)


def _sample_memory() -> dict:
    return {
        "calculation_version": "finance-v1",
        "competencia": "2026-04",
        "source": {"type": "finance_mission", "id": 101},
        "participant": {"tripulante_id": 11, "funcao": "comandante"},
        "inputs": {
            "mission_id": 101,
            "horario_apresentacao": datetime(2026, 4, 29, 8, 0),
            "horario_abandono": datetime(2026, 4, 29, 18, 30),
        },
        "parameters": [
            {
                "id": 501,
                "tipo": "adicional_noturno",
                "funcao": "comandante",
                "categoria": "categoria a",
                "valor": Decimal("120.50"),
                "unidade": "BRL",
                "vigencia_inicio": date(2026, 4, 1),
                "vigencia_fim": None,
                "applied_at": datetime(2026, 4, 29, 12, 0),
            }
        ],
        "calendar_flags": {"domingo": False, "feriado": True, "noturno": True},
        "steps": [
            {
                "rule_key": "adicional_noturno",
                "rule_label": "Adicional noturno",
                "entrada_usada": {"minutos_noturnos": 60},
                "parametro_usado": {
                    "parameter_id": 501,
                    "tipo": "adicional_noturno",
                    "funcao": "comandante",
                    "categoria": "categoria a",
                    "valor": Decimal("120.50"),
                    "unidade": "BRL",
                    "vigencia_inicio": date(2026, 4, 1),
                },
                "formula_conceitual": "minutos_noturnos convertidos por parametro vigente",
                "resultado_intermediario": {"horas": Decimal("1.0")},
                "resultado_final": {"valor": Decimal("120.50")},
                "notes": ["calculo pelo backend"],
            }
        ],
        "totals": {"total": Decimal("120.50")},
        "warnings": [{"code": "holiday_detected"}],
        "generated_at": datetime(2026, 4, 29, 12, 5),
    }


def test_serialize_finance_mission_preserves_unique_mission_hours_and_tripulante_ids():
    payload = serialize_finance_mission(
        {
            "id": 101,
            "competencia": "2026-04",
            "data_missao": date(2026, 4, 29),
            "data_final": date(2026, 4, 30),
            "cavok_numero_voo": "CAVOK-123",
            "contratante": "Cliente",
            "chamado": "CH-123",
            "aeronave_id": 7,
            "categoria_financeira_aeronave": "categoria_a",
            "comandante_tripulante_id": 11,
            "copiloto_tripulante_id": 12,
            "horario_apresentacao": datetime(2026, 4, 29, 8, 0),
            "horario_abandono": datetime(2026, 4, 29, 18, 30),
            "pos_exec_min": 20,
            "trecho": "SBSP-SBRJ",
            "houve_pernoite": True,
            "quantidade_pernoites": 1,
            "cobertura_base": False,
            "operacao_especial": "Palmas turboélice",
            "justificativa": "Excecao operacional documentada",
            "status": "ativa",
            "observacoes": "Registro operacional",
            "comandante_horario_apresentacao": "nao deve vazar",
            "copiloto_horario_abandono": "nao deve vazar",
            "comandante_nome": "nao duplica cadastro",
            "copiloto_cpf": "nao duplica cadastro",
        }
    )

    assert payload["org_id"] == FINANCE_ORG_SCOPE_DEFAULT
    assert payload["comandante_tripulante_id"] == 11
    assert payload["copiloto_tripulante_id"] == 12
    assert payload["horario_apresentacao"] == "2026-04-29T08:00:00"
    assert payload["horario_abandono"] == "2026-04-29T18:30:00"
    assert payload["data_final"] == "2026-04-30"
    assert payload["pos_exec_min"] == 20
    assert payload["operacao_especial"] == "Palmas turboélice"
    assert payload["justificativa"] == "Excecao operacional documentada"
    assert payload["links"]["self"] == "/api/v1/financeiro/missoes/101"
    assert "comandante_horario_apresentacao" not in payload
    assert "copiloto_horario_abandono" not in payload
    assert "comandante_nome" not in payload
    assert "copiloto_cpf" not in payload


def test_serialize_finance_mission_participant_has_no_participant_hours():
    payload = serialize_finance_mission_participant(
        {
            "mission_id": 101,
            "tripulante_id": 11,
            "funcao": "comandante",
            "hourly_bonus_calculation_id": 900,
            "calculation_status": "calculado",
            "total_calculado": Decimal("350.75"),
            "calculation_version": "finance-v1",
            "horario_apresentacao": "nao pertence ao participante",
            "horario_abandono": "nao pertence ao participante",
        }
    )

    assert payload == {
        "mission_id": 101,
        "tripulante_id": 11,
        "funcao": "comandante",
        "hourly_bonus_calculation_id": 900,
        "calculation_status": "calculado",
        "total_calculado": "350.75",
        "calculation_version": "finance-v1",
    }


def test_serialize_hourly_bonus_calculation_is_participant_scoped():
    payload = serialize_hourly_bonus_calculation(
        {
            "id": 900,
            "mission_id": 101,
            "tripulante_id": 11,
            "funcao": "comandante",
            "jornada_total_minutos": 630,
            "minutos_diurnos": 570,
            "minutos_noturnos": 60,
            "horas_noturnas_convertidas": Decimal("1.142857"),
            "minutos_pre": 30,
            "minutos_pos": 20,
            "domingo_feriado": True,
            "valor_adicional_noturno": Decimal("120.50"),
            "valor_domingo_feriado_diurno": Decimal("80.00"),
            "valor_domingo_feriado_noturno": Decimal("40.00"),
            "valor_pre": Decimal("25.00"),
            "valor_pos": Decimal("15.00"),
            "total": Decimal("280.50"),
            "memoria_calculo": _sample_memory(),
            "calculation_version": "finance-v1",
            "parametros_usados": _sample_memory()["parameters"],
        }
    )

    assert payload["org_id"] == FINANCE_ORG_SCOPE_DEFAULT
    assert payload["mission_id"] == 101
    assert payload["tripulante_id"] == 11
    assert payload["funcao"] == "comandante"
    assert payload["total"] == "280.50"
    assert payload["memoria_calculo"]["steps"][0]["rule_key"] == "adicional_noturno"
    assert payload["parametros_usados"][0]["parameter_id"] == 501


def test_serialize_productivity_bonus_calculation_is_competencia_and_tripulante_scoped():
    payload = serialize_productivity_bonus_calculation(
        {
            "id": 910,
            "competencia": "2026-04",
            "tripulante_id": 11,
            "funcao": "comandante",
            "categoria_aplicavel": "categoria a",
            "valor_icao": Decimal("10"),
            "valor_instrutor": Decimal("20"),
            "valor_checador": Decimal("30"),
            "valor_missoes_categoria_a": Decimal("400"),
            "valor_missoes_categoria_b": Decimal("0"),
            "valor_cobertura_base": Decimal("50"),
            "valor_pernoite_comum": Decimal("80"),
            "valor_excecao_palmas": Decimal("0"),
            "produtividade_calculada": Decimal("510"),
            "garantia_minima": Decimal("700"),
            "total_devido": Decimal("700"),
            "memoria_calculo": _sample_memory(),
            "parametros_usados": _sample_memory()["parameters"],
        }
    )

    assert payload["org_id"] == FINANCE_ORG_SCOPE_DEFAULT
    assert payload["competencia"] == "2026-04"
    assert payload["tripulante_id"] == 11
    assert payload["total_devido"] == "700"
    assert payload["valor_pernoite_comum"] == "80"
    assert payload["memoria_calculo"]["participant"]["tripulante_id"] == 11


def test_serialize_finance_parameter_requires_vigencia_contract_fields():
    payload = serialize_finance_parameter(
        {
            "id": 501,
            "tipo": "garantia_minima",
            "funcao": "comandante",
            "categoria": "categoria a",
            "valor": Decimal("700.00"),
            "unidade": "BRL",
            "vigencia_inicio": date(2026, 4, 1),
            "vigencia_fim": date(2026, 12, 31),
            "status": "ativo",
            "motivo": "Parametro aprovado",
            "created_by": 3,
            "created_at": datetime(2026, 4, 1, 9, 0),
            "updated_by": 4,
            "updated_at": datetime(2026, 4, 2, 10, 0),
        }
    )

    assert payload["org_id"] == FINANCE_ORG_SCOPE_DEFAULT
    assert payload["tipo"] == "garantia_minima"
    assert payload["valor"] == "700.00"
    assert payload["vigencia_inicio"] == "2026-04-01"
    assert payload["vigencia_fim"] == "2026-12-31"
    assert payload["updated_by"] == 4
    assert payload["updated_at"] == "2026-04-02T10:00:00"
    assert payload["links"]["self"] == "/api/v1/financeiro/parametros/501"


def test_serialize_finance_holiday_is_national_calendar_contract():
    payload = serialize_finance_holiday(
        {
            "id": 601,
            "data": date(2026, 4, 21),
            "nome": "Tiradentes",
            "tipo": "nacional",
            "localidade": None,
            "status": "ativo",
            "created_by": 3,
            "created_at": datetime(2026, 4, 1, 9, 0),
            "updated_by": 4,
            "updated_at": datetime(2026, 4, 2, 10, 0),
        }
    )

    assert payload["org_id"] == FINANCE_ORG_SCOPE_DEFAULT
    assert payload["data"] == "2026-04-21"
    assert payload["tipo"] == "nacional"
    assert payload["localidade"] is None
    assert payload["links"]["self"] == "/api/v1/financeiro/feriados/601"


def test_serialize_finance_period_contains_status_totals_and_snapshot():
    payload = serialize_finance_period(
        {
            "competencia": "2026-04",
            "status": "fechada",
            "totals": {"total_devido": Decimal("980.50")},
            "snapshot": {
                "mission_ids": [101],
                "participants": [{"tripulante_id": 11, "funcao": "comandante"}],
                "calculation_version": "finance-v1",
            },
            "closed_by": 3,
            "closed_at": datetime(2026, 4, 30, 18, 0),
            "reopen_reason": "",
        }
    )

    assert payload["org_id"] == FINANCE_ORG_SCOPE_DEFAULT
    assert payload["status"] == "fechada"
    assert payload["totals"]["total_devido"] == "980.50"
    assert payload["snapshot"]["mission_ids"] == [101]
    assert payload["closed_at"] == "2026-04-30T18:00:00"
    assert payload["reopen_reason"] is None


def test_serialize_calculation_memory_keeps_clear_serializable_structure():
    payload = serialize_calculation_memory(_sample_memory())

    assert payload["org_id"] == FINANCE_ORG_SCOPE_DEFAULT
    assert payload["calculation_version"] == "finance-v1"
    assert payload["inputs"]["horario_apresentacao"] == "2026-04-29T08:00:00"
    assert payload["parameters"][0]["valor"] == "120.50"
    assert payload["steps"][0]["formula_conceitual"] == "minutos_noturnos convertidos por parametro vigente"
    assert payload["steps"][0]["resultado_final"]["valor"] == "120.50"
    assert payload["totals"]["total"] == "120.50"


def test_serialize_finance_audit_event_maps_current_audit_shape_to_finance_contract():
    payload = serialize_finance_audit_event(
        {
            "id": 77,
            "acao": "finance.period.closed",
            "entidade": "finance_period",
            "entidade_id": 202604,
            "realizado_por": 3,
            "payload_anterior": {"status": "em_conferencia"},
            "payload_novo": {"status": "fechada", "snapshot_id": 55},
            "metadata": {"permission": "finance:periods:close"},
            "realizado_em": datetime(2026, 4, 30, 18, 0),
        }
    )

    assert payload["org_id"] == FINANCE_ORG_SCOPE_DEFAULT
    assert payload["event_name"] == "finance.period.closed"
    assert payload["entity_type"] == "finance_period"
    assert payload["entity_id"] == 202604
    assert payload["actor_user_id"] == 3
    assert payload["before"]["status"] == "em_conferencia"
    assert payload["after"]["snapshot_id"] == 55


def test_serialize_finance_divergence_contract():
    payload = serialize_finance_divergence(
        {
            "id": 8,
            "competencia": "2026-04",
            "severity": "bloqueante",
            "code": "missing_parameter",
            "message": "Parametro vigente nao encontrado.",
            "entity_type": "finance_mission",
            "entity_id": 101,
            "mission_id": 101,
            "tripulante_id": 11,
            "status": "aberta",
            "metadata": {"tipo": "adicional_noturno"},
            "detected_at": datetime(2026, 4, 29, 13, 0),
        }
    )

    assert payload["org_id"] == FINANCE_ORG_SCOPE_DEFAULT
    assert payload["severity"] == "bloqueante"
    assert payload["mission_id"] == 101
    assert payload["tripulante_id"] == 11
    assert payload["metadata"]["tipo"] == "adicional_noturno"


def test_finance_collection_and_future_paths_are_declared_without_routes():
    collection = serialize_finance_mission_collection(
        items=[{"id": 101, "comandante_tripulante_id": 11, "copiloto_tripulante_id": 12}],
        page=1,
        offset=0,
        total=1,
    )

    assert collection["pagination"] == {"page": 1, "offset": 0, "total": 1}
    assert collection["items"][0]["org_id"] == FINANCE_ORG_SCOPE_DEFAULT
    assert "/api/v1/financeiro/missoes" in finance_api_paths()
    assert "/api/v1/financeiro/competencias/<competencia>/fechar" in finance_api_paths()


def test_finance_constants_cover_domain_options():
    assert FINANCE_ORG_SCOPE_DEFAULT == "default_single_tenant"
    assert FINANCE_CREW_FUNCTIONS == ("comandante", "copiloto")
    assert "duracao_hora_noturna_minutos" in FINANCE_PARAMETER_TYPES
    assert "garantia_minima" in FINANCE_PARAMETER_TYPES
    assert "bloqueante" in FINANCE_DIVERGENCE_SEVERITIES


