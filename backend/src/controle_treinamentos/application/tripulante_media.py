from __future__ import annotations

import base64
import binascii
import io
import re

from flask import current_app, has_app_context

try:
    import psycopg2
except ImportError:
    psycopg2 = None  # type: ignore[assignment]

from werkzeug.datastructures import FileStorage

from ..constants import MAX_PHOTO_BYTES
from ..core.audit_utils import audit_event, rollback_db
from ..core.domain_errors import DomainConflictError, DomainNotFoundError, DomainUnavailableError, DomainUnexpectedError
from ..core.http_utils import safe_pdf_filename
from ..core.legacy_blob_policy import LEGACY_PHOTO_BLOB_COMPAT_SOURCE
from ..db import get_db
from ..infra.document_blobs import annotate_document_blob_state, read_document_blob
from ..infra.media_storage import delete_media_ref, read_media_bytes, write_tripulante_document, write_tripulante_photo
from ..repositories.tripulante_files import (
    _query_tripulante_file_only,
    find_active_duplicate_hash,
    find_tripulante_file_by_id,
    insert_tripulante_file,
)
from ..repositories.tripulantes import fetch_tripulante_for_write
from ..service_layers.pure_validation import validate_photo_data_uri, validate_tripulante_file_upload
from ..service_layers.tripulante_files import normalize_tipo_documento
from .tripulantes import TripulanteNotFoundError, TripulanteValidationError

_PHOTO_DATA_URI_RE = re.compile(r"^data:image/(png|jpe?g|webp);base64,", re.IGNORECASE)


class TripulanteFileConflictError(DomainConflictError):
    def __init__(self, message: str, *, code: str = "tripulante_file_conflict", status: int = 409):
        super().__init__(message, code=code, status=status)


class TripulanteFileNotFoundError(DomainNotFoundError):
    def __init__(self, message: str, *, code: str = "tripulante_file_not_found", status: int = 404):
        super().__init__(message, code=code, status=status)


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

    raw_filename = str(payload.get("filename") or "").strip()
    fallback_filename = str(payload.get("filename_fallback") or "documento_tripulante.pdf")
    filename = safe_pdf_filename(raw_filename, fallback=fallback_filename)
    payload["filename_effective"] = filename
    payload["filename_source"] = "upload" if raw_filename else "fallback"
    payload["filename_was_fallback"] = not bool(raw_filename)
    content_type = str(payload.get("content_type") or payload.get("mime_type") or "").strip()
    return FileStorage(
        stream=io.BytesIO(content),
        filename=filename,
        content_type=content_type,
    )


def _decode_photo_data_uri(raw_value: str) -> tuple[bytes, str] | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    match = _PHOTO_DATA_URI_RE.match(value)
    if not match:
        return None
    try:
        decoded = base64.b64decode(value.split(",", 1)[1], validate=True)
    except (ValueError, binascii.Error):
        return None
    if not decoded:
        return None
    image_format = match.group(1).lower()
    mime_type = "image/jpeg" if image_format in {"jpg", "jpeg"} else f"image/{image_format}"
    return decoded, mime_type


def _log_legacy_tripulante_photo_read(row: dict, *, source: str) -> None:
    if not has_app_context():
        return
    current_app.logger.warning(
        "Compat residual de foto lida via %s. source=%s tripulante_id=%s foto_storage_ref=%s",
        LEGACY_PHOTO_BLOB_COMPAT_SOURCE,
        source,
        row.get("id") or row.get("tripulante_id") or "",
        row.get("foto_storage_ref") or "",
    )


def load_tripulante_photo_payload(row: dict) -> dict | None:
    storage_ref = str(row.get("foto_storage_ref") or "").strip()
    if storage_ref:
        payload_bytes = read_media_bytes(storage_ref, fallback_bytes=None)
        if payload_bytes:
            return {
                "payload_bytes": payload_bytes,
                "mime_type": (row.get("foto_mime_type") or "").strip() or "image/jpeg",
                "has_photo": True,
                "source": "storage",
                "compat_residual": False,
                "compat_source": "",
            }

    decoded = _decode_photo_data_uri(str(row.get("foto_base64") or ""))
    if decoded:
        payload_bytes, mime_type = decoded
        _log_legacy_tripulante_photo_read(row, source="application.tripulante_media")
        return {
            "payload_bytes": payload_bytes,
            "mime_type": mime_type,
            "has_photo": True,
            "source": "base64",
            "compat_residual": True,
            "compat_source": LEGACY_PHOTO_BLOB_COMPAT_SOURCE,
        }
    return None


def _assert_photo_blob_readable(storage_ref: str | None, expected_bytes: bytes) -> None:
    if read_media_bytes(storage_ref, fallback_bytes=None) != expected_bytes:
        raise DomainUnavailableError(
            "Nao foi possivel confirmar a persistencia fisica da foto.",
            code="tripulante_photo_blob_unavailable",
        )


def resolve_tripulante_photo_state(row: dict) -> dict:
    storage_ref = str(row.get("foto_storage_ref") or "").strip()
    has_legacy_base64 = bool(str(row.get("foto_base64") or "").strip())
    payload = load_tripulante_photo_payload(row)
    if payload:
        return {
            "has_photo": True,
            "source": payload["source"],
            "mime_type": payload["mime_type"],
            "storage_ref": storage_ref,
            "broken_reference": False,
            "compat_residual": bool(payload.get("compat_residual")),
            "compat_source": payload.get("compat_source") or "",
        }
    return {
        "has_photo": False,
        "source": "broken_reference" if storage_ref or has_legacy_base64 else "empty",
        "mime_type": "",
        "storage_ref": storage_ref,
        "broken_reference": bool(storage_ref or has_legacy_base64),
        "compat_residual": False,
        "compat_source": "",
    }


def list_tripulante_files(*, tripulante_id: int) -> list[dict]:
    db = get_db()
    _load_tripulante_for_media(tripulante_id=tripulante_id)
    rows = _query_tripulante_file_only(db, tripulante_id=tripulante_id)
    return [annotate_document_blob_state(dict(row)) for row in rows]


def get_tripulante_file(*, tripulante_id: int, arquivo_id: int) -> dict:
    db = get_db()
    _load_tripulante_for_media(tripulante_id=tripulante_id)
    row = find_tripulante_file_by_id(db, tripulante_id=tripulante_id, arquivo_id=arquivo_id)
    if not row or row.get("status") == "removido":
        raise TripulanteFileNotFoundError("Documento não encontrado.")
    payload_bytes = read_document_blob(dict(row))
    if not payload_bytes:
        raise TripulanteFileNotFoundError("Documento não encontrado.")
    item = dict(row)
    item["payload_bytes"] = payload_bytes
    return annotate_document_blob_state(item)


def upload_tripulante_file(payload: dict, *, tripulante_id: int, enviado_por: int) -> dict:
    db = get_db()
    tripulante = _load_tripulante_for_media(tripulante_id=tripulante_id)
    file_storage = _file_storage_from_payload(payload)
    tipo_documento = normalize_tipo_documento(payload.get("tipo_documento"))
    substitui_arquivo_id_raw = str(payload.get("substitui_arquivo_id") or "").strip()
    substitui_arquivo_id = None
    replaced_row = None
    if substitui_arquivo_id_raw:
        try:
            substitui_arquivo_id = int(substitui_arquivo_id_raw)
        except (TypeError, ValueError) as exc:
            raise TripulanteValidationError(
                "Documento a substituir invalido.",
                code="tripulante_file_invalid_replace_target",
            ) from exc
        if substitui_arquivo_id <= 0:
            raise TripulanteValidationError(
                "Documento a substituir invalido.",
                code="tripulante_file_invalid_replace_target",
            )
        replaced_row = find_tripulante_file_by_id(
            db,
            tripulante_id=tripulante_id,
            arquivo_id=substitui_arquivo_id,
        )
        if not replaced_row:
            raise TripulanteFileNotFoundError("Documento a substituir nao encontrado.")
        replaced_row = dict(replaced_row)
        if replaced_row.get("status") != "ativo":
            raise TripulanteFileConflictError("A substituicao so e permitida para documentos ativos.")
        if not tipo_documento:
            tipo_documento = normalize_tipo_documento(replaced_row.get("tipo_documento"))
    parsed = None
    try:
        parsed = validate_tripulante_file_upload(file_storage)
        payload.update(
            {
                "filename_effective": parsed["nome_original"],
                "validated_mime_type": parsed["mime_type"],
                "detected_mime_type": parsed["detected_mime_type"],
                "upload_policy": parsed["upload_policy"],
                "tamanho_bytes": parsed["tamanho_bytes"],
                "arquivo_hash": parsed["arquivo_hash"],
            }
        )
        duplicate = find_active_duplicate_hash(
            db,
            tripulante_id=tripulante_id,
            arquivo_hash=parsed["arquivo_hash"],
            exclude_id=substitui_arquivo_id,
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
            substitui_arquivo_id=substitui_arquivo_id,
        )
        if substitui_arquivo_id is not None:
            db.execute(
                """
                UPDATE tripulante_arquivos_pdf
                SET status = 'substituido',
                    motivo_status = %s
                WHERE id = %s
                  AND tripulante_id = %s
                """,
                (f"Substituido pelo documento #{created['id']}.", substitui_arquivo_id, tripulante_id),
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
                "substitui_arquivo_id": substitui_arquivo_id,
            },
        )
        if substitui_arquivo_id is not None and replaced_row is not None:
            audit_event(
                db,
                "tripulante_arquivo_pdf",
                substitui_arquivo_id,
                "update",
                anterior={
                    "status": replaced_row.get("status"),
                    "nome_original": replaced_row.get("nome_original"),
                },
                novo={
                    "status": "substituido",
                    "substituido_por_arquivo_id": created["id"],
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
        if psycopg2 is not None and isinstance(exc, psycopg2.IntegrityError):
            raise TripulanteFileConflictError("Falha ao persistir o documento de tripulante.") from exc
        if psycopg2 is not None and isinstance(exc, psycopg2.Error):
            raise DomainUnavailableError(
                "Nao foi possivel persistir o documento de tripulante no momento.",
                code="tripulante_file_persistence_unavailable",
            ) from exc
        raise DomainUnexpectedError(
            "Falha inesperada ao persistir o documento de tripulante.",
            code="tripulante_file_unexpected",
        ) from exc


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
        return annotate_document_blob_state(row)
    except Exception as exc:
        rollback_db(db)
        raise DomainUnavailableError(
            "Nao foi possivel remover o documento de tripulante no momento.",
            code="tripulante_file_delete_unavailable",
        ) from exc


def get_tripulante_photo(*, tripulante_id: int) -> dict:
    row = _load_tripulante_for_media(tripulante_id=tripulante_id)
    payload = load_tripulante_photo_payload(row)
    if payload:
        return payload
    raise TripulanteFileNotFoundError("Foto não encontrada.")


def _tripulante_photo_audit_state(row: dict) -> dict:
    return {
        "has_photo": bool(row.get("foto_storage_ref") or row.get("foto_base64")),
        "storage_ref_present": bool(row.get("foto_storage_ref")),
        "legacy_base64_present": bool(row.get("foto_base64")),
        "mime_type": row.get("foto_mime_type") or "",
    }


def save_tripulante_photo(payload: dict, *, tripulante_id: int) -> dict:
    db = get_db()
    row = _load_tripulante_for_media(tripulante_id=tripulante_id)
    raw_value = str(payload.get("foto_base64") or "").strip()
    if not raw_value:
        raise TripulanteValidationError("Envie a foto em base64 para continuar.", code="tripulante_invalid_photo")
    try:
        decoded, mime_type = validate_photo_data_uri(raw_value)
        match = _PHOTO_DATA_URI_RE.match(raw_value)
    except ValueError as exc:
        raise TripulanteValidationError("A foto enviada está inválida.", code="tripulante_invalid_photo") from exc
    if len(decoded) > MAX_PHOTO_BYTES:
        raise TripulanteValidationError("A foto deve ter no máximo 1 MB.", code="tripulante_invalid_photo")
    image_format = match.group(1).lower()
    mime_type = "image/jpeg" if image_format in {"jpg", "jpeg"} else f"image/{image_format}"
    new_storage_ref = None
    old_storage_ref = row.get("foto_storage_ref")
    try:
        new_storage_ref = write_tripulante_photo(tripulante_id, row.get("nome"), decoded, mime_type=mime_type)
        _assert_photo_blob_readable(new_storage_ref, decoded)
        db.execute(
            """
            UPDATE tripulantes
            SET foto_base64 = NULL,
                foto_storage_ref = %s,
                foto_mime_type = %s,
                possui_foto = %s
            WHERE id = %s
            """,
            (new_storage_ref, mime_type, True, tripulante_id),
        )
        audit_event(
            db,
            "tripulante_photo",
            tripulante_id,
            "update",
            anterior=_tripulante_photo_audit_state(row),
            novo={
                "has_photo": True,
                "storage_ref_present": bool(new_storage_ref),
                "legacy_base64_present": False,
                "mime_type": mime_type,
            },
            observacao="Atualizacao de foto do tripulante.",
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
            SET foto_base64 = NULL,
                foto_storage_ref = %s,
                foto_mime_type = %s,
                possui_foto = %s
            WHERE id = %s
            """,
            (None, None, False, tripulante_id),
        )
        audit_event(
            db,
            "tripulante_photo",
            tripulante_id,
            "delete",
            anterior=_tripulante_photo_audit_state(row),
            novo={
                "has_photo": False,
                "storage_ref_present": False,
                "legacy_base64_present": False,
                "mime_type": "",
            },
            observacao="Remocao de foto do tripulante.",
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
