from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_manifest_context(path: Path | None) -> tuple[dict | None, str, str, str]:
    if path is None:
        return None, "", "", "homolog"
    payload = _load_json(path)
    return (
        payload,
        str(payload.get("release_id", "") or "").strip(),
        str(payload.get("commit_sha", "") or "").strip(),
        str(payload.get("environment", "") or "").strip().lower() or "homolog",
    )


def _flatten_login_failures(runs: list[dict]) -> list[str]:
    failures: list[str] = []
    for run in runs:
        for item in run.get("login_failures", []) or []:
            text = str(item or "").strip()
            if text:
                failures.append(text)
    return failures


def _flatten_preflight_issues(runs: list[dict], key: str) -> list[dict]:
    items: list[dict] = []
    for run in runs:
        preflight = run.get("preflight") if isinstance(run.get("preflight"), dict) else {}
        for item in preflight.get(key, []) or []:
            if isinstance(item, dict):
                items.append(item)
    return items


def _as_float(value: object, default: float) -> float:
    if value is None or value == "":
        return float(default)
    return float(value)


def _build_scenario_artifact(
    *,
    matrix_report: dict,
    scenario_report: dict,
    manifest_path: Path | None,
    matrix_path: Path,
    release_id: str,
    commit_sha: str,
    environment: str,
) -> dict:
    scenario = str(scenario_report.get("scenario", "") or "").strip()
    summary = scenario_report.get("summary") if isinstance(scenario_report.get("summary"), dict) else {}
    runs = [item for item in (scenario_report.get("runs") or []) if isinstance(item, dict)]
    if not summary:
        raise RuntimeError(f"Resumo ausente para cenário {scenario or '<unknown>'}.")
    if not runs:
        raise RuntimeError(f"Execuções ausentes para cenário {scenario or '<unknown>'}.")

    workers = int(summary.get("workers", 0) or 0)
    seconds = int(summary.get("seconds", 0) or 0)
    requests = sum(int(run.get("requests", 0) or 0) for run in runs)
    auth_failures = sum(int(run.get("auth_failures", 0) or 0) for run in runs)
    permission_failures = sum(int(run.get("permission_failures", 0) or 0) for run in runs)
    non_http_errors = sum(int(run.get("non_http_errors", 0) or 0) for run in runs)
    recovered_transport_errors = sum(
        int(((run.get("transport_errors") or {}).get("recovered_total", 0) or 0)) for run in runs
    )
    latency_avg_values = [
        float(((run.get("latency_ms") or {}).get("avg", 0.0) or 0.0))
        for run in runs
    ]

    return {
        "success": bool(summary.get("pass", False)),
        "authenticated": all(bool(run.get("authenticated", False)) for run in runs),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": environment,
        "release_id": release_id,
        "commit_sha": commit_sha,
        "evidence_manifest": str(manifest_path) if manifest_path is not None else "",
        "base_url": str(matrix_report.get("base_url", "") or "").strip(),
        "scenario": scenario,
        "workers": workers,
        "seconds": seconds,
        "repeats": len(runs),
        "requests": requests,
        "availability_percent": float(((summary.get("availability_percent") or {}).get("worst", 0.0) or 0.0)),
        "percent_5xx": _as_float((summary.get("percent_5xx") or {}).get("worst"), 100.0),
        "latency_ms": {
            "p50": float(((summary.get("latency_ms") or {}).get("p50_median", 0.0) or 0.0)),
            "p95": float(((summary.get("latency_ms") or {}).get("p95_worst", 0.0) or 0.0)),
            "p99": float(((summary.get("latency_ms") or {}).get("p99_median", 0.0) or 0.0)),
            "avg": round(sum(latency_avg_values) / len(latency_avg_values), 2) if latency_avg_values else 0.0,
        },
        "non_http_errors": non_http_errors,
        "auth_failures": auth_failures,
        "permission_failures": permission_failures,
        "login_failures": _flatten_login_failures(runs),
        "transport_errors": {
            "recovered_total": recovered_transport_errors,
        },
        "preflight": {
            "auth_failures": _flatten_preflight_issues(runs, "auth_failures"),
            "permission_failures": _flatten_preflight_issues(runs, "permission_failures"),
        },
        "criteria": matrix_report.get("criteria", {}),
        "matrix_summary": summary,
        "phase_metrics": summary.get("phase_metrics", {}),
        "phase_hotspots": summary.get("phase_hotspots", []),
        "runs": runs,
        "source_matrix_artifact": str(matrix_path),
    }


def _upsert_manifest(
    manifest_path: Path,
    *,
    load_20_artifact: Path,
    load_30_artifact: Path,
    matrix_artifact: Path,
    load_20_ok: bool,
    load_30_ok: bool,
) -> None:
    payload = _load_json(manifest_path)
    checks = payload.get("checks")
    if not isinstance(checks, dict):
        checks = {}
        payload["checks"] = checks

    checks["load_authenticated_20w"] = {
        "status": "PASS" if load_20_ok else "FAIL",
        "artifacts": [str(load_20_artifact), str(matrix_artifact)],
    }
    checks["load_authenticated_30w"] = {
        "status": "PASS" if load_30_ok else "FAIL",
        "artifacts": [str(load_30_artifact), str(matrix_artifact)],
    }
    _write_json(manifest_path, payload)


def _upsert_checklist_load_attachment(checklist_path: Path, attachment: Path) -> None:
    lines = checklist_path.read_text(encoding="utf-8").splitlines()
    updated_lines: list[str] = []
    replaced = False

    for line in lines:
        if line.strip().lower().startswith("- carga autenticada:"):
            if not replaced:
                updated_lines.append(f"- Carga autenticada: {attachment}")
                replaced = True
            continue
        updated_lines.append(line)

    if not replaced:
        updated_lines.append(f"- Carga autenticada: {attachment}")

    checklist_path.write_text("\n".join(updated_lines).rstrip() + "\n", encoding="utf-8")


def _run_matrix(py_exec: str, script: Path, cmd_args: list[str]) -> dict:
    cmd = [py_exec, str(script), *cmd_args]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    merged = ((completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")).strip()
    if not merged:
        raise RuntimeError("Matriz autenticada sem saída JSON.")
    try:
        payload = json.loads(merged)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Saída inválida da matriz autenticada: {merged[:280]!r}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Payload inválido da matriz autenticada.")
    payload["_exit_code"] = completed.returncode
    payload["_command"] = " ".join(shlex.quote(part) for part in cmd)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Executa carga autenticada real por cenário e integra ao pacote release.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--login", required=True)
    parser.add_argument("--password", default="")
    parser.add_argument("--password-file", default="")
    parser.add_argument("--password-env", default="LOADTEST_PASSWORD")
    parser.add_argument("--job-id", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--transport-retries", type=int, default=2)
    parser.add_argument("--max-non-http-errors", type=int, default=0)
    parser.add_argument("--max-recovered-transport-errors", type=int, default=50)
    parser.add_argument("--include-bases-endpoint", action="store_true")
    parser.add_argument("--out-dir", required=True, help="Diretório externo para evidências de carga autenticada.")
    parser.add_argument("--summary-json", default="", help="JSON agregado da matriz autenticada.")
    parser.add_argument("--manifest", default="", help="Manifest do pacote release para atualizar os checks.")
    parser.add_argument("--regression-checklist", default="", help="Checklist de regressão para atualizar o anexo.")
    args = parser.parse_args()

    ops_root = Path(__file__).resolve().parents[2]
    repo_root = ops_root.parent
    matrix_script = ops_root / "scripts" / "perf" / "run_authenticated_matrix.py"
    windows_py = repo_root / ".venv" / "Scripts" / "python.exe"
    posix_py = repo_root / ".venv" / "bin" / "python"
    py_exec = str(windows_py if windows_py.exists() else posix_py if posix_py.exists() else Path(sys.executable))

    out_dir = Path(args.out_dir).expanduser()
    if not out_dir.is_absolute():
        raise SystemExit("--out-dir deve apontar para um diretório externo explícito.")
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_path = Path(args.summary_json).expanduser() if (args.summary_json or "").strip() else (out_dir / "load_auth_matrix.json")
    if not summary_path.is_absolute():
        raise SystemExit("--summary-json deve apontar para um caminho externo explícito.")
    summary_path = summary_path.resolve()
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    manifest_path = Path(args.manifest).expanduser().resolve() if (args.manifest or "").strip() else None
    checklist_path = Path(args.regression_checklist).expanduser().resolve() if (args.regression_checklist or "").strip() else None
    _manifest_payload, release_id, commit_sha, environment = _load_manifest_context(manifest_path)

    matrix_args = [
        "--base-url",
        (args.base_url or "").strip(),
        "--login",
        (args.login or "").strip(),
        "--job-id",
        str(max(1, int(args.job_id))),
        "--timeout",
        str(max(3, int(args.timeout))),
        "--repeats",
        str(max(1, int(args.repeats))),
        "--transport-retries",
        str(max(0, int(args.transport_retries))),
        "--max-non-http-errors",
        str(max(0, int(args.max_non_http_errors))),
        "--max-recovered-transport-errors",
        str(max(0, int(args.max_recovered_transport_errors))),
        "--output",
        str(summary_path),
    ]
    if (args.password or "").strip():
        matrix_args.extend(["--password", args.password.strip()])
    if (args.password_file or "").strip():
        matrix_args.extend(["--password-file", args.password_file.strip()])
    if (args.password_env or "").strip():
        matrix_args.extend(["--password-env", args.password_env.strip()])
    if args.include_bases_endpoint:
        matrix_args.append("--include-bases-endpoint")

    matrix_report = _run_matrix(py_exec, matrix_script, matrix_args)
    matrix_report["generated_at"] = datetime.now(timezone.utc).isoformat()
    matrix_report["environment"] = environment
    matrix_report["release_id"] = release_id
    matrix_report["commit_sha"] = commit_sha
    matrix_report["evidence_manifest"] = str(manifest_path) if manifest_path is not None else ""
    matrix_report["base_url"] = (args.base_url or "").strip()
    matrix_report["command"] = str(matrix_report.get("_command", "") or "")
    _write_json(summary_path, {k: v for k, v in matrix_report.items() if not str(k).startswith("_")})

    scenario_index: dict[int, tuple[dict, Path]] = {}
    for item in matrix_report.get("matrix", []) or []:
        if not isinstance(item, dict):
            continue
        summary = item.get("summary") if isinstance(item.get("summary"), dict) else {}
        workers = int(summary.get("workers", 0) or 0)
        if workers not in {20, 30}:
            continue
        artifact_name = f"load_auth_{workers}w.json"
        artifact_path = (out_dir / artifact_name).resolve()
        artifact_payload = _build_scenario_artifact(
            matrix_report={k: v for k, v in matrix_report.items() if not str(k).startswith("_")},
            scenario_report=item,
            manifest_path=manifest_path,
            matrix_path=summary_path,
            release_id=release_id,
            commit_sha=commit_sha,
            environment=environment,
        )
        _write_json(artifact_path, artifact_payload)
        scenario_index[workers] = (artifact_payload, artifact_path)

    if 20 not in scenario_index or 30 not in scenario_index:
        raise RuntimeError("A matriz autenticada não produziu artefatos 20w e 30w.")

    load_20_payload, load_20_path = scenario_index[20]
    load_30_payload, load_30_path = scenario_index[30]

    if manifest_path is not None:
        _upsert_manifest(
            manifest_path,
            load_20_artifact=load_20_path,
            load_30_artifact=load_30_path,
            matrix_artifact=summary_path,
            load_20_ok=bool(load_20_payload.get("success")),
            load_30_ok=bool(load_30_payload.get("success")),
        )

    if checklist_path is not None:
        _upsert_checklist_load_attachment(checklist_path, summary_path)

    print(
        json.dumps(
            {
                "success": bool(matrix_report.get("success", False)),
                "base_url": (args.base_url or "").strip(),
                "artifacts": {
                    "load_authenticated_20w": str(load_20_path),
                    "load_authenticated_30w": str(load_30_path),
                    "matrix": str(summary_path),
                },
                "results": {
                    "load_authenticated_20w": {
                        "success": bool(load_20_payload.get("success", False)),
                        "requests": int(load_20_payload.get("requests", 0) or 0),
                        "availability_percent": float(load_20_payload.get("availability_percent", 0.0) or 0.0),
                        "p95_ms": float(((load_20_payload.get("latency_ms") or {}).get("p95", 0.0) or 0.0)),
                    },
                    "load_authenticated_30w": {
                        "success": bool(load_30_payload.get("success", False)),
                        "requests": int(load_30_payload.get("requests", 0) or 0),
                        "availability_percent": float(load_30_payload.get("availability_percent", 0.0) or 0.0),
                        "p95_ms": float(((load_30_payload.get("latency_ms") or {}).get("p95", 0.0) or 0.0)),
                    },
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if bool(matrix_report.get("success", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
