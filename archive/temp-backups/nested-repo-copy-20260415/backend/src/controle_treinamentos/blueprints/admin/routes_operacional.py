from __future__ import annotations

import os
import time
from datetime import datetime

from flask import Response, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from ...auth import permission_required
from ...backup import list_backup_history
from ...core.http_contract import programmatic_json
from ...core.utils import env_int
from ...db import get_db
from ...jobs import (
    JOB_STATUS_DEAD_LETTER,
    build_bucketed_idempotency_key,
    enqueue_backup_job,
    requeue_dead_letter_job,
)
from ...monitoring import collect_system_monitoring_snapshot, format_bytes_human
from ...reports import build_user_guide_pdf
from ...repositories.dashboard_cache import get_panel_cache, set_panel_cache
from . import admin_bp


@admin_bp.route("/backups")
@permission_required("backups:view")
def backups_list():
    rows = list_backup_history(limit=120)
    return render_template(
        "backups_list.html",
        backups=rows,
        backup_remote_enabled=(os.getenv("BACKUP_REMOTE_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}),
        backup_remote_bucket=(os.getenv("BACKUP_S3_BUCKET", "") or "").strip(),
        backup_retention_days=env_int("BACKUP_RETENTION_DAYS", 15, minimum=1),
    )


@admin_bp.route("/backups/executar", methods=["POST"])
@permission_required("backups:run")
def backups_run():
    db = get_db()
    idempotency_key = build_bucketed_idempotency_key(
        "manual-backup",
        granularity="minute",
        suffix=str(current_user.id),
    )
    from flask import g as flask_g
    enqueue_result = enqueue_backup_job(
        db,
        source="manual",
        backup_type="manual",
        requested_by=int(current_user.id),
        idempotency_key=idempotency_key,
        request_id=getattr(flask_g, "request_id", None),
    )
    db.commit()

    if not enqueue_result.created and enqueue_result.status in {"queued", "running"}:
        flash("Já existe um backup em processamento para esta janela. Aguarde a conclusão.", "error")
        return redirect(url_for("admin.backups_list"))
    if not enqueue_result.created and enqueue_result.status == "succeeded":
        flash("Backup já processado com sucesso nesta janela de execução.", "success")
        return redirect(url_for("admin.backups_list"))
    if not enqueue_result.created and enqueue_result.status in {"dead_letter", "failed", "canceled"}:
        retry_key = f"{idempotency_key}:retry:{int(time.time())}"
        try:
            from flask import g as flask_g
            enqueue_result = enqueue_backup_job(
                db,
                source="manual",
                backup_type="manual",
                requested_by=int(current_user.id),
                idempotency_key=retry_key,
                request_id=getattr(flask_g, "request_id", None),
            )
            db.commit()
        except Exception:
            db.conn.rollback()
            current_app.logger.exception("Falha ao reenfileirar backup manual.")
            flash("O backup anterior falhou e não foi possível reenfileirar agora. Tente novamente.", "error")
            return redirect(url_for("admin.backups_list"))

    flash(
        f"Backup enfileirado com sucesso (job #{enqueue_result.job_id}). "
        "Acompanhe o status no monitoramento de jobs.",
        "success",
    )
    return redirect(url_for("admin.backups_list"))


@admin_bp.route("/monitoramento")
@permission_required("monitoramento:view")
def monitoramento_sistema():
    db = get_db()
    monitoramento_timeout = env_int("MONITORAMENTO_STATEMENT_TIMEOUT_MS", 4000, minimum=0)
    if monitoramento_timeout > 0:
        try:
            db.execute("SET LOCAL statement_timeout = %s", (monitoramento_timeout,))
        except Exception:
            current_app.logger.debug("Não foi possível aplicar statement_timeout local no monitoramento.")
    force_refresh = (request.args.get("refresh", "") or "").strip().lower() in {"1", "true", "yes", "on"}
    cache_key = "monitoramento:snapshot"
    monitoramento_ttl = env_int("MONITORAMENTO_CACHE_TTL_SECONDS", 90, minimum=15)
    context = None if force_refresh else get_panel_cache(cache_key)
    if context is None:
        context = collect_system_monitoring_snapshot(db)
        set_panel_cache(cache_key, context, ttl_seconds=monitoramento_ttl)
        if force_refresh:
            flash("Verificação técnica atualizada com sucesso.", "success")
    return render_template("monitoramento_sistema_v2.html", **context, format_bytes=format_bytes_human)


@admin_bp.route("/jobs/<int:job_id>/reativar", methods=["POST"])
@permission_required("usuarios:manage")
@programmatic_json
def jobs_requeue(job_id):
    db = get_db()
    row = db.execute(
        """
        SELECT id, status, job_type
        FROM background_jobs
        WHERE id = %s
        """,
        (job_id,),
    ).fetchone()
    if not row:
        return jsonify({"success": False, "message": "Job não encontrado."}), 404
    if row["status"] != JOB_STATUS_DEAD_LETTER:
        return jsonify(
            {
                "success": False,
                "message": "Apenas jobs em dead-letter podem ser reativados manualmente.",
                "status": row["status"],
            }
        ), 400

    try:
        requeued = requeue_dead_letter_job(db, job_id=job_id)
        if not requeued:
            db.conn.rollback()
            return jsonify({"success": False, "message": "Não foi possível reativar o job informado."}), 409
        db.commit()
    except Exception:
        db.conn.rollback()
        current_app.logger.exception("Falha ao reativar job em dead-letter.")
        return jsonify({"success": False, "message": "Erro ao reativar o job."}), 500

    return jsonify(
        {
            "success": True,
            "message": "Job reativado e reenfileirado com sucesso.",
            "job_id": job_id,
            "status": "queued",
        }
    )


@admin_bp.route("/jobs/<int:job_id>/status", methods=["GET"])
@permission_required("usuarios:manage")
@programmatic_json
def jobs_status(job_id):
    db = get_db()
    row = db.execute(
        """
        SELECT id, job_type, status, attempts, max_attempts, last_error, scheduled_for, started_at, finished_at, updated_at
        FROM background_jobs
        WHERE id = %s
        """,
        (job_id,),
    ).fetchone()
    if not row:
        return jsonify({"success": False, "message": "Job não encontrado.", "job_id": job_id}), 404
    payload = dict(row)
    payload["success"] = payload["status"] == "succeeded"
    payload["job_id"] = payload.pop("id")
    return jsonify(payload), 200


@admin_bp.route("/manual/usuario.pdf")
@permission_required("monitoramento:view")
def manual_usuario_pdf():
    emitted_at = datetime.now().strftime("%d/%m/%Y %H:%M")
    pdf_bytes = build_user_guide_pdf(emitted_at=emitted_at)
    filename = f"guia_usuario_treinamentos_brasilvida_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    response = Response(pdf_bytes, mimetype="application/pdf")
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Cache-Control"] = "no-store"
    return response
