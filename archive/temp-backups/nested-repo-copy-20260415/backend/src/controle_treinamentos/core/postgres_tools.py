from __future__ import annotations

import os
import shutil
from pathlib import Path


def _binary_env_name(binary_name: str) -> str:
    normalized = binary_name.replace(".exe", "").replace("-", "_").upper()
    return f"{normalized}_PATH"


def _binary_filename(binary_name: str) -> str:
    normalized = binary_name.replace(".exe", "")
    if os.name == "nt":
        return f"{normalized}.exe"
    return normalized


def _iter_candidate_pg_bin_dirs() -> list[Path]:
    candidates: list[Path] = []
    raw_pg_bin_dir = (os.getenv("PG_BIN_DIR", "") or "").strip()
    if raw_pg_bin_dir:
        candidates.append(Path(raw_pg_bin_dir).expanduser())

    if os.name != "nt":
        return candidates

    seen: set[str] = {str(path).lower() for path in candidates}
    for env_name in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        raw_root = (os.getenv(env_name, "") or "").strip()
        if not raw_root:
            continue
        base_dir = Path(raw_root) / "PostgreSQL"
        if not base_dir.exists() or not base_dir.is_dir():
            continue
        try:
            version_dirs = sorted(
                (item for item in base_dir.iterdir() if item.is_dir()),
                key=lambda item: item.name,
                reverse=True,
            )
        except OSError:
            continue
        for version_dir in version_dirs:
            candidate = version_dir / "bin"
            candidate_key = str(candidate).lower()
            if candidate.is_dir() and candidate_key not in seen:
                seen.add(candidate_key)
                candidates.append(candidate)
    return candidates


def find_postgres_binary(binary_name: str) -> Path | None:
    explicit_path = (os.getenv(_binary_env_name(binary_name), "") or "").strip()
    if explicit_path:
        candidate = Path(explicit_path).expanduser()
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()

    resolved = shutil.which(binary_name) or shutil.which(_binary_filename(binary_name))
    if resolved:
        return Path(resolved).resolve()

    binary_filename = _binary_filename(binary_name)
    for bin_dir in _iter_candidate_pg_bin_dirs():
        candidate = (bin_dir / binary_filename).expanduser()
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()
    return None
