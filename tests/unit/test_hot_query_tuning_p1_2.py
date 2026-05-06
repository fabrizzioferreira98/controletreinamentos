from __future__ import annotations

from datetime import date

from backend.src.controle_treinamentos.contracts.relatorios import (
    habilitacoes_report_to_html_context,
    serialize_habilitacoes_report,
)
from backend.src.controle_treinamentos.repositories.dashboard_cache import (
    build_habilitacoes_consolidadas_context,
)


class _CaptureCursor:
    def __init__(self, *, rows=None):
        self._rows = rows or []

    def fetchall(self):
        return self._rows


class _CaptureDB:
    def __init__(self, *rows_by_call):
        self._rows_by_call = list(rows_by_call)
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, query, params=()):
        self.calls.append((query, params))
        index = len(self.calls) - 1
        rows = self._rows_by_call[index] if index < len(self._rows_by_call) else []
        return _CaptureCursor(rows=rows)


def _prepare_cache_boundaries(monkeypatch):
    monkeypatch.setattr(
        "backend.src.controle_treinamentos.repositories.dashboard_cache.business_today",
        lambda: date(2026, 4, 16),
    )
    monkeypatch.setattr(
        "backend.src.controle_treinamentos.repositories.dashboard_cache.fetch_cached_rows",
        lambda *_args, **_kwargs: [{"id": 2, "nome": "CQ IFR"}],
    )
    monkeypatch.setattr(
        "backend.src.controle_treinamentos.repositories.dashboard_cache.fetch_unique_bases",
        lambda _db: [{"nome": "SSA", "uf": "BA"}],
    )
    monkeypatch.setattr(
        "backend.src.controle_treinamentos.repositories.dashboard_cache.get_panel_cache",
        lambda _key: None,
    )
    monkeypatch.setattr(
        "backend.src.controle_treinamentos.repositories.dashboard_cache.set_panel_cache",
        lambda *_args, **_kwargs: None,
    )


def test_build_habilitacoes_context_splits_query_cost_from_mounting(monkeypatch):
    _prepare_cache_boundaries(monkeypatch)
    db = _CaptureDB(
        [
            {
                "tripulante_id": 7,
                "tripulante_nome": "Lucas Silva",
                "tripulante_base": "SSA",
                "tripulante_cargo": "",
            },
            {
                "tripulante_id": 4,
                "tripulante_nome": "Ana Lima",
                "tripulante_base": "SSA",
                "tripulante_cargo": "",
            },
        ],
        [
            {
                "tripulante_id": 7,
                "treinamento_id": 71,
                "tipo_treinamento_id": 2,
                "habilitacao_nome": "CQ IFR",
                "data_vencimento": date(2026, 5, 30),
            },
            {
                "tripulante_id": 4,
                "treinamento_id": 41,
                "tipo_treinamento_id": 2,
                "habilitacao_nome": "Revalidacao ANAC",
                "data_vencimento": date(2026, 4, 20),
            },
        ],
    )

    context = build_habilitacoes_consolidadas_context(
        db,
        nome="",
        base="SSA",
        status="",
        tipo="2",
        ordenacao="vencimento",
    )
    report = serialize_habilitacoes_report(context)
    legacy = habilitacoes_report_to_html_context(report)

    assert len(db.calls) == 2

    tripulante_query, tripulante_params = db.calls[0]
    assert "FROM tripulantes c" in tripulante_query
    assert "LEFT JOIN pilotos p ON p.tripulante_id = c.id" in tripulante_query
    assert "LEFT JOIN bases pb ON pb.id = p.base_id" in tripulante_query
    assert "pb.nome AS tripulante_base" in tripulante_query
    assert "COALESCE(pb.nome, c.base)" not in tripulante_query
    assert "JOIN treinamentos" not in tripulante_query
    assert "ORDER BY" not in tripulante_query
    assert tripulante_params == ("SSA",)

    training_query, training_params = db.calls[1]
    assert "FROM treinamentos t" in training_query
    assert "JOIN tipos_treinamento tt" in training_query
    assert "JOIN tripulantes" not in training_query
    assert "ORDER BY" not in training_query
    assert "t.tripulante_id = ANY(%s)" in training_query
    assert "t.tipo_treinamento_id = %s" in training_query
    assert training_params == ([7, 4], 2)

    assert [group["tripulante_nome"] for group in context["tripulantes_grouped"]] == [
        "Ana Lima",
        "Lucas Silva",
    ]
    assert report["summary"]["total_tripulantes"] == 2
    assert report["summary"]["total_habilitacoes"] == 2
    assert report["items"][0]["habilitacoes"][0]["status_key"] == "critico_15"
    assert "status_class" not in report["items"][0]["habilitacoes"][0]
    assert legacy["tripulantes_grouped"][0]["habilitacoes"][0]["status_class"] == "status-red"


def test_build_habilitacoes_context_returns_honest_empty_habilitacoes(monkeypatch):
    _prepare_cache_boundaries(monkeypatch)
    db = _CaptureDB(
        [
            {
                "tripulante_id": 11,
                "tripulante_nome": "Carla Rocha",
                "tripulante_base": "SSA",
                "tripulante_cargo": "",
            }
        ],
        [],
    )

    context = build_habilitacoes_consolidadas_context(
        db,
        nome="Carla",
        base="SSA",
        status="",
        tipo="",
        ordenacao="criticidade",
    )
    report = serialize_habilitacoes_report(context)
    legacy = habilitacoes_report_to_html_context(report)

    assert len(db.calls) == 2
    tripulante_query, tripulante_params = db.calls[0]
    assert "LEFT JOIN pilotos p ON p.tripulante_id = c.id" in tripulante_query
    assert "LEFT JOIN bases pb ON pb.id = p.base_id" in tripulante_query
    assert tripulante_params == ("%carla%", "SSA")
    training_query, training_params = db.calls[1]
    assert "FROM treinamentos t" in training_query
    assert "ORDER BY" not in training_query
    assert training_params == ([11],)

    assert report["items"][0]["has_habilitacoes"] is False
    assert report["items"][0]["habilitacoes"] == []
    assert legacy["tripulantes_grouped"][0]["has_habilitacoes"] is False
    assert legacy["tripulantes_grouped"][0]["habilitacoes"] == []
