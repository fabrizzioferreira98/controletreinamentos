from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import subprocess
from copy import deepcopy
from dataclasses import dataclass
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


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class EvidenceValidationResult:
    ok: bool
    issues: list[str]
    checked_artifacts: int


def _load_manifest(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _resolve_artifact(root: Path, candidate: str) -> Path:
    artifact = Path((candidate or "").strip())
    if artifact.is_absolute():
        return artifact
    return (root / artifact).resolve()


def _artifact_has_release_segment(candidate: str, release_id: str) -> bool:
    if not (candidate or "").strip() or not (release_id or "").strip():
        return False
    normalized = str(candidate).replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    return release_id in parts


def _load_json_file(path: Path) -> dict | None:
    if path.suffix.lower() != ".json":
        return None
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
        # Artefatos operacionais podem conter linhas de log antes/depois do JSON.
        # Extraímos o primeiro objeto JSON válido do conteúdo.
        decoder = json.JSONDecoder()
        index = raw.find("{")
        while index != -1:
            try:
                payload, _end = decoder.raw_decode(raw[index:])
                if isinstance(payload, dict):
                    return payload
            except Exception:
                pass
            index = raw.find("{", index + 1)
        return None
    except Exception:
        return None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _signature_payload(payload: dict) -> str:
    canonical = deepcopy(payload)
    canonical.pop("signature_hmac_sha256", None)
    return json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _expected_signature(payload: dict, signing_key: str) -> str:
    body = _signature_payload(payload).encode("utf-8")
    key = signing_key.encode("utf-8")
    return hmac.new(key, body, hashlib.sha256).hexdigest()


def _git_head(root: Path) -> str | None:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=str(root),
                text=True,
                stderr=subprocess.DEVNULL,
            )
            .strip()
            .lower()
        )
    except Exception:
        return "workspace-without-git"


def _looks_like_pytest_pass_log(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
    except Exception:
        return False
    if "error collecting" in text or " interrupted" in text or " failed" in text:
        return False
    return bool(re.search(r"\b\d+\s+passed\b", text))


def _validate_semantics(
    check_name: str,
    artifacts: list[Path],
    issues: list[str],
    *,
    require_rollback_runtime_ids: bool = False,
    require_alert_ack: bool = False,
) -> None:
    json_payloads = [payload for payload in (_load_json_file(path) for path in artifacts) if payload is not None]

    if check_name == "e2e_homolog":
        pass_logs = [path for path in artifacts if _looks_like_pytest_pass_log(path)]
        if len(pass_logs) < 2:
            issues.append("e2e_runs_insufficient_or_invalid")
        return

    if check_name in {"load_authenticated_20w", "load_authenticated_30w"}:
        expected_workers = 20 if check_name.endswith("20w") else 30
        payload = next((p for p in json_payloads if int(p.get("workers", -1)) == expected_workers), None)
        if not payload:
            issues.append(f"{check_name}:missing_expected_workers_payload")
            return
        if int(payload.get("seconds", 0) or 0) < 300:
            issues.append(f"{check_name}:seconds_below_minimum_300")
        if not bool(payload.get("success")):
            issues.append(f"{check_name}:payload_success_false")
        if not bool(payload.get("authenticated")):
            issues.append(f"{check_name}:authenticated_false")
        if int(payload.get("requests", 0) or 0) <= 0:
            issues.append(f"{check_name}:requests_not_positive")
        if float(payload.get("availability_percent", 0.0) or 0.0) < 99.0:
            issues.append(f"{check_name}:availability_below_threshold")
        latency = payload.get("latency_ms", {}) if isinstance(payload.get("latency_ms"), dict) else {}
        if float(latency.get("p95", 0.0) or 0.0) > 1200.0:
            issues.append(f"{check_name}:p95_above_threshold")
        if payload.get("login_failures"):
            issues.append(f"{check_name}:login_failures_present")
        if int(payload.get("auth_failures", 0) or 0) > 0:
            issues.append(f"{check_name}:auth_failures_present")
        return

    if check_name == "jobs_concurrency_retry_dead_letter":
        payload = json_payloads[0] if json_payloads else None
        if not payload:
            issues.append("jobs_concurrency_retry_dead_letter:missing_json_payload")
            return
        if not bool(payload.get("success")):
            issues.append("jobs_concurrency_retry_dead_letter:payload_success_false")
        counts_final = payload.get("counts_final", {}) if isinstance(payload.get("counts_final"), dict) else {}
        if int(counts_final.get("queued", 0) or 0) != 0:
            issues.append("jobs_concurrency_retry_dead_letter:queued_not_zero")
        if int(counts_final.get("running", 0) or 0) != 0:
            issues.append("jobs_concurrency_retry_dead_letter:running_not_zero")
        return

    if check_name == "alerts_external_e2e":
        payload = json_payloads[0] if json_payloads else None
        if not payload:
            issues.append("alerts_external_e2e:missing_json_payload")
            return
        if not bool(payload.get("success")):
            issues.append("alerts_external_e2e:payload_success_false")
        status = int(payload.get("status", 0) or 0)
        if not (200 <= status <= 299):
            issues.append("alerts_external_e2e:http_status_not_2xx")
        if require_alert_ack:
            if not bool(payload.get("acknowledged")):
                issues.append("alerts_external_e2e:acknowledged_false")
            if not str(payload.get("acknowledged_by", "") or "").strip():
                issues.append("alerts_external_e2e:acknowledged_by_missing")
            if not str(payload.get("escalation_target", "") or "").strip():
                issues.append("alerts_external_e2e:escalation_target_missing")
        return

    if check_name == "backup_restore_drill":
        payload = json_payloads[0] if json_payloads else None
        if not payload:
            issues.append("backup_restore_drill:missing_json_payload")
            return
        if not bool(payload.get("success")):
            issues.append("backup_restore_drill:payload_success_false")
        steps = payload.get("steps", []) if isinstance(payload.get("steps"), list) else []
        restore_step = next((item for item in steps if item.get("step") == "restore_full"), None)
        if not restore_step or not bool(restore_step.get("success")):
            issues.append("backup_restore_drill:restore_full_not_success")
        return

    if check_name == "rollback_drill":
        smoke_payloads = [p for p in json_payloads if "failed" in p]
        if len(smoke_payloads) < 3:
            issues.append("rollback_drill:smoke_payloads_insufficient")
            return
        if any(bool(p.get("failed")) for p in smoke_payloads):
            issues.append("rollback_drill:smoke_failed_true")
        if require_rollback_runtime_ids:
            meta = next(
                (
                    payload
                    for payload in json_payloads
                    if all(
                        key in payload
                        for key in ("before_runtime_id", "rollback_runtime_id", "forward_runtime_id")
                    )
                ),
                None,
            )
            if not meta:
                issues.append("rollback_drill:missing_runtime_metadata")
                return
            if not bool(meta.get("success")):
                issues.append("rollback_drill:runtime_metadata_success_false")
            ids = [
                str(meta.get("before_runtime_id", "") or "").strip(),
                str(meta.get("rollback_runtime_id", "") or "").strip(),
                str(meta.get("forward_runtime_id", "") or "").strip(),
            ]
            if not all(ids):
                issues.append("rollback_drill:runtime_id_missing_value")
            if len(set(ids)) < 2:
                issues.append("rollback_drill:runtime_ids_not_distinct")
            for smoke_key in ("smoke_before_ok", "smoke_rollback_ok", "smoke_forward_ok"):
                if smoke_key in meta and not bool(meta.get(smoke_key)):
                    issues.append(f"rollback_drill:{smoke_key}_false")
        return

    if check_name == "post_deploy_smoke":
        payload = json_payloads[0] if json_payloads else None
        if not payload:
            issues.append("post_deploy_smoke:missing_json_payload")
            return
        if bool(payload.get("failed")):
            issues.append("post_deploy_smoke:failed_true")
        results = payload.get("results", [])
        if not isinstance(results, list) or not results:
            issues.append("post_deploy_smoke:results_missing_or_empty")
            return
        if any(not bool(item.get("ok")) for item in results if isinstance(item, dict)):
            issues.append("post_deploy_smoke:contains_failed_check")
        return

    if check_name == "metrics_hardening":
        payload = next((p for p in json_payloads if "without_token_status" in p), None)
        if not payload:
            issues.append("metrics_hardening:missing_hardening_payload")
            return
        if not bool(payload.get("success")):
            issues.append("metrics_hardening:payload_success_false")
        if str(payload.get("without_token_status")) not in {"403", "503"}:
            issues.append("metrics_hardening:without_token_status_invalid")
        if str(payload.get("invalid_token_status")) not in {"403", "503"}:
            issues.append("metrics_hardening:invalid_token_status_invalid")
        if str(payload.get("valid_token_status")) != "200":
            issues.append("metrics_hardening:valid_token_status_invalid")
        return


def validate_manifest(
    manifest_path: Path,
    *,
    root: Path,
    max_age_hours: int = 24,
    require_hashes: bool = False,
    require_signature: bool = False,
    signing_key_env: str = "RELEASE_EVIDENCE_SIGNING_KEY",
    require_rollback_runtime_ids: bool = False,
    require_alert_ack: bool = False,
) -> EvidenceValidationResult:
    issues: list[str] = []
    checked_artifacts = 0

    if not manifest_path.exists():
        return EvidenceValidationResult(ok=False, issues=[f"manifest_not_found: {manifest_path}"], checked_artifacts=0)

    try:
        payload = _load_manifest(manifest_path)
    except Exception as exc:
        return EvidenceValidationResult(ok=False, issues=[f"manifest_parse_error: {exc}"], checked_artifacts=0)

    for top_key in ("generated_at", "environment", "release_id", "commit_sha", "checks"):
        if top_key not in payload:
            issues.append(f"missing_top_level_key:{top_key}")

    artifact_hashes = payload.get("artifacts_sha256", {})
    if require_hashes and not isinstance(artifact_hashes, dict):
        issues.append("artifacts_sha256_missing_or_invalid")
        artifact_hashes = {}

    generated_at = str(payload.get("generated_at", "") or "").strip()
    try:
        generated_at_dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except Exception:
        generated_at_dt = None
        issues.append("generated_at_invalid")
    if generated_at_dt is not None:
        age = _now_utc() - generated_at_dt
        if age > timedelta(hours=max(1, int(max_age_hours))):
            issues.append(f"manifest_stale_older_than_{max_age_hours}h")
        if generated_at_dt > (_now_utc() + timedelta(minutes=5)):
            issues.append("generated_at_in_future")

    manifest_commit = str(payload.get("commit_sha", "") or "").strip().lower()
    git_head = _git_head(root)
    if not git_head:
        issues.append("git_head_unavailable_for_commit_match")
    elif manifest_commit != git_head:
        issues.append(f"commit_sha_mismatch:{manifest_commit}:head:{git_head}")

    release_id = str(payload.get("release_id", "") or "").strip()
    if not release_id:
        issues.append("release_id_empty")
    elif not re.match(r"^[A-Za-z0-9._:-]{6,128}$", release_id):
        issues.append("release_id_invalid_format")

    environment = str(payload.get("environment", "") or "").strip().lower()
    if environment not in {"homolog", "staging", "production"}:
        issues.append(f"environment_invalid:{environment or 'EMPTY'}")
    if require_signature:
        signature = str(payload.get("signature_hmac_sha256", "") or "").strip().lower()
        if not signature:
            issues.append("signature_missing")
        signing_key = (os.getenv(signing_key_env, "") or "").strip()
        if not signing_key:
            issues.append(f"signing_key_env_missing:{signing_key_env}")
        elif signature:
            expected = _expected_signature(payload, signing_key)
            if not hmac.compare_digest(signature, expected):
                issues.append("signature_invalid")
    checks = payload.get("checks", {})
    if not isinstance(checks, dict):
        issues.append("checks_must_be_object")
        checks = {}

    for check_name in REQUIRED_CHECKS:
        check_item = checks.get(check_name)
        if not isinstance(check_item, dict):
            issues.append(f"missing_check:{check_name}")
            continue

        status = str(check_item.get("status", "")).strip().upper()
        if status != "PASS":
            issues.append(f"check_not_pass:{check_name}:{status or 'EMPTY'}")

        artifacts = check_item.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            issues.append(f"missing_artifacts:{check_name}")
            continue

        resolved_artifacts: list[Path] = []
        for raw_artifact in artifacts:
            artifact_candidate = str(raw_artifact or "").strip()
            artifact_path = _resolve_artifact(root, artifact_candidate)
            checked_artifacts += 1
            if not artifact_path.exists():
                issues.append(f"artifact_not_found:{check_name}:{artifact_path}")
                continue
            if artifact_path.is_dir():
                issues.append(f"artifact_is_directory:{check_name}:{artifact_path}")
                continue
            if artifact_path.stat().st_size <= 0:
                issues.append(f"artifact_empty:{check_name}:{artifact_path}")
                continue
            if release_id and not _artifact_has_release_segment(artifact_candidate, release_id):
                issues.append(f"artifact_release_id_mismatch:{check_name}:{artifact_candidate}:expected:{release_id}")
                continue
            if require_hashes:
                expected_hash = str(artifact_hashes.get(artifact_candidate, "") or "").strip().lower()
                if not expected_hash:
                    issues.append(f"artifact_hash_missing:{check_name}:{artifact_candidate}")
                    continue
                actual_hash = _sha256_file(artifact_path).lower()
                if actual_hash != expected_hash:
                    issues.append(f"artifact_hash_mismatch:{check_name}:{artifact_candidate}")
                    continue
            resolved_artifacts.append(artifact_path)

        if resolved_artifacts:
            _validate_semantics(
                check_name,
                resolved_artifacts,
                issues,
                require_rollback_runtime_ids=require_rollback_runtime_ids,
                require_alert_ack=require_alert_ack,
            )

    return EvidenceValidationResult(ok=not issues, issues=issues, checked_artifacts=checked_artifacts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Valida evidencias operacionais obrigatorias para release.")
    parser.add_argument("--manifest", required=True, help="Caminho do manifest JSON de evidencias.")
    parser.add_argument("--max-age-hours", type=int, default=24, help="Idade maxima aceitavel do manifest.")
    parser.add_argument("--require-hashes", action="store_true", help="Exige hash SHA-256 para todos os artefatos.")
    parser.add_argument("--require-signature", action="store_true", help="Exige assinatura HMAC do manifest.")
    parser.add_argument(
        "--signing-key-env",
        default="RELEASE_EVIDENCE_SIGNING_KEY",
        help="Nome da variável de ambiente com a chave HMAC.",
    )
    parser.add_argument(
        "--require-rollback-runtime-ids",
        action="store_true",
        help="Exige metadados de runtime/instancia no rollback drill.",
    )
    parser.add_argument(
        "--require-alert-ack",
        action="store_true",
        help="Exige confirmação de ack/escalonamento no alerta externo.",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    manifest_path = Path(args.manifest).expanduser().resolve()
    result = validate_manifest(
        manifest_path,
        root=root,
        max_age_hours=max(1, int(args.max_age_hours)),
        require_hashes=bool(args.require_hashes),
        require_signature=bool(args.require_signature),
        signing_key_env=(args.signing_key_env or "").strip() or "RELEASE_EVIDENCE_SIGNING_KEY",
        require_rollback_runtime_ids=bool(args.require_rollback_runtime_ids),
        require_alert_ack=bool(args.require_alert_ack),
    )
    print(
        json.dumps(
            {
                "success": result.ok,
                "manifest": str(manifest_path),
                "required_checks": list(REQUIRED_CHECKS),
                "checked_artifacts": result.checked_artifacts,
                "issues": result.issues,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
