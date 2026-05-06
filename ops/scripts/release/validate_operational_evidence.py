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


RELEASE_REQUIRED_CHECKS = (
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

PROFILE_REQUIRED_CHECKS = {
    "release": RELEASE_REQUIRED_CHECKS,
    "pre29-minimal": PRE29_MINIMAL_REQUIRED_CHECKS,
}

CHECKLIST_IDENTITY_KEYS = {
    "release id": "release_id",
    "commit sha": "commit_sha",
    "ambiente": "environment",
    "manifest de evidencias": "manifest_path",
}

RELEASE_OPERATIONAL_WINDOW = timedelta(hours=12)
RELEASE_FUTURE_TOLERANCE = timedelta(minutes=30)
RELEASE_SEQUENCE_TOLERANCE = timedelta(minutes=15)
RELEASE_STRONG_PRE_GATE_CHECKS = (
    "e2e_homolog",
    "load_authenticated_20w",
    "load_authenticated_30w",
    "jobs_concurrency_retry_dead_letter",
    "alerts_external_e2e",
    "backup_restore_drill",
    "rollback_drill",
)

RELEASE_CHECKLIST_MANIFEST_ATTACHMENTS = {
    "e2e": ("e2e_homolog",),
    "carga autenticada": ("load_authenticated_20w", "load_authenticated_30w"),
    "jobs concorrentes": ("jobs_concurrency_retry_dead_letter",),
    "alertas externos": ("alerts_external_e2e",),
    "backup/restore": ("backup_restore_drill",),
    "rollback": ("rollback_drill",),
    "smoke": ("post_deploy_smoke",),
}

RELEASE_CHECKLIST_EXTERNAL_ATTACHMENTS = (
    "paridade minima entre ambientes",
    "gate final strict",
    "checklist de release",
    "checklist de rollback",
    "scheduler/cron ou declaracao de escopo",
    "storage/pdf/upload-download",
    "smoke pos-release",
)

RELEASE_CHECKLIST_CHECKBOX_ATTACHMENT_HINTS = {
    "jobs (enqueue, worker, retry, dead-letter) validados.": "jobs concorrentes",
    "backup/restore drill validado.": "backup/restore",
    "rollback drill validado (ida e volta).": "rollback",
    "carga autenticada validada dentro do slo.": "carga autenticada",
    "alertas externos validados ponta a ponta.": "alertas externos",
    "checklist de release preenchido no pacote externo do release.": "checklist de release",
    "checklist de rollback preenchido antes do deploy.": "checklist de rollback",
    "smoke pos-deploy validado.": "smoke",
    "gate final strict executado e anexado.": "gate final strict",
}


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


def _artifact_has_environment_segment(candidate: str, environment: str) -> bool:
    if not (candidate or "").strip() or not (environment or "").strip():
        return False
    normalized = str(candidate).replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    return environment in parts


def _normalized_candidate(candidate: str) -> str:
    return str(candidate or "").strip().replace("\\", "/")


def _load_checklist_pairs(path: Path) -> dict[str, str]:
    pairs: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return pairs

    for line in lines:
        match = re.match(r"^\s*-\s*(?P<key>[^:]+):\s*(?P<value>.*?)\s*$", line)
        if not match:
            continue
        key = str(match.group("key") or "").strip().lower()
        value = str(match.group("value") or "").strip()
        if key and value:
            pairs[key] = value
    return pairs


def _load_checklist_checkbox_states(path: Path) -> list[tuple[str, bool]]:
    states: list[tuple[str, bool]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return states

    for line in lines:
        match = re.match(r"^\s*-\s*\[(?P<state>[ xX])\]\s+(?P<label>.+?)\s*$", line)
        if not match:
            continue
        label = str(match.group("label") or "").strip().lower()
        checked = str(match.group("state") or "").strip().lower() == "x"
        if label:
            states.append((label, checked))
    return states


def _collect_manifest_artifact_candidates(checks: dict) -> set[str]:
    candidates: set[str] = set()
    if not isinstance(checks, dict):
        return candidates
    for check_item in checks.values():
        artifacts = check_item.get("artifacts", []) if isinstance(check_item, dict) else []
        if not isinstance(artifacts, list):
            continue
        for raw_artifact in artifacts:
            candidate = _normalized_candidate(str(raw_artifact or ""))
            if candidate:
                candidates.add(candidate)
    return candidates


def _resolve_optional_path(root: Path, candidate: str) -> Path | None:
    value = str(candidate or "").strip()
    if not value:
        return None
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (root / path).resolve()


def _load_checklist_identity(path: Path) -> dict[str, str]:
    identity = {
        "release_id": "",
        "commit_sha": "",
        "environment": "",
        "manifest_path": "",
    }
    pairs = _load_checklist_pairs(path)

    for key, target in CHECKLIST_IDENTITY_KEYS.items():
        value = str(pairs.get(key, "") or "").strip()
        if value:
            identity[target] = value

    identity["commit_sha"] = identity["commit_sha"].strip().lower()
    identity["environment"] = identity["environment"].strip().lower()
    return identity


def _parse_datetime_signal(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _path_mtime_utc(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except Exception:
        return None


def _json_payload_has_domain_content(payload: dict) -> bool:
    identity_keys = {
        "release_id",
        "commit_sha",
        "environment",
        "generated_at",
        "completed_at",
        "finished_at",
        "ended_at",
        "created_at",
        "timestamp",
        "manifest",
        "manifest_path",
        "evidence_manifest",
    }
    return any(str(key or "").strip().lower() not in identity_keys for key in payload)


def _attachment_unusable_reason(key: str, path: Path) -> str | None:
    if not path.exists():
        return "not_found"
    if path.is_dir():
        return "is_directory"
    if path.stat().st_size <= 0:
        return "empty"

    if path.suffix.lower() == ".json":
        payload = _load_json_file(path)
        if payload is None:
            return "json_unparseable"
        if not _json_payload_has_domain_content(payload):
            return "json_without_domain_content"
        return None

    try:
        text = path.read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:
        return "read_error"
    if not text:
        return "empty_text"
    lowered = text.lower()
    normalized_key = str(key or "").strip().lower()
    if normalized_key == "gate final strict" and "pass" not in lowered:
        return "missing_pass_marker"
    if normalized_key in {"checklist de release", "checklist de rollback"} and "- [" not in text:
        return "checklist_markers_missing"
    return None


def _artifact_temporal_signal(path: Path) -> tuple[datetime | None, str]:
    payload = _load_json_file(path)
    if payload:
        for key in ("generated_at", "completed_at", "finished_at", "ended_at", "created_at", "timestamp"):
            parsed = _parse_datetime_signal(payload.get(key))
            if parsed is not None:
                return parsed, f"json:{key}"
    return _path_mtime_utc(path), "mtime"


def _load_release_checklist_temporal_signals(path: Path, root: Path) -> dict[str, datetime]:
    signals: dict[str, datetime] = {}
    pairs = _load_checklist_pairs(path)
    timestamp_value = pairs.get("data/hora", "")
    timestamp = _parse_datetime_signal(timestamp_value)
    if timestamp is not None:
        signals["timestamp"] = timestamp

    gate_path = _resolve_optional_path(root, pairs.get("gate final strict", ""))
    if gate_path is not None and gate_path.exists() and gate_path.is_file():
        gate_mtime = _path_mtime_utc(gate_path)
        if gate_mtime is not None:
            signals["gate_final_strict"] = gate_mtime

    return signals


def _validate_release_package_temporal_coherence(
    *,
    manifest_path: Path,
    root: Path,
    payload: dict,
    resolved_artifacts: list[tuple[str, str, Path]],
    issues: list[str],
    regression_checklist: Path | None,
) -> None:
    manifest_time = _parse_datetime_signal(payload.get("generated_at"))
    if manifest_time is None:
        return

    timeline: list[datetime] = [manifest_time]
    latest_artifact_by_check: dict[str, datetime] = {}

    for check_name, _artifact_candidate, artifact_path in resolved_artifacts:
        artifact_time, _signal = _artifact_temporal_signal(artifact_path)
        if artifact_time is None:
            continue
        timeline.append(artifact_time)
        current_latest = latest_artifact_by_check.get(check_name)
        if current_latest is None or artifact_time > current_latest:
            latest_artifact_by_check[check_name] = artifact_time

        if artifact_time < (manifest_time - RELEASE_OPERATIONAL_WINDOW):
            issues.append(
                "artifact_reused_from_previous_execution:"
                f"{check_name}:{artifact_path}:{artifact_time.isoformat()}:manifest:{manifest_time.isoformat()}"
            )
        elif artifact_time > (manifest_time + RELEASE_FUTURE_TOLERANCE):
            issues.append(
                "artifact_time_out_of_window:"
                f"{check_name}:{artifact_path}:{artifact_time.isoformat()}:manifest:{manifest_time.isoformat()}"
            )

    latest_pre_gate_evidence = max(
        (
            latest_artifact_by_check[check_name]
            for check_name in RELEASE_STRONG_PRE_GATE_CHECKS
            if check_name in latest_artifact_by_check
        ),
        default=None,
    )
    post_deploy_smoke_time = latest_artifact_by_check.get("post_deploy_smoke")
    if latest_pre_gate_evidence is not None and post_deploy_smoke_time is not None:
        if post_deploy_smoke_time + RELEASE_SEQUENCE_TOLERANCE < latest_pre_gate_evidence:
            issues.append(
                "post_deploy_smoke_before_prerelease_evidence:"
                f"{post_deploy_smoke_time.isoformat()}:latest:{latest_pre_gate_evidence.isoformat()}"
            )

    if regression_checklist is not None and regression_checklist.exists():
        checklist_signals = _load_release_checklist_temporal_signals(regression_checklist, root)

        checklist_time = checklist_signals.get("timestamp")
        if checklist_time is not None:
            timeline.append(checklist_time)
            if checklist_time < (manifest_time - RELEASE_OPERATIONAL_WINDOW) or checklist_time > (
                manifest_time + RELEASE_FUTURE_TOLERANCE
            ):
                issues.append(
                    "regression_checklist:timestamp_out_of_window:"
                    f"{checklist_time.isoformat()}:manifest:{manifest_time.isoformat()}"
                )

        gate_time = checklist_signals.get("gate_final_strict")
        if gate_time is not None:
            timeline.append(gate_time)
            if gate_time < (manifest_time - RELEASE_OPERATIONAL_WINDOW) or gate_time > (
                manifest_time + RELEASE_FUTURE_TOLERANCE
            ):
                issues.append(
                    "gate_final_strict:timestamp_out_of_window:"
                    f"{gate_time.isoformat()}:manifest:{manifest_time.isoformat()}"
                )
            if latest_pre_gate_evidence is not None and gate_time + RELEASE_SEQUENCE_TOLERANCE < latest_pre_gate_evidence:
                issues.append(
                    "gate_final_strict_before_prerelease_evidence:"
                    f"{gate_time.isoformat()}:latest:{latest_pre_gate_evidence.isoformat()}"
                )
            if post_deploy_smoke_time is not None and post_deploy_smoke_time + RELEASE_SEQUENCE_TOLERANCE < gate_time:
                issues.append(
                    "post_deploy_smoke_before_gate:"
                    f"{post_deploy_smoke_time.isoformat()}:gate:{gate_time.isoformat()}"
                )

    if timeline:
        earliest = min(timeline)
        latest = max(timeline)
        if (latest - earliest) > RELEASE_OPERATIONAL_WINDOW:
            issues.append(
                "release_package_time_window_exceeded:"
                f"{earliest.isoformat()}:latest:{latest.isoformat()}:manifest:{manifest_path}"
            )


def _validate_release_package_completeness(
    *,
    root: Path,
    resolved_artifacts: list[tuple[str, str, Path]],
    issues: list[str],
    regression_checklist: Path | None,
) -> None:
    if regression_checklist is None or not regression_checklist.exists():
        return

    checklist_pairs = _load_checklist_pairs(regression_checklist)
    checklist_checkbox_states = _load_checklist_checkbox_states(regression_checklist)
    resolved_by_check: dict[str, set[Path]] = {}
    for check_name, _artifact_candidate, artifact_path in resolved_artifacts:
        resolved_by_check.setdefault(check_name, set()).add(artifact_path.resolve())

    attachment_values: dict[str, str] = {}
    for key in RELEASE_CHECKLIST_EXTERNAL_ATTACHMENTS:
        attachment_values[key] = str(checklist_pairs.get(key, "") or "").strip()
    for key in RELEASE_CHECKLIST_MANIFEST_ATTACHMENTS:
        attachment_values[key] = str(checklist_pairs.get(key, "") or "").strip()

    for key, value in attachment_values.items():
        if not value:
            issues.append(f"release_package_attachment_missing:{key}")

    for label, checked in checklist_checkbox_states:
        if not checked:
            continue
        attachment_key = RELEASE_CHECKLIST_CHECKBOX_ATTACHMENT_HINTS.get(label)
        if attachment_key and not attachment_values.get(attachment_key, ""):
            issues.append(f"checklist_checked_without_attachment:{attachment_key}")

    for key, value in attachment_values.items():
        if not value:
            continue
        resolved_path = _resolve_optional_path(root, value)
        if resolved_path is None:
            issues.append(f"release_package_attachment_missing:{key}")
            continue

        unusable_reason = _attachment_unusable_reason(key, resolved_path)
        if unusable_reason is not None:
            issues.append(f"release_package_attachment_unusable:{key}:{resolved_path}:{unusable_reason}")
            continue

        if key in RELEASE_CHECKLIST_MANIFEST_ATTACHMENTS:
            expected_checks = RELEASE_CHECKLIST_MANIFEST_ATTACHMENTS[key]
            allowed_paths = {
                artifact_path
                for check_name in expected_checks
                for artifact_path in resolved_by_check.get(check_name, set())
            }
            if resolved_path.resolve() not in allowed_paths:
                issues.append(f"release_package_attachment_not_backed_by_manifest:{key}:{resolved_path}")


def _validate_release_package_identity(
    *,
    manifest_path: Path,
    root: Path,
    payload: dict,
    checks: dict,
    artifact_hashes: dict,
    resolved_artifacts: list[tuple[str, str, Path]],
    issues: list[str],
    require_hashes: bool,
    regression_checklist: Path | None,
) -> None:
    release_id = str(payload.get("release_id", "") or "").strip()
    commit_sha = str(payload.get("commit_sha", "") or "").strip().lower()
    environment = str(payload.get("environment", "") or "").strip().lower()

    if regression_checklist is not None:
        if not regression_checklist.exists():
            issues.append(f"regression_checklist_not_found:{regression_checklist}")
        else:
            checklist_identity = _load_checklist_identity(regression_checklist)
            checklist_release_id = checklist_identity.get("release_id", "").strip()
            checklist_commit_sha = checklist_identity.get("commit_sha", "").strip().lower()
            checklist_environment = checklist_identity.get("environment", "").strip().lower()
            checklist_manifest_path = checklist_identity.get("manifest_path", "").strip()

            if checklist_release_id and release_id and checklist_release_id != release_id:
                issues.append(
                    f"regression_checklist:release_id_mismatch:{checklist_release_id}:expected:{release_id}"
                )
            if checklist_commit_sha and commit_sha and checklist_commit_sha != commit_sha:
                issues.append(
                    f"regression_checklist:commit_sha_mismatch:{checklist_commit_sha}:expected:{commit_sha}"
                )
            if checklist_environment and environment and checklist_environment != environment:
                issues.append(
                    f"regression_checklist:environment_mismatch:{checklist_environment}:expected:{environment}"
                )

            resolved_manifest_ref = _resolve_optional_path(root, checklist_manifest_path)
            if resolved_manifest_ref is not None and resolved_manifest_ref != manifest_path:
                issues.append(
                    "regression_checklist:manifest_reference_mismatch:"
                    f"{resolved_manifest_ref}:expected:{manifest_path}"
                )

    expected_candidates = _collect_manifest_artifact_candidates(checks)
    if require_hashes and isinstance(artifact_hashes, dict):
        provided_candidates = {_normalized_candidate(str(candidate or "")) for candidate in artifact_hashes}
        for candidate in sorted(item for item in provided_candidates - expected_candidates if item):
            issues.append(f"artifact_hash_unreferenced:{candidate}")

    for check_name, _artifact_candidate, artifact_path in resolved_artifacts:
        json_payload = _load_json_file(artifact_path)
        if not json_payload:
            continue

        artifact_release_id = str(json_payload.get("release_id", "") or "").strip()
        artifact_commit_sha = str(json_payload.get("commit_sha", "") or "").strip().lower()
        artifact_environment = str(json_payload.get("environment", "") or "").strip().lower()
        artifact_manifest_path = _resolve_optional_path(
            root,
            str(
                json_payload.get("evidence_manifest")
                or json_payload.get("manifest_path")
                or json_payload.get("manifest")
                or ""
            ),
        )

        if artifact_release_id and release_id and artifact_release_id != release_id:
            issues.append(
                f"artifact_identity_mismatch:{check_name}:release_id:{artifact_release_id}:expected:{release_id}"
            )
        if artifact_commit_sha and commit_sha and artifact_commit_sha != commit_sha:
            issues.append(
                f"artifact_identity_mismatch:{check_name}:commit_sha:{artifact_commit_sha}:expected:{commit_sha}"
            )
        if artifact_environment and environment and artifact_environment != environment:
            issues.append(
                f"artifact_identity_mismatch:{check_name}:environment:{artifact_environment}:expected:{environment}"
            )
        if artifact_manifest_path is not None and artifact_manifest_path != manifest_path:
            issues.append(
                f"artifact_identity_mismatch:{check_name}:manifest_path:{artifact_manifest_path}:expected:{manifest_path}"
            )


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


def _looks_like_ci_validation_log(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    lowered = text.lower()
    if "ci validation: pass" not in lowered:
        return False
    if "frontend build generated at:" not in lowered:
        return False
    if not re.search(r"\b\d+\s+passed\b", lowered):
        return False
    return True


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

    if check_name == "ci_validation":
        if not any(_looks_like_ci_validation_log(path) for path in artifacts):
            issues.append("ci_validation:missing_pass_log")
        return

    if check_name == "repo_hygiene":
        payload = json_payloads[0] if json_payloads else None
        if not payload:
            issues.append("repo_hygiene:missing_json_payload")
            return
        if not bool(payload.get("success")):
            issues.append("repo_hygiene:payload_success_false")
        violations = payload.get("violations", [])
        if not isinstance(violations, list):
            issues.append("repo_hygiene:violations_not_list")
        elif violations:
            issues.append("repo_hygiene:violations_present")
        return

    if check_name == "auth_session":
        payload = json_payloads[0] if json_payloads else None
        if not payload:
            issues.append("auth_session:missing_json_payload")
            return
        if not bool(payload.get("success")):
            issues.append("auth_session:payload_success_false")
        required_truthy = (
            "login_page_ok",
            "login_success_redirect",
            "session_authenticated",
            "csrf_token_present",
            "logout_ok",
            "post_logout_redirect_ok",
        )
        for field_name in required_truthy:
            if not bool(payload.get(field_name)):
                issues.append(f"auth_session:{field_name}_false")
        return

    if check_name == "storage_docs":
        payload = json_payloads[0] if json_payloads else None
        if not payload:
            issues.append("storage_docs:missing_json_payload")
            return
        if not bool(payload.get("ok")):
            issues.append("storage_docs:payload_ok_false")
        summary = (
            payload.get("post_restore_validation", {})
            if isinstance(payload.get("post_restore_validation"), dict)
            else {}
        )
        if str(summary.get("status_key", "") or "").strip().lower() != "operational":
            issues.append("storage_docs:status_not_operational")
        if int(summary.get("critical_count", 0) or 0) != 0:
            issues.append("storage_docs:critical_count_not_zero")
        if int(summary.get("warning_count", 0) or 0) != 0:
            issues.append("storage_docs:warning_count_not_zero")
        if int(summary.get("document_row_count", 0) or 0) <= 0:
            issues.append("storage_docs:document_rows_missing")
        if int(summary.get("photo_row_count", 0) or 0) <= 0:
            issues.append("storage_docs:photo_rows_missing")
        contract = payload.get("restore_contract", {}) if isinstance(payload.get("restore_contract"), dict) else {}
        if contract and not bool(contract.get("success")):
            issues.append("storage_docs:restore_contract_false")
        return

    if check_name == "db_consistency":
        payload = json_payloads[0] if json_payloads else None
        if not payload:
            issues.append("db_consistency:missing_json_payload")
            return
        if not bool(payload.get("ok")):
            issues.append("db_consistency:payload_ok_false")
        schema = payload.get("schema", {}) if isinstance(payload.get("schema"), dict) else {}
        data = payload.get("data", {}) if isinstance(payload.get("data"), dict) else {}
        if not bool(schema.get("is_consistent")):
            issues.append("db_consistency:schema_not_consistent")
        if int(data.get("total_issues", 0) or 0) != 0:
            issues.append("db_consistency:data_issues_present")
        return

    if check_name == "jobs_drill":
        payload = json_payloads[0] if json_payloads else None
        if not payload:
            issues.append("jobs_drill:missing_json_payload")
            return
        if not bool(payload.get("success")):
            issues.append("jobs_drill:payload_success_false")
        if str(payload.get("success_job_type", "") or "").strip().lower() != "probe":
            issues.append("jobs_drill:success_job_type_not_probe")
        counts_final = payload.get("counts_final", {}) if isinstance(payload.get("counts_final"), dict) else {}
        if int(counts_final.get("queued", 0) or 0) != 0:
            issues.append("jobs_drill:queued_not_zero")
        if int(counts_final.get("running", 0) or 0) != 0:
            issues.append("jobs_drill:running_not_zero")
        concurrency = payload.get("concurrency_proof", {}) if isinstance(payload.get("concurrency_proof"), dict) else {}
        if int(concurrency.get("peak_concurrent_executions", 0) or 0) < 2:
            issues.append("jobs_drill:peak_concurrency_below_2")
        distinct_workers = concurrency.get("distinct_success_workers", [])
        if not isinstance(distinct_workers, list) or len(distinct_workers) < 2:
            issues.append("jobs_drill:distinct_success_workers_below_2")
        probe_state = payload.get("probe_state", {}) if isinstance(payload.get("probe_state"), dict) else {}
        if int(probe_state.get("max_active_count", 0) or 0) < 2:
            issues.append("jobs_drill:max_active_count_below_2")
        return

    if check_name == "backup_restore":
        payload = json_payloads[0] if json_payloads else None
        if not payload:
            issues.append("backup_restore:missing_json_payload")
            return
        if not bool(payload.get("success")):
            issues.append("backup_restore:payload_success_false")
        steps = payload.get("steps", []) if isinstance(payload.get("steps"), list) else []
        restore_step = next((item for item in steps if item.get("step") == "restore_full"), None)
        if not restore_step or not bool(restore_step.get("success")):
            issues.append("backup_restore:restore_full_not_success")
            return
        if not bool(restore_step.get("counts_match")):
            issues.append("backup_restore:counts_match_false")
        postcheck_step = next((item for item in steps if item.get("step") == "restore_postcheck"), None)
        if not postcheck_step or not bool(postcheck_step.get("success")):
            issues.append("backup_restore:restore_postcheck_not_success")
        else:
            postcheck = (
                postcheck_step.get("postcheck_result", {})
                if isinstance(postcheck_step.get("postcheck_result"), dict)
                else {}
            )
            if postcheck and not bool(postcheck.get("ok")):
                issues.append("backup_restore:postcheck_payload_ok_false")
        contract_step = next((item for item in steps if item.get("step") == "canonical_restore_artifacts"), None)
        if not contract_step or not bool(contract_step.get("success")):
            issues.append("backup_restore:canonical_restore_artifacts_not_success")
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
    profile: str = "release",
    regression_checklist: Path | None = None,
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

    required_checks = PROFILE_REQUIRED_CHECKS.get(profile, RELEASE_REQUIRED_CHECKS)
    resolved_artifact_entries: list[tuple[str, str, Path]] = []

    for check_name in required_checks:
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
            if profile == "release" and environment and not _artifact_has_environment_segment(artifact_candidate, environment):
                issues.append(
                    f"artifact_environment_mismatch:{check_name}:{artifact_candidate}:expected:{environment}"
                )
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
            resolved_artifact_entries.append((check_name, artifact_candidate, artifact_path))

        if resolved_artifacts:
            _validate_semantics(
                check_name,
                resolved_artifacts,
                issues,
                require_rollback_runtime_ids=require_rollback_runtime_ids,
                require_alert_ack=require_alert_ack,
            )

    if profile == "release":
        _validate_release_package_identity(
            manifest_path=manifest_path,
            root=root,
            payload=payload,
            checks=checks,
            artifact_hashes=artifact_hashes,
            resolved_artifacts=resolved_artifact_entries,
            issues=issues,
            require_hashes=require_hashes,
            regression_checklist=regression_checklist,
        )
        _validate_release_package_temporal_coherence(
            manifest_path=manifest_path,
            root=root,
            payload=payload,
            resolved_artifacts=resolved_artifact_entries,
            issues=issues,
            regression_checklist=regression_checklist,
        )
        _validate_release_package_completeness(
            root=root,
            resolved_artifacts=resolved_artifact_entries,
            issues=issues,
            regression_checklist=regression_checklist,
        )

    return EvidenceValidationResult(ok=not issues, issues=issues, checked_artifacts=checked_artifacts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Valida evidencias operacionais obrigatorias para release.")
    parser.add_argument("--manifest", required=True, help="Caminho do manifest JSON de evidencias.")
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILE_REQUIRED_CHECKS),
        default="release",
        help="Perfil de evidencias exigidas.",
    )
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
    parser.add_argument(
        "--regression-checklist",
        default="",
        help="Checklist de regressao preenchido para validar identidade transversal do pacote release.",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    manifest_path = Path(args.manifest).expanduser().resolve()
    regression_checklist = None
    if (args.regression_checklist or "").strip():
        regression_checklist = Path(args.regression_checklist).expanduser()
        if not regression_checklist.is_absolute():
            regression_checklist = (root / regression_checklist).resolve()
        else:
            regression_checklist = regression_checklist.resolve()
    result = validate_manifest(
        manifest_path,
        root=root,
        max_age_hours=max(1, int(args.max_age_hours)),
        require_hashes=bool(args.require_hashes),
        require_signature=bool(args.require_signature),
        signing_key_env=(args.signing_key_env or "").strip() or "RELEASE_EVIDENCE_SIGNING_KEY",
        require_rollback_runtime_ids=bool(args.require_rollback_runtime_ids),
        require_alert_ack=bool(args.require_alert_ack),
        profile=str(args.profile or "release").strip() or "release",
        regression_checklist=regression_checklist,
    )
    required_checks = PROFILE_REQUIRED_CHECKS.get(args.profile, RELEASE_REQUIRED_CHECKS)
    print(
        json.dumps(
            {
                "success": result.ok,
                "manifest": str(manifest_path),
                "profile": args.profile,
                "required_checks": list(required_checks),
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
