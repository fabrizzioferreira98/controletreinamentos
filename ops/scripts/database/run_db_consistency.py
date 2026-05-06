"""IMPLEMENTATION: rotina de consistencia e repair manual isolado.

Comando oficial para validacao: backend/tools/maintenance/run_db_consistency.py.
Comando oficial para repair manual/perigoso: backend/tools/manual_unsafe/run_db_repair.py.
Execucao direta fica despriorizada para evitar ambiguidade operacional.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


import argparse
import json
from dataclasses import dataclass

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.db import get_db, repair_and_validate_schema, schema_consistency_report


DIRECT_ENTRY_NOTICE = (
    "Entrada direta despriorizada: ops/scripts/database/run_db_consistency.py e implementacao; "
    "use backend/tools/maintenance/run_db_consistency.py para validacao e "
    "backend/tools/manual_unsafe/run_db_repair.py para repair manual."
)
REPAIR_ACK_TOKEN = "run-db-repair-manual-unsafe"


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Valida e repara consistência estrutural do banco de dados.")
    parser.add_argument("--repair", action="store_true", help="Executa migrações/seed antes da validação.")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Imprime saída em JSON.")
    parser.add_argument("--repair-ack", default="", help="Confirmacao explicita para repair manual/perigoso.")
    args = parser.parse_args(argv)

    if args.repair and (args.repair_ack or "").strip() != REPAIR_ACK_TOKEN:
        payload = {
            "ok": False,
            "error": "manual_unsafe_repair_ack_required",
            "message": (
                "Repair saiu da trilha normal. Use backend/tools/manual_unsafe/run_db_repair.py "
                "ou confirme explicitamente o risco."
            ),
            "required_ack": REPAIR_ACK_TOKEN,
            "classification": "manual_unsafe",
        }
        if args.as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(payload["message"])
            print(f"Ack obrigatorio: {REPAIR_ACK_TOKEN}")
        return 1

    app = create_app()

    try:
        with app.app_context():
            db = get_db()
            if args.repair:
                schema_report = repair_and_validate_schema(db)
            else:
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
        "classification": "manual_unsafe" if args.repair else "validation",
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
    print(DIRECT_ENTRY_NOTICE, file=sys.stderr)
    raise SystemExit(main())
