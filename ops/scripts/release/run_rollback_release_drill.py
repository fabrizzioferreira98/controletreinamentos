from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_manifest_context(path: Path | None) -> tuple[str, str, str]:
    if path is None:
        return "", "", "homolog"
    payload = _load_json(path)
    return (
        str(payload.get("release_id", "") or "").strip(),
        str(payload.get("commit_sha", "") or "").strip(),
        str(payload.get("environment", "") or "").strip().lower() or "homolog",
    )


def _resolve_existing_path(raw: str, *, label: str, issues: list[str]) -> Path | None:
    value = (raw or "").strip()
    if not value:
        issues.append(f"{label}_missing")
        return None
    path = Path(value).expanduser().resolve()
    if not path.exists() or path.is_dir():
        issues.append(f"{label}_not_found")
        return None
    return path


def _load_smoke(path: Path | None, *, label: str, issues: list[str]) -> dict | None:
    if path is None:
        return None
    try:
        payload = _load_json(path)
    except Exception:
        issues.append(f"{label}_not_json")
        return None
    if not isinstance(payload, dict):
        issues.append(f"{label}_not_object")
        return None
    if "failed" not in payload:
        issues.append(f"{label}_missing_failed_flag")
    return payload


def _run_metadata_builder(
    *,
    py_exec: str,
    script: Path,
    header_before: Path,
    header_rollback: Path,
    header_forward: Path,
    smoke_before: Path,
    smoke_rollback: Path,
    smoke_forward: Path,
    output: Path,
) -> tuple[int, dict, str]:
    cmd = [
        py_exec,
        str(script),
        "--header-before",
        str(header_before),
        "--header-rollback",
        str(header_rollback),
        "--header-forward",
        str(header_forward),
        "--smoke-before",
        str(smoke_before),
        "--smoke-rollback",
        str(smoke_rollback),
        "--smoke-forward",
        str(smoke_forward),
        "--output",
        str(output),
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    output_text = ((completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")).strip()
    payload = _load_json(output) if output.exists() else {}
    return completed.returncode, payload if isinstance(payload, dict) else {}, output_text


def _upsert_manifest(manifest_path: Path, *, artifacts: list[Path], ok: bool) -> None:
    payload = _load_json(manifest_path)
    checks = payload.get("checks")
    if not isinstance(checks, dict):
        checks = {}
        payload["checks"] = checks
    checks["rollback_drill"] = {
        "status": "PASS" if ok else "FAIL",
        "artifacts": [str(path) for path in artifacts],
    }
    _write_json(manifest_path, payload)


def _upsert_checklist_rollback_attachment(checklist_path: Path, attachment: Path) -> None:
    lines = checklist_path.read_text(encoding="utf-8").splitlines()
    updated: list[str] = []
    replaced = False
    for line in lines:
        if line.strip().lower().startswith("- rollback:"):
            if not replaced:
                updated.append(f"- Rollback: {attachment}")
                replaced = True
            continue
        updated.append(line)
    if not replaced:
        updated.append(f"- Rollback: {attachment}")
    checklist_path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")


def _failure_payload(
    *,
    release_id: str,
    commit_sha: str,
    environment: str,
    manifest_path: Path | None,
    base_url: str,
    issues: list[str],
    required: dict[str, str],
) -> dict:
    return {
        "success": False,
        "rollback_exercised": False,
        "generated_at": _utc_now(),
        "environment": environment,
        "release_id": release_id,
        "commit_sha": commit_sha,
        "evidence_manifest": str(manifest_path) if manifest_path is not None else "",
        "base_url": base_url,
        "required_artifacts": required,
        "issues": issues,
        "message": (
            "rollback_drill nao executado como ida/volta operacional; "
            "sao obrigatorios smokes antes/apos rollback/apos forward e headers A/B/A."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Integra rollback drill real A/B/A ao pacote release sem fabricar evidencia."
    )
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--manifest", default="")
    parser.add_argument("--regression-checklist", default="")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--header-before", default="")
    parser.add_argument("--header-rollback", default="")
    parser.add_argument("--header-forward", default="")
    parser.add_argument("--smoke-before", default="")
    parser.add_argument("--smoke-rollback", default="")
    parser.add_argument("--smoke-forward", default="")
    parser.add_argument("--metadata-output", default="")
    parser.add_argument("--attempt-output", default="")
    args = parser.parse_args()

    ops_root = Path(__file__).resolve().parents[2]
    repo_root = ops_root.parent
    windows_py = repo_root / ".venv" / "Scripts" / "python.exe"
    posix_py = repo_root / ".venv" / "bin" / "python"
    py_exec = str(windows_py if windows_py.exists() else posix_py if posix_py.exists() else Path(sys.executable))

    out_dir = Path(args.out_dir).expanduser()
    if not out_dir.is_absolute():
        raise SystemExit("--out-dir deve apontar para diretorio externo explicito.")
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = Path(args.manifest).expanduser().resolve() if (args.manifest or "").strip() else None
    checklist_path = Path(args.regression_checklist).expanduser().resolve() if (args.regression_checklist or "").strip() else None
    release_id, commit_sha, environment = _load_manifest_context(manifest_path)

    metadata_path = (
        Path(args.metadata_output).expanduser().resolve()
        if (args.metadata_output or "").strip()
        else (out_dir / "rollback_runtime_ids.json").resolve()
    )
    attempt_path = (
        Path(args.attempt_output).expanduser().resolve()
        if (args.attempt_output or "").strip()
        else (out_dir / "rollback_drill_attempt.json").resolve()
    )

    required = {
        "header_before": (args.header_before or "").strip(),
        "header_rollback": (args.header_rollback or "").strip(),
        "header_forward": (args.header_forward or "").strip(),
        "smoke_before": (args.smoke_before or "").strip(),
        "smoke_rollback": (args.smoke_rollback or "").strip(),
        "smoke_forward": (args.smoke_forward or "").strip(),
    }

    issues: list[str] = []
    header_before = _resolve_existing_path(args.header_before, label="header_before", issues=issues)
    header_rollback = _resolve_existing_path(args.header_rollback, label="header_rollback", issues=issues)
    header_forward = _resolve_existing_path(args.header_forward, label="header_forward", issues=issues)
    smoke_before_path = _resolve_existing_path(args.smoke_before, label="smoke_before", issues=issues)
    smoke_rollback_path = _resolve_existing_path(args.smoke_rollback, label="smoke_rollback", issues=issues)
    smoke_forward_path = _resolve_existing_path(args.smoke_forward, label="smoke_forward", issues=issues)

    smoke_before = _load_smoke(smoke_before_path, label="smoke_before", issues=issues)
    smoke_rollback = _load_smoke(smoke_rollback_path, label="smoke_rollback", issues=issues)
    smoke_forward = _load_smoke(smoke_forward_path, label="smoke_forward", issues=issues)

    if issues:
        payload = _failure_payload(
            release_id=release_id,
            commit_sha=commit_sha,
            environment=environment,
            manifest_path=manifest_path,
            base_url=(args.base_url or "").strip(),
            issues=issues,
            required=required,
        )
        _write_json(attempt_path, payload)
        if manifest_path is not None:
            _upsert_manifest(manifest_path, artifacts=[attempt_path], ok=False)
        if checklist_path is not None:
            _upsert_checklist_rollback_attachment(checklist_path, attempt_path)
        print(json.dumps({"success": False, "artifact": str(attempt_path), "issues": issues}, ensure_ascii=False, indent=2))
        return 1

    assert header_before is not None
    assert header_rollback is not None
    assert header_forward is not None
    assert smoke_before_path is not None
    assert smoke_rollback_path is not None
    assert smoke_forward_path is not None

    builder_script = ops_root / "scripts" / "release" / "build_rollback_metadata.py"
    returncode, metadata, builder_output = _run_metadata_builder(
        py_exec=py_exec,
        script=builder_script,
        header_before=header_before,
        header_rollback=header_rollback,
        header_forward=header_forward,
        smoke_before=smoke_before_path,
        smoke_rollback=smoke_rollback_path,
        smoke_forward=smoke_forward_path,
        output=metadata_path,
    )

    smoke_ok = all(not bool((payload or {}).get("failed")) for payload in (smoke_before, smoke_rollback, smoke_forward))
    ok = bool(smoke_ok and returncode == 0 and metadata.get("success"))
    summary = {
        "success": ok,
        "rollback_exercised": ok,
        "generated_at": _utc_now(),
        "environment": environment,
        "release_id": release_id,
        "commit_sha": commit_sha,
        "evidence_manifest": str(manifest_path) if manifest_path is not None else "",
        "base_url": (args.base_url or "").strip(),
        "metadata_artifact": str(metadata_path),
        "smoke_before": str(smoke_before_path),
        "smoke_rollback": str(smoke_rollback_path),
        "smoke_forward": str(smoke_forward_path),
        "runtime_metadata_success": bool(metadata.get("success")),
        "builder_exit_code": returncode,
        "builder_output_length": len(builder_output or ""),
    }
    _write_json(attempt_path, summary)

    manifest_artifacts = [smoke_before_path, smoke_rollback_path, smoke_forward_path, metadata_path]
    if manifest_path is not None:
        _upsert_manifest(manifest_path, artifacts=manifest_artifacts, ok=ok)
    if checklist_path is not None:
        _upsert_checklist_rollback_attachment(checklist_path, metadata_path if ok else attempt_path)

    print(
        json.dumps(
            {
                "success": ok,
                "rollback_exercised": ok,
                "artifacts": [str(path) for path in manifest_artifacts],
                "summary": str(attempt_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
