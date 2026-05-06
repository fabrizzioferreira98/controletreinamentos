"""Legacy pure-validation surface kept for backward-compatible imports."""

from __future__ import annotations

import hashlib
from datetime import date
from uuid import uuid4

from ..constants import (
    TRAINING_ATTACHMENT_ALLOWED_MIME,
    TRAINING_ATTACHMENT_MAX_BYTES,
    TRIPULANTE_CATEGORIA_OPTIONS,
    TRIPULANTE_FILE_ALLOWED_MIME,
    TRIPULANTE_FILE_MAX_BYTES,
    TRIPULANTE_FUNCAO_OPTIONS,
    TRIPULANTE_STATUS_OPTIONS,
)
from ..core.http_utils import safe_pdf_filename
from ..services import parse_date


_TRIPULANTE_STATUS_CANONICAL_MAP = {
    "ativo": "Ativo",
    "folga": "Folga",
    "ferias": "Férias",
    "férias": "Férias",
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
    if normalized == "Férias":
        # Compatibilidade com registros históricos sem acento.
        return ("Férias", "Ferias")
    return (normalized,)


def validate_tripulante_status(value: str) -> str:
    normalized = normalize_tripulante_status(value)
    if normalized is None or normalized not in TRIPULANTE_STATUS_OPTIONS:
        raise ValueError("Selecione um status válido para o tripulante.")
    return normalized

def validate_tripulante_funcao(value: str) -> str:
    if value not in TRIPULANTE_FUNCAO_OPTIONS:
        raise ValueError("Selecione uma função operacional válida.")
    return value

def validate_tripulante_categoria(value: str) -> str:
    if value not in TRIPULANTE_CATEGORIA_OPTIONS:
        raise ValueError("Selecione uma categoria operacional válida.")
    return value

def _validate_pdf_upload(
    file_storage,
    *,
    max_bytes: int,
    allowed_mime: set[str],
    fallback_name: str,
):
    if file_storage is None:
        raise ValueError("Selecione um arquivo PDF para enviar.")

    raw_name = (getattr(file_storage, "filename", "") or "").strip()
    if not raw_name or not raw_name.lower().endswith(".pdf"):
        raise ValueError("Apenas arquivos PDF são permitidos.")
    original_name = safe_pdf_filename(raw_name, fallback=fallback_name)

    file_bytes = file_storage.read()
    if not file_bytes:
        raise ValueError("O arquivo enviado está vazio.")
    if len(file_bytes) > max_bytes:
        raise ValueError(f"O PDF excede o limite de {max_bytes // (1024 * 1024)} MB.")
    if not file_bytes.startswith(b"%PDF"):
        raise ValueError("Arquivo inválido. Envie um PDF válido.")
    if b"%%EOF" not in file_bytes[-4096:]:
        raise ValueError("Arquivo PDF inválido ou corrompido.")

    mime_type = (getattr(file_storage, "mimetype", "") or "").lower().strip()
    if mime_type and mime_type not in allowed_mime and mime_type != "application/octet-stream":
        raise ValueError("Tipo de arquivo inválido. Envie apenas PDF.")

    return {
        "nome_original": original_name,
        "nome_interno": f"{uuid4().hex}_{original_name}",
        "mime_type": "application/pdf",
        "tamanho_bytes": len(file_bytes),
        "arquivo_hash": hashlib.sha256(file_bytes).hexdigest(),
        "arquivo_pdf": file_bytes,
        "storage_ref": None,
    }

def validate_pdf_upload(file_storage):
    return _validate_pdf_upload(
        file_storage,
        max_bytes=TRAINING_ATTACHMENT_MAX_BYTES,
        allowed_mime=TRAINING_ATTACHMENT_ALLOWED_MIME,
        fallback_name="anexo.pdf",
    )

def validate_tripulante_file_upload(file_storage):
    return _validate_pdf_upload(
        file_storage,
        max_bytes=TRIPULANTE_FILE_MAX_BYTES,
        allowed_mime=TRIPULANTE_FILE_ALLOWED_MIME,
        fallback_name="documento_tripulante.pdf",
    )

def training_dates_are_valid(data_realizacao, data_vencimento):
    realized = data_realizacao if isinstance(data_realizacao, date) else parse_date(data_realizacao)
    due = data_vencimento if isinstance(data_vencimento, date) else parse_date(data_vencimento)
    if realized and due and realized > due:
        return False
    return True
