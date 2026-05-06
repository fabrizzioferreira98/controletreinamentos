from __future__ import annotations

import pytest

from backend.src.controle_treinamentos.application import financeiro_observabilidade as observabilidade_app
from backend.src.controle_treinamentos.repositories import financeiro_observabilidade as observabilidade_repo


class _Cursor:
    def __init__(self, rows, description=None):
        self._rows = rows
        self.description = description or []

    def fetchall(self):
        return self._rows


class _FakeDB:
    def __init__(self, rows, description=None):
        self.rows = rows
        self.description = description or []
        self.calls = []

    def execute(self, query, params):
        self.calls.append((query, params))
        return _Cursor(self.rows, description=self.description)


def _assert_query_is_read_only(query: str) -> None:
    normalized = " ".join(query.lower().split())
    assert normalized.startswith("select")
    assert " insert " not in f" {normalized} "
    assert " update " not in f" {normalized} "
    assert " delete " not in f" {normalized} "
    assert " drop " not in f" {normalized} "
    assert " truncate " not in f" {normalized} "


def test_repository_audit_list_query_is_read_only_and_scoped_to_finance_events():
    db = _FakeDB(rows=[])
    observabilidade_repo.listar_eventos_auditoria_financeira(
        db,
        competencia="2026-04",
        entity_type="finance_mission",
        entity_id=101,
        event_name="finance.mission.created",
        limit=20,
        offset=0,
    )

    assert len(db.calls) == 1
    query, params = db.calls[0]
    _assert_query_is_read_only(query)
    assert "FROM auditoria_eventos" in query
    assert "ae.acao LIKE %s" in query
    assert "ORDER BY ae.realizado_em DESC, ae.id DESC" in query
    assert "finance.%" in params
    assert params[-2:] == (20, 0)


def test_repository_divergences_list_query_is_read_only():
    db = _FakeDB(rows=[])
    observabilidade_repo.listar_divergencias_financeiras(
        db,
        competencia="2026-04",
        status="aberta",
        severidade="alta",
        codigo="parametro_ausente",
        limit=15,
        offset=5,
    )

    assert len(db.calls) == 1
    query, params = db.calls[0]
    _assert_query_is_read_only(query)
    assert "FROM financeiro_divergencias fd" in query
    assert "fd.org_id = %s" in query
    assert "fd.competencia = %s" in query
    assert "fd.status = %s" in query
    assert "fd.severidade = %s" in query
    assert "fd.codigo = %s" in query
    assert params[-2:] == (15, 5)


def test_repository_audit_list_maps_tuple_rows_by_column_name():
    description = [
        ("id", None, None, None, None, None, None),
        ("org_id", None, None, None, None, None, None),
        ("event_name", None, None, None, None, None, None),
        ("entity_type", None, None, None, None, None, None),
        ("entity_id", None, None, None, None, None, None),
        ("competencia", None, None, None, None, None, None),
        ("permission", None, None, None, None, None, None),
        ("actor_user_id", None, None, None, None, None, None),
        ("before", None, None, None, None, None, None),
        ("after", None, None, None, None, None, None),
        ("metadata", None, None, None, None, None, None),
        ("created_at", None, None, None, None, None, None),
    ]
    db = _FakeDB(
        rows=[
            (
                1,
                "default_single_tenant",
                "finance.mission.recalculated",
                "finance_mission",
                10,
                "2026-04",
                "finance:missions:recalculate",
                7,
                {"status": "antes"},
                {"status": "depois"},
                {"origin": "runtime"},
                "2026-04-10T12:00:00+00:00",
            )
        ],
        description=description,
    )

    rows = observabilidade_repo.listar_eventos_auditoria_financeira(db, limit=5, offset=0)

    assert rows == [
        {
            "id": 1,
            "org_id": "default_single_tenant",
            "event_name": "finance.mission.recalculated",
            "entity_type": "finance_mission",
            "entity_id": 10,
            "competencia": "2026-04",
            "permission": "finance:missions:recalculate",
            "actor_user_id": 7,
            "before": {"status": "antes"},
            "after": {"status": "depois"},
            "metadata": {"origin": "runtime"},
            "created_at": "2026-04-10T12:00:00+00:00",
        }
    ]


def test_use_case_clamps_limit_and_preserves_empty_result(monkeypatch):
    captured = {}

    def _rows(_db, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(observabilidade_app, "listar_eventos_auditoria_financeira_rows", _rows)

    result = observabilidade_app.listar_eventos_auditoria_financeira(
        db=object(),
        competencia="2026-04",
        limit="999",
        offset="0",
    )

    assert captured["competencia"] == "2026-04"
    assert captured["limit"] == 100
    assert captured["offset"] == 0
    assert result["items"] == []
    assert result["pagination"]["limit"] == 100
    assert result["pagination"]["total"] == 0


def test_use_case_rejects_invalid_limit_and_severity():
    with pytest.raises(observabilidade_app.ObservabilidadeFinanceiraInvalidaErro) as audit_error:
        observabilidade_app.listar_eventos_auditoria_financeira(
            db=object(),
            limit="abc",
        )
    assert audit_error.value.code == "finance_observability_limit_invalid"

    with pytest.raises(observabilidade_app.ObservabilidadeFinanceiraInvalidaErro) as divergence_error:
        observabilidade_app.listar_divergencias_financeiras(
            db=object(),
            severidade="critica",
        )
    assert divergence_error.value.code == "finance_divergence_severity_invalid"
