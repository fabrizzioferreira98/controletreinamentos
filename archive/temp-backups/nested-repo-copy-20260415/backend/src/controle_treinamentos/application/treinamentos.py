from __future__ import annotations

import base64
import binascii
import io

try:
    import psycopg2
except ImportError:
    psycopg2 = None  # type: ignore[assignment]

from werkzeug.datastructures import FileStorage

from ..core.audit_utils import audit_event, rollback_db
from ..core.http_utils import get_optional_date, get_optional_int, get_optional_limited_text, get_optional_text, get_required_int
from ..db import get_db
from ..infra.media_storage import delete_media_ref, read_media_bytes, write_training_attachment
from ..repositories.dashboard_cache import clear_panel_cache
from ..repositories.treinamentos import (
    create_treinamento,
    create_treinamento_attachment_record,
    delete_treinamento as delete_treinamento_row,
    delete_treinamento_attachment_record,
    delete_treinamento_notifications,
    fetch_treinamento_attachment_row,
    fetch_treinamento_attachments,
    fetch_treinamento_delete_target,
    fetch_treinamento_detail,
    update_treinamento,
)
from ..service_layers.domain_validation import resolve_due_date, training_dates_are_valid, validate_pdf_upload, validate_training_references
from .tripulantes import TripulanteValidationError


class TreinamentoNotFoundError(RuntimeError):
    code = "treinamento_not_found"
    status = 404


class TreinamentoConflictError(RuntimeError):
    code = "treinamento_conflict"
    status = 409


class TreinamentoAttachmentNotFoundError(RuntimeError):
    code = "treinamento_attachment_not_found"
    status = 404


def _parse_training_payload(payload: dict, *, current_training: dict | None = None) -> dict:
    db = get_db()
    try:
        tripulante_id = get_required_int(payload, "tripulante_id", "Tripulante")
        equipamento_id = get_optional_int(payload, "equipamento_id", "Equipamento")
        tipo_treinamento_id = get_required_int(payload, "tipo_treinamento_id", "Tipo de treinamento")
        data_realizacao = get_optional_date(payload, "data_realizacao", "Data de realização")
        due_date_mode = get_optional_text(payload, "due_date_mode") or "auto"
        validate_training_references(
            db,
            tripulante_id,
            tipo_treinamento_id,
            equipamento_id,
            current_training=current_training,
        )
        data_vencimento = resolve_due_date(
            db,
            tipo_treinamento_id,
            data_realizacao,
            get_optional_date(payload, "data_vencimento", "Data de vencimento"),
            due_date_mode,
        )
    except ValueError as exc:
        raise TripulanteValidationError(str(exc), code="treinamento_validation_error") from exc

    if not training_dates_are_valid(data_realizacao, data_vencimento):
        raise TripulanteValidationError(
            "A data de realização não pode ser posterior à data de vencimento.",
            code="treinamento_validation_error",
        )

    return {
        "tripulante_id": tripulante_id,
        "equipamento_id": equipamento_id,
        "tipo_treinamento_id": tipo_treinamento_id,
        "data_realizacao": data_realizacao,
        "data_vencimento": data_vencimento,
        "due_date_mode": due_date_mode,
        "observacao": get_optional_limited_text(payload, "observacao", "Observação"),
    }


def save_treinamento(payload: dict, *, treinamento_id: int | None = None) -> dict:
    db = get_db()
    current_training = fetch_treinamento_detail(db, treinamento_id=treinamento_id) if treinamento_id is not None else None
    if treinamento_id is not None and not current_training:
        raise TreinamentoNotFoundError("Treinamento não encontrado.")
    data = _parse_training_payload(payload, current_training=current_training)

    try:
        if treinamento_id is None:
            treinamento_id = create_treinamento(db, data=data)
            audit_event(db, "treinamento", treinamento_id, "create", novo=data)
            operation = "created"
        else:
            update_treinamento(db, treinamento_id=treinamento_id, data=data)
            audit_event(db, "treinamento", treinamento_id, "update", anterior=current_training, novo=data)
            operation = "updated"

        db.commit()
        clear_panel_cache()
    except Exception as exc:
        rollback_db(db)
        if psycopg2 is not None and isinstance(exc, psycopg2.IntegrityError):
            raise TreinamentoConflictError("Não foi possível salvar o treinamento com os dados informados.") from exc
        raise

    detail = fetch_treinamento_detail(db, treinamento_id=treinamento_id)
    attachments = fetch_treinamento_attachments(db, treinamento_id=treinamento_id)
    return {
        "operation": operation,
        "treinamento": detail,
        "attachments": attachments,
    }


def delete_treinamento(*, treinamento_id: int) -> dict:
    db = get_db()
    treinamento = fetch_treinamento_delete_target(db, treinamento_id=treinamento_id)
    if not treinamento:
        raise TreinamentoNotFoundError("Treinamento não encontrado.")
    try:
        delete_treinamento_notifications(db, treinamento_id=treinamento_id)
        audit_event(db, "treinamento", treinamento_id, "delete", anterior=treinamento)
        delete_treinamento_row(db, treinamento_id=treinamento_id)
        db.commit()
        clear_panel_cache()
        return {
            "operation": "deleted",
            "treinamento_id": treinamento_id,
        }
    except Exception as exc:
        rollback_db(db)
        if psycopg2 is not None and isinstance(exc, psycopg2.Error):
            raise TreinamentoConflictError("Não foi possível excluir o treinamento no momento.") from exc
        raise


def list_treinamento_attachments(*, treinamento_id: int) -> list[dict]:
    db = get_db()
    treinamento = fetch_treinamento_detail(db, treinamento_id=treinamento_id)
    if not treinamento:
        raise TreinamentoNotFoundError("Treinamento não encontrado.")
    return fetch_treinamento_attachments(db, treinamento_id=treinamento_id)


def _file_storage_from_payload(payload: dict) -> FileStorage:
    raw_bytes = payload.get("arquivo_bytes")
    if isinstance(raw_bytes, bytes):
        content = raw_bytes
    else:
        encoded = str(payload.get("arquivo_base64") or "").strip()
        if not encoded:
            raise TripulanteValidationError("Selecione um arquivo PDF para enviar.", code="treinamento_attachment_invalid")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise TripulanteValidationError("Arquivo PDF inválido.", code="treinamento_attachment_invalid") from exc
    filename = str(payload.get("filename") or "anexo.pdf")
    return FileStorage(stream=io.BytesIO(content), filename=filename, content_type="application/pdf")


def upload_treinamento_attachment(payload: dict, *, treinamento_id: int, enviado_por: int) -> dict:
    db = get_db()
    treinamento = fetch_treinamento_detail(db, treinamento_id=treinamento_id)
    if not treinamento:
        raise TreinamentoNotFoundError("Treinamento não encontrado.")
    parsed = None
    try:
        parsed = validate_pdf_upload(_file_storage_from_payload(payload))
        parsed["storage_ref"] = write_training_attachment(
            treinamento["tripulante_id"],
            treinamento.get("tripulante_nome"),
            treinamento_id,
            parsed["nome_interno"],
            parsed["arquivo_pdf"],
        )
        anexo_id = create_treinamento_attachment_record(
            db,
            treinamento_id=treinamento_id,
            parsed=parsed,
            enviado_por=enviado_por,
        )
        audit_event(
            db,
            "treinamento_anexo_pdf",
            anexo_id,
            "create",
            novo={
                "treinamento_id": treinamento_id,
                "nome_original": parsed["nome_original"],
                "mime_type": parsed["mime_type"],
                "tamanho_bytes": parsed["tamanho_bytes"],
            },
        )
        db.commit()
        return fetch_treinamento_attachments(db, treinamento_id=treinamento_id)[0]
    except ValueError as exc:
        rollback_db(db)
        delete_media_ref(parsed.get("storage_ref") if parsed else None)
        raise TripulanteValidationError(str(exc), code="treinamento_attachment_invalid") from exc
    except Exception:
        rollback_db(db)
        delete_media_ref(parsed.get("storage_ref") if parsed else None)
        raise


def get_treinamento_attachment(*, treinamento_id: int, anexo_id: int) -> dict:
    db = get_db()
    row = fetch_treinamento_attachment_row(db, treinamento_id=treinamento_id, anexo_id=anexo_id)
    if not row:
        raise TreinamentoAttachmentNotFoundError("Anexo não encontrado.")
    payload_bytes = read_media_bytes(
        row.get("storage_ref"),
        fallback_bytes=bytes(row["arquivo_pdf"]) if row.get("arquivo_pdf") is not None else None,
    )
    if not payload_bytes:
        raise TreinamentoAttachmentNotFoundError("Anexo não encontrado.")
    row["payload_bytes"] = payload_bytes
    return row


def delete_treinamento_attachment(*, treinamento_id: int, anexo_id: int) -> dict:
    db = get_db()
    treinamento = fetch_treinamento_detail(db, treinamento_id=treinamento_id)
    if not treinamento:
        raise TreinamentoNotFoundError("Treinamento não encontrado.")

    row = fetch_treinamento_attachment_row(db, treinamento_id=treinamento_id, anexo_id=anexo_id)
    if not row:
        raise TreinamentoAttachmentNotFoundError("Anexo não encontrado.")

    storage_ref = row.get("storage_ref")
    try:
        audit_event(db, "treinamento_anexo_pdf", anexo_id, "delete", anterior=row)
        delete_treinamento_attachment_record(db, treinamento_id=treinamento_id, anexo_id=anexo_id)
        db.commit()
        delete_media_ref(storage_ref)
        return row
    except Exception:
        rollback_db(db)
        raise
