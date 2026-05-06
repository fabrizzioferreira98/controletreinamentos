from __future__ import annotations

import ast
from pathlib import Path

from backend.src.controle_treinamentos.contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT
from backend.src.controle_treinamentos.repositories import financeiro_feriados

REPO_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_FILE = (
    REPO_ROOT / "backend" / "src" / "controle_treinamentos" / "repositories" / "financeiro_feriados.py"
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


def _holiday_row(**overrides):
    row = {
        "id": 1,
        "org_id": FINANCE_ORG_SCOPE_DEFAULT,
        "data": "2026-04-21",
        "nome": "Tiradentes",
        "tipo": "nacional",
        "localidade": None,
        "status": "ativo",
        "created_by": 7,
        "updated_by": 7,
    }
    row.update(overrides)
    return row


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


def test_create_list_update_holiday_queries_are_org_scoped_and_national_only():
    db = _FakeDB(
        [
            _FakeCursor(row=_holiday_row()),
            _FakeCursor(rows=[_holiday_row()]),
            _FakeCursor(row=_holiday_row(nome="Tiradentes atualizado")),
        ]
    )

    created = financeiro_feriados.criar_feriado_nacional(
        db,
        data={
            "data": "2026-04-21",
            "nome": "Tiradentes",
            "tipo": "municipal",
            "localidade": "Sao Paulo",
            "created_by": 7,
            "updated_by": 7,
        },
    )
    listed = financeiro_feriados.listar_feriados_nacionais(db, ano=2026, limit=20, offset=0)
    updated = financeiro_feriados.atualizar_feriado_nacional(
        db,
        feriado_id=1,
        data={"nome": "Tiradentes atualizado", "tipo": "nacional", "localidade": "RJ", "updated_by": 7},
    )

    assert created["tipo"] == "nacional"
    assert listed[0]["data"] == "2026-04-21"
    assert updated["nome"] == "Tiradentes atualizado"
    insert_query, insert_params = db.executed[0]
    list_query, list_params = db.executed[1]
    update_query, update_params = db.executed[2]
    assert "INSERT INTO financeiro_feriados" in insert_query
    assert "'nacional'" in insert_query
    assert "NULL" in insert_query
    assert insert_params[0] == FINANCE_ORG_SCOPE_DEFAULT
    assert "WHERE org_id = %s AND tipo = 'nacional'" in list_query
    assert list_params[0] == FINANCE_ORG_SCOPE_DEFAULT
    assert "UPDATE financeiro_feriados" in update_query
    assert "AND org_id = %s" in update_query
    assert "AND tipo = 'nacional'" in update_query
    assert update_params[-1] == FINANCE_ORG_SCOPE_DEFAULT


def test_duplicate_and_date_lookup_are_org_scoped_active_national_queries():
    db = _FakeDB(
        [
            _FakeCursor(row=_holiday_row()),
            _FakeCursor(row=_holiday_row(id=2)),
        ]
    )

    current = financeiro_feriados.verificar_feriado_nacional_por_data(db, data="2026-04-21")
    duplicate = financeiro_feriados.verificar_duplicidade_feriado_nacional(
        db,
        data="2026-04-21",
        exclude_id=1,
    )

    assert current["nome"] == "Tiradentes"
    assert duplicate["id"] == 2
    current_query, current_params = db.executed[0]
    duplicate_query, duplicate_params = db.executed[1]
    assert "tipo = 'nacional'" in current_query
    assert "status = %s" in current_query
    assert current_params[0] == FINANCE_ORG_SCOPE_DEFAULT
    assert "tipo = 'nacional'" in duplicate_query
    assert "status = 'ativo'" in duplicate_query
    assert "id <> %s" in duplicate_query
    assert duplicate_params[0] == FINANCE_ORG_SCOPE_DEFAULT
    assert duplicate_params[-1] == 1
