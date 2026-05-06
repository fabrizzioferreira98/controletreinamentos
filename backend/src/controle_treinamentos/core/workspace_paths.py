from __future__ import annotations

import os
from pathlib import Path
from tempfile import gettempdir

SECURE_APP_ENVS = {"production", "staging", "homolog"}


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _app_env() -> str:
    return ((os.getenv("APP_ENV", "") or "").strip().lower() or "development")


def _is_secure_env() -> bool:
    return _app_env() in SECURE_APP_ENVS


def _external_data_root() -> Path:
    raw = (os.getenv("CONTROLE_TREINAMENTOS_DATA_ROOT", "") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path(gettempdir()) / "controle-treinamentos" / _app_env()


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _is_within_workspace(path: Path) -> bool:
    candidate = _resolved(path)
    root = _resolved(workspace_root())
    return candidate == root or root in candidate.parents


def validate_operational_path(path: Path, *, label: str) -> Path:
    if _is_secure_env() and _is_within_workspace(path):
        raise RuntimeError(
            f"{label} nao pode apontar para dentro do checkout do repositorio em ambiente seguro."
        )
    return path


def ops_root() -> Path:
    raw = (os.getenv("WORKSPACE_OPS_ROOT", "") or "").strip()
    return Path(raw).expanduser() if raw else (workspace_root() / "ops")


def runtime_root() -> Path:
    raw = (os.getenv("WORKSPACE_RUNTIME_ROOT", "") or "").strip()
    path = Path(raw).expanduser() if raw else (_external_data_root() / "runtime")
    return validate_operational_path(path, label="WORKSPACE_RUNTIME_ROOT")


def evidence_root() -> Path:
    raw = (os.getenv("WORKSPACE_EVIDENCE_ROOT", "") or "").strip()
    path = Path(raw).expanduser() if raw else (_external_data_root() / "evidence")
    return validate_operational_path(path, label="WORKSPACE_EVIDENCE_ROOT")


def artifacts_root() -> Path:
    raw = (os.getenv("WORKSPACE_ARTIFACTS_ROOT", "") or "").strip()
    path = Path(raw).expanduser() if raw else (_external_data_root() / "artifacts")
    return validate_operational_path(path, label="WORKSPACE_ARTIFACTS_ROOT")


def local_backups_root() -> Path:
    raw = (os.getenv("WORKSPACE_LOCAL_BACKUPS_ROOT", "") or "").strip()
    path = Path(raw).expanduser() if raw else (_external_data_root() / "backups")
    return validate_operational_path(path, label="WORKSPACE_LOCAL_BACKUPS_ROOT")


def runtime_instance_root() -> Path:
    raw = (os.getenv("APP_INSTANCE_PATH", "") or "").strip()
    path = Path(raw).expanduser() if raw else (runtime_root() / "instance")
    return validate_operational_path(path, label="APP_INSTANCE_PATH")


def runtime_temp_root(*parts: str) -> Path:
    base = runtime_root() / "tmp"
    return base.joinpath(*parts)
