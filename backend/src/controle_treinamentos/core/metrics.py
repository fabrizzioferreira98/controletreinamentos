from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any

try:
    from prometheus_client import Counter, Gauge, Histogram, REGISTRY
except ImportError:
    Counter = Gauge = Histogram = None  # type: ignore[assignment]
    REGISTRY = None  # type: ignore[assignment]


class _MockMetric:
    def labels(self, *_args, **_kwargs):
        return self

    def inc(self, *_args, **_kwargs) -> None:
        return None

    def observe(self, *_args, **_kwargs) -> None:
        return None

    def set(self, *_args, **_kwargs) -> None:
        return None


def _existing_collector(name: str):
    names = getattr(REGISTRY, "_names_to_collectors", {}) if REGISTRY is not None else {}
    candidates = [name]
    if name.endswith("_total"):
        candidates.append(name.removesuffix("_total"))
    else:
        candidates.append(f"{name}_total")
    for candidate in candidates:
        collector = names.get(candidate)
        if collector is not None:
            return collector
    return None


def _metric(factory, name: str, description: str, labels: list[str] | None = None, **kwargs):
    if factory is None:
        return _MockMetric()
    try:
        return factory(name, description, labels or [], **kwargs)
    except ValueError:
        return _existing_collector(name) or _MockMetric()


def _counter(name: str, description: str, labels: list[str] | None = None):
    return _metric(Counter, name, description, labels)


def _gauge(name: str, description: str, labels: list[str] | None = None):
    return _metric(Gauge, name, description, labels)


def _histogram(name: str, description: str, labels: list[str] | None = None, *, buckets: tuple[float, ...]):
    return _metric(Histogram, name, description, labels, buckets=buckets)


def _label(value: Any, *, default: str = "unknown", limit: int = 80) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        raw = default
    safe = []
    for char in raw[:limit]:
        safe.append(char if char.isalnum() or char in {"_", "-", ".", ":"} else "_")
    return "".join(safe).strip("_") or default


def _seconds_from_ms(duration_ms: int | float | None) -> float:
    return max(0.0, float(duration_ms or 0) / 1000.0)


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


HTTP_OPERATION_BUCKETS: tuple[float, ...] = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30)
JOB_DURATION_BUCKETS: tuple[float, ...] = (0.1, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 900, 1800, 3600)
BYTE_BUCKETS: tuple[float, ...] = (
    1024,
    10 * 1024,
    100 * 1024,
    1024 * 1024,
    5 * 1024 * 1024,
    20 * 1024 * 1024,
    100 * 1024 * 1024,
)

BACKGROUND_JOB_EXECUTIONS_TOTAL = _counter(
    "background_job_executions_total",
    "Total background job executions by type and final status.",
    ["job_type", "status"],
)
BACKGROUND_JOB_DURATION_SECONDS = _histogram(
    "background_job_duration_seconds",
    "Background job execution duration in seconds.",
    ["job_type", "status"],
    buckets=JOB_DURATION_BUCKETS,
)
BACKGROUND_JOB_QUEUE_BACKLOG = _gauge(
    "background_job_queue_backlog",
    "Current background job backlog by state.",
    ["state"],
)
BACKGROUND_JOB_OLDEST_QUEUED_SECONDS = _gauge(
    "background_job_oldest_queued_seconds",
    "Age in seconds of the oldest queued background job.",
)
BACKGROUND_WORKER_CYCLES_TOTAL = _counter(
    "background_worker_cycles_total",
    "Total background worker cycles by status.",
    ["status"],
)

PDF_GENERATIONS_TOTAL = _counter(
    "pdf_generations_total",
    "Total generated PDF render attempts by renderer and status.",
    ["renderer", "status"],
)
PDF_GENERATION_DURATION_SECONDS = _histogram(
    "pdf_generation_duration_seconds",
    "Generated PDF render duration in seconds.",
    ["renderer", "status"],
    buckets=HTTP_OPERATION_BUCKETS + (60, 120, 300),
)
PDF_GENERATION_SIZE_BYTES = _histogram(
    "pdf_generation_size_bytes",
    "Generated PDF size in bytes.",
    ["renderer", "status"],
    buckets=BYTE_BUCKETS,
)
PDF_RESPONSES_TOTAL = _counter(
    "pdf_document_responses_total",
    "Total PDF document response attempts by policy and status.",
    ["policy", "kind", "status"],
)
PDF_RESPONSE_SIZE_BYTES = _histogram(
    "pdf_document_response_size_bytes",
    "PDF document response size in bytes.",
    ["policy", "kind", "status"],
    buckets=BYTE_BUCKETS,
)

FILE_ACCESS_RESPONSES_TOTAL = _counter(
    "file_access_responses_total",
    "Total file access response attempts by policy, action, source and status.",
    ["policy", "action", "source", "status"],
)
FILE_ACCESS_RESPONSE_DURATION_SECONDS = _histogram(
    "file_access_response_duration_seconds",
    "File access response preparation duration in seconds.",
    ["policy", "action", "source", "status"],
    buckets=HTTP_OPERATION_BUCKETS,
)
FILE_ACCESS_RESPONSE_SIZE_BYTES = _histogram(
    "file_access_response_size_bytes",
    "File access response payload size in bytes.",
    ["policy", "action", "source", "status"],
    buckets=BYTE_BUCKETS,
)

STORAGE_OPERATIONS_TOTAL = _counter(
    "storage_operations_total",
    "Total media storage operations by operation, policy and status.",
    ["operation", "policy", "status"],
)
STORAGE_OPERATION_DURATION_SECONDS = _histogram(
    "storage_operation_duration_seconds",
    "Media storage operation duration in seconds.",
    ["operation", "policy", "status"],
    buckets=HTTP_OPERATION_BUCKETS,
)
STORAGE_TRANSFER_SIZE_BYTES = _histogram(
    "storage_transfer_size_bytes",
    "Media storage transferred payload size in bytes.",
    ["operation", "policy", "status"],
    buckets=BYTE_BUCKETS,
)

CRITICAL_FLOW_FAILURES_TOTAL = _counter(
    "critical_flow_failures_total",
    "Total critical operational flow failures by flow and reason.",
    ["flow", "reason"],
)
CRITICAL_FLOW_DURATION_SECONDS = _histogram(
    "critical_flow_duration_seconds",
    "Critical operational flow duration in seconds.",
    ["flow", "status"],
    buckets=JOB_DURATION_BUCKETS,
)

RUNTIME_PROCESS_MEMORY_BYTES = _gauge(
    "runtime_process_memory_bytes",
    "Current process memory usage in bytes.",
    ["kind"],
)
RUNTIME_PROCESS_CPU_PERCENT = _gauge(
    "runtime_process_cpu_percent",
    "Current process CPU percent at scrape refresh time.",
)
RUNTIME_DISK_USAGE_PERCENT = _gauge(
    "runtime_disk_usage_percent",
    "Current disk usage percent for runtime storage scopes.",
    ["scope"],
)
RUNTIME_RESOURCE_METRICS_AVAILABLE = _gauge(
    "runtime_resource_metrics_available",
    "Whether runtime resource metrics could be collected.",
    ["collector"],
)
RUNTIME_ENVIRONMENT_SIGNAL = _gauge(
    "runtime_environment_signal",
    "Environment-level operational signal for the running process.",
    ["app_env", "database_configured", "metrics_token_configured", "sentry_configured"],
)


def record_background_job_execution(job_type: str, status: str, duration_ms: int | float) -> None:
    safe_job_type = _label(job_type, default="unknown_job")
    safe_status = _label(status, default="unknown")
    BACKGROUND_JOB_EXECUTIONS_TOTAL.labels(safe_job_type, safe_status).inc()
    BACKGROUND_JOB_DURATION_SECONDS.labels(safe_job_type, safe_status).observe(_seconds_from_ms(duration_ms))
    if safe_status not in {"succeeded", "success"}:
        record_critical_flow_failure(f"background_job:{safe_job_type}", safe_status)


def record_background_worker_cycle(status: str) -> None:
    BACKGROUND_WORKER_CYCLES_TOTAL.labels(_label(status, default="unknown")).inc()


def set_background_job_queue_snapshot(snapshot: dict[str, Any]) -> None:
    for state in ("queued", "running", "succeeded", "dead_letter", "stale_running"):
        BACKGROUND_JOB_QUEUE_BACKLOG.labels(state).set(int(snapshot.get(state) or 0))
    oldest_minutes = snapshot.get("oldest_queued_minutes")
    BACKGROUND_JOB_OLDEST_QUEUED_SECONDS.set(0 if oldest_minutes is None else max(0.0, float(oldest_minutes) * 60.0))


def record_pdf_generation(renderer: str, status: str, duration_ms: int | float, size_bytes: int | None = None) -> None:
    safe_renderer = _label(renderer, default="unknown_renderer")
    safe_status = _label(status, default="unknown")
    PDF_GENERATIONS_TOTAL.labels(safe_renderer, safe_status).inc()
    PDF_GENERATION_DURATION_SECONDS.labels(safe_renderer, safe_status).observe(_seconds_from_ms(duration_ms))
    if size_bytes is not None:
        PDF_GENERATION_SIZE_BYTES.labels(safe_renderer, safe_status).observe(max(0, int(size_bytes)))
    if safe_status not in {"succeeded", "success"}:
        record_critical_flow_failure(f"pdf_generation:{safe_renderer}", safe_status)


def record_pdf_response(policy: str, kind: str, status: str, size_bytes: int | None = None) -> None:
    safe_policy = _label(policy, default="unknown_policy")
    safe_kind = _label(kind, default="unknown_kind")
    safe_status = _label(status, default="unknown")
    PDF_RESPONSES_TOTAL.labels(safe_policy, safe_kind, safe_status).inc()
    if size_bytes is not None:
        PDF_RESPONSE_SIZE_BYTES.labels(safe_policy, safe_kind, safe_status).observe(max(0, int(size_bytes)))
    if safe_status not in {"succeeded", "success"}:
        record_critical_flow_failure(f"pdf_response:{safe_policy}", safe_status)


def record_file_access_response(
    *,
    policy: str,
    action: str,
    source: str,
    status: str,
    duration_ms: int | float,
    size_bytes: int | None = None,
) -> None:
    safe_policy = _label(policy, default="unknown_policy")
    safe_action = _label(action, default="unknown_action")
    safe_source = _label(source, default="unknown_source")
    safe_status = _label(status, default="unknown")
    FILE_ACCESS_RESPONSES_TOTAL.labels(safe_policy, safe_action, safe_source, safe_status).inc()
    FILE_ACCESS_RESPONSE_DURATION_SECONDS.labels(safe_policy, safe_action, safe_source, safe_status).observe(
        _seconds_from_ms(duration_ms)
    )
    if size_bytes is not None:
        FILE_ACCESS_RESPONSE_SIZE_BYTES.labels(safe_policy, safe_action, safe_source, safe_status).observe(
            max(0, int(size_bytes))
        )
    if safe_status not in {"succeeded", "success", "forbidden"}:
        record_critical_flow_failure(f"file_access:{safe_policy}:{safe_action}", safe_status)


def record_storage_operation(
    *,
    operation: str,
    policy: str,
    status: str,
    duration_ms: int | float,
    size_bytes: int | None = None,
) -> None:
    safe_operation = _label(operation, default="unknown_operation")
    safe_policy = _label(policy, default="generic")
    safe_status = _label(status, default="unknown")
    STORAGE_OPERATIONS_TOTAL.labels(safe_operation, safe_policy, safe_status).inc()
    STORAGE_OPERATION_DURATION_SECONDS.labels(safe_operation, safe_policy, safe_status).observe(
        _seconds_from_ms(duration_ms)
    )
    if size_bytes is not None:
        STORAGE_TRANSFER_SIZE_BYTES.labels(safe_operation, safe_policy, safe_status).observe(max(0, int(size_bytes)))
    if safe_status not in {"succeeded", "success"}:
        record_critical_flow_failure(f"storage:{safe_operation}:{safe_policy}", safe_status)


def record_critical_flow_failure(flow: str, reason: str) -> None:
    CRITICAL_FLOW_FAILURES_TOTAL.labels(
        _label(flow, default="unknown_flow", limit=120),
        _label(reason, default="unknown_reason", limit=120),
    ).inc()


def record_critical_flow_duration(flow: str, status: str, duration_ms: int | float) -> None:
    CRITICAL_FLOW_DURATION_SECONDS.labels(
        _label(flow, default="unknown_flow", limit=120),
        _label(status, default="unknown_status"),
    ).observe(_seconds_from_ms(duration_ms))


def refresh_runtime_resource_metrics(*, instance_path: str | os.PathLike[str] | None = None) -> None:
    try:
        import psutil  # type: ignore

        process = psutil.Process(os.getpid())
        memory = process.memory_info()
        RUNTIME_PROCESS_MEMORY_BYTES.labels("rss").set(int(memory.rss))
        RUNTIME_PROCESS_MEMORY_BYTES.labels("vms").set(int(memory.vms))
        RUNTIME_PROCESS_CPU_PERCENT.set(float(process.cpu_percent(interval=None)))
        RUNTIME_RESOURCE_METRICS_AVAILABLE.labels("psutil").set(1)
    except Exception:
        RUNTIME_RESOURCE_METRICS_AVAILABLE.labels("psutil").set(0)

    if instance_path is None:
        return
    try:
        usage = shutil.disk_usage(str(Path(instance_path)))
        used_percent = 0 if usage.total <= 0 else (usage.used / usage.total) * 100.0
        RUNTIME_DISK_USAGE_PERCENT.labels("instance").set(float(used_percent))
        RUNTIME_RESOURCE_METRICS_AVAILABLE.labels("disk_usage").set(1)
    except Exception:
        RUNTIME_RESOURCE_METRICS_AVAILABLE.labels("disk_usage").set(0)


def refresh_environment_signal(*, app_env: str | None = None) -> None:
    RUNTIME_ENVIRONMENT_SIGNAL.labels(
        _label(app_env or os.getenv("APP_ENV") or "development", default="development"),
        "1" if (os.getenv("DATABASE_URL", "") or "").strip() else "0",
        "1" if (os.getenv("METRICS_TOKEN", "") or "").strip() else "0",
        "1" if (os.getenv("SENTRY_DSN", "") or "").strip() else "0",
    ).set(1)

