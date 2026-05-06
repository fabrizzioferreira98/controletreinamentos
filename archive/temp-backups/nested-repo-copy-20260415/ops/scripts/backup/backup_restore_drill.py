from __future__ import annotations

import argparse
import gzip
import json
import os
import subprocess
import sys
import tarfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.backup import run_backup_job
from backend.src.controle_treinamentos.core.postgres_tools import find_postgres_binary
from backend.src.controle_treinamentos.core.workspace_paths import evidence_root

_CRITICAL_TABLES = (
    "usuarios",
    "tripulantes",
    "treinamentos",
    "background_jobs",
    "treinamento_anexos_pdf",
    "tripulante_arquivos_pdf",
)


def _replace_db_in_url(url: str, db_name: str) -> str:
    parsed = urlparse(url)
    new_path = f"/{db_name}"
    return urlunparse((parsed.scheme, parsed.netloc, new_path, parsed.params, parsed.query, parsed.fragment))


def _run_pg_restore_list(dump_path: Path) -> tuple[bool, str]:
    pg_restore_binary = find_postgres_binary("pg_restore")
    if not pg_restore_binary:
        return False, "pg_restore nao encontrado no ambiente. Configure PG_BIN_DIR/PG_RESTORE_PATH."
    try:
        completed = subprocess.run(
            [str(pg_restore_binary), "--list", str(dump_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        return False, "pg_restore não encontrado no ambiente."
    except subprocess.TimeoutExpired:
        return False, "Timeout ao validar dump com pg_restore --list."

    if completed.returncode != 0:
        msg = (completed.stderr or completed.stdout or "Falha ao validar dump.").strip()
        return False, msg[:500]
    return True, "Dump validado por pg_restore --list."


def _collect_table_counts(conn, tables: tuple[str, ...] = _CRITICAL_TABLES) -> dict[str, int | None]:
    counts: dict[str, int | None] = {}
    with conn.cursor() as cur:
        for table in tables:
            try:
                cur.execute(f'SELECT COUNT(*) FROM "{table}"')
                counts[table] = int(cur.fetchone()[0])
            except Exception:
                counts[table] = None
                conn.rollback()
    return counts


def _run_full_restore(dump_path: Path, restore_url: str, *, restore_schema: str = "public") -> tuple[bool, dict]:
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    temp_db = f"restore_drill_{stamp}"
    admin_conn = None
    restored_conn = None
    payload = {"temp_db": temp_db}
    pg_restore_binary = find_postgres_binary("pg_restore")
    if not pg_restore_binary:
        payload["restore_error"] = "pg_restore nao encontrado no ambiente. Configure PG_BIN_DIR/PG_RESTORE_PATH."
        return False, payload

    try:
        admin_conn = psycopg2.connect(restore_url)
        admin_conn.autocommit = True
        parsed_restore = urlparse(restore_url)
        payload["restore_server"] = f"{parsed_restore.hostname or ''}:{parsed_restore.port or 5432}"
        payload["source_table_counts"] = {}
        source_db = (urlparse(restore_url).path or "/").lstrip("/") or "postgres"
        payload["source_database"] = source_db
        source_conn = None
        try:
            source_conn = psycopg2.connect(_replace_db_in_url(restore_url, source_db))
            payload["source_table_counts"] = _collect_table_counts(source_conn)
        finally:
            if source_conn is not None:
                source_conn.close()
        with admin_conn.cursor() as cur:
            cur.execute(f'CREATE DATABASE "{temp_db}"')

        target_url = _replace_db_in_url(restore_url, temp_db)
        payload["target_url"] = target_url

        command = [
            str(pg_restore_binary),
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-privileges",
            *( [f"--schema={restore_schema}"] if restore_schema else [] ),
            "--dbname",
            target_url,
            str(dump_path),
        ]

        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=900,
        )
        if completed.returncode != 0:
            payload["restore_error"] = (completed.stderr or completed.stdout or "Falha no pg_restore.")[:1000]
            return False, payload

        restored_conn = psycopg2.connect(target_url)
        with restored_conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS total
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE'
                  AND table_schema NOT IN ('pg_catalog', 'information_schema')
                """
            )
            payload["restored_table_count"] = int(cur.fetchone()[0])
            restored_counts = _collect_table_counts(restored_conn)
            payload["key_table_counts"] = restored_counts
            payload["counts_match"] = restored_counts == payload["source_table_counts"]
            if not payload["counts_match"]:
                payload["count_mismatch_tables"] = [
                    table
                    for table in sorted(set(restored_counts) | set(payload["source_table_counts"]))
                    if restored_counts.get(table) != payload["source_table_counts"].get(table)
                ]
                payload["restore_error"] = "Restore concluiu, mas as contagens das tabelas críticas divergem da origem."
                return False, payload

        # Close active restore connection before dropping temp DB.
        restored_conn.close()
        restored_conn = None

        try:
            with admin_conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = %s
                      AND pid <> pg_backend_pid()
                    """,
                    (temp_db,),
                )
                cur.execute(f'DROP DATABASE IF EXISTS "{temp_db}"')
            payload["dropped_temp_db"] = True
        except Exception as cleanup_exc:
            # Restore validation already succeeded; keep drill as success with warning.
            payload["dropped_temp_db"] = False
            payload["cleanup_warning"] = str(cleanup_exc)
        return True, payload
    except Exception as exc:
        payload["exception"] = str(exc)
        return False, payload
    finally:
        if restored_conn is not None:
            try:
                restored_conn.close()
            except Exception:
                pass
        if admin_conn is not None:
            try:
                admin_conn.close()
            except Exception:
                pass


def _validate_tar_archive(archive_path: Path) -> tuple[bool, dict]:
    payload: dict = {"archive": str(archive_path)}
    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            members = [member for member in tar.getmembers() if member.isfile() or member.isdir()]
        payload["members_count"] = len(members)
        payload["top_level_names"] = sorted({member.name.split("/", 1)[0] for member in members[:50] if member.name})
        return True, payload
    except Exception as exc:
        payload["error"] = str(exc)
        return False, payload


def _extract_tar_archive(archive_path: Path, target_dir: Path) -> tuple[bool, dict]:
    payload: dict = {"archive": str(archive_path), "target_dir": str(target_dir)}
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(target_dir)
            members = [member.name for member in tar.getmembers()]
        payload["restored_members_count"] = len(members)
        payload["restored_sample"] = members[:20]
        return True, payload
    except Exception as exc:
        payload["error"] = str(exc)
        return False, payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Drill de backup/restore (pré-deploy).")
    parser.add_argument(
        "--restore-url",
        default="",
        help="URL de um Postgres isolado para restore real (opcional).",
    )
    parser.add_argument(
        "--restore-schema",
        default="public",
        help="Schema alvo para restore drill (default: public).",
    )
    parser.add_argument(
        "--extract-archives",
        action="store_true",
        help="Extrai os arquivos .tar.gz gerados para validar restore de arquivos/configurações.",
    )
    args = parser.parse_args()

    report: dict = {"steps": []}
    db_url = (os.getenv("DATABASE_URL", "") or "").strip()
    if not db_url:
        print(json.dumps({"success": False, "message": "DATABASE_URL não configurada."}, ensure_ascii=False, indent=2))
        return 1

    app = create_app()
    with app.app_context():
        result = run_backup_job(backup_type="drill")

    backup_step = {
        "step": "backup_run",
        "success": bool(result.success),
        "status": result.status,
        "message": result.message,
        "file_path": result.file_path,
        "artifacts": result.artifacts,
        "size_bytes": result.size_bytes,
        "duration_ms": result.duration_ms,
    }
    report["steps"].append(backup_step)
    if not result.success or not result.file_path:
        report["success"] = False
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    dump_path = Path(result.file_path)
    asset_archives = [Path(item) for item in result.artifacts if item.endswith(".tar.gz")]
    file_ok = dump_path.exists() and dump_path.stat().st_size > 0
    report["steps"].append(
        {
            "step": "artifact_exists",
            "success": bool(file_ok),
            "path": str(dump_path),
            "size_bytes": int(dump_path.stat().st_size) if dump_path.exists() else 0,
        }
    )
    if not file_ok:
        report["success"] = False
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    for archive_path in asset_archives:
        ok_archive, payload = _validate_tar_archive(archive_path)
        report["steps"].append({"step": "archive_integrity", "success": ok_archive, **payload})
        if not ok_archive:
            report["success"] = False
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 1
        if args.extract_archives:
            restore_dir = evidence_root() / "restore_drill" / archive_path.stem
            ok_extract, extract_payload = _extract_tar_archive(archive_path, restore_dir)
            report["steps"].append({"step": "archive_restore", "success": ok_extract, **extract_payload})
            if not ok_extract:
                report["success"] = False
                print(json.dumps(report, ensure_ascii=False, indent=2))
                return 1

    suffix = dump_path.suffix.lower()
    if suffix == ".dump":
        ok, msg = _run_pg_restore_list(dump_path)
        report["steps"].append({"step": "dump_integrity", "success": ok, "message": msg})
        if not ok:
            report["success"] = False
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 1

        restore_url = (args.restore_url or "").strip()
        if restore_url:
            ok_restore, payload = _run_full_restore(
                dump_path,
                restore_url,
                restore_schema=(args.restore_schema or "").strip(),
            )
            report["steps"].append({"step": "restore_full", "success": ok_restore, **payload})
            report["success"] = ok_restore
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if ok_restore else 1

        report["steps"].append(
            {
                "step": "restore_full",
                "success": False,
                "skipped": True,
                "message": "Restore real não executado (passe --restore-url para concluir o drill completo).",
            }
        )
        report["success"] = False
        report["status"] = "partial"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    if suffix.endswith(".gz"):
        try:
            with gzip.open(dump_path, "rb") as fh:
                _ = fh.read(1024)
            report["steps"].append(
                {
                    "step": "gzip_integrity",
                    "success": True,
                    "message": "Arquivo compactado íntegro.",
                }
            )
        except Exception as exc:
            report["steps"].append(
                {
                    "step": "gzip_integrity",
                    "success": False,
                    "message": f"Falha ao validar gzip: {exc}",
                }
            )
            report["success"] = False
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 1

        report["steps"].append(
            {
                "step": "restore_full",
                "success": False,
                "skipped": True,
                "message": "Restore automático não suportado para artefato .gz neste script.",
            }
        )
        report["success"] = False
        report["status"] = "partial"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    report["steps"].append(
        {
            "step": "restore_full",
            "success": False,
            "skipped": True,
            "message": f"Tipo de artefato não suportado para restore automático: {dump_path.name}",
        }
    )
    report["success"] = False
    report["status"] = "partial"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
