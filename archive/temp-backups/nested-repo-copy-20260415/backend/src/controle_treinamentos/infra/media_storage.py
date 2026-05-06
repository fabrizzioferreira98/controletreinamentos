from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile
from typing import Final
from uuid import uuid4

from flask import current_app, has_app_context
from ..core.workspace_paths import runtime_instance_root, validate_operational_path

_FS_STORAGE_PREFIX: Final[str] = "fs:"
_PHOTO_EXTENSIONS: Final[dict[str, str]] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
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
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Caminho relativo de storage invalido.")
    return path


def storage_ref_to_path(storage_ref: str | None) -> Path | None:
    raw = (storage_ref or "").strip()
    if not raw or not raw.startswith(_FS_STORAGE_PREFIX):
        return None
    relative_path = _safe_relative_path(raw[len(_FS_STORAGE_PREFIX) :])
    return media_storage_root() / Path(*relative_path.parts)


def build_storage_ref(relative_path: str | PurePosixPath) -> str:
    path = relative_path if isinstance(relative_path, PurePosixPath) else _safe_relative_path(str(relative_path))
    return f"{_FS_STORAGE_PREFIX}{path.as_posix()}"


def _write_bytes_atomic(target: Path, payload: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=target.parent, delete=False) as handle:
        handle.write(payload)
        temp_path = Path(handle.name)
    temp_path.replace(target)


def normalize_tripulante_slug(value: str | None) -> str:
    raw = unicodedata.normalize("NFKD", (value or "").strip()).encode("ascii", "ignore").decode("ascii")
    normalized = _NON_ALNUM_RE.sub("-", raw.lower()).strip("-")
    return normalized or "tripulante"


def tripulante_storage_dirname(tripulante_id: int, tripulante_name: str | None) -> str:
    return f"{int(tripulante_id)}-{normalize_tripulante_slug(tripulante_name)}"


def write_tripulante_photo(tripulante_id: int, tripulante_name: str | None, payload: bytes, *, mime_type: str) -> str:
    extension = _PHOTO_EXTENSIONS.get((mime_type or "").strip().lower())
    if not extension:
        raise ValueError("Mime type de foto nao suportado para storage em disco.")
    relative = (
        PurePosixPath("tripulantes")
        / tripulante_storage_dirname(tripulante_id, tripulante_name)
        / "foto"
        / f"{uuid4().hex}{extension}"
    )
    target = media_storage_root() / Path(*relative.parts)
    _write_bytes_atomic(target, payload)
    return build_storage_ref(relative)


def write_tripulante_document(tripulante_id: int, tripulante_name: str | None, file_name: str, payload: bytes) -> str:
    relative = (
        PurePosixPath("tripulantes")
        / tripulante_storage_dirname(tripulante_id, tripulante_name)
        / "documentos"
        / file_name
    )
    target = media_storage_root() / Path(*relative.parts)
    _write_bytes_atomic(target, payload)
    return build_storage_ref(relative)


def write_training_attachment(
    tripulante_id: int,
    tripulante_name: str | None,
    treinamento_id: int,
    file_name: str,
    payload: bytes,
) -> str:
    relative = (
        PurePosixPath("tripulantes")
        / tripulante_storage_dirname(tripulante_id, tripulante_name)
        / "treinamentos"
        / str(int(treinamento_id))
        / file_name
    )
    target = media_storage_root() / Path(*relative.parts)
    _write_bytes_atomic(target, payload)
    return build_storage_ref(relative)


def read_media_bytes(storage_ref: str | None, *, fallback_bytes: bytes | None = None) -> bytes | None:
    target = storage_ref_to_path(storage_ref)
    if target is not None:
        if not target.exists() or not target.is_file():
            return None
        return target.read_bytes()
    return fallback_bytes


def delete_media_ref(storage_ref: str | None) -> None:
    target = storage_ref_to_path(storage_ref)
    if target is None or not target.exists() or not target.is_file():
        return
    target.unlink()
    current = target.parent
    root = media_storage_root().resolve()
    while current.exists() and current != root:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent
