from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

from backend.src.controle_treinamentos.contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT
from backend.src.controle_treinamentos.repositories import financeiro_calculos_produtividade

REPO_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_FILE = (
    REPO_ROOT
    / "backend"
    / "src"
    / "controle_treinamentos"
    / "repositories"
    / "financeiro_calculos_produtividade.py"
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


def _calculation(**overrides):
    payload = {
        "org_id": FINANCE_ORG_SCOPE_DEFAULT,
        "competencia": "2026-04",
        "tripulante_id": 101,
        "funcao": "comandante",
        "categoria_aplicavel": "a",
        "valor_icao": Decimal("100.00"),
        "valor_instrutor": Decimal("0.00"),
        "valor_checador": Decimal("0.00"),
        "valor_missoes_categoria_a": Decimal("200.00"),
        "valor_missoes_categoria_b": Decimal("0.00"),
        "valor_cobertura_base": Decimal("0.00"),
        "valor_pernoite_comum": Decimal("0.00"),
        "valor_excecao_palmas": Decimal("0.00"),
        "produtividade_calculada": Decimal("300.00"),
        "garantia_minima": Decimal("250.00"),
        "total_devido": Decimal("300.00"),
        "memoria_calculo": {"steps": [{"rule_key": "produtividade_calculada"}]},
        "parametros_usados": [{"tipo": "missao_categoria_a", "valor": "200.00"}],
        "calculation_version": "finance-productivity-v1",
    }
    payload.update(overrides)
    return payload


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


def test_salvar_calculo_produtividade_uses_upsert_json_memory_and_org_scope():
    row = {
        "id": 99,
        "org_id": FINANCE_ORG_SCOPE_DEFAULT,
        "competencia": "2026-04",
        "tripulante_id": 101,
        "funcao": "comandante",
    }
    db = _FakeDB([_FakeCursor(row=row)])

    result = financeiro_calculos_produtividade.salvar_calculo_produtividade(db, data=_calculation())

    assert result["id"] == 99
    query, params = db.executed[0]
    assert "INSERT INTO financeiro_calculos_produtividade" in query
    assert "ON CONFLICT (org_id, competencia, tripulante_id, funcao)" in query
    assert "memoria_calculo" in query
    assert "%s::jsonb" in query
    assert params[0] == FINANCE_ORG_SCOPE_DEFAULT
    assert params[1] == "2026-04"
    assert params[2] == 101
    assert '"produtividade_calculada"' in params[16]
    assert '"missao_categoria_a"' in params[17]


def test_list_detail_and_participations_are_org_scoped():
    db = _FakeDB(
        [
            _FakeCursor(rows=[{"id": 99, "org_id": FINANCE_ORG_SCOPE_DEFAULT}]),
            _FakeCursor(row={"id": 99, "org_id": FINANCE_ORG_SCOPE_DEFAULT}),
            _FakeCursor(rows=[{"missao_operacional_id": 10, "tripulante_id": 101, "funcao": "comandante"}]),
        ]
    )

    rows = financeiro_calculos_produtividade.listar_calculos_produtividade(
        db,
        competencia="2026-04",
        tripulante_id=101,
        status="calculado",
    )
    detail = financeiro_calculos_produtividade.detalhar_calculo_produtividade_por_tripulante(
        db,
        tripulante_id=101,
        competencia="2026-04",
    )
    participations = financeiro_calculos_produtividade.listar_participacoes_produtividade_por_competencia(
        db,
        competencia="2026-04",
    )

    assert rows == [{"id": 99, "org_id": FINANCE_ORG_SCOPE_DEFAULT}]
    assert detail == {"id": 99, "org_id": FINANCE_ORG_SCOPE_DEFAULT}
    assert participations == [{"missao_operacional_id": 10, "tripulante_id": 101, "funcao": "comandante"}]
    list_query, list_params = db.executed[0]
    detail_query, detail_params = db.executed[1]
    participations_query, participations_params = db.executed[2]
    assert "WHERE cp.org_id = %s" in list_query
    assert "JOIN tripulantes t" in list_query
    assert list_params[0] == FINANCE_ORG_SCOPE_DEFAULT
    assert "WHERE cp.org_id = %s" in detail_query
    assert detail_params[0] == FINANCE_ORG_SCOPE_DEFAULT
    assert "FROM financeiro_missao_tripulantes mt" in participations_query
    assert "JOIN financeiro_missoes_operacionais mo" in participations_query
    assert "AND mo.status <> 'cancelada'" in participations_query
    assert participations_params[0] == FINANCE_ORG_SCOPE_DEFAULT
