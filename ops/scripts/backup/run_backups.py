"""IMPLEMENTATION: rotina de backup usada pela entrada canonica.

Comando oficial: backend/tools/maintenance/run_backups.py.
Execucao direta fica despriorizada para evitar concorrencia operacional.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.backup import run_backup_job
from backend.src.controle_treinamentos.db import get_db
from backend.src.controle_treinamentos.jobs import JOB_TYPE_RUN_BACKUP, collect_in_flight_jobs_by_type


DIRECT_ENTRY_NOTICE = (
    "Entrada direta despriorizada: ops/scripts/backup/run_backups.py e implementacao; "
    "use backend/tools/maintenance/run_backups.py."
)


def _env_flag(name: str) -> bool:
    return (os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _direct_execution_guard(app) -> dict:
    try:
        with app.app_context():
            snapshot = collect_in_flight_jobs_by_type(get_db(), job_type=JOB_TYPE_RUN_BACKUP)
    except Exception as exc:
        return {
            "checked": False,
            "blocked": False,
            "status": "guard_unavailable",
            "error": str(exc)[:500],
        }

    in_flight = int(snapshot.get("total") or 0)
    override = _env_flag("BACKUP_DIRECT_ALLOW_IN_FLIGHT")
    blocked = in_flight > 0 and not override
    status = "blocked" if blocked else ("override" if in_flight > 0 else "clear")
    return {
        "checked": True,
        "blocked": blocked,
        "status": status,
        "override_env": "BACKUP_DIRECT_ALLOW_IN_FLIGHT" if override else None,
        "in_flight": snapshot,
    }


def main() -> int:
    app = create_app()
    app.logger.info(
        "Backup command started.",
        extra={
            "event": "backup_command_start",
            "component": "backup_cli",
            "execution_path": "ops/scripts/backup/run_backups.py",
        },
    )
    guard = _direct_execution_guard(app)
    if guard.get("blocked"):
        app.logger.warning(
            "Backup command blocked by in-flight guard.",
            extra={
                "event": "backup_command_blocked",
                "component": "backup_cli",
                "reason": "backup_job_in_flight",
                "in_flight_guard": guard,
            },
        )
        print(
            json.dumps(
                {
                    "success": False,
                    "status": "blocked",
                    "error": "backup_job_in_flight",
                    "message": "Execucao direta bloqueada: ha run_backup queued/running na fila.",
                    "mode": "direct_manual_compat",
                    "execution_path": "ops/scripts/backup/run_backups.py",
                    "in_flight_guard": guard,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    with app.app_context():
        result = run_backup_job(backup_type="agendado")
        app.logger.info(
            "Backup command completed.",
            extra={
                "event": "backup_command_complete",
                "component": "backup_cli",
                "success": bool(result.success),
                "status": result.status,
                "file_path": result.file_path,
                "artifacts_count": len(result.artifacts),
                "size_bytes": result.size_bytes,
                "duration_ms": result.duration_ms,
                "in_flight_guard": guard,
            },
        )
        print(
            json.dumps(
                {
                    "success": result.success,
                    "status": result.status,
                    "message": result.message,
                    "mode": "direct_manual_compat",
                    "execution_path": "ops/scripts/backup/run_backups.py",
                    "in_flight_guard": guard,
                    "file_path": result.file_path,
                    "artifacts": result.artifacts,
                    "size_bytes": result.size_bytes,
                    "duration_ms": result.duration_ms,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        if result.success:
            return 0
        return 1


if __name__ == "__main__":
    print(DIRECT_ENTRY_NOTICE, file=sys.stderr)
    raise SystemExit(main())
