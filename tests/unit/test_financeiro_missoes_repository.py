from __future__ import annotations

import ast
import inspect
from pathlib import Path

from backend.src.controle_treinamentos.contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT
from backend.src.controle_treinamentos.repositories import financeiro_missoes

REPO_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_FILE = (
    REPO_ROOT / "backend" / "src" / "controle_treinamentos" / "repositories" / "financeiro_missoes.py"
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


def test_repository_preserves_operational_mission_naming_and_scope():
    source = REPOSITORY_FILE.read_text(encoding="utf-8")

    assert "financeiro_missoes_operacionais" in source
    assert "financeiro_missao_tripulantes" in source
    assert "missao_operacional_id" in source
    assert "missao_financeira_id" not in source
    assert "CREATE TABLE financeiro_missoes" not in source
    assert "org_id" in source
    assert "FINANCE_ORG_SCOPE_DEFAULT" in source


def test_participant_repository_functions_do_not_use_schedule_columns():
    participant_source = "\n".join(
        (
            inspect.getsource(financeiro_missoes.insert_missao_tripulante),
            inspect.getsource(financeiro_missoes.insert_tripulantes_missao),
            inspect.getsource(financeiro_missoes.list_missao_tripulantes),
        )
    )

    assert "horario_apresentacao" not in participant_source
    assert "horario_abandono" not in participant_source


def test_create_missao_operacional_defaults_org_id_and_inserts_participants():
    mission_row = {
        "id": 10,
        "org_id": FINANCE_ORG_SCOPE_DEFAULT,
        "comandante_tripulante_id": 101,
        "copiloto_tripulante_id": 202,
    }
    db = _FakeDB(
        [
            _FakeCursor(row=mission_row),
            _FakeCursor(row={"id": 1, "org_id": FINANCE_ORG_SCOPE_DEFAULT, "funcao": "comandante"}),
            _FakeCursor(row={"id": 2, "org_id": FINANCE_ORG_SCOPE_DEFAULT, "funcao": "copiloto"}),
        ]
    )

    result = financeiro_missoes.create_missao_operacional_with_tripulantes(
        db,
        data={
            "competencia": "2026-04",
            "data_missao": "2026-04-10",
            "comandante_tripulante_id": 101,
            "copiloto_tripulante_id": 202,
            "horario_apresentacao": "2026-04-10 08:00:00",
            "horario_abandono": "2026-04-10 18:00:00",
        },
    )

    assert result["org_id"] == FINANCE_ORG_SCOPE_DEFAULT
    assert [item["funcao"] for item in result["participantes"]] == ["comandante", "copiloto"]
    insert_query, insert_params = db.executed[0]
    assert "INSERT INTO financeiro_missoes_operacionais" in insert_query
    assert insert_params[0] == FINANCE_ORG_SCOPE_DEFAULT
    for query, params in db.executed[1:]:
        assert "INSERT INTO financeiro_missao_tripulantes" in query
        assert "WHERE mo.id = %s" in query
        assert "AND mo.org_id = %s" in query
        assert params[0] == FINANCE_ORG_SCOPE_DEFAULT
        assert params[-1] == FINANCE_ORG_SCOPE_DEFAULT


def test_replace_missao_tripulantes_is_org_scoped_and_reinserts_crew_pair():
    db = _FakeDB(
        [
            _FakeCursor(),
            _FakeCursor(row={"id": 11, "org_id": FINANCE_ORG_SCOPE_DEFAULT, "funcao": "comandante"}),
            _FakeCursor(row={"id": 12, "org_id": FINANCE_ORG_SCOPE_DEFAULT, "funcao": "copiloto"}),
        ]
    )

    result = financeiro_missoes.replace_missao_tripulantes(
        db,
        missao_operacional_id=10,
        comandante_tripulante_id=303,
        copiloto_tripulante_id=404,
    )

    assert [item["funcao"] for item in result] == ["comandante", "copiloto"]
    delete_query, delete_params = db.executed[0]
    assert "DELETE FROM financeiro_missao_tripulantes" in delete_query
    assert "WHERE missao_operacional_id = %s" in delete_query
    assert "AND org_id = %s" in delete_query
    assert delete_params == (10, FINANCE_ORG_SCOPE_DEFAULT)
    assert db.executed[1][1][1] == 303
    assert db.executed[2][1][1] == 404


def test_update_and_cancel_are_org_scoped_and_do_not_delete():
    db = _FakeDB(
        [
            _FakeCursor(row={"id": 10, "org_id": FINANCE_ORG_SCOPE_DEFAULT, "trecho": "BSB-GRU"}),
            _FakeCursor(row={"id": 10, "org_id": FINANCE_ORG_SCOPE_DEFAULT, "status": "cancelada"}),
        ]
    )

    updated = financeiro_missoes.update_missao_operacional(
        db,
        missao_operacional_id=10,
        data={"trecho": "BSB-GRU", "updated_by": 7},
    )
    cancelled = financeiro_missoes.cancel_missao_operacional(db, missao_operacional_id=10, updated_by=7)

    assert updated["trecho"] == "BSB-GRU"
    assert cancelled["status"] == "cancelada"
    update_query, update_params = db.executed[0]
    cancel_query, cancel_params = db.executed[1]
    assert "UPDATE financeiro_missoes_operacionais" in update_query
    assert "WHERE id = %s" in update_query
    assert "AND org_id = %s" in update_query
    assert update_params[-1] == FINANCE_ORG_SCOPE_DEFAULT
    assert "DELETE FROM" not in cancel_query
    assert "status = 'cancelada'" in cancel_query
    assert cancel_params[-1] == FINANCE_ORG_SCOPE_DEFAULT


def test_soft_delete_is_org_scoped_and_marks_participants_removed():
    db = _FakeDB(
        [
            _FakeCursor(row={"id": 10, "org_id": FINANCE_ORG_SCOPE_DEFAULT, "deleted_at": "2026-05-04"}),
            _FakeCursor(rows=[{"id": 1, "status": "removido"}, {"id": 2, "status": "removido"}]),
        ]
    )

    deleted = financeiro_missoes.soft_delete_missao_operacional(
        db,
        missao_operacional_id=10,
        deleted_by=7,
        delete_reason="erro de lancamento",
    )
    removed = financeiro_missoes.remover_missao_tripulantes(db, missao_operacional_id=10)

    assert deleted["deleted_at"] == "2026-05-04"
    assert [item["status"] for item in removed] == ["removido", "removido"]
    delete_query, delete_params = db.executed[0]
    remove_query, remove_params = db.executed[1]
    assert "UPDATE financeiro_missoes_operacionais" in delete_query
    assert "deleted_at = CURRENT_TIMESTAMP" in delete_query
    assert "AND org_id = %s" in delete_query
    assert "AND deleted_at IS NULL" in delete_query
    assert delete_params[-1] == FINANCE_ORG_SCOPE_DEFAULT
    assert "UPDATE financeiro_missao_tripulantes" in remove_query
    assert "status = 'removido'" in remove_query
    assert remove_params[-1] == FINANCE_ORG_SCOPE_DEFAULT


def test_delete_dependency_summary_counts_financial_links():
    db = _FakeDB(
        [
            _FakeCursor(row={"total": 1}),
            _FakeCursor(row={"total": 2}),
            _FakeCursor(row={"total": 3}),
        ]
    )

    summary = financeiro_missoes.mission_delete_dependency_summary(
        db,
        missao_operacional_id=10,
        competencia="2026-04",
    )

    assert summary == {"calculos_horarios": 1, "calculos_produtividade": 2, "divergencias": 3}
    assert all(params[0] == FINANCE_ORG_SCOPE_DEFAULT for _query, params in db.executed)


def test_list_and_duplicate_queries_require_org_scope():
    db = _FakeDB(
        [
            _FakeCursor(rows=[{"id": 10, "org_id": FINANCE_ORG_SCOPE_DEFAULT}]),
            _FakeCursor(row={"id": 10, "org_id": FINANCE_ORG_SCOPE_DEFAULT}),
        ]
    )

    rows = financeiro_missoes.list_missoes_operacionais(db, competencia="2026-04")
    duplicate = financeiro_missoes.find_duplicate_missao_operacional(
        db,
        cavok_numero_voo="CAVOK-1",
        contratante="Cliente",
        chamado="CH-1",
    )

    assert rows == [{"id": 10, "org_id": FINANCE_ORG_SCOPE_DEFAULT}]
    assert duplicate == {"id": 10, "org_id": FINANCE_ORG_SCOPE_DEFAULT}
    list_query, list_params = db.executed[0]
    duplicate_query, duplicate_params = db.executed[1]
    assert "WHERE org_id = %s AND competencia = %s AND deleted_at IS NULL" in list_query
    assert list_params[:2] == (FINANCE_ORG_SCOPE_DEFAULT, "2026-04")
    assert "WHERE org_id = %s" in duplicate_query
    assert "deleted_at IS NULL" in duplicate_query
    assert duplicate_params[0] == FINANCE_ORG_SCOPE_DEFAULT
