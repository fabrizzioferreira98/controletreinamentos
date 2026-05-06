from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


import argparse
import json
from dataclasses import dataclass

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.db import execute_script, get_db, schema_consistency_report


@dataclass
class QueryCheck:
    name: str
    query: str


DATA_CHECKS = [
    QueryCheck(
        name="tripulantes_incompletos",
        query="""
            SELECT COUNT(*) AS total
            FROM tripulantes
            WHERE TRIM(COALESCE(nome, '')) = ''
               OR TRIM(COALESCE(cpf, '')) = ''
               OR TRIM(COALESCE(licenca_anac, '')) = ''
               OR TRIM(COALESCE(base, '')) = ''
        """,
    ),
    QueryCheck(
        name="treinamentos_sem_vencimento",
        query="SELECT COUNT(*) AS total FROM treinamentos WHERE data_vencimento IS NULL",
    ),
    QueryCheck(
        name="missoes_sem_tripulante",
        query="""
            SELECT COUNT(*) AS total
            FROM missoes_operacionais m
            LEFT JOIN missao_tripulantes mt ON mt.missao_id = m.id
            WHERE mt.id IS NULL
        """,
    ),
    QueryCheck(
        name="pernoites_quantidade_invalida",
        query="SELECT COUNT(*) AS total FROM pernoites_operacionais WHERE quantidade <= 0",
    ),
    QueryCheck(
        name="tripulantes_status_nao_canonico",
        query="""
            SELECT COUNT(*) AS total
            FROM tripulantes
            WHERE LOWER(TRIM(COALESCE(status, ''))) NOT IN (
                'ativo', 'folga', 'ferias', 'férias', 'atestado', 'afastado', 'treinamento'
            )
        """,
    ),
    QueryCheck(
        name="pilotos_status_nao_canonico",
        query="""
            SELECT COUNT(*) AS total
            FROM pilotos
            WHERE LOWER(TRIM(COALESCE(status, ''))) NOT IN (
                'ativo', 'folga', 'ferias', 'férias', 'atestado', 'afastado', 'treinamento'
            )
        """,
    ),
]


def _safe_count(db, query: str) -> tuple[int | None, str | None]:
    try:
        row = db.execute(query).fetchone()
        if row is None:
            return 0, None
        if hasattr(row, "keys"):
            value = row["total"] if "total" in row.keys() else row[next(iter(row.keys()))]
        else:
            value = row[0]
        return int(value or 0), None
    except Exception as exc:  # pragma: no cover - variates by DB state
        return None, str(exc)


def collect_data_consistency_report(db) -> dict:
    checks = []
    total_issues = 0
    for item in DATA_CHECKS:
        total, error = _safe_count(db, item.query)
        if total is not None:
            total_issues += int(total)
        checks.append({"name": item.name, "total": total, "error": error})
    return {"total_issues": total_issues, "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(description="Valida e repara consistência estrutural do banco de dados.")
    parser.add_argument("--repair", action="store_true", help="Executa migrações/seed antes da validação.")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Imprime saída em JSON.")
    args = parser.parse_args()

    app = create_app()

    try:
        with app.app_context():
            db = get_db()
            if args.repair:
                execute_script()
            schema_report = schema_consistency_report(db)
            data_report = collect_data_consistency_report(db)
    except Exception as exc:
        message = f"Falha ao validar consistência do banco: {exc}"
        if args.as_json:
            print(json.dumps({"ok": False, "error": message}, ensure_ascii=False, indent=2))
        else:
            print(message)
        return 1

    result = {
        "ok": bool(schema_report["is_consistent"] and data_report["total_issues"] == 0),
        "schema": schema_report,
        "data": data_report,
    }

    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("=== Consistência do Banco ===")
        print(f"Schema consistente: {'sim' if schema_report['is_consistent'] else 'não'}")
        print(f"Tabelas faltantes: {schema_report['missing_tables'] or 'nenhuma'}")
        print(f"Colunas faltantes: {schema_report['missing_columns'] or 'nenhuma'}")
        print(f"Inconsistências de dados: {data_report['total_issues']}")
        for check in data_report["checks"]:
            if check["error"]:
                print(f"- {check['name']}: indisponível ({check['error']})")
            else:
                print(f"- {check['name']}: {check['total']}")

    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
