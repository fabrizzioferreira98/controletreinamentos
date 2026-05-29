from __future__ import annotations

from backend.src.controle_treinamentos.application import financeiro_lancamentos_jornada as usecases
from backend.src.controle_treinamentos.contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT


def _payload(**overrides):
    payload = {
        "competencia": "2026-04",
        "data": "2026-04-10",
        "tripulante_id": 101,
        "funcao": "comandante",
        "aeronave_id": 7,
        "categoria_financeira_aeronave": "A",
        "comandante_tripulante_id": 101,
        "copiloto_tripulante_id": 202,
        "relatorio_voo": "CAVOK-10",
        "contratante": "Cliente",
        "numero_db": "CH-10",
        "trecho": "BSB-GRU",
        "status": "ativa",
    }
    payload.update(overrides)
    return payload


def test_mission_payload_from_journey_preserves_two_effective_commanders(monkeypatch):
    tripulantes = {
        101: {"id": 101, "ativo": 1, "funcao_operacional": "comandante"},
        202: {"id": 202, "ativo": 1, "funcao_operacional": "comandante"},
    }

    monkeypatch.setattr(
        usecases,
        "fetch_tripulante_basico",
        lambda _db, *, tripulante_id: tripulantes.get(int(tripulante_id)),
    )
    monkeypatch.setattr(
        usecases,
        "fetch_equipamento_basico",
        lambda _db, *, aeronave_id: {"id": int(aeronave_id), "ativo": 1, "categoria_financeira": "A"},
    )

    data = usecases._mission_payload_from_journey(
        _payload(),
        org_id=FINANCE_ORG_SCOPE_DEFAULT,
        actor_user_id=55,
        db=object(),
    )

    assert data["comandante_tripulante_id"] == 101
    assert data["copiloto_tripulante_id"] == 202
    assert [item["tripulante_id"] for item in data["participantes"]] == [101, 202]
    assert [item["funcao"] for item in data["participantes"]] == ["comandante", "comandante"]
    assert [item["funcao_missao"] for item in data["participantes"]] == ["comandante", "copiloto"]


def test_mission_payload_from_journey_preserves_optional_third_crew(monkeypatch):
    tripulantes = {
        101: {"id": 101, "ativo": 1, "funcao_operacional": "comandante"},
        202: {"id": 202, "ativo": 1, "funcao_operacional": "copiloto"},
        303: {"id": 303, "ativo": 1, "funcao_operacional": "comandante"},
    }

    monkeypatch.setattr(
        usecases,
        "fetch_tripulante_basico",
        lambda _db, *, tripulante_id: tripulantes.get(int(tripulante_id)),
    )
    monkeypatch.setattr(
        usecases,
        "fetch_equipamento_basico",
        lambda _db, *, aeronave_id: {"id": int(aeronave_id), "ativo": 1, "categoria_financeira": "A"},
    )

    data = usecases._mission_payload_from_journey(
        _payload(terceiro_tripulante_id=303, terceiro_tripulante_funcao="comandante"),
        org_id=FINANCE_ORG_SCOPE_DEFAULT,
        actor_user_id=55,
        db=object(),
    )

    assert data["terceiro_tripulante_id"] == 303
    assert data["terceiro_tripulante_funcao"] == "comandante"
    assert data["participantes"][-1] == {
        "tripulante_id": 303,
        "funcao": "comandante",
        "funcao_missao": "comandante",
        "status": "ativo",
    }


def test_criar_linha_jornada_resolves_second_effective_commander(monkeypatch):
    class FakeDB:
        def __init__(self):
            self.commit_count = 0

        def commit(self):
            self.commit_count += 1

    db = FakeDB()
    captured = {}
    data = {
        **_payload(tripulante_id=202, funcao="comandante"),
        "org_id": FINANCE_ORG_SCOPE_DEFAULT,
        "comandante_tripulante_id": 101,
        "copiloto_tripulante_id": 202,
        "participantes": [
            {"tripulante_id": 101, "funcao": "comandante", "funcao_missao": "comandante", "status": "ativo"},
            {"tripulante_id": 202, "funcao": "comandante", "funcao_missao": "copiloto", "status": "ativo"},
        ],
    }

    monkeypatch.setattr(usecases, "_mission_payload_from_journey", lambda *args, **kwargs: data)
    monkeypatch.setattr(usecases, "validar_competencia_aberta_para_mutacao", lambda *args, **kwargs: None)
    monkeypatch.setattr(usecases, "criar_missao_operacional", lambda *args, **kwargs: {"id": 99})
    monkeypatch.setattr(usecases, "_recalculate_after_journey_save", lambda *args, **kwargs: {"status": "calculado"})
    monkeypatch.setattr(usecases, "_audit", lambda *args, **kwargs: None)

    def fake_listar_linhas_jornada(_db, **kwargs):
        captured.update(kwargs)
        return [
            {
                "linha_id": 12,
                "missao_operacional_id": 99,
                "competencia": "2026-04",
                "data_missao": "2026-04-10",
                "data_final": "2026-04-10",
                "linha_tripulante_id": 202,
                "linha_funcao": "comandante",
                "linha_status": "ativo",
                "missao_status": "ativa",
                "comandante_tripulante_id": 101,
                "copiloto_tripulante_id": 202,
            }
        ]

    monkeypatch.setattr(usecases, "listar_linhas_jornada", fake_listar_linhas_jornada)

    result = usecases.criar_linha_jornada(
        _payload(tripulante_id=202, funcao="comandante"),
        actor_user_id=55,
        db=db,
    )

    assert captured["funcao"] == "comandante"
    assert captured["tripulante_id"] == 202
    assert result["linha"]["tripulante_id"] == 202
    assert result["linha"]["funcao"] == "comandante"
    assert db.commit_count == 1
