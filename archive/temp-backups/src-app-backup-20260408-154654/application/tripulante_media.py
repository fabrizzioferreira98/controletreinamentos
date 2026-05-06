from __future__ import annotations

import base64
import binascii
import io
import re

try:
    import psycopg2
except ImportError:
    psycopg2 = None  # type: ignore[assignment]

from werkzeug.datastructures import FileStorage

from ..constants import MAX_PHOTO_BYTES
from ..core.audit_utils import audit_event, rollback_db
from ..core.http_utils import safe_pdf_filename
from ..db import get_db
from ..infra.media_storage import delete_media_ref, read_media_bytes, write_tripulante_document, write_tripulante_photo
from ..repositories.tripulante_files import (
    _query_tripulante_file_only,
    find_active_duplicate_hash,
    find_tripulante_file_by_id,
    insert_tripulante_file,
)
from ..repositories.tripulantes import fetch_tripulante_for_write
from ..service_layers.domain_validation import validate_tripulante_file_upload
from ..service_layers.tripulante_files import normalize_tipo_documento
from .tripulantes import TripulanteNotFoundError, TripulanteValidationError

_PHOTO_DATA_URI_RE = re.compile(r"^data:image/(png|jpe?g|webp);base64,", re.IGNORECASE)


class TripulanteFileConflictError(RuntimeError):
    code = "tripulante_file_conflict"
    status = 409


class TripulanteFileNotFoundError(RuntimeError):
    code = "tripulante_file_not_found"
    status = 404


def _load_tripulante_for_media(*, tripulante_id: int) -> dict:
    db = get_db()
    row = fetch_tripulante_for_write(db, tripulante_id=tripulante_id)
    if not row:
        raise TripulanteNotFoundError("Tripulante não encontrado.")
    return row


def _file_storage_from_payload(payload: dict) -> FileStorage:
    raw_bytes = payload.get("arquivo_bytes")
    if isinstance(raw_bytes, bytes):
        content = raw_bytes
    else:
        encoded = str(payload.get("arquivo_base64") or "").strip()
        if not encoded:
            raise TripulanteValidationError("Selecione um arquivo PDF para enviar.", code="tripulante_file_invalid_upload")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise TripulanteValidationError("Arquivo PDF inválido.", code="tripulante_file_invalid_upload") from exc

    filename = safe_pdf_filename(payload.get("filename"), fallback="documento_tripulante.pdf")
    return FileStorage(
        stream=io.BytesIO(content),
        filename=filename,
        content_type="application/pdf",
    )


def list_tripulante_files(*, tripulante_id: int) -> list[dict]:
    db = get_db()
    _load_tripulante_for_media(tripulante_id=tripulante_id)
    rows = _query_tripulante_file_only(db, tripulante_id=tripulante_id)
    return [dict(row) for row in rows]


def get_tripulante_file(*, tripulante_id: int, arquivo_id: int) -> dict:
    db = get_db()
    _load_tripulante_for_media(tripulante_id=tripulante_id)
    row = find_tripulante_file_by_id(db, tripulante_id=tripulante_id, arquivo_id=arquivo_id)
    if not row or row.get("status") == "removido":
        raise TripulanteFileNotFoundError("Documento não encontrado.")
    payload_bytes = read_media_bytes(
        row.get("storage_ref"),
        fallback_bytes=bytes(row["arquivo_pdf"]) if row.get("arquivo_pdf") is not None else None,
    )
    if not payload_bytes:
        raise TripulanteFileNotFoundError("Documento não encontrado.")
    item = dict(row)
    item["payload_bytes"] = payload_bytes
    return item


def upload_tripulante_file(payload: dict, *, tripulante_id: int, enviado_por: int) -> dict:
    db = get_db()
    tripulante = _load_tripulante_for_media(tripulante_id=tripulante_id)
    file_storage = _file_storage_from_payload(payload)
    tipo_documento = normalize_tipo_documento(payload.get("tipo_documento"))
    parsed = None
    try:
        parsed = validate_tripulante_file_upload(file_storage)
        duplicate = find_active_duplicate_hash(
            db,
            tripulante_id=tripulante_id,
            arquivo_hash=parsed["arquivo_hash"],
        )
        if duplicate:
            raise TripulanteFileConflictError(
                f"Duplicado: já existe um documento ativo com o mesmo conteúdo ({duplicate['nome_original']})."
            )
        parsed["storage_ref"] = write_tripulante_document(
            tripulante_id,
            tripulante.get("nome"),
            parsed["nome_interno"],
            parsed["arquivo_pdf"],
        )
        created = insert_tripulante_file(
            db,
            tripulante_id=tripulante_id,
            tipo_documento=tipo_documento,
            payload=parsed,
            enviado_por=enviado_por,
        )
        audit_event(
            db,
            "tripulante_arquivo_pdf",
            created["id"],
            "create",
            novo={
                "tripulante_id": tripulante_id,
                "tipo_documento": tipo_documento,
                "nome_original": parsed["nome_original"],
                "mime_type": parsed["mime_type"],
                "tamanho_bytes": parsed["tamanho_bytes"],
            },
        )
        db.commit()
        return get_tripulante_file(tripulante_id=tripulante_id, arquivo_id=int(created["id"]))
    except TripulanteFileConflictError:
        rollback_db(db)
        delete_media_ref(parsed.get("storage_ref") if parsed else None)
        raise
    except ValueError as exc:
        rollback_db(db)
        delete_media_ref(parsed.get("storage_ref") if parsed else None)
        raise TripulanteValidationError(str(exc), code="tripulante_file_invalid_upload") from exc
    except Exception as exc:
        rollback_db(db)
        delete_media_ref(parsed.get("storage_ref") if parsed else None)
        if psycopg2 is not None and isinstance(exc, psycopg2.Error):
            raise TripulanteFileConflictError("Falha ao persistir o documento de tripulante.") from exc
        raise


def delete_tripulante_file(*, tripulante_id: int, arquivo_id: int, removido_por: int) -> dict:
    db = get_db()
    _load_tripulante_for_media(tripulante_id=tripulante_id)
    row = find_tripulante_file_by_id(db, tripulante_id=tripulante_id, arquivo_id=arquivo_id)
    if not row:
        raise TripulanteFileNotFoundError("Documento não encontrado.")
    row = dict(row)
    if row.get("status") == "removido":
        raise TripulanteFileConflictError("Este documento já foi removido anteriormente.")
    try:
        db.execute(
            """
            UPDATE tripulante_arquivos_pdf
            SET status = 'removido',
                removido_por = %s,
                removido_em = CURRENT_TIMESTAMP,
                motivo_status = %s
            WHERE id = %s AND tripulante_id = %s
            """,
            (removido_por, "Removido manualmente via API.", arquivo_id, tripulante_id),
        )
        audit_event(
            db,
            "tripulante_arquivo_pdf",
            arquivo_id,
            "delete",
            anterior={
                "tripulante_id": tripulante_id,
                "nome_original": row.get("nome_original"),
                "status": row.get("status"),
                "tamanho_bytes": row.get("tamanho_bytes"),
            },
            novo={"status": "removido"},
        )
        db.commit()
        row["status"] = "removido"
        row["motivo_status"] = "Removido manualmente via API."
        row["removido_por"] = removido_por
        return row
    except Exception:
        rollback_db(db)
        raise


def get_tripulante_photo(*, tripulante_id: int) -> dict:
    row = _load_tripulante_for_media(tripulante_id=tripulante_id)
    payload_bytes = read_media_bytes(
        row.get("foto_storage_ref"),
        fallback_bytes=None,
    )
    if payload_bytes:
        return {
            "payload_bytes": payload_bytes,
            "mime_type": (row.get("foto_mime_type") or "").strip() or "image/jpeg",
            "has_photo": True,
        }
    raw_value = str(row.get("foto_base64") or "").strip()
    if raw_value:
        match = _PHOTO_DATA_URI_RE.match(raw_value)
        if match:
            try:
                decoded = base64.b64decode(raw_value.split(",", 1)[1], validate=True)
            except (ValueError, binascii.Error):
                decoded = None
            if decoded:
                image_format = match.group(1).lower()
                mime_type = "image/jpeg" if image_format in {"jpg", "jpeg"} else f"image/{image_format}"
                return {
                    "payload_bytes": decoded,
                    "mime_type": mime_type,
                    "has_photo": True,
                }
    raise TripulanteFileNotFoundError("Foto não encontrada.")


def save_tripulante_photo(payload: dict, *, tripulante_id: int) -> dict:
    db = get_db()
    row = _load_tripulante_for_media(tripulante_id=tripulante_id)
    raw_value = str(payload.get("foto_base64") or "").strip()
    if not raw_value:
        raise TripulanteValidationError("Envie a foto em base64 para continuar.", code="tripulante_invalid_photo")
    match = _PHOTO_DATA_URI_RE.match(raw_value)
    if not match:
        raise TripulanteValidationError("A foto deve estar em JPG, PNG ou WEBP.", code="tripulante_invalid_photo")
    try:
        decoded = base64.b64decode(raw_value.split(",", 1)[1], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise TripulanteValidationError("A foto enviada está inválida.", code="tripulante_invalid_photo") from exc
    if len(decoded) > MAX_PHOTO_BYTES:
        raise TripulanteValidationError("A foto deve ter no máximo 1 MB.", code="tripulante_invalid_photo")
    image_format = match.group(1).lower()
    mime_type = "image/jpeg" if image_format in {"jpg", "jpeg"} else f"image/{image_format}"
    new_storage_ref = None
    old_storage_ref = row.get("foto_storage_ref")
    try:
        new_storage_ref = write_tripulante_photo(tripulante_id, row.get("nome"), decoded, mime_type=mime_type)
        db.execute(
            """
            UPDATE tripulantes
            SET foto_base64 = %s,
                foto_storage_ref = %s,
                foto_mime_type = %s,
                possui_foto = %s
            WHERE id = %s
            """,
            (None, new_storage_ref, mime_type, True, tripulante_id),
        )
        db.commit()
        delete_media_ref(old_storage_ref)
        return {
            "tripulante_id": tripulante_id,
            "has_photo": True,
            "photo_storage_ref": new_storage_ref,
            "mime_type": mime_type,
        }
    except Exception:
        rollback_db(db)
        delete_media_ref(new_storage_ref)
        raise


def delete_tripulante_photo(*, tripulante_id: int) -> dict:
    db = get_db()
    row = _load_tripulante_for_media(tripulante_id=tripulante_id)
    storage_ref = row.get("foto_storage_ref")
    if not storage_ref and not row.get("foto_base64"):
        raise TripulanteFileNotFoundError("Foto não encontrada.")
    try:
        db.execute(
            """
            UPDATE tripulantes
            SET foto_base64 = %s,
                foto_storage_ref = %s,
                foto_mime_type = %s,
                possui_foto = %s
            WHERE id = %s
            """,
            (None, None, None, False, tripulante_id),
        )
        db.commit()
        delete_media_ref(storage_ref)
        return {
            "tripulante_id": tripulante_id,
            "has_photo": False,
        }
    except Exception:
        rollback_db(db)
        raise
