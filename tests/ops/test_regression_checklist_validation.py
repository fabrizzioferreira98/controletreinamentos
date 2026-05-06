from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _validator_script() -> str:
    root = Path(__file__).resolve().parents[2]
    return str(root / "ops" / "scripts" / "release" / "validate_regression_checklist.py")


def _git_head(root: Path) -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(root), text=True).strip()
    except Exception:
        return "workspace-without-git"


def _build_checklist(tmp_path: Path, *, checked: bool = True) -> tuple[Path, Path]:
    root = Path(__file__).resolve().parents[2]
    manifest = tmp_path / "release_manifest.json"
    manifest.write_text(json.dumps({"ok": True}), encoding="utf-8")
    state = "x" if checked else " "
    content = f"""# Auditoria de Regressao por Release

## Metadados
- Release ID: release_test_001
- Commit SHA: {_git_head(root)}
- Ambiente: homolog
- Responsavel tecnico: qa-release
- Data/hora: 2026-03-29T23:00:00Z

## Checklist obrigatorio (PASS/FAIL)
- [{state}] Contrato HTTP validado.
- [{state}] Carga autenticada validada dentro do SLO.

## Evidencias anexadas
- Paridade minima entre ambientes: C:/tmp/release_test_001/parity/report.json
- Gate final strict: C:/tmp/release_test_001/gate/run_release_strict.log
- Checklist de release: C:/tmp/release_test_001/release/release_execution_checklist.md
- Checklist de rollback: C:/tmp/release_test_001/rollback/rollback_checklist.md
- E2E: C:/tmp/release_test_001/e2e/report.json
- Carga autenticada: C:/tmp/release_test_001/load/report.json
- Jobs concorrentes: C:/tmp/release_test_001/jobs/report.json
- Scheduler/cron ou declaracao de escopo: C:/tmp/release_test_001/scheduler/report.json
- Storage/PDF/upload-download: C:/tmp/release_test_001/storage/report.json
- Alertas externos: C:/tmp/release_test_001/alerts/report.json
- Backup/restore: C:/tmp/release_test_001/backup/report.json
- Rollback: C:/tmp/release_test_001/rollback/report.json
- Smoke: C:/tmp/release_test_001/smoke/report.json
- Smoke pos-release: C:/tmp/release_test_001/smoke/post_release_smoke.json
- Manifest de evidencias: {manifest}

## Decisao
- Resultado: GO
- Justificativa: ok
- Riscos residuais: baixos
"""
    checklist = tmp_path / "checklist.md"
    checklist.write_text(content, encoding="utf-8")
    return checklist, manifest


def test_validate_regression_checklist_passes(tmp_path):
    checklist, _manifest = _build_checklist(tmp_path, checked=True)
    result = subprocess.run(
        [sys.executable, _validator_script(), "--checklist", str(checklist), "--expected-release-id", "release_test_001"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    payload = json.loads(result.stdout)
    assert payload["success"] is True


def test_validate_regression_checklist_fails_when_item_unchecked(tmp_path):
    checklist, _manifest = _build_checklist(tmp_path, checked=False)
    result = subprocess.run(
        [sys.executable, _validator_script(), "--checklist", str(checklist), "--expected-release-id", "release_test_001"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["success"] is False
    assert any(issue.startswith("checklist_item_unchecked:") for issue in payload["issues"])


def test_validate_regression_checklist_fails_when_release_id_mismatch(tmp_path):
    checklist, _manifest = _build_checklist(tmp_path, checked=True)
    result = subprocess.run(
        [sys.executable, _validator_script(), "--checklist", str(checklist), "--expected-release-id", "release_other"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["success"] is False
    assert any(issue.startswith("release_id_mismatch:") for issue in payload["issues"])


def test_validate_regression_checklist_fails_when_evidence_points_to_other_release(tmp_path):
    checklist, _manifest = _build_checklist(tmp_path, checked=True)
    text = checklist.read_text(encoding="utf-8")
    text = text.replace(
        "- E2E: C:/tmp/release_test_001/e2e/report.json",
        "- E2E: C:/tmp/release_old/e2e/report.json",
    )
    checklist.write_text(text, encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            _validator_script(),
            "--checklist",
            str(checklist),
            "--expected-release-id",
            "release_test_001",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["success"] is False
    assert any(issue.startswith("evidence_release_id_mismatch:E2E:") for issue in payload["issues"])
