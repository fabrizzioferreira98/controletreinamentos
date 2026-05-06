from __future__ import annotations

from pathlib import Path

from backend.src.controle_treinamentos.db.schema import _REQUIRED_COLUMNS_BY_TABLE, SCHEMA

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "backend" / "src" / "controle_treinamentos" / "db" / "migrations.py"


def _table_ddl(table_name: str) -> str:
    marker = f"CREATE TABLE IF NOT EXISTS {table_name} ("
    start = SCHEMA.index(marker)
    end = SCHEMA.index("\n);", start)
    return SCHEMA[start:end]


def test_equipamentos_schema_contains_nullable_finance_category_with_allowed_slugs():
    ddl = _table_ddl("equipamentos")

    assert "categoria_financeira TEXT" in ddl
    assert "categoria_financeira IS NULL" in ddl
    for value in ("a", "b", "turbohelice_palmas", "nao_aplicavel"):
        assert f"'{value}'" in ddl
    assert "categoria_financeira" in _REQUIRED_COLUMNS_BY_TABLE["equipamentos"]


def test_equipamentos_corrective_migration_adds_finance_category_without_seed_values():
    migrations = MIGRATIONS.read_text(encoding="utf-8")

    assert "ALTER TABLE equipamentos ADD COLUMN IF NOT EXISTS categoria_financeira TEXT" in migrations
    assert "equipamentos_categoria_financeira_check" in migrations
    assert "categoria_financeira IN ('a', 'b', 'turbohelice_palmas', 'nao_aplicavel')" in migrations
    assert "UPDATE equipamentos SET categoria_financeira = 'a'" not in migrations
    assert "UPDATE equipamentos SET categoria_financeira = 'b'" not in migrations
