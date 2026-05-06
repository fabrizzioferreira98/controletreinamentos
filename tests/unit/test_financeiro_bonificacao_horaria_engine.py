from __future__ import annotations

import ast
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from backend.src.controle_treinamentos.application.financeiro_bonificacao_horaria import (
    ParametroBonificacaoHorariaAusenteErro,
    ParametroBonificacaoHorariaNaoElegivelErro,
    calcular_bonificacao_horaria,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ENGINE_FILE = (
    REPO_ROOT
    / "backend"
    / "src"
    / "controle_treinamentos"
    / "application"
    / "financeiro_bonificacao_horaria.py"
)


def _mission(**overrides):
    payload = {
        "id": 101,
        "org_id": "default_single_tenant",
        "competencia": "2026-04",
        "data_missao": "2026-04-29",
        "horario_apresentacao": "2026-04-29T08:00:00",
        "horario_abandono": "2026-04-29T18:00:00",
    }
    payload.update(overrides)
    return payload


def _participant(funcao="comandante", tripulante_id=11):
    return {
        "mission_id": 101,
        "tripulante_id": tripulante_id,
        "funcao": funcao,
    }


def _param(tipo, valor, *, funcao=None, unidade="valor", parameter_id=1, status="ativo", motivo=""):
    return {
        "id": parameter_id,
        "tipo": tipo,
        "funcao": funcao,
        "categoria": None,
        "valor": valor,
        "unidade": unidade,
        "status": status,
        "motivo": motivo,
        "vigencia_inicio": date(2026, 4, 1),
        "vigencia_fim": None,
    }


def _params():
    return [
        _param("duracao_hora_noturna_minutos", "52.5", unidade="minutos", parameter_id=1),
        _param("periodo_diurno_inicio", "360", unidade="minutos_do_dia", parameter_id=2),
        _param("periodo_diurno_fim", "1080", unidade="minutos_do_dia", parameter_id=3),
        _param("adicional_noturno", "100", funcao="comandante", parameter_id=4),
        _param("domingo_feriado_diurno", "300", funcao="comandante", parameter_id=5),
        _param("domingo_feriado_noturno", "400", funcao="comandante", parameter_id=6),
        _param("adicional_noturno", "80", funcao="copiloto", parameter_id=7),
        _param("domingo_feriado_diurno", "200", funcao="copiloto", parameter_id=8),
        _param("domingo_feriado_noturno", "250", funcao="copiloto", parameter_id=9),
    ]


def _calculate(mission=None, participant=None, params=None, **kwargs):
    return calcular_bonificacao_horaria(
        missao_operacional=mission or _mission(),
        participante=participant or _participant(),
        parametros_vigentes=params or _params(),
        **kwargs,
    )


def test_engine_is_pure_python_without_flask_db_repository_audit_or_frontend_imports():
    tree = ast.parse(ENGINE_FILE.read_text(encoding="utf-8"), filename=str(ENGINE_FILE))
    violations = []
    forbidden = ("flask", "psycopg2", "sqlalchemy", "db", "repositories", "audit", "frontend")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            candidates = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            candidates = [module, *(f"{module}.{alias.name}" for alias in node.names)]
        else:
            continue
        for candidate in candidates:
            if any(part in candidate.split(".") for part in forbidden):
                violations.append(f"{node.lineno}: {candidate}")

    assert violations == []


def test_jornada_diurna_sem_domingo_feriado_nao_gera_valor():
    result = _calculate()

    assert result["jornada_total_minutos"] == 600
    assert result["minutos_diurnos"] == 600
    assert result["minutos_noturnos_reais"] == 0
    assert result["horas_noturnas_convertidas"] == Decimal("0.0000")
    assert result["domingo_feriado"] is False
    assert result["total"] == Decimal("0.00")


def test_pos_exec_min_persistido_entra_no_motor_horario_sem_estouro_nao_inventa_valor():
    result = _calculate(_mission(pos_exec_min=25))

    assert result["minutos_pos"] == 0
    assert result["valor_pos"] == Decimal("0.00")
    assert result["total"] == Decimal("0.00")
    assert result["memoria_calculo"]["inputs"]["pos_exec_min"] == 25
    pre_pos_step = next(step for step in result["memoria_calculo"]["steps"] if step["rule_key"] == "pre_pos_jornada")
    assert pre_pos_step["resultado_intermediario"]["minutos_pos"] == 0


def test_estouro_de_jornada_entra_no_pos_calculo_e_altera_valor_total():
    params = [
        *_params()[:3],
        _param("adicional_noturno", "92.18", funcao="comandante", parameter_id=4),
        _param("domingo_feriado_diurno", "92.18", funcao="comandante", parameter_id=5),
        _param("domingo_feriado_noturno", "184.36", funcao="comandante", parameter_id=6),
        *_params()[6:],
    ]
    result = _calculate(
        _mission(
            data_missao="2026-04-04",
            horario_apresentacao="2026-04-04T06:15:00",
            horario_abandono="2026-04-04T19:30:00",
        ),
        _participant("comandante", 91),
        params,
    )

    assert result["jornada_total_minutos"] == 795
    assert result["minutos_diurnos"] == 705
    assert result["minutos_noturnos_reais"] == 90
    assert result["minutos_pos"] == 165
    assert result["horas_noturnas_convertidas"] == Decimal("4.8571")
    assert result["valor_adicional_noturno"] == Decimal("158.02")
    assert result["valor_pos"] == Decimal("289.71")
    assert result["total"] == Decimal("447.73")


def test_pos_exec_min_negativo_bloqueia_calculo_horario():
    with pytest.raises(Exception) as exc_info:
        _calculate(_mission(pos_exec_min=-1))

    assert getattr(exc_info.value, "code", "") == "bonificacao_horaria_pos_exec_min_invalido"


def test_jornada_noturna_usa_hora_noturna_de_52_5_e_nao_60():
    result = _calculate(
        _mission(
            horario_apresentacao="2026-04-29T18:00:00",
            horario_abandono="2026-04-29T19:45:00",
        )
    )

    assert result["jornada_total_minutos"] == 105
    assert result["minutos_diurnos"] == 0
    assert result["minutos_noturnos_reais"] == 105
    assert result["horas_noturnas_convertidas"] == Decimal("2.0000")
    assert result["horas_noturnas_convertidas"] != Decimal("1.7500")
    assert result["valor_adicional_noturno"] == Decimal("200.00")
    assert result["total"] == Decimal("200.00")


def test_total_monetario_usa_hora_noturna_precisa_sem_perder_centavo_por_arredondamento_intermediario():
    params = [
        *_params()[:3],
        _param("adicional_noturno", "92.18", funcao="comandante", parameter_id=4),
        _param("domingo_feriado_diurno", "92.18", funcao="comandante", parameter_id=5),
        _param("domingo_feriado_noturno", "184.36", funcao="comandante", parameter_id=6),
        *_params()[6:],
    ]
    result = _calculate(
        _mission(
            data_missao="2026-04-01",
            horario_apresentacao="2026-04-01T12:15:00",
            horario_abandono="2026-04-01T19:10:00",
        ),
        _participant("comandante", 91),
        params,
    )

    assert result["minutos_noturnos_reais"] == 70
    assert result["horas_noturnas_convertidas"] == Decimal("1.3333")
    assert result["valor_adicional_noturno"] == Decimal("122.91")
    assert result["total"] == Decimal("122.91")


def test_total_domingo_feriado_noturno_tambem_usa_hora_noturna_precisa():
    params = [
        *_params()[:3],
        _param("adicional_noturno", "92.18", funcao="comandante", parameter_id=4),
        _param("domingo_feriado_diurno", "92.18", funcao="comandante", parameter_id=5),
        _param("domingo_feriado_noturno", "184.36", funcao="comandante", parameter_id=6),
        *_params()[6:],
    ]
    result = _calculate(
        _mission(
            data_missao="2026-05-03",
            horario_apresentacao="2026-05-03T18:00:00",
            horario_abandono="2026-05-03T19:10:00",
        ),
        _participant("comandante", 91),
        params,
    )

    assert result["domingo_feriado"] is True
    assert result["minutos_noturnos_reais"] == 70
    assert result["horas_noturnas_convertidas"] == Decimal("1.3333")
    assert result["valor_domingo_feriado_noturno"] == Decimal("245.81")
    assert result["total"] == Decimal("245.81")


def test_voo_20_04_cruzando_tiradentes_separa_normal_e_feriado_noturno():
    params = [
        *_params()[:3],
        _param("adicional_noturno", "92.18", funcao="comandante", parameter_id=4),
        _param("domingo_feriado_diurno", "92.18", funcao="comandante", parameter_id=5),
        _param("domingo_feriado_noturno", "184.36", funcao="comandante", parameter_id=6),
        *_params()[6:],
    ]
    result = _calculate(
        _mission(
            data_missao="2026-04-20",
            data_final="2026-04-21",
            horario_apresentacao="2026-04-20T18:30:00",
            horario_abandono="2026-04-21T04:30:00",
        ),
        _participant("comandante", 91),
        params,
        feriados=["2026-04-21"],
    )

    step = next(
        item
        for item in result["memoria_calculo"]["steps"]
        if item["rule_key"] == "separacao_diurno_noturno"
    )

    assert result["jornada_total_minutos"] == 600
    assert result["minutos_diurnos"] == 0
    assert result["minutos_noturnos_reais"] == 600
    fatias = step["resultado_intermediario"]["fatias"]
    assert sum(item["minutos_noturnos_reais"] for item in fatias if not item["especial"]) == 330
    assert sum(item["minutos_noturnos_reais"] for item in fatias if item["especial"]) == 270
    assert result["valor_adicional_noturno"] == Decimal("579.42")
    assert result["valor_domingo_feriado_noturno"] == Decimal("948.14")
    assert result["total"] == Decimal("1527.56")


def test_jornada_cruza_periodo_diurno_e_noturno():
    result = _calculate(
        _mission(
            horario_apresentacao="2026-04-29T21:00:00",
            horario_abandono="2026-04-29T23:00:00",
        )
    )

    assert result["jornada_total_minutos"] == 120
    assert result["minutos_diurnos"] == 0
    assert result["minutos_noturnos_reais"] == 120
    assert result["horas_noturnas_convertidas"] == Decimal("2.2857")
    assert result["valor_adicional_noturno"] == Decimal("228.57")


@pytest.mark.parametrize(
    ("start", "end", "diurnal_minutes", "night_minutes", "converted_hours"),
    [
        ("17:00", "19:00", 60, 60, Decimal("1.1429")),
        ("18:00", "19:00", 0, 60, Decimal("1.1429")),
        ("05:00", "07:00", 60, 60, Decimal("1.1429")),
        ("21:00", "23:00", 0, 120, Decimal("2.2857")),
        ("06:00", "18:00", 720, 0, Decimal("1.7143")),
        ("18:00", "06:00", 0, 720, Decimal("15.4286")),
    ],
)
def test_periodo_noturno_canonico_18_00_ate_06_00(
    start,
    end,
    diurnal_minutes,
    night_minutes,
    converted_hours,
):
    result = _calculate(_mission(horario_apresentacao=start, horario_abandono=end))

    assert result["minutos_diurnos"] == diurnal_minutes
    assert result["minutos_noturnos_reais"] == night_minutes
    assert result["horas_noturnas_convertidas"] == converted_hours


def test_jornada_cruza_periodo_noturno_para_diurno():
    result = _calculate(
        _mission(
            horario_apresentacao="2026-04-29T05:30:00",
            horario_abandono="2026-04-29T06:30:00",
        )
    )

    assert result["jornada_total_minutos"] == 60
    assert result["minutos_diurnos"] == 30
    assert result["minutos_noturnos_reais"] == 30
    assert result["horas_noturnas_convertidas"] == Decimal("0.5714")
    assert result["valor_adicional_noturno"] == Decimal("57.14")


def test_jornada_com_virada_de_dia():
    result = _calculate(
        _mission(
            horario_apresentacao="23:30",
            horario_abandono="01:15",
        )
    )

    assert result["jornada_total_minutos"] == 105
    assert result["minutos_diurnos"] == 0
    assert result["minutos_noturnos_reais"] == 105
    assert result["horas_noturnas_convertidas"] == Decimal("2.0000")


def test_data_final_define_abandono_hhmm_em_missao_multi_dia():
    result = _calculate(
        _mission(
            data_missao="2026-04-29",
            data_final="2026-04-30",
            horario_apresentacao="23:00",
            horario_abandono="01:00",
        )
    )

    assert result["memoria_calculo"]["inputs"]["data_final"] == "2026-04-30"
    assert result["memoria_calculo"]["inputs"]["horario_abandono"] == "2026-04-30T01:00:00"
    assert result["jornada_total_minutos"] == 120
    assert result["minutos_noturnos_reais"] == 120
    assert result["valor_adicional_noturno"] == Decimal("228.57")


def test_jornada_sabado_para_domingo_fatia_minutos_normais_e_especiais():
    result = _calculate(
        _mission(
            data_missao="2026-05-02",
            data_final="2026-05-03",
            horario_apresentacao="23:00",
            horario_abandono="07:00",
        )
    )

    assert result["domingo_feriado"] is True
    assert result["jornada_total_minutos"] == 480
    assert result["minutos_diurnos"] == 60
    assert result["minutos_noturnos_reais"] == 420
    assert result["valor_adicional_noturno"] == Decimal("114.29")
    assert result["valor_domingo_feriado_diurno"] == Decimal("300.00")
    assert result["valor_domingo_feriado_noturno"] == Decimal("2742.86")
    assert result["total"] == Decimal("3157.15")
    totals = result["memoria_calculo"]["totals"]
    assert totals["normal_minutos_noturnos"] == 60
    assert totals["especial_minutos_diurnos"] == 60
    assert totals["especial_minutos_noturnos"] == 360


def test_jornada_domingo_para_segunda_nao_trata_segunda_como_domingo():
    result = _calculate(
        _mission(
            data_missao="2026-05-03",
            data_final="2026-05-04",
            horario_apresentacao="23:00",
            horario_abandono="01:00",
        )
    )

    assert result["domingo_feriado"] is True
    assert result["minutos_noturnos_reais"] == 120
    assert result["valor_domingo_feriado_noturno"] == Decimal("457.14")
    assert result["valor_adicional_noturno"] == Decimal("114.29")
    assert result["total"] == Decimal("571.43")


def test_feriado_no_meio_da_jornada_aplica_especial_apenas_no_dia_feriado():
    result = _calculate(
        _mission(
            data_missao="2026-04-20",
            data_final="2026-04-21",
            horario_apresentacao="23:00",
            horario_abandono="01:00",
        ),
        feriados=["2026-04-21"],
    )

    assert result["domingo_feriado"] is True
    assert result["memoria_calculo"]["calendar_flags"]["feriado"] is True
    assert result["valor_adicional_noturno"] == Decimal("114.29")
    assert result["valor_domingo_feriado_noturno"] == Decimal("457.14")
    assert result["total"] == Decimal("571.43")


def test_domingo_diurno_aplica_parametro_de_domingo_feriado_diurno():
    result = _calculate(
        _mission(
            data_missao="2026-05-03",
            horario_apresentacao="2026-05-03T08:00:00",
            horario_abandono="2026-05-03T10:00:00",
        )
    )

    assert result["domingo_feriado"] is True
    assert result["minutos_diurnos"] == 120
    assert result["valor_adicional_noturno"] == Decimal("0")
    assert result["valor_domingo_feriado_diurno"] == Decimal("600.00")
    assert result["total"] == Decimal("600.00")


def test_domingo_noturno_aplica_parametro_de_domingo_feriado_noturno():
    result = _calculate(
        _mission(
            data_missao="2026-05-03",
            horario_apresentacao="2026-05-03T18:00:00",
            horario_abandono="2026-05-03T19:45:00",
        )
    )

    assert result["domingo_feriado"] is True
    assert result["horas_noturnas_convertidas"] == Decimal("2.0000")
    assert result["valor_adicional_noturno"] == Decimal("0")
    assert result["valor_domingo_feriado_noturno"] == Decimal("800.00")
    assert result["total"] == Decimal("800.00")


def test_feriado_explicito_aplica_regra_de_domingo_feriado():
    result = _calculate(
        _mission(
            data_missao="2026-04-21",
            horario_apresentacao="2026-04-21T08:00:00",
            horario_abandono="2026-04-21T09:00:00",
        ),
        feriado=True,
    )

    assert result["domingo_feriado"] is True
    assert result["valor_domingo_feriado_diurno"] == Decimal("300.00")
    assert result["total"] == Decimal("300.00")


def test_comandante_e_copiloto_usam_parametros_diferentes_por_funcao():
    mission = _mission(
        horario_apresentacao="2026-04-29T18:00:00",
        horario_abandono="2026-04-29T19:45:00",
    )
    comandante = _calculate(mission, _participant("comandante", 11))
    copiloto = _calculate(mission, _participant("copiloto", 12))

    assert comandante["valor_adicional_noturno"] == Decimal("200.00")
    assert copiloto["valor_adicional_noturno"] == Decimal("160.00")
    assert comandante["parametros_usados"][3]["funcao"] == "comandante"
    assert copiloto["parametros_usados"][3]["funcao"] == "copiloto"


def test_parametro_ausente_gera_erro_de_dominio():
    params = [param for param in _params() if param["tipo"] != "duracao_hora_noturna_minutos"]

    with pytest.raises(ParametroBonificacaoHorariaAusenteErro) as exc:
        _calculate(params=params)

    assert exc.value.code == "bonificacao_horaria_parametro_ausente"
    assert "duracao_hora_noturna_minutos" in exc.value.message


def test_parametro_global_com_funcao_preenchida_bloqueia_motor():
    params = [
        _param("duracao_hora_noturna_minutos", "52.5", funcao="comandante", unidade="minutos", parameter_id=1),
        *_params()[1:],
    ]

    with pytest.raises(ParametroBonificacaoHorariaNaoElegivelErro) as exc:
        _calculate(
            _mission(
                horario_apresentacao="2026-04-29T18:00:00",
                horario_abandono="2026-04-29T19:45:00",
            ),
            params=params,
        )

    assert exc.value.code == "bonificacao_horaria_parametro_nao_elegivel"
    blocked = {item["parameter_id"]: set(item["reasons"]) for item in exc.value.details["blocking_parameters"]}
    assert "funcao_invalida_para_tipo" in blocked[1]


def test_parametros_brl_antigos_bloqueiam_motor():
    old_smoke_params = [
        _param("adicional_noturno", "10", funcao="comandante", unidade="BRL", parameter_id=40),
        _param("domingo_feriado_diurno", "20", funcao="comandante", unidade="BRL", parameter_id=41),
        _param("domingo_feriado_noturno", "30", funcao="comandante", unidade="BRL", parameter_id=42),
    ]
    params = [
        _params()[0],
        _params()[1],
        _params()[2],
        *old_smoke_params,
        _param("adicional_noturno", "100", funcao="comandante", unidade="valor", parameter_id=18),
        _param("domingo_feriado_diurno", "300", funcao="comandante", unidade="valor", parameter_id=19),
        _param("domingo_feriado_noturno", "400", funcao="comandante", unidade="valor", parameter_id=20),
    ]

    with pytest.raises(ParametroBonificacaoHorariaNaoElegivelErro) as exc:
        _calculate(
            _mission(horario_apresentacao="2026-04-29T18:00:00", horario_abandono="2026-04-29T19:45:00"),
            params=params,
        )

    assert exc.value.code == "bonificacao_horaria_parametro_nao_elegivel"
    blocked = {item["parameter_id"]: set(item["reasons"]) for item in exc.value.details["blocking_parameters"]}
    assert "unidade_brl_legacy" in blocked[40]
    assert "unidade_brl_legacy" in blocked[41]
    assert "unidade_brl_legacy" in blocked[42]


def test_parametro_valor_duplicado_bloqueia_por_sobreposicao():
    params = [
        *_params(),
        _param("adicional_noturno", "101", funcao="comandante", unidade="valor", parameter_id=99),
    ]

    with pytest.raises(ParametroBonificacaoHorariaNaoElegivelErro) as exc:
        _calculate(
            _mission(horario_apresentacao="2026-04-29T18:00:00", horario_abandono="2026-04-29T19:45:00"),
            params=params,
        )

    assert exc.value.code == "bonificacao_horaria_parametro_nao_elegivel"
    blocked = {item["parameter_id"]: set(item["reasons"]) for item in exc.value.details["blocking_parameters"]}
    assert "sobreposicao_semantica_ativa" in blocked[4]
    assert "sobreposicao_semantica_ativa" in blocked[99]


def test_periodo_diurno_deve_usar_minutos_do_dia_no_motor():
    params = [
        _param("periodo_diurno_inicio", "06:00", unidade="horario", parameter_id=2)
        if param["tipo"] == "periodo_diurno_inicio"
        else param
        for param in _params()
    ]

    with pytest.raises(ParametroBonificacaoHorariaNaoElegivelErro) as exc:
        _calculate(params=params)

    assert exc.value.code == "bonificacao_horaria_parametro_nao_elegivel"
    blocked = {item["parameter_id"]: set(item["reasons"]) for item in exc.value.details["blocking_parameters"]}
    assert "unidade_invalida_para_tipo" in blocked[2]


def test_real_closure_com_release_candidate_permite_calculo():
    params = [{**item, "motivo": "GOV_CLASS=hml-release-candidate"} for item in _params()]

    result = _calculate(
        _mission(horario_apresentacao="2026-04-29T18:00:00", horario_abandono="2026-04-29T19:45:00"),
        params=params,
        real_closure=True,
        release_environment="hml",
    )

    assert result["total"] == Decimal("200.00")


def test_real_closure_bloqueia_qa_smoke():
    params = []
    for item in _params():
        reason = "GOV_CLASS=hml-release-candidate"
        if item["id"] == 4:
            reason = "GOV_CLASS=qa-smoke"
        params.append({**item, "motivo": reason})

    with pytest.raises(ParametroBonificacaoHorariaNaoElegivelErro) as exc:
        _calculate(
            _mission(horario_apresentacao="2026-04-29T18:00:00", horario_abandono="2026-04-29T19:45:00"),
            params=params,
            real_closure=True,
            release_environment="hml",
        )

    assert exc.value.code == "bonificacao_horaria_parametro_nao_elegivel"
    blocked = {item["parameter_id"]: set(item["reasons"]) for item in exc.value.details["blocking_parameters"]}
    assert "classificacao_qa_smoke_bloqueada" in blocked[4]


def test_memoria_de_calculo_contem_entradas_formulas_parametros_e_resultados():
    result = _calculate(
        _mission(
            horario_apresentacao=datetime(2026, 4, 29, 17, 0),
            horario_abandono=datetime(2026, 4, 29, 19, 0),
        )
    )
    memory = result["memoria_calculo"]

    assert memory["calculation_version"] == "finance-hourly-v1"
    assert memory["source"]["type"] == "finance_mission_operational"
    assert memory["participant"] == {"tripulante_id": 11, "funcao": "comandante"}
    assert memory["inputs"]["horario_apresentacao"] == "2026-04-29T17:00:00"
    assert len(memory["parameters"]) == 6
    assert memory["calendar_flags"]["domingo_feriado"] is False
    assert {step["rule_key"] for step in memory["steps"]} >= {
        "jornada_total",
        "separacao_diurno_noturno",
        "conversao_hora_noturna",
        "adicional_aplicavel",
        "pre_pos_jornada",
    }
    conversion_step = next(step for step in memory["steps"] if step["rule_key"] == "conversao_hora_noturna")
    assert "duracao_hora_noturna_minutos" in conversion_step["formula_conceitual"]
    assert conversion_step["parametro_usado"]["valor"] == "52.5"
    assert conversion_step["resultado_final"]["horas_noturnas_convertidas"] == "1.1429"
    separation_step = next(step for step in memory["steps"] if step["rule_key"] == "separacao_diurno_noturno")
    assert separation_step["entrada_usada"]["periodo_diurno_inicio"] == {
        "minutos_do_dia": 360,
        "display_value": "06:00",
    }
    assert separation_step["entrada_usada"]["periodo_diurno_fim"] == {
        "minutos_do_dia": 1080,
        "display_value": "18:00",
    }
    period_parameters = {
        item["tipo"]: item
        for item in memory["parameters"]
        if item["tipo"] in {"periodo_diurno_inicio", "periodo_diurno_fim"}
    }
    assert period_parameters["periodo_diurno_inicio"]["valor"] == "360"
    assert period_parameters["periodo_diurno_inicio"]["unidade"] == "minutos_do_dia"
    assert period_parameters["periodo_diurno_inicio"]["display_value"] == "06:00"
    assert period_parameters["periodo_diurno_fim"]["valor"] == "1080"
    assert period_parameters["periodo_diurno_fim"]["display_value"] == "18:00"
    assert memory["totals"]["total"] == "114.29"

