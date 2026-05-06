from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


PASSED_RE = re.compile(r"(?P<count>\d+)\s+passed")


def _extract_passed_count(output: str) -> int:
    match = PASSED_RE.search(output or "")
    if not match:
        return 0
    try:
        return int(match.group("count"))
    except ValueError:
        return 0


def _run_round(py: str, out_log: Path) -> tuple[bool, int]:
    cmd = [py, "-m", "pytest", "-q", "-m", "e2e", "-rs"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    merged = ((result.stdout or "") + ("\n" + result.stderr if result.stderr else "")).strip()
    out_log.write_text((merged + "\n") if merged else "", encoding="utf-8")
    return result.returncode == 0, _extract_passed_count(merged)


def main() -> int:
    parser = argparse.ArgumentParser(description="Executa E2E de homologação em múltiplas rodadas com artefatos.")
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--min-passed", type=int, default=4)
    parser.add_argument("--out-dir", required=True, help="Diretorio externo para gravar os logs E2E.")
    parser.add_argument(
        "--summary-json",
        default="",
        help="Caminho externo do summary JSON. Se omitido, sera criado dentro de --out-dir.",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    py = str(root / ".venv" / "bin" / "python")
    if not Path(py).exists():
        py = sys.executable

    rounds = max(1, int(args.rounds))
    min_passed = max(1, int(args.min_passed))
    out_dir = Path(args.out_dir).expanduser()
    if not out_dir.is_absolute():
        raise SystemExit("--out-dir deve apontar para um diretorio externo explicito.")
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    ok = True
    for idx in range(1, rounds + 1):
        out_log = out_dir / f"e2e_round{idx}.log"
        round_ok, passed = _run_round(py, out_log)
        round_pass = round_ok and passed >= min_passed
        rows.append(
            {
                "round": idx,
                "ok": round_ok,
                "passed": passed,
                "required_min_passed": min_passed,
                "pass": round_pass,
                "artifact": str(out_log),
            }
        )
        if not round_pass:
            ok = False

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
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

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
