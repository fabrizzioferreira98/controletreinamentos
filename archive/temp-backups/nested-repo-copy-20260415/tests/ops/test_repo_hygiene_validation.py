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
    (tmp_path / ".venv" / "pyvenv.cfg").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".venv" / "pyvenv.cfg").write_text("home = C:/Python", encoding="utf-8")
    (tmp_path / "frontend" / "dist" / "index.html").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "frontend" / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")
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
    assert ".venv" in paths
    assert "frontend/dist" in paths
    assert "backend/runtime" in paths
    assert "backend/src/__pycache__" in paths
    assert "ops/windows/env/prod.env" in paths
    assert "ops/windows/env/prod.env.example" not in paths


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
