from __future__ import annotations

import re
from pathlib import Path

from backend.src.controle_treinamentos.application import tripulantes as tripulantes_app
from backend.src.controle_treinamentos.db import seeder
from backend.src.controle_treinamentos.repositories.tripulantes import build_tripulante_filters
from backend.src.controle_treinamentos.service_layers.tripulante_operational_status import (
    TRIPULANTE_BASE_SNAPSHOT_COMPAT_SOURCE,
    TRIPULANTE_OPERATIONAL_BASE_OWNER,
    TRIPULANTE_OPERATIONAL_STATUS_OWNER,
    TRIPULANTE_STATUS_BASE_OWNER_DECISION,
    TRIPULANTE_STATUS_SNAPSHOT_COMPAT_SOURCE,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = PROJECT_ROOT / "backend" / "src"
FORBIDDEN_PRIMARY_SNAPSHOT_PATTERNS = {
    "base_coalesce_fallback": re.compile(r"COALESCE\(\s*pb\.nome\s*,\s*[ct]\.base\s*\)", re.IGNORECASE),
    "status_unlinked_fallback": re.compile(
        r"OR\s*\(\s*p\.tripulante_id\s+IS\s+NULL\s+AND\s+[ct]\.status\b",
        re.IGNORECASE,
    ),
    "base_unlinked_fallback": re.compile(
        r"OR\s*\(\s*p\.tripulante_id\s+IS\s+NULL\s+AND\s+LOWER\(TRIM\(COALESCE\([ct]\.base",
        re.IGNORECASE,
    ),
    "base_alias_from_snapshot": re.compile(r"\b[ct]\.base\s+AS\s+(?!base_snapshot_compat\b)\w*base\b", re.IGNORECASE),
    "status_alias_from_snapshot": re.compile(
        r"\b[ct]\.status\s+AS\s+(?!status_snapshot_compat\b)\w*status\b",
        re.IGNORECASE,
    ),
}


class _Cursor:
    def __init__(self, *, row=None, rows=None):
        self._row = row
        self._rows = rows or []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _SyncDB:
    def __init__(self, *, linked_pilot=None, mapped_base=None, active_base=None):
        self.linked_pilot = linked_pilot
        self.mapped_base = mapped_base
        self.active_base = active_base
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, query, params=()):
        compact = " ".join(query.split())
        self.calls.append((compact, params))
        if compact == "SELECT id, base_id, status FROM pilotos WHERE tripulante_id = %s":
            return _Cursor(row=self.linked_pilot)
        if compact == "SELECT id, nome, uf FROM bases WHERE id = %s AND ativa = TRUE":
            return _Cursor(row=self.active_base)
        if compact == "SELECT id FROM bases WHERE ativa = TRUE AND LOWER(nome) = LOWER(%s)":
            return _Cursor(row=self.mapped_base)
        if compact.startswith("UPDATE pilotos SET nome = %s, matricula = %s, base_id = %s, status = %s WHERE id = %s"):
            return _Cursor()
        if compact.startswith("INSERT INTO pilotos (nome, matricula, tripulante_id, base_id, status)"):
            return _Cursor()
        if compact.startswith("UPDATE tripulantes SET base = %s, status = %s WHERE id = %s"):
            return _Cursor()
        raise AssertionError(f"Unexpected query: {compact}")


class _CaptureDB:
    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, query, params=()):
        self.calls.append((" ".join(query.split()), params))
        return _Cursor()


def _find_call(calls, fragment: str) -> tuple[str, tuple]:
    for query, params in calls:
        if fragment in query:
            return query, params
    raise AssertionError(f"Call containing {fragment!r} not found")


def test_backend_queries_do_not_promote_tripulante_snapshots_as_primary_source():
    offenders = []
    for path in BACKEND_SRC.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        for label, pattern in FORBIDDEN_PRIMARY_SNAPSHOT_PATTERNS.items():
            if pattern.search(source):
                offenders.append(f"{path.relative_to(PROJECT_ROOT)}::{label}")

    assert offenders == []


def test_sync_linked_pilot_from_tripulante_applies_submitted_status_and_preserves_base_owner(monkeypatch):
    db = _SyncDB(
        linked_pilot={"id": 31, "base_id": 4, "status": "folga"},
        active_base={"id": 4, "nome": "Sao Paulo", "uf": "SP"},
    )
    monkeypatch.setattr(
        tripulantes_app,
        "ensure_base_exists",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("linked pilot should not ensure snapshot base")),
    )
    monkeypatch.setattr(tripulantes_app, "resolve_tripulante_pilot_matricula", lambda *_args, **_kwargs: "MAT-000031")

    tripulantes_app.sync_linked_pilot_from_tripulante(
        db,
        tripulante_id=7,
        nome="Lucas Silva",
        licenca_anac="123456",
        base_nome="Sao Paulo",
        status_text="Ativo",
        is_active=True,
    )

    _query, pilot_params = _find_call(db.calls, "UPDATE pilotos SET nome = %s, matricula = %s, base_id = %s, status = %s")
    assert pilot_params[2] == 4
    assert pilot_params[3] == "ativo"
    _query, snapshot_params = _find_call(db.calls, "UPDATE tripulantes SET base = %s, status = %s WHERE id = %s")
    assert snapshot_params == ("Sao Paulo", "Ativo", 7)


def test_sync_linked_pilot_from_tripulante_regression_training_to_active_with_exceptional_flag(monkeypatch):
    db = _SyncDB(
        linked_pilot={"id": 33, "base_id": 4, "status": "treinamento"},
        active_base={"id": 4, "nome": "Sao Paulo", "uf": "SP"},
    )
    monkeypatch.setattr(
        tripulantes_app,
        "ensure_base_exists",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("linked pilot should not ensure snapshot base")),
    )
    monkeypatch.setattr(tripulantes_app, "resolve_tripulante_pilot_matricula", lambda *_args, **_kwargs: "MAT-000033")

    tripulantes_app.sync_linked_pilot_from_tripulante(
        db,
        tripulante_id=33,
        nome="Tripulante Excepcional",
        licenca_anac="333333",
        base_nome="Sao Paulo",
        status_text="Ativo",
        is_active=True,
    )

    _query, pilot_params = _find_call(db.calls, "UPDATE pilotos SET nome = %s, matricula = %s, base_id = %s, status = %s")
    assert pilot_params[3] == "ativo"
    _query, snapshot_params = _find_call(db.calls, "UPDATE tripulantes SET base = %s, status = %s WHERE id = %s")
    assert snapshot_params == ("Sao Paulo", "Ativo", 33)


def test_sync_linked_pilot_from_tripulante_inactivation_forces_afastado(monkeypatch):
    db = _SyncDB(
        linked_pilot={"id": 32, "base_id": 5, "status": "ativo"},
        active_base={"id": 5, "nome": "Manaus", "uf": "AM"},
    )
    monkeypatch.setattr(
        tripulantes_app,
        "ensure_base_exists",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("linked pilot should not ensure snapshot base")),
    )
    monkeypatch.setattr(tripulantes_app, "resolve_tripulante_pilot_matricula", lambda *_args, **_kwargs: "MAT-000032")

    tripulantes_app.sync_linked_pilot_from_tripulante(
        db,
        tripulante_id=9,
        nome="Tripulante Inativado",
        licenca_anac="654321",
        base_nome="Manaus",
        status_text="Folga",
        is_active=False,
    )

    _query, pilot_params = _find_call(db.calls, "UPDATE pilotos SET nome = %s, matricula = %s, base_id = %s, status = %s")
    assert pilot_params[2] == 5
    assert pilot_params[3] == "afastado"
    _query, snapshot_params = _find_call(db.calls, "UPDATE tripulantes SET base = %s, status = %s WHERE id = %s")
    assert snapshot_params == ("Manaus", "Afastado", 9)


def test_sync_linked_pilot_from_tripulante_bootstraps_missing_pilot_from_snapshot_base(monkeypatch):
    db = _SyncDB(active_base={"id": 8, "nome": "Manaus", "uf": "AM"})
    monkeypatch.setattr(tripulantes_app, "ensure_base_exists", lambda *_args, **_kwargs: {"id": 8})
    monkeypatch.setattr(tripulantes_app, "resolve_tripulante_pilot_matricula", lambda *_args, **_kwargs: "MAT-000011")

    tripulantes_app.sync_linked_pilot_from_tripulante(
        db,
        tripulante_id=11,
        nome="Tripulante Novo",
        licenca_anac="111111",
        base_nome="Manaus",
        status_text="Ativo",
        is_active=True,
    )

    _query, snapshot_params = _find_call(db.calls, "UPDATE tripulantes SET base = %s, status = %s WHERE id = %s")
    assert snapshot_params == ("Manaus", "Ativo", 11)
    _query, insert_params = _find_call(db.calls, "INSERT INTO pilotos (nome, matricula, tripulante_id, base_id, status)")
    assert insert_params[3] == 8
    assert insert_params[4] == "ativo"


def test_owner_decision_is_unique_and_snapshot_sources_are_residual():
    assert TRIPULANTE_OPERATIONAL_STATUS_OWNER == "pilotos.status"
    assert TRIPULANTE_OPERATIONAL_BASE_OWNER == "pilotos.base_id"
    assert TRIPULANTE_STATUS_SNAPSHOT_COMPAT_SOURCE == "tripulantes.status"
    assert TRIPULANTE_BASE_SNAPSHOT_COMPAT_SOURCE == "tripulantes.base"
    assert TRIPULANTE_STATUS_BASE_OWNER_DECISION["status"]["canonical_owner"] == "pilotos.status"
    assert TRIPULANTE_STATUS_BASE_OWNER_DECISION["base"]["canonical_owner"] == "pilotos.base_id"
    assert TRIPULANTE_STATUS_BASE_OWNER_DECISION["status"]["snapshot_role"] == "compat_residual"
    assert TRIPULANTE_STATUS_BASE_OWNER_DECISION["base"]["snapshot_role"] == "compat_residual"


def test_build_tripulante_filters_uses_pilot_status_owner_only():
    where, params = build_tripulante_filters(status="Ferias")

    assert "LOWER(TRIM(COALESCE(p.status, ''))) = %s" in where
    assert "t.status" not in where
    assert params == ("ferias",)


def test_build_tripulante_filters_uses_pilot_base_owner_only():
    where, params = build_tripulante_filters(base="Manaus")

    assert "LOWER(TRIM(COALESCE(pb.nome, ''))) = LOWER(%s)" in where
    assert "t.base" not in where
    assert params == ("Manaus",)


def test_sync_tripulantes_to_pilotos_preserves_existing_pilot_status_and_base_owner():
    db = _CaptureDB()

    seeder.sync_tripulantes_to_pilotos(db)

    first_query, _params = db.calls[0]
    assert "UPDATE pilotos p SET nome = t.nome" in first_query
    assert "base_id =" not in first_query
    assert "JOIN bases b" not in first_query
    assert "status = CASE" not in first_query
    second_query, _params = db.calls[1]
    assert "CASE LOWER(TRIM(t.status))" in second_query
