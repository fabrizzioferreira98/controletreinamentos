from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


REQUIRED_METADATA = (
    "Release ID",
    "Commit SHA",
    "Ambiente",
    "Responsavel tecnico",
    "Data/hora",
)

CHECKBOX_RE = re.compile(r"^\s*-\s*\[(?P<state>[ xX])\]\s+(?P<label>.+?)\s*$")
DECISION_RE = re.compile(r"^\s*-\s*Resultado:\s*(?P<value>.+?)\s*$", re.IGNORECASE)
EVIDENCE_RE = re.compile(r"^\s*-\s*Manifest de evidencias:\s*(?P<value>.+?)\s*$", re.IGNORECASE)
META_RE = re.compile(r"^\s*-\s*(?P<key>[^:]+):\s*(?P<value>.*?)\s*$")
EVIDENCE_ATTACHMENT_KEYS = (
    "E2E",
    "Carga autenticada",
    "Jobs concorrentes",
    "Alertas externos",
    "Backup/restore",
    "Rollback",
    "Smoke",
)


@dataclass
class ChecklistValidationResult:
    ok: bool
    issues: list[str]
    checked_items: int


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


def validate_checklist(
    checklist_path: Path,
    *,
    root: Path,
    expected_release_id: str = "",
    expected_environment: str = "",
    require_decision: bool = True,
    enforce_head_commit_match: bool = True,
    allowed_results: tuple[str, ...] = ("GO", "GO CONDICIONAL"),
) -> ChecklistValidationResult:
    issues: list[str] = []
    checked_items = 0
    if not checklist_path.exists():
        return ChecklistValidationResult(ok=False, issues=[f"checklist_not_found:{checklist_path}"], checked_items=0)

    try:
        lines = checklist_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception as exc:
        return ChecklistValidationResult(ok=False, issues=[f"checklist_read_error:{exc}"], checked_items=0)

    metadata: dict[str, str] = {}
    decision_value = ""
    evidence_manifest_value = ""
    evidence_attachments: dict[str, str] = {}
    checkbox_items: list[tuple[str, bool]] = []

    for line in lines:
        m = META_RE.match(line)
        if m:
            key = (m.group("key") or "").strip()
            value = (m.group("value") or "").strip()
            if key:
                metadata[key] = value
                if key in EVIDENCE_ATTACHMENT_KEYS:
                    evidence_attachments[key] = value
        m = DECISION_RE.match(line)
        if m:
            decision_value = (m.group("value") or "").strip().upper()
        m = EVIDENCE_RE.match(line)
        if m:
            evidence_manifest_value = (m.group("value") or "").strip()
        m = CHECKBOX_RE.match(line)
        if m:
            checked = (m.group("state") or "").strip().lower() == "x"
            label = (m.group("label") or "").strip()
            checkbox_items.append((label, checked))

    for key in REQUIRED_METADATA:
        value = (metadata.get(key, "") or "").strip()
        if not value:
            issues.append(f"metadata_missing:{key}")

    checklist_release_id = (metadata.get("Release ID", "") or "").strip()
    if expected_release_id and checklist_release_id and checklist_release_id != expected_release_id:
        issues.append(f"release_id_mismatch:{checklist_release_id}:expected:{expected_release_id}")
    if expected_release_id:
        for key in EVIDENCE_ATTACHMENT_KEYS:
            value = (evidence_attachments.get(key, "") or "").strip()
            if not value:
                continue
            if expected_release_id not in value:
                issues.append(f"evidence_release_id_mismatch:{key}:{value}:expected:{expected_release_id}")

    checklist_environment = (metadata.get("Ambiente", "") or "").strip().lower()
    if expected_environment and checklist_environment and checklist_environment != expected_environment.lower():
        issues.append(f"environment_mismatch:{checklist_environment}:expected:{expected_environment.lower()}")

    manifest_path = evidence_manifest_value
    if not manifest_path:
        issues.append("evidence_manifest_missing")
    else:
        resolved_manifest = Path(manifest_path).expanduser()
        if not resolved_manifest.is_absolute():
            resolved_manifest = (root / resolved_manifest).resolve()
        if not resolved_manifest.exists():
            issues.append(f"evidence_manifest_not_found:{resolved_manifest}")

    commit_sha = (metadata.get("Commit SHA", "") or "").strip().lower()
    if not commit_sha:
        issues.append("metadata_missing:Commit SHA")
    elif enforce_head_commit_match:
        git_head = _git_head(root)
        if git_head and commit_sha and commit_sha != git_head:
            issues.append(f"commit_sha_mismatch:{commit_sha}:head:{git_head}")

    if not checkbox_items:
        issues.append("checklist_items_missing")
    else:
        for label, checked in checkbox_items:
            checked_items += 1
            if not checked:
                issues.append(f"checklist_item_unchecked:{label}")

    if require_decision:
        if not decision_value:
            issues.append("decision_missing")
        elif decision_value not in {item.upper() for item in allowed_results}:
            issues.append(f"decision_invalid:{decision_value}")

    return ChecklistValidationResult(ok=not issues, issues=issues, checked_items=checked_items)


def main() -> int:
    parser = argparse.ArgumentParser(description="Valida checklist de regressão obrigatória para release.")
    parser.add_argument("--checklist", required=True, help="Caminho do checklist markdown.")
    parser.add_argument("--expected-release-id", default="", help="Release ID esperado.")
    parser.add_argument("--expected-environment", default="", help="Ambiente esperado (homolog/staging/production).")
    parser.add_argument(
        "--allowed-results",
        default="GO,GO CONDICIONAL",
        help="Resultados aceitos em Decisão/Resultado, separados por vírgula.",
    )
    parser.add_argument(
        "--skip-head-commit-check",
        action="store_true",
        help="Não compara Commit SHA do checklist com git HEAD (útil em releases com checklist versionado).",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    checklist_path = Path(args.checklist).expanduser().resolve()
    allowed = tuple(item.strip() for item in (args.allowed_results or "").split(",") if item.strip()) or ("GO",)
    result = validate_checklist(
        checklist_path,
        root=root,
        expected_release_id=(args.expected_release_id or "").strip(),
        expected_environment=(args.expected_environment or "").strip(),
        enforce_head_commit_match=not bool(args.skip_head_commit_check),
        allowed_results=allowed,
    )
    print(
        json.dumps(
            {
                "success": result.ok,
                "checklist": str(checklist_path),
                "checked_items": result.checked_items,
                "issues": result.issues,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
