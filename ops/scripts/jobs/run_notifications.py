"""IMPLEMENTATION: rotina de notificacoes usada pela entrada canonica.

Comando oficial: backend/tools/maintenance/run_notifications.py.
Execucao direta fica despriorizada para evitar concorrencia operacional.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.db import get_db
from backend.src.controle_treinamentos.jobs import (
    JOB_TYPE_SEND_DAILY_NOTIFICATIONS,
    collect_in_flight_jobs_by_type,
)
from backend.src.controle_treinamentos.mailer import generate_notification_payload, send_daily_notifications


DIRECT_ENTRY_NOTICE = (
    "Entrada direta despriorizada: ops/scripts/jobs/run_notifications.py e implementacao; "
    "use backend/tools/maintenance/run_notifications.py."
)


def _env_flag(name: str) -> bool:
    return (os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _direct_execution_guard(app) -> dict:
    try:
        with app.app_context():
            snapshot = collect_in_flight_jobs_by_type(get_db(), job_type=JOB_TYPE_SEND_DAILY_NOTIFICATIONS)
    except Exception as exc:
        return {
            "checked": False,
            "blocked": False,
            "status": "guard_unavailable",
            "error": str(exc)[:500],
        }

    in_flight = int(snapshot.get("total") or 0)
    override = _env_flag("NOTIFICATIONS_DIRECT_ALLOW_IN_FLIGHT")
    blocked = in_flight > 0 and not override
    status = "blocked" if blocked else ("override" if in_flight > 0 else "clear")
    return {
        "checked": True,
        "blocked": blocked,
        "status": status,
        "override_env": "NOTIFICATIONS_DIRECT_ALLOW_IN_FLIGHT" if override else None,
        "in_flight": snapshot,
    }


def _base_payload(*, guard: dict | None = None) -> dict:
    return {
        "mode": "direct_manual_compat",
        "execution_path": "ops/scripts/jobs/run_notifications.py",
        "in_flight_guard": guard or {},
    }


def main() -> int:
    try:
        app = create_app()
        guard = _direct_execution_guard(app)
        if guard.get("blocked"):
            _emit(
                {
                    "success": False,
                    "status": "blocked",
                    "error": "notification_job_in_flight",
                    "message": "Execucao direta bloqueada: ha send_daily_notifications queued/running na fila.",
                    **_base_payload(guard=guard),
                }
            )
            return 1

        with app.app_context():
            payload = generate_notification_payload()

            if not payload["recipients"]:
                _emit(
                    {
                        "success": False,
                        "status": "skipped",
                        "reason": "no_recipients",
                        "message": "No active email recipients configured.",
                        **_base_payload(guard=guard),
                    }
                )
                return 1

            if payload["total_items"] == 0:
                _emit(
                    {
                        "success": True,
                        "status": "skipped",
                        "reason": "no_due_items",
                        "message": "No due trainings to notify today.",
                        **_base_payload(guard=guard),
                    }
                )
                return 0

            if not payload.get("email_ready"):
                provider = (payload.get("provider") or "").strip().lower()
                missing = payload.get("missing_config_fields") or []
                _emit(
                    {
                        "success": False,
                        "status": "failed",
                        "reason": "email_config_incomplete",
                        "provider": provider or "smtp",
                        "missing_config_fields": missing,
                        "message": "Email configuration is incomplete.",
                        **_base_payload(guard=guard),
                    }
                )
                return 1

        result = send_daily_notifications(app)
        if result.sent:
            _emit(
                {
                    "success": True,
                    "status": "completed",
                    "reason": result.reason,
                    "message": "Daily notifications sent successfully.",
                    **_base_payload(guard=guard),
                }
            )
            return 0

        if result.error:
            message = f"Daily notifications were not sent. Reason: {result.reason}. Error: {result.error}"
        else:
            message = f"Daily notifications were not sent. Reason: {result.reason}"
        _emit(
            {
                "success": result.reason == "no_due_items",
                "status": "skipped" if result.reason == "no_due_items" else "failed",
                "reason": result.reason,
                "error": result.error,
                "message": message,
                **_base_payload(guard=guard),
            }
        )
        return 0 if result.reason == "no_due_items" else 1
    except RuntimeError as exc:
        _emit({"success": False, "status": "failed", "error": "runtime_error", "message": str(exc), **_base_payload()})
        return 1
    except Exception as exc:
        _emit({"success": False, "status": "failed", "error": "unexpected_failure", "message": str(exc), **_base_payload()})
        return 1


if __name__ == "__main__":
    print(DIRECT_ENTRY_NOTICE, file=sys.stderr)
    raise SystemExit(main())
