from __future__ import annotations

import re

from backend.src.controle_treinamentos.db.schema import SCHEMA, _expected_tables_from_schema
from backend.src.controle_treinamentos.db.schema_bootstrap import _schema_statements

EXPECTED_FINANCE_TABLES = {
    "financeiro_missoes_operacionais",
    "financeiro_missao_tripulantes",
    "financeiro_parametros",
    "financeiro_feriados",
    "financeiro_competencias",
    "financeiro_calculos_horarios",
    "financeiro_calculos_produtividade",
    "financeiro_divergencias",
}


def _table_sql(table_name: str) -> str:
    match = re.search(
        rf"CREATE TABLE IF NOT EXISTS {re.escape(table_name)} \((.*?)\n\);",
        SCHEMA,
        flags=re.DOTALL,
    )
    if not match:
        raise AssertionError(f"Table {table_name} not found in canonical schema.")
    return match.group(1)


def _index_sql() -> str:
    return "\n".join(_schema_statements(kind="indexes"))


def test_finance_schema_declares_expected_tables_in_canonical_bootstrap():
    expected_tables = set(_expected_tables_from_schema())
    table_statements = "\n".join(_schema_statements(kind="tables"))

    assert EXPECTED_FINANCE_TABLES <= expected_tables
    for table_name in EXPECTED_FINANCE_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in table_statements


def test_finance_schema_uses_operational_mission_names_only():
    assert "financeiro_missoes_operacionais" in SCHEMA
    assert "missao_operacional_id" in SCHEMA
    assert not re.search(r"CREATE TABLE IF NOT EXISTS\s+financeiro_missoes\s*\(", SCHEMA)
    assert "missao_financeira_id" not in SCHEMA


def test_all_finance_tables_have_org_scope_default():
    for table_name in EXPECTED_FINANCE_TABLES:
        table_sql = _table_sql(table_name)
        assert "org_id TEXT NOT NULL DEFAULT 'default_single_tenant'" in table_sql


def test_operational_mission_keeps_single_timeline_and_participants_have_no_times():
    mission_sql = _table_sql("financeiro_missoes_operacionais")
    participant_sql = _table_sql("financeiro_missao_tripulantes")

    assert "horario_apresentacao TIMESTAMP NOT NULL" in mission_sql
    assert "horario_abandono TIMESTAMP NOT NULL" in mission_sql
    assert "comandante_tripulante_id INTEGER NOT NULL REFERENCES tripulantes (id)" in mission_sql
    assert "copiloto_tripulante_id INTEGER NOT NULL REFERENCES tripulantes (id)" in mission_sql
    assert "aeronave_id INTEGER REFERENCES equipamentos (id)" in mission_sql
    assert "horario_apresentacao" not in participant_sql
    assert "horario_abandono" not in participant_sql
    assert "missao_operacional_id BIGINT NOT NULL REFERENCES financeiro_missoes_operacionais (id)" in participant_sql
    assert "tripulante_id INTEGER NOT NULL REFERENCES tripulantes (id)" in participant_sql
    assert "UNIQUE (org_id, missao_operacional_id, funcao)" in participant_sql


def test_finance_parameters_periods_and_calculations_support_validity_snapshots_and_memory():
    parametros_sql = _table_sql("financeiro_parametros")
    competencias_sql = _table_sql("financeiro_competencias")
    calculos_horarios_sql = _table_sql("financeiro_calculos_horarios")
    calculos_produtividade_sql = _table_sql("financeiro_calculos_produtividade")
    divergencias_sql = _table_sql("financeiro_divergencias")

    assert "vigencia_inicio DATE NOT NULL" in parametros_sql
    assert "vigencia_fim DATE" in parametros_sql
    assert "CHECK (vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio)" in parametros_sql
    assert "totals_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb" in competencias_sql
    assert "fechamento_snapshot JSONB" in competencias_sql
    assert "UNIQUE (org_id, competencia)" in competencias_sql
    for calculation_sql in (calculos_horarios_sql, calculos_produtividade_sql):
        assert "memoria_calculo JSONB NOT NULL DEFAULT '{}'::jsonb" in calculation_sql
        assert "parametros_usados JSONB NOT NULL DEFAULT '{}'::jsonb" in calculation_sql
        assert "calculation_version TEXT NOT NULL DEFAULT 'v1'" in calculation_sql
    assert "horas_noturnas_convertidas NUMERIC(10,4) NOT NULL DEFAULT 0" in calculos_horarios_sql
    assert "detalhes JSONB NOT NULL DEFAULT '{}'::jsonb" in divergencias_sql
    assert "severidade TEXT NOT NULL CHECK" in divergencias_sql


def test_finance_indexes_and_uniques_include_org_scope():
    indexes = _index_sql()

    expected_index_fragments = (
        "idx_financeiro_missoes_operacionais_org_competencia",
        "ON financeiro_missoes_operacionais (org_id, competencia, data_missao)",
        "idx_financeiro_missao_tripulantes_org_missao",
        "ON financeiro_missao_tripulantes (org_id, missao_operacional_id)",
        "idx_financeiro_parametros_org_tipo_vigencia",
        "ON financeiro_parametros (org_id, tipo, funcao, categoria, vigencia_inicio, vigencia_fim)",
        "uq_financeiro_feriados_org_data_tipo_localidade",
        "ON financeiro_feriados (org_id, data, tipo, COALESCE(localidade, ''))",
        "idx_financeiro_competencias_org_status",
        "ON financeiro_competencias (org_id, status, competencia)",
        "idx_financeiro_calculos_horarios_org_missao_tripulante_funcao",
        "ON financeiro_calculos_horarios (org_id, missao_operacional_id, tripulante_id, funcao)",
        "uq_financeiro_calculos_horarios_current",
        "WHERE status <> 'obsoleto'",
        "idx_financeiro_calculos_produtividade_org_comp_trip_funcao",
        "ON financeiro_calculos_produtividade (org_id, competencia, tripulante_id, funcao)",
        "idx_financeiro_divergencias_org_competencia_status",
        "ON financeiro_divergencias (org_id, competencia, status)",
    )
    for fragment in expected_index_fragments:
        assert fragment in indexes


def test_finance_schema_has_no_financial_rule_seed_values_or_functional_layers():
    assert "92,18" not in SCHEMA
    assert "92.18" not in SCHEMA
    assert "INSERT INTO financeiro_" not in SCHEMA
    assert "CREATE OR REPLACE FUNCTION" not in SCHEMA
