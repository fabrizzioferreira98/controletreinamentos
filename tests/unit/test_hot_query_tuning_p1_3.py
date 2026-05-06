from __future__ import annotations

from collections import Counter
from datetime import date

from backend.src.controle_treinamentos.db.training_program_seed import load_training_program_reference
from backend.src.controle_treinamentos.repositories.training_program import (
    fetch_training_program_hour_for_type_and_model,
    fetch_training_program_record_list,
)


class _CaptureCursor:
    def __init__(self, *, rows=None, row=None):
        self._rows = rows or []
        self._row = row

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._row


class _CaptureDB:
    def __init__(self, *, rows=None, row=None):
        self.rows = rows or []
        self.row = row
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, query, params=()):
        self.calls.append((query, params))
        return _CaptureCursor(rows=self.rows, row=self.row)


def test_aeronave_modelo_hot_queries_still_use_function_wrapped_predicates(monkeypatch):
    monkeypatch.setattr(
        "backend.src.controle_treinamentos.repositories.training_program.business_today",
        lambda: date(2026, 4, 16),
    )

    hour_db = _CaptureDB(
        row={
            "id": 6,
            "tipo_treinamento_id": 4,
            "tipo_treinamento_nome": "Treinamento Periodico",
            "aeronave_modelo": "King Air B200/200/C90A/C90GT",
            "solo_horas": 8.0,
            "voo_pic_sic_horas": 3.0,
            "voo_crew_horas": 0.0,
            "observacao": "",
            "ativo": 1,
        }
    )

    fetch_training_program_hour_for_type_and_model(
        hour_db,
        tipo_treinamento_id=4,
        aeronave_modelo="King Air B200/200/C90A/C90GT",
    )
    hour_query, hour_params = hour_db.calls[0]

    assert "WHERE hv.tipo_treinamento_id = %s" in hour_query
    assert "LOWER(hv.aeronave_modelo) = LOWER(%s)" in hour_query
    assert "ORDER BY hv.id" in hour_query
    assert "LIMIT 1" in hour_query
    assert hour_params == (4, "King Air B200/200/C90A/C90GT")

    record_db = _CaptureDB(
        rows=[
            {
                "id": 88,
                "tripulante_id": 7,
                "equipamento_id": 3,
                "tipo_treinamento_id": 4,
                "segmento_teorico_id": 26,
                "aeronave_modelo_snapshot": "King Air B200/200/C90A/C90GT",
                "ctac_solo_horas": None,
                "ctac_voo_pic_sic_horas": None,
                "ctac_voo_crew_horas": None,
                "data_realizacao": date(2026, 4, 1),
                "data_vencimento": date(2027, 4, 1),
                "observacao": "",
                "tripulante_nome": "Lucas Silva",
                "tripulante_matricula": "123456",
                "tipo_treinamento_nome": "Treinamento Periodico",
                "tipo_treinamento_codigo": "T4",
                "nome_segmento": "Operacoes Autorizadas",
                "modelo_segmento": "Gerais",
                "periodicidade_meses": 12,
                "total_anexos": 1,
                "ctac_required": False,
            }
        ]
    )

    fetch_training_program_record_list(
        record_db,
        tipo_treinamento_id=4,
        aeronave_modelo_snapshot="King Air B200/200/C90A/C90GT",
    )
    record_query, record_params = record_db.calls[0]

    assert "LOWER(COALESCE(t.aeronave_modelo, '')) = LOWER(%s)" in record_query
    assert "WITH ctac_refs AS" in record_query
    assert "LOWER(hv.aeronave_modelo) AS aeronave_modelo_key" in record_query
    assert "ctac_refs.aeronave_modelo_key = LOWER(COALESCE(t.aeronave_modelo, ''))" in record_query
    assert "ORDER BY" in record_query
    assert record_params == (4, "King Air B200/200/C90A/C90GT")


def test_aeronave_modelo_seed_selectivity_is_by_type_plus_model_not_model_alone():
    reference = load_training_program_reference()
    horas_voo = [
        row
        for row in reference["horas_voo"]
        if (row.get("tipo_treinamento_id") or "").isdigit() and (row.get("aeronave_modelo") or "").strip()
    ]

    model_counts = Counter(row["aeronave_modelo"] for row in horas_voo)
    pair_counts = Counter((row["tipo_treinamento_id"], row["aeronave_modelo"]) for row in horas_voo)

    assert any(count > 1 for count in model_counts.values())
    assert all(count == 1 for count in pair_counts.values())
    assert model_counts["King Air B200/200/C90A/C90GT"] > 1
