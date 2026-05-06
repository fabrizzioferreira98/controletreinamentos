from __future__ import annotations

import ast
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from backend.src.controle_treinamentos.application.financeiro_bonificacao_produtividade import (
    ParametroBonificacaoProdutividadeAusenteErro,
    ParametroBonificacaoProdutividadeNaoElegivelErro,
    calcular_bonificacao_produtividade,
)
from backend.src.controle_treinamentos.application.financeiro_categorias import (
    CANONICAL_CATEGORY_A,
    CANONICAL_CATEGORY_B,
    normalizar_categoria_operacional,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ENGINE_FILE = (
    REPO_ROOT
    / "backend"
    / "src"
    / "controle_treinamentos"
    / "application"
    / "financeiro_bonificacao_produtividade.py"
)


def _tripulante(**overrides):
    payload = {
        "id": 101,
        "org_id": "default_single_tenant",
        "categoria_operacional": "A",
        "sdea_ativo": False,
        "instrutor_ativo": False,
        "checador_ativo": False,
    }
    payload.update(overrides)
    return payload


def _mission(**overrides):
    payload = {
        "id": 10,
        "competencia": "2026-04",
        "categoria_financeira_aeronave": "a",
        "cobertura_base": False,
        "operacao_especial": "",
    }
    payload.update(overrides)
    return payload


def _param(tipo, valor, *, funcao=None, categoria=None, unidade="valor", parameter_id=1, status="ativo", motivo=""):
    return {
        "id": parameter_id,
        "tipo": tipo,
        "funcao": funcao,
        "categoria": categoria,
        "valor": valor,
        "unidade": unidade,
        "status": status,
        "motivo": motivo,
        "vigencia_inicio": date(2026, 4, 1),
        "vigencia_fim": None,
    }


def _params(**overrides):
    values = {
        "icao_sdea_comandante": "300",
        "icao_sdea_copiloto": "150",
        "instrutor": "300",
        "checador": "300",
        "missao_categoria_a_comandante": "300",
        "missao_categoria_a_copiloto": "150",
        "missao_categoria_b_comandante": "600",
        "missao_categoria_b_copiloto": "300",
        "cobertura_base_comandante": "200",
        "cobertura_base_copiloto": "100",
        "pernoite_comum_sem_cobertura_comandante": None,
        "pernoite_comum_sem_cobertura_copiloto": None,
        "excecao_palmas_turbohelice_comandante": "5000",
        "excecao_palmas_turbohelice_copiloto": "2500",
        "garantia_minima": "3000",
        "garantia_minima_a_comandante": None,
        "garantia_minima_a_copiloto": "1500",
        "garantia_minima_b_comandante": "6000",
        "garantia_minima_b_copiloto": "3000",
    }
    values.update(overrides)
    garantia_a_comandante = values["garantia_minima_a_comandante"] or values["garantia_minima"]
    params = [
        _param("icao_sdea", values["icao_sdea_comandante"], funcao="comandante", parameter_id=1),
        _param("icao_sdea", values["icao_sdea_copiloto"], funcao="copiloto", parameter_id=2),
        _param("instrutor", values["instrutor"], parameter_id=3),
        _param("checador", values["checador"], parameter_id=4),
        _param(
            "missao_categoria_a",
            values["missao_categoria_a_comandante"],
            funcao="comandante",
            categoria="categoria a",
            parameter_id=5,
        ),
        _param(
            "missao_categoria_a",
            values["missao_categoria_a_copiloto"],
            funcao="copiloto",
            categoria="categoria a",
            parameter_id=6,
        ),
        _param(
            "missao_categoria_b",
            values["missao_categoria_b_comandante"],
            funcao="comandante",
            categoria="categoria b",
            parameter_id=7,
        ),
        _param(
            "missao_categoria_b",
            values["missao_categoria_b_copiloto"],
            funcao="copiloto",
            categoria="categoria b",
            parameter_id=8,
        ),
        _param("cobertura_base", values["cobertura_base_comandante"], funcao="comandante", parameter_id=9),
        _param("cobertura_base", values["cobertura_base_copiloto"], funcao="copiloto", parameter_id=10),
        _param(
            "excecao_palmas_turbohelice",
            values["excecao_palmas_turbohelice_comandante"],
            funcao="comandante",
            categoria="turbohelice_palmas",
            parameter_id=11,
        ),
        _param(
            "excecao_palmas_turbohelice",
            values["excecao_palmas_turbohelice_copiloto"],
            funcao="copiloto",
            categoria="turbohelice_palmas",
            parameter_id=12,
        ),
        _param(
            "garantia_minima",
            garantia_a_comandante,
            funcao="comandante",
            categoria="categoria a",
            parameter_id=13,
        ),
        _param(
            "garantia_minima",
            values["garantia_minima_a_copiloto"],
            funcao="copiloto",
            categoria="categoria a",
            parameter_id=14,
        ),
        _param(
            "garantia_minima",
            values["garantia_minima_b_comandante"],
            funcao="comandante",
            categoria="categoria b",
            parameter_id=15,
        ),
        _param(
            "garantia_minima",
            values["garantia_minima_b_copiloto"],
            funcao="copiloto",
            categoria="categoria b",
            parameter_id=16,
        ),
    ]
    if values["pernoite_comum_sem_cobertura_comandante"] is not None:
        params.append(
            _param(
                "pernoite_comum_sem_cobertura",
                values["pernoite_comum_sem_cobertura_comandante"],
                funcao="comandante",
                parameter_id=17,
            )
        )
    if values["pernoite_comum_sem_cobertura_copiloto"] is not None:
        params.append(
            _param(
                "pernoite_comum_sem_cobertura",
                values["pernoite_comum_sem_cobertura_copiloto"],
                funcao="copiloto",
                parameter_id=18,
            )
        )
    return params


def _calculate(tripulante=None, missions=None, params=None, funcao="comandante", **kwargs):
    return calcular_bonificacao_produtividade(
        competencia="2026-04",
        tripulante=tripulante or _tripulante(),
        funcao=funcao,
        missoes_operacionais=missions if missions is not None else [_mission()],
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


def test_icao_sdea_flag_aplica_parametro_icao_sdea():
    result = _calculate(
        _tripulante(sdea_ativo=True, sdea_icao_validade=date(2026, 4, 30)),
        params=_params(garantia_minima="0"),
    )

    assert result["valor_icao"] == Decimal("300.00")
    assert result["produtividade_calculada"] == Decimal("600.00")
    assert result["parametros_usados"][0]["tipo"] == "icao_sdea"


def test_icao_sdea_ativo_sem_validade_explicita_conta_como_vigencia_aberta():
    result = _calculate(
        _tripulante(sdea_ativo=True, sdea_icao_validade=None),
        missions=[_mission(categoria_financeira_aeronave="a")],
        params=_params(garantia_minima="0", missao_categoria_a_comandante="0"),
    )

    assert result["valor_icao"] == Decimal("300.00")
    assert result["produtividade_calculada"] == Decimal("300.00")
    flags = result["memoria_calculo"]["inputs"]["flags_operacionais"]
    assert flags["sdea_ativo"] is True
    assert flags["sdea_validade_aberta"] is True
    assert flags["sdea_regra_vigencia"] == "validade_vazia_conta_como_vigencia_aberta"
    assert not result["memoria_calculo"]["warnings"]


def test_instrutor_flag_aplica_parametro_instrutor():
    result = _calculate(
        _tripulante(instrutor_ativo=True, instrutor_inicio=date(2026, 4, 1)),
        missions=[_mission(categoria_financeira_aeronave="a")],
        params=_params(garantia_minima="0", missao_categoria_a_comandante="0"),
    )

    assert result["valor_instrutor"] == Decimal("300.00")
    assert result["produtividade_calculada"] == Decimal("300.00")


def test_checador_flag_aplica_parametro_checador():
    result = _calculate(
        _tripulante(checador_ativo=True, checador_inicio=date(2026, 4, 1), checador_carta_designacao="CHK-001"),
        missions=[_mission(categoria_financeira_aeronave="a")],
        params=_params(garantia_minima="0", missao_categoria_a_comandante="0"),
    )

    assert result["valor_checador"] == Decimal("300.00")
    assert result["produtividade_calculada"] == Decimal("300.00")


def test_sdea_vencido_na_competencia_nao_paga_e_gera_memoria():
    result = _calculate(
        _tripulante(sdea_ativo=True, sdea_icao_validade=date(2026, 4, 29)),
        missions=[_mission(categoria_financeira_aeronave="a")],
        params=_params(garantia_minima="0", missao_categoria_a_comandante="0"),
    )

    assert result["valor_icao"] == Decimal("0.00")
    assert result["memoria_calculo"]["inputs"]["flags_operacionais"]["sdea_ativo"] is False
    assert result["memoria_calculo"]["warnings"][0]["code"] == "sdea_icao_sem_vigencia_valida"
    assert "validade vencida" in result["memoria_calculo"]["warnings"][0]["message"]


def test_instrutor_fora_da_vigencia_nao_paga():
    result = _calculate(
        _tripulante(instrutor_ativo=True, instrutor_inicio=date(2026, 3, 1), instrutor_fim=date(2026, 3, 31)),
        missions=[_mission(categoria_financeira_aeronave="a")],
        params=_params(garantia_minima="0", missao_categoria_a_comandante="0"),
    )

    assert result["valor_instrutor"] == Decimal("0.00")
    assert result["memoria_calculo"]["warnings"][0]["code"] == "instrutor_fora_da_vigencia"


def test_checador_multiplas_cartas_vigentes_paga_uma_vez():
    result = _calculate(
        _tripulante(
            checador_ativo=True,
            checador_designacoes=[
                {"carta_designacao": "CHK-001", "data_inicio": date(2026, 1, 1), "data_fim": None, "ativo": True},
                {"carta_designacao": "CHK-002", "data_inicio": date(2026, 4, 1), "data_fim": None, "ativo": True},
            ],
        ),
        missions=[_mission(categoria_financeira_aeronave="a")],
        params=_params(garantia_minima="0", missao_categoria_a_comandante="0"),
    )

    assert result["valor_checador"] == Decimal("300.00")
    flags = result["memoria_calculo"]["inputs"]["flags_operacionais"]
    assert flags["checador_cartas_ativas"] == 2
    assert flags["checador_carta_considerada"] == "CHK-001"
    assert result["memoria_calculo"]["warnings"][0]["code"] == "checador_multiplas_cartas_nao_acumulam"


def test_checador_sem_carta_vigente_nao_paga():
    result = _calculate(
        _tripulante(checador_ativo=True, checador_inicio=date(2026, 4, 1)),
        missions=[_mission(categoria_financeira_aeronave="a")],
        params=_params(garantia_minima="0", missao_categoria_a_comandante="0"),
    )

    assert result["valor_checador"] == Decimal("0.00")
    assert result["memoria_calculo"]["warnings"][0]["code"] == "checador_sem_designacao_vigente"


def test_missoes_categoria_a_e_b_somam_por_quantidade():
    result = _calculate(
        missions=[
            _mission(categoria_financeira_aeronave="a"),
            _mission(categoria_financeira_aeronave="b"),
            _mission(categoria_financeira_aeronave="b"),
        ],
        params=_params(garantia_minima="0"),
    )

    assert result["valor_missoes_categoria_a"] == Decimal("300.00")
    assert result["valor_missoes_categoria_b"] == Decimal("1200.00")
    assert result["categoria_aplicavel"] == "mista"
    assert result["produtividade_calculada"] == Decimal("1500.00")


def test_cobertura_base_soma_parametro_por_missao_sinalizada():
    result = _calculate(
        missions=[
            _mission(categoria_financeira_aeronave="a", cobertura_base=True),
            _mission(categoria_financeira_aeronave="a", cobertura_base=True),
        ],
        params=_params(garantia_minima="0", missao_categoria_a_comandante="0"),
    )

    assert result["valor_cobertura_base"] == Decimal("400.00")
    assert result["produtividade_calculada"] == Decimal("400.00")


def test_cobertura_base_usa_quantidade_de_pernoites_quando_informada():
    result = _calculate(
        missions=[
            _mission(categoria_financeira_aeronave="a", cobertura_base=True, quantidade_pernoites=3),
        ],
        params=_params(garantia_minima="0", missao_categoria_a_comandante="0"),
    )

    assert result["valor_cobertura_base"] == Decimal("600.00")
    assert result["produtividade_calculada"] == Decimal("600.00")


def test_pernoite_comum_sem_cobertura_com_zero_pernoites_nao_gera_adicional():
    result = _calculate(
        missions=[
            _mission(categoria_financeira_aeronave="a", cobertura_base=False, quantidade_pernoites=0),
        ],
        params=_params(
            garantia_minima="0",
            missao_categoria_a_comandante="0",
            pernoite_comum_sem_cobertura_comandante="80",
        ),
    )

    assert result["valor_cobertura_base"] == Decimal("0.00")
    assert result["valor_pernoite_comum"] == Decimal("0.00")
    assert result["produtividade_calculada"] == Decimal("0.00")


def test_pernoite_comum_sem_cobertura_com_um_pernoite_nao_gera_adicional():
    result = _calculate(
        missions=[
            _mission(categoria_financeira_aeronave="a", cobertura_base=False, quantidade_pernoites=1),
        ],
        params=_params(garantia_minima="0", missao_categoria_a_comandante="0"),
    )

    assert result["valor_cobertura_base"] == Decimal("0.00")
    assert result["valor_pernoite_comum"] == Decimal("0.00")
    assert result["produtividade_calculada"] == Decimal("0.00")
    assert result["memoria_calculo"]["inputs"]["contagens_agregadas"]["pernoite_comum_sem_cobertura"] == 0
    assert result["memoria_calculo"]["warnings"] == []


def test_pernoite_comum_sem_cobertura_a_partir_do_segundo_pernoite_fica_alertado_sem_parametro():
    result = _calculate(
        missions=[
            _mission(categoria_financeira_aeronave="a", cobertura_base=False, quantidade_pernoites=3),
        ],
        params=_params(garantia_minima="0", missao_categoria_a_comandante="0"),
    )

    warnings = result["memoria_calculo"]["warnings"]
    assert result["valor_cobertura_base"] == Decimal("0.00")
    assert result["valor_pernoite_comum"] == Decimal("0.00")
    assert result["produtividade_calculada"] == Decimal("0.00")
    assert result["memoria_calculo"]["inputs"]["contagens_agregadas"]["pernoite_comum_sem_cobertura"] == 2
    assert warnings[0]["code"] == "pernoite_comum_parametro_ausente"
    assert warnings[0]["quantidade"] == 2


def test_pernoite_comum_sem_cobertura_com_dois_pernoites_paga_um_quando_parametro_existe():
    result = _calculate(
        missions=[
            _mission(categoria_financeira_aeronave="a", cobertura_base=False, quantidade_pernoites=2),
        ],
        params=_params(
            garantia_minima="0",
            missao_categoria_a_comandante="0",
            pernoite_comum_sem_cobertura_comandante="80",
        ),
    )

    assert result["valor_cobertura_base"] == Decimal("0.00")
    assert result["valor_pernoite_comum"] == Decimal("80.00")
    assert result["produtividade_calculada"] == Decimal("80.00")
    assert result["memoria_calculo"]["warnings"] == []
    pernoite_step = [
        step for step in result["memoria_calculo"]["steps"]
        if step["rule_key"] == "pernoite_comum_sem_cobertura"
    ][0]
    assert pernoite_step["parametro_usado"]["tipo"] == "pernoite_comum_sem_cobertura"
    assert pernoite_step["resultado_intermediario"]["pernoites_remuneraveis"] == 1


def test_pernoite_comum_sem_cobertura_com_tres_pernoites_paga_dois_por_funcao():
    result = _calculate(
        tripulante=_tripulante(id=202),
        funcao="copiloto",
        missions=[
            _mission(categoria_financeira_aeronave="a", cobertura_base=False, quantidade_pernoites=3),
        ],
        params=_params(
            garantia_minima_a_copiloto="0",
            missao_categoria_a_copiloto="0",
            pernoite_comum_sem_cobertura_comandante="80",
            pernoite_comum_sem_cobertura_copiloto="45",
        ),
    )

    assert result["valor_pernoite_comum"] == Decimal("90.00")
    assert result["produtividade_calculada"] == Decimal("90.00")
    common_refs = [
        item for item in result["parametros_usados"]
        if item["tipo"] == "pernoite_comum_sem_cobertura"
    ]
    assert common_refs[0]["funcao"] == "copiloto"


def test_cobertura_base_nao_usa_parametro_de_pernoite_comum():
    result = _calculate(
        missions=[
            _mission(categoria_financeira_aeronave="a", cobertura_base=True, quantidade_pernoites=2),
        ],
        params=_params(
            garantia_minima="0",
            missao_categoria_a_comandante="0",
            pernoite_comum_sem_cobertura_comandante="999",
        ),
    )

    assert result["valor_cobertura_base"] == Decimal("400.00")
    assert result["valor_pernoite_comum"] == Decimal("0.00")
    assert result["produtividade_calculada"] == Decimal("400.00")


def test_excecao_palmas_turbohelice_soma_parametro_especifico():
    result = _calculate(
        missions=[_mission(categoria_financeira_aeronave="turbohelice_palmas")],
        params=_params(garantia_minima="0"),
    )

    assert result["valor_excecao_palmas"] == Decimal("5000.00")
    assert result["categoria_aplicavel"] == "turbohelice_palmas"
    assert result["produtividade_calculada"] == Decimal("5000.00")


def test_operacao_especial_palmas_turbohelice_tambem_aciona_excecao_financeira():
    result = _calculate(
        missions=[_mission(categoria_financeira_aeronave="", operacao_especial="Palmas turboélice")],
        params=_params(garantia_minima="0"),
    )

    assert result["valor_excecao_palmas"] == Decimal("5000.00")
    assert result["categoria_aplicavel"] == "turbohelice_palmas"
    assert result["produtividade_calculada"] == Decimal("5000.00")


def test_operacao_especial_nao_reconhecida_nao_altera_calculo_financeiro():
    result = _calculate(
        missions=[_mission(operacao_especial="Observação operacional interna")],
        params=_params(garantia_minima="0"),
    )

    assert result["valor_excecao_palmas"] == Decimal("0.00")
    assert result["categoria_aplicavel"] == CANONICAL_CATEGORY_A


def test_categoria_nao_aplicavel_na_missao_mantem_piso_pela_categoria_do_tripulante():
    result = _calculate(
        missions=[_mission(categoria_financeira_aeronave="nao_aplicavel")],
        params=_params(),
    )

    assert result["categoria_aplicavel"] == "nao_aplicavel"
    assert result["valor_missoes_categoria_a"] == Decimal("0.00")
    assert result["valor_missoes_categoria_b"] == Decimal("0.00")
    assert result["garantia_minima"] == Decimal("3000.00")
    assert result["excedente"] == Decimal("0.00")
    assert result["total_devido"] == Decimal("3000.00")
    assert result["memoria_calculo"]["inputs"]["categoria_garantia_minima"] == CANONICAL_CATEGORY_A


def test_sem_missoes_mantem_piso_mensal_pela_categoria_do_tripulante():
    result = _calculate(
        tripulante=_tripulante(categoria_operacional="B"),
        missions=[],
        params=_params(),
    )

    assert result["categoria_aplicavel"] == "nao_aplicavel"
    assert result["produtividade_calculada"] == Decimal("0.00")
    assert result["garantia_minima"] == Decimal("6000.00")
    assert result["excedente"] == Decimal("0.00")
    assert result["total_devido"] == Decimal("6000.00")
    assert result["memoria_calculo"]["inputs"]["categoria_garantia_minima"] == CANONICAL_CATEGORY_B


def test_categoria_operacional_nao_elegivel_nao_inventa_piso_e_gera_aviso():
    result = _calculate(
        tripulante=_tripulante(categoria_operacional="N/A"),
        missions=[_mission(categoria_financeira_aeronave="nao_aplicavel")],
        params=_params(),
    )

    assert result["garantia_minima"] == Decimal("0.00")
    assert result["total_devido"] == Decimal("0.00")
    assert result["memoria_calculo"]["warnings"][0]["code"] == "categoria_operacional_tripulante_nao_elegivel_garantia"


def test_garantia_minima_define_total_quando_produtividade_fica_abaixo():
    result = _calculate(
        missions=[_mission(categoria_financeira_aeronave="a")],
        params=_params(garantia_minima="2500", missao_categoria_a_comandante="0"),
    )

    assert result["produtividade_calculada"] == Decimal("0.00")
    assert result["garantia_minima"] == Decimal("2500.00")
    assert result["total_devido"] == Decimal("2500.00")


def test_total_devido_fica_acima_da_garantia_quando_produtividade_supera_minimo():
    result = _calculate(
        _tripulante(
            sdea_ativo=True,
            sdea_icao_validade=date(2026, 4, 30),
            instrutor_ativo=True,
            instrutor_inicio=date(2026, 4, 1),
            checador_ativo=True,
            checador_inicio=date(2026, 4, 1),
            checador_carta_designacao="CHK-001",
        ),
        missions=[
            _mission(categoria_financeira_aeronave="a"),
            _mission(categoria_financeira_aeronave="b"),
            _mission(categoria_financeira_aeronave="b", cobertura_base=True),
            _mission(categoria_financeira_aeronave="turbohelice_palmas"),
        ],
        params=_params(garantia_minima="2500"),
    )

    assert result["valor_icao"] == Decimal("300.00")
    assert result["valor_instrutor"] == Decimal("300.00")
    assert result["valor_checador"] == Decimal("300.00")
    assert result["valor_missoes_categoria_a"] == Decimal("300.00")
    assert result["valor_missoes_categoria_b"] == Decimal("1200.00")
    assert result["valor_cobertura_base"] == Decimal("200.00")
    assert result["valor_excecao_palmas"] == Decimal("5000.00")
    assert result["produtividade_calculada"] == Decimal("7600.00")
    assert result["garantia_minima"] == Decimal("2500.00")
    assert result["excedente"] == Decimal("5100.00")
    assert result["total_devido"] == Decimal("7600.00")


def test_total_devido_pode_ser_parametrizado_sem_garantia_minima():
    result = _calculate(
        missions=[_mission(categoria_financeira_aeronave="a")],
        params=_params(garantia_minima="2500"),
        aplicar_garantia_minima=False,
    )

    assert result["garantia_minima"] == Decimal("2500.00")
    assert result["total_devido"] == Decimal("300.00")
    assert result["memoria_calculo"]["inputs"]["politica_total_devido"] == "produtividade_calculada"


def test_parametros_brl_antigos_bloqueiam_motor():
    old_smoke_params = [
        _param("missao_categoria_a", "100.00", funcao="comandante", categoria="categoria a", unidade="BRL", parameter_id=7),
        _param("garantia_minima", "500.00", funcao="comandante", categoria="categoria a", unidade="BRL", parameter_id=9),
    ]
    official_params = [
        _param("missao_categoria_a", "300.00", funcao="comandante", categoria="categoria a", unidade="valor", parameter_id=28),
        _param("garantia_minima", "3000.00", funcao="comandante", categoria="categoria a", unidade="valor", parameter_id=34),
    ]

    with pytest.raises(ParametroBonificacaoProdutividadeNaoElegivelErro) as exc:
        _calculate(
            missions=[_mission(categoria_financeira_aeronave="a")],
            params=old_smoke_params + official_params,
        )

    assert exc.value.code == "bonificacao_produtividade_parametro_nao_elegivel"
    blocked = {item["parameter_id"]: set(item["reasons"]) for item in exc.value.details["blocking_parameters"]}
    assert "unidade_brl_legacy" in blocked[7]
    assert "unidade_brl_legacy" in blocked[9]


def test_categoria_b_usa_diaria_e_garantia_minima_categorizadas():
    result = _calculate(
        tripulante=_tripulante(categoria_operacional="B"),
        missions=[_mission(categoria_financeira_aeronave="b")],
        params=_params(),
    )

    assert result["valor_missoes_categoria_b"] == Decimal("600.00")
    assert result["garantia_minima"] == Decimal("6000.00")
    assert result["total_devido"] == Decimal("6000.00")
    assert result["categoria_aplicavel"] == CANONICAL_CATEGORY_B


def test_copiloto_categoria_a_usa_valores_oficiais_da_funcao():
    result = _calculate(
        tripulante=_tripulante(id=202),
        funcao="copiloto",
        missions=[_mission(categoria_financeira_aeronave="a")],
        params=_params(),
    )

    assert result["valor_missoes_categoria_a"] == Decimal("150.00")
    assert result["garantia_minima"] == Decimal("1500.00")
    assert result["total_devido"] == Decimal("1500.00")
    assert result["memoria_calculo"]["participant"] == {"tripulante_id": 202, "funcao": "copiloto"}


def test_parametro_duplicado_valido_bloqueia_por_sobreposicao():
    params = [
        *_params(garantia_minima="0"),
        _param("missao_categoria_a", "333.00", funcao="comandante", categoria="categoria a", unidade="valor", parameter_id=99),
    ]

    with pytest.raises(ParametroBonificacaoProdutividadeNaoElegivelErro) as exc:
        _calculate(missions=[_mission(categoria_financeira_aeronave="a")], params=params)

    assert exc.value.code == "bonificacao_produtividade_parametro_nao_elegivel"
    blocked = {item["parameter_id"]: set(item["reasons"]) for item in exc.value.details["blocking_parameters"]}
    assert "sobreposicao_semantica_ativa" in blocked[5]
    assert "sobreposicao_semantica_ativa" in blocked[99]


def test_parametro_ausente_gera_erro_de_dominio():
    params = [parameter for parameter in _params(garantia_minima="0") if parameter["tipo"] != "missao_categoria_a"]

    with pytest.raises(ParametroBonificacaoProdutividadeAusenteErro) as exc:
        _calculate(missions=[_mission(categoria_financeira_aeronave="a")], params=params)

    assert exc.value.code == "bonificacao_produtividade_parametro_ausente"
    assert "missao_categoria_a" in exc.value.message


def test_categoria_invalida_bloqueia_motor():
    params = [
        _param("missao_categoria_a", "300.00", funcao="comandante", categoria="x", unidade="valor", parameter_id=500),
        *_params(garantia_minima="0"),
    ]

    with pytest.raises(ParametroBonificacaoProdutividadeNaoElegivelErro) as exc:
        _calculate(missions=[_mission(categoria_financeira_aeronave="a")], params=params)

    assert exc.value.code == "bonificacao_produtividade_parametro_nao_elegivel"
    blocked = {item["parameter_id"]: set(item["reasons"]) for item in exc.value.details["blocking_parameters"]}
    assert "categoria_invalida_para_tipo" in blocked[500]


def test_normalizador_converte_categoria_operacional_abreviada_para_canonica():
    assert normalizar_categoria_operacional("a") == CANONICAL_CATEGORY_A
    assert normalizar_categoria_operacional("b") == CANONICAL_CATEGORY_B
    assert normalizar_categoria_operacional("categoria_a") == CANONICAL_CATEGORY_A
    assert normalizar_categoria_operacional("categoria b") == CANONICAL_CATEGORY_B


def test_parametro_abreviado_a_b_nao_e_canonico_novo():
    params = []
    for parameter in _params(garantia_minima="0"):
        if parameter["tipo"] in {"missao_categoria_a", "garantia_minima"}:
            params.append({**parameter, "categoria": "a"})
        else:
            params.append(parameter)

    with pytest.raises(ParametroBonificacaoProdutividadeNaoElegivelErro) as exc:
        _calculate(missions=[_mission(categoria_financeira_aeronave="a")], params=params)

    blocked = {item["parameter_id"]: set(item["reasons"]) for item in exc.value.details["blocking_parameters"]}
    assert "categoria_invalida_para_tipo" in blocked[5]
    assert "categoria_invalida_para_tipo" in blocked[13]


def test_real_closure_com_release_candidate_permite_calculo():
    params = [{**item, "motivo": "GOV_CLASS=hml-release-candidate"} for item in _params(garantia_minima="0")]

    result = _calculate(
        _tripulante(sdea_ativo=True, sdea_icao_validade=date(2026, 4, 30)),
        missions=[_mission(categoria_financeira_aeronave="a")],
        params=params,
        real_closure=True,
        release_environment="hml",
    )

    assert result["total_devido"] == Decimal("600.00")


def test_real_closure_bloqueia_qa_smoke():
    params = []
    for item in _params(garantia_minima="0"):
        reason = "GOV_CLASS=hml-release-candidate"
        if item["id"] == 5:
            reason = "GOV_CLASS=qa-smoke"
        params.append({**item, "motivo": reason})

    with pytest.raises(ParametroBonificacaoProdutividadeNaoElegivelErro) as exc:
        _calculate(
            _tripulante(sdea_ativo=True, sdea_icao_validade=date(2026, 4, 30)),
            missions=[_mission(categoria_financeira_aeronave="a")],
            params=params,
            real_closure=True,
            release_environment="hml",
        )

    assert exc.value.code == "bonificacao_produtividade_parametro_nao_elegivel"
    blocked = {item["parameter_id"]: set(item["reasons"]) for item in exc.value.details["blocking_parameters"]}
    assert "classificacao_qa_smoke_bloqueada" in blocked[5]


def test_memoria_de_calculo_contem_entradas_formulas_parametros_e_resultados():
    result = _calculate(
        _tripulante(sdea_ativo=True, sdea_icao_validade=date(2026, 4, 30)),
        missions=[_mission(categoria_financeira_aeronave="a", cobertura_base=True)],
        params=_params(garantia_minima="2500"),
    )
    memory = result["memoria_calculo"]

    assert memory["calculation_version"] == "finance-productivity-v1"
    assert memory["source"]["type"] == "finance_productivity_competence"
    assert memory["participant"] == {"tripulante_id": 101, "funcao": "comandante"}
    assert memory["inputs"]["competencia"] == "2026-04"
    assert memory["inputs"]["contagens_agregadas"]["categoria_a"] == 1
    assert memory["inputs"]["politica_total_devido"] == "max(produtividade_calculada, garantia_minima)"
    assert {step["rule_key"] for step in memory["steps"]} >= {
        "flags_cadastrais",
        "missoes_por_categoria",
        "cobertura_base",
        "excecao_palmas_turbohelice",
        "produtividade_calculada",
        "garantia_minima",
    }
    guarantee_step = next(step for step in memory["steps"] if step["rule_key"] == "garantia_minima")
    assert guarantee_step["formula_conceitual"] == "total_devido = max(produtividade_calculada, garantia_minima)"
    assert memory["totals"]["garantia_minima"] == "2500.00"
    assert memory["totals"]["total_devido"] == "2500.00"
    assert all(parameter["unidade"] == "valor" for parameter in memory["parameters"])
    assert {parameter["categoria"] for parameter in memory["parameters"] if parameter["tipo"] == "garantia_minima"} == {
        CANONICAL_CATEGORY_A
    }

