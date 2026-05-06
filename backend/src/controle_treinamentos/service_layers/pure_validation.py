"""Side-effect-free validation and normalization rules."""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
import struct
from datetime import date
from typing import Final

from ..constants import (
    MAX_PHOTO_BYTES,
    PHOTO_ALLOWED_MIME,
    TRIPULANTE_CATEGORIA_OPTIONS,
    TRIPULANTE_FUNCAO_OPTIONS,
    TRIPULANTE_STATUS_OPTIONS,
)
from ..core.http_utils import safe_pdf_filename
from ..core.storage_naming import build_pdf_physical_name
from ..services import parse_date
from .upload_policy import (
    PDF_CONTENT_SIGNATURE,
    PDF_EOF_MARKER,
    PDF_EOF_SCAN_BYTES,
    TRAINING_ATTACHMENT_UPLOAD_POLICY,
    TRIPULANTE_FILE_UPLOAD_POLICY,
    UploadPolicy,
)

_PHOTO_DATA_URI_RE: Final[re.Pattern[str]] = re.compile(r"^data:image/(png|jpe?g|webp);base64,", re.IGNORECASE)
_PHOTO_DECLARED_MIME: Final[dict[str, str]] = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}
_PNG_SIGNATURE: Final[bytes] = b"\x89PNG\r\n\x1a\n"
_WEBP_CHUNK_TYPES: Final[set[bytes]] = {b"VP8 ", b"VP8L", b"VP8X"}


_TRIPULANTE_STATUS_CANONICAL_MAP = {
    "ativo": "Ativo",
    "folga": "Folga",
    "ferias": "F\u00e9rias",
    "f\u00e9rias": "F\u00e9rias",
    "atestado": "Atestado",
    "afastado": "Afastado",
    "treinamento": "Treinamento",
}


def normalize_tripulante_status(value: str | None) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    return _TRIPULANTE_STATUS_CANONICAL_MAP.get(raw.lower())


def tripulante_status_filter_values(value: str | None) -> tuple[str, ...]:
    normalized = normalize_tripulante_status(value)
    if not normalized:
        return ()
    if normalized == "F\u00e9rias":
        return ("F\u00e9rias", "Ferias")
    return (normalized,)


def validate_tripulante_status(value: str) -> str:
    normalized = normalize_tripulante_status(value)
    if normalized is None or normalized not in TRIPULANTE_STATUS_OPTIONS:
        raise ValueError("Selecione um status valido para o tripulante.")
    return normalized


def validate_tripulante_funcao(value: str) -> str:
    if value not in TRIPULANTE_FUNCAO_OPTIONS:
        raise ValueError("Selecione uma funcao operacional valida.")
    return value


def validate_tripulante_categoria(value: str) -> str:
    if value not in TRIPULANTE_CATEGORIA_OPTIONS:
        raise ValueError("Selecione uma categoria operacional valida.")
    return value


def _is_png(payload: bytes) -> bool:
    if not payload.startswith(_PNG_SIGNATURE):
        return False
    offset = len(_PNG_SIGNATURE)
    seen_ihdr = False
    while offset + 12 <= len(payload):
        chunk_length = struct.unpack(">I", payload[offset : offset + 4])[0]
        chunk_type = payload[offset + 4 : offset + 8]
        chunk_end = offset + 12 + chunk_length
        if chunk_end > len(payload):
            return False
        if not seen_ihdr:
            if chunk_type != b"IHDR" or chunk_length != 13:
                return False
            seen_ihdr = True
        if chunk_type == b"IEND":
            return seen_ihdr
        offset = chunk_end
    return False


def _detect_photo_mime(payload: bytes) -> str | None:
    if payload.startswith(b"\xff\xd8\xff") and payload.endswith(b"\xff\xd9"):
        return "image/jpeg"
    if _is_png(payload):
        return "image/png"
    if (
        len(payload) >= 20
        and payload[:4] == b"RIFF"
        and payload[8:12] == b"WEBP"
        and payload[12:16] in _WEBP_CHUNK_TYPES
    ):
        return "image/webp"
    return None


def validate_photo_data_uri(raw_value: str | None) -> tuple[bytes, str]:
    photo_base64 = (raw_value or "").strip()
    match = _PHOTO_DATA_URI_RE.match(photo_base64)
    if not match:
        allowed = ", ".join(PHOTO_ALLOWED_MIME)
        raise ValueError(f"A foto deve estar em um dos tipos permitidos: {allowed}.")
    declared_mime = _PHOTO_DECLARED_MIME[match.group(1).lower()]
    try:
        decoded = base64.b64decode(photo_base64.split(",", 1)[1], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("A foto enviada esta invalida.") from exc
    if not decoded:
        raise ValueError("A foto enviada esta vazia.")
    if len(decoded) > MAX_PHOTO_BYTES:
        raise ValueError("A foto deve ter no maximo 1 MB.")
    detected_mime = _detect_photo_mime(decoded)
    if detected_mime is None:
        raise ValueError("Arquivo de imagem invalido. Envie uma foto real em JPG, PNG ou WEBP.")
    if detected_mime != declared_mime:
        raise ValueError("O conteudo da foto nao corresponde ao tipo informado.")
    return decoded, detected_mime


def _validate_pdf_upload(
    file_storage,
    *,
    policy: UploadPolicy,
):
    if file_storage is None:
        raise ValueError("Selecione um arquivo PDF para enviar.")

    raw_name = (getattr(file_storage, "filename", "") or "").strip()
    if not raw_name or not policy.accepts_extension(raw_name):
        raise ValueError("Apenas arquivos PDF sao permitidos.")
    original_name = safe_pdf_filename(raw_name, fallback=policy.fallback_filename)

    file_bytes = file_storage.read()
    if not file_bytes:
        raise ValueError("O arquivo enviado esta vazio.")
    if len(file_bytes) > policy.max_bytes:
        raise ValueError(f"O PDF excede o limite de {policy.max_mb} MB.")
    if not file_bytes.startswith(PDF_CONTENT_SIGNATURE):
        raise ValueError("Arquivo invalido. Envie um PDF valido.")
    if PDF_EOF_MARKER not in file_bytes[-PDF_EOF_SCAN_BYTES:]:
        raise ValueError("Arquivo PDF invalido ou corrompido.")

    declared_mime = policy.normalize_declared_mime(getattr(file_storage, "mimetype", ""))
    if not policy.accepts_declared_mime(declared_mime):
        raise ValueError("Tipo de arquivo invalido. Envie apenas PDF.")

    return {
        "nome_original": original_name,
        "nome_interno": build_pdf_physical_name(policy.physical_name_kind),
        "mime_type": policy.canonical_mime_type,
        "declared_mime_type": declared_mime,
        "detected_mime_type": policy.canonical_mime_type,
        "upload_policy": policy.key,
        "extension": ".pdf",
        "tamanho_bytes": len(file_bytes),
        "arquivo_hash": hashlib.sha256(file_bytes).hexdigest(),
        "arquivo_pdf": file_bytes,
        "storage_ref": None,
    }


def validate_pdf_upload(file_storage):
    return _validate_pdf_upload(
        file_storage,
        policy=TRAINING_ATTACHMENT_UPLOAD_POLICY,
    )


def validate_tripulante_file_upload(file_storage):
    return _validate_pdf_upload(
        file_storage,
        policy=TRIPULANTE_FILE_UPLOAD_POLICY,
    )


def training_dates_are_valid(data_realizacao, data_vencimento):
    realized = data_realizacao if isinstance(data_realizacao, date) else parse_date(data_realizacao)
    due = data_vencimento if isinstance(data_vencimento, date) else parse_date(data_vencimento)
    if realized and due and realized > due:
        return False
    return True
