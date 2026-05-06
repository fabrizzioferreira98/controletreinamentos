from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

try:
    import psycopg2
except ImportError:
    psycopg2 = None  # type: ignore[assignment]
from flask import current_app, g, has_app_context, has_request_context

from ..core.metrics import (
    record_background_job_execution,
    record_background_worker_cycle,
    record_critical_flow_failure,
    set_background_job_queue_snapshot,
)
from ..core.utils import env_int as _env_int
from ..db import get_db

JOB_TYPE_SEND_DAILY_NOTIFICATIONS = "send_daily_notifications"
JOB_TYPE_RUN_BACKUP = "run_backup"

JOB_STATUS_QUEUED = "queued"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_SUCCEEDED = "succeeded"
JOB_STATUS_DEAD_LETTER = "dead_letter"


@dataclass(frozen=True)
class JobEnqueueResult:
    job_id: int
    status: str
    created: bool
    job_type: str
    idempotency_key: str | None


@dataclass(frozen=True)
class JobProcessResult:
    job_id: int
    processed: bool
    success: bool
    status: str
    error: str | None = None
    details: dict[str, Any] | None = None





def _safe_json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, default=str)


def _current_trace_context(
    *,
    request_id: str | None = None,
    correlation_id: str | None = None,
) -> tuple[str | None, str | None]:
    current_request_id = (request_id or "").strip() or None
    current_correlation_id = (correlation_id or "").strip() or None
    if has_request_context():
        current_request_id = current_request_id or (getattr(g, "request_id", None) or None)
        current_correlation_id = current_correlation_id or (getattr(g, "correlation_id", None) or None)
    current_correlation_id = current_correlation_id or current_request_id
    return current_request_id, current_correlation_id


def _payload_with_trace(payload: dict[str, Any], *, correlation_id: str | None) -> dict[str, Any]:
    safe_payload = dict(payload or {})
    if not correlation_id:
        return safe_payload
    trace_payload = safe_payload.get("_trace")
    if not isinstance(trace_payload, dict):
        trace_payload = {}
    trace_payload.setdefault("correlation_id", correlation_id)
    safe_payload["_trace"] = trace_payload
    return safe_payload


def _job_correlation_id(job_row) -> str | None:
    payload = job_row["payload"] if isinstance(job_row.get("payload"), dict) else {}
    trace_payload = payload.get("_trace") if isinstance(payload.get("_trace"), dict) else {}
    return (trace_payload.get("correlation_id") or job_row.get("origin_request_id") or "").strip() or None


def _log_job_enqueue(result: JobEnqueueResult, *, request_id: str | None, correlation_id: str | None) -> None:
    if not has_app_context():
        return
    current_app.logger.info(
        "Background job enqueue recorded.",
        extra={
            "event": "background_job_enqueued",
            "job_id": int(result.job_id),
            "job_type": result.job_type,
            "job_status": result.status,
            "idempotency_key": result.idempotency_key,
            "job_created": bool(result.created),
            "request_id": request_id,
            "origin_request_id": request_id,
            "correlation_id": correlation_id or request_id,
        },
    )


def _count_in_flight_jobs_by_type(db, *, job_type: str) -> int:
    row = db.execute(
        """
        SELECT COUNT(*) AS total
        FROM background_jobs
        WHERE job_type = %s
          AND status IN (%s, %s)
        """,
        (job_type, JOB_STATUS_QUEUED, JOB_STATUS_RUNNING),
    ).fetchone()
    if row is None:
        return 0
    if hasattr(row, "keys"):
        return int(row.get("total", 0) or 0)
    return int(row[0] or 0)


def collect_in_flight_jobs_by_type(db, *, job_type: str) -> dict[str, Any]:
    safe_job_type = (job_type or "").strip()
    if not safe_job_type:
        return {"job_type": "", "queued": 0, "running": 0, "total": 0, "oldest_created_at": None}

    rows = db.execute(
        """
        SELECT status, COUNT(*) AS total, MIN(created_at) AS oldest_created_at
        FROM background_jobs
        WHERE job_type = %s
          AND status IN (%s, %s)
        GROUP BY status
        """,
        (safe_job_type, JOB_STATUS_QUEUED, JOB_STATUS_RUNNING),
    ).fetchall()

    snapshot: dict[str, Any] = {
        "job_type": safe_job_type,
        JOB_STATUS_QUEUED: 0,
        JOB_STATUS_RUNNING: 0,
        "total": 0,
        "oldest_created_at": None,
    }
    oldest_created_at = None
    for row in rows:
        status = row["status"] if hasattr(row, "keys") else row[0]
        total = int((row["total"] if hasattr(row, "keys") else row[1]) or 0)
        created_at = row["oldest_created_at"] if hasattr(row, "keys") else row[2]
        if status in {JOB_STATUS_QUEUED, JOB_STATUS_RUNNING}:
            snapshot[status] = total
            snapshot["total"] += total
        if created_at is not None and (oldest_created_at is None or created_at < oldest_created_at):
            oldest_created_at = created_at

    if oldest_created_at is not None:
        snapshot["oldest_created_at"] = (
            oldest_created_at.isoformat() if hasattr(oldest_created_at, "isoformat") else str(oldest_created_at)
        )
    return snapshot


def _job_relevant_for_dedup(status: str | None) -> bool:
    return status in {JOB_STATUS_QUEUED, JOB_STATUS_RUNNING, JOB_STATUS_SUCCEEDED}


def build_bucketed_idempotency_key(
    prefix: str,
    *,
    granularity: str = "minute",
    now: datetime | None = None,
    suffix: str | None = None,
) -> str:
    reference = now or datetime.utcnow()
    key_granularity = (granularity or "").strip().lower()
    if key_granularity == "day":
        stamp = reference.strftime("%Y%m%d")
    elif key_granularity == "hour":
        stamp = reference.strftime("%Y%m%d%H")
    else:
        stamp = reference.strftime("%Y%m%d%H%M")
    parts = [prefix.strip() or "job", stamp]
    if suffix:
        parts.append((suffix or "").strip())
    return ":".join(parts)


def enqueue_background_job(
    db,
    *,
    job_type: str,
    payload: dict[str, Any] | None = None,
    priority: int = 100,
    max_attempts: int = 3,
    idempotency_key: str | None = None,
    requested_by: int | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
) -> JobEnqueueResult:
    safe_job_type = (job_type or "").strip()
    if not safe_job_type:
        raise ValueError("job_type é obrigatório para enfileirar tarefa.")

    safe_idempotency_key = (idempotency_key or "").strip() or None
    effective_request_id, effective_correlation_id = _current_trace_context(
        request_id=request_id,
        correlation_id=correlation_id,
    )
    safe_payload = _payload_with_trace(payload or {}, correlation_id=effective_correlation_id)
    safe_priority = max(1, int(priority))
    safe_max_attempts = max(1, int(max_attempts))
    max_in_flight_per_type = _env_int("JOB_MAX_IN_FLIGHT_PER_TYPE", 0, minimum=0)

    if max_in_flight_per_type > 0:
        in_flight = _count_in_flight_jobs_by_type(db, job_type=safe_job_type)
        if in_flight >= max_in_flight_per_type:
            raise RuntimeError(
                "Fila de jobs saturada para este tipo. "
                f"job_type={safe_job_type} in_flight={in_flight} limit={max_in_flight_per_type}"
            )

    if safe_idempotency_key:
        existing = db.execute(
            """
            SELECT id, status, job_type, idempotency_key
            FROM background_jobs
            WHERE idempotency_key = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (safe_idempotency_key,),
        ).fetchone()
        if existing and _job_relevant_for_dedup(existing["status"]):
            result = JobEnqueueResult(
                job_id=int(existing["id"]),
                status=existing["status"],
                created=False,
                job_type=existing["job_type"],
                idempotency_key=existing["idempotency_key"],
            )
            _log_job_enqueue(result, request_id=effective_request_id, correlation_id=effective_correlation_id)
            return result

    db.execute("SAVEPOINT enqueue_background_job_sp")
    try:
        row = db.execute(
            """
            INSERT INTO background_jobs
            (job_type, payload, status, priority, max_attempts, idempotency_key, requested_by, origin_request_id)
            VALUES (%s, %s::jsonb, %s, %s, %s, %s, %s, %s)
            RETURNING id, status, job_type, idempotency_key
            """,
            (
                safe_job_type,
                _safe_json(safe_payload),
                JOB_STATUS_QUEUED,
                safe_priority,
                safe_max_attempts,
                safe_idempotency_key,
                requested_by,
                effective_request_id,
            ),
        ).fetchone()
        db.execute("RELEASE SAVEPOINT enqueue_background_job_sp")
        result = JobEnqueueResult(
            job_id=int(row["id"]),
            status=row["status"],
            created=True,
            job_type=row["job_type"],
            idempotency_key=row["idempotency_key"],
        )
        _log_job_enqueue(result, request_id=effective_request_id, correlation_id=effective_correlation_id)
        return result
    except psycopg2.IntegrityError:
        db.execute("ROLLBACK TO SAVEPOINT enqueue_background_job_sp")
        if not safe_idempotency_key:
            raise
        existing = db.execute(
            """
            SELECT id, status, job_type, idempotency_key
            FROM background_jobs
            WHERE idempotency_key = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (safe_idempotency_key,),
        ).fetchone()
        if not existing:
            raise
        result = JobEnqueueResult(
            job_id=int(existing["id"]),
            status=existing["status"],
            created=False,
            job_type=existing["job_type"],
            idempotency_key=existing["idempotency_key"],
        )
        _log_job_enqueue(result, request_id=effective_request_id, correlation_id=effective_correlation_id)
        return result


def enqueue_notifications_job(
    db,
    *,
    source: str,
    requested_by: int | None = None,
    idempotency_key: str | None = None,
    request_id: str | None = None,
) -> JobEnqueueResult:
    return enqueue_background_job(
        db,
        job_type=JOB_TYPE_SEND_DAILY_NOTIFICATIONS,
        payload={"source": (source or "").strip() or "manual"},
        priority=40,
        max_attempts=3,
        idempotency_key=idempotency_key,
        requested_by=requested_by,
        request_id=request_id,
    )


def enqueue_backup_job(
    db,
    *,
    source: str,
    backup_type: str = "agendado",
    requested_by: int | None = None,
    idempotency_key: str | None = None,
    request_id: str | None = None,
) -> JobEnqueueResult:
    return enqueue_background_job(
        db,
        job_type=JOB_TYPE_RUN_BACKUP,
        payload={
            "source": (source or "").strip() or "manual",
            "backup_type": (backup_type or "").strip() or "agendado",
        },
        priority=30,
        max_attempts=2,
        idempotency_key=idempotency_key,
        requested_by=requested_by,
        request_id=request_id,
    )


def _requeue_stale_running_jobs(db, *, stale_lock_seconds: int) -> list[dict[str, Any]]:
    if stale_lock_seconds <= 0:
        return []
    rows = db.execute(
        """
        WITH stale AS (
            SELECT id
            FROM background_jobs
            WHERE status = %s
              AND locked_at IS NOT NULL
              AND locked_at < (CURRENT_TIMESTAMP - (%s * INTERVAL '1 second'))
            FOR UPDATE SKIP LOCKED
        )
        UPDATE background_jobs
        SET
            status = CASE
                WHEN COALESCE(attempts, 0) + 1 >= GREATEST(COALESCE(max_attempts, 1), 1) THEN %s
                ELSE %s
            END,
            attempts = COALESCE(attempts, 0) + 1,
            locked_by = NULL,
            locked_at = NULL,
            idempotency_key = CASE
                WHEN COALESCE(attempts, 0) + 1 >= GREATEST(COALESCE(max_attempts, 1), 1) THEN NULL
                ELSE idempotency_key
            END,
            finished_at = CASE
                WHEN COALESCE(attempts, 0) + 1 >= GREATEST(COALESCE(max_attempts, 1), 1) THEN CURRENT_TIMESTAMP
                ELSE finished_at
            END,
            updated_at = CURRENT_TIMESTAMP,
            last_error = COALESCE(last_error, '') || CASE
                WHEN COALESCE(last_error, '') = '' THEN 'Reenfileirado por deadline/lock expirado.'
                ELSE ' | Reenfileirado por deadline/lock expirado.'
            END
        FROM stale
        WHERE background_jobs.id = stale.id
        RETURNING background_jobs.id, background_jobs.job_type, background_jobs.status, background_jobs.attempts
        """,
        (JOB_STATUS_RUNNING, stale_lock_seconds, JOB_STATUS_DEAD_LETTER, JOB_STATUS_QUEUED),
    ).fetchall()
    return [dict(row) for row in rows]


def _claim_next_job(db, *, worker_id: str):
    return db.execute(
        """
        WITH candidate AS (
            SELECT id
            FROM background_jobs
            WHERE status = %s
              AND scheduled_for <= CURRENT_TIMESTAMP
            ORDER BY priority ASC, scheduled_for ASC, id ASC
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        UPDATE background_jobs j
        SET
            status = %s,
            locked_by = %s,
            locked_at = CURRENT_TIMESTAMP,
            started_at = COALESCE(j.started_at, CURRENT_TIMESTAMP),
            updated_at = CURRENT_TIMESTAMP
        FROM candidate
        WHERE j.id = candidate.id
        RETURNING j.*
        """,
        (JOB_STATUS_QUEUED, JOB_STATUS_RUNNING, worker_id),
    ).fetchone()


def _claim_job_by_id(db, *, job_id: int, worker_id: str):
    return db.execute(
        """
        UPDATE background_jobs
        SET
            status = %s,
            locked_by = %s,
            locked_at = CURRENT_TIMESTAMP,
            started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
          AND status = %s
          AND scheduled_for <= CURRENT_TIMESTAMP
        RETURNING *
        """,
        (JOB_STATUS_RUNNING, worker_id, job_id, JOB_STATUS_QUEUED),
    ).fetchone()


def _create_execution_log(db, *, job_id: int, attempt: int, worker_id: str):
    row = db.execute(
        """
        INSERT INTO background_job_executions
        (job_id, attempt, status, worker_id)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (job_id, attempt, JOB_STATUS_RUNNING, worker_id),
    ).fetchone()
    return int(row["id"])


def _finalize_execution_log(
    db,
    *,
    execution_id: int,
    status: str,
    duration_ms: int,
    error: str | None = None,
    result_payload: dict[str, Any] | None = None,
):
    db.execute(
        """
        UPDATE background_job_executions
        SET
            status = %s,
            finished_at = CURRENT_TIMESTAMP,
            duration_ms = %s,
            error = %s,
            result_payload = %s::jsonb
        WHERE id = %s
        """,
        (
            status,
            max(0, int(duration_ms)),
            (error or "").strip()[:1000] or None,
            _safe_json(result_payload or {}),
            execution_id,
        ),
    )


def _run_handler(app, job_row) -> tuple[bool, dict[str, Any]]:
    from .backup import run_backup_job
    from .mailer import send_daily_notifications

    payload = job_row["payload"] if isinstance(job_row["payload"], dict) else {}
    job_type = job_row["job_type"]

    if job_type == JOB_TYPE_SEND_DAILY_NOTIFICATIONS:
        result = send_daily_notifications(app)
        success = bool(result.sent or result.reason in {"no_due_items", "no_recipients"})
        details = {
            "sent": bool(result.sent),
            "reason": result.reason,
            "error": result.error,
        }
        return success, details

    if job_type == JOB_TYPE_RUN_BACKUP:
        backup_type = (payload.get("backup_type") or "agendado").strip()
        result = run_backup_job(backup_type=backup_type)
        details = {
            "success": bool(result.success),
            "status": result.status,
            "message": result.message,
            "file_path": result.file_path,
            "duration_ms": result.duration_ms,
        }
        return bool(result.success), details

    raise RuntimeError(f"Tipo de job não suportado: {job_type}")


def _retry_delay_seconds(attempt: int) -> int:
    # Backoff exponencial curto para evitar loop agressivo em falha persistente.
    return min(900, max(10, (2 ** max(0, attempt - 1)) * 15))


def _job_timeout_seconds() -> int:
    return _env_int("JOB_WORKER_JOB_TIMEOUT_SECONDS", 1800, minimum=0)


def _effective_stale_lock_seconds() -> int:
    stale_lock_seconds = _env_int("JOB_STALE_LOCK_SECONDS", 14400, minimum=60)
    timeout_seconds = _job_timeout_seconds()
    if timeout_seconds > 0:
        return max(60, min(stale_lock_seconds, timeout_seconds))
    return stale_lock_seconds


def _mark_job_as_success(db, *, job_id: int, attempt: int):
    db.execute(
        """
        UPDATE background_jobs
        SET
            status = %s,
            attempts = %s,
            locked_by = NULL,
            locked_at = NULL,
            last_error = NULL,
            finished_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (JOB_STATUS_SUCCEEDED, attempt, job_id),
    )


def _mark_job_as_failure(db, *, job_row, attempt: int, error: str):
    max_attempts = max(1, int(job_row["max_attempts"] or 1))
    normalized_error = (error or "Falha sem detalhe.").strip()[:1000]
    if attempt >= max_attempts:
        db.execute(
            """
            UPDATE background_jobs
            SET
                status = %s,
                attempts = %s,
                locked_by = NULL,
                locked_at = NULL,
                idempotency_key = NULL,
                last_error = %s,
                finished_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (JOB_STATUS_DEAD_LETTER, attempt, normalized_error, int(job_row["id"])),
        )
        return JOB_STATUS_DEAD_LETTER

    delay_seconds = _retry_delay_seconds(attempt)
    db.execute(
        """
        UPDATE background_jobs
        SET
            status = %s,
            attempts = %s,
            locked_by = NULL,
            locked_at = NULL,
            scheduled_for = CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'),
            last_error = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (JOB_STATUS_QUEUED, attempt, delay_seconds, normalized_error, int(job_row["id"])),
    )
    return JOB_STATUS_QUEUED


def _set_sentry_trace_tags(request_id: str | None, correlation_id: str | None) -> None:
    if not request_id and not correlation_id:
        return
    try:
        import sentry_sdk  # type: ignore
    except Exception:
        return
    try:
        set_tag = getattr(sentry_sdk, "set_tag", None)
        if callable(set_tag):
            if request_id:
                set_tag("request_id", request_id)
            if correlation_id:
                set_tag("correlation_id", correlation_id)
    except Exception:
        # Observabilidade não deve derrubar processamento assíncrono.
        return


def _set_sentry_request_tag(request_id: str | None) -> None:
    _set_sentry_trace_tags(request_id, None)


def _job_log_extra(
    job_row,
    *,
    worker_id: str,
    execution_id: int | None = None,
    attempt: int | None = None,
    duration_ms: int | None = None,
    status: str | None = None,
    error: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = job_row["payload"] if isinstance(job_row.get("payload"), dict) else {}
    origin_request_id = job_row.get("origin_request_id")
    correlation_id = _job_correlation_id(job_row)
    extra: dict[str, Any] = {
        "job_id": int(job_row["id"]),
        "job_type": job_row["job_type"],
        "worker_id": worker_id,
        "request_id": origin_request_id,
        "origin_request_id": origin_request_id,
        "correlation_id": correlation_id,
        "requested_by": job_row.get("requested_by"),
        "idempotency_key": job_row.get("idempotency_key"),
        "job_payload_source": payload.get("source"),
        "job_payload_backup_type": payload.get("backup_type"),
    }
    if execution_id is not None:
        extra["execution_id"] = int(execution_id)
    if attempt is not None:
        extra["attempt"] = int(attempt)
    if duration_ms is not None:
        extra["duration_ms"] = int(duration_ms)
    if status is not None:
        extra["job_status"] = status
    if error:
        extra["error"] = str(error)[:500]
    if details:
        for key in ("reason", "sent", "status", "file_path"):
            if key in details:
                extra[f"result_{key}"] = details.get(key)
    return extra


def _process_claimed_job(app, db, *, claimed_job, worker_id: str) -> JobProcessResult:
    origin_request_id = claimed_job.get("origin_request_id")
    correlation_id = _job_correlation_id(claimed_job)
    _set_sentry_trace_tags(origin_request_id, correlation_id)

    app.logger.info(
        "Initiating processing of background job.",
        extra={
            "event": "background_job_started",
            **_job_log_extra(claimed_job, worker_id=worker_id),
        },
    )

    attempt = int(claimed_job["attempts"] or 0) + 1
    execution_id = _create_execution_log(
        db,
        job_id=int(claimed_job["id"]),
        attempt=attempt,
        worker_id=worker_id,
    )
    db.commit()

    started = time.monotonic()
    try:
        success, details = _run_handler(app, claimed_job)
        duration_ms = int((time.monotonic() - started) * 1000)
        timeout_seconds = _job_timeout_seconds()
        if timeout_seconds > 0 and duration_ms > timeout_seconds * 1000:
            details = dict(details or {})
            details.update(
                {
                    "error": "job_timeout",
                    "timeout_seconds": timeout_seconds,
                    "duration_ms": duration_ms,
                }
            )
            success = False
            app.logger.warning(
                "Background job exceeded configured deadline.",
                extra={
                    "event": "background_job_deadline_exceeded",
                    **_job_log_extra(
                        claimed_job,
                        worker_id=worker_id,
                        execution_id=execution_id,
                        attempt=attempt,
                        duration_ms=duration_ms,
                        status="deadline_exceeded",
                        error="job_timeout",
                        details=details,
                    ),
                },
            )
        if success:
            _mark_job_as_success(db, job_id=int(claimed_job["id"]), attempt=attempt)
            _finalize_execution_log(
                db,
                execution_id=execution_id,
                status=JOB_STATUS_SUCCEEDED,
                duration_ms=duration_ms,
                result_payload=details,
            )
            db.commit()
            record_background_job_execution(claimed_job["job_type"], JOB_STATUS_SUCCEEDED, duration_ms)
            app.logger.info(
                "Background job completed successfully.",
                extra={
                    "event": "background_job_completed",
                    **_job_log_extra(
                        claimed_job,
                        worker_id=worker_id,
                        execution_id=execution_id,
                        attempt=attempt,
                        duration_ms=duration_ms,
                        status=JOB_STATUS_SUCCEEDED,
                        details=details,
                    ),
                },
            )
            return JobProcessResult(
                job_id=int(claimed_job["id"]),
                processed=True,
                success=True,
                status=JOB_STATUS_SUCCEEDED,
                details=details,
            )

        failure_reason = (details or {}).get("error") or (details or {}).get("reason") or "job_failed"
        job_status = _mark_job_as_failure(
            db,
            job_row=claimed_job,
            attempt=attempt,
            error=failure_reason,
        )
        _finalize_execution_log(
            db,
            execution_id=execution_id,
            status="failed",
            duration_ms=duration_ms,
            error=failure_reason,
            result_payload=details,
        )
        db.commit()
        record_background_job_execution(claimed_job["job_type"], job_status, duration_ms)
        app.logger.warning(
            "Background job finished without success.",
            extra={
                "event": "background_job_failed",
                **_job_log_extra(
                    claimed_job,
                    worker_id=worker_id,
                    execution_id=execution_id,
                    attempt=attempt,
                    duration_ms=duration_ms,
                    status=job_status,
                    error=str(failure_reason),
                    details=details,
                ),
            },
        )
        return JobProcessResult(
            job_id=int(claimed_job["id"]),
            processed=True,
            success=False,
            status=job_status,
            error=str(failure_reason),
            details=details,
        )
    except Exception as exc:
        db.conn.rollback()
        duration_ms = int((time.monotonic() - started) * 1000)
        error_text = str(exc)[:1000] or "unexpected_error"
        try:
            job_status = _mark_job_as_failure(
                db,
                job_row=claimed_job,
                attempt=attempt,
                error=error_text,
            )
            _finalize_execution_log(
                db,
                execution_id=execution_id,
                status="failed",
                duration_ms=duration_ms,
                error=error_text,
                result_payload={"error": error_text},
            )
            db.commit()
        except Exception:
            db.conn.rollback()
            job_status = JOB_STATUS_RUNNING
        record_background_job_execution(claimed_job["job_type"], job_status, duration_ms)
        current_app.logger.exception(
            "Falha inesperada no processamento de background job.",
            extra={
                "event": "background_job_unexpected_failure",
                **_job_log_extra(
                    claimed_job,
                    worker_id=worker_id,
                    execution_id=execution_id,
                    attempt=attempt,
                    duration_ms=duration_ms,
                    status=job_status,
                    error=error_text,
                ),
            },
        )
        return JobProcessResult(
            job_id=int(claimed_job["id"]),
            processed=True,
            success=False,
            status=job_status,
            error=error_text,
            details={"error": error_text},
        )


def process_background_job_by_id(
    app,
    job_id: int,
    *,
    worker_id: str | None = None,
) -> JobProcessResult:
    with app.app_context():
        db = get_db()
        stale_lock_seconds = _effective_stale_lock_seconds()
        stale_rows = _requeue_stale_running_jobs(db, stale_lock_seconds=stale_lock_seconds)
        if stale_rows:
            record_critical_flow_failure("background_jobs", "stale_running_requeued")
            app.logger.warning(
                "Requeued stale background jobs before direct claim.",
                extra={"stale_lock_seconds": stale_lock_seconds, "jobs": stale_rows},
            )
        claimed_job = _claim_job_by_id(
            db,
            job_id=int(job_id),
            worker_id=(worker_id or f"worker:{os.getpid()}"),
        )
        db.commit()
        if not claimed_job:
            row = db.execute(
                "SELECT id, status FROM background_jobs WHERE id = %s",
                (int(job_id),),
            ).fetchone()
            status = row["status"] if row else "missing"
            set_background_job_queue_snapshot(collect_job_queue_snapshot(db, stale_lock_seconds=stale_lock_seconds))
            return JobProcessResult(
                job_id=int(job_id),
                processed=False,
                success=status == JOB_STATUS_SUCCEEDED,
                status=status,
            )
        result = _process_claimed_job(
            app,
            db,
            claimed_job=claimed_job,
            worker_id=(worker_id or f"worker:{os.getpid()}"),
        )
        set_background_job_queue_snapshot(collect_job_queue_snapshot(db, stale_lock_seconds=stale_lock_seconds))
        return result


def process_background_jobs(
    app,
    *,
    max_jobs: int = 5,
    worker_id: str | None = None,
) -> dict[str, int]:
    summary = {"processed": 0, "succeeded": 0, "failed": 0, "dead_letter": 0}
    with app.app_context():
        db = get_db()
        stale_lock_seconds = _effective_stale_lock_seconds()
        stale_rows = _requeue_stale_running_jobs(db, stale_lock_seconds=stale_lock_seconds)
        if stale_rows:
            record_critical_flow_failure("background_jobs", "stale_running_requeued")
            app.logger.warning(
                "Requeued stale background jobs before processing queue.",
                extra={"stale_lock_seconds": stale_lock_seconds, "jobs": stale_rows},
            )
        db.commit()

        effective_worker = worker_id or f"worker:{os.getpid()}"
        app.logger.info(
            "Background job worker cycle started.",
            extra={
                "event": "worker_cycle_started",
                "worker_id": effective_worker,
                "max_jobs": max(1, int(max_jobs)),
                "stale_lock_seconds": stale_lock_seconds,
            },
        )
        for _ in range(max(1, int(max_jobs))):
            claimed_job = _claim_next_job(db, worker_id=effective_worker)
            db.commit()
            if not claimed_job:
                break
            result = _process_claimed_job(app, db, claimed_job=claimed_job, worker_id=effective_worker)
            summary["processed"] += 1
            if result.success:
                summary["succeeded"] += 1
            else:
                summary["failed"] += 1
                if result.status == JOB_STATUS_DEAD_LETTER:
                    summary["dead_letter"] += 1
        _cleanup_old_job_history(db)
        db.commit()
        set_background_job_queue_snapshot(collect_job_queue_snapshot(db, stale_lock_seconds=stale_lock_seconds))
        record_background_worker_cycle("success")
        app.logger.info(
            "Background job worker cycle completed.",
            extra={
                "event": "worker_cycle_completed",
                "worker_id": effective_worker,
                **summary,
            },
        )
    return summary


def collect_job_queue_snapshot(
    db,
    *,
    stale_lock_seconds: int | None = None,
) -> dict[str, int | float | None]:
    stale_seconds = max(60, int(stale_lock_seconds or _env_int("JOB_STALE_LOCK_SECONDS", 14400, minimum=60)))
    queued, _ = _safe_int_scalar(db, "SELECT COUNT(*) AS total FROM background_jobs WHERE status = %s", (JOB_STATUS_QUEUED,))
    running, _ = _safe_int_scalar(db, "SELECT COUNT(*) AS total FROM background_jobs WHERE status = %s", (JOB_STATUS_RUNNING,))
    succeeded, _ = _safe_int_scalar(db, "SELECT COUNT(*) AS total FROM background_jobs WHERE status = %s", (JOB_STATUS_SUCCEEDED,))
    dead_letter, _ = _safe_int_scalar(db, "SELECT COUNT(*) AS total FROM background_jobs WHERE status = %s", (JOB_STATUS_DEAD_LETTER,))
    stale_running, _ = _safe_int_scalar(
        db,
        """
        SELECT COUNT(*) AS total
        FROM background_jobs
        WHERE status = %s
          AND locked_at IS NOT NULL
          AND locked_at < (CURRENT_TIMESTAMP - (%s * INTERVAL '1 second'))
        """,
        (JOB_STATUS_RUNNING, stale_seconds),
    )
    oldest_queued_minutes, _ = _safe_float_scalar(
        db,
        """
        SELECT EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - MIN(scheduled_for))) / 60.0 AS minutes
        FROM background_jobs
        WHERE status = %s
        """,
        (JOB_STATUS_QUEUED,),
    )
    return {
        "queued": int(queued or 0),
        "running": int(running or 0),
        "succeeded": int(succeeded or 0),
        "dead_letter": int(dead_letter or 0),
        "stale_running": int(stale_running or 0),
        "oldest_queued_minutes": float(oldest_queued_minutes) if oldest_queued_minutes is not None else None,
    }


def requeue_dead_letter_job(db, *, job_id: int) -> bool:
    row = db.execute(
        """
        UPDATE background_jobs
        SET
            status = %s,
            scheduled_for = CURRENT_TIMESTAMP,
            locked_by = NULL,
            locked_at = NULL,
            attempts = 0,
            finished_at = NULL,
            updated_at = CURRENT_TIMESTAMP,
            last_error = COALESCE(last_error, '') || CASE
                WHEN COALESCE(last_error, '') = '' THEN 'Reprocessamento manual solicitado.'
                ELSE ' | Reprocessamento manual solicitado.'
            END
        WHERE id = %s
          AND status = %s
        RETURNING id
        """,
        (JOB_STATUS_QUEUED, int(job_id), JOB_STATUS_DEAD_LETTER),
    ).fetchone()
    return bool(row)


def _safe_int_scalar(db, query: str, params: tuple = ()) -> tuple[int | None, str | None]:
    try:
        row = db.execute(query, params).fetchone()
        if row is None:
            return 0, None
        value = row[0] if not hasattr(row, "keys") else row[next(iter(row.keys()))]
        return int(value or 0), None
    except Exception as exc:
        return None, str(exc)


def _safe_float_scalar(db, query: str, params: tuple = ()) -> tuple[float | None, str | None]:
    try:
        row = db.execute(query, params).fetchone()
        if row is None:
            return None, None
        value = row[0] if not hasattr(row, "keys") else row[next(iter(row.keys()))]
        return (None if value is None else float(value)), None
    except Exception as exc:
        return None, str(exc)


def _cleanup_old_job_history(db) -> None:
    enabled = (os.getenv("JOB_AUTO_CLEANUP_ENABLED", "1") or "").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return

    succeeded_retention_days = max(1, _env_int("JOB_SUCCESS_RETENTION_DAYS", 30, minimum=1))
    failed_retention_days = max(1, _env_int("JOB_FAILED_RETENTION_DAYS", 90, minimum=1))
    execution_retention_days = max(1, _env_int("JOB_EXECUTION_RETENTION_DAYS", 30, minimum=1))

    db.execute(
        """
        DELETE FROM background_job_executions
        WHERE started_at < (CURRENT_TIMESTAMP - (%s * INTERVAL '1 day'))
        """,
        (execution_retention_days,),
    )
    db.execute(
        """
        DELETE FROM background_jobs
        WHERE status = %s
          AND finished_at IS NOT NULL
          AND finished_at < (CURRENT_TIMESTAMP - (%s * INTERVAL '1 day'))
        """,
        (JOB_STATUS_SUCCEEDED, succeeded_retention_days),
    )
    db.execute(
        """
        DELETE FROM background_jobs
        WHERE status = %s
          AND finished_at IS NOT NULL
          AND finished_at < (CURRENT_TIMESTAMP - (%s * INTERVAL '1 day'))
        """,
        (JOB_STATUS_DEAD_LETTER, failed_retention_days),
    )
