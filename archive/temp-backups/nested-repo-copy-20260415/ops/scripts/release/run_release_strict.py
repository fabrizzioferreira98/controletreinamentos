from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Executa gate oficial de release em perfil strict.")
    parser.add_argument("--base-url", required=True, help="URL alvo para smoke pós-deploy.")
    parser.add_argument("--evidence-manifest", required=True, help="Manifest JSON de evidências.")
    parser.add_argument(
        "--regression-checklist",
        default=str(Path("docs") / "operations" / "REGRESSION_AUDIT_CHECKLIST.md"),
        help="Checklist de regressão obrigatório.",
    )
    parser.add_argument("--evidence-max-age-hours", type=int, default=24)
    parser.add_argument("--metrics-token-file", default="", help="Arquivo com token para smoke de métricas.")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    gate = root / "scripts" / "release" / "release_gate.py"
    py = root / ".venv" / "bin" / "python"
    py_exec = str(py if py.exists() else Path(sys.executable))

    env_ok, missing = _required_env()
    if not env_ok:
        print(f"FAIL: variáveis obrigatórias ausentes: {', '.join(missing)}")
        return 1

    manifest = Path(args.evidence_manifest).expanduser()
    if not manifest.is_absolute():
        manifest = (root / manifest).resolve()
    if not manifest.exists():
        print(f"FAIL: evidence manifest não encontrado: {manifest}")
        return 1

    checklist = Path(args.regression_checklist).expanduser()
    if not checklist.is_absolute():
        checklist = (root / checklist).resolve()
    if not checklist.exists():
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
    result = subprocess.run(cmd, cwd=str(root))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())

