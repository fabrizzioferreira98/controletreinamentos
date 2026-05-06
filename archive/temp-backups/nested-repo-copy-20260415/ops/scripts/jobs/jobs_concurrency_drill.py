from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.db import get_db
from backend.src.controle_treinamentos.jobs import (
    JOB_STATUS_DEAD_LETTER,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    enqueue_backup_job,
    enqueue_background_job,
    process_background_jobs,
)


def _run_workers(app, *, workers: int, max_jobs_per_worker: int) -> list[dict]:
    def _runner(idx: int) -> dict:
        return process_background_jobs(
            app,
            max_jobs=max_jobs_per_worker,
            worker_id=f"drill-worker-{idx}",
        )

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(_runner, i + 1) for i in range(max(1, workers))]
        return [f.result() for f in futures]


def _group_status_counts(db, *, key_prefix: str) -> dict[str, int]:
    rows = db.execute(
        """
        SELECT status, COUNT(*) AS total
        FROM background_jobs
        WHERE idempotency_key LIKE %s
        GROUP BY status
        """,
        (f"{key_prefix}%",),
    ).fetchall()
    counts: dict[str, int] = {}
    for row in rows:
        counts[str(row["status"])] = int(row["total"])
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Drill de concorrencia/retry/dead-letter da fila de jobs.")
    parser.add_argument("--success-jobs", type=int, default=6, help="Quantidade de jobs esperados com sucesso.")
    parser.add_argument("--retry-fail-jobs", type=int, default=3, help="Quantidade de jobs de falha com retry.")
    parser.add_argument(
        "--success-job-type",
        choices=("backup", "notifications"),
        default="backup",
        help="Tipo de job usado para trilha de sucesso do drill (default: backup).",
    )
    parser.add_argument("--workers", type=int, default=4, help="Quantidade de workers concorrentes para o drill.")
    parser.add_argument("--max-jobs-per-worker", type=int, default=25)
    parser.add_argument("--cleanup", action="store_true", help="Remove os jobs do drill ao final.")
    parser.add_argument("--output", default="", help="Arquivo opcional para salvar o JSON de evidencia.")
    args = parser.parse_args()

    db_url = (os.getenv("DATABASE_URL", "") or "").strip()
    if not db_url:
        print(json.dumps({"success": False, "message": "DATABASE_URL não configurada."}, ensure_ascii=False, indent=2))
        return 1

    app = create_app()
    run_id = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    key_prefix = f"drill:jobs:{run_id}:"
    success_jobs = max(1, int(args.success_jobs))
    retry_fail_jobs = max(1, int(args.retry_fail_jobs))

    with app.app_context():
        db = get_db()
        success_ids: list[int] = []
        retry_ids: list[int] = []

        for index in range(success_jobs):
            if args.success_job_type == "notifications":
                result = enqueue_background_job(
                    db,
                    job_type="send_daily_notifications",
                    payload={"source": "drill"},
                    max_attempts=3,
                    idempotency_key=f"{key_prefix}ok:{index}",
                )
            else:
                result = enqueue_backup_job(
                    db,
                    source="drill",
                    backup_type="drill",
                    idempotency_key=f"{key_prefix}ok:{index}",
                )
            success_ids.append(result.job_id)

        for index in range(retry_fail_jobs):
            result = enqueue_background_job(
                db,
                job_type="drill_unsupported_job_type",
                payload={"drill": True, "kind": "retry_dead_letter", "index": index},
                max_attempts=2,
                idempotency_key=f"{key_prefix}fail:{index}",
            )
            retry_ids.append(result.job_id)

        db.commit()

        phase1_workers = _run_workers(
            app,
            workers=max(1, int(args.workers)),
            max_jobs_per_worker=max(1, int(args.max_jobs_per_worker)),
        )
        counts_after_phase1 = _group_status_counts(db, key_prefix=key_prefix)

        # Force immediate retry for queued failures to avoid waiting for backoff window in the drill.
        db.execute(
            """
            UPDATE background_jobs
            SET scheduled_for = CURRENT_TIMESTAMP
            WHERE id = ANY(%s)
              AND status = %s
            """,
            (retry_ids, JOB_STATUS_QUEUED),
        )
        db.commit()

        phase2_workers = _run_workers(
            app,
            workers=max(1, int(args.workers)),
            max_jobs_per_worker=max(1, int(args.max_jobs_per_worker)),
        )
        counts_final = _group_status_counts(db, key_prefix=key_prefix)

        if args.cleanup:
            db.execute(
                "DELETE FROM background_jobs WHERE idempotency_key LIKE %s",
                (f"{key_prefix}%",),
            )
            db.commit()

    queued_final = counts_final.get(JOB_STATUS_QUEUED, 0)
    running_final = counts_final.get(JOB_STATUS_RUNNING, 0)
    dead_final = counts_final.get(JOB_STATUS_DEAD_LETTER, 0)
    succeeded_final = counts_final.get("succeeded", 0)

    success = (
        queued_final == 0
        and running_final == 0
        and dead_final >= retry_fail_jobs
        and succeeded_final >= success_jobs
    )

    report = {
        "success": success,
        "run_id": run_id,
        "key_prefix": key_prefix,
        "success_job_type": args.success_job_type,
        "expected": {
            "succeeded_min": success_jobs,
            "dead_letter_min": retry_fail_jobs,
            "queued_final": 0,
            "running_final": 0,
        },
        "phase1_worker_summaries": phase1_workers,
        "phase2_worker_summaries": phase2_workers,
        "counts_after_phase1": counts_after_phase1,
        "counts_final": counts_final,
        "cleanup": bool(args.cleanup),
    }

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)

    if args.output:
        output_path = Path(args.output).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")

    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
