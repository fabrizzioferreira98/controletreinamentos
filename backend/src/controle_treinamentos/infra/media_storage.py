from __future__ import annotations

import os
import re
import time
import unicodedata
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile
from typing import Final

from flask import current_app, has_app_context
from ..core.document_storage import assert_storage_ref_matches_policy
from ..core.metrics import record_storage_operation
from ..core.storage_naming import (
    build_photo_physical_name,
    canonical_training_dirname,
    canonical_tripulante_dirname,
    safe_storage_filename,
)
from ..core.workspace_paths import runtime_instance_root, validate_operational_path

_FS_STORAGE_PREFIX: Final[str] = "fs:"
_NON_ALNUM_RE: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9]+")


def media_storage_root() -> Path:
    raw_root = (
        (os.getenv("MEDIA_STORAGE_ROOT", "") or "").strip()
        or (os.getenv("UPLOAD_ROOT", "") or "").strip()
    )
    if raw_root:
        return validate_operational_path(Path(raw_root), label="MEDIA_STORAGE_ROOT")
    if has_app_context():
        return validate_operational_path(Path(current_app.instance_path) / "uploads", label="MEDIA_STORAGE_ROOT")
    return validate_operational_path(runtime_instance_root() / "uploads", label="MEDIA_STORAGE_ROOT")


def _safe_relative_path(relative_path: str) -> PurePosixPath:
    raw = (relative_path or "").strip().lstrip("/")
    if not raw:
        raise ValueError("Caminho relativo de storage vazio.")
    if "\\" in raw or "\x00" in raw:
        raise ValueError("Caminho relativo de storage invalido.")
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Caminho relativo de storage invalido.")
    return path


def storage_ref_to_path(storage_ref: str | None) -> Path | None:
    raw = (storage_ref or "").strip()
    if not raw or not raw.startswith(_FS_STORAGE_PREFIX):
        return None
    relative_path = _safe_relative_path(raw[len(_FS_STORAGE_PREFIX) :])
    root = media_storage_root().resolve()
    target = root / Path(*relative_path.parts)
    try:
        target.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise ValueError("Referencia de storage fora da raiz operacional.") from exc
    return target


def build_storage_ref(relative_path: str | PurePosixPath) -> str:
    path = relative_path if isinstance(relative_path, PurePosixPath) else _safe_relative_path(str(relative_path))
    return f"{_FS_STORAGE_PREFIX}{path.as_posix()}"


def _write_bytes_atomic(target: Path, payload: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=target.parent, delete=False) as handle:
        handle.write(payload)
        temp_path = Path(handle.name)
    temp_path.replace(target)


def _log_storage_event(level: str, message: str, **extra) -> None:
    if not has_app_context():
        return
    payload = {"component": "media_storage", **extra}
    logger = current_app.logger
    if level == "exception":
        logger.exception(message, extra=payload)
        return
    if level == "warning":
        logger.warning(message, extra=payload)
        return
    logger.info(message, extra=payload)


def normalize_tripulante_slug(value: str | None) -> str:
    raw = unicodedata.normalize("NFKD", (value or "").strip()).encode("ascii", "ignore").decode("ascii")
    normalized = _NON_ALNUM_RE.sub("-", raw.lower()).strip("-")
    return normalized or "tripulante"


def legacy_tripulante_storage_dirname(tripulante_id: int, tripulante_name: str | None) -> str:
    return f"{int(tripulante_id)}-{normalize_tripulante_slug(tripulante_name)}"


def tripulante_storage_dirname(tripulante_id: int, tripulante_name: str | None = None) -> str:
    return canonical_tripulante_dirname(tripulante_id)


def write_tripulante_photo(tripulante_id: int, tripulante_name: str | None, payload: bytes, *, mime_type: str) -> str:
    relative = (
        PurePosixPath("tripulantes")
        / tripulante_storage_dirname(tripulante_id, tripulante_name)
        / "fotos"
        / build_photo_physical_name(mime_type)
    )
    storage_ref = build_storage_ref(relative)
    assert_storage_ref_matches_policy("tripulante_photo", storage_ref, tripulante_id=tripulante_id)
    target = media_storage_root() / Path(*relative.parts)
    started = time.monotonic()
    try:
        _write_bytes_atomic(target, payload)
    except Exception:
        record_storage_operation(
            operation="write",
            policy="tripulante_photo",
            status="failed",
            duration_ms=int((time.monotonic() - started) * 1000),
            size_bytes=len(payload or b""),
        )
        _log_storage_event(
            "exception",
            "Media storage write failed.",
            event="storage_write_failed",
            storage_policy="tripulante_photo",
            tripulante_id=int(tripulante_id),
            storage_ref=storage_ref,
            path=str(target),
            size_bytes=len(payload or b""),
            mime_type=mime_type,
        )
        raise
    record_storage_operation(
        operation="write",
        policy="tripulante_photo",
        status="success",
        duration_ms=int((time.monotonic() - started) * 1000),
        size_bytes=len(payload or b""),
    )
    _log_storage_event(
        "info",
        "Media storage write completed.",
        event="storage_write",
        storage_policy="tripulante_photo",
        tripulante_id=int(tripulante_id),
        storage_ref=storage_ref,
        path=str(target),
        size_bytes=len(payload or b""),
        mime_type=mime_type,
    )
    return storage_ref


def write_tripulante_document(tripulante_id: int, tripulante_name: str | None, file_name: str, payload: bytes) -> str:
    physical_name = safe_storage_filename(file_name)
    relative = (
        PurePosixPath("tripulantes")
        / tripulante_storage_dirname(tripulante_id, tripulante_name)
        / "documentos"
        / physical_name
    )
    storage_ref = build_storage_ref(relative)
    assert_storage_ref_matches_policy("tripulante_document", storage_ref, tripulante_id=tripulante_id)
    target = media_storage_root() / Path(*relative.parts)
    started = time.monotonic()
    try:
        _write_bytes_atomic(target, payload)
    except Exception:
        record_storage_operation(
            operation="write",
            policy="tripulante_document",
            status="failed",
            duration_ms=int((time.monotonic() - started) * 1000),
            size_bytes=len(payload or b""),
        )
        _log_storage_event(
            "exception",
            "Media storage write failed.",
            event="storage_write_failed",
            storage_policy="tripulante_document",
            tripulante_id=int(tripulante_id),
            storage_ref=storage_ref,
            path=str(target),
            size_bytes=len(payload or b""),
            original_name=file_name,
        )
        raise
    record_storage_operation(
        operation="write",
        policy="tripulante_document",
        status="success",
        duration_ms=int((time.monotonic() - started) * 1000),
        size_bytes=len(payload or b""),
    )
    _log_storage_event(
        "info",
        "Media storage write completed.",
        event="storage_write",
        storage_policy="tripulante_document",
        tripulante_id=int(tripulante_id),
        storage_ref=storage_ref,
        path=str(target),
        size_bytes=len(payload or b""),
        original_name=file_name,
    )
    return storage_ref


def write_training_attachment(
    tripulante_id: int,
    tripulante_name: str | None,
    treinamento_id: int,
    file_name: str,
    payload: bytes,
) -> str:
    physical_name = safe_storage_filename(file_name)
    relative = (
        PurePosixPath("treinamentos")
        / canonical_training_dirname(treinamento_id)
        / "anexos"
        / physical_name
    )
    storage_ref = build_storage_ref(relative)
    assert_storage_ref_matches_policy("training_attachment", storage_ref, treinamento_id=treinamento_id)
    target = media_storage_root() / Path(*relative.parts)
    started = time.monotonic()
    try:
        _write_bytes_atomic(target, payload)
    except Exception:
        record_storage_operation(
            operation="write",
            policy="training_attachment",
            status="failed",
            duration_ms=int((time.monotonic() - started) * 1000),
            size_bytes=len(payload or b""),
        )
        _log_storage_event(
            "exception",
            "Media storage write failed.",
            event="storage_write_failed",
            storage_policy="training_attachment",
            treinamento_id=int(treinamento_id),
            storage_ref=storage_ref,
            path=str(target),
            size_bytes=len(payload or b""),
            original_name=file_name,
        )
        raise
    record_storage_operation(
        operation="write",
        policy="training_attachment",
        status="success",
        duration_ms=int((time.monotonic() - started) * 1000),
        size_bytes=len(payload or b""),
    )
    _log_storage_event(
        "info",
        "Media storage write completed.",
        event="storage_write",
        storage_policy="training_attachment",
        treinamento_id=int(treinamento_id),
        storage_ref=storage_ref,
        path=str(target),
        size_bytes=len(payload or b""),
        original_name=file_name,
    )
    return storage_ref


def read_media_bytes(storage_ref: str | None, *, fallback_bytes: bytes | None = None) -> bytes | None:
    started = time.monotonic()
    try:
        target = storage_ref_to_path(storage_ref)
    except Exception:
        record_storage_operation(
            operation="read",
            policy="generic",
            status="failed",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        raise
    if target is not None:
        if not target.exists() or not target.is_file():
            record_storage_operation(
                operation="read",
                policy="generic",
                status="missing",
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            _log_storage_event(
                "warning",
                "Media storage read missed expected file.",
                event="storage_read_missing",
                storage_ref=storage_ref,
                path=str(target),
            )
            return None
        try:
            data = target.read_bytes()
        except Exception:
            record_storage_operation(
                operation="read",
                policy="generic",
                status="failed",
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            raise
        record_storage_operation(
            operation="read",
            policy="generic",
            status="success",
            duration_ms=int((time.monotonic() - started) * 1000),
            size_bytes=len(data),
        )
        return data
    return fallback_bytes


def media_ref_exists(storage_ref: str | None) -> bool:
    target = storage_ref_to_path(storage_ref)
    return bool(target is not None and target.exists() and target.is_file())


def iter_local_media_refs() -> list[str]:
    root = media_storage_root()
    if not root.exists() or not root.is_dir():
        return []
    refs: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        refs.append(build_storage_ref(PurePosixPath(*relative.parts)))
    return sorted(refs)


def delete_media_ref(storage_ref: str | None) -> None:
    started = time.monotonic()
    try:
        target = storage_ref_to_path(storage_ref)
    except Exception:
        record_storage_operation(
            operation="delete",
            policy="generic",
            status="failed",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        raise
    if target is None or not target.exists() or not target.is_file():
        return
    try:
        target.unlink()
    except Exception:
        record_storage_operation(
            operation="delete",
            policy="generic",
            status="failed",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        _log_storage_event(
            "exception",
            "Media storage delete failed.",
            event="storage_delete_failed",
            storage_ref=storage_ref,
            path=str(target),
        )
        raise
    record_storage_operation(
        operation="delete",
        policy="generic",
        status="success",
        duration_ms=int((time.monotonic() - started) * 1000),
    )
    _log_storage_event(
        "info",
        "Media storage delete completed.",
        event="storage_delete",
        storage_ref=storage_ref,
        path=str(target),
    )
    current = target.parent
    root = media_storage_root().resolve()
    while current.exists() and current != root:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent
