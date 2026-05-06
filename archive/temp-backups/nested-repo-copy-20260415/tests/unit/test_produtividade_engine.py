from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.src.controle_treinamentos.produtividade import CompetenciaDataBundle, ProdutividadeEngine


def _bundle_base():
    return CompetenciaDataBundle(
        competencia="2026-03",
        month_start=date(2026, 3, 1),
        month_end_exclusive=date(2026, 4, 1),
        regras_map={
            ("A", "comandante"): {
                "piso_minimo_mensal": Decimal("3000"),
                "valor_missao": Decimal("300"),
                "valor_pernoite_cobertura": Decimal("200"),
                "valor_idioma_mensal": Decimal("300"),
                "valor_instrutor_mensal": Decimal("300"),
                "valor_checador_mensal": Decimal("300"),
            },
            ("N/A", "outro"): {
                "piso_minimo_mensal": Decimal("0"),
                "valor_missao": Decimal("0"),
                "valor_pernoite_cobertura": Decimal("0"),
                "valor_idioma_mensal": Decimal("0"),
                "valor_instrutor_mensal": Decimal("0"),
                "valor_checador_mensal": Decimal("0"),
            },
        },
        parametros={
            "valor_pernoite_operacional_comum": Decimal("50"),
            "contar_pernoite_operacional_a_partir_segundo_dia": Decimal("1"),
            "adicional_excepcional_comandante": Decimal("5000"),
        },
        missoes_by_tripulante={},
        pernoites_by_tripulante={},
        adicional_manual_by_tripulante={},
    )


def _tripulante_base():
    return {
        "id": 10,
        "nome": "Tripulante Teste",
        "base": "Goiânia",
        "funcao_operacional": "comandante",
        "categoria_operacional": "A",
        "sdea_ativo": 0,
        "instrutor_ativo": 0,
        "checador_ativo": 0,
        "elegivel_adicional_excepcional": 0,
        "ativo": 1,
    }


def test_consolida_missoes_por_codigo_e_contratante():
    engine = ProdutividadeEngine(db=None)
    bundle = _bundle_base()
    trip = _tripulante_base()
    bundle.missoes_by_tripulante[trip["id"]] = [
        {"id": 1, "codigo_voo": "BV123", "contratante": "Cliente X", "conta_missao_produtividade": True},
        {"id": 2, "codigo_voo": "BV123", "contratante": "Cliente X", "conta_missao_produtividade": True},
        {"id": 3, "codigo_voo": "BV123", "contratante": "Cliente Y", "conta_missao_produtividade": True},
        {"id": 4, "codigo_voo": "BV999", "contratante": "Cliente Y", "conta_missao_produtividade": False},
    ]

    result = engine.calculate_tripulante(tripulante=trip, competencia="2026-03", bundle=bundle)
    assert result["total_missoes_validas"] == 2
    assert result["valor_total_missoes"] == Decimal("600")


def test_pernoite_operacional_conta_a_partir_do_segundo_dia():
    engine = ProdutividadeEngine(db=None)
    bundle = _bundle_base()
    trip = _tripulante_base()
    bundle.pernoites_by_tripulante[trip["id"]] = [
        {"id": 1, "tipo_pernoite": "cobertura_base", "quantidade": 2},
        {"id": 2, "tipo_pernoite": "operacional_comum", "missao_id": 77, "quantidade": 3},
    ]

    result = engine.calculate_tripulante(tripulante=trip, competencia="2026-03", bundle=bundle)
    assert result["total_pernoites_cobertura"] == 2
    assert result["valor_total_pernoites_cobertura"] == Decimal("400")
    assert result["total_pernoites_operacionais_elegiveis"] == 2
    assert result["valor_total_pernoites_operacionais"] == Decimal("100")


def test_adicional_excepcional_so_aplica_quando_elegivel():
    engine = ProdutividadeEngine(db=None)
    bundle = _bundle_base()
    trip = _tripulante_base()
    bundle.adicional_manual_by_tripulante[trip["id"]] = Decimal("2500")

    sem_elegibilidade = engine.calculate_tripulante(tripulante=trip, competencia="2026-03", bundle=bundle)
    assert sem_elegibilidade["valor_adicional_excepcional"] == Decimal("0")

    trip["elegivel_adicional_excepcional"] = 1
    com_elegibilidade = engine.calculate_tripulante(tripulante=trip, competencia="2026-03", bundle=bundle)
    assert com_elegibilidade["valor_adicional_excepcional"] == Decimal("2500")


def test_fechamento_aplica_piso_minimo_quando_produtividade_menor():
    engine = ProdutividadeEngine(db=None)
    bundle = _bundle_base()
    trip = _tripulante_base()

    result = engine.calculate_tripulante(tripulante=trip, competencia="2026-03", bundle=bundle)
    assert result["total_produtividade"] == Decimal("0")
    assert result["valor_final_mes"] == Decimal("3000")
    assert result["criterio_fechamento"] == "piso mínimo"


def test_fechamento_aplica_produtividade_quando_superior_ao_piso():
    engine = ProdutividadeEngine(db=None)
    bundle = _bundle_base()
    trip = _tripulante_base()
    trip.update({"sdea_ativo": 1, "instrutor_ativo": 1, "checador_ativo": 1, "elegivel_adicional_excepcional": 1})
    bundle.missoes_by_tripulante[trip["id"]] = [
        {"id": 1, "codigo_voo": "BV123", "contratante": "Cliente X", "conta_missao_produtividade": True},
        {"id": 2, "codigo_voo": "BV777", "contratante": "Cliente Y", "conta_missao_produtividade": True},
    ]
    bundle.adicional_manual_by_tripulante[trip["id"]] = Decimal("5000")

    result = engine.calculate_tripulante(tripulante=trip, competencia="2026-03", bundle=bundle)
    assert result["total_produtividade"] == Decimal("6500")
    assert result["valor_final_mes"] == Decimal("6500")
    assert result["criterio_fechamento"] == "produtividade apurada"
