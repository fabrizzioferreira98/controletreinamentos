from __future__ import annotations

import argparse
import json
import shlex
import statistics
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ScenarioResult:
    workers: int
    seconds: int
    run_index: int
    success: bool
    report: dict


def _as_float(value: object, default: float) -> float:
    if value is None or value == "":
        return float(default)
    return float(value)


def _as_int(value: object, default: int) -> int:
    if value is None or value == "":
        return int(default)
    return int(value)


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    idx = max(0, min(len(values) - 1, int(round((p / 100.0) * (len(values) - 1)))))
    return sorted(values)[idx]


def _run_once(*, base_cmd: list[str], workers: int, seconds: int, run_index: int) -> ScenarioResult:
    cmd = [*base_cmd, "--workers", str(workers), "--seconds", str(seconds)]
    completed = subprocess.run(cmd, capture_output=True, text=True)

    output = (completed.stdout or "").strip()
    if not output:
        raise RuntimeError(
            f"Teste sem saída JSON. workers={workers} run={run_index} stderr={(completed.stderr or '').strip()[:280]}"
        )
    try:
        report = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Saída inválida do teste autenticado. workers={workers} run={run_index}. "
            f"stdout_snippet={output[:280]!r} stderr_snippet={(completed.stderr or '')[:280]!r}"
        ) from exc

    return ScenarioResult(
        workers=workers,
        seconds=seconds,
        run_index=run_index,
        success=bool(report.get("success", False)) and completed.returncode == 0,
        report=report,
    )


def _summarize(results: list[ScenarioResult]) -> dict:
    lat_p50 = [float(r.report.get("latency_ms", {}).get("p50", 0.0) or 0.0) for r in results]
    lat_p95 = [float(r.report.get("latency_ms", {}).get("p95", 0.0) or 0.0) for r in results]
    lat_p99 = [float(r.report.get("latency_ms", {}).get("p99", 0.0) or 0.0) for r in results]
    avail = [float(r.report.get("availability_percent", 0.0) or 0.0) for r in results]
    pct_5xx = [_as_float(r.report.get("percent_5xx"), 100.0) for r in results]
    non_http = [int(r.report.get("non_http_errors", 0) or 0) for r in results]
    auth_fail = [int(r.report.get("auth_failures", 0) or 0) for r in results]
    permission_fail = [int(r.report.get("permission_failures", 0) or 0) for r in results]
    login_fail = [len(r.report.get("login_failures", []) or []) for r in results]
    preflight_auth_fail = [len(((r.report.get("preflight") or {}).get("auth_failures") or [])) for r in results]

    endpoint_p95_samples: dict[str, list[float]] = {}
    for result in results:
        for endpoint, metrics in (result.report.get("per_endpoint") or {}).items():
            endpoint_p95_samples.setdefault(endpoint, []).append(
                float((metrics.get("latency_ms") or {}).get("p95", 0.0) or 0.0)
            )

    endpoint_hotspots = [
        {
            "endpoint": endpoint,
            "p95_ms_median": round(statistics.median(values), 2),
            "p95_ms_p95": round(_percentile(values, 95), 2),
        }
        for endpoint, values in endpoint_p95_samples.items()
    ]
    endpoint_hotspots.sort(key=lambda x: x["p95_ms_p95"], reverse=True)

    phase_p95_samples: dict[str, list[float]] = {}
    phase_request_counts: dict[str, int] = {}
    for result in results:
        for phase, metrics in (result.report.get("phase_metrics") or {}).items():
            if not isinstance(metrics, dict):
                continue
            phase_p95_samples.setdefault(str(phase), []).append(
                float(((metrics.get("latency_ms") or {}).get("p95", 0.0) or 0.0))
            )
            phase_request_counts[str(phase)] = phase_request_counts.get(str(phase), 0) + int(metrics.get("requests", 0) or 0)

    phase_metrics = {
        phase: {
            "requests": int(phase_request_counts.get(phase, 0)),
            "exercised": int(phase_request_counts.get(phase, 0)) > 0,
            "p95_ms_median": round(statistics.median(values), 2),
            "p95_ms_p95": round(_percentile(values, 95), 2),
        }
        for phase, values in sorted(phase_p95_samples.items())
    }
    phase_hotspots = [
        {"phase": phase, **metrics}
        for phase, metrics in sorted(
            phase_metrics.items(),
            key=lambda item: item[1]["p95_ms_p95"],
            reverse=True,
        )
        if metrics["requests"] > 0
    ]

    return {
        "runs": len(results),
        "success_runs": sum(1 for r in results if r.success),
        "latency_ms": {
            "p50_median": round(statistics.median(lat_p50), 2) if lat_p50 else 0.0,
            "p95_median": round(statistics.median(lat_p95), 2) if lat_p95 else 0.0,
            "p99_median": round(statistics.median(lat_p99), 2) if lat_p99 else 0.0,
            "p95_worst": round(max(lat_p95), 2) if lat_p95 else 0.0,
        },
        "availability_percent": {
            "median": round(statistics.median(avail), 2) if avail else 0.0,
            "worst": round(min(avail), 2) if avail else 0.0,
        },
        "percent_5xx": {
            "median": round(statistics.median(pct_5xx), 3) if pct_5xx else 100.0,
            "worst": round(max(pct_5xx), 3) if pct_5xx else 100.0,
        },
        "non_http_errors": {
            "median": int(statistics.median(non_http)) if non_http else 0,
            "worst": int(max(non_http)) if non_http else 0,
        },
        "auth_failures": {
            "median": int(statistics.median(auth_fail)) if auth_fail else 0,
            "worst": int(max(auth_fail)) if auth_fail else 0,
        },
        "permission_failures": {
            "median": int(statistics.median(permission_fail)) if permission_fail else 0,
            "worst": int(max(permission_fail)) if permission_fail else 0,
        },
        "login_failures": {
            "median": int(statistics.median(login_fail)) if login_fail else 0,
            "worst": int(max(login_fail)) if login_fail else 0,
        },
        "preflight_auth_failures": {
            "median": int(statistics.median(preflight_auth_fail)) if preflight_auth_fail else 0,
            "worst": int(max(preflight_auth_fail)) if preflight_auth_fail else 0,
        },
        "hotspots": endpoint_hotspots[:8],
        "phase_metrics": phase_metrics,
        "phase_hotspots": phase_hotspots,
    }


def _scenario_pass(summary: dict) -> bool:
    # PASS estrito para pré-produção autenticada.
    return (
        int(summary.get("runs", 0)) > 0
        and int(summary.get("success_runs", 0)) == int(summary.get("runs", 0))
        and _as_float((summary.get("availability_percent") or {}).get("worst"), 0.0) >= 99.0
        and _as_float((summary.get("latency_ms") or {}).get("p95_worst"), 999999.0) <= 1200.0
        and _as_float((summary.get("percent_5xx") or {}).get("worst"), 100.0) <= 0.5
        and _as_int((summary.get("auth_failures") or {}).get("worst"), 999999) == 0
        and _as_int((summary.get("permission_failures") or {}).get("worst"), 999999) == 0
        and _as_int((summary.get("login_failures") or {}).get("worst"), 999999) == 0
        and _as_int((summary.get("preflight_auth_failures") or {}).get("worst"), 999999) == 0
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Matriz de carga autenticada 20w/30w com repetição.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--login", required=True)
    parser.add_argument("--password", default="")
    parser.add_argument("--password-file", default="")
    parser.add_argument("--password-env", default="LOADTEST_PASSWORD")
    parser.add_argument("--job-id", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--transport-retries", type=int, default=2)
    parser.add_argument("--max-non-http-errors", type=int, default=0)
    parser.add_argument("--max-recovered-transport-errors", type=int, default=50)
    parser.add_argument("--include-bases-endpoint", action="store_true")
    parser.add_argument(
        "--include-soak-30w-1800s",
        action="store_true",
        help="Inclui cenário de soak obrigatório 30 workers por 1800 segundos.",
    )
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    base_cmd = [
        sys.executable,
        "ops/scripts/perf/load_test_authenticated.py",
        "--base-url",
        args.base_url,
        "--login",
        args.login,
        "--job-id",
        str(args.job_id),
        "--timeout",
        str(args.timeout),
        "--transport-retries",
        str(args.transport_retries),
        "--max-non-http-errors",
        str(args.max_non_http_errors),
        "--max-permission-failures",
        "0",
        "--max-recovered-transport-errors",
        str(args.max_recovered_transport_errors),
        "--require-preflight-auth",
    ]
    if args.password:
        base_cmd.extend(["--password", args.password])
    if args.password_file:
        base_cmd.extend(["--password-file", args.password_file])
    if args.password_env:
        base_cmd.extend(["--password-env", args.password_env])
    if args.include_bases_endpoint:
        base_cmd.append("--include-bases-endpoint")

    scenarios = [(20, 300), (30, 300)]
    if args.include_soak_30w_1800s:
        scenarios.append((30, 1800))
    repeats = max(1, int(args.repeats))

    matrix_results = []
    for workers, seconds in scenarios:
        runs = []
        for run_index in range(1, repeats + 1):
            runs.append(_run_once(base_cmd=base_cmd, workers=workers, seconds=seconds, run_index=run_index))
        summary = _summarize(runs)
        summary["pass"] = _scenario_pass(summary)
        summary["workers"] = workers
        summary["seconds"] = seconds
        matrix_results.append(
            {
                "scenario": f"{workers}w/{seconds}s",
                "summary": summary,
                "runs": [r.report for r in runs],
            }
        )

    overall_pass = all((item.get("summary") or {}).get("pass", False) for item in matrix_results)

    report = {
        "success": overall_pass,
        "criteria": {
            "availability_min_percent": 99.0,
            "p95_worst_max_ms": 1200.0,
            "percent_5xx_worst_max": 0.5,
            "auth_failures_worst_max": 0,
            "permission_failures_worst_max": 0,
            "login_failures_worst_max": 0,
            "preflight_auth_failures_worst_max": 0,
        },
        "command": " ".join(shlex.quote(part) for part in base_cmd),
        "matrix": matrix_results,
    }

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as fh:
            fh.write(rendered + "\n")

    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
