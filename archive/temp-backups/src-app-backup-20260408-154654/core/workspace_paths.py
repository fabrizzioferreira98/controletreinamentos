from __future__ import annotations

import os
from pathlib import Path


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[3]


def ops_root() -> Path:
    raw = (os.getenv("WORKSPACE_OPS_ROOT", "") or "").strip()
    return Path(raw).expanduser() if raw else (workspace_root() / "ops")


def runtime_root() -> Path:
    raw = (os.getenv("WORKSPACE_RUNTIME_ROOT", "") or "").strip()
    return Path(raw).expanduser() if raw else (workspace_root() / "runtime")


def evidence_root() -> Path:
    raw = (os.getenv("WORKSPACE_EVIDENCE_ROOT", "") or "").strip()
    return Path(raw).expanduser() if raw else (ops_root() / "evidence")


def artifacts_root() -> Path:
    raw = (os.getenv("WORKSPACE_ARTIFACTS_ROOT", "") or "").strip()
    return Path(raw).expanduser() if raw else (ops_root() / "artifacts")


def local_backups_root() -> Path:
    raw = (os.getenv("WORKSPACE_LOCAL_BACKUPS_ROOT", "") or "").strip()
    return Path(raw).expanduser() if raw else (ops_root() / "backups")


def runtime_instance_root() -> Path:
    raw = (os.getenv("APP_INSTANCE_PATH", "") or "").strip()
    return Path(raw).expanduser() if raw else (runtime_root() / "instance")


def runtime_temp_root(*parts: str) -> Path:
    base = runtime_root() / "tmp"
    return base.joinpath(*parts)

