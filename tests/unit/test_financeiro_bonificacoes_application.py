from __future__ import annotations

import pytest

from backend.src.controle_treinamentos.application import financeiro_bonificacoes
from backend.src.controle_treinamentos.application.financeiro_bonificacoes import (
    BonificacaoHorariaNaoEncontradaErro,
    detalhar_bonificacao_horaria,
    listar_bonificacoes_horarias,
)
from backend.src.controle_treinamentos.contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT


class _FakeDB:
    pass


def _calculation_row(**overrides):
    payload = {
        "id": 10,
        "org_id": FINANCE_ORG_SCOPE_DEFAULT,
        "missao_operacional_id": 22,
        "competencia": "2026-04",
        "data_missao": "2026-04-10",
        "cavok_numero_voo": "CAVOK-100",
        "contratante": "Cliente",
        "chamado": "CH-1",
        "aeronave_id": 5,
        "categoria_financeira_aeronave": "a",
        "horario_apresentacao": "2026-04-10T18:00:00",
        "horario_abandono": "2026-04-10T23:00:00",
        "missao_status": "ativa",
        "tripulante_id": 101,
        "tripulante_nome": "Comandante Um",
        "tripulante_cpf": "00000000000",
        "tripulante_licenca_anac": "123456",
        "funcao": "comandante",
        "jornada_total_minutos": 300,
        "minutos_diurnos": 120,
        "minutos_noturnos": 180,
        "horas_noturnas_convertidas": "3.4286",
        "minutos_pre": 0,
        "minutos_pos": 0,
        "domingo_feriado": False,
        "valor_adicional_noturno": "120.00",
        "valor_domingo_feriado_diurno": "0.00",
        "valor_domingo_feriado_noturno": "0.00",
        "valor_pre": "0.00",
        "valor_pos": "0.00",
        "total": "120.00",
        "memoria_calculo": {
            "steps": [
                {
                    "rule_key": "conversao_hora_noturna",
                    "formula_conceitual": "minutos_noturnos_reais / duracao_hora_noturna_minutos",
                }
            ]
        },
        "parametros_usados": [{"tipo": "duracao_hora_noturna_minutos", "valor": "52.5", "unidade": "minutos"}],
        "calculation_version": "finance-hourly-v1",
        "status": "calculado",
    }
    payload.update(overrides)
    return payload


def test_listar_bonificacoes_horarias_serializa_missao_tripulante_e_memoria(monkeypatch):
    calls = []

    def _list_rows(db, **kwargs):
        calls.append((db, kwargs))
        return [_calculation_row()]

    monkeypatch.setattr(financeiro_bonificacoes, "listar_calculos_horarios", _list_rows)

    result = listar_bonificacoes_horarias(
        competencia="2026-04",
        tripulante_id=101,
        funcao="comandante",
        status="calculado",
        page=2,
        offset=100,
        limit=100,
        db=_FakeDB(),
    )

    assert result["pagination"] == {"page": 2, "offset": 100, "total": 1}
    item = result["items"][0]
    assert item["competencia"] == "2026-04"
    assert item["mission_id"] == 22
    assert item["missao"]["cavok_numero_voo"] == "CAVOK-100"
    assert item["tripulante"]["nome"] == "Comandante Um"
    assert item["minutos_noturnos_reais"] == 180
    assert item["horas_noturnas_convertidas"] == "3.4286"
    assert item["parametros_usados"][0]["valor"] == "52.5"
    assert calls[0][1]["org_id"] == FINANCE_ORG_SCOPE_DEFAULT
    assert calls[0][1]["competencia"] == "2026-04"


def test_detalhar_bonificacao_horaria_retorna_memoria_ou_404(monkeypatch):
    monkeypatch.setattr(
        financeiro_bonificacoes,
        "detalhar_calculo_horario",
        lambda db, **kwargs: _calculation_row(id=77, minutos_noturnos=105, horas_noturnas_convertidas="2.0000"),
    )

    detail = detalhar_bonificacao_horaria(77, db=_FakeDB())

    assert detail["id"] == 77
    assert detail["minutos_noturnos_reais"] == 105
    assert detail["memoria_calculo"]["steps"][0]["rule_key"] == "conversao_hora_noturna"

    monkeypatch.setattr(financeiro_bonificacoes, "detalhar_calculo_horario", lambda db, **kwargs: None)
    with pytest.raises(BonificacaoHorariaNaoEncontradaErro):
        detalhar_bonificacao_horaria(999, db=_FakeDB())
