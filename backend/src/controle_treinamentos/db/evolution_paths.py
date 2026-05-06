from __future__ import annotations

DATABASE_EVOLUTION_GROUP_STRUCTURAL = "bootstrap_estrutural"
DATABASE_EVOLUTION_GROUP_CORRECTIVE = "migracao_corretiva"
DATABASE_EVOLUTION_GROUP_RUNTIME_SEED = "seed_minima_runtime"
DATABASE_EVOLUTION_GROUP_HISTORICAL_SEED = "seed_import_historico"
DATABASE_EVOLUTION_GROUP_OPERATIONAL_SYNC = "sync_operacional"
DATABASE_EVOLUTION_GROUP_HISTORICAL_COMPAT = "compat_historica"
DATABASE_EVOLUTION_GROUP_VALIDATION = "validacao"
DATABASE_EVOLUTION_GROUP_MANUAL_UNSAFE = "manual_unsafe"

DATABASE_EVOLUTION_ARTIFACTS: tuple[dict[str, object], ...] = (
    {
        "path": "backend/src/controle_treinamentos/db/schema.py",
        "group": DATABASE_EVOLUTION_GROUP_STRUCTURAL,
        "role": "declaracao canonica de tabelas, colunas, indices e checks estruturais",
        "default_path": True,
        "frozen": False,
    },
    {
        "path": "backend/src/controle_treinamentos/db/schema_bootstrap.py",
        "group": DATABASE_EVOLUTION_GROUP_STRUCTURAL,
        "role": "executor idempotente do bootstrap estrutural e validador de schema",
        "default_path": True,
        "frozen": False,
    },
    {
        "path": "backend/tools/maintenance/bootstrap_db_schema.py",
        "group": DATABASE_EVOLUTION_GROUP_STRUCTURAL,
        "role": "comando operacional canonico para subir schema sem seed ou sync",
        "default_path": True,
        "frozen": False,
    },
    {
        "path": "backend/src/controle_treinamentos/db/migrations.py",
        "group": DATABASE_EVOLUTION_GROUP_CORRECTIVE,
        "role": "migracoes corretivas legadas para bancos historicos, chamadas apenas por repair manual",
        "default_path": False,
        "frozen": False,
    },
    {
        "path": "backend/tools/manual_unsafe/run_db_repair.py",
        "group": DATABASE_EVOLUTION_GROUP_CORRECTIVE,
        "role": "entrada explicita de repair manual; executa bootstrap estrutural e corretivas legadas",
        "default_path": False,
        "frozen": False,
    },
    {
        "path": "backend/tools/maintenance/bootstrap_seed_data.py",
        "group": DATABASE_EVOLUTION_GROUP_RUNTIME_SEED,
        "role": "seed minima operacional de runtime local/defaults; nao e evolucao estrutural",
        "default_path": True,
        "frozen": False,
    },
    {
        "path": "backend/src/controle_treinamentos/db/seeder.py",
        "group": DATABASE_EVOLUTION_GROUP_RUNTIME_SEED,
        "role": "implementacao de bases/defaults e reconciliacoes minimas idempotentes",
        "default_path": True,
        "frozen": False,
    },
    {
        "path": "backend/src/controle_treinamentos/db/training_program_seed.py",
        "group": DATABASE_EVOLUTION_GROUP_HISTORICAL_SEED,
        "role": "seed historico de referencia de programa; nao roda em bootstrap nem repair padrao",
        "default_path": False,
        "frozen": True,
    },
    {
        "path": "backend/tools/data/import_tripulantes_csv.py",
        "group": DATABASE_EVOLUTION_GROUP_HISTORICAL_SEED,
        "role": "entrada explicita para importacao historica de planilha; fora da trilha principal",
        "default_path": False,
        "frozen": True,
    },
    {
        "path": "ops/scripts/database/import_tripulantes_csv.py",
        "group": DATABASE_EVOLUTION_GROUP_HISTORICAL_SEED,
        "role": "implementacao de importacao historica de planilha; nao e bootstrap",
        "default_path": False,
        "frozen": True,
    },
    {
        "path": "ops/scripts/database/sync_training_master_types.py",
        "group": DATABASE_EVOLUTION_GROUP_OPERATIONAL_SYNC,
        "role": "sync pontual de catalogo mestre entre ambientes; nao e migration",
        "default_path": False,
        "frozen": False,
    },
    {
        "path": "backend/tools/compat_residual/sync_tripulantes_snapshot.py",
        "group": DATABASE_EVOLUTION_GROUP_HISTORICAL_COMPAT,
        "role": "wrapper residual para snapshot/reidratacao de tripulantes",
        "default_path": False,
        "frozen": True,
    },
    {
        "path": "ops/scripts/database/sync_tripulantes_snapshot.py",
        "group": DATABASE_EVOLUTION_GROUP_HISTORICAL_COMPAT,
        "role": "implementacao residual com apply ack obrigatorio",
        "default_path": False,
        "frozen": True,
    },
    {
        "path": "ops/scripts/database/migrate_tripulante_media_to_storage.py",
        "group": DATABASE_EVOLUTION_GROUP_HISTORICAL_COMPAT,
        "role": "migracao pontual de blobs/fotos historicos para storage",
        "default_path": False,
        "frozen": True,
    },
    {
        "path": "ops/scripts/database/reconcile_tripulante_photos.py",
        "group": DATABASE_EVOLUTION_GROUP_HISTORICAL_COMPAT,
        "role": "reconciliacao pontual de fotos legadas",
        "default_path": False,
        "frozen": True,
    },
    {
        "path": "backend/tools/maintenance/run_db_consistency.py",
        "group": DATABASE_EVOLUTION_GROUP_VALIDATION,
        "role": "validacao canonica de schema e dados, sem repair",
        "default_path": True,
        "frozen": False,
    },
    {
        "path": "ops/scripts/database/run_db_consistency.py",
        "group": DATABASE_EVOLUTION_GROUP_VALIDATION,
        "role": "implementacao despriorizada da validacao e do repair manual",
        "default_path": False,
        "frozen": False,
    },
    {
        "path": "backend/tools/manual_unsafe/cleanup_operational_data.py",
        "group": DATABASE_EVOLUTION_GROUP_MANUAL_UNSAFE,
        "role": "cleanup destrutivo manual, fora de bootstrap, migration e seed",
        "default_path": False,
        "frozen": False,
    },
)

DATABASE_MAIN_PATH: tuple[str, ...] = (
    "backend/tools/maintenance/bootstrap_db_schema.py",
    "backend/tools/maintenance/bootstrap_seed_data.py",
    "backend/tools/maintenance/run_db_consistency.py",
)


def database_evolution_artifacts(*, group: str | None = None) -> tuple[dict[str, object], ...]:
    artifacts = DATABASE_EVOLUTION_ARTIFACTS
    if group is not None:
        artifacts = tuple(item for item in artifacts if item["group"] == group)
    return tuple(dict(item) for item in artifacts)


def database_main_path() -> tuple[str, ...]:
    return tuple(DATABASE_MAIN_PATH)


def frozen_historical_database_artifacts() -> tuple[dict[str, object], ...]:
    return tuple(dict(item) for item in DATABASE_EVOLUTION_ARTIFACTS if item["frozen"])
