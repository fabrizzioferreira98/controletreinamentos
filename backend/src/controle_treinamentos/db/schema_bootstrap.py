from __future__ import annotations

import re

from flask import current_app

from .schema import _REQUIRED_COLUMNS_BY_TABLE, SCHEMA, _expected_tables_from_schema


def _schema_statements(*, kind: str) -> list[str]:
    if kind == "tables":
        pattern = r"(CREATE TABLE IF NOT EXISTS\s+[a-zA-Z_][a-zA-Z0-9_]*\s*\(.*?\);)"
    elif kind == "indexes":
        pattern = r"(CREATE(?: UNIQUE)? INDEX IF NOT EXISTS\s+[a-zA-Z_][a-zA-Z0-9_]*\s+ON\s+.*?;)"
    else:  # pragma: no cover - defensive guard
        raise ValueError(f"Unsupported schema statement kind: {kind}")
    return [statement.strip() for statement in re.findall(pattern, SCHEMA, flags=re.DOTALL | re.IGNORECASE)]


def _execute_schema_statements(db, *, kind: str) -> None:
    for statement in _schema_statements(kind=kind):
        db.execute(statement)


def execute_schema_bootstrap(db) -> None:
    try:
        _execute_schema_statements(db, kind="tables")
        db.commit()
    except Exception as exc:
        current_app.logger.warning(f"Could not bootstrap base tables from schema script: {exc}")
        db.conn.rollback()

    try:
        _execute_schema_statements(db, kind="indexes")
        db.commit()
    except Exception as exc:
        current_app.logger.warning(f"Could not apply schema indexes bootstrap: {exc}")
        db.conn.rollback()


def schema_consistency_report(db) -> dict:
    expected_tables = _expected_tables_from_schema()
    existing_rows = db.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE'
        """
    ).fetchall()
    existing_tables = {row["table_name"] for row in existing_rows}
    missing_tables = sorted(set(expected_tables) - existing_tables)

    missing_columns: dict[str, list[str]] = {}
    for table_name, required_columns in _REQUIRED_COLUMNS_BY_TABLE.items():
        if table_name not in existing_tables:
            missing_columns[table_name] = list(required_columns)
            continue
        column_rows = db.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            """,
            (table_name,),
        ).fetchall()
        existing_columns = {row["column_name"] for row in column_rows}
        missing_for_table = [column for column in required_columns if column not in existing_columns]
        if missing_for_table:
            missing_columns[table_name] = missing_for_table

    return {
        "expected_tables_total": len(expected_tables),
        "existing_tables_total": len(existing_tables),
        "missing_tables": missing_tables,
        "missing_columns": missing_columns,
        "is_consistent": not missing_tables and not missing_columns,
    }


def repair_and_validate_schema(db) -> dict:
    execute_schema_bootstrap(db)
    from .migrations import execute_corrective_migrations

    execute_corrective_migrations(db)
    report = schema_consistency_report(db)
    if not report["is_consistent"]:
        raise RuntimeError(
            "Banco inconsistente apos migracao automatica. "
            f"Tabelas faltantes: {', '.join(report['missing_tables']) or 'nenhuma'}. "
            f"Colunas faltantes: {report['missing_columns'] or 'nenhuma'}."
        )
    return report
