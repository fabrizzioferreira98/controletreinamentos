from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_module(name: str, relative_path: str):
    target = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, target)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _write_manifest(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "generated_at": "2026-04-20T16:00:00Z",
                "environment": "homolog",
                "release_id": "release_20260420_160000",
                "commit_sha": "workspace-without-git",
                "checks": {
                    "rollback_drill": {
                        "status": "PENDING",
                        "artifacts": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def _write_smoke(path: Path) -> None:
    path.write_text(json.dumps({"failed": False, "results": [{"check": "login_page", "ok": True}]}), encoding="utf-8")


def test_run_rollback_release_drill_updates_manifest_when_aba_evidence_exists(monkeypatch, tmp_path):
    module = _load_module(
        "run_rollback_release_drill_test",
        "ops/scripts/release/run_rollback_release_drill.py",
    )

    manifest_path = tmp_path / "release_evidence_manifest.json"
    checklist_path = tmp_path / "regression_checklist.md"
    out_dir = tmp_path / "rollback"
    _write_manifest(manifest_path)
    checklist_path.write_text("- Rollback: <placeholder>\n", encoding="utf-8")

    header_before = tmp_path / "headers_before.txt"
    header_rollback = tmp_path / "headers_rollback.txt"
    header_forward = tmp_path / "headers_forward.txt"
    header_before.write_text("X-Release-Instance-Id: release-a\n", encoding="utf-8")
    header_rollback.write_text("X-Release-Instance-Id: release-b\n", encoding="utf-8")
    header_forward.write_text("X-Release-Instance-Id: release-a\n", encoding="utf-8")

    smoke_before = tmp_path / "smoke_A_before.json"
    smoke_rollback = tmp_path / "smoke_B_after_rollback.json"
    smoke_forward = tmp_path / "smoke_A_after_forward.json"
    for smoke in (smoke_before, smoke_rollback, smoke_forward):
        _write_smoke(smoke)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_rollback_release_drill.py",
            "--out-dir",
            str(out_dir),
            "--manifest",
            str(manifest_path),
            "--regression-checklist",
            str(checklist_path),
            "--header-before",
            str(header_before),
            "--header-rollback",
            str(header_rollback),
            "--header-forward",
            str(header_forward),
            "--smoke-before",
            str(smoke_before),
            "--smoke-rollback",
            str(smoke_rollback),
            "--smoke-forward",
            str(smoke_forward),
        ],
    )

    assert module.main() == 0

    metadata_path = out_dir / "rollback_runtime_ids.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["success"] is True
    assert metadata["before_runtime_id"] == "release-a"
    assert metadata["rollback_runtime_id"] == "release-b"
    assert metadata["forward_runtime_id"] == "release-a"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    check = manifest["checks"]["rollback_drill"]
    assert check["status"] == "PASS"
    assert check["artifacts"] == [
        str(smoke_before.resolve()),
        str(smoke_rollback.resolve()),
        str(smoke_forward.resolve()),
        str(metadata_path.resolve()),
    ]
    assert str(metadata_path.resolve()) in checklist_path.read_text(encoding="utf-8")


def test_run_rollback_release_drill_refuses_missing_real_evidence(monkeypatch, tmp_path):
    module = _load_module(
        "run_rollback_release_drill_failure_test",
        "ops/scripts/release/run_rollback_release_drill.py",
    )

    manifest_path = tmp_path / "release_evidence_manifest.json"
    checklist_path = tmp_path / "regression_checklist.md"
    out_dir = tmp_path / "rollback"
    _write_manifest(manifest_path)
    checklist_path.write_text("- Rollback: \n", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_rollback_release_drill.py",
            "--out-dir",
            str(out_dir),
            "--manifest",
            str(manifest_path),
            "--regression-checklist",
            str(checklist_path),
            "--base-url",
            "https://homolog.example.test",
        ],
    )

    assert module.main() == 1

    attempt_path = out_dir / "rollback_drill_attempt.json"
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    assert attempt["success"] is False
    assert attempt["rollback_exercised"] is False
    assert "smoke_before_missing" in attempt["issues"]
    assert "header_rollback_missing" in attempt["issues"]

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    check = manifest["checks"]["rollback_drill"]
    assert check["status"] == "FAIL"
    assert check["artifacts"] == [str(attempt_path.resolve())]
    assert str(attempt_path.resolve()) in checklist_path.read_text(encoding="utf-8")
