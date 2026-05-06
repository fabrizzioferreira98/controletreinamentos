from backend.src.controle_treinamentos.application import financeiro_lancamentos_jornada


class _FakeDB:
    pass


def test_consolidado_produtividade_usa_recorte_e_exclui_nao_vigentes(monkeypatch):
    calls = {}

    monkeypatch.setattr(
        financeiro_lancamentos_jornada,
        "fetch_competencia_financeira",
        lambda db, *, competencia, org_id: {"competencia": competencia, "org_id": org_id, "status": "aberta"},
    )

    def fake_productivity(db, **kwargs):
        calls["productivity"] = kwargs
        return [
            {
                "id": 10,
                "tripulante_id": 1,
                "tripulante_nome": "Joao Silva",
                "funcao": "comandante",
                "status": "calculado",
                "produtividade_calculada": "1000.00",
                "total_devido": "1200.00",
                "valor_excecao_palmas": "200.00",
                "memoria_calculo": {"alertas": [{"code": "special", "message": "Condicao especial aplicada"}]},
            },
            {
                "id": 11,
                "tripulante_id": 2,
                "tripulante_nome": "Maria Souza",
                "funcao": "comandante",
                "status": "obsoleto",
                "produtividade_calculada": "9999.00",
                "total_devido": "9999.00",
            },
            {
                "id": 12,
                "tripulante_id": 3,
                "tripulante_nome": "Carlos Lima",
                "funcao": "comandante",
                "status": "bloqueado",
                "produtividade_calculada": "500.00",
                "total_devido": "500.00",
                "memoria_calculo": {"bloqueios": [{"code": "blocked", "message": "Missao bloqueada"}]},
            },
        ]

    def fake_participations(db, **kwargs):
        calls["participations"] = kwargs
        return [
            {
                "missao_operacional_id": 100,
                "tripulante_id": 1,
                "tripulante_nome": "Joao Silva",
                "funcao": "comandante",
                "missao_status": "ativa",
                "participante_status": "ativo",
                "operacao_especial": "Palmas turboelice",
            },
            {
                "missao_operacional_id": 101,
                "tripulante_id": 1,
                "tripulante_nome": "Joao Silva",
                "funcao": "comandante",
                "missao_status": "cancelada",
                "participante_status": "ativo",
                "operacao_especial": "Cancelada",
            },
        ]

    monkeypatch.setattr(financeiro_lancamentos_jornada, "listar_produtividade_jornada", fake_productivity)
    monkeypatch.setattr(financeiro_lancamentos_jornada, "listar_participacoes_produtividade_jornada", fake_participations)

    result = financeiro_lancamentos_jornada.consolidar_produtividade_jornada(
        competencia="2026-04",
        funcao="comandante",
        tripulante_id=1,
        org_id="org-a",
        db=_FakeDB(),
    )

    assert calls["productivity"] == {
        "competencia": "2026-04",
        "org_id": "org-a",
        "funcao": "comandante",
        "tripulante_id": 1,
    }
    assert calls["participations"] == {
        "competencia": "2026-04",
        "org_id": "org-a",
        "funcao": "comandante",
        "tripulante_id": 1,
    }
    assert result["indicadores"]["total_a_pagar"] == "1200.00"
    assert result["indicadores"]["missoes_consideradas"] == 1
    assert result["indicadores"]["missoes_bloqueadas"] == 1
    assert result["indicadores"]["excecoes"] == 1
    assert result["indicadores"]["alertas"] == 1
    assert result["condicoes_especiais"][0]["condicao_operacional_especial"] == "Palmas turboelice"
    assert len(result["linhas_por_tripulante"]) == 2
    assert result["linhas_por_tripulante"][0]["total_a_pagar"] == "0.00"
    assert result["linhas_por_tripulante"][1]["total_a_pagar"] == "1200.00"


def test_salvar_linha_jornada_recalcula_produtividade_da_competencia(monkeypatch):
    calls = []

    def fake_recalculate_mission(mission_id, **kwargs):
        calls.append(("mission", mission_id, kwargs))
        return {
            "mission_id": mission_id,
            "competence": "2026-05",
            "calculation_status": "calculado",
            "current_result": {"total": "100.00"},
        }

    def fake_recalculate_period(competencia, **kwargs):
        calls.append(("period", competencia, kwargs))
        return {
            "totals": {
                "total_produtividade": "1200.00",
                "total_geral": "1300.00",
            },
            "items": [{"id": 1}],
        }

    monkeypatch.setattr(financeiro_lancamentos_jornada, "recalcular_missao_operacional", fake_recalculate_mission)
    monkeypatch.setattr(financeiro_lancamentos_jornada, "recalcular_competencia_financeira", fake_recalculate_period)

    result = financeiro_lancamentos_jornada._recalculate_after_journey_save(
        99,
        actor_user_id=7,
        org_id="org-a",
        db=_FakeDB(),
    )

    assert calls[0][0] == "mission"
    assert calls[1][0] == "period"
    assert calls[1][1] == "2026-05"
    assert result["status"] == "calculado"
    assert result["productivity_status"] == "calculado"
    assert result["productivity_recalculation"]["totals"]["total_produtividade"] == "1200.00"


def test_salvar_linha_jornada_nao_falha_quando_produtividade_fica_pendente(monkeypatch):
    monkeypatch.setattr(
        financeiro_lancamentos_jornada,
        "recalcular_missao_operacional",
        lambda *args, **kwargs: {
            "mission_id": 99,
            "competence": "2026-05",
            "calculation_status": "calculado",
        },
    )

    def fail_productivity(*args, **kwargs):
        raise financeiro_lancamentos_jornada.DomainValidationError(
            "Parametro de produtividade ausente.",
            code="finance_productivity_parameter_missing",
            status=422,
        )

    monkeypatch.setattr(financeiro_lancamentos_jornada, "recalcular_competencia_financeira", fail_productivity)

    result = financeiro_lancamentos_jornada._recalculate_after_journey_save(
        99,
        actor_user_id=7,
        org_id="org-a",
        db=_FakeDB(),
    )

    assert result["status"] == "calculado"
    assert result["productivity_status"] == "pendente"
    assert result["productivity_error"]["code"] == "finance_productivity_parameter_missing"
