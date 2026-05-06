import os
import sys
import traceback
from hmac import compare_digest
from uuid import uuid4

from flask import Flask, jsonify, request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

app = Flask(__name__)


def _boot_failure_response(exc: Exception):
    error_ref = uuid4().hex
    error_details = traceback.format_exc()
    sys.stderr.write(f"[CRON BOOT FAILURE][ref={error_ref}] {exc}\n{error_details}\n")
    return (
        jsonify(
            {
                "success": False,
                "error": "BOOT_FAILURE_CRON",
                "message": "Falha interna ao inicializar rotina de cron.",
                "error_ref": error_ref,
            }
        ),
        500,
    )


@app.route('/', defaults={'path': ''}, methods=['GET', 'POST'])
@app.route('/<path:path>', methods=['GET', 'POST'])
def cron_handler(path):
    auth_header = request.headers.get('Authorization')
    cron_secret = os.environ.get("CRON_SECRET", "")
    expected_header = f"Bearer {cron_secret}" if cron_secret else ""
    if not expected_header or not compare_digest(auth_header or "", expected_header):
        return jsonify({"error": "Unauthorized"}), 401

    try:
        from backend.src.controle_treinamentos import create_app
        from backend.src.controle_treinamentos.db import get_db
        from backend.src.controle_treinamentos.jobs import (
            build_bucketed_idempotency_key,
            enqueue_backup_job,
            enqueue_notifications_job,
        )
        main_app = create_app()
    except Exception as exc:
        return _boot_failure_response(exc)

    task = (request.args.get("task", "") or "").strip().lower()
    if not task and path:
        task = path.strip("/").lower()

    with main_app.app_context():
        db = get_db()
        if task not in {"", "notificacoes", "notifications", "backup"}:
            return jsonify({"success": False, "error": "Unsupported task", "task": task}), 400

        if task == "backup":
            try:
                enqueue_result = enqueue_backup_job(
                    db,
                    source="cron",
                    backup_type="agendado",
                    idempotency_key=build_bucketed_idempotency_key("cron-backup", granularity="hour"),
                )
                db.commit()
            except RuntimeError as exc:
                db.conn.rollback()
                return jsonify(
                    {
                        "success": False,
                        "task": "backup",
                        "error": "queue_saturated",
                        "message": str(exc),
                    }
                ), 429
            except Exception:
                db.conn.rollback()
                return jsonify(
                    {
                        "success": False,
                        "task": "backup",
                        "error": "enqueue_failed",
                    }
                ), 500
            return jsonify(
                {
                    "success": True,
                    "task": "backup",
                    "job_id": enqueue_result.job_id,
                    "job_created": enqueue_result.created,
                    "job_status": enqueue_result.status,
                    "processed": False,
                    "message": "Backup enfileirado com sucesso.",
                }
            ), 202

        try:
            enqueue_result = enqueue_notifications_job(
                db,
                source="cron",
                idempotency_key=build_bucketed_idempotency_key("cron-notifications", granularity="day"),
            )
            db.commit()
        except RuntimeError as exc:
            db.conn.rollback()
            return jsonify(
                {
                    "success": False,
                    "task": "notifications",
                    "error": "queue_saturated",
                    "message": str(exc),
                }
            ), 429
        except Exception:
            db.conn.rollback()
            return jsonify(
                {
                    "success": False,
                    "task": "notifications",
                    "error": "enqueue_failed",
                }
            ), 500
        return jsonify(
            {
                "success": True,
                "task": "notifications",
                "job_id": enqueue_result.job_id,
                "job_created": enqueue_result.created,
                "job_status": enqueue_result.status,
                "processed": False,
                "message": "Notificações enfileiradas com sucesso.",
            }
        ), 202
