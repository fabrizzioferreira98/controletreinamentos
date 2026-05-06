from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.db import get_db
from backend.src.controle_treinamentos.infra import jobs as jobs_module
from backend.src.controle_treinamentos.jobs import (
    JOB_STATUS_DEAD_LETTER,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    JOB_STATUS_SUCCEEDED,
    enqueue_background_job,
    process_background_jobs,
)


DRILL_SUCCESS_JOB_TYPE = "drill_concurrency_probe"
DEFAULT_PROBE_SLEEP_SECONDS = 1.2


@dataclass
class ProbeObservation:
    job_id: int
    worker_id: str
    event: str
    active_count: int
    monotonic_ts: float


@dataclass
class ProbeState:
    barrier_parties: int
    barrier: threading.Barrier | None = field(init=False)
    lock: threading.Lock = field(default_factory=threading.Lock)
    active_count: int = 0
    max_active_count: int = 0
    barrier_slots_consumed: int = 0
    barrier_release_count: int = 0
    observations: list[ProbeObservation] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.barrier = threading.Barrier(self.barrier_parties) if self.barrier_parties > 1 else None

    def should_use_barrier(self) -> bool:
        if self.barrier is None:
            return False
        with self.lock:
            if self.barrier_slots_consumed >= self.barrier_parties:
                return False
            self.barrier_slots_consumed += 1
            return True

    @contextmanager
    def track(self, *, job_id: int, worker_id: str):
        started = time.monotonic()
        with self.lock:
            self.active_count += 1
            self.max_active_count = max(self.max_active_count, self.active_count)
            self.observations.append(
                ProbeObservation(
                    job_id=job_id,
                    worker_id=worker_id,
                    event="start",
                    active_count=self.active_count,
                    monotonic_ts=started,
                )
            )
        try:
            yield
        finally:
            finished = time.monotonic()
            with self.lock:
                self.observations.append(
                    ProbeObservation(
                        job_id=job_id,
                        worker_id=worker_id,
                        event="finish",
                        active_count=max(0, self.active_count - 1),
                        monotonic_ts=finished,
                    )
                )
                self.active_count = max(0, self.active_count - 1)


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


def _group_status_counts(db, *, job_ids: list[int]) -> dict[str, int]:
    if not job_ids:
        return {}
    rows = db.execute(
        """
        SELECT status, COUNT(*) AS total
        FROM background_jobs
        WHERE id = ANY(%s)
        GROUP BY status
        """,
        (job_ids,),
    ).fetchall()
    counts: dict[str, int] = {}
    for row in rows:
        counts[str(row["status"])] = int(row["total"])
    return counts


def _fetch_execution_rows(db, *, job_ids: list[int]) -> list[dict[str, Any]]:
    if not job_ids:
        return []
    rows = db.execute(
        """
        SELECT
            j.id AS job_id,
            j.job_type,
            j.status AS job_status,
            e.attempt,
            e.status AS execution_status,
            e.worker_id,
            e.started_at,
            e.finished_at,
            e.duration_ms,
            e.result_payload
        FROM background_jobs j
        LEFT JOIN background_job_executions e ON e.job_id = j.id
        WHERE j.id = ANY(%s)
        ORDER BY e.started_at NULLS LAST, e.id NULLS LAST, j.id
        """,
        (job_ids,),
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "job_id": int(row["job_id"]),
                "job_type": str(row["job_type"]),
                "job_status": str(row["job_status"]),
                "attempt": int(row["attempt"]) if row["attempt"] is not None else None,
                "execution_status": str(row["execution_status"]) if row["execution_status"] is not None else None,
                "worker_id": str(row["worker_id"]) if row["worker_id"] is not None else "",
                "started_at": row["started_at"].isoformat() if row["started_at"] is not None else None,
                "finished_at": row["finished_at"].isoformat() if row["finished_at"] is not None else None,
                "duration_ms": int(row["duration_ms"]) if row["duration_ms"] is not None else None,
                "result_payload": row["result_payload"] if isinstance(row["result_payload"], dict) else {},
            }
        )
    return result


def _compute_peak_concurrency(execution_rows: list[dict[str, Any]]) -> dict[str, Any]:
    timeline: list[tuple[datetime, int, int]] = []
    windows: list[dict[str, Any]] = []

    for row in execution_rows:
        if row["job_type"] != DRILL_SUCCESS_JOB_TYPE:
            continue
        if row["execution_status"] != JOB_STATUS_SUCCEEDED:
            continue
        started_at = row["started_at"]
        finished_at = row["finished_at"]
        if not started_at or not finished_at:
            continue
        start_dt = datetime.fromisoformat(started_at)
        finish_dt = datetime.fromisoformat(finished_at)
        timeline.append((start_dt, 0, row["job_id"]))
        timeline.append((finish_dt, 1, row["job_id"]))
        windows.append(
            {
                "job_id": row["job_id"],
                "worker_id": row["worker_id"],
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_ms": row["duration_ms"],
            }
        )

    timeline.sort(key=lambda item: (item[0], item[1], item[2]))
    current = 0
    peak = 0
    for _, kind, _job_id in timeline:
        if kind == 0:
            current += 1
            peak = max(peak, current)
        else:
            current = max(0, current - 1)

    distinct_workers = sorted({row["worker_id"] for row in windows if row["worker_id"]})
    return {
        "peak_concurrent_executions": peak,
        "distinct_success_workers": distinct_workers,
        "success_execution_windows": windows,
    }


def _build_probe_handler(*, probe_state: ProbeState):
    original_handler = jobs_module._run_handler

    def _handler(app, job_row):
        if str(job_row.get("job_type")) != DRILL_SUCCESS_JOB_TYPE:
            return original_handler(app, job_row)

        payload = job_row["payload"] if isinstance(job_row.get("payload"), dict) else {}
        sleep_seconds = max(0.2, float(payload.get("sleep_seconds") or DEFAULT_PROBE_SLEEP_SECONDS))
        job_id = int(job_row["id"])
        worker_id = str(job_row.get("locked_by") or payload.get("worker_id") or "unknown-worker")

        with probe_state.track(job_id=job_id, worker_id=worker_id):
            if probe_state.should_use_barrier() and probe_state.barrier is not None:
                try:
                    probe_state.barrier.wait(timeout=max(5.0, sleep_seconds + 3.0))
                    with probe_state.lock:
                        probe_state.barrier_release_count += 1
                except threading.BrokenBarrierError as exc:
                    raise RuntimeError("drill_concurrency_barrier_timeout") from exc
            time.sleep(sleep_seconds)

        return True, {
            "probe": True,
            "sleep_seconds": sleep_seconds,
            "barrier_parties": probe_state.barrier_parties,
            "max_active_count": probe_state.max_active_count,
        }

    return original_handler, _handler


def main() -> int:
    parser = argparse.ArgumentParser(description="Drill real de concorrencia/retry/dead-letter da fila de jobs.")
    parser.add_argument("--success-jobs", type=int, default=6, help="Quantidade de jobs de sucesso do drill.")
    parser.add_argument("--retry-fail-jobs", type=int, default=3, help="Quantidade de jobs de falha com retry.")
    parser.add_argument(
        "--success-job-type",
        choices=("probe", "backup", "notifications"),
        default="probe",
        help="Tipo de job de sucesso do drill. Use probe para prova real de concorrencia.",
    )
    parser.add_argument("--workers", type=int, default=4, help="Quantidade de workers concorrentes para o drill.")
    parser.add_argument("--max-jobs-per-worker", type=int, default=25)
    parser.add_argument(
        "--probe-sleep-seconds",
        type=float,
        default=DEFAULT_PROBE_SLEEP_SECONDS,
        help="Tempo de trabalho de cada probe de concorrencia.",
    )
    parser.add_argument(
        "--min-concurrent-workers",
        type=int,
        default=2,
        help="Concorrencia minima real exigida para o drill.",
    )
    parser.add_argument("--cleanup", action="store_true", help="Remove os jobs do drill ao final.")
    parser.add_argument("--output", default="", help="Arquivo opcional para salvar o JSON de evidencia.")
    args = parser.parse_args()

    db_url = (os.getenv("DATABASE_URL", "") or "").strip()
    if not db_url:
        print(json.dumps({"success": False, "message": "DATABASE_URL nao configurada."}, ensure_ascii=False, indent=2))
        return 1

    success_jobs = max(1, int(args.success_jobs))
    retry_fail_jobs = max(1, int(args.retry_fail_jobs))
    workers = max(1, int(args.workers))
    max_jobs_per_worker = max(1, int(args.max_jobs_per_worker))
    min_concurrent_workers = max(2, int(args.min_concurrent_workers))

    issues: list[str] = []
    if workers < min_concurrent_workers:
        issues.append("configured_workers_below_minimum_concurrency")
    if success_jobs < min_concurrent_workers:
        issues.append("configured_success_jobs_below_minimum_concurrency")

    app = create_app()
    run_id = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    key_prefix = f"drill:jobs:{run_id}:"
    probe_state = ProbeState(barrier_parties=min(min_concurrent_workers, workers, success_jobs))
    original_handler, drill_handler = _build_probe_handler(probe_state=probe_state)

    execution_rows: list[dict[str, Any]] = []
    counts_after_phase1: dict[str, int] = {}
    counts_final: dict[str, int] = {}
    phase1_workers: list[dict[str, int]] = []
    phase2_workers: list[dict[str, int]] = []
    success_ids: list[int] = []
    retry_ids: list[int] = []

    jobs_module._run_handler = drill_handler
    try:
        with app.app_context():
            db = get_db()

            for index in range(success_jobs):
                if args.success_job_type == "notifications":
                    result = enqueue_background_job(
                        db,
                        job_type="send_daily_notifications",
                        payload={"source": "drill"},
                        max_attempts=3,
                        idempotency_key=f"{key_prefix}ok:{index}",
                    )
                elif args.success_job_type == "backup":
                    result = enqueue_background_job(
                        db,
                        job_type="run_backup",
                        payload={"source": "drill", "backup_type": "drill"},
                        max_attempts=2,
                        idempotency_key=f"{key_prefix}ok:{index}",
                    )
                else:
                    result = enqueue_background_job(
                        db,
                        job_type=DRILL_SUCCESS_JOB_TYPE,
                        payload={"sleep_seconds": float(args.probe_sleep_seconds)},
                        max_attempts=1,
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
                workers=workers,
                max_jobs_per_worker=max_jobs_per_worker,
            )
            all_job_ids = success_ids + retry_ids
            counts_after_phase1 = _group_status_counts(db, job_ids=all_job_ids)

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
                workers=workers,
                max_jobs_per_worker=max_jobs_per_worker,
            )
            counts_final = _group_status_counts(db, job_ids=all_job_ids)
            execution_rows = _fetch_execution_rows(db, job_ids=all_job_ids)

            if args.cleanup:
                db.execute(
                    "DELETE FROM background_jobs WHERE id = ANY(%s)",
                    (all_job_ids,),
                )
                db.commit()
    finally:
        jobs_module._run_handler = original_handler

    concurrency = _compute_peak_concurrency(execution_rows)
    succeeded_final = counts_final.get(JOB_STATUS_SUCCEEDED, 0)
    dead_final = counts_final.get(JOB_STATUS_DEAD_LETTER, 0)
    queued_final = counts_final.get(JOB_STATUS_QUEUED, 0)
    running_final = counts_final.get(JOB_STATUS_RUNNING, 0)

    probe_concurrency_ok = args.success_job_type == "probe" and (
        concurrency["peak_concurrent_executions"] >= min_concurrent_workers
        and len(concurrency["distinct_success_workers"]) >= min_concurrent_workers
        and probe_state.max_active_count >= min_concurrent_workers
        and probe_state.barrier_release_count >= probe_state.barrier_parties
    )
    if args.success_job_type != "probe":
        issues.append("success_job_type_not_real_concurrency_proof")
    if not probe_concurrency_ok:
        issues.append("concurrency_proof_below_minimum")
    if succeeded_final < success_jobs:
        issues.append("success_jobs_below_expected")
    if dead_final < retry_fail_jobs:
        issues.append("dead_letter_jobs_below_expected")
    if queued_final != 0:
        issues.append("queued_jobs_remaining")
    if running_final != 0:
        issues.append("running_jobs_remaining")

    report = {
        "success": not issues,
        "run_id": run_id,
        "key_prefix": key_prefix,
        "success_job_type": args.success_job_type,
        "expected": {
            "succeeded_min": success_jobs,
            "dead_letter_min": retry_fail_jobs,
            "queued_final": 0,
            "running_final": 0,
            "min_concurrent_workers": min_concurrent_workers,
        },
        "phase1_worker_summaries": phase1_workers,
        "phase2_worker_summaries": phase2_workers,
        "counts_after_phase1": counts_after_phase1,
        "counts_final": counts_final,
        "probe_state": {
            "barrier_parties": probe_state.barrier_parties,
            "barrier_release_count": probe_state.barrier_release_count,
            "max_active_count": probe_state.max_active_count,
            "observations": [
                {
                    "job_id": item.job_id,
                    "worker_id": item.worker_id,
                    "event": item.event,
                    "active_count": item.active_count,
                    "monotonic_ts": round(item.monotonic_ts, 6),
                }
                for item in probe_state.observations
            ],
        },
        "concurrency_proof": concurrency,
        "execution_rows": execution_rows,
        "cleanup": bool(args.cleanup),
        "issues": issues,
    }

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)

    if args.output:
        output_path = Path(args.output).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")

    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
