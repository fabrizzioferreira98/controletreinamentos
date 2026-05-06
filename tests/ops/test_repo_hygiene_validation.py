from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _validator_script() -> str:
    root = Path(__file__).resolve().parents[2]
    return str(root / "ops" / "scripts" / "repo" / "validate_repo_hygiene.py")


def _run_validator(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, _validator_script(), "--root", str(root)],
        capture_output=True,
        text=True,
    )


def test_repo_hygiene_flags_forbidden_material_and_allows_templates(tmp_path: Path):
    (tmp_path / ".tmp").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".tmp" / "snapshot.txt").write_text("backup", encoding="utf-8")
    (tmp_path / "backend" / "runtime" / "instance").mkdir(parents=True, exist_ok=True)
    (tmp_path / "backend" / "src" / "__pycache__" / "app.cpython-311.pyc").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "backend" / "src" / "__pycache__" / "app.cpython-311.pyc").write_bytes(b"pyc")
    (tmp_path / "ops" / "windows" / "env" / "prod.env").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "ops" / "windows" / "env" / "prod.env").write_text("SECRET_KEY=real", encoding="utf-8")
    (tmp_path / "ops" / "windows" / "env" / "prod.env.example").write_text("SECRET_KEY=template", encoding="utf-8")

    result = _run_validator(tmp_path)
    assert result.returncode == 1, result.stdout + "\n" + result.stderr
    payload = json.loads(result.stdout)
    assert payload["success"] is False

    paths = {item["path"] for item in payload["violations"]}
    assert ".tmp" in paths
    assert "backend/runtime" in paths
    assert "backend/src/__pycache__" in paths
    assert "ops/windows/env/prod.env" in paths
    assert "ops/windows/env/prod.env.example" not in paths


def test_repo_hygiene_allows_documented_local_workspace_exceptions(tmp_path: Path):
    (tmp_path / ".env").write_text("SECRET_KEY=local-only", encoding="utf-8")
    (tmp_path / ".venv" / "pyvenv.cfg").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".venv" / "pyvenv.cfg").write_text("home = C:/Python", encoding="utf-8")
    (tmp_path / ".venv" / "Lib" / "site-packages" / "__pycache__" / "pkg.cpython-311.pyc").parent.mkdir(
        parents=True, exist_ok=True
    )
    (tmp_path / ".venv" / "Lib" / "site-packages" / "__pycache__" / "pkg.cpython-311.pyc").write_bytes(b"pyc")
    (tmp_path / "frontend" / "dist" / "index.html").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "frontend" / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "frontend" / "dist" / "config.js").write_text("window.APP_CONFIG = {}", encoding="utf-8")
    (tmp_path / "runtime" / "evidence" / "smoke.json").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "runtime" / "evidence" / "smoke.json").write_text("{}", encoding="utf-8")
    (tmp_path / "ops" / "artifacts" / "financeiro" / "smoke.json").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "ops" / "artifacts" / "financeiro" / "smoke.json").write_text("{}", encoding="utf-8")
    artifact_script = tmp_path / "ops" / "scripts" / "database" / "collect_financeiro_artifact.py"
    artifact_script.parent.mkdir(parents=True, exist_ok=True)
    artifact_script.write_text("OUTPUT = 'ops/artifacts/financeiro/smoke.json'\n", encoding="utf-8")

    result = _run_validator(tmp_path)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    payload = json.loads(result.stdout)
    assert payload["success"] is True


def test_repo_hygiene_flags_repo_local_evidence_references_in_current_docs(tmp_path: Path):
    checklist = tmp_path / "docs" / "operations" / "RUNBOOK.md"
    checklist.parent.mkdir(parents=True, exist_ok=True)
    checklist.write_text(
        "Manifest de evidencias: ops/evidence/release_20260410/release_manifest.json\n",
        encoding="utf-8",
    )

    result = _run_validator(tmp_path)
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert any(
        item["kind"] == "forbidden_content_reference" and item["path"] == "docs/operations/RUNBOOK.md"
        for item in payload["violations"]
    )


def test_repo_hygiene_passes_when_only_canonical_templates_and_external_paths_exist(tmp_path: Path):
    evidence_template = tmp_path / "docs" / "operations" / "RELEASE_EVIDENCE_TEMPLATE.json"
    evidence_template.parent.mkdir(parents=True, exist_ok=True)
    evidence_template.write_text(
        json.dumps(
            {
                "artifacts": [
                    "C:/srv-data/controle-treinamentos/hml/evidence/release_20260410_120000/release_manifest.json"
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "ops" / "windows" / "env" / "prod.env.example").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "ops" / "windows" / "env" / "prod.env.example").write_text("SECRET_KEY=template", encoding="utf-8")
    (tmp_path / "frontend" / ".env.example").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "frontend" / ".env.example").write_text("API_URL=http://localhost:3000", encoding="utf-8")

    result = _run_validator(tmp_path)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    payload = json.loads(result.stdout)
    assert payload["success"] is True


def test_repo_hygiene_blocks_root_snapshot_or_backup(tmp_path: Path):
    (tmp_path / "backend-snapshot-20260415").mkdir()
    (tmp_path / "db-backup-20260415.dump").write_text("backup", encoding="utf-8")

    result = _run_validator(tmp_path)
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert any(
        item["kind"] == "root_snapshot_or_backup"
        and item["path"] == "backend-snapshot-20260415"
        and "archive/repo-snapshots" in item["reason"]
        for item in payload["violations"]
    )
    assert any(
        item["kind"] == "root_snapshot_or_backup"
        and item["path"] == "db-backup-20260415.dump"
        and "archive/temp-backups" in item["reason"]
        for item in payload["violations"]
    )


def test_repo_hygiene_blocks_dated_archivable_material_in_live_tree(tmp_path: Path):
    (tmp_path / "backend" / "src" / "app-backup-20260415").mkdir(parents=True)
    snapshot = tmp_path / "frontend" / "src" / "ui-snapshot-20260415.json"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text("{}", encoding="utf-8")

    allowed_script = tmp_path / "ops" / "scripts" / "backup" / "run_backups.py"
    allowed_script.parent.mkdir(parents=True, exist_ok=True)
    allowed_script.write_text("print('canonical backup script')\n", encoding="utf-8")

    allowed_archive = tmp_path / "archive" / "temp-backups" / "app-backup-20260415"
    allowed_archive.mkdir(parents=True)

    result = _run_validator(tmp_path)
    assert result.returncode == 1
    payload = json.loads(result.stdout)

    violations = {
        (item["kind"], item["path"], item["reason"])
        for item in payload["violations"]
    }
    assert any(
        kind == "unclassified_archivable_material"
        and path == "backend/src/app-backup-20260415"
        and "archive/temp-backups" in reason
        for kind, path, reason in violations
    )
    assert any(
        kind == "unclassified_archivable_material"
        and path == "frontend/src/ui-snapshot-20260415.json"
        and "archive/repo-snapshots" in reason
        for kind, path, reason in violations
    )
    assert not any(path == "ops/scripts/backup/run_backups.py" for _, path, _ in violations)
    assert not any(path == "archive/temp-backups/app-backup-20260415" for _, path, _ in violations)


def test_repo_hygiene_blocks_unclassified_scripts_compat_wrapper(tmp_path: Path):
    script = tmp_path / "scripts" / "jobs" / "run_legacy_worker.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("print('legacy')\n", encoding="utf-8")

    result = _run_validator(tmp_path)
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert any(
        item["kind"] == "unclassified_compat_script" and item["path"] == "scripts/jobs/run_legacy_worker.py"
        for item in payload["violations"]
    )


def test_repo_hygiene_blocks_allowed_wrapper_without_removal_plan(tmp_path: Path):
    script = tmp_path / "scripts" / "backup" / "run_backups.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        '"""COMPAT: wrapper historico.\n\n'
        "Comando oficial: backend/tools/maintenance/run_backups.py.\n"
        '"""\n',
        encoding="utf-8",
    )
    readme = tmp_path / "scripts" / "README.md"
    readme.write_text(
        "# Scripts\n\n"
        "| wrapper de compatibilidade | trilha canonica |\n"
        "| --- | --- |\n"
        "| `scripts/backup/run_backups.py` | `backend/tools/maintenance/run_backups.py` |\n",
        encoding="utf-8",
    )

    result = _run_validator(tmp_path)
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert any(
        item["kind"] == "missing_compat_removal_plan"
        and item["path"] == "scripts/backup/run_backups.py"
        for item in payload["violations"]
    )


def test_repo_hygiene_blocks_unregistered_live_document(tmp_path: Path):
    manual = tmp_path / "docs" / "product" / "manual_usuario_operacional_v2.md"
    manual.parent.mkdir(parents=True, exist_ok=True)
    manual.write_text("# Manual duplicado\n", encoding="utf-8")

    result = _run_validator(tmp_path)
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert any(
        item["kind"] == "unregistered_live_document"
        and item["path"] == "docs/product/manual_usuario_operacional_v2.md"
        for item in payload["violations"]
    )


def test_repo_hygiene_blocks_ambiguous_root_directory(tmp_path: Path):
    (tmp_path / "platform").mkdir()

    result = _run_validator(tmp_path)
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert any(
        item["kind"] == "ambiguous_root_directory"
        and item["path"] == "platform"
        and "approved root category" in item["reason"]
        for item in payload["violations"]
    )


def test_repo_hygiene_blocks_new_sistema_controle_usage_outside_allowlist(tmp_path: Path):
    file = tmp_path / "backend" / "src" / "controle_treinamentos" / "services" / "new_state.py"
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(
        "def load_state(db):\n"
        "    return db.execute(\"SELECT valor FROM sistema_controle WHERE chave = %s\", ('x',)).fetchone()\n",
        encoding="utf-8",
    )

    result = _run_validator(tmp_path)
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert any(
        item["kind"] == "forbidden_sistema_controle_usage"
        and item["path"] == "backend/src/controle_treinamentos/services/new_state.py"
        for item in payload["violations"]
    )
