from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
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

PRE29_MINIMAL_REQUIRED_CHECKS = (
    "ci_validation",
    "repo_hygiene",
    "auth_session",
    "storage_docs",
    "db_consistency",
    "jobs_drill",
    "backup_restore",
)


def _validator_script() -> str:
    root = Path(__file__).resolve().parents[2]
    return str(root / "ops" / "scripts" / "release" / "validate_operational_evidence.py")


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


def _set_file_mtime(path: Path, when: datetime) -> None:
    timestamp = when.astimezone(timezone.utc).timestamp()
    os.utime(path, (timestamp, timestamp))


def _checklist_attachment_path(checklist_path: Path, label: str) -> Path:
    prefix = f"- {label}: "
    for line in checklist_path.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            return Path(line[len(prefix) :].strip())
    raise AssertionError(f"attachment not found: {label}")


def _build_release_regression_checklist(
    tmp_path: Path,
    *,
    release_id: str,
    commit_sha: str,
    environment: str,
    manifest_path: Path,
    manifest_payload: dict,
    release_id_override: str | None = None,
    commit_sha_override: str | None = None,
    environment_override: str | None = None,
    manifest_ref_override: str | None = None,
    checklist_timestamp: datetime | None = None,
    gate_timestamp: datetime | None = None,
) -> Path:
    artifacts_dir = tmp_path / "artifacts" / environment / release_id
    release_checklist = artifacts_dir / "release_execution_checklist.md"
    rollback_checklist = artifacts_dir / "rollback_checklist.md"
    gate_log = artifacts_dir / "gate_final_strict.log"
    scheduler_scope = artifacts_dir / "scheduler_scope.txt"
    storage_validation = artifacts_dir / "storage_validation.txt"
    smoke_pos_release = artifacts_dir / "smoke_pos_release.txt"

    for path, content in (
        (
            release_checklist,
            "\n".join(
                [
                    "# release checklist",
                    "",
                    "- [x] gate strict executado",
                    "- [x] deploy promovido",
                ]
            )
            + "\n",
        ),
        (
            rollback_checklist,
            "\n".join(
                [
                    "# rollback checklist",
                    "",
                    "- [x] backup anterior validado",
                    "- [x] procedimento de volta revisado",
                ]
            )
            + "\n",
        ),
        (gate_log, "RELEASE GATE: PASS\n"),
        (scheduler_scope, "scheduler validated\n"),
        (storage_validation, "storage validated\n"),
        (smoke_pos_release, "post release smoke validated\n"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    checks = manifest_payload["checks"]
    manifest_generated_at = datetime.fromisoformat(str(manifest_payload["generated_at"]).replace("Z", "+00:00"))
    if manifest_generated_at.tzinfo is None:
        manifest_generated_at = manifest_generated_at.replace(tzinfo=timezone.utc)
    gate_timestamp = gate_timestamp or (manifest_generated_at - timedelta(minutes=10))
    checklist_timestamp = checklist_timestamp or (manifest_generated_at + timedelta(minutes=1))
    _set_file_mtime(release_checklist, gate_timestamp - timedelta(minutes=1))
    _set_file_mtime(rollback_checklist, gate_timestamp - timedelta(minutes=1))
    _set_file_mtime(gate_log, gate_timestamp)
    _set_file_mtime(scheduler_scope, checklist_timestamp)
    _set_file_mtime(storage_validation, checklist_timestamp)
    _set_file_mtime(smoke_pos_release, checklist_timestamp)

    checklist_path = artifacts_dir / "regression_audit_checklist.md"
    checklist_path.write_text(
        "\n".join(
            [
                "# Checklist de Auditoria de Regressao",
                "",
                "## Metadados",
                f"- Release ID: {release_id_override or release_id}",
                f"- Commit SHA: {commit_sha_override or commit_sha}",
                f"- Ambiente: {environment_override or environment}",
                "- Responsavel tecnico: release-bot",
                f"- Data/hora: {checklist_timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                "## Checklist obrigatorio",
                "- [x] Paridade minima local/homolog/producao revisada contra `docs/operations/ENVIRONMENT_PARITY.md`.",
                "- [x] Contrato HTTP (401/403/500/CSRF) validado em navegacao e chamadas programaticas.",
                "- [x] Autenticacao e autorizacao (login, logout, permissao) validadas.",
                "- [x] Auth/cookies/origens do frontend validados no modo real do ambiente-alvo.",
                "- [x] CRUDs criticos validados ponta a ponta.",
                "- [x] Jobs (enqueue, worker, retry, dead-letter) validados.",
                "- [x] Worker ativo consumindo fila real e scheduler/cron equivalente validado ou explicitamente fora do escopo.",
                "- [x] Storage, uploads/downloads e PDFs validados em raiz real do ambiente.",
                "- [x] Notificacoes e integracoes externas validadas ponta a ponta ou explicitamente excluidas da evidencia.",
                "- [x] Massa minima canonica declarada e coerente com o ambiente-alvo.",
                "- [x] Backup/restore drill validado.",
                "- [x] Rollback drill validado (ida e volta).",
                "- [x] Carga autenticada validada dentro do SLO.",
                "- [x] Alertas externos validados ponta a ponta.",
                "- [x] Checklist de release preenchido no pacote externo do release.",
                "- [x] Checklist de rollback preenchido antes do deploy.",
                "- [x] Smoke pos-deploy validado.",
                "- [x] Gate final strict executado e anexado.",
                "- [x] Gate de release com evidencias operacionais em PASS.",
                "",
                "## Evidencias anexadas",
                f"- Paridade minima entre ambientes: {checks['post_deploy_smoke']['artifacts'][0]}",
                f"- Gate final strict: {gate_log}",
                f"- Checklist de release: {release_checklist}",
                f"- Checklist de rollback: {rollback_checklist}",
                f"- E2E: {checks['e2e_homolog']['artifacts'][0]}",
                f"- Carga autenticada: {checks['load_authenticated_20w']['artifacts'][0]}",
                f"- Jobs concorrentes: {checks['jobs_concurrency_retry_dead_letter']['artifacts'][0]}",
                f"- Scheduler/cron ou declaracao de escopo: {scheduler_scope}",
                f"- Storage/PDF/upload-download: {storage_validation}",
                f"- Alertas externos: {checks['alerts_external_e2e']['artifacts'][0]}",
                f"- Backup/restore: {checks['backup_restore_drill']['artifacts'][0]}",
                f"- Rollback: {checks['rollback_drill']['artifacts'][0]}",
                f"- Smoke: {checks['post_deploy_smoke']['artifacts'][0]}",
                f"- Smoke pos-release: {smoke_pos_release}",
                f"- Manifest de evidencias: {manifest_ref_override or manifest_path}",
                "",
                "## Decisao",
                "- Resultado: GO",
                "- Justificativa: pacote coerente",
                "- Riscos residuais: nenhum",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    _set_file_mtime(checklist_path, checklist_timestamp)
    return checklist_path


def _build_manifest(
    tmp_path: Path,
    *,
    missing_check: str | None = None,
    environment: str = "homolog",
) -> Path:
    release_id = "release_test_001"
    artifacts_dir = tmp_path / "artifacts" / environment / release_id
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[2]
    commit_sha = _git_head(root)
    base_time = datetime.now(timezone.utc) - timedelta(minutes=40)

    def at(minutes: int) -> datetime:
        return base_time + timedelta(minutes=minutes)

    def write_text_artifact(path: Path, content: str, when: datetime) -> None:
        path.write_text(content, encoding="utf-8")
        _set_file_mtime(path, when)

    def write_json_artifact(path: Path, payload: dict, when: datetime) -> None:
        payload = {
            "release_id": release_id,
            "commit_sha": commit_sha,
            "environment": environment,
            "generated_at": when.isoformat(),
            **payload,
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
        _set_file_mtime(path, when)

    e2e_run_1 = artifacts_dir / "e2e_round1.log"
    write_text_artifact(e2e_run_1, "3 passed in 1.23s\n", at(0))
    e2e_run_2 = artifacts_dir / "e2e_round2.log"
    write_text_artifact(e2e_run_2, "3 passed in 1.18s\n", at(1))

    load_20 = artifacts_dir / "load_auth_20w.json"
    write_json_artifact(
        load_20,
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
        },
        at(2),
    )

    load_30 = artifacts_dir / "load_auth_30w.json"
    write_json_artifact(
        load_30,
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
        },
        at(3),
    )

    jobs = artifacts_dir / "jobs_concurrency_drill.json"
    write_json_artifact(
        jobs,
        {
            "success": True,
            "counts_final": {"queued": 0, "running": 0, "dead_letter": 1, "succeeded": 2},
        },
        at(4),
    )

    alerts = artifacts_dir / "alerts_external_drill.json"
    write_json_artifact(
        alerts,
        {
            "success": True,
            "status": 200,
            "acknowledged": True,
            "acknowledged_by": "oncall-user",
            "escalation_target": "pagerduty-primary",
        },
        at(5),
    )

    backup = artifacts_dir / "backup_restore_drill.json"
    write_json_artifact(
        backup,
        {
            "success": True,
            "steps": [{"step": "restore_full", "success": True}],
        },
        at(6),
    )

    smoke_a = artifacts_dir / "smoke_A_before.json"
    write_json_artifact(smoke_a, {"failed": False}, at(7))
    smoke_b = artifacts_dir / "smoke_B_after_rollback.json"
    write_json_artifact(smoke_b, {"failed": False}, at(8))
    smoke_c = artifacts_dir / "smoke_A_after_forward.json"
    write_json_artifact(smoke_c, {"failed": False}, at(9))
    rollback_meta = artifacts_dir / "rollback_runtime_ids.json"
    write_json_artifact(
        rollback_meta,
        {
            "success": True,
            "before_runtime_id": "selfhosted-instance-a",
            "rollback_runtime_id": "selfhosted-instance-b",
            "forward_runtime_id": "selfhosted-instance-a",
        },
        at(10),
    )

    post_smoke = artifacts_dir / "post_deploy_smoke.json"
    write_json_artifact(
        post_smoke,
        {
            "failed": False,
            "results": [
                {"check": "login_page", "ok": True},
                {"check": "dashboard_redirect", "ok": True},
                {"check": "internal_metrics", "ok": True},
            ],
        },
        at(12),
    )

    metrics_hardening = artifacts_dir / "metrics_hardening.json"
    write_json_artifact(
        metrics_hardening,
        {
            "success": True,
            "without_token_status": "403",
            "invalid_token_status": "403",
            "valid_token_status": "200",
        },
        at(13),
    )

    metrics_no = artifacts_dir / "metrics_no_token.json"
    write_json_artifact(metrics_no, {}, at(13))
    metrics_bad = artifacts_dir / "metrics_bad_token.json"
    write_json_artifact(metrics_bad, {}, at(13))
    metrics_ok = artifacts_dir / "metrics_ok.json"
    write_json_artifact(metrics_ok, {}, at(13))

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
        "generated_at": at(20).isoformat(),
        "environment": environment,
        "release_id": release_id,
        "commit_sha": commit_sha,
        "checks": checks,
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    _set_file_mtime(path, at(20))
    return path


def _build_pre29_minimal_manifest(tmp_path: Path, *, missing_check: str | None = None) -> Path:
    release_id = "pre29_minimal_001"
    artifacts_dir = tmp_path / "artifacts" / release_id
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[2]
    generated_at = datetime.now(timezone.utc).isoformat()

    ci_validation = artifacts_dir / "ci_validation.log"
    ci_validation.write_text(
        "\n".join(
            [
                "Frontend build generated at: C:/srv-data/pre29/frontend-dist",
                "5 passed in 1.23s",
                "CI VALIDATION: PASS",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    repo_hygiene = artifacts_dir / "repo_hygiene.json"
    repo_hygiene.write_text(
        json.dumps({"success": True, "violations": []}),
        encoding="utf-8",
    )

    auth_session = artifacts_dir / "auth_session.json"
    auth_session.write_text(
        json.dumps(
            {
                "success": True,
                "login_page_ok": True,
                "login_success_redirect": True,
                "session_authenticated": True,
                "csrf_token_present": True,
                "logout_ok": True,
                "post_logout_redirect_ok": True,
            }
        ),
        encoding="utf-8",
    )

    storage_docs = artifacts_dir / "storage_docs.json"
    storage_docs.write_text(
        json.dumps(
            {
                "ok": True,
                "post_restore_validation": {
                    "status_key": "operational",
                    "critical_count": 0,
                    "warning_count": 0,
                    "document_row_count": 1,
                    "photo_row_count": 1,
                },
                "restore_contract": {"success": True},
            }
        ),
        encoding="utf-8",
    )

    db_consistency = artifacts_dir / "db_consistency.json"
    db_consistency.write_text(
        json.dumps(
            {
                "ok": True,
                "schema": {"is_consistent": True},
                "data": {"total_issues": 0},
            }
        ),
        encoding="utf-8",
    )

    jobs_drill = artifacts_dir / "jobs_drill.json"
    jobs_drill.write_text(
        json.dumps(
            {
                "success": True,
                "success_job_type": "probe",
                "counts_final": {"queued": 0, "running": 0, "dead_letter": 2, "succeeded": 4},
                "probe_state": {"max_active_count": 2},
                "concurrency_proof": {
                    "peak_concurrent_executions": 2,
                    "distinct_success_workers": ["worker-1", "worker-2"],
                },
            }
        ),
        encoding="utf-8",
    )

    backup_restore = artifacts_dir / "backup_restore.json"
    backup_restore.write_text(
        json.dumps(
            {
                "success": True,
                "steps": [
                    {"step": "canonical_restore_artifacts", "success": True},
                    {"step": "restore_full", "success": True, "counts_match": True},
                    {
                        "step": "restore_postcheck",
                        "success": True,
                        "postcheck_result": {"ok": True},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    checks = {
        "ci_validation": {"status": "PASS", "artifacts": [str(ci_validation)]},
        "repo_hygiene": {"status": "PASS", "artifacts": [str(repo_hygiene)]},
        "auth_session": {"status": "PASS", "artifacts": [str(auth_session)]},
        "storage_docs": {"status": "PASS", "artifacts": [str(storage_docs)]},
        "db_consistency": {"status": "PASS", "artifacts": [str(db_consistency)]},
        "jobs_drill": {"status": "PASS", "artifacts": [str(jobs_drill)]},
        "backup_restore": {"status": "PASS", "artifacts": [str(backup_restore)]},
    }
    if missing_check:
        checks.pop(missing_check, None)

    manifest = {
        "generated_at": generated_at,
        "environment": "staging",
        "release_id": release_id,
        "commit_sha": _git_head(root),
        "checks": checks,
    }
    path = tmp_path / "pre29_minimal_manifest.json"
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


def test_validate_operational_evidence_manifest_fails_when_artifact_environment_mismatch(tmp_path):
    manifest = _build_manifest(tmp_path, environment="homolog")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    wrong_env_artifact = tmp_path / "artifacts" / "production" / payload["release_id"] / "post_deploy_smoke.json"
    wrong_env_artifact.parent.mkdir(parents=True, exist_ok=True)
    wrong_env_artifact.write_text(
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
    payload["checks"]["post_deploy_smoke"]["artifacts"] = [str(wrong_env_artifact)]
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, _validator_script(), "--manifest", str(manifest)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    response_payload = json.loads(result.stdout)
    assert response_payload["success"] is False
    assert any(issue.startswith("artifact_environment_mismatch:post_deploy_smoke") for issue in response_payload["issues"])


def test_validate_operational_evidence_manifest_strict_mode_passes(tmp_path, monkeypatch):
    manifest = _build_manifest(tmp_path)
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    checklist = _build_release_regression_checklist(
        tmp_path,
        release_id=manifest_payload["release_id"],
        commit_sha=manifest_payload["commit_sha"],
        environment=manifest_payload["environment"],
        manifest_path=manifest,
        manifest_payload=manifest_payload,
    )
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
            "--regression-checklist",
            str(checklist),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    payload = json.loads(result.stdout)
    assert payload["success"] is True


def test_validate_operational_evidence_manifest_fails_when_checklist_timestamp_out_of_window(tmp_path):
    manifest = _build_manifest(tmp_path)
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    manifest_time = datetime.fromisoformat(str(manifest_payload["generated_at"]).replace("Z", "+00:00"))
    checklist = _build_release_regression_checklist(
        tmp_path,
        release_id=manifest_payload["release_id"],
        commit_sha=manifest_payload["commit_sha"],
        environment=manifest_payload["environment"],
        manifest_path=manifest,
        manifest_payload=manifest_payload,
        checklist_timestamp=manifest_time - timedelta(days=2),
    )

    result = subprocess.run(
        [sys.executable, _validator_script(), "--manifest", str(manifest), "--regression-checklist", str(checklist)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    response_payload = json.loads(result.stdout)
    assert any(
        issue.startswith("regression_checklist:timestamp_out_of_window:")
        for issue in response_payload["issues"]
    )


def test_validate_operational_evidence_manifest_fails_when_artifact_reused_from_previous_execution(tmp_path):
    manifest = _build_manifest(tmp_path)
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    manifest_time = datetime.fromisoformat(str(manifest_payload["generated_at"]).replace("Z", "+00:00"))
    alerts_artifact = Path(manifest_payload["checks"]["alerts_external_e2e"]["artifacts"][0])
    alerts_payload = json.loads(alerts_artifact.read_text(encoding="utf-8"))
    alerts_payload["generated_at"] = (manifest_time - timedelta(days=2)).isoformat()
    alerts_artifact.write_text(json.dumps(alerts_payload), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, _validator_script(), "--manifest", str(manifest)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    response_payload = json.loads(result.stdout)
    assert any(
        issue.startswith("artifact_reused_from_previous_execution:alerts_external_e2e:")
        for issue in response_payload["issues"]
    )


def test_validate_operational_evidence_manifest_fails_when_post_deploy_smoke_precedes_gate(tmp_path):
    manifest = _build_manifest(tmp_path)
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    manifest_time = datetime.fromisoformat(str(manifest_payload["generated_at"]).replace("Z", "+00:00"))
    checklist = _build_release_regression_checklist(
        tmp_path,
        release_id=manifest_payload["release_id"],
        commit_sha=manifest_payload["commit_sha"],
        environment=manifest_payload["environment"],
        manifest_path=manifest,
        manifest_payload=manifest_payload,
        gate_timestamp=manifest_time - timedelta(minutes=5),
    )
    smoke_artifact = Path(manifest_payload["checks"]["post_deploy_smoke"]["artifacts"][0])
    smoke_payload = json.loads(smoke_artifact.read_text(encoding="utf-8"))
    smoke_payload["generated_at"] = (manifest_time - timedelta(minutes=30)).isoformat()
    smoke_artifact.write_text(json.dumps(smoke_payload), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, _validator_script(), "--manifest", str(manifest), "--regression-checklist", str(checklist)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    response_payload = json.loads(result.stdout)
    assert any(issue.startswith("post_deploy_smoke_before_gate:") for issue in response_payload["issues"])


def test_validate_operational_evidence_manifest_fails_when_required_checklist_attachment_missing(tmp_path):
    manifest = _build_manifest(tmp_path)
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    checklist = _build_release_regression_checklist(
        tmp_path,
        release_id=manifest_payload["release_id"],
        commit_sha=manifest_payload["commit_sha"],
        environment=manifest_payload["environment"],
        manifest_path=manifest,
        manifest_payload=manifest_payload,
    )
    checklist.write_text(
        checklist.read_text(encoding="utf-8").replace(
            f"- Gate final strict: {_checklist_attachment_path(checklist, 'Gate final strict')}\n",
            "",
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, _validator_script(), "--manifest", str(manifest), "--regression-checklist", str(checklist)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    response_payload = json.loads(result.stdout)
    assert any(
        issue == "release_package_attachment_missing:gate final strict"
        for issue in response_payload["issues"]
    )
    assert any(
        issue == "checklist_checked_without_attachment:gate final strict"
        for issue in response_payload["issues"]
    )


def test_validate_operational_evidence_manifest_fails_when_checklist_attachment_is_not_backed_by_manifest(tmp_path):
    manifest = _build_manifest(tmp_path)
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    checklist = _build_release_regression_checklist(
        tmp_path,
        release_id=manifest_payload["release_id"],
        commit_sha=manifest_payload["commit_sha"],
        environment=manifest_payload["environment"],
        manifest_path=manifest,
        manifest_payload=manifest_payload,
    )
    foreign_attachment = _checklist_attachment_path(checklist, "Checklist de release")
    checklist.write_text(
        checklist.read_text(encoding="utf-8").replace(
            f"- E2E: {_checklist_attachment_path(checklist, 'E2E')}",
            f"- E2E: {foreign_attachment}",
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, _validator_script(), "--manifest", str(manifest), "--regression-checklist", str(checklist)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    response_payload = json.loads(result.stdout)
    assert any(
        issue.startswith("release_package_attachment_not_backed_by_manifest:e2e:")
        for issue in response_payload["issues"]
    )


def test_validate_operational_evidence_manifest_fails_when_required_attachment_json_has_no_domain_content(tmp_path):
    manifest = _build_manifest(tmp_path)
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    checklist = _build_release_regression_checklist(
        tmp_path,
        release_id=manifest_payload["release_id"],
        commit_sha=manifest_payload["commit_sha"],
        environment=manifest_payload["environment"],
        manifest_path=manifest,
        manifest_payload=manifest_payload,
    )
    alerts_artifact = Path(manifest_payload["checks"]["alerts_external_e2e"]["artifacts"][0])
    alerts_payload = json.loads(alerts_artifact.read_text(encoding="utf-8"))
    alerts_artifact.write_text(
        json.dumps(
            {
                "release_id": alerts_payload["release_id"],
                "commit_sha": alerts_payload["commit_sha"],
                "environment": alerts_payload["environment"],
                "generated_at": alerts_payload["generated_at"],
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, _validator_script(), "--manifest", str(manifest), "--regression-checklist", str(checklist)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    response_payload = json.loads(result.stdout)
    assert any(
        issue.startswith("release_package_attachment_unusable:alertas externos:")
        and issue.endswith(":json_without_domain_content")
        for issue in response_payload["issues"]
    )


def test_validate_operational_evidence_manifest_fails_when_package_is_coherent_but_incomplete(tmp_path):
    manifest = _build_manifest(tmp_path)
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    checklist = _build_release_regression_checklist(
        tmp_path,
        release_id=manifest_payload["release_id"],
        commit_sha=manifest_payload["commit_sha"],
        environment=manifest_payload["environment"],
        manifest_path=manifest,
        manifest_payload=manifest_payload,
    )
    smoke_pos_release = _checklist_attachment_path(checklist, "Smoke pos-release")
    smoke_pos_release.write_text("", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, _validator_script(), "--manifest", str(manifest), "--regression-checklist", str(checklist)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    response_payload = json.loads(result.stdout)
    assert any(
        issue.startswith("release_package_attachment_unusable:smoke pos-release:")
        and issue.endswith(":empty")
        for issue in response_payload["issues"]
    )


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


def test_validate_operational_evidence_manifest_fails_when_hash_has_unreferenced_artifact(tmp_path):
    manifest = _build_manifest(tmp_path)
    payload = _harden_manifest(manifest, signing_key=None)
    extra_artifact = tmp_path / "artifacts" / "homolog" / payload["release_id"] / "extra_foreign_artifact.json"
    extra_artifact.parent.mkdir(parents=True, exist_ok=True)
    extra_artifact.write_text(json.dumps({"success": True}), encoding="utf-8")
    payload["artifacts_sha256"][str(extra_artifact)] = _sha256_file(extra_artifact)
    manifest.write_text(json.dumps(payload), encoding="utf-8")

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
    assert any(issue.startswith("artifact_hash_unreferenced:") for issue in response_payload["issues"])


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


def test_validate_operational_evidence_manifest_fails_when_artifact_release_identity_mismatch(tmp_path):
    manifest = _build_manifest(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    smoke_artifact = Path(payload["checks"]["post_deploy_smoke"]["artifacts"][0])
    smoke_payload = json.loads(smoke_artifact.read_text(encoding="utf-8"))
    smoke_payload["release_id"] = "release_other_999"
    smoke_artifact.write_text(json.dumps(smoke_payload), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, _validator_script(), "--manifest", str(manifest)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    response_payload = json.loads(result.stdout)
    assert any(
        issue.startswith("artifact_identity_mismatch:post_deploy_smoke:release_id:")
        for issue in response_payload["issues"]
    )


def test_validate_operational_evidence_manifest_fails_when_artifact_commit_identity_mismatch(tmp_path):
    manifest = _build_manifest(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    metrics_artifact = Path(payload["checks"]["metrics_hardening"]["artifacts"][0])
    metrics_payload = json.loads(metrics_artifact.read_text(encoding="utf-8"))
    metrics_payload["commit_sha"] = "1111111111111111111111111111111111111111"
    metrics_artifact.write_text(json.dumps(metrics_payload), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, _validator_script(), "--manifest", str(manifest)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    response_payload = json.loads(result.stdout)
    assert any(
        issue.startswith("artifact_identity_mismatch:metrics_hardening:commit_sha:")
        for issue in response_payload["issues"]
    )


def test_validate_operational_evidence_manifest_fails_when_checklist_identity_mismatch(tmp_path):
    manifest = _build_manifest(tmp_path)
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    checklist = _build_release_regression_checklist(
        tmp_path,
        release_id=manifest_payload["release_id"],
        commit_sha=manifest_payload["commit_sha"],
        environment=manifest_payload["environment"],
        manifest_path=manifest,
        manifest_payload=manifest_payload,
        release_id_override="release_other_123",
    )

    result = subprocess.run(
        [sys.executable, _validator_script(), "--manifest", str(manifest), "--regression-checklist", str(checklist)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    response_payload = json.loads(result.stdout)
    assert any(
        issue.startswith("regression_checklist:release_id_mismatch:")
        for issue in response_payload["issues"]
    )


def test_validate_operational_evidence_manifest_fails_when_checklist_commit_identity_mismatch(tmp_path):
    manifest = _build_manifest(tmp_path)
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    checklist = _build_release_regression_checklist(
        tmp_path,
        release_id=manifest_payload["release_id"],
        commit_sha=manifest_payload["commit_sha"],
        environment=manifest_payload["environment"],
        manifest_path=manifest,
        manifest_payload=manifest_payload,
        commit_sha_override="2222222222222222222222222222222222222222",
    )

    result = subprocess.run(
        [sys.executable, _validator_script(), "--manifest", str(manifest), "--regression-checklist", str(checklist)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    response_payload = json.loads(result.stdout)
    assert any(
        issue.startswith("regression_checklist:commit_sha_mismatch:")
        for issue in response_payload["issues"]
    )


def test_validate_operational_evidence_manifest_fails_when_checklist_points_to_other_manifest(tmp_path):
    manifest = _build_manifest(tmp_path)
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    other_manifest = tmp_path / "foreign_manifest.json"
    other_manifest.write_text(
        json.dumps(
            {
                **manifest_payload,
                "release_id": "release_foreign_777",
            }
        ),
        encoding="utf-8",
    )
    checklist = _build_release_regression_checklist(
        tmp_path,
        release_id=manifest_payload["release_id"],
        commit_sha=manifest_payload["commit_sha"],
        environment=manifest_payload["environment"],
        manifest_path=manifest,
        manifest_payload=manifest_payload,
        manifest_ref_override=str(other_manifest),
    )

    result = subprocess.run(
        [sys.executable, _validator_script(), "--manifest", str(manifest), "--regression-checklist", str(checklist)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    response_payload = json.loads(result.stdout)
    assert any(
        issue.startswith("regression_checklist:manifest_reference_mismatch:")
        for issue in response_payload["issues"]
    )


def test_validate_operational_evidence_pre29_minimal_manifest_passes(tmp_path):
    manifest = _build_pre29_minimal_manifest(tmp_path)
    result = subprocess.run(
        [sys.executable, _validator_script(), "--manifest", str(manifest), "--profile", "pre29-minimal"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    payload = json.loads(result.stdout)
    assert payload["success"] is True
    assert payload["profile"] == "pre29-minimal"
    assert payload["required_checks"] == list(PRE29_MINIMAL_REQUIRED_CHECKS)


def test_validate_operational_evidence_pre29_minimal_manifest_fails_when_jobs_not_real_concurrency(tmp_path):
    manifest = _build_pre29_minimal_manifest(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    jobs_artifact = Path(payload["checks"]["jobs_drill"]["artifacts"][0])
    jobs_payload = json.loads(jobs_artifact.read_text(encoding="utf-8"))
    jobs_payload["concurrency_proof"]["peak_concurrent_executions"] = 1
    jobs_payload["probe_state"]["max_active_count"] = 1
    jobs_payload["concurrency_proof"]["distinct_success_workers"] = ["worker-1"]
    jobs_artifact.write_text(json.dumps(jobs_payload), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, _validator_script(), "--manifest", str(manifest), "--profile", "pre29-minimal"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    response_payload = json.loads(result.stdout)
    assert response_payload["success"] is False
    assert any(issue == "jobs_drill:peak_concurrency_below_2" for issue in response_payload["issues"])
