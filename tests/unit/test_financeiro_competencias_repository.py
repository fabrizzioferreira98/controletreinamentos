from __future__ import annotations

import ast
from pathlib import Path

from backend.src.controle_treinamentos.contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT
from backend.src.controle_treinamentos.repositories import financeiro_competencias

REPO_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_FILE = (
    REPO_ROOT / "backend" / "src" / "controle_treinamentos" / "repositories" / "financeiro_competencias.py"
)


class _FakeCursor:
    def __init__(self, row=None, rows=None):
        self._row = row
        self._rows = rows or []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _FakeDB:
    def __init__(self, cursors):
        self._cursors = list(cursors)
        self.executed = []

    def execute(self, query, params=()):
        self.executed.append((query, params))
        if not self._cursors:
            raise AssertionError(f"Unexpected query: {query}")
        return self._cursors.pop(0)


def _import_candidates(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        candidates = [module] if module else []
        candidates.extend(f"{module}.{alias.name}" if module else alias.name for alias in node.names)
        return candidates
    return []


def test_repository_imports_only_persistence_safe_dependencies():
    tree = ast.parse(REPOSITORY_FILE.read_text(encoding="utf-8"), filename=str(REPOSITORY_FILE))
    banned_fragments = (
        "flask",
        "api",
        "application",
        "auth",
        "audit",
        "financeiro_audit_events",
        "frontend",
        "service",
        "use_case",
    )
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Import | ast.ImportFrom):
            continue
        for candidate in _import_candidates(node):
            if any(fragment in candidate for fragment in banned_fragments):
                violations.append(f"{node.lineno}: import '{candidate}'")

    assert violations == []


def test_competencia_repository_upserts_closes_reopens_and_lists_divergences_with_org_scope():
    db = _FakeDB(
        [
            _FakeCursor(row={"id": 1, "org_id": FINANCE_ORG_SCOPE_DEFAULT, "status": "aberta"}),
            _FakeCursor(row={"id": 1, "org_id": FINANCE_ORG_SCOPE_DEFAULT, "status": "em_conferencia"}),
            _FakeCursor(row={"id": 1, "org_id": FINANCE_ORG_SCOPE_DEFAULT, "status": "fechada"}),
            _FakeCursor(row={"id": 1, "org_id": FINANCE_ORG_SCOPE_DEFAULT, "status": "reaberta"}),
            _FakeCursor(rows=[{"id": 9, "org_id": FINANCE_ORG_SCOPE_DEFAULT}]),
        ]
    )

    fetched = financeiro_competencias.fetch_competencia_financeira(db, competencia="2026-04")
    recalculated = financeiro_competencias.upsert_competencia_em_conferencia(
        db,
        competencia="2026-04",
        totals={"total_geral": "100.00"},
    )
    closed = financeiro_competencias.fechar_competencia_financeira(
        db,
        competencia="2026-04",
        totals={"total_geral": "100.00"},
        snapshot={"missoes_operacionais": []},
        closed_by=501,
    )
    reopened = financeiro_competencias.reabrir_competencia_financeira(
        db,
        competencia="2026-04",
        motivo="ajuste operacional",
        reopened_by=501,
    )
    divergences = financeiro_competencias.listar_divergencias_competencia(db, competencia="2026-04")

    assert fetched["status"] == "aberta"
    assert recalculated["status"] == "em_conferencia"
    assert closed["status"] == "fechada"
    assert reopened["status"] == "reaberta"
    assert divergences == [{"id": 9, "org_id": FINANCE_ORG_SCOPE_DEFAULT}]

    fetch_query, fetch_params = db.executed[0]
    recalc_query, recalc_params = db.executed[1]
    close_query, close_params = db.executed[2]
    reopen_query, reopen_params = db.executed[3]
    divergences_query, divergences_params = db.executed[4]

    assert "FROM financeiro_competencias" in fetch_query
    assert fetch_params[0] == FINANCE_ORG_SCOPE_DEFAULT
    assert "ON CONFLICT (org_id, competencia)" in recalc_query
    assert recalc_params[0] == FINANCE_ORG_SCOPE_DEFAULT
    assert "fechamento_snapshot" in close_query
    assert close_params[0] == FINANCE_ORG_SCOPE_DEFAULT
    assert "reopen_reason" in reopen_query
    assert reopen_params[2] == FINANCE_ORG_SCOPE_DEFAULT
    assert "FROM financeiro_divergencias" in divergences_query
    assert divergences_params[0] == FINANCE_ORG_SCOPE_DEFAULT
