from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass

import psycopg2


@dataclass(frozen=True)
class CleanupStep:
    table: str
    where: str | None = None
    params: tuple = ()


TABLES_TO_COUNT = (
    "usuarios",
    "tripulantes",
    "equipamentos",
    "tipos_treinamento",
    "treinamentos",
    "treinamento_anexos_pdf",
    "tripulante_arquivos_pdf",
    "notificacoes_email",
    "notificacoes_treinamento",
    "missoes_operacionais",
    "missao_tripulantes",
    "pernoites_operacionais",
    "produtividade_adicionais_excepcionais",
    "produtividade_conferencias",
    "pilotos",
    "historico_status_piloto",
    "background_jobs",
    "background_job_executions",
    "backups_execucoes",
    "auditoria_eventos",
    "sistema_controle",
    "bases",
)


def _existing_tables(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        return {str(row[0]) for row in cur.fetchall()}


def _count_rows(conn, tables: tuple[str, ...]) -> dict[str, int]:
    out: dict[str, int] = {}
    existing = _existing_tables(conn)
    with conn.cursor() as cur:
        for table in tables:
            if table not in existing:
                continue
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            out[table] = int(cur.fetchone()[0])
    return out


def _admin_snapshot(conn, preserve_login: str) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, login, nome, perfil, ativo
            FROM usuarios
            WHERE login = %s
            LIMIT 1
            """,
            (preserve_login,),
        )
        row = cur.fetchone()
    if not row:
        return {"found": False, "login": preserve_login}
    return {
        "found": True,
        "id": int(row[0]),
        "login": row[1],
        "nome": row[2],
        "perfil": row[3],
        "ativo": int(row[4]),
    }


def _build_cleanup_steps(preserve_login: str) -> list[CleanupStep]:
    return [
        CleanupStep("background_job_executions"),
        CleanupStep("background_jobs"),
        CleanupStep("backups_execucoes"),
        CleanupStep("notificacoes_treinamento"),
        CleanupStep("treinamento_anexos_pdf"),
        CleanupStep("tripulante_arquivos_pdf"),
        CleanupStep("missao_tripulantes"),
        CleanupStep("pernoites_operacionais"),
        CleanupStep("produtividade_conferencias"),
        CleanupStep("produtividade_adicionais_excepcionais"),
        CleanupStep("missoes_operacionais"),
        CleanupStep("treinamentos"),
        CleanupStep("historico_status_piloto"),
        CleanupStep("pilotos"),
        CleanupStep("auditoria_eventos"),
        CleanupStep("notificacoes_email"),
        CleanupStep("tripulantes"),
        CleanupStep("equipamentos"),
        CleanupStep("tipos_treinamento"),
        CleanupStep("sistema_controle"),
        CleanupStep("usuarios", where="login <> %s", params=(preserve_login,)),
    ]


def _execute_cleanup(conn, *, preserve_login: str) -> dict[str, int]:
    deleted: dict[str, int] = {}
    existing = _existing_tables(conn)
    with conn.cursor() as cur:
        for step in _build_cleanup_steps(preserve_login):
            if step.table not in existing:
                continue
            if step.where:
                cur.execute(f"DELETE FROM {step.table} WHERE {step.where}", step.params)
            else:
                cur.execute(f"DELETE FROM {step.table}")
            deleted[step.table] = int(cur.rowcount if cur.rowcount is not None else 0)
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Limpeza controlada de dados operacionais. "
            "Preserva schema/config estrutural e o usuário admin informado."
        )
    )
    parser.add_argument("--database-url", default="", help="Postgres URL. Default: DATABASE_URL.")
    parser.add_argument(
        "--preserve-login",
        required=True,
        help="Login do usuário admin a preservar.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Executa limpeza. Sem esta flag roda apenas em modo dry-run.",
    )
    args = parser.parse_args()

    db_url = (args.database_url or os.getenv("DATABASE_URL") or "").strip()
    if not db_url:
        print(json.dumps({"success": False, "error": "missing_database_url"}, ensure_ascii=False, indent=2))
        return 1

    preserve_login = (args.preserve_login or "").strip()
    if not preserve_login:
        print(json.dumps({"success": False, "error": "missing_preserve_login"}, ensure_ascii=False, indent=2))
        return 1

    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    try:
        before_counts = _count_rows(conn, TABLES_TO_COUNT)
        admin_before = _admin_snapshot(conn, preserve_login)
        if not admin_before.get("found"):
            conn.rollback()
            print(
                json.dumps(
                    {
                        "success": False,
                        "error": "preserve_admin_not_found",
                        "preserve_login": preserve_login,
                        "before_counts": before_counts,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1

        if not args.execute:
            conn.rollback()
            print(
                json.dumps(
                    {
                        "success": True,
                        "mode": "dry-run",
                        "preserve_admin": admin_before,
                        "before_counts": before_counts,
                        "cleanup_plan_tables": [step.table for step in _build_cleanup_steps(preserve_login)],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        deleted = _execute_cleanup(conn, preserve_login=preserve_login)
        after_counts = _count_rows(conn, TABLES_TO_COUNT)
        admin_after = _admin_snapshot(conn, preserve_login)
        if not admin_after.get("found"):
            conn.rollback()
            print(
                json.dumps(
                    {
                        "success": False,
                        "error": "admin_missing_after_cleanup",
                        "preserve_login": preserve_login,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1

        conn.commit()
        print(
            json.dumps(
                {
                    "success": True,
                    "mode": "execute",
                    "preserve_admin": admin_after,
                    "deleted_rows_by_table": deleted,
                    "before_counts": before_counts,
                    "after_counts": after_counts,
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
                {"success": False, "error": "cleanup_exception", "detail": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
