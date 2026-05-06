from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
from pathlib import Path


CRITICAL_UI_FILES = (
    "backend/src/controle_treinamentos/templates/base.html",
    "backend/src/controle_treinamentos/templates/login.html",
    "backend/src/controle_treinamentos/templates/dashboard.html",
    "backend/src/controle_treinamentos/templates/tripulantes_list.html",
    "backend/src/controle_treinamentos/templates/bases/index.html",
    "backend/src/controle_treinamentos/static/styles.css",
)

SEMANTIC_UI_GUARDS = (
    "test_frontend_build_script_resolves_current_paths",
    "test_frontend_api_feedback_and_error_guards_are_present",
    "test_spa_session_and_logout_contracts_do_not_depend_on_html_flows",
    "test_spa_route_render_failures_leave_navigable_error_state",
    "test_login_flow_has_inline_feedback_busy_state_and_destination_guard",
    "test_dashboard_uses_partial_error_adapters_instead_of_single_promise_all",
    "test_active_frontend_pages_do_not_use_destructive_reload_or_native_confirm",
    "test_training_program_has_narrow_adapters_and_hash_filter_source_of_truth",
    "test_tripulantes_flow_has_contract_adapters_and_inline_recovery",
    "test_critical_frontend_forms_keep_validation_busy_and_error_feedback",
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


def _format_issue(exc: BaseException) -> str:
    rendered = " ".join(str(exc).strip().split())
    return rendered[:240] if rendered else type(exc).__name__


def _semantic_guard_results(root: Path) -> tuple[int, list[str]]:
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    try:
        module = importlib.import_module("tests.contract.test_frontend_ux_functional_guards")
    except Exception as exc:
        return 0, [f"semantic_guard_import_error:{type(exc).__name__}:{_format_issue(exc)}"]

    passed = 0
    issues: list[str] = []
    for guard_name in SEMANTIC_UI_GUARDS:
        guard = getattr(module, guard_name, None)
        if not callable(guard):
            issues.append(f"semantic_guard_missing:{guard_name}")
            continue
        try:
            guard()
            passed += 1
        except AssertionError as exc:
            issues.append(f"semantic_guard_failed:{guard_name}:{_format_issue(exc)}")
        except Exception as exc:
            issues.append(f"semantic_guard_error:{guard_name}:{type(exc).__name__}:{_format_issue(exc)}")
    return passed, issues


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Valida baseline de UI por hash dos arquivos criticos e por guardas semanticos "
            "de comportamento frontend."
        )
    )
    parser.add_argument(
        "--baseline",
        default="docs/operations/ui_baseline_hashes.json",
        help="Arquivo baseline de hashes UI.",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Atualiza baseline para os hashes atuais (use conscientemente em mudancas visuais intencionais).",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[3]
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

    semantic_passed, semantic_issues = _semantic_guard_results(root)
    issues.extend(semantic_issues)

    print(
        json.dumps(
            {
                "success": not issues,
                "baseline": str(baseline_path),
                "checked_files": len(current),
                "semantic_guards_total": len(SEMANTIC_UI_GUARDS),
                "semantic_guards_passed": semantic_passed,
                "issues": issues,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
