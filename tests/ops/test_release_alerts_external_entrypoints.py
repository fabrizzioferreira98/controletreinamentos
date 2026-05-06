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
                    "alerts_external_e2e": {
                        "status": "PENDING",
                        "artifacts": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def test_run_alerts_external_release_updates_manifest_and_checklist(monkeypatch, tmp_path):
    module = _load_module(
        "run_alerts_external_release_test",
        "ops/scripts/release/run_alerts_external_release.py",
    )

    manifest_path = tmp_path / "release_evidence_manifest.json"
    checklist_path = tmp_path / "regression_checklist.md"
    out_dir = tmp_path / "alerts"
    output_path = out_dir / "alerts_external_drill.json"
    capture_path = tmp_path / "delivery_capture.json"
    _write_manifest(manifest_path)
    checklist_path.write_text(
        "# Checklist\n\n## Evidencias anexadas\n- Alertas externos: <placeholder>\n",
        encoding="utf-8",
    )
    capture_path.write_text(
        json.dumps(
            {
                "received": True,
                "status": 202,
                "payload": {"event": "release_alert_drill"},
            }
        ),
        encoding="utf-8",
    )

    def fake_run_drill(py_exec, script, cmd_args):
        assert "--webhook-url-file" in cmd_args
        assert "--require-ack" in cmd_args
        return (
            0,
            {
                "success": True,
                "status": 202,
                "response_body_sha256": "abc123",
                "response_body_length": 2,
                "payload": {"event": "release_alert_drill"},
                "acknowledged": True,
                "acknowledged_by": "oncall-homolog",
                "escalation_target": "pagerduty-primary",
            },
            "{}",
            "",
            "python alerts_external_drill.py --webhook-url-file C:/secret/webhook.txt",
        )

    monkeypatch.setattr(module, "_run_drill", fake_run_drill)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_alerts_external_release.py",
            "--out-dir",
            str(out_dir),
            "--output",
            str(output_path),
            "--manifest",
            str(manifest_path),
            "--regression-checklist",
            str(checklist_path),
            "--webhook-url-file",
            str(tmp_path / "webhook.txt"),
            "--delivery-capture-file",
            str(capture_path),
            "--acknowledged-by",
            "oncall-homolog",
            "--escalation-target",
            "pagerduty-primary",
        ],
    )

    assert module.main() == 0

    artifact_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert artifact_payload["success"] is True
    assert artifact_payload["status"] == 202
    assert artifact_payload["external_delivery_exercised"] is True
    assert artifact_payload["external_delivery_evidence"]["received"] is True
    assert artifact_payload["release_id"] == "release_20260420_160000"
    assert artifact_payload["commit_sha"] == "workspace-without-git"
    assert artifact_payload["environment"] == "homolog"

    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    check = manifest_payload["checks"]["alerts_external_e2e"]
    assert check["status"] == "PASS"
    assert check["artifacts"] == [str(output_path.resolve())]
    assert str(output_path.resolve()) in checklist_path.read_text(encoding="utf-8")


def test_run_alerts_external_release_keeps_failure_as_fail(monkeypatch, tmp_path):
    module = _load_module(
        "run_alerts_external_release_failure_test",
        "ops/scripts/release/run_alerts_external_release.py",
    )

    manifest_path = tmp_path / "release_evidence_manifest.json"
    checklist_path = tmp_path / "regression_checklist.md"
    out_dir = tmp_path / "alerts"
    output_path = out_dir / "alerts_external_drill.json"
    _write_manifest(manifest_path)
    checklist_path.write_text("- Alertas externos: \n", encoding="utf-8")

    def fake_run_drill(py_exec, script, cmd_args):
        return (
            1,
            {
                "success": False,
                "message": "Webhook de alerta nao configurado.",
            },
            "{}",
            "",
            "python alerts_external_drill.py",
        )

    monkeypatch.setattr(module, "_run_drill", fake_run_drill)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_alerts_external_release.py",
            "--out-dir",
            str(out_dir),
            "--output",
            str(output_path),
            "--manifest",
            str(manifest_path),
            "--regression-checklist",
            str(checklist_path),
            "--acknowledged-by",
            "oncall-homolog",
            "--escalation-target",
            "pagerduty-primary",
        ],
    )

    assert module.main() == 1

    artifact_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert artifact_payload["success"] is False
    assert artifact_payload["external_delivery_exercised"] is False

    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    check = manifest_payload["checks"]["alerts_external_e2e"]
    assert check["status"] == "FAIL"
    assert check["artifacts"] == [str(output_path.resolve())]


def test_alerts_external_drill_accepts_bom_webhook_file(monkeypatch, tmp_path, capsys):
    module = _load_module(
        "alerts_external_drill_bom_test",
        "ops/scripts/release/alerts_external_drill.py",
    )
    webhook_path = tmp_path / "webhook.txt"
    webhook_path.write_text("\ufeffhttp://127.0.0.1:18080/webhook\n", encoding="utf-8")

    class FakeResponse:
        status = 202

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b"ok"

    def fake_urlopen(request, timeout):
        assert request.full_url == "http://127.0.0.1:18080/webhook"
        return FakeResponse()

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "alerts_external_drill.py",
            "--webhook-url-file",
            str(webhook_path),
            "--acknowledged-by",
            "oncall-homolog",
            "--escalation-target",
            "pagerduty-primary",
            "--require-ack",
        ],
    )

    assert module.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is True
    assert payload["acknowledged_by"] == "oncall-homolog"
