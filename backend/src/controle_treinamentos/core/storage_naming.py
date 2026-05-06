from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Final
from uuid import uuid4

_SAFE_STORAGE_FILENAME_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_PDF_PHYSICAL_PREFIXES: Final[dict[str, str]] = {
    "tripulante_document": "documento",
    "training_attachment": "anexo",
}
_PHOTO_EXTENSIONS: Final[dict[str, str]] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def canonical_tripulante_dirname(tripulante_id: int) -> str:
    return f"tripulante-{int(tripulante_id)}"


def canonical_training_dirname(treinamento_id: int) -> str:
    return f"treinamento-{int(treinamento_id)}"


def safe_storage_filename(file_name: str) -> str:
    name = (file_name or "").strip()
    if not name or "/" in name or "\\" in name:
        raise ValueError("Nome fisico de arquivo invalido.")
    path = PurePosixPath(name)
    if path.name != name or name in {".", ".."}:
        raise ValueError("Nome fisico de arquivo invalido.")
    if not _SAFE_STORAGE_FILENAME_RE.match(name):
        raise ValueError("Nome fisico de arquivo invalido.")
    return name


def build_pdf_physical_name(kind: str) -> str:
    prefix = _PDF_PHYSICAL_PREFIXES.get((kind or "").strip())
    if not prefix:
        raise ValueError("Dominio de PDF sem politica de naming.")
    return f"{prefix}-{uuid4().hex}.pdf"


def build_photo_physical_name(mime_type: str) -> str:
    extension = _PHOTO_EXTENSIONS.get((mime_type or "").strip().lower())
    if not extension:
        raise ValueError("Mime type de foto nao suportado para storage em disco.")
    return f"foto-{uuid4().hex}{extension}"
