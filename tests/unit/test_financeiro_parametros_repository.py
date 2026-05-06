from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

from backend.src.controle_treinamentos.contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT
from backend.src.controle_treinamentos.repositories import financeiro_parametros

REPO_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_FILE = (
    REPO_ROOT / "backend" / "src" / "controle_treinamentos" / "repositories" / "financeiro_parametros.py"
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


def _parameter_row(**overrides):
    row = {
        "id": 1,
        "org_id": FINANCE_ORG_SCOPE_DEFAULT,
        "tipo": "duracao_hora_noturna_minutos",
        "funcao": None,
        "categoria": None,
        "valor": Decimal("52.5"),
        "unidade": "minutos",
        "vigencia_inicio": "2026-04-01",
        "vigencia_fim": None,
        "status": "ativo",
        "motivo": "baseline",
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


def test_create_list_update_parameter_queries_are_org_scoped():
    db = _FakeDB(
        [
            _FakeCursor(row=_parameter_row()),
            _FakeCursor(rows=[_parameter_row()]),
            _FakeCursor(row=_parameter_row(valor=Decimal("60"))),
        ]
    )

    created = financeiro_parametros.criar_parametro_financeiro(
        db,
        data={
            "tipo": "duracao_hora_noturna_minutos",
            "valor": Decimal("52.5"),
            "unidade": "minutos",
            "vigencia_inicio": "2026-04-01",
            "created_by": 7,
            "updated_by": 7,
        },
    )
    listed = financeiro_parametros.listar_parametros_financeiros(
        db,
        tipo="duracao_hora_noturna_minutos",
        status="ativo",
        limit=20,
        offset=0,
    )
    updated = financeiro_parametros.atualizar_parametro_financeiro(
        db,
        parametro_id=1,
        data={"valor": Decimal("60"), "updated_by": 7},
    )

    assert created["org_id"] == FINANCE_ORG_SCOPE_DEFAULT
    assert listed[0]["tipo"] == "duracao_hora_noturna_minutos"
    assert updated["valor"] == Decimal("60")
    insert_query, insert_params = db.executed[0]
    list_query, list_params = db.executed[1]
    update_query, update_params = db.executed[2]
    assert "INSERT INTO financeiro_parametros" in insert_query
    assert insert_params[0] == FINANCE_ORG_SCOPE_DEFAULT
    assert "WHERE org_id = %s" in list_query
    assert list_params[0] == FINANCE_ORG_SCOPE_DEFAULT
    assert "UPDATE financeiro_parametros" in update_query
    assert "WHERE id = %s" in update_query
    assert "AND org_id = %s" in update_query
    assert update_params[-1] == FINANCE_ORG_SCOPE_DEFAULT


def test_current_parameter_and_overlap_queries_use_org_scope_and_active_validity():
    db = _FakeDB(
        [
            _FakeCursor(row=_parameter_row()),
            _FakeCursor(row=_parameter_row(id=2)),
        ]
    )

    current = financeiro_parametros.buscar_parametro_vigente(
        db,
        tipo="duracao_hora_noturna_minutos",
        vigencia_em="2026-04-15",
        unidade="minutos",
    )
    overlap = financeiro_parametros.verificar_sobreposicao_vigencia(
        db,
        tipo="duracao_hora_noturna_minutos",
        unidade="minutos",
        vigencia_inicio="2026-04-01",
        vigencia_fim=None,
        exclude_id=1,
    )

    assert current["valor"] == Decimal("52.5")
    assert overlap["id"] == 2
    current_query, current_params = db.executed[0]
    overlap_query, overlap_params = db.executed[1]
    assert "status = 'ativo'" in current_query
    assert "vigencia_inicio <= %s::date" in current_query
    assert current_params[0] == FINANCE_ORG_SCOPE_DEFAULT
    assert "status = 'ativo'" in overlap_query
    assert "NOT (" in overlap_query
    assert "id <> %s" in overlap_query
    assert overlap_params[0] == FINANCE_ORG_SCOPE_DEFAULT
    assert overlap_params[-1] == 1


def test_current_parameter_lookup_matches_funcao_case_insensitively():
    db = _FakeDB([_FakeCursor(row=_parameter_row(funcao="Comandante", unidade="valor"))])

    current = financeiro_parametros.buscar_parametro_vigente(
        db,
        tipo="adicional_noturno",
        vigencia_em="2026-04-15",
        unidade="valor",
        funcao="comandante",
    )

    query, params = db.executed[0]
    assert current["funcao"] == "Comandante"
    assert "LOWER(COALESCE(funcao, '')) = LOWER(COALESCE(%s, ''))" in query
    assert params[4] == "comandante"


def test_listar_parametros_por_ids_respeita_org_scope_e_parametros():
    db = _FakeDB([_FakeCursor(rows=[_parameter_row(id=10), _parameter_row(id=11)])])

    rows = financeiro_parametros.listar_parametros_financeiros_por_ids(
        db,
        parameter_ids=[11, 10],
    )

    assert [item["id"] for item in rows] == [10, 11]
    query, params = db.executed[0]
    assert "FROM financeiro_parametros" in query
    assert "id IN (%s, %s)" in query
    assert params[0] == FINANCE_ORG_SCOPE_DEFAULT
    assert set(params[1:]) == {10, 11}
