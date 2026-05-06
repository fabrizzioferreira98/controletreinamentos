from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path


OFFICIAL_ROOT_DIRECTORIES = {
    ".github",
    "archive",
    "backend",
    "docs",
    "frontend",
    "legacy",
    "ops",
    "scripts",
    "tests",
}

SKIP_SCAN_DIRECTORIES = {
    ".git",
}

CLASSIFIED_ARCHIVE_PREFIXES = (
    "archive",
    "docs/archive",
    "docs/migration/retired-platforms",
)

FORBIDDEN_ROOT_DIRECTORIES: dict[str, tuple[str, str]] = {
    "controle-treinamentos": (
        "nested_repo_copy",
        "nested repository copies create a second apparent product root; use docs/governance/nested-repo-classification.md",
    ),
    ".tmp": (
        "historical_residue",
        "temporary backups and ad hoc residue must not reappear in the root; classify them under archive/ or remove them",
    ),
    ".vscode": ("local_environment", "editor settings are local environment, not repository architecture"),
    "venv": ("generated_artifact", "local virtual environments must not live inside the repository"),
    "frontend/_backup": (
        "backup",
        "frontend backup directories must not live in the live tree; classify them under archive/temp-backups or remove them",
    ),
    "backend/runtime": ("mutable_state", "runtime state must stay outside the repository"),
    "ops/evidence": ("operational_evidence", "live operational evidence must stay outside the repository"),
    "ops/backups": (
        "backup",
        "operational backups must stay outside the repository; historical classified backups belong in archive/temp-backups",
    ),
    "ops/artifacts": ("generated_artifact", "generated operational artifacts must stay outside the repository"),
    "logs": ("mutable_state", "runtime logs must stay outside the repository"),
}

FORBIDDEN_GLOB_DIRECTORIES: dict[str, tuple[str, str]] = {
    "frontend/prod-backup-*": (
        "backup",
        "frontend backup snapshots must not live in the live tree; classify them under archive/repo-snapshots or remove them",
    ),
}

DATED_ARCHIVABLE_NAME_RE = re.compile(r"(?:^|[-_])20\d{6}(?:[-_.]|$)")

ROOT_ARCHIVE_FILE_SUFFIXES = (
    ".7z",
    ".gz",
    ".rar",
    ".tar",
    ".tgz",
    ".zip",
)

ROOT_BACKUP_FILE_SUFFIXES = (
    ".bak",
    ".dump",
    ".sql",
)

ROOT_SNAPSHOT_TOKENS = (
    "snapshot",
)

ROOT_BACKUP_TOKENS = (
    "backup",
    "dump",
)

FORBIDDEN_DIRECTORY_NAMES: dict[str, tuple[str, str]] = {
    "__pycache__": ("generated_artifact", "python bytecode cache directories must not live in the repository"),
    ".pytest_cache": ("generated_artifact", "pytest cache directories must not live in the repository"),
    ".mypy_cache": ("generated_artifact", "mypy cache directories must not live in the repository"),
    ".ruff_cache": ("generated_artifact", "ruff cache directories must not live in the repository"),
}

EXPLICIT_LOCAL_DIRECTORY_EXCEPTIONS: dict[str, str] = {
    ".venv": (
        "workspace-local Python environment; allowed only at the repository root as a gitignored developer convenience "
        "and never as official topology or runtime authority"
    ),
    "frontend/dist": (
        "workspace-local frontend publish artifact; allowed only at the canonical build output path as generated, "
        "gitignored output and never as source of truth"
    ),
    "runtime": (
        "workspace-local mutable runtime/evidence scratch area; allowed only at the repository root as gitignored "
        "local output and never as source, release artifact, or documentation authority"
    ),
    "ops/artifacts": (
        "workspace-local operational artifact/evidence output; allowed only as gitignored local history and never "
        "as source, canonical runtime input, or documentation authority"
    ),
}

EXPLICIT_LOCAL_FILE_EXCEPTIONS: dict[str, str] = {
    ".env": (
        "workspace-local sensitive runtime configuration; allowed only at the repository root as gitignored local "
        "input and never as committed source or template"
    ),
}

TEXT_SCAN_ROOTS = (
    ".github/workflows",
    "docs/operations",
    "ops/scripts",
)

SISTEMA_CONTROLE_ALLOWED_CODE_PATHS = {
    "backend/src/controle_treinamentos/cache.py",
    "backend/src/controle_treinamentos/core/sistema_controle_policy.py",
    "backend/src/controle_treinamentos/blueprints/admin/routes.py",
    "backend/src/controle_treinamentos/db/schema.py",
    "backend/src/controle_treinamentos/db/seeder.py",
    "backend/src/controle_treinamentos/infra/mailer.py",
    "backend/src/controle_treinamentos/monitoring/_monitoring_impl.py",
}

TEXT_EXTENSIONS = {
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}

LIVE_DOC_EXTENSIONS = {
    ".html",
    ".json",
    ".md",
    ".pdf",
}

LIVE_DOC_ALLOWED_PATHS = {
    "docs/architecture/architecture.md",
    "docs/architecture/document_layer_policy.md",
    "docs/architecture/document_storage_policy.md",
    "docs/architecture/file_access_policy.md",
    "docs/architecture/file_classic_risks.md",
    "docs/architecture/file_persistence_policy.md",
    "docs/architecture/frontend_architecture.md",
    "docs/architecture/financeiro/adr-001-novo-dominio-financeiro-nao-restauracao-legado.md",
    "docs/architecture/financeiro/adr-002-financeiro-modular-flask-spa.md",
    "docs/architecture/financeiro/adr-003-backend-fonte-verdade-calculos.md",
    "docs/architecture/financeiro/adr-004-separacao-fatos-calculos-parametros-fechamento.md",
    "docs/architecture/financeiro/adr-005-org-scope-evolucao-saas.md",
    "docs/architecture/financeiro/adr-006-contratos-http-financeiro-api-v1.md",
    "docs/architecture/financeiro/adr-007-rbac-audit-log-trilha-calculo.md",
    "docs/architecture/financeiro/adr-008-parametros-vigencia-snapshots-fechamento.md",
    "docs/architecture/financeiro/baseline-api-financeiro.md",
    "docs/architecture/financeiro/catalogo-audit-log-financeiro.md",
    "docs/architecture/financeiro/checklist-pre-schema-financeiro.md",
    "docs/architecture/financeiro/contrato-memoria-calculo-financeiro.md",
    "docs/architecture/financeiro/contratos-dominio-financeiro.md",
    "docs/architecture/financeiro/glossario-dominio-financeiro.md",
    "docs/architecture/financeiro/matriz-rbac-financeiro.md",
    "docs/architecture/financeiro/org-scope-placeholder-financeiro.md",
    "docs/architecture/financeiro/readme.md",
    "docs/architecture/financeiro/run-financeiro-postgres-test.md",
    "docs/architecture/financeiro/visao-tecnica-financeiro.md",
    "docs/architecture/pdf_document_policy.md",
    "docs/architecture/storage_naming_policy.md",
    "docs/architecture/upload_policy.md",
    "docs/governance/documentation-governance.md",
    "docs/governance/legacy-policy.md",
    "docs/governance/nested-repo-classification.md",
    "docs/governance/removal-backlog.md",
    "docs/governance/repository-governance.md",
    "docs/governance/repo-topology.md",
    "docs/governance/root-entry-policy.md",
    "docs/governance/technical-conventions.md",
    "docs/governance/tmp-classification.md",
    "docs/operations/auth_test_users.md",
    "docs/operations/canonical-commands.md",
    "docs/operations/ci_release_pipeline.md",
    "docs/operations/database_evolution.md",
    "docs/operations/environment_parity.md",
    "docs/operations/frontend_publish_safety.md",
    "docs/operations/http_contract_guardrails.md",
    "docs/operations/load_test_plan.md",
    "docs/operations/local_runtime.md",
    "docs/operations/observability.md",
    "docs/operations/post_release_validation.md",
    "docs/operations/readme.md",
    "docs/operations/regression_audit_checklist.md",
    "docs/operations/release_evidence_template.json",
    "docs/operations/release_execution_checklist.md",
    "docs/operations/release_gates.md",
    "docs/operations/release_management.md",
    "docs/operations/rollback_checklist.md",
    "docs/operations/runbook.md",
    "docs/operations/security_front_26.md",
    "docs/operations/slos.md",
    "docs/operations/test_protection_strategy.md",
    "docs/operations/ui_baseline_hashes.json",
    "docs/operations/windows_backup_restore_rollback.md",
    "docs/operations/windows_self_hosted_server.md",
    "docs/product/manual_usuario_operacional.md",
    "docs/product/readme.md",
}

LIVE_DOC_PREFIXES = (
    "docs/architecture/",
    "docs/governance/",
    "docs/operations/",
    "docs/product/",
)

SCRIPTS_COMPAT_TARGETS = {
    "scripts/backup/run_backups.py": "backend/tools/maintenance/run_backups.py",
    "scripts/database/run_db_consistency.py": "backend/tools/maintenance/run_db_consistency.py",
    "scripts/jobs/run_jobs_worker.py": "backend/tools/maintenance/run_jobs_worker.py",
    "scripts/jobs/run_notifications.py": "backend/tools/maintenance/run_notifications.py",
    "scripts/windows/invoke-appservice.ps1": "ops/windows/scripts/invoke-appservice.ps1",
    "scripts/windows/invoke-operationalpython.ps1": "ops/windows/scripts/invoke-operationalpython.ps1",
}

SCRIPT_COMPAT_EXTENSIONS = {
    ".ps1",
    ".py",
}

FORBIDDEN_CONTENT_PATTERNS: dict[str, str] = {
    "ops/evidence": "documentation and scripts must not direct live evidence into the repository",
    "ops/backups": "documentation and scripts must not direct backups into the repository",
}

SECRET_FILE_SUFFIXES: dict[str, tuple[str, str]] = {
    ".key": ("local_secret", "private keys must not live in the repository"),
    ".pem": ("local_secret", "certificate/key material must not live in the repository"),
    ".pfx": ("local_secret", "certificate bundles must not live in the repository"),
    ".secret": ("local_secret", "secret payloads must not live in the repository"),
    ".token": ("local_secret", "token material must not live in the repository"),
    ".webhook": ("local_secret", "webhook secrets must not live in the repository"),
}

BACKUP_FILE_SUFFIXES: dict[str, tuple[str, str]] = {
    ".bak": ("backup", "backup files must not live in the repository"),
    ".dump": ("backup", "database or binary dumps must not live in the repository"),
}

GENERATED_FILE_SUFFIXES: dict[str, tuple[str, str]] = {
    ".pyc": ("generated_artifact", "python bytecode files must not live in the repository"),
    ".pyd": ("generated_artifact", "python extension build artifacts must not live in the repository"),
    ".pyo": ("generated_artifact", "python optimized bytecode files must not live in the repository"),
}


@dataclass(frozen=True)
class Violation:
    kind: str
    category: str
    path: str
    reason: str


def _normalize_rel(path: Path) -> str:
    normalized = path.as_posix()
    if normalized == ".":
        return ""
    if normalized.startswith("./"):
        return normalized[2:]
    return normalized


def _is_classified_archive(rel_path: Path) -> bool:
    normalized = _normalize_rel(rel_path).lower()
    return any(normalized == prefix or normalized.startswith(prefix + "/") for prefix in CLASSIFIED_ARCHIVE_PREFIXES)


def _allowed_env_template(path: Path) -> bool:
    name = path.name.lower()
    return name == ".env.example" or name.endswith(".env.example")


def _matches_root_snapshot_or_backup(rel_path: Path) -> tuple[str, str] | None:
    if len(rel_path.parts) != 1:
        return None
    name = rel_path.name.lower()
    if name in OFFICIAL_ROOT_DIRECTORIES or name in SKIP_SCAN_DIRECTORIES:
        return None
    if any(token in name for token in ROOT_SNAPSHOT_TOKENS):
        return (
            "historical_residue",
            "root snapshots must not live in the root; move classified snapshots to archive/repo-snapshots/ or remove them",
        )
    if any(token in name for token in ROOT_BACKUP_TOKENS):
        return (
            "backup",
            "root backups/dumps must not live in the root; move classified backups to archive/temp-backups/ or remove them",
        )
    if name.endswith(ROOT_BACKUP_FILE_SUFFIXES):
        return (
            "backup",
            "backup or database dump files must not live in the root; move classified backups to archive/temp-backups/ or remove them",
        )
    if name.endswith(ROOT_ARCHIVE_FILE_SUFFIXES):
        return (
            "historical_residue",
            "compressed archives must not live in the root; classify them under archive/repo-snapshots or archive/temp-backups, or remove them",
        )
    return None


def _matches_unclassified_archivable_material(rel_path: Path) -> tuple[str, str] | None:
    if _is_classified_archive(rel_path):
        return None
    name = rel_path.name.lower()
    if not DATED_ARCHIVABLE_NAME_RE.search(name):
        return None
    if "snapshot" in name:
        return (
            "historical_residue",
            "dated snapshot material must not live in the live tree; move classified snapshots to archive/repo-snapshots/ or remove them",
        )
    if "backup" in name or "dump" in name:
        return (
            "backup",
            "dated backup/dump material must not live in the live tree; move classified backups to archive/temp-backups/ or remove them",
        )
    return None


def _matches_ambiguous_root_directory(rel_path: Path) -> tuple[str, str] | None:
    if len(rel_path.parts) != 1:
        return None
    name = rel_path.name
    normalized = name.lower()
    if normalized in OFFICIAL_ROOT_DIRECTORIES or normalized in SKIP_SCAN_DIRECTORIES:
        return None
    if _matches_forbidden_directory(rel_path):
        return None
    return (
        "ambiguous_root_directory",
        (
            "new root directories need an approved root category "
            "(nucleo vivo, operacao, teste, docs, archive, or compat/legacy with justification); "
            "document the decision in docs/governance/root-entry-policy.md and repo-topology.md"
        ),
    )


def _is_explicit_local_directory_exception(rel_path: Path) -> bool:
    normalized = _normalize_rel(rel_path).lower()
    return normalized in EXPLICIT_LOCAL_DIRECTORY_EXCEPTIONS


def _is_explicit_local_file_exception(rel_path: Path) -> bool:
    normalized = _normalize_rel(rel_path).lower()
    return normalized in EXPLICIT_LOCAL_FILE_EXCEPTIONS


def _matches_forbidden_directory(rel_path: Path) -> tuple[str, str] | None:
    normalized = _normalize_rel(rel_path).lower()
    if not normalized:
        return None
    if _is_explicit_local_directory_exception(rel_path):
        return None
    name = rel_path.name.lower()
    if name in FORBIDDEN_DIRECTORY_NAMES:
        return FORBIDDEN_DIRECTORY_NAMES[name]
    if normalized in FORBIDDEN_ROOT_DIRECTORIES:
        return FORBIDDEN_ROOT_DIRECTORIES[normalized]
    for pattern, violation in FORBIDDEN_GLOB_DIRECTORIES.items():
        if fnmatch.fnmatch(normalized, pattern):
            return violation
    return None


def _check_live_document_registration(rel_path: Path) -> Violation | None:
    normalized = _normalize_rel(rel_path).lower()
    if not normalized or rel_path.suffix.lower() not in LIVE_DOC_EXTENSIONS:
        return None
    if not any(normalized.startswith(prefix) for prefix in LIVE_DOC_PREFIXES):
        return None
    if normalized in LIVE_DOC_ALLOWED_PATHS:
        return None
    return Violation(
        kind="unregistered_live_document",
        category="documentation_drift",
        path=_normalize_rel(rel_path),
        reason=(
            "live docs must be the single official source for their subject; consolidate, archive, "
            "or register the document in the hygiene allowlist and governance docs"
        ),
    )


def _check_script_classification(root: Path, abs_path: Path, rel_path: Path) -> list[Violation]:
    normalized = _normalize_rel(rel_path).lower()
    if not normalized.startswith("scripts/") or rel_path.suffix.lower() not in SCRIPT_COMPAT_EXTENSIONS:
        return []

    if normalized not in SCRIPTS_COMPAT_TARGETS:
        return [
            Violation(
                kind="unclassified_compat_script",
                category="operational_drift",
                path=_normalize_rel(rel_path),
                reason=(
                    "scripts/ is compat-only; register the wrapper in scripts/README.md, add a COMPAT header, "
                    "and delegate to the canonical command or move the implementation to ops/ or backend/tools/"
                ),
            )
        ]

    violations: list[Violation] = []
    canonical_target = SCRIPTS_COMPAT_TARGETS[normalized]
    try:
        text = abs_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        text = ""
    header_text = text[:500].replace("\\", "/").lower()
    if "COMPAT:" not in text[:500]:
        violations.append(
            Violation(
                kind="missing_compat_header",
                category="operational_drift",
                path=_normalize_rel(rel_path),
                reason="compat wrappers must declare COMPAT in the file header so they do not look canonical",
            )
        )
    if canonical_target not in header_text:
        violations.append(
            Violation(
                kind="missing_compat_canonical_target",
                category="operational_drift",
                path=_normalize_rel(rel_path),
                reason="compat wrappers must declare their canonical target in the file header",
            )
        )

    readme = root / "scripts" / "README.md"
    try:
        readme_text = readme.read_text(encoding="utf-8", errors="ignore").replace("\\", "/").lower()
    except Exception:
        readme_text = ""
    if not _readme_has_wrapper_target(readme_text, normalized, canonical_target):
        violations.append(
            Violation(
                kind="missing_compat_documentation",
                category="operational_drift",
                path=_normalize_rel(rel_path),
                reason="compat wrappers must be listed in scripts/README.md with their canonical target",
            )
        )
    if not _readme_has_removal_queue(readme_text, normalized, canonical_target):
        violations.append(
            Violation(
                kind="missing_compat_removal_plan",
                category="operational_drift",
                path=_normalize_rel(rel_path),
                reason=(
                    "compat wrappers must have a removal queue row in scripts/README.md with current consumer, "
                    "removal precondition, and compatibility risk"
                ),
            )
        )
    return violations


def _markdown_table_cells(line: str) -> list[str]:
    if not line.strip().startswith("|"):
        return []
    cells = [cell.strip().strip("`").strip() for cell in line.strip().strip("|").split("|")]
    return [cell.replace("\\", "/").lower() for cell in cells]


def _readme_has_wrapper_target(readme_text: str, wrapper: str, canonical_target: str) -> bool:
    for line in readme_text.splitlines():
        cells = _markdown_table_cells(line)
        if len(cells) >= 2 and cells[0] == wrapper and cells[1] == canonical_target:
            return True
    return False


def _readme_has_removal_queue(readme_text: str, wrapper: str, canonical_target: str) -> bool:
    for line in readme_text.splitlines():
        cells = _markdown_table_cells(line)
        if len(cells) < 5:
            continue
        if cells[0] != wrapper or cells[1] != canonical_target:
            continue
        consumer, precondition, risk = cells[2], cells[3], cells[4]
        return all(value and value != "-" for value in (consumer, precondition, risk))
    return False


def _classify_forbidden_file(rel_path: Path) -> tuple[str, str] | None:
    normalized = _normalize_rel(rel_path).lower()
    if not normalized:
        return None

    name = rel_path.name.lower()
    if _is_explicit_local_file_exception(rel_path):
        return None
    if _allowed_env_template(rel_path):
        return None

    if name == ".env" or name.endswith(".env") or ".env." in name:
        return ("local_secret", "live environment/config files must not live in the repository")
    if name == ".coverage" or name.startswith(".coverage."):
        return ("generated_artifact", "coverage output must not live in the repository")
    if name == ".python_history":
        return ("local_secret", "local shell/python history must not live in the repository")
    if ".pyc." in name:
        return ("generated_artifact", "python bytecode snapshots must not live in the repository")

    for suffix_map in (SECRET_FILE_SUFFIXES, BACKUP_FILE_SUFFIXES, GENERATED_FILE_SUFFIXES):
        for suffix, violation in suffix_map.items():
            if name.endswith(suffix):
                return violation

    return None


def _should_scan_content(rel_path: Path) -> bool:
    normalized = _normalize_rel(rel_path).lower()
    if not normalized or rel_path.suffix.lower() not in TEXT_EXTENSIONS:
        return False
    if normalized.startswith("ops/scripts/repo/"):
        return False
    for root_prefix in TEXT_SCAN_ROOTS:
        prefix = root_prefix.lower()
        if normalized == prefix or normalized.startswith(prefix + "/"):
            return True
    return False


def _scan_content(abs_path: Path, rel_path: Path) -> list[Violation]:
    try:
        text = abs_path.read_text(encoding="utf-8", errors="ignore").lower()
    except Exception:
        return []

    violations: list[Violation] = []
    for token, reason in FORBIDDEN_CONTENT_PATTERNS.items():
        if token in text:
            violations.append(
                Violation(
                    kind="forbidden_content_reference",
                    category="operational_drift",
                    path=_normalize_rel(rel_path),
                    reason=reason,
                )
            )
    return violations


def _check_sistema_controle_usage(abs_path: Path, rel_path: Path) -> Violation | None:
    normalized = _normalize_rel(rel_path).lower()
    if not normalized.startswith("backend/src/controle_treinamentos/"):
        return None
    if rel_path.suffix.lower() != ".py":
        return None
    try:
        text = abs_path.read_text(encoding="utf-8", errors="ignore").lower()
    except Exception:
        return None
    if "sistema_controle" not in text:
        return None
    if normalized in SISTEMA_CONTROLE_ALLOWED_CODE_PATHS:
        return None
    return Violation(
        kind="forbidden_sistema_controle_usage",
        category="operational_drift",
        path=_normalize_rel(rel_path),
        reason=(
            "sistema_controle e superficie residual fechada; novo uso em codigo vivo deve ir para "
            "owner canonico, cache_service ou fila/metadata especifica"
        ),
    )


def scan_repo(root: Path) -> list[Violation]:
    violations: list[Violation] = []

    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        rel_dir = current_path.relative_to(root)
        rel_dir = Path() if str(rel_dir) == "." else rel_dir

        kept_dirs: list[str] = []
        for dirname in dirs:
            rel_candidate = rel_dir / dirname if rel_dir.parts else Path(dirname)
            normalized_candidate = _normalize_rel(rel_candidate).lower()
            if normalized_candidate in SKIP_SCAN_DIRECTORIES or _is_classified_archive(rel_candidate):
                continue
            if _is_explicit_local_directory_exception(rel_candidate):
                continue
            root_snapshot = _matches_root_snapshot_or_backup(rel_candidate)
            if root_snapshot:
                category, reason = root_snapshot
                violations.append(
                    Violation(
                        kind="root_snapshot_or_backup",
                        category=category,
                        path=_normalize_rel(rel_candidate),
                        reason=reason,
                    )
                )
                continue
            archivable = _matches_unclassified_archivable_material(rel_candidate)
            if archivable:
                category, reason = archivable
                violations.append(
                    Violation(
                        kind="unclassified_archivable_material",
                        category=category,
                        path=_normalize_rel(rel_candidate),
                        reason=reason,
                    )
                )
                continue
            violation = _matches_forbidden_directory(rel_candidate)
            if violation:
                category, reason = violation
                violations.append(
                    Violation(
                        kind="forbidden_directory",
                        category=category,
                        path=_normalize_rel(rel_candidate),
                        reason=reason,
                    )
                )
                continue
            ambiguous = _matches_ambiguous_root_directory(rel_candidate)
            if ambiguous:
                category, reason = ambiguous
                violations.append(
                    Violation(
                        kind="ambiguous_root_directory",
                        category=category,
                        path=_normalize_rel(rel_candidate),
                        reason=reason,
                    )
                )
                continue
            kept_dirs.append(dirname)
        dirs[:] = kept_dirs

        for filename in files:
            rel_candidate = rel_dir / filename if rel_dir.parts else Path(filename)
            if _is_classified_archive(rel_candidate):
                continue
            root_snapshot = _matches_root_snapshot_or_backup(rel_candidate)
            if root_snapshot:
                category, reason = root_snapshot
                violations.append(
                    Violation(
                        kind="root_snapshot_or_backup",
                        category=category,
                        path=_normalize_rel(rel_candidate),
                        reason=reason,
                    )
                )
                continue
            archivable = _matches_unclassified_archivable_material(rel_candidate)
            if archivable:
                category, reason = archivable
                violations.append(
                    Violation(
                        kind="unclassified_archivable_material",
                        category=category,
                        path=_normalize_rel(rel_candidate),
                        reason=reason,
                    )
                )
                continue
            violation = _classify_forbidden_file(rel_candidate)
            if violation:
                category, reason = violation
                violations.append(
                    Violation(
                        kind="forbidden_file",
                        category=category,
                        path=_normalize_rel(rel_candidate),
                        reason=reason,
                    )
                )
                continue

            live_doc_violation = _check_live_document_registration(rel_candidate)
            if live_doc_violation:
                violations.append(live_doc_violation)
                continue

            sistema_controle_violation = _check_sistema_controle_usage(root / rel_candidate, rel_candidate)
            if sistema_controle_violation:
                violations.append(sistema_controle_violation)
                continue

            script_violations = _check_script_classification(root, root / rel_candidate, rel_candidate)
            if script_violations:
                violations.extend(script_violations)
                continue

            if _should_scan_content(rel_candidate):
                violations.extend(_scan_content(root / rel_candidate, rel_candidate))

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Validates repository/workspace hygiene guardrails.")
    parser.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parents[3]),
        help="Repository/workspace root to audit.",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Returns success even when violations are present; useful for local inventory runs.",
    )
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    violations = scan_repo(root)
    payload = {
        "success": not violations,
        "root": str(root),
        "violations": [asdict(item) for item in violations],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if (not violations or args.report_only) else 1


if __name__ == "__main__":
    raise SystemExit(main())
