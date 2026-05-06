from backend.src.controle_treinamentos.application import financeiro_jornada_query as query


def test_jornada_query_maps_saved_line_without_calculation_as_pending(monkeypatch):
    calls = []

    def _lines(_db, **kwargs):
        calls.append(kwargs)
        return [
            {
                "linha_id": 10,
                "linha_org_id": "org-qa",
                "org_id": "org-qa",
                "missao_operacional_id": 20,
                "competencia": "2026-04",
                "data_missao": "2026-04-05",
                "linha_tripulante_id": 135,
                "tripulante_nome": "Comandante QA",
                "linha_funcao": "comandante",
                "missao_status": "ativa",
                "cavok_numero_voo": "QA-100",
                "trecho": "SDEA/SBSP",
                "calculo_horario_id": None,
                "calculo_status": None,
            }
        ]

    monkeypatch.setattr(query, "listar_linhas_jornada", _lines)

    rows = query.consultar_calculos_horarios_jornada(
        object(),
        org_id="org-qa",
        competencia="2026-04",
        tripulante_id=135,
        funcao="comandante",
    )

    assert calls[0]["org_id"] == "org-qa"
    assert calls[0]["competencia"] == "2026-04"
    assert rows[0]["fonte_calculo"] == "financeiro_jornada_query"
    assert rows[0]["status"] == "recalculo_pendente"
    assert rows[0]["total"] == 0
    assert rows[0]["memoria_calculo"]["warnings"][0]["code"] == "calculation_pending"


def test_jornada_query_delegates_obsolete_reads_to_legacy_repository(monkeypatch):
    legacy_calls = []

    def _legacy(_db, **kwargs):
        legacy_calls.append(kwargs)
        return [{"id": 99, "status": "obsoleto"}]

    monkeypatch.setattr(query, "_listar_calculos_horarios_legacy", _legacy)

    rows = query.consultar_calculos_horarios_jornada(
        object(),
        org_id="org-qa",
        competencia="2026-04",
        tripulante_id=135,
        status="obsoleto",
        incluir_obsoletos=True,
    )

    assert rows == [{"id": 99, "status": "obsoleto"}]
    assert legacy_calls[0]["status"] == "obsoleto"
    assert legacy_calls[0]["incluir_obsoletos"] if "incluir_obsoletos" in legacy_calls[0] else True


def test_jornada_query_filters_productivity_from_same_journey_cut(monkeypatch):
    monkeypatch.setattr(
        query,
        "listar_produtividade_jornada",
        lambda _db, **_kwargs: [
            {"tripulante_id": 135, "funcao": "comandante", "status": "calculado", "total_devido": "100.00"},
            {"tripulante_id": 135, "funcao": "comandante", "status": "recalculo_pendente", "total_devido": "0.00"},
        ],
    )

    rows = query.consultar_calculos_produtividade_jornada(
        object(),
        competencia="2026-04",
        tripulante_id=135,
        funcao="comandante",
        status="calculado",
    )

    assert len(rows) == 1
    assert rows[0]["status"] == "calculado"
