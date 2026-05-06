import json
from pathlib import Path

import pytest

from backend.src.controle_treinamentos.db.evolution_paths import (
    DATABASE_EVOLUTION_GROUP_CORRECTIVE,
    DATABASE_EVOLUTION_GROUP_HISTORICAL_COMPAT,
    DATABASE_EVOLUTION_GROUP_HISTORICAL_SEED,
    DATABASE_EVOLUTION_GROUP_OPERATIONAL_SYNC,
    DATABASE_EVOLUTION_GROUP_RUNTIME_SEED,
    DATABASE_EVOLUTION_GROUP_STRUCTURAL,
    database_evolution_artifacts,
    database_main_path,
    frozen_historical_database_artifacts,
)
from backend.src.controle_treinamentos.db.schema_bootstrap import _schema_statements
from backend.src.controle_treinamentos.db.seeder import _jornada_tabela_regulamentar_default_json
from backend.src.controle_treinamentos.db.training_program_seed import seed_training_program_reference

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_schema_statements_split_tables_and_indexes():
    table_statements = _schema_statements(kind="tables")
    index_statements = _schema_statements(kind="indexes")

    assert table_statements
    assert index_statements
    assert all(statement.startswith("CREATE TABLE IF NOT EXISTS") for statement in table_statements)
    assert all("INDEX IF NOT EXISTS" in statement for statement in index_statements)
    assert any("tipos_treinamento" in statement for statement in table_statements)
    assert any("uq_tipos_treinamento_codigo" in statement for statement in index_statements)


def test_migrations_module_no_longer_embeds_training_program_seed():
    source = (REPO_ROOT / "backend" / "src" / "controle_treinamentos" / "db" / "migrations.py").read_text(
        encoding="utf-8"
    )

    assert "seed_training_program_reference" not in source
    assert "Bootstrap estrutural canonico" in source
    assert "MIGRATIONS_MODULE_CLASSIFICATION" in source
    assert "execute_corrective_migrations" in source


def test_seeder_uses_structural_bootstrap_without_legacy_migrations():
    source = (REPO_ROOT / "backend" / "src" / "controle_treinamentos" / "db" / "seeder.py").read_text(
        encoding="utf-8"
    )

    assert "from .schema_bootstrap import execute_schema_bootstrap" in source
    assert "execute_schema_bootstrap(db)" in source
    assert "from .migrations import execute_migrations" not in source


def test_seeder_inclui_tabela_regulamentar_padrao_da_planilha():
    table = json.loads(_jornada_tabela_regulamentar_default_json())

    assert len(table) == 288
    assert table["00:00"] == "09:45"
    assert table["17:00"] == "02:15"
    assert table["23:55"] == "09:43"


def test_run_db_consistency_repair_does_not_call_operational_seed():
    source = (REPO_ROOT / "ops" / "scripts" / "database" / "run_db_consistency.py").read_text(encoding="utf-8")

    assert "repair_and_validate_schema" in source
    assert "execute_script()" not in source


def test_repair_path_uses_corrective_migration_name_not_mixed_migration_name():
    source = (REPO_ROOT / "backend" / "src" / "controle_treinamentos" / "db" / "schema_bootstrap.py").read_text(
        encoding="utf-8"
    )

    assert "execute_corrective_migrations" in source
    assert "execute_migrations(db)" not in source


def test_database_evolution_artifacts_are_classified_by_path_and_group():
    artifacts = database_evolution_artifacts()
    groups = {item["group"] for item in artifacts}
    by_path = {item["path"]: item for item in artifacts}

    assert {
        DATABASE_EVOLUTION_GROUP_STRUCTURAL,
        DATABASE_EVOLUTION_GROUP_CORRECTIVE,
        DATABASE_EVOLUTION_GROUP_RUNTIME_SEED,
        DATABASE_EVOLUTION_GROUP_HISTORICAL_SEED,
        DATABASE_EVOLUTION_GROUP_OPERATIONAL_SYNC,
        DATABASE_EVOLUTION_GROUP_HISTORICAL_COMPAT,
    }.issubset(groups)
    assert by_path["backend/tools/maintenance/bootstrap_db_schema.py"]["default_path"] is True
    assert by_path["backend/src/controle_treinamentos/db/migrations.py"]["group"] == DATABASE_EVOLUTION_GROUP_CORRECTIVE
    assert by_path["backend/src/controle_treinamentos/db/training_program_seed.py"]["frozen"] is True
    assert by_path["ops/scripts/database/sync_training_master_types.py"]["default_path"] is False
    assert by_path["ops/scripts/database/sync_tripulantes_snapshot.py"]["group"] == DATABASE_EVOLUTION_GROUP_HISTORICAL_COMPAT


def test_database_main_path_excludes_historical_seed_sync_and_repair():
    main_path = database_main_path()

    assert main_path == (
        "backend/tools/maintenance/bootstrap_db_schema.py",
        "backend/tools/maintenance/bootstrap_seed_data.py",
        "backend/tools/maintenance/run_db_consistency.py",
    )
    assert "backend/src/controle_treinamentos/db/migrations.py" not in main_path
    assert "backend/src/controle_treinamentos/db/training_program_seed.py" not in main_path
    assert "ops/scripts/database/sync_training_master_types.py" not in main_path
    assert "ops/scripts/database/sync_tripulantes_snapshot.py" not in main_path


def test_historical_artifacts_are_frozen_and_require_explicit_write_path():
    frozen_paths = {item["path"] for item in frozen_historical_database_artifacts()}

    assert "backend/src/controle_treinamentos/db/training_program_seed.py" in frozen_paths
    assert "ops/scripts/database/import_tripulantes_csv.py" in frozen_paths
    assert "ops/scripts/database/sync_tripulantes_snapshot.py" in frozen_paths
    with pytest.raises(RuntimeError, match="Seed historico"):
        seed_training_program_reference(object())


def test_canonical_commands_split_bootstrap_from_repair():
    source = (REPO_ROOT / "docs" / "operations" / "canonical-commands.md").read_text(encoding="utf-8")

    assert "bootstrap estrutural de banco" in source
    assert "bootstrap_db_schema.py" in source
    assert "use `--repair` apenas como reparo manual" in source
    assert "repair manual de banco historico" in source
    assert "DATABASE_EVOLUTION.md" in source


def test_database_evolution_doc_records_operational_classification():
    source = (REPO_ROOT / "docs" / "operations" / "DATABASE_EVOLUTION.md").read_text(encoding="utf-8")
    operations_readme = (REPO_ROOT / "docs" / "operations" / "README.md").read_text(encoding="utf-8")

    assert "bootstrap estrutural" in source
    assert "migracao corretiva" in source
    assert "seed/import historico" in source
    assert "sync operacional" in source
    assert "compat historica" in source
    assert "nao chama seed historico, import historico, sync entre ambientes" in source
    assert "DATABASE_EVOLUTION.md" in operations_readme
