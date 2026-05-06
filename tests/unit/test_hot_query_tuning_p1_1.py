from __future__ import annotations

from datetime import date

from backend.src.controle_treinamentos.repositories.training_program import (
    fetch_training_program_record_list,
    fetch_training_program_tripulantes,
)


class _CaptureCursor:
    def __init__(self, *, rows=None):
        self._rows = rows or []

    def fetchall(self):
        return self._rows


class _CaptureDB:
    def __init__(self, *, rows=None):
        self.rows = rows or []
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, query, params=()):
        self.calls.append((query, params))
        return _CaptureCursor(rows=self.rows)


def test_fetch_training_program_record_list_reduces_join_fanout(monkeypatch):
    monkeypatch.setattr(
        "backend.src.controle_treinamentos.repositories.training_program.business_today",
        lambda: date(2026, 4, 16),
    )
    db = _CaptureDB(
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
                "total_anexos": 2,
                "ctac_required": True,
            }
        ]
    )

    rows = fetch_training_program_record_list(
        db,
        tripulante_id=7,
        tipo_treinamento_id=4,
        aeronave_modelo_snapshot="King Air B200/200/C90A/C90GT",
    )
    query, params = db.calls[0]

    assert "LEFT JOIN treinamento_anexos_pdf" not in query
    assert "LEFT JOIN horas_voo_aeronave" not in query
    assert "COUNT(a.id)" not in query
    assert "GROUP BY" not in query
    assert "WITH ctac_refs AS" in query
    assert "SELECT COUNT(*)" in query
    assert "EXISTS(" not in query
    assert "LEFT JOIN LATERAL" not in query
    assert "LEFT JOIN pilotos p ON p.tripulante_id = c.id" in query
    assert "LEFT JOIN ctac_refs" in query
    assert "POSITION('conforme ctac'" in query
    assert params == (7, 4, "King Air B200/200/C90A/C90GT")
    assert rows[0]["total_anexos"] == 2
    assert rows[0]["ctac_required"] is True
    assert rows[0]["status_calculado"] == "regular"


def test_fetch_training_program_tripulantes_filters_by_pilot_base_owner_only():
    db = _CaptureDB()

    rows = fetch_training_program_tripulantes(db, base="SSA")
    query, params = db.calls[0]

    assert rows == []
    assert "LEFT JOIN pilotos p ON p.tripulante_id = c.id" in query
    assert "LEFT JOIN bases pb ON pb.id = p.base_id" in query
    assert "LOWER(TRIM(COALESCE(pb.nome, ''))) = LOWER(%s)" in query
    assert "c.base" not in query
    assert params == ("SSA",)


def test_fetch_training_program_record_list_filters_by_pilot_base_owner_only():
    db = _CaptureDB()

    rows = fetch_training_program_record_list(db, base="SSA")
    query, params = db.calls[0]

    assert rows == []
    assert "LEFT JOIN pilotos p ON p.tripulante_id = c.id" in query
    assert "LEFT JOIN bases pb ON pb.id = p.base_id" in query
    assert "LOWER(TRIM(COALESCE(pb.nome, ''))) = LOWER(%s)" in query
    assert "t.base" not in query
    assert params == ("SSA",)
