import pytest

from backend.src.controle_treinamentos.application import treinamentos as treinamentos_app


def test_generic_training_payload_rejects_aircraft_model_snapshot_fields(monkeypatch):
    monkeypatch.setattr(treinamentos_app, "get_db", lambda: object())

    with pytest.raises(treinamentos_app.TreinamentoValidationError) as exc:
        treinamentos_app._parse_training_payload(
            {
                "tripulante_id": 7,
                "equipamento_id": 3,
                "tipo_treinamento_id": 2,
                "data_realizacao": "2026-04-01",
                "aeronave_modelo_snapshot": "King Air B200/200/C90A/C90GT",
            }
        )

    assert exc.value.code == "treinamento_program_write_requires_program_flow"


def test_generic_training_update_rejects_program_origin_records(monkeypatch):
    current_training = {
        "id": 55,
        "tripulante_id": 7,
        "equipamento_id": None,
        "tipo_treinamento_id": 2,
        "segmento_teorico_id": 26,
        "aeronave_modelo": "King Air B200/200/C90A/C90GT",
        "ctac_solo_horas": None,
        "ctac_voo_pic_sic_horas": None,
        "ctac_voo_crew_horas": None,
    }
    monkeypatch.setattr(treinamentos_app, "get_db", lambda: object())
    monkeypatch.setattr(
        treinamentos_app,
        "fetch_treinamento_detail",
        lambda _db, treinamento_id: current_training if treinamento_id == 55 else None,
    )

    with pytest.raises(treinamentos_app.TreinamentoValidationError) as exc:
        treinamentos_app.save_treinamento(
            {
                "tripulante_id": 7,
                "equipamento_id": 3,
                "tipo_treinamento_id": 2,
                "data_realizacao": "2026-04-01",
                "data_vencimento": "2026-10-01",
            },
            treinamento_id=55,
        )

    assert exc.value.code == "treinamento_program_record_requires_program_flow"
