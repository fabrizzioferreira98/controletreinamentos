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
from ..core.domain_errors import DomainConflictError, DomainNotFoundError, DomainValidationError
from ..core.http_utils import (
    get_optional_date,
    get_optional_int,
    get_optional_limited_text,
    get_optional_text,
    get_required_int,
    safe_pdf_filename,
)
from ..db import get_db
from ..infra.document_blobs import annotate_document_blob_state, read_document_blob
from ..infra.media_storage import delete_media_ref, write_training_attachment
from ..repositories.dashboard_cache import clear_panel_cache
from ..repositories.treinamentos import (
    create_treinamento,
    create_treinamento_attachment_record,
    delete_treinamento_attachment_record,
    delete_treinamento_notifications,
    find_active_training_attachment_duplicate_hash,
    fetch_treinamento_attachment_row,
    fetch_treinamento_attachments,
    fetch_treinamento_delete_target,
    fetch_treinamento_detail,
    update_treinamento,
)
from ..repositories.treinamentos import (
    delete_treinamento as delete_treinamento_row,
)
from ..service_layers.training_completeness import TrainingCompletenessError, ensure_simple_training_completeness
from ..service_layers.pure_validation import training_dates_are_valid, validate_pdf_upload
from ..services import add_months
from ..training_aircraft_model import is_training_program_record


class TreinamentoValidationError(DomainValidationError, ValueError):
    def __init__(self, message: str, *, code: str = "treinamento_validation_error", status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


class TreinamentoNotFoundError(DomainNotFoundError):
    code = "treinamento_not_found"
    status = 404


class TreinamentoConflictError(DomainConflictError):
    code = "treinamento_conflict"
    status = 409


class TreinamentoAttachmentNotFoundError(DomainNotFoundError):
    code = "treinamento_attachment_not_found"
    status = 404


class TreinamentoAttachmentConflictError(DomainConflictError):
    code = "treinamento_attachment_conflict"
    status = 409


def _ensure_generic_training_write_contract(payload: dict, *, current_training: dict | None = None) -> None:
    if current_training is not None and is_training_program_record(current_training):
        raise TreinamentoValidationError(
            "Este registro pertence ao fluxo de programa e deve ser alterado em treinamentos-tripulantes.",
            code="treinamento_program_record_requires_program_flow",
        )
    try:
        ensure_simple_training_completeness(payload)
    except TrainingCompletenessError as exc:
        raise TreinamentoValidationError(
            str(exc),
            code="treinamento_program_write_requires_program_flow",
        ) from exc


def _validate_training_references(db, tripulante_id, tipo_treinamento_id, equipamento_id, current_training=None):
    tripulante = db.execute("SELECT id FROM tripulantes WHERE id = %s", (tripulante_id,)).fetchone()
    if not tripulante:
        raise ValueError("O tripulante selecionado nao existe.")

    current_tipo_id = current_training["tipo_treinamento_id"] if current_training is not None else None
    tipo = db.execute(
        "SELECT id, exige_equipamento FROM tipos_treinamento WHERE id = %s AND (ativo = 1 OR id = %s)",
        (tipo_treinamento_id, current_tipo_id or 0),
    ).fetchone()
    if not tipo:
        raise ValueError("O tipo de treinamento selecionado nao existe ou esta inativo.")

    if tipo["exige_equipamento"] and equipamento_id is None:
        raise ValueError("Este tipo de treinamento exige um equipamento ou aeronave vinculado.")

    if equipamento_id is not None:
        current_equipamento_id = current_training["equipamento_id"] if current_training is not None else None
        equipamento = db.execute(
            "SELECT id FROM equipamentos WHERE id = %s AND (ativo = 1 OR id = %s)",
            (equipamento_id, current_equipamento_id or 0),
        ).fetchone()
        if not equipamento:
            raise ValueError("O equipamento selecionado nao existe ou esta inativo.")


def _resolve_due_date(db, tipo_treinamento_id, data_realizacao, provided_due_date, due_date_mode="auto"):
    mode = (due_date_mode or "auto").strip().lower()
    if mode == "manual":
        if not provided_due_date:
            raise ValueError("Informe a data de vencimento ao escolher o modo manual.")
        return provided_due_date

    if provided_due_date:
        return provided_due_date
    if not data_realizacao:
        raise ValueError("Informe a data de vencimento ou a data de realizacao para calculo automatico.")
    tipo = db.execute(
        "SELECT periodicidade_meses FROM tipos_treinamento WHERE id = %s",
        (tipo_treinamento_id,),
    ).fetchone()
    if not tipo or not tipo["periodicidade_meses"]:
        raise ValueError(
            "Nao foi possivel calcular o vencimento porque o tipo de treinamento nao possui periodicidade valida."
        )
    calculated_due_date = add_months(data_realizacao, int(tipo["periodicidade_meses"]))
    if not calculated_due_date:
        raise ValueError("Nao foi possivel calcular a data de vencimento com os dados informados.")
    return calculated_due_date


def _parse_training_payload(payload: dict, *, current_training: dict | None = None) -> dict:
    db = get_db()
    _ensure_generic_training_write_contract(payload, current_training=current_training)
    try:
        tripulante_id = get_required_int(payload, "tripulante_id", "Tripulante")
        equipamento_id = get_optional_int(payload, "equipamento_id", "Equipamento")
        tipo_treinamento_id = get_required_int(payload, "tipo_treinamento_id", "Tipo de treinamento")
        data_realizacao = get_optional_date(payload, "data_realizacao", "Data de realização")
        due_date_mode = get_optional_text(payload, "due_date_mode") or "auto"
        _validate_training_references(
            db,
            tripulante_id,
            tipo_treinamento_id,
            equipamento_id,
            current_training=current_training,
        )
        data_vencimento = _resolve_due_date(
            db,
            tipo_treinamento_id,
            data_realizacao,
            get_optional_date(payload, "data_vencimento", "Data de vencimento"),
            due_date_mode,
        )
    except ValueError as exc:
        raise TreinamentoValidationError(str(exc), code="treinamento_validation_error") from exc

    if not training_dates_are_valid(data_realizacao, data_vencimento):
        raise TreinamentoValidationError(
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
    attachments = [annotate_document_blob_state(row) for row in fetch_treinamento_attachments(db, treinamento_id=treinamento_id)]
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
    attachments = []
    try:
        attachments = fetch_treinamento_attachments(db, treinamento_id=treinamento_id, include_removed=True)
        delete_treinamento_notifications(db, treinamento_id=treinamento_id)
        audit_event(db, "treinamento", treinamento_id, "delete", anterior=treinamento)
        delete_treinamento_row(db, treinamento_id=treinamento_id)
        db.commit()
        clear_panel_cache()
        for attachment in attachments:
            delete_media_ref(attachment.get("storage_ref"))
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
    return [annotate_document_blob_state(row) for row in fetch_treinamento_attachments(db, treinamento_id=treinamento_id)]


def _file_storage_from_payload(payload: dict) -> FileStorage:
    raw_bytes = payload.get("arquivo_bytes")
    if isinstance(raw_bytes, bytes):
        content = raw_bytes
    else:
        encoded = str(payload.get("arquivo_base64") or "").strip()
        if not encoded:
            raise TreinamentoValidationError("Selecione um arquivo PDF para enviar.", code="treinamento_attachment_invalid")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise TreinamentoValidationError("Arquivo PDF inválido.", code="treinamento_attachment_invalid") from exc
    raw_filename = str(payload.get("filename") or "").strip()
    fallback_filename = str(payload.get("filename_fallback") or "anexo.pdf")
    filename = safe_pdf_filename(raw_filename, fallback=fallback_filename)
    payload["filename_effective"] = filename
    payload["filename_source"] = "upload" if raw_filename else "fallback"
    payload["filename_was_fallback"] = not bool(raw_filename)
    content_type = str(payload.get("content_type") or payload.get("mime_type") or "").strip()
    return FileStorage(stream=io.BytesIO(content), filename=filename, content_type=content_type)


def upload_treinamento_attachment(payload: dict, *, treinamento_id: int, enviado_por: int) -> dict:
    db = get_db()
    treinamento = fetch_treinamento_detail(db, treinamento_id=treinamento_id)
    if not treinamento:
        raise TreinamentoNotFoundError("Treinamento não encontrado.")
    parsed = None
    try:
        parsed = validate_pdf_upload(_file_storage_from_payload(payload))
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
        duplicate = find_active_training_attachment_duplicate_hash(
            db,
            treinamento_id=treinamento_id,
            arquivo_hash=parsed["arquivo_hash"],
        )
        if duplicate:
            raise TreinamentoAttachmentConflictError(
                f"Duplicado: ja existe um anexo ativo com o mesmo conteudo ({duplicate['nome_original']})."
            )
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
        return annotate_document_blob_state(fetch_treinamento_attachments(db, treinamento_id=treinamento_id)[0])
    except TreinamentoAttachmentConflictError:
        rollback_db(db)
        delete_media_ref(parsed.get("storage_ref") if parsed else None)
        raise
    except ValueError as exc:
        rollback_db(db)
        delete_media_ref(parsed.get("storage_ref") if parsed else None)
        raise TreinamentoValidationError(str(exc), code="treinamento_attachment_invalid") from exc
    except Exception:
        rollback_db(db)
        delete_media_ref(parsed.get("storage_ref") if parsed else None)
        raise


def get_treinamento_attachment(*, treinamento_id: int, anexo_id: int) -> dict:
    db = get_db()
    row = fetch_treinamento_attachment_row(db, treinamento_id=treinamento_id, anexo_id=anexo_id)
    if not row:
        raise TreinamentoAttachmentNotFoundError("Anexo não encontrado.")
    payload_bytes = read_document_blob(row)
    if not payload_bytes:
        raise TreinamentoAttachmentNotFoundError("Anexo não encontrado.")
    row["payload_bytes"] = payload_bytes
    return annotate_document_blob_state(row)


def delete_treinamento_attachment(*, treinamento_id: int, anexo_id: int, removido_por: int | None = None) -> dict:
    db = get_db()
    treinamento = fetch_treinamento_detail(db, treinamento_id=treinamento_id)
    if not treinamento:
        raise TreinamentoNotFoundError("Treinamento não encontrado.")

    row = fetch_treinamento_attachment_row(db, treinamento_id=treinamento_id, anexo_id=anexo_id)
    if not row:
        raise TreinamentoAttachmentNotFoundError("Anexo não encontrado.")

    try:
        audit_event(db, "treinamento_anexo_pdf", anexo_id, "delete", anterior=row)
        delete_treinamento_attachment_record(
            db,
            treinamento_id=treinamento_id,
            anexo_id=anexo_id,
            removido_por=removido_por,
        )
        db.commit()
        row["status"] = "removido"
        row["removido_por"] = removido_por
        row["motivo_status"] = "Removido manualmente."
        return annotate_document_blob_state(row)
    except Exception:
        rollback_db(db)
        raise
