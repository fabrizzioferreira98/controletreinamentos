from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


PASSED_RE = re.compile(r"(?P<count>\d+)\s+passed")
CHECKLIST_E2E_RE = re.compile(r"^[ \t]*-[ \t]*E2E:[ \t]*.*$", re.IGNORECASE)


def _extract_passed_count(text: str) -> int:
    match = PASSED_RE.search(text or "")
    if not match:
        return 0
    try:
        return int(match.group("count"))
    except ValueError:
        return 0


def _render_round_log(payload: dict) -> str:
    lines = [
        f"runtime=homolog",
        f"base_url={payload.get('base_url', '')}",
        f"round={payload.get('round_index', '')}",
        f"started_at={payload.get('started_at', '')}",
        f"finished_at={payload.get('finished_at', '')}",
        f"login={payload.get('login', '')}",
        "",
    ]
    for step in payload.get("steps", []):
        if not isinstance(step, dict):
            continue
        status = "PASS" if bool(step.get("ok")) else "FAIL"
        lines.append(
            f"[{status}] {step.get('name', '')} ({int(step.get('duration_ms', 0) or 0)} ms) - {step.get('detail', '')}"
        )
    lines.append("")
    lines.append(f"{int(payload.get('passed_steps', 0) or 0)} passed in 0.00s")
    return "\n".join(lines).strip() + "\n"


def _run_round(py: str, script: Path, *, base_url: str, round_index: int, login: str, password: str) -> tuple[bool, dict]:
    cmd = [py, str(script), "--base-url", base_url, "--round-index", str(round_index)]
    if login:
        cmd.extend(["--login", login])
    if password:
        cmd.extend(["--password", password])
    result = subprocess.run(cmd, capture_output=True, text=True)
    merged = ((result.stdout or "") + ("\n" + result.stderr if result.stderr else "")).strip()
    if not merged:
        raise RuntimeError(f"E2E homolog round sem saida. round={round_index}")
    try:
        payload = json.loads(merged)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"E2E homolog round gerou saida invalida. round={round_index} snippet={merged[:280]!r}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"E2E homolog round gerou payload invalido. round={round_index}")
    return result.returncode == 0 and bool(payload.get("success")), payload


def _upsert_manifest(manifest_path: Path, artifacts: list[str]) -> None:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    checks = payload.get("checks")
    if not isinstance(checks, dict):
        checks = {}
        payload["checks"] = checks
    checks["e2e_homolog"] = {"status": "PASS", "artifacts": artifacts}
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _upsert_checklist_e2e_attachment(checklist_path: Path, attachment: str) -> None:
    lines = checklist_path.read_text(encoding="utf-8").splitlines()
    updated_lines: list[str] = []
    replaced = False

    for line in lines:
        if CHECKLIST_E2E_RE.match(line):
            if not replaced:
                updated_lines.append(f"- E2E: {attachment}")
                replaced = True
            continue
        updated_lines.append(line)

    if not replaced:
        updated_lines.append(f"- E2E: {attachment}")

    checklist_path.write_text("\n".join(updated_lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Executa E2E real de homologacao em multiplas rodadas com artefatos.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--min-passed", type=int, default=4)
    parser.add_argument("--out-dir", required=True, help="Diretorio externo para gravar logs e summary.")
    parser.add_argument("--summary-json", default="", help="Caminho externo para o summary JSON.")
    parser.add_argument("--manifest", default="", help="Manifest do pacote release para atualizar o check e2e_homolog.")
    parser.add_argument(
        "--regression-checklist",
        default="",
        help="Checklist de regressao preenchido para atualizar o anexo E2E.",
    )
    parser.add_argument("--login", default="")
    parser.add_argument("--password", default="")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "release" / "run_e2e_homolog_live.py"
    windows_py = root.parent / ".venv" / "Scripts" / "python.exe"
    posix_py = root.parent / ".venv" / "bin" / "python"
    py = str(windows_py if windows_py.exists() else posix_py if posix_py.exists() else Path(sys.executable))

    out_dir = Path(args.out_dir).expanduser()
    if not out_dir.is_absolute():
        raise SystemExit("--out-dir deve apontar para um diretorio externo explicito.")
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    rounds = max(1, int(args.rounds))
    min_passed = max(1, int(args.min_passed))
    rows: list[dict] = []
    log_artifacts: list[str] = []
    ok = True

    for round_index in range(1, rounds + 1):
        round_ok, payload = _run_round(
            py,
            script,
            base_url=(args.base_url or "").strip(),
            round_index=round_index,
            login=(args.login or "").strip(),
            password=(args.password or "").strip(),
        )
        log_path = (out_dir / f"e2e_run_{round_index}.txt").resolve()
        log_path.write_text(_render_round_log(payload), encoding="utf-8")
        passed_steps = int(payload.get("passed_steps", 0) or 0)
        round_pass = round_ok and passed_steps >= min_passed
        log_artifacts.append(str(log_path))
        rows.append(
            {
                "round": round_index,
                "ok": round_ok,
                "passed": passed_steps,
                "required_min_passed": min_passed,
                "pass": round_pass,
                "artifact": str(log_path),
                "result": payload,
            }
        )
        if not round_pass:
            ok = False

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": "homolog",
        "base_url": (args.base_url or "").strip(),
        "rounds": rounds,
        "min_passed": min_passed,
        "success": ok,
        "results": rows,
    }

    summary_path = Path(args.summary_json).expanduser() if args.summary_json else (out_dir / "e2e_homolog_summary.json")
    if not summary_path.is_absolute():
        raise SystemExit("--summary-json deve apontar para um caminho externo explicito.")
    summary_path = summary_path.resolve()
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest_path = Path(args.manifest).expanduser().resolve() if (args.manifest or "").strip() else None
    if manifest_path is not None:
        _upsert_manifest(manifest_path, [*log_artifacts, str(summary_path)])

    checklist_path = Path(args.regression_checklist).expanduser().resolve() if (args.regression_checklist or "").strip() else None
    if checklist_path is not None:
        _upsert_checklist_e2e_attachment(checklist_path, log_artifacts[0])

    print(
        json.dumps(
            {
                "success": ok,
                "rounds": rounds,
                "min_passed": min_passed,
                "artifacts": [*log_artifacts, str(summary_path)],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
