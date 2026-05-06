from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


CRITICAL_UI_FILES = (
    "backend/src/controle_treinamentos/templates/base.html",
    "backend/src/controle_treinamentos/templates/login.html",
    "backend/src/controle_treinamentos/templates/dashboard.html",
    "backend/src/controle_treinamentos/templates/tripulantes_list.html",
    "backend/src/controle_treinamentos/templates/bases/index.html",
    "backend/src/controle_treinamentos/static/styles.css",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _current_hashes(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for rel in CRITICAL_UI_FILES:
        file_path = (root / rel).resolve()
        if not file_path.exists():
            raise FileNotFoundError(f"ui_file_missing:{rel}")
        result[rel] = _sha256(file_path)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Valida baseline de regressão visual por hash de arquivos UI críticos.")
    parser.add_argument(
        "--baseline",
        default="docs/operations/ui_baseline_hashes.json",
        help="Arquivo baseline de hashes UI.",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Atualiza baseline para os hashes atuais (use conscientemente em mudanças visuais intencionais).",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    baseline_path = Path(args.baseline).expanduser()
    if not baseline_path.is_absolute():
        baseline_path = (root / baseline_path).resolve()

    current = _current_hashes(root)

    if args.update_baseline or not baseline_path.exists():
        payload = {
            "version": 1,
            "files": current,
        }
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"success": True, "updated": True, "baseline": str(baseline_path)}, ensure_ascii=False))
        return 0

    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    expected = baseline.get("files", {}) if isinstance(baseline, dict) else {}
    if not isinstance(expected, dict):
        print(json.dumps({"success": False, "issues": ["baseline_invalid_format"]}, ensure_ascii=False, indent=2))
        return 1

    issues: list[str] = []
    for rel, digest in current.items():
        expected_digest = str(expected.get(rel, "") or "").strip().lower()
        if not expected_digest:
            issues.append(f"baseline_missing:{rel}")
            continue
        if digest != expected_digest:
            issues.append(f"ui_regression_hash_mismatch:{rel}")

    for rel in expected.keys():
        if rel not in current:
            issues.append(f"baseline_extra_entry:{rel}")

    print(
        json.dumps(
            {
                "success": not issues,
                "baseline": str(baseline_path),
                "checked_files": len(current),
                "issues": issues,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
