from __future__ import annotations

import hashlib
import hmac
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REQUIRED_CHECKS = (
    "e2e_homolog",
    "load_authenticated_20w",
    "load_authenticated_30w",
    "jobs_concurrency_retry_dead_letter",
    "alerts_external_e2e",
    "backup_restore_drill",
    "rollback_drill",
    "post_deploy_smoke",
    "metrics_hardening",
)


def _validator_script() -> str:
    root = Path(__file__).resolve().parents[1]
    return str(root / "scripts" / "release" / "validate_operational_evidence.py")


def _git_head(root: Path) -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(root), text=True).strip()
    except Exception:
        return "workspace-without-git"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _signature_payload(payload: dict) -> str:
    canonical = dict(payload)
    canonical.pop("signature_hmac_sha256", None)
    return json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _harden_manifest(path: Path, *, signing_key: str | None = None) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    artifact_hashes: dict[str, str] = {}
    for check in payload.get("checks", {}).values():
        artifacts = check.get("artifacts", []) if isinstance(check, dict) else []
        for raw in artifacts:
            artifact_candidate = str(raw or "").strip()
            if not artifact_candidate:
                continue
            artifact_hashes[artifact_candidate] = _sha256_file(Path(artifact_candidate))
    payload["artifacts_sha256"] = artifact_hashes
    if signing_key:
        body = _signature_payload(payload).encode("utf-8")
        payload["signature_hmac_sha256"] = hmac.new(signing_key.encode("utf-8"), body, hashlib.sha256).hexdigest()
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def _build_manifest(tmp_path: Path, *, missing_check: str | None = None) -> Path:
    release_id = "release_test_001"
    artifacts_dir = tmp_path / "artifacts" / release_id
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    generated_at = datetime.now(timezone.utc).isoformat()

    e2e_run_1 = artifacts_dir / "e2e_round1.log"
    e2e_run_1.write_text("3 passed in 1.23s\n", encoding="utf-8")
    e2e_run_2 = artifacts_dir / "e2e_round2.log"
    e2e_run_2.write_text("3 passed in 1.18s\n", encoding="utf-8")

    load_20 = artifacts_dir / "load_auth_20w.json"
    load_20.write_text(
        json.dumps(
            {
                "success": True,
                "authenticated": True,
                "workers": 20,
                "seconds": 300,
                "requests": 100,
                "auth_failures": 0,
                "availability_percent": 99.5,
                "latency_ms": {"p95": 800.0},
                "login_failures": [],
            }
        ),
        encoding="utf-8",
    )

    load_30 = artifacts_dir / "load_auth_30w.json"
    load_30.write_text(
        json.dumps(
            {
                "success": True,
                "authenticated": True,
                "workers": 30,
                "seconds": 300,
                "requests": 100,
                "auth_failures": 0,
                "availability_percent": 99.2,
                "latency_ms": {"p95": 950.0},
                "login_failures": [],
            }
        ),
        encoding="utf-8",
    )

    jobs = artifacts_dir / "jobs_concurrency_drill.json"
    jobs.write_text(
        json.dumps(
            {
                "success": True,
                "counts_final": {"queued": 0, "running": 0, "dead_letter": 1, "succeeded": 2},
            }
        ),
        encoding="utf-8",
    )

    alerts = artifacts_dir / "alerts_external_drill.json"
    alerts.write_text(
        json.dumps(
            {
                "success": True,
                "status": 200,
                "acknowledged": True,
                "acknowledged_by": "oncall-user",
                "escalation_target": "pagerduty-primary",
            }
        ),
        encoding="utf-8",
    )

    backup = artifacts_dir / "backup_restore_drill.json"
    backup.write_text(
        json.dumps(
            {
                "success": True,
                "steps": [{"step": "restore_full", "success": True}],
            }
        ),
        encoding="utf-8",
    )

    smoke_a = artifacts_dir / "smoke_A_before.json"
    smoke_a.write_text(json.dumps({"failed": False}), encoding="utf-8")
    smoke_b = artifacts_dir / "smoke_B_after_rollback.json"
    smoke_b.write_text(json.dumps({"failed": False}), encoding="utf-8")
    smoke_c = artifacts_dir / "smoke_A_after_forward.json"
    smoke_c.write_text(json.dumps({"failed": False}), encoding="utf-8")
    rollback_meta = artifacts_dir / "rollback_runtime_ids.json"
    rollback_meta.write_text(
        json.dumps(
            {
                "success": True,
                "before_runtime_id": "selfhosted-instance-a",
                "rollback_runtime_id": "selfhosted-instance-b",
                "forward_runtime_id": "selfhosted-instance-a",
            }
        ),
        encoding="utf-8",
    )

    post_smoke = artifacts_dir / "post_deploy_smoke.json"
    post_smoke.write_text(
        json.dumps(
            {
                "failed": False,
                "results": [
                    {"check": "login_page", "ok": True},
                    {"check": "dashboard_redirect", "ok": True},
                    {"check": "internal_metrics", "ok": True},
                ],
            }
        ),
        encoding="utf-8",
    )

    metrics_hardening = artifacts_dir / "metrics_hardening.json"
    metrics_hardening.write_text(
        json.dumps(
            {
                "success": True,
                "without_token_status": "403",
                "invalid_token_status": "403",
                "valid_token_status": "200",
            }
        ),
        encoding="utf-8",
    )

    metrics_no = artifacts_dir / "metrics_no_token.json"
    metrics_no.write_text("{}", encoding="utf-8")
    metrics_bad = artifacts_dir / "metrics_bad_token.json"
    metrics_bad.write_text("{}", encoding="utf-8")
    metrics_ok = artifacts_dir / "metrics_ok.json"
    metrics_ok.write_text("{}", encoding="utf-8")

    checks = {}
    checks["e2e_homolog"] = {"status": "PASS", "artifacts": [str(e2e_run_1), str(e2e_run_2)]}
    checks["load_authenticated_20w"] = {"status": "PASS", "artifacts": [str(load_20)]}
    checks["load_authenticated_30w"] = {"status": "PASS", "artifacts": [str(load_30)]}
    checks["jobs_concurrency_retry_dead_letter"] = {"status": "PASS", "artifacts": [str(jobs)]}
    checks["alerts_external_e2e"] = {"status": "PASS", "artifacts": [str(alerts)]}
    checks["backup_restore_drill"] = {"status": "PASS", "artifacts": [str(backup)]}
    checks["rollback_drill"] = {
        "status": "PASS",
        "artifacts": [str(smoke_a), str(smoke_b), str(smoke_c), str(rollback_meta)],
    }
    checks["post_deploy_smoke"] = {"status": "PASS", "artifacts": [str(post_smoke)]}
    checks["metrics_hardening"] = {
        "status": "PASS",
        "artifacts": [str(metrics_hardening), str(metrics_no), str(metrics_bad), str(metrics_ok)],
    }
    if missing_check:
        checks.pop(missing_check, None)

    manifest = {
        "generated_at": generated_at,
        "environment": "homolog",
        "release_id": release_id,
        "commit_sha": _git_head(root),
        "checks": checks,
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_validate_operational_evidence_manifest_passes(tmp_path):
    manifest = _build_manifest(tmp_path)
    result = subprocess.run(
        [sys.executable, _validator_script(), "--manifest", str(manifest)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    payload = json.loads(result.stdout)
    assert payload["success"] is True


def test_validate_operational_evidence_manifest_fails_when_check_missing(tmp_path):
    manifest = _build_manifest(tmp_path, missing_check="alerts_external_e2e")
    result = subprocess.run(
        [sys.executable, _validator_script(), "--manifest", str(manifest)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["success"] is False
    assert any("missing_check:alerts_external_e2e" in issue for issue in payload["issues"])


def test_validate_operational_evidence_manifest_fails_when_commit_mismatch(tmp_path):
    manifest = _build_manifest(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["commit_sha"] = "0000000000000000000000000000000000000000"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, _validator_script(), "--manifest", str(manifest)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    response_payload = json.loads(result.stdout)
    assert response_payload["success"] is False
    assert any(issue.startswith("commit_sha_mismatch:") for issue in response_payload["issues"])


def test_validate_operational_evidence_manifest_fails_when_artifact_release_id_mismatch(tmp_path):
    manifest = _build_manifest(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    out_of_release_artifact = tmp_path / "post_deploy_smoke.json"
    out_of_release_artifact.write_text(json.dumps({"failed": False}), encoding="utf-8")
    payload["checks"]["post_deploy_smoke"]["artifacts"] = [str(out_of_release_artifact)]
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, _validator_script(), "--manifest", str(manifest)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    response_payload = json.loads(result.stdout)
    assert response_payload["success"] is False
    assert any(issue.startswith("artifact_release_id_mismatch:post_deploy_smoke") for issue in response_payload["issues"])


def test_validate_operational_evidence_manifest_fails_when_release_id_only_as_substring(tmp_path):
    manifest = _build_manifest(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    tricky = tmp_path / "notrelease_test_001suffix" / "post_deploy_smoke.json"
    tricky.parent.mkdir(parents=True, exist_ok=True)
    tricky.write_text(json.dumps({"failed": False, "results": [{"ok": True}]}), encoding="utf-8")
    payload["checks"]["post_deploy_smoke"]["artifacts"] = [str(tricky)]
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, _validator_script(), "--manifest", str(manifest)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    response_payload = json.loads(result.stdout)
    assert response_payload["success"] is False
    assert any(issue.startswith("artifact_release_id_mismatch:post_deploy_smoke") for issue in response_payload["issues"])


def test_validate_operational_evidence_manifest_strict_mode_passes(tmp_path, monkeypatch):
    manifest = _build_manifest(tmp_path)
    signing_env = "TEST_EVIDENCE_SIGNING_KEY"
    signing_key = "test-signing-key-123"
    monkeypatch.setenv(signing_env, signing_key)
    _harden_manifest(manifest, signing_key=signing_key)

    result = subprocess.run(
        [
            sys.executable,
            _validator_script(),
            "--manifest",
            str(manifest),
            "--require-hashes",
            "--require-signature",
            "--signing-key-env",
            signing_env,
            "--require-rollback-runtime-ids",
            "--require-alert-ack",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    payload = json.loads(result.stdout)
    assert payload["success"] is True


def test_validate_operational_evidence_manifest_fails_when_hash_mismatch(tmp_path):
    manifest = _build_manifest(tmp_path)
    payload = _harden_manifest(manifest, signing_key=None)
    tampered_artifact = Path(payload["checks"]["post_deploy_smoke"]["artifacts"][0])
    tampered_artifact.write_text(json.dumps({"failed": True}), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            _validator_script(),
            "--manifest",
            str(manifest),
            "--require-hashes",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    response_payload = json.loads(result.stdout)
    assert any(issue.startswith("artifact_hash_mismatch:post_deploy_smoke") for issue in response_payload["issues"])


def test_validate_operational_evidence_manifest_fails_when_alert_ack_missing(tmp_path):
    manifest = _build_manifest(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    alerts_artifact = Path(payload["checks"]["alerts_external_e2e"]["artifacts"][0])
    alerts_artifact.write_text(json.dumps({"success": True, "status": 200, "acknowledged": False}), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            _validator_script(),
            "--manifest",
            str(manifest),
            "--require-alert-ack",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    response_payload = json.loads(result.stdout)
    assert any(issue.startswith("alerts_external_e2e:acknowledged_false") for issue in response_payload["issues"])


def test_validate_operational_evidence_manifest_fails_when_rollback_metadata_missing(tmp_path):
    manifest = _build_manifest(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    rollback_artifacts = payload["checks"]["rollback_drill"]["artifacts"]
    payload["checks"]["rollback_drill"]["artifacts"] = rollback_artifacts[:3]
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            _validator_script(),
            "--manifest",
            str(manifest),
            "--require-rollback-runtime-ids",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    response_payload = json.loads(result.stdout)
    assert any(issue.startswith("rollback_drill:missing_runtime_metadata") for issue in response_payload["issues"])


def test_validate_operational_evidence_manifest_fails_when_signature_invalid(tmp_path, monkeypatch):
    manifest = _build_manifest(tmp_path)
    signing_env = "TEST_EVIDENCE_SIGNING_KEY"
    signing_key = "test-signing-key-456"
    monkeypatch.setenv(signing_env, signing_key)
    payload = _harden_manifest(manifest, signing_key=signing_key)
    payload["environment"] = "production"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            _validator_script(),
            "--manifest",
            str(manifest),
            "--require-signature",
            "--signing-key-env",
            signing_env,
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    response_payload = json.loads(result.stdout)
    assert any(issue.startswith("signature_invalid") for issue in response_payload["issues"])


def test_validate_operational_evidence_manifest_fails_when_release_id_empty(tmp_path):
    manifest = _build_manifest(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["release_id"] = ""
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, _validator_script(), "--manifest", str(manifest)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    response_payload = json.loads(result.stdout)
    assert any(issue == "release_id_empty" for issue in response_payload["issues"])


def test_validate_operational_evidence_manifest_fails_when_load_has_auth_failures(tmp_path):
    manifest = _build_manifest(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    load_artifact = Path(payload["checks"]["load_authenticated_20w"]["artifacts"][0])
    load_payload = json.loads(load_artifact.read_text(encoding="utf-8"))
    load_payload["auth_failures"] = 3
    load_artifact.write_text(json.dumps(load_payload), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, _validator_script(), "--manifest", str(manifest)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    response_payload = json.loads(result.stdout)
    assert any(
        issue.startswith("load_authenticated_20w:auth_failures_present")
        for issue in response_payload["issues"]
    )
