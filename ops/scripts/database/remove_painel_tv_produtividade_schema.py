"""IMPLEMENTATION: remocao destrutiva/manual de schema retirado.

Comando oficial: backend/tools/manual_unsafe/remove_painel_tv_produtividade_schema.py.
Execucao direta fica despriorizada para evitar aparencia de rotina normal.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse
from uuid import uuid4

import psycopg2


DIRECT_ENTRY_NOTICE = (
    "Entrada direta despriorizada: ops/scripts/database/remove_painel_tv_produtividade_schema.py e implementacao; "
    "use backend/tools/manual_unsafe/remove_painel_tv_produtividade_schema.py."
)

RETENTION_POLICY = "destroy-after-backup"

REMOVED_TABLES = (
    "produtividade_conferencias",
    "produtividade_adicionais_excepcionais",
    "produtividade_parametros",
    "produtividade_regras",
)

REMOVED_INDEXES = (
    "idx_missoes_conta_prod",
    "idx_excepcionais_competencia",
    "idx_excepcionais_tripulante",
    "idx_produtividade_conferencias_competencia",
    "idx_produtividade_conferencias_tripulante",
)

DESTRUCTIVE_SQL = (
    "DROP INDEX IF EXISTS idx_produtividade_conferencias_competencia",
    "DROP INDEX IF EXISTS idx_produtividade_conferencias_tripulante",
    "DROP INDEX IF EXISTS idx_excepcionais_competencia",
    "DROP INDEX IF EXISTS idx_excepcionais_tripulante",
    "DROP INDEX IF EXISTS idx_missoes_conta_prod",
    "DROP TABLE IF EXISTS produtividade_conferencias",
    "DROP TABLE IF EXISTS produtividade_adicionais_excepcionais",
    "DROP TABLE IF EXISTS produtividade_parametros",
    "DROP TABLE IF EXISTS produtividade_regras",
    "ALTER TABLE IF EXISTS missoes_operacionais DROP COLUMN IF EXISTS conta_missao_produtividade",
)

ROLLBACK_SCHEMA_SQL = (
    "CREATE TABLE IF NOT EXISTS produtividade_regras ("
    "id SERIAL PRIMARY KEY, "
    "categoria_operacional TEXT NOT NULL, "
    "funcao_operacional TEXT NOT NULL, "
    "piso_minimo_mensal NUMERIC(12,2) NOT NULL DEFAULT 0, "
    "valor_missao NUMERIC(12,2) NOT NULL DEFAULT 0, "
    "valor_pernoite_cobertura NUMERIC(12,2) NOT NULL DEFAULT 0, "
    "valor_idioma_mensal NUMERIC(12,2) NOT NULL DEFAULT 0, "
    "valor_instrutor_mensal NUMERIC(12,2) NOT NULL DEFAULT 0, "
    "valor_checador_mensal NUMERIC(12,2) NOT NULL DEFAULT 0, "
    "ativo BOOLEAN NOT NULL DEFAULT TRUE, "
    "UNIQUE (categoria_operacional, funcao_operacional)"
    ")",
    "CREATE TABLE IF NOT EXISTS produtividade_parametros ("
    "chave TEXT PRIMARY KEY, "
    "valor_numerico NUMERIC(12,2), "
    "valor_texto TEXT, "
    "atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
    ")",
    "ALTER TABLE IF EXISTS missoes_operacionais "
    "ADD COLUMN IF NOT EXISTS conta_missao_produtividade BOOLEAN NOT NULL DEFAULT TRUE",
    "CREATE TABLE IF NOT EXISTS produtividade_adicionais_excepcionais ("
    "id SERIAL PRIMARY KEY, "
    "tripulante_id INTEGER NOT NULL REFERENCES tripulantes (id) ON DELETE CASCADE, "
    "competencia TEXT NOT NULL, "
    "valor NUMERIC(12,2) NOT NULL DEFAULT 0, "
    "observacao TEXT, "
    "ativo BOOLEAN NOT NULL DEFAULT TRUE"
    ")",
    "CREATE TABLE IF NOT EXISTS produtividade_conferencias ("
    "id BIGSERIAL PRIMARY KEY, "
    "tripulante_id INTEGER NOT NULL REFERENCES tripulantes (id) ON DELETE CASCADE, "
    "competencia TEXT NOT NULL, "
    "conferido_por INTEGER NOT NULL REFERENCES usuarios (id), "
    "conferido_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "
    "UNIQUE (tripulante_id, competencia)"
    ")",
    "CREATE INDEX IF NOT EXISTS idx_missoes_conta_prod "
    "ON missoes_operacionais (conta_missao_produtividade)",
    "CREATE INDEX IF NOT EXISTS idx_excepcionais_competencia "
    "ON produtividade_adicionais_excepcionais (competencia)",
    "CREATE INDEX IF NOT EXISTS idx_excepcionais_tripulante "
    "ON produtividade_adicionais_excepcionais (tripulante_id)",
    "CREATE INDEX IF NOT EXISTS idx_produtividade_conferencias_competencia "
    "ON produtividade_conferencias (competencia, conferido_em DESC)",
    "CREATE INDEX IF NOT EXISTS idx_produtividade_conferencias_tripulante "
    "ON produtividade_conferencias (tripulante_id)",
)


@dataclass(frozen=True)
class SchemaRemovalPlan:
    existing_tables: tuple[str, ...]
    existing_indexes: tuple[str, ...]
    column_exists: bool
    row_counts: dict[str, int]
    mission_flag_stats: dict[str, int] | None


def _utc_now_text() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _database_target(db_url: str) -> dict:
    parsed = urlparse(db_url)
    return {
        "scheme": parsed.scheme,
        "host": parsed.hostname or "",
        "port": parsed.port,
        "database": (parsed.path or "/").lstrip("/"),
        "user": parsed.username or "",
    }


def _expected_confirmation(target: dict) -> str:
    database = target.get("database") or "unknown"
    return f"remove-painel-tv-produtividade-schema:{database}"


def _existing_tables(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
            """
        )
        return {str(row[0]) for row in cur.fetchall()}


def _existing_indexes(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND indexname = ANY(%s)
            """,
            (list(REMOVED_INDEXES),),
        )
        return {str(row[0]) for row in cur.fetchall()}


def _column_exists(conn, *, table: str, column: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
              AND column_name = %s
            LIMIT 1
            """,
            (table, column),
        )
        return cur.fetchone() is not None


def _count_rows(conn, tables: tuple[str, ...], existing_tables: set[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    with conn.cursor() as cur:
        for table in tables:
            if table not in existing_tables:
                continue
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            counts[table] = int(cur.fetchone()[0])
    return counts


def _mission_flag_stats(conn, *, column_exists: bool) -> dict[str, int] | None:
    if not column_exists:
        return None
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE conta_missao_produtividade IS FALSE) AS false_rows,
                COUNT(*) FILTER (WHERE conta_missao_produtividade IS NULL) AS null_rows
            FROM missoes_operacionais
            """
        )
        row = cur.fetchone()
    return {
        "total": int(row[0]),
        "false_rows": int(row[1]),
        "null_rows": int(row[2]),
    }


def _build_plan(conn) -> SchemaRemovalPlan:
    existing_tables = _existing_tables(conn)
    existing_indexes = _existing_indexes(conn)
    column_exists = "missoes_operacionais" in existing_tables and _column_exists(
        conn,
        table="missoes_operacionais",
        column="conta_missao_produtividade",
    )
    return SchemaRemovalPlan(
        existing_tables=tuple(table for table in REMOVED_TABLES if table in existing_tables),
        existing_indexes=tuple(index for index in REMOVED_INDEXES if index in existing_indexes),
        column_exists=column_exists,
        row_counts=_count_rows(conn, REMOVED_TABLES, existing_tables),
        mission_flag_stats=_mission_flag_stats(conn, column_exists=column_exists),
    )


def _execute_schema_removal(conn) -> None:
    with conn.cursor() as cur:
        for statement in DESTRUCTIVE_SQL:
            cur.execute(statement)


def _policy_error_payload(*, execution_id: str, target: dict, args: argparse.Namespace) -> dict | None:
    expected_confirmation = _expected_confirmation(target)
    provided_confirmation = (
        args.confirm_schema_removal or os.getenv("PAINEL_TV_PRODUTIVIDADE_SCHEMA_REMOVAL_CONFIRM") or ""
    ).strip()
    missing: list[str] = []
    if args.retention_policy != RETENTION_POLICY:
        missing.append("retention_policy")
    if not (args.backup_reference or "").strip():
        missing.append("backup_reference")
    if provided_confirmation != expected_confirmation:
        missing.append("confirm_schema_removal")
    if not missing:
        return None
    return {
        "success": False,
        "error": "schema_removal_policy_required",
        "classification": "manual_unsafe",
        "mode": "execute",
        "execution_id": execution_id,
        "started_at": _utc_now_text(),
        "target": target,
        "missing": missing,
        "required_retention_policy": RETENTION_POLICY,
        "required_backup_reference": "referencia material de backup/snapshot antes do DROP",
        "required_confirmation": expected_confirmation,
        "confirmation_sources": [
            "--confirm-schema-removal",
            "PAINEL_TV_PRODUTIVIDADE_SCHEMA_REMOVAL_CONFIRM",
        ],
        "rollback": {
            "schema_sql": list(ROLLBACK_SCHEMA_SQL),
            "data_restore": "restaurar linhas removidas a partir do backup_reference informado",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run/aplicacao manual unsafe da remocao final de schema de Painel TV e Produtividade. "
            "Nao remove dados sem politica, backup e confirmacao explicita."
        )
    )
    parser.add_argument("--database-url", default="", help="Postgres URL. Default: DATABASE_URL.")
    parser.add_argument("--execute", action="store_true", help="Executa DROP/ALTER destrutivo. Sem esta flag e dry-run.")
    parser.add_argument(
        "--retention-policy",
        default="",
        help=f"Obrigatorio para --execute: {RETENTION_POLICY}.",
    )
    parser.add_argument(
        "--backup-reference",
        default="",
        help="Referencia material do backup/snapshot aprovado antes da destruicao.",
    )
    parser.add_argument(
        "--confirm-schema-removal",
        default="",
        help="Confirmacao obrigatoria: remove-painel-tv-produtividade-schema:<database>.",
    )
    args = parser.parse_args(argv)
    execution_id = uuid4().hex

    db_url = (args.database_url or os.getenv("DATABASE_URL") or "").strip()
    target = _database_target(db_url) if db_url else {}
    if not db_url:
        print(
            json.dumps(
                {
                    "success": False,
                    "error": "missing_database_url",
                    "classification": "manual_unsafe",
                    "execution_id": execution_id,
                    "started_at": _utc_now_text(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    if args.execute:
        policy_error = _policy_error_payload(execution_id=execution_id, target=target, args=args)
        if policy_error is not None:
            print(json.dumps(policy_error, ensure_ascii=False, indent=2))
            return 1

    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    try:
        before = _build_plan(conn)
        if not args.execute:
            conn.rollback()
            print(
                json.dumps(
                    {
                        "success": True,
                        "classification": "manual_unsafe",
                        "mode": "dry-run",
                        "execution_id": execution_id,
                        "started_at": _utc_now_text(),
                        "target": target,
                        "candidate_tables": list(REMOVED_TABLES),
                        "candidate_indexes": list(REMOVED_INDEXES),
                        "candidate_column": "missoes_operacionais.conta_missao_produtividade",
                        "existing_tables": list(before.existing_tables),
                        "existing_indexes": list(before.existing_indexes),
                        "column_exists": before.column_exists,
                        "row_counts": before.row_counts,
                        "mission_flag_stats": before.mission_flag_stats,
                        "required_policy_for_execute": RETENTION_POLICY,
                        "required_confirmation_for_execute": _expected_confirmation(target),
                        "rollback": {
                            "schema_sql": list(ROLLBACK_SCHEMA_SQL),
                            "data_restore": "restaurar linhas removidas a partir do backup_reference informado",
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        _execute_schema_removal(conn)
        after = _build_plan(conn)
        conn.commit()
        print(
            json.dumps(
                {
                    "success": True,
                    "classification": "manual_unsafe",
                    "mode": "execute",
                    "execution_id": execution_id,
                    "started_at": _utc_now_text(),
                    "target": target,
                    "retention_policy": args.retention_policy,
                    "backup_reference": args.backup_reference,
                    "before": before.__dict__,
                    "after": after.__dict__,
                    "rollback": {
                        "schema_sql": list(ROLLBACK_SCHEMA_SQL),
                        "data_restore": "restaurar linhas removidas a partir do backup_reference informado",
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except Exception as exc:
        conn.rollback()
        print(
            json.dumps(
                {
                    "success": False,
                    "error": "schema_removal_exception",
                    "classification": "manual_unsafe",
                    "detail": str(exc),
                    "execution_id": execution_id,
                    "started_at": _utc_now_text(),
                    "target": target,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    print(DIRECT_ENTRY_NOTICE, file=sys.stderr)
    raise SystemExit(main())
