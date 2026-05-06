from __future__ import annotations

import argparse
import json
import logging
import os
import shlex
import subprocess
import sys
from pathlib import Path
from uuid import uuid4


def _required_env() -> tuple[bool, list[str]]:
    required = (
        "DATABASE_URL",
        "E2E_DATABASE_URL",
        "E2E_LOGIN",
        "E2E_PASSWORD",
        "RELEASE_EVIDENCE_SIGNING_KEY",
    )
    missing = [name for name in required if not (os.getenv(name, "") or "").strip()]
    return len(missing) == 0, missing


def _configure_release_logger(repo_root: Path) -> logging.Logger:
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    try:
        from backend.src.controle_treinamentos.core.logging import configure_cli_logger

        return configure_cli_logger("controle_treinamentos.release")
    except Exception:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
        return logging.getLogger("controle_treinamentos.release")


def _load_release_context(manifest: Path) -> tuple[str, str]:
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception:
        return "", ""
    if not isinstance(payload, dict):
        return "", ""
    release_id = str(payload.get("release_id", "") or "").strip()
    environment = str(payload.get("environment", "") or "").strip().lower()
    return release_id, environment


def main() -> int:
    parser = argparse.ArgumentParser(description="Executa gate oficial de release em perfil strict.")
    parser.add_argument("--base-url", required=True, help="URL alvo para smoke pós-deploy.")
    parser.add_argument("--evidence-manifest", required=True, help="Manifest JSON de evidências.")
    parser.add_argument(
        "--regression-checklist",
        required=True,
        help="Checklist de regressao preenchido da release.",
    )
    parser.add_argument("--evidence-max-age-hours", type=int, default=24)
    parser.add_argument("--metrics-token-file", default="", help="Arquivo com token para smoke de métricas.")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    logger = _configure_release_logger(repo_root)
    gate = repo_root / "ops" / "scripts" / "release" / "release_gate.py"
    windows_py = repo_root / ".venv" / "Scripts" / "python.exe"
    posix_py = repo_root / ".venv" / "bin" / "python"
    py_exec = str(windows_py if windows_py.exists() else posix_py if posix_py.exists() else Path(sys.executable))

    manifest = Path(args.evidence_manifest).expanduser()
    if not manifest.is_absolute():
        manifest = (repo_root / manifest).resolve()
    release_id, release_environment = _load_release_context(manifest)
    correlation_id = (
        (os.getenv("CONTROL_TREINAMENTOS_CORRELATION_ID", "") or "").strip()
        or (os.getenv("RELEASE_CORRELATION_ID", "") or "").strip()
        or release_id
        or f"release:{uuid4().hex}"
    )

    env_ok, missing = _required_env()
    logger.info(
        "Strict release gate command started.",
        extra={
            "event": "release_gate_start",
            "component": "run_release_strict",
            "correlation_id": correlation_id,
            "release_id": release_id,
            "release_environment": release_environment,
            "base_url": (args.base_url or "").strip(),
            "evidence_manifest": str(manifest),
            "regression_checklist": args.regression_checklist,
            "evidence_max_age_hours": max(1, int(args.evidence_max_age_hours)),
            "metrics_token_file_configured": bool((args.metrics_token_file or "").strip()),
        },
    )
    if not env_ok:
        logger.error(
            "Strict release gate blocked by missing required environment.",
            extra={
                "event": "release_gate_blocked",
                "component": "run_release_strict",
                "correlation_id": correlation_id,
                "release_id": release_id,
                "reason": "missing_required_env",
                "missing_env": missing,
            },
        )
        print(f"FAIL: variáveis obrigatórias ausentes: {', '.join(missing)}")
        return 1

    if not manifest.exists():
        logger.error(
            "Strict release gate blocked by missing evidence manifest.",
            extra={
                "event": "release_gate_blocked",
                "component": "run_release_strict",
                "correlation_id": correlation_id,
                "release_id": release_id,
                "reason": "missing_evidence_manifest",
                "evidence_manifest": str(manifest),
            },
        )
        print(f"FAIL: evidence manifest não encontrado: {manifest}")
        return 1

    checklist = Path(args.regression_checklist).expanduser()
    if not checklist.is_absolute():
        checklist = (repo_root / checklist).resolve()
    if not checklist.exists():
        logger.error(
            "Strict release gate blocked by missing regression checklist.",
            extra={
                "event": "release_gate_blocked",
                "component": "run_release_strict",
                "correlation_id": correlation_id,
                "release_id": release_id,
                "reason": "missing_regression_checklist",
                "regression_checklist": str(checklist),
            },
        )
        print(f"FAIL: regression checklist não encontrado: {checklist}")
        return 1

    cmd = [
        py_exec,
        str(gate),
        "--gate-profile",
        "strict",
        "--base-url",
        (args.base_url or "").strip(),
        "--evidence-manifest",
        str(manifest),
        "--evidence-max-age-hours",
        str(max(1, int(args.evidence_max_age_hours))),
        "--regression-checklist",
        str(checklist),
    ]
    if (args.metrics_token_file or "").strip():
        cmd.extend(["--metrics-token-file", args.metrics_token_file.strip()])

    print("$", " ".join(shlex.quote(part) for part in cmd))
    env = os.environ.copy()
    env["CONTROL_TREINAMENTOS_RELEASE_GATE_INTERNAL"] = "1"
    env["CONTROL_TREINAMENTOS_CORRELATION_ID"] = correlation_id
    if release_id:
        env["CONTROL_TREINAMENTOS_RELEASE_ID"] = release_id
    result = subprocess.run(cmd, cwd=str(repo_root), env=env)
    log_payload = {
        "event": "release_gate_complete",
        "component": "run_release_strict",
        "correlation_id": correlation_id,
        "release_id": release_id,
        "release_environment": release_environment,
        "exit_code": result.returncode,
        "base_url": (args.base_url or "").strip(),
        "evidence_manifest": str(manifest),
        "regression_checklist": str(checklist),
    }
    if result.returncode == 0:
        logger.info("Strict release gate command completed.", extra=log_payload)
    else:
        logger.error("Strict release gate command failed.", extra=log_payload)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
