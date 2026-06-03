from __future__ import annotations

from pathlib import Path

import pytest

from backend.src.controle_treinamentos.application import tripulante_operational_periods as periods_app


class _FakeConn:
    def __init__(self):
        self.rolled_back = False

    def rollback(self):
        self.rolled_back = True


class _FakeDB:
    def __init__(self):
        self.conn = _FakeConn()
        self.committed = False

    def commit(self):
        self.committed = True


def test_create_tripulante_operational_period_persists_valid_vacation(monkeypatch):
    db = _FakeDB()
    captured = {}

    monkeypatch.setattr(periods_app, "get_db", lambda: db)
    monkeypatch.setattr(periods_app, "tripulante_exists", lambda _db, *, tripulante_id: tripulante_id == 11)
    monkeypatch.setattr(periods_app, "find_overlapping_operational_period", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(periods_app, "audit_event", lambda *_args, **_kwargs: None)

    def fake_insert_operational_period(_db, *, data):
        captured.update(data)
        return {
            "id": 41,
            "tripulante_id": data["tripulante_id"],
            "tipo": data["tipo"],
            "data_inicio": data["data_inicio"],
            "data_fim": data["data_fim"],
            "status": "ativo",
            "observacao": data["observacao"],
            "criado_em": None,
            "cancelado_em": None,
        }

    monkeypatch.setattr(periods_app, "insert_operational_period", fake_insert_operational_period)

    result = periods_app.create_tripulante_operational_period(
        tripulante_id=11,
        actor_user_id=21,
        payload={
            "tipo": "ferias",
            "data_inicio": "2026-06-01",
            "data_fim": "2026-06-10",
            "observacao": "Ferias aprovadas RH",
        },
    )

    assert result["item"]["id"] == 41
    assert result["item"]["status"] == "ativo"
    assert captured["tripulante_id"] == 11
    assert captured["criado_por"] == 21
    assert captured["data_inicio"] == "2026-06-01"
    assert captured["data_fim"] == "2026-06-10"
    assert db.committed is True
    assert db.conn.rolled_back is False


def test_create_tripulante_operational_period_rejects_invalid_date_range(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(periods_app, "get_db", lambda: db)
    monkeypatch.setattr(periods_app, "tripulante_exists", lambda *_args, **_kwargs: True)

    with pytest.raises(periods_app.TripulanteOperationalPeriodValidationError) as excinfo:
        periods_app.create_tripulante_operational_period(
            tripulante_id=11,
            actor_user_id=21,
            payload={"tipo": "ferias", "data_inicio": "2026-06-10", "data_fim": "2026-06-01"},
        )

    assert excinfo.value.code == "tripulante_periodo_operacional_validation_error"
    assert "f\u00e9rias" in excinfo.value.message
    assert "\u00c3" not in excinfo.value.message
    assert db.committed is False


def test_create_tripulante_operational_period_blocks_active_overlap(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(periods_app, "get_db", lambda: db)
    monkeypatch.setattr(periods_app, "tripulante_exists", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        periods_app,
        "find_overlapping_operational_period",
        lambda *_args, **_kwargs: {"id": 40, "data_inicio": "2026-06-05", "data_fim": "2026-06-12"},
    )

    with pytest.raises(periods_app.TripulanteOperationalPeriodConflictError) as excinfo:
        periods_app.create_tripulante_operational_period(
            tripulante_id=11,
            actor_user_id=21,
            payload={"tipo": "ferias", "data_inicio": "2026-06-01", "data_fim": "2026-06-10"},
        )

    assert excinfo.value.code == "tripulante_periodo_operacional_overlap"
    assert db.committed is False


def test_operational_period_lifecycle_create_list_and_cancel(monkeypatch):
    db = _FakeDB()
    rows = []
    next_id = {"value": 41}

    monkeypatch.setattr(periods_app, "get_db", lambda: db)
    monkeypatch.setattr(periods_app, "tripulante_exists", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(periods_app, "audit_event", lambda *_args, **_kwargs: None)

    def fake_find_overlap(_db, *, tripulante_id, data_inicio, data_fim):
        for row in rows:
            if (
                row["tripulante_id"] == tripulante_id
                and row["status"] != "cancelado"
                and row["data_inicio"] <= data_fim
                and row["data_fim"] >= data_inicio
            ):
                return row
        return None

    def fake_insert(_db, *, data):
        row = {
            "id": next_id["value"],
            "tripulante_id": data["tripulante_id"],
            "tipo": data["tipo"],
            "data_inicio": data["data_inicio"],
            "data_fim": data["data_fim"],
            "status": "ativo",
            "observacao": data["observacao"],
            "criado_em": None,
            "cancelado_em": None,
        }
        rows.append(row)
        next_id["value"] += 1
        return row

    def fake_fetch_many(_db, *, tripulante_id):
        return [row for row in rows if row["tripulante_id"] == tripulante_id]

    def fake_fetch_one(_db, *, tripulante_id, periodo_id):
        return next((row for row in rows if row["tripulante_id"] == tripulante_id and row["id"] == periodo_id), None)

    def fake_cancel(_db, *, tripulante_id, periodo_id, cancelado_por):
        row = fake_fetch_one(_db, tripulante_id=tripulante_id, periodo_id=periodo_id)
        if not row or row["status"] == "cancelado":
            return None
        row["status"] = "cancelado"
        row["cancelado_por"] = cancelado_por
        row["cancelado_em"] = "2026-06-01T12:00:00"
        return row

    monkeypatch.setattr(periods_app, "find_overlapping_operational_period", fake_find_overlap)
    monkeypatch.setattr(periods_app, "insert_operational_period", fake_insert)
    monkeypatch.setattr(periods_app, "fetch_operational_periods_by_tripulante", fake_fetch_many)
    monkeypatch.setattr(periods_app, "fetch_operational_period", fake_fetch_one)
    monkeypatch.setattr(periods_app, "cancel_operational_period", fake_cancel)

    created = periods_app.create_tripulante_operational_period(
        tripulante_id=11,
        actor_user_id=21,
        payload={"tipo": "ferias", "data_inicio": "2026-06-01", "data_fim": "2026-06-10"},
    )
    listed = periods_app.list_tripulante_operational_periods(tripulante_id=11)
    cancelled = periods_app.cancel_tripulante_operational_period(
        tripulante_id=11,
        periodo_id=created["item"]["id"],
        actor_user_id=21,
    )

    assert listed["items"] == [created["item"]]
    assert cancelled["operation"] == "cancelled"
    assert cancelled["item"]["status"] == "cancelado"
    assert periods_app.list_tripulante_operational_periods(tripulante_id=11)["items"][0]["status"] == "cancelado"


def test_operational_periods_migration_repairs_partial_existing_table():
    source = Path("backend/src/controle_treinamentos/db/migrations.py").read_text(encoding="utf-8")

    for column in ("criado_em", "cancelado_por", "cancelado_em", "motivo_status"):
        assert f"ALTER TABLE tripulante_periodos_operacionais ADD COLUMN IF NOT EXISTS {column}" in source
