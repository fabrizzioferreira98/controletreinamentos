from __future__ import annotations

import argparse
import json
import os
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


def _extract_json_object(text: str) -> dict:
    decoder = json.JSONDecoder()
    raw = text or ""
    index = raw.find("{")
    while index != -1:
        try:
            payload, _end = decoder.raw_decode(raw[index:])
        except json.JSONDecodeError:
            index = raw.find("{", index + 1)
            continue
        if isinstance(payload, dict):
            return payload
        index = raw.find("{", index + 1)
    raise RuntimeError("Drill de alerta externo nao produziu JSON consumivel.")


def _sanitized_command(parts: list[str]) -> str:
    sanitized: list[str] = []
    skip_next = False
    secret_flags = {"--webhook-url"}
    for part in parts:
        if skip_next:
            sanitized.append("<redacted>")
            skip_next = False
            continue
        sanitized.append(part)
        if part in secret_flags:
            skip_next = True
    return " ".join(shlex.quote(item) for item in sanitized)


def _upsert_manifest(manifest_path: Path, *, artifact: Path, ok: bool) -> None:
    payload = _load_json(manifest_path)
    checks = payload.get("checks")
    if not isinstance(checks, dict):
        checks = {}
        payload["checks"] = checks
    checks["alerts_external_e2e"] = {
        "status": "PASS" if ok else "FAIL",
        "artifacts": [str(artifact)],
    }
    _write_json(manifest_path, payload)


def _upsert_checklist_alert_attachment(checklist_path: Path, attachment: Path) -> None:
    lines = checklist_path.read_text(encoding="utf-8").splitlines()
    updated: list[str] = []
    replaced = False
    for line in lines:
        if line.strip().lower().startswith("- alertas externos:"):
            if not replaced:
                updated.append(f"- Alertas externos: {attachment}")
                replaced = True
            continue
        updated.append(line)
    if not replaced:
        updated.append(f"- Alertas externos: {attachment}")
    checklist_path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")


def _run_drill(py_exec: str, script: Path, cmd_args: list[str]) -> tuple[int, dict, str, str, str]:
    cmd = [py_exec, str(script), *cmd_args]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    output = ((completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")).strip()
    payload = _extract_json_object(output)
    return completed.returncode, payload, completed.stdout or "", completed.stderr or "", _sanitized_command(cmd)


def main() -> int:
    parser = argparse.ArgumentParser(description="Executa alerta externo real e integra a evidencia ao pacote release.")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--output", default="")
    parser.add_argument("--manifest", default="")
    parser.add_argument("--regression-checklist", default="")
    parser.add_argument("--webhook-url", default="")
    parser.add_argument("--webhook-url-file", default="")
    parser.add_argument("--webhook-url-env", default="ALERTS_TEST_WEBHOOK_URL")
    parser.add_argument("--delivery-capture-file", default="")
    parser.add_argument("--source", default="release-gate")
    parser.add_argument("--severity", default="warning")
    parser.add_argument("--message", default="Teste controlado de alerta externo para validacao de release.")
    parser.add_argument("--acknowledged-by", required=True)
    parser.add_argument("--escalation-target", required=True)
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()

    ops_root = Path(__file__).resolve().parents[2]
    repo_root = ops_root.parent
    windows_py = repo_root / ".venv" / "Scripts" / "python.exe"
    posix_py = repo_root / ".venv" / "bin" / "python"
    py_exec = str(windows_py if windows_py.exists() else posix_py if posix_py.exists() else Path(sys.executable))
    drill_script = ops_root / "scripts" / "release" / "alerts_external_drill.py"

    out_dir = Path(args.out_dir).expanduser()
    if not out_dir.is_absolute():
        raise SystemExit("--out-dir deve apontar para diretorio externo explicito.")
    out_dir = out_dir.resolve()
    output_path = Path(args.output).expanduser() if (args.output or "").strip() else out_dir / "alerts_external_drill.json"
    if not output_path.is_absolute():
        raise SystemExit("--output deve apontar para caminho externo explicito.")
    output_path = output_path.resolve()

    manifest_path = Path(args.manifest).expanduser().resolve() if (args.manifest or "").strip() else None
    checklist_path = Path(args.regression_checklist).expanduser().resolve() if (args.regression_checklist or "").strip() else None
    release_id, commit_sha, environment = _load_manifest_context(manifest_path)

    drill_args = [
        "--source",
        (args.source or "").strip() or "release-gate",
        "--severity",
        (args.severity or "").strip() or "warning",
        "--message",
        (args.message or "").strip() or "Teste controlado de alerta externo para validacao de release.",
        "--acknowledged-by",
        (args.acknowledged_by or "").strip(),
        "--escalation-target",
        (args.escalation_target or "").strip(),
        "--require-ack",
        "--timeout",
        str(max(3, int(args.timeout))),
    ]
    if (args.webhook_url or "").strip():
        drill_args.extend(["--webhook-url", args.webhook_url.strip()])
    if (args.webhook_url_file or "").strip():
        drill_args.extend(["--webhook-url-file", args.webhook_url_file.strip()])
    if (args.webhook_url_env or "").strip():
        drill_args.extend(["--webhook-url-env", args.webhook_url_env.strip()])

    returncode, drill_payload, stdout, stderr, sanitized_command = _run_drill(py_exec, drill_script, drill_args)
    delivery_capture = None
    if (args.delivery_capture_file or "").strip():
        capture_path = Path(args.delivery_capture_file).expanduser().resolve()
        if capture_path.exists():
            delivery_capture = _load_json(capture_path)
        else:
            delivery_capture = {"received": False, "capture_file": str(capture_path)}
    ok = bool(drill_payload.get("success")) and returncode == 0
    capture_received = True
    if delivery_capture is not None:
        captured_payload = delivery_capture.get("payload") if isinstance(delivery_capture.get("payload"), dict) else {}
        capture_received = bool(delivery_capture.get("received")) and captured_payload.get("event") == "release_alert_drill"
    payload = {
        **drill_payload,
        "generated_at": _utc_now(),
        "environment": environment,
        "release_id": release_id,
        "commit_sha": commit_sha,
        "evidence_manifest": str(manifest_path) if manifest_path is not None else "",
        "drill_command": sanitized_command,
        "external_delivery_exercised": bool(
            ok
            and 200 <= int(drill_payload.get("status", 0) or 0) <= 299
            and bool(drill_payload.get("acknowledged"))
            and capture_received
        ),
        "external_delivery_evidence": delivery_capture,
        "stdout_length": len(stdout or ""),
        "stderr_length": len(stderr or ""),
    }
    _write_json(output_path, payload)

    if manifest_path is not None:
        _upsert_manifest(manifest_path, artifact=output_path, ok=ok)
    if checklist_path is not None:
        _upsert_checklist_alert_attachment(checklist_path, output_path)

    print(
        json.dumps(
            {
                "success": ok,
                "artifact": str(output_path),
                "status": payload.get("status"),
                "acknowledged": bool(payload.get("acknowledged")),
                "external_delivery_exercised": bool(payload.get("external_delivery_exercised")),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
