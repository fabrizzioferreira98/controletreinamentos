from __future__ import annotations

import argparse
import json
import statistics
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor


def _hit(url: str, timeout: int) -> dict:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=timeout) as resp:
            _ = resp.read(256)
            status = resp.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    except Exception:
        status = 0
    duration_ms = (time.perf_counter() - started) * 1000
    return {"status": status, "duration_ms": duration_ms}


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    idx = max(0, min(len(values) - 1, int(round((p / 100.0) * (len(values) - 1)))))
    return sorted(values)[idx]


def main() -> int:
    parser = argparse.ArgumentParser(description="Load test leve para baseline")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=10)
    args = parser.parse_args()

    targets = [
        "/login",
        "/dashboard",
        "/treinamentos",
        "/missoes",
        "/notificacoes-email",
    ]
    urls = [args.base_url.rstrip("/") + target for target in targets]

    lock = threading.Lock()
    samples: list[dict] = []
    deadline = time.time() + max(5, args.seconds)
    max_workers = max(1, args.workers)
    # Keep a bounded in-flight queue; prevents long drain times after deadline.
    max_in_flight = max_workers * max(1, len(urls))

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = []
        while time.time() < deadline or futures:
            while time.time() < deadline and len(futures) < max_in_flight:
                for url in urls:
                    if time.time() >= deadline or len(futures) >= max_in_flight:
                        break
                    futures.append(pool.submit(_hit, url, args.timeout))

            done = [f for f in futures if f.done()]
            if not done:
                time.sleep(0.01)
                continue
            for fut in done:
                futures.remove(fut)
                with lock:
                    samples.append(fut.result())

    durations = [item["duration_ms"] for item in samples]
    status_non_error = [item for item in samples if item["status"] and item["status"] < 500]
    availability = (len(status_non_error) / len(samples) * 100.0) if samples else 0.0

    report = {
        "requests": len(samples),
        "availability_percent": round(availability, 2),
        "latency_ms": {
            "p50": round(_percentile(durations, 50), 2),
            "p95": round(_percentile(durations, 95), 2),
            "p99": round(_percentile(durations, 99), 2),
            "avg": round(statistics.mean(durations), 2) if durations else 0.0,
        },
        "status_histogram": {
            str(status): sum(1 for item in samples if item["status"] == status)
            for status in sorted({item["status"] for item in samples})
        },
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))

    fail = report["availability_percent"] < 99.0 or report["latency_ms"]["p95"] > 1200
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
