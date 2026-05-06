from __future__ import annotations

import pytest

from backend.src.controle_treinamentos.application import financeiro_bonificacoes
from backend.src.controle_treinamentos.application.financeiro_bonificacoes import (
    BonificacaoProdutividadeNaoEncontradaErro,
    detalhar_bonificacao_produtividade_por_tripulante,
    listar_bonificacoes_produtividade,
    recalcular_produtividade_competencia,
)
from backend.src.controle_treinamentos.application.financeiro_missoes import CompetenciaFinanceiraFechadaErro
from backend.src.controle_treinamentos.contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT


class _FakeConn:
    def __init__(self):
        self.rollback_called = False

    def rollback(self):
        self.rollback_called = True


class _FakeDB:
    def __init__(self):
        self.conn = _FakeConn()
        self.committed = False

    def commit(self):
        self.committed = True


def _productivity_row(**overrides):
    payload = {
        "id": 10,
        "org_id": FINANCE_ORG_SCOPE_DEFAULT,
        "competencia": "2026-04",
        "tripulante_id": 101,
        "tripulante_nome": "Comandante Um",
        "tripulante_cpf": "00000000000",
        "tripulante_licenca_anac": "123456",
        "funcao": "comandante",
        "categoria_aplicavel": "a",
        "valor_icao": "0.00",
        "valor_instrutor": "0.00",
        "valor_checador": "0.00",
        "valor_missoes_categoria_a": "120.00",
        "valor_missoes_categoria_b": "0.00",
        "valor_cobertura_base": "0.00",
        "valor_pernoite_comum": "0.00",
        "valor_excecao_palmas": "0.00",
        "produtividade_calculada": "120.00",
        "garantia_minima": "100.00",
        "total_devido": "120.00",
        "memoria_calculo": {"steps": [{"rule_key": "produtividade_calculada"}]},
        "parametros_usados": [{"tipo": "missao_categoria_a", "valor": "120.00", "unidade": "valor"}],
        "calculation_version": "finance-productivity-v1",
        "status": "calculado",
    }
    payload.update(overrides)
    return payload


def _participation(**overrides):
    payload = {
        "missao_operacional_id": 55,
        "org_id": FINANCE_ORG_SCOPE_DEFAULT,
        "competencia": "2026-04",
        "data_missao": "2026-04-10",
        "cavok_numero_voo": "CAVOK-1",
        "contratante": "Cliente",
        "chamado": "CH-1",
        "aeronave_id": 5,
        "categoria_financeira_aeronave": "a",
        "cobertura_base": False,
        "operacao_especial": None,
        "missao_status": "ativa",
        "tripulante_id": 101,
        "funcao": "comandante",
        "tripulante_nome": "Comandante Um",
        "tripulante_categoria_operacional": "A",
        "tripulante_sdea_ativo": 0,
        "tripulante_instrutor_ativo": 0,
        "tripulante_checador_ativo": 0,
    }
    payload.update(overrides)
    return payload


def _parameter(tipo, valor, *, funcao="comandante", categoria=None, unidade="valor"):
    return {
        "id": abs(hash((tipo, funcao, categoria))) % 10000,
        "tipo": tipo,
        "funcao": funcao,
        "categoria": categoria,
        "valor": valor,
        "unidade": unidade,
        "vigencia_inicio": "2026-01-01",
        "vigencia_fim": None,
    }


def test_listar_e_detalhar_bonificacoes_produtividade_serializam_memoria(monkeypatch):
    monkeypatch.setattr(
        financeiro_bonificacoes,
        "listar_calculos_produtividade",
        lambda db, **kwargs: [_productivity_row()],
    )
    monkeypatch.setattr(
        financeiro_bonificacoes,
        "detalhar_calculo_produtividade_por_tripulante",
        lambda db, **kwargs: _productivity_row(tripulante_id=kwargs["tripulante_id"]),
    )

    result = listar_bonificacoes_produtividade(
        competencia="2026-04",
        tripulante_id=101,
        funcao="comandante",
        status="calculado",
        page=1,
        offset=0,
        limit=100,
        db=_FakeDB(),
    )
    detail = detalhar_bonificacao_produtividade_por_tripulante(101, competencia="2026-04", db=_FakeDB())

    assert result["items"][0]["tripulante"]["nome"] == "Comandante Um"
    assert result["items"][0]["total_devido"] == "120.00"
    assert detail["memoria_calculo"]["steps"][0]["rule_key"] == "produtividade_calculada"

    monkeypatch.setattr(financeiro_bonificacoes, "detalhar_calculo_produtividade_por_tripulante", lambda db, **kwargs: None)
    with pytest.raises(BonificacaoProdutividadeNaoEncontradaErro):
        detalhar_bonificacao_produtividade_por_tripulante(999, db=_FakeDB())


def test_recalcular_produtividade_competencia_persiste_memoria_e_audit_log(monkeypatch):
    db = _FakeDB()
    saved_payloads = []
    audit_calls = []
    parameter_query_kwargs = []

    monkeypatch.setattr(financeiro_bonificacoes, "validar_competencia_aberta_para_mutacao", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        financeiro_bonificacoes,
        "listar_participacoes_produtividade_por_competencia",
        lambda *args, **kwargs: [_participation()],
    )
    monkeypatch.setattr(
        financeiro_bonificacoes,
        "listar_tripulantes_elegiveis_produtividade",
        lambda *args, **kwargs: [],
    )
    def _list_parameters(*args, **kwargs):
        parameter_query_kwargs.append(kwargs)
        return [
            _parameter("missao_categoria_a", "120.00", categoria="categoria a"),
            _parameter("garantia_minima", "100.00", categoria="categoria a"),
        ]

    monkeypatch.setattr(financeiro_bonificacoes, "listar_parametros_financeiros_rows", _list_parameters)

    def _save(_db, *, data, org_id=None):
        saved_payloads.append(data)
        return _productivity_row(id=77, **data)

    monkeypatch.setattr(financeiro_bonificacoes, "salvar_calculo_produtividade", _save)
    monkeypatch.setattr(financeiro_bonificacoes, "record_audit_event", lambda *args, **kwargs: audit_calls.append((args, kwargs)))

    result = recalcular_produtividade_competencia("2026-04", actor_user_id=501, db=db)

    assert db.committed is True
    assert result["competencia"] == "2026-04"
    assert result["totals"]["participant_count"] == 1
    assert result["items"][0]["total_devido"] == "120.00"
    assert saved_payloads[0]["memoria_calculo"]["steps"]
    assert saved_payloads[0]["parametros_usados"]
    assert all(parameter["unidade"] == "valor" for parameter in saved_payloads[0]["parametros_usados"])
    assert saved_payloads[0]["org_id"] == FINANCE_ORG_SCOPE_DEFAULT
    assert parameter_query_kwargs[0]["unidade"] == "valor"
    assert [call[1]["acao"] for call in audit_calls] == [
        "finance.productivity.calculated",
        "finance.period.recalculated",
    ]


def test_recalcular_produtividade_competencia_persiste_piso_para_tripulante_sem_missao(monkeypatch):
    db = _FakeDB()
    saved_payloads = []

    monkeypatch.setattr(financeiro_bonificacoes, "validar_competencia_aberta_para_mutacao", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        financeiro_bonificacoes,
        "listar_participacoes_produtividade_por_competencia",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        financeiro_bonificacoes,
        "listar_tripulantes_elegiveis_produtividade",
        lambda *args, **kwargs: [
            {
                "tripulante_id": 202,
                "tripulante_nome": "Copiloto Piso",
                "funcao": "copiloto",
                "tripulante_categoria_operacional": "B",
                "tripulante_sdea_ativo": 0,
                "tripulante_instrutor_ativo": 0,
                "tripulante_checador_ativo": 0,
            }
        ],
    )
    monkeypatch.setattr(
        financeiro_bonificacoes,
        "listar_parametros_financeiros_rows",
        lambda *args, **kwargs: [
            _parameter("missao_categoria_b", "300.00", funcao="copiloto", categoria="categoria b"),
            _parameter("garantia_minima", "3000.00", funcao="copiloto", categoria="categoria b"),
        ],
    )

    def _save(_db, *, data, org_id=None):
        saved_payloads.append(data)
        row = _productivity_row(id=88, **data)
        row["tripulante_nome"] = "Copiloto Piso"
        return row

    monkeypatch.setattr(financeiro_bonificacoes, "salvar_calculo_produtividade", _save)
    monkeypatch.setattr(financeiro_bonificacoes, "record_audit_event", lambda *args, **kwargs: None)

    result = recalcular_produtividade_competencia("2026-04", actor_user_id=501, db=db)

    assert result["totals"]["participant_count"] == 1
    assert result["totals"]["total_devido"] == "3000.00"
    assert saved_payloads[0]["produtividade_calculada"] == 0
    assert saved_payloads[0]["garantia_minima"] == 3000


def test_recalcular_produtividade_competencia_bloqueia_competencia_fechada(monkeypatch):
    db = _FakeDB()

    def _closed(*args, **kwargs):
        raise CompetenciaFinanceiraFechadaErro("2026-04")

    monkeypatch.setattr(financeiro_bonificacoes, "validar_competencia_aberta_para_mutacao", _closed)

    with pytest.raises(CompetenciaFinanceiraFechadaErro):
        recalcular_produtividade_competencia("2026-04", actor_user_id=501, db=db)

    assert db.conn.rollback_called is True
