from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

from backend.src.controle_treinamentos.contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT
from backend.src.controle_treinamentos.repositories import financeiro_calculos_horarios

REPO_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_FILE = (
    REPO_ROOT
    / "backend"
    / "src"
    / "controle_treinamentos"
    / "repositories"
    / "financeiro_calculos_horarios.py"
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
        "missao_operacional_id": 10,
        "tripulante_id": 101,
        "funcao": "comandante",
        "jornada_total_minutos": 105,
        "minutos_diurnos": 0,
        "minutos_noturnos_reais": 105,
        "horas_noturnas_convertidas": Decimal("2.0000"),
        "minutos_pre": 0,
        "minutos_pos": 0,
        "domingo_feriado": False,
        "valor_adicional_noturno": Decimal("200.00"),
        "valor_domingo_feriado_diurno": Decimal("0.00"),
        "valor_domingo_feriado_noturno": Decimal("0.00"),
        "valor_pre": Decimal("0.00"),
        "valor_pos": Decimal("0.00"),
        "total": Decimal("200.00"),
        "memoria_calculo": {"steps": [{"rule_key": "conversao_hora_noturna"}]},
        "parametros_usados": [{"tipo": "duracao_hora_noturna_minutos", "valor": "52.5"}],
        "calculation_version": "finance-hourly-v1",
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


def test_salvar_calculo_horario_persists_json_memory_and_org_scope():
    row = {
        "id": 99,
        "org_id": FINANCE_ORG_SCOPE_DEFAULT,
        "missao_operacional_id": 10,
        "tripulante_id": 101,
        "funcao": "comandante",
    }
    db = _FakeDB([_FakeCursor(row=row)])

    result = financeiro_calculos_horarios.salvar_calculo_horario(db, data=_calculation())

    assert result["id"] == 99
    query, params = db.executed[0]
    assert "INSERT INTO financeiro_calculos_horarios" in query
    assert "memoria_calculo" in query
    assert "%s::jsonb" in query
    assert params[0] == FINANCE_ORG_SCOPE_DEFAULT
    assert params[2] == 101
    assert '"conversao_hora_noturna"' in params[18]
    assert '"duracao_hora_noturna_minutos"' in params[19]


def test_salvar_ou_atualizar_calculo_horario_vigente_usa_chave_logica_idempotente():
    row = {
        "id": 99,
        "org_id": FINANCE_ORG_SCOPE_DEFAULT,
        "missao_operacional_id": 10,
        "tripulante_id": 101,
        "funcao": "comandante",
        "persistence_action": "updated",
    }
    db = _FakeDB([_FakeCursor(row=row)])

    result = financeiro_calculos_horarios.salvar_ou_atualizar_calculo_horario_vigente(db, data=_calculation())

    assert result["id"] == 99
    query, params = db.executed[0]
    assert "UPDATE financeiro_calculos_horarios" in query
    assert "missao_operacional_id = %s" in query
    assert "tripulante_id = %s" in query
    assert "funcao = %s" in query
    assert "status <> 'obsoleto'" in query
    assert "memoria_calculo = %s::jsonb" in query
    assert "parametros_usados = %s::jsonb" in query
    assert params[-4:] == (FINANCE_ORG_SCOPE_DEFAULT, 10, 101, "comandante")


def test_salvar_ou_atualizar_calculo_horario_vigente_insere_com_on_conflict_parcial_quando_nao_existe():
    row = {
        "id": 100,
        "org_id": FINANCE_ORG_SCOPE_DEFAULT,
        "missao_operacional_id": 10,
        "tripulante_id": 101,
        "funcao": "comandante",
        "persistence_action": "inserted",
    }
    db = _FakeDB([_FakeCursor(row=None), _FakeCursor(row=row)])

    result = financeiro_calculos_horarios.salvar_ou_atualizar_calculo_horario_vigente(db, data=_calculation())

    assert result["id"] == 100
    insert_query, insert_params = db.executed[1]
    assert "INSERT INTO financeiro_calculos_horarios" in insert_query
    assert "ON CONFLICT (org_id, missao_operacional_id, tripulante_id, funcao)" in insert_query
    assert "WHERE status <> 'obsoleto'" in insert_query
    assert "DO UPDATE SET" in insert_query
    assert insert_params[:4] == (FINANCE_ORG_SCOPE_DEFAULT, 10, 101, "comandante")


def test_listar_e_obsoletar_vigentes_da_missao_ignoram_historico_obsoleto():
    db = _FakeDB(
        [
            _FakeCursor(rows=[{"id": 88, "status": "obsoleto"}]),
            _FakeCursor(rows=[{"id": 99, "status": "calculado"}]),
        ]
    )

    obsolete = financeiro_calculos_horarios.obsoletar_calculos_vigentes_duplicados_da_missao(
        db,
        missao_operacional_id=10,
    )
    current = financeiro_calculos_horarios.listar_calculos_horarios_vigentes_da_missao(
        db,
        missao_operacional_id=10,
    )

    assert obsolete == [{"id": 88, "status": "obsoleto"}]
    assert current == [{"id": 99, "status": "calculado"}]
    obsolete_query, obsolete_params = db.executed[0]
    current_query, current_params = db.executed[1]
    assert "ROW_NUMBER() OVER" in obsolete_query
    assert "PARTITION BY org_id, missao_operacional_id, tripulante_id, funcao" in obsolete_query
    assert "status <> 'obsoleto'" in obsolete_query
    assert "status <> 'obsoleto'" in current_query
    assert obsolete_params == (FINANCE_ORG_SCOPE_DEFAULT, 10)
    assert current_params == (FINANCE_ORG_SCOPE_DEFAULT, 10)


def test_list_detail_and_replace_are_org_scoped():
    db = _FakeDB(
        [
            _FakeCursor(rows=[{"id": 99, "org_id": FINANCE_ORG_SCOPE_DEFAULT}]),
            _FakeCursor(row={"id": 99, "org_id": FINANCE_ORG_SCOPE_DEFAULT}),
            _FakeCursor(rows=[{"id": 99}, {"id": 100}]),
        ]
    )

    rows = financeiro_calculos_horarios.listar_calculos_horarios(
        db,
        missao_operacional_id=10,
        status="calculado",
    )
    detail = financeiro_calculos_horarios.detalhar_calculo_horario(db, calculo_horario_id=99)
    replaced = financeiro_calculos_horarios.substituir_calculos_da_missao(db, missao_operacional_id=10)

    assert rows == [{"id": 99, "org_id": FINANCE_ORG_SCOPE_DEFAULT}]
    assert detail == {"id": 99, "org_id": FINANCE_ORG_SCOPE_DEFAULT}
    assert replaced == 2
    list_query, list_params = db.executed[0]
    detail_query, detail_params = db.executed[1]
    replace_query, replace_params = db.executed[2]
    assert "WHERE ch.org_id = %s" in list_query
    assert "JOIN financeiro_missoes_operacionais mo" in list_query
    assert "JOIN tripulantes t" in list_query
    assert list_params[0] == FINANCE_ORG_SCOPE_DEFAULT
    assert "AND ch.org_id = %s" in detail_query
    assert "JOIN financeiro_missoes_operacionais mo" in detail_query
    assert detail_params[-1] == FINANCE_ORG_SCOPE_DEFAULT
    assert "SET status = 'obsoleto'" in replace_query
    assert replace_params[0] == FINANCE_ORG_SCOPE_DEFAULT
