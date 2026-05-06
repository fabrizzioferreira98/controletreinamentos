from __future__ import annotations

import argparse
import fnmatch
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


FORBIDDEN_ROOT_DIRECTORIES: dict[str, tuple[str, str]] = {
    ".tmp": ("historical_residue", "temporary backups and ad hoc residue must stay outside the repository"),
    ".venv": ("generated_artifact", "local virtual environments must not live inside the repository"),
    "venv": ("generated_artifact", "local virtual environments must not live inside the repository"),
    "frontend/dist": ("generated_artifact", "frontend publish/build output must be rebuilt, not versioned"),
    "frontend/_backup": ("backup", "frontend backup directories must stay outside the repository"),
    "backend/runtime": ("mutable_state", "runtime state must stay outside the repository"),
    "ops/evidence": ("operational_evidence", "live operational evidence must stay outside the repository"),
    "ops/backups": ("backup", "backups must stay outside the repository"),
    "ops/artifacts": ("generated_artifact", "generated operational artifacts must stay outside the repository"),
    "logs": ("mutable_state", "runtime logs must stay outside the repository"),
}

FORBIDDEN_GLOB_DIRECTORIES: dict[str, tuple[str, str]] = {
    "frontend/prod-backup-*": ("backup", "frontend backup snapshots must stay outside the repository"),
}

FORBIDDEN_DIRECTORY_NAMES: dict[str, tuple[str, str]] = {
    "__pycache__": ("generated_artifact", "python bytecode cache directories must not live in the repository"),
    ".pytest_cache": ("generated_artifact", "pytest cache directories must not live in the repository"),
    ".mypy_cache": ("generated_artifact", "mypy cache directories must not live in the repository"),
    ".ruff_cache": ("generated_artifact", "ruff cache directories must not live in the repository"),
}

TEXT_SCAN_ROOTS = (
    ".github/workflows",
    "docs/operations",
    "ops/scripts",
)

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

FORBIDDEN_CONTENT_PATTERNS: dict[str, str] = {
    "ops/evidence": "documentation and scripts must not direct live evidence into the repository",
    "ops/backups": "documentation and scripts must not direct backups into the repository",
    "ops/artifacts": "documentation and scripts must not direct generated artifacts into the repository",
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


def _allowed_env_template(path: Path) -> bool:
    name = path.name.lower()
    return name == ".env.example" or name.endswith(".env.example")


def _matches_forbidden_directory(rel_path: Path) -> tuple[str, str] | None:
    normalized = _normalize_rel(rel_path).lower()
    if not normalized:
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


def _classify_forbidden_file(rel_path: Path) -> tuple[str, str] | None:
    normalized = _normalize_rel(rel_path).lower()
    if not normalized:
        return None

    name = rel_path.name.lower()
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


def scan_repo(root: Path) -> list[Violation]:
    violations: list[Violation] = []

    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        rel_dir = current_path.relative_to(root)
        rel_dir = Path() if str(rel_dir) == "." else rel_dir

        kept_dirs: list[str] = []
        for dirname in dirs:
            rel_candidate = rel_dir / dirname if rel_dir.parts else Path(dirname)
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
            kept_dirs.append(dirname)
        dirs[:] = kept_dirs

        for filename in files:
            rel_candidate = rel_dir / filename if rel_dir.parts else Path(filename)
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
