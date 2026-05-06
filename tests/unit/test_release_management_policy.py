from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_release_management_docs_are_indexed() -> None:
    operations_index = _read("docs/operations/README.md")
    docs_index = _read("docs/README.md")

    for expected in (
        "RELEASE_MANAGEMENT.md",
        "RELEASE_EXECUTION_CHECKLIST.md",
        "ROLLBACK_CHECKLIST.md",
        "POST_RELEASE_VALIDATION.md",
    ):
        assert expected in operations_index
        assert expected in docs_index


def test_release_management_doc_closes_manual_truth() -> None:
    content = _read("docs/operations/RELEASE_MANAGEMENT.md")

    assert "run_ci_validation_minimal.py" in content
    assert "run_release_strict.py" in content
    assert "Invoke-AppService.ps1" in content
    assert "post_deploy_smoke.py" in content
    assert "ROLLBACK_CHECKLIST.md" in content
    assert "RELEASE_EXECUTION_CHECKLIST.md" in content
    assert "deploy oficial" in content.lower()
    assert "rollback oficial nao pode depender de memoria" in content.lower()


def test_regression_audit_mentions_release_checklists_and_gate() -> None:
    checklist = _read("docs/operations/REGRESSION_AUDIT_CHECKLIST.md")

    for expected in (
        "Checklist de release",
        "Checklist de rollback",
        "Gate final strict",
        "Smoke pos-release",
    ):
        assert expected in checklist


def test_regression_checklist_validator_requires_new_evidence_keys() -> None:
    validator = _read("ops/scripts/release/validate_regression_checklist.py")

    for expected in (
        "REQUIRED_EVIDENCE_ATTACHMENT_KEYS",
        "Checklist de release",
        "Checklist de rollback",
        "Gate final strict",
        "Smoke pos-release",
        "parents[3]",
    ):
        assert expected in validator
