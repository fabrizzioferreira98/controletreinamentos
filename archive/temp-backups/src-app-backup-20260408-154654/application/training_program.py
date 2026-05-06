from __future__ import annotations

import base64
import binascii
import io
from decimal import Decimal

try:
    import psycopg2
except ImportError:
    psycopg2 = None  # type: ignore[assignment]

from werkzeug.datastructures import FileStorage

from ..constants import TRAINING_MASTER_STATUS_OPTIONS, TRAINING_PERIODICITY_OPTIONS, TRAINING_SEGMENT_MODEL_OPTIONS
from ..core.audit_utils import audit_event, rollback_db
from ..core.http_utils import (
    get_optional_date,
    get_optional_decimal,
    get_optional_limited_text,
    get_optional_text,
    get_required_int,
    get_required_text,
)
from ..db import get_db
from ..infra.media_storage import delete_media_ref, write_training_attachment
from ..repositories.dashboard_cache import clear_catalog_options_cache, clear_panel_cache
from ..repositories.training_program import (
    fetch_training_master_hour_detail,
    fetch_training_master_segment_detail,
    fetch_training_master_type_detail,
    fetch_training_program_record_detail,
)
from ..repositories.treinamentos import fetch_treinamento_attachments
from ..service_layers.domain_validation import training_dates_are_valid, validate_pdf_upload
from ..services import add_months


class TrainingProgramValidationError(RuntimeError):
    def __init__(self, message: str, *, code: str = "training_program_validation_error", status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


class TrainingProgramNotFoundError(RuntimeError):
    def __init__(self, message: str, *, code: str = "training_program_not_found", status: int = 404):
        super().__init__(message)
        self.code = code
        self.status = status


class TrainingProgramConflictError(RuntimeError):
    def __init__(self, message: str, *, code: str = "training_program_conflict", status: int = 409):
        super().__init__(message)
        self.code = code
        self.status = status


class TrainingProgramAttachmentError(RuntimeError):
    def __init__(self, message: str, *, code: str = "training_program_attachment_error", status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


def _normalize_status(value: str, *, field_name: str = "Status") -> int:
    raw = str(value or "").strip().lower()
    if raw in {"ativo", "1", "true", "sim", "yes", "on"}:
        return 1
    if raw in {"inativo", "0", "false", "nao", "não", "off"}:
        return 0
    raise TrainingProgramValidationError(
        f"{field_name} invalido. Use uma das opcoes: {', '.join(TRAINING_MASTER_STATUS_OPTIONS)}.",
        code="training_program_invalid_status",
    )


def _normalize_segment_model(value: str) -> str:
    raw = str(value or "").strip()
    allowed = {item.lower(): item for item in TRAINING_SEGMENT_MODEL_OPTIONS}
    resolved = allowed.get(raw.lower())
    if not resolved:
        raise TrainingProgramValidationError(
            "Modelo do segmento invalido.",
            code="training_program_invalid_segment_model",
        )
    return resolved


def _normalize_periodicity(value) -> int:
    raw = str(value or "").strip().lower()
    mapping = {
        "12": 12,
        "12 meses": 12,
        "24": 24,
        "24 meses": 24,
        "0": 0,
        "sem validade": 0,
    }
    if raw not in mapping:
        allowed = ", ".join(item["label"] for item in TRAINING_PERIODICITY_OPTIONS)
        raise TrainingProgramValidationError(
            f"Periodicidade invalida. Use uma das opcoes: {allowed}.",
            code="training_program_invalid_periodicity",
        )
    return int(mapping[raw])


def _normalize_requires_aircraft(value) -> int:
    raw = str(value or "").strip().lower()
    if raw in {"sim", "1", "true", "yes", "on"}:
        return 1
    if raw in {"nao", "não", "0", "false", "no", "off"}:
        return 0
    raise TrainingProgramValidationError(
        "Exige aeronave invalido.",
        code="training_program_invalid_requires_aircraft",
    )


def _optional_decimal_to_value(payload: dict, field_name: str, label: str) -> Decimal:
    value = get_optional_decimal(payload, field_name, label)
    return value if value is not None else Decimal("0")


def _ensure_tripulante_exists(db, *, tripulante_id: int) -> dict:
    row = db.execute(
        """
        SELECT c.id, c.nome, COALESCE(p.matricula, c.licenca_anac, '') AS matricula
        FROM tripulantes c
        LEFT JOIN pilotos p ON p.tripulante_id = c.id
        WHERE c.id = %s
        """,
        (tripulante_id,),
    ).fetchone()
    if not row:
        raise TrainingProgramValidationError("Tripulante invalido.", code="training_program_tripulante_not_found")
    return dict(row)


def _ensure_tipo_exists(db, *, tipo_treinamento_id: int, include_inactive: bool = False) -> dict:
    params = [int(tipo_treinamento_id)]
    where = "WHERE id = %s"
    if not include_inactive:
        where += " AND ativo = 1"
    row = db.execute(
        f"""
        SELECT id, nome, codigo, descricao, periodicidade_meses, exige_equipamento, ativo
        FROM tipos_treinamento
        {where}
        LIMIT 1
        """,
        tuple(params),
    ).fetchone()
    if not row:
        raise TrainingProgramValidationError("Tipo de treinamento invalido.", code="training_program_type_not_found")
    return dict(row)


def _ensure_segment_exists(db, *, segmento_id: int, tipo_treinamento_id: int | None = None, include_inactive: bool = False) -> dict:
    clauses = ["st.id = %s"]
    params: list = [int(segmento_id)]
    if tipo_treinamento_id is not None:
        clauses.append("st.tipo_treinamento_id = %s")
        params.append(int(tipo_treinamento_id))
    if not include_inactive:
        clauses.append("st.ativo = 1")
    row = db.execute(
        f"""
        SELECT st.*
        FROM segmentos_teoricos st
        WHERE {' AND '.join(clauses)}
        LIMIT 1
        """,
        tuple(params),
    ).fetchone()
    if not row:
        raise TrainingProgramValidationError("Segmento teorico invalido.", code="training_program_segment_not_found")
    return dict(row)


def _ensure_hour_exists(db, *, hora_id: int, include_inactive: bool = False) -> dict:
    clauses = ["hv.id = %s"]
    if not include_inactive:
        clauses.append("hv.ativo = 1")
    row = db.execute(
        f"""
        SELECT hv.*
        FROM horas_voo_aeronave hv
        WHERE {' AND '.join(clauses)}
        LIMIT 1
        """,
        (int(hora_id),),
    ).fetchone()
    if not row:
        raise TrainingProgramValidationError("Registro de horas de voo invalido.", code="training_program_hour_not_found")
    return dict(row)


def _sync_tipo_periodicidade(db, *, tipo_treinamento_id: int) -> None:
    row = db.execute(
        """
        SELECT COALESCE(MAX(periodicidade_meses), 0) AS periodicidade_meses
        FROM segmentos_teoricos
        WHERE tipo_treinamento_id = %s
          AND ativo = 1
        """,
        (tipo_treinamento_id,),
    ).fetchone()
    periodicidade = int(row["periodicidade_meses"] or 0) if row else 0
    db.execute(
        "UPDATE tipos_treinamento SET periodicidade_meses = %s WHERE id = %s",
        (periodicidade, tipo_treinamento_id),
    )


def _hours_require_ctac(hours_row: dict | None) -> bool:
    return bool(hours_row and "conforme ctac" in str(hours_row.get("observacao") or "").strip().lower())


def _parse_type_payload(payload: dict) -> dict:
    nome = get_required_text(payload, "nome", "Nome do treinamento")
    codigo = get_required_text(payload, "codigo", "Codigo do treinamento")
    return {
        "nome": nome,
        "codigo": codigo,
        "descricao": get_optional_limited_text(payload, "descricao", "Descricao"),
        "ativo": _normalize_status(payload.get("status"), field_name="Status do treinamento"),
        "exige_equipamento": _normalize_requires_aircraft(payload.get("exige_aeronave") or payload.get("exige_equipamento") or "Nao"),
    }


def save_training_master_type(payload: dict, *, tipo_treinamento_id: int | None = None) -> dict:
    db = get_db()
    current = fetch_training_master_type_detail(db, tipo_treinamento_id=tipo_treinamento_id) if tipo_treinamento_id else None
    if tipo_treinamento_id and not current:
        raise TrainingProgramNotFoundError("Tipo de treinamento nao encontrado.", code="training_program_type_not_found")
    data = _parse_type_payload(payload)
    try:
        if tipo_treinamento_id is None:
            created = db.execute(
                """
                INSERT INTO tipos_treinamento (nome, codigo, descricao, periodicidade_meses, exige_equipamento, ativo)
                VALUES (%s, %s, %s, 0, %s, %s)
                RETURNING id
                """,
                (
                    data["nome"],
                    data["codigo"],
                    data["descricao"],
                    data["exige_equipamento"],
                    data["ativo"],
                ),
            ).fetchone()
            tipo_treinamento_id = int(created["id"])
            audit_event(db, "tipo_treinamento", tipo_treinamento_id, "create", novo=data)
            operation = "created"
        else:
            db.execute(
                """
                UPDATE tipos_treinamento
                SET nome = %s,
                    codigo = %s,
                    descricao = %s,
                    exige_equipamento = %s,
                    ativo = %s
                WHERE id = %s
                """,
                (
                    data["nome"],
                    data["codigo"],
                    data["descricao"],
                    data["exige_equipamento"],
                    data["ativo"],
                    tipo_treinamento_id,
                ),
            )
            audit_event(db, "tipo_treinamento", tipo_treinamento_id, "update", anterior=current, novo=data)
            operation = "updated"
        _sync_tipo_periodicidade(db, tipo_treinamento_id=tipo_treinamento_id)
        db.commit()
        clear_catalog_options_cache()
        clear_panel_cache()
    except Exception as exc:
        rollback_db(db)
        if psycopg2 is not None and isinstance(exc, psycopg2.IntegrityError):
            raise TrainingProgramConflictError(
                "Ja existe um tipo de treinamento com este codigo.",
                code="training_program_type_conflict",
            ) from exc
        raise
    return {
        "operation": operation,
        "tipo": fetch_training_master_type_detail(db, tipo_treinamento_id=tipo_treinamento_id),
    }


def delete_training_master_type(*, tipo_treinamento_id: int) -> dict:
    db = get_db()
    current = fetch_training_master_type_detail(db, tipo_treinamento_id=tipo_treinamento_id)
    if not current:
        raise TrainingProgramNotFoundError("Tipo de treinamento nao encontrado.", code="training_program_type_not_found")
    linked = db.execute(
        "SELECT id FROM treinamentos WHERE tipo_treinamento_id = %s LIMIT 1",
        (tipo_treinamento_id,),
    ).fetchone()
    if linked:
        raise TrainingProgramConflictError(
            "Nao e possivel excluir este tipo porque existem treinamentos registrados.",
            code="training_program_type_in_use",
        )
    try:
        audit_event(db, "tipo_treinamento", tipo_treinamento_id, "delete", anterior=current)
        db.execute("DELETE FROM horas_voo_aeronave WHERE tipo_treinamento_id = %s", (tipo_treinamento_id,))
        db.execute("DELETE FROM segmentos_teoricos WHERE tipo_treinamento_id = %s", (tipo_treinamento_id,))
        db.execute("DELETE FROM tipos_treinamento WHERE id = %s", (tipo_treinamento_id,))
        db.commit()
        clear_catalog_options_cache()
        clear_panel_cache()
    except Exception:
        rollback_db(db)
        raise
    return {"deleted_id": tipo_treinamento_id}


def _parse_segment_payload(payload: dict, *, current: dict | None = None) -> dict:
    db = get_db()
    tipo_treinamento_id = get_required_int(payload, "tipo_treinamento_id", "Tipo de treinamento")
    _ensure_tipo_exists(db, tipo_treinamento_id=tipo_treinamento_id, include_inactive=bool(current))
    return {
        "tipo_treinamento_id": tipo_treinamento_id,
        "modelo_segmento": _normalize_segment_model(payload.get("modelo_segmento")),
        "nome_segmento": get_required_text(payload, "nome_segmento", "Nome do segmento"),
        "carga_horaria": _optional_decimal_to_value(payload, "carga_horaria", "Carga horaria"),
        "carga_teorica": _optional_decimal_to_value(payload, "carga_teorica", "Carga teorica"),
        "carga_pratica": _optional_decimal_to_value(payload, "carga_pratica", "Carga pratica"),
        "periodicidade_meses": _normalize_periodicity(payload.get("periodicidade_meses")),
        "observacao": get_optional_limited_text(payload, "observacao", "Observacao"),
        "ativo": 1 if payload.get("ativo", "1") not in {"0", 0, False, "false"} else 0,
    }


def save_training_master_segment(payload: dict, *, segmento_id: int | None = None) -> dict:
    db = get_db()
    current = fetch_training_master_segment_detail(db, segmento_id=segmento_id) if segmento_id else None
    if segmento_id and not current:
        raise TrainingProgramNotFoundError("Segmento teorico nao encontrado.", code="training_program_segment_not_found")
    data = _parse_segment_payload(payload, current=current)
    try:
        if segmento_id is None:
            created = db.execute(
                """
                INSERT INTO segmentos_teoricos
                (
                    tipo_treinamento_id,
                    modelo_segmento,
                    nome_segmento,
                    carga_horaria,
                    carga_teorica,
                    carga_pratica,
                    periodicidade_meses,
                    observacao,
                    ativo
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    data["tipo_treinamento_id"],
                    data["modelo_segmento"],
                    data["nome_segmento"],
                    data["carga_horaria"],
                    data["carga_teorica"],
                    data["carga_pratica"],
                    data["periodicidade_meses"],
                    data["observacao"],
                    data["ativo"],
                ),
            ).fetchone()
            segmento_id = int(created["id"])
            audit_event(db, "segmento_teorico", segmento_id, "create", novo=data)
            operation = "created"
        else:
            db.execute(
                """
                UPDATE segmentos_teoricos
                SET tipo_treinamento_id = %s,
                    modelo_segmento = %s,
                    nome_segmento = %s,
                    carga_horaria = %s,
                    carga_teorica = %s,
                    carga_pratica = %s,
                    periodicidade_meses = %s,
                    observacao = %s,
                    ativo = %s
                WHERE id = %s
                """,
                (
                    data["tipo_treinamento_id"],
                    data["modelo_segmento"],
                    data["nome_segmento"],
                    data["carga_horaria"],
                    data["carga_teorica"],
                    data["carga_pratica"],
                    data["periodicidade_meses"],
                    data["observacao"],
                    data["ativo"],
                    segmento_id,
                ),
            )
            audit_event(db, "segmento_teorico", segmento_id, "update", anterior=current, novo=data)
            operation = "updated"
        _sync_tipo_periodicidade(db, tipo_treinamento_id=data["tipo_treinamento_id"])
        if current and int(current["tipo_treinamento_id"]) != int(data["tipo_treinamento_id"]):
            _sync_tipo_periodicidade(db, tipo_treinamento_id=int(current["tipo_treinamento_id"]))
        db.commit()
        clear_catalog_options_cache()
        clear_panel_cache()
    except Exception:
        rollback_db(db)
        raise
    return {
        "operation": operation,
        "segmento": fetch_training_master_segment_detail(db, segmento_id=segmento_id),
    }


def delete_training_master_segment(*, segmento_id: int) -> dict:
    db = get_db()
    current = fetch_training_master_segment_detail(db, segmento_id=segmento_id)
    if not current:
        raise TrainingProgramNotFoundError("Segmento teorico nao encontrado.", code="training_program_segment_not_found")
    linked = db.execute(
        "SELECT id FROM treinamentos WHERE segmento_teorico_id = %s LIMIT 1",
        (segmento_id,),
    ).fetchone()
    if linked:
        raise TrainingProgramConflictError(
            "Nao e possivel excluir este segmento porque existem registros vinculados.",
            code="training_program_segment_in_use",
        )
    try:
        audit_event(db, "segmento_teorico", segmento_id, "delete", anterior=current)
        db.execute("DELETE FROM segmentos_teoricos WHERE id = %s", (segmento_id,))
        _sync_tipo_periodicidade(db, tipo_treinamento_id=int(current["tipo_treinamento_id"]))
        db.commit()
        clear_catalog_options_cache()
        clear_panel_cache()
    except Exception:
        rollback_db(db)
        raise
    return {"deleted_id": segmento_id}


def _parse_hour_payload(payload: dict, *, current: dict | None = None) -> dict:
    db = get_db()
    tipo_treinamento_id = get_required_int(payload, "tipo_treinamento_id", "Tipo de treinamento")
    _ensure_tipo_exists(db, tipo_treinamento_id=tipo_treinamento_id, include_inactive=bool(current))
    return {
        "tipo_treinamento_id": tipo_treinamento_id,
        "aeronave_modelo": get_required_text(payload, "aeronave_modelo", "Modelo de aeronave"),
        "solo_horas": _optional_decimal_to_value(payload, "solo_horas", "Solo horas"),
        "voo_pic_sic_horas": _optional_decimal_to_value(payload, "voo_pic_sic_horas", "Voo PIC/SIC horas"),
        "voo_crew_horas": _optional_decimal_to_value(payload, "voo_crew_horas", "Voo CREW horas"),
        "observacao": get_optional_limited_text(payload, "observacao", "Observacao"),
        "ativo": 1 if payload.get("ativo", "1") not in {"0", 0, False, "false"} else 0,
    }


def save_training_master_hour(payload: dict, *, hora_id: int | None = None) -> dict:
    db = get_db()
    current = fetch_training_master_hour_detail(db, hora_id=hora_id) if hora_id else None
    if hora_id and not current:
        raise TrainingProgramNotFoundError("Registro de horas de voo nao encontrado.", code="training_program_hour_not_found")
    data = _parse_hour_payload(payload, current=current)
    try:
        if hora_id is None:
            created = db.execute(
                """
                INSERT INTO horas_voo_aeronave
                (
                    tipo_treinamento_id,
                    aeronave_modelo,
                    solo_horas,
                    voo_pic_sic_horas,
                    voo_crew_horas,
                    observacao,
                    ativo
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    data["tipo_treinamento_id"],
                    data["aeronave_modelo"],
                    data["solo_horas"],
                    data["voo_pic_sic_horas"],
                    data["voo_crew_horas"],
                    data["observacao"],
                    data["ativo"],
                ),
            ).fetchone()
            hora_id = int(created["id"])
            audit_event(db, "horas_voo_aeronave", hora_id, "create", novo=data)
            operation = "created"
        else:
            db.execute(
                """
                UPDATE horas_voo_aeronave
                SET tipo_treinamento_id = %s,
                    aeronave_modelo = %s,
                    solo_horas = %s,
                    voo_pic_sic_horas = %s,
                    voo_crew_horas = %s,
                    observacao = %s,
                    ativo = %s
                WHERE id = %s
                """,
                (
                    data["tipo_treinamento_id"],
                    data["aeronave_modelo"],
                    data["solo_horas"],
                    data["voo_pic_sic_horas"],
                    data["voo_crew_horas"],
                    data["observacao"],
                    data["ativo"],
                    hora_id,
                ),
            )
            audit_event(db, "horas_voo_aeronave", hora_id, "update", anterior=current, novo=data)
            operation = "updated"
        db.commit()
        clear_catalog_options_cache()
        clear_panel_cache()
    except Exception as exc:
        rollback_db(db)
        if psycopg2 is not None and isinstance(exc, psycopg2.IntegrityError):
            raise TrainingProgramConflictError("Conflito ao salvar horas de voo.") from exc
        raise
    return {
        "operation": operation,
        "hora_voo": fetch_training_master_hour_detail(db, hora_id=hora_id),
    }


def delete_training_master_hour(*, hora_id: int) -> dict:
    db = get_db()
    current = fetch_training_master_hour_detail(db, hora_id=hora_id)
    if not current:
        raise TrainingProgramNotFoundError("Registro de horas de voo nao encontrado.", code="training_program_hour_not_found")
    try:
        audit_event(db, "horas_voo_aeronave", hora_id, "delete", anterior=current)
        db.execute("DELETE FROM horas_voo_aeronave WHERE id = %s", (hora_id,))
        db.commit()
        clear_catalog_options_cache()
        clear_panel_cache()
    except Exception:
        rollback_db(db)
        raise
    return {"deleted_id": hora_id}


def build_training_program_template(*, tipo_treinamento_id: int, aeronave_modelo: str | None = None) -> dict:
    from ..repositories.training_program import (
        fetch_training_program_hour_for_type_and_model,
        fetch_training_program_segments_for_type,
    )

    db = get_db()
    tipo = _ensure_tipo_exists(db, tipo_treinamento_id=tipo_treinamento_id)
    aeronave = (aeronave_modelo or "").strip()
    if tipo["exige_equipamento"] and not aeronave:
        raise TrainingProgramValidationError(
            "Selecione o modelo de aeronave para carregar a referencia de horas de voo.",
            code="training_program_missing_aircraft_model",
        )
    segments = fetch_training_program_segments_for_type(db, tipo_treinamento_id=tipo_treinamento_id)
    hours_row = None
    if aeronave:
        hours_row = fetch_training_program_hour_for_type_and_model(
            db,
            tipo_treinamento_id=tipo_treinamento_id,
            aeronave_modelo=aeronave,
        )
        if tipo["exige_equipamento"] and hours_row is None:
            raise TrainingProgramValidationError(
                "Nao ha referencia de horas de voo para o modelo de aeronave selecionado.",
                code="training_program_aircraft_hours_not_found",
            )
    return {
        "tipo": tipo,
        "aeronave_modelo": aeronave,
        "segmentos": segments,
        "horas_voo": hours_row,
        "ctac_required": _hours_require_ctac(hours_row),
    }


def _data_url_to_file_storage(data_url: str | None, *, filename: str | None) -> FileStorage | None:
    raw = str(data_url or "").strip()
    if not raw:
        return None
    encoded = raw.split(",", 1)[1] if "," in raw else raw
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise TrainingProgramAttachmentError("Arquivo PDF invalido.", code="training_program_invalid_pdf") from exc
    return FileStorage(stream=io.BytesIO(content), filename=filename or "anexo.pdf", content_type="application/pdf")


def _create_attachment_for_training(
    db,
    *,
    treinamento_id: int,
    tripulante_id: int,
    tripulante_nome: str | None,
    payload: dict,
    enviado_por: int,
) -> dict | None:
    file_storage = _data_url_to_file_storage(payload.get("arquivo_base64"), filename=payload.get("filename"))
    if file_storage is None:
        return None
    parsed = validate_pdf_upload(file_storage)
    parsed["storage_ref"] = write_training_attachment(
        tripulante_id,
        tripulante_nome,
        treinamento_id,
        parsed["nome_interno"],
        parsed["arquivo_pdf"],
    )
    try:
        created = db.execute(
            """
            INSERT INTO treinamento_anexos_pdf
            (
                treinamento_id,
                nome_original,
                nome_interno,
                mime_type,
                tamanho_bytes,
                storage_ref,
                arquivo_pdf,
                arquivo_hash,
                status,
                enviado_por
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'ativo', %s)
            RETURNING id
            """,
            (
                treinamento_id,
                parsed["nome_original"],
                parsed["nome_interno"],
                parsed["mime_type"],
                parsed["tamanho_bytes"],
                parsed["storage_ref"],
                parsed["arquivo_pdf"],
                parsed["arquivo_hash"],
                enviado_por,
            ),
        ).fetchone()
        audit_event(
            db,
            "treinamento_anexo_pdf",
            int(created["id"]),
            "create",
            novo={"treinamento_id": treinamento_id, "nome_original": parsed["nome_original"]},
        )
        return {"id": int(created["id"]), "storage_ref": parsed["storage_ref"]}
    except Exception:
        delete_media_ref(parsed.get("storage_ref"))
        raise


def _parse_batch_segment_item(payload: dict, *, segment_lookup: dict[int, dict], ctac_required: bool) -> dict:
    segment_id = get_required_int(payload, "segmento_id", "Segmento")
    segment = segment_lookup.get(segment_id)
    if not segment:
        raise TrainingProgramValidationError(
            "Ha um segmento invalido na selecao.",
            code="training_program_segment_not_found",
        )
    data_realizacao = get_optional_date(payload, "data_realizacao", "Data de realizacao")
    if not data_realizacao:
        raise TrainingProgramValidationError(
            f"Informe a data de realizacao para o segmento '{segment['nome_segmento']}'.",
            code="training_program_missing_realization_date",
        )
    data_vencimento = add_months(data_realizacao, int(segment.get("periodicidade_meses") or 0))
    if int(segment.get("periodicidade_meses") or 0) == 0:
        data_vencimento = None
    if not training_dates_are_valid(data_realizacao, data_vencimento):
        raise TrainingProgramValidationError(
            "A data de realizacao nao pode ser posterior a data de vencimento.",
            code="training_program_invalid_dates",
        )
    item = {
        "segmento_id": segment_id,
        "segmento": segment,
        "data_realizacao": data_realizacao,
        "data_vencimento": data_vencimento,
        "observacao": get_optional_limited_text(payload, "observacao", "Observacao"),
        "arquivo_base64": get_optional_text(payload, "arquivo_base64"),
        "filename": get_optional_text(payload, "filename"),
        "ctac_solo_horas": None,
        "ctac_voo_pic_sic_horas": None,
        "ctac_voo_crew_horas": None,
    }
    if ctac_required:
        item["ctac_solo_horas"] = _optional_decimal_to_value(payload, "ctac_solo_horas", "Solo horas CTAC")
        item["ctac_voo_pic_sic_horas"] = _optional_decimal_to_value(payload, "ctac_voo_pic_sic_horas", "Voo PIC/SIC horas CTAC")
        item["ctac_voo_crew_horas"] = _optional_decimal_to_value(payload, "ctac_voo_crew_horas", "Voo CREW horas CTAC")
    return item


def create_tripulante_training_batch(payload: dict, *, criado_por: int) -> dict:
    db = get_db()
    tripulante_id = get_required_int(payload, "tripulante_id", "Tripulante")
    tipo_treinamento_id = get_required_int(payload, "tipo_treinamento_id", "Tipo de treinamento")
    tripulante = _ensure_tripulante_exists(db, tripulante_id=tripulante_id)
    template = build_training_program_template(
        tipo_treinamento_id=tipo_treinamento_id,
        aeronave_modelo=get_optional_text(payload, "aeronave_modelo"),
    )
    segmentos_payload = payload.get("segmentos")
    if not isinstance(segmentos_payload, list) or not segmentos_payload:
        raise TrainingProgramValidationError(
            "Selecione ao menos um segmento para registrar.",
            code="training_program_missing_segments",
        )
    segment_lookup = {int(item["id"]): item for item in template["segmentos"]}
    items = [
        _parse_batch_segment_item(item if isinstance(item, dict) else {}, segment_lookup=segment_lookup, ctac_required=template["ctac_required"])
        for item in segmentos_payload
    ]
    created_ids: list[int] = []
    created_storage_refs: list[str] = []
    try:
        for item in items:
            created = db.execute(
                """
                INSERT INTO treinamentos
                (
                    tripulante_id,
                    equipamento_id,
                    tipo_treinamento_id,
                    segmento_teorico_id,
                    aeronave_modelo,
                    ctac_solo_horas,
                    ctac_voo_pic_sic_horas,
                    ctac_voo_crew_horas,
                    data_realizacao,
                    data_vencimento,
                    observacao
                )
                VALUES (%s, NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    tripulante_id,
                    tipo_treinamento_id,
                    item["segmento_id"],
                    template["aeronave_modelo"] or None,
                    item["ctac_solo_horas"],
                    item["ctac_voo_pic_sic_horas"],
                    item["ctac_voo_crew_horas"],
                    item["data_realizacao"],
                    item["data_vencimento"],
                    item["observacao"],
                ),
            ).fetchone()
            treinamento_id = int(created["id"])
            created_ids.append(treinamento_id)
            attachment = _create_attachment_for_training(
                db,
                treinamento_id=treinamento_id,
                tripulante_id=tripulante_id,
                tripulante_nome=tripulante.get("nome"),
                payload=item,
                enviado_por=criado_por,
            )
            if attachment and attachment.get("storage_ref"):
                created_storage_refs.append(str(attachment["storage_ref"]))
            audit_event(
                db,
                "treinamento",
                treinamento_id,
                "create",
                novo={
                    "tripulante_id": tripulante_id,
                    "tipo_treinamento_id": tipo_treinamento_id,
                    "segmento_teorico_id": item["segmento_id"],
                    "aeronave_modelo": template["aeronave_modelo"],
                    "data_realizacao": item["data_realizacao"],
                    "data_vencimento": item["data_vencimento"],
                },
            )
        db.commit()
        clear_panel_cache()
        records = [fetch_training_program_record_detail(db, treinamento_id=item_id) for item_id in created_ids]
        return {
            "created_ids": created_ids,
            "items": [item for item in records if item],
            "template": template,
        }
    except Exception:
        rollback_db(db)
        for storage_ref in created_storage_refs:
            delete_media_ref(storage_ref)
        raise


def update_tripulante_training_record(payload: dict, *, treinamento_id: int) -> dict:
    db = get_db()
    current = fetch_training_program_record_detail(db, treinamento_id=treinamento_id)
    if not current:
        raise TrainingProgramNotFoundError("Registro de treinamento nao encontrado.", code="training_program_record_not_found")
    tripulante_id = get_required_int(payload, "tripulante_id", "Tripulante")
    tipo_treinamento_id = get_required_int(payload, "tipo_treinamento_id", "Tipo de treinamento")
    segmento_id = get_required_int(payload, "segmento_id", "Segmento")
    tripulante = _ensure_tripulante_exists(db, tripulante_id=tripulante_id)
    template = build_training_program_template(
        tipo_treinamento_id=tipo_treinamento_id,
        aeronave_modelo=get_optional_text(payload, "aeronave_modelo"),
    )
    segment = _ensure_segment_exists(db, segmento_id=segmento_id, tipo_treinamento_id=tipo_treinamento_id, include_inactive=True)
    data_realizacao = get_optional_date(payload, "data_realizacao", "Data de realizacao")
    if not data_realizacao:
        raise TrainingProgramValidationError("Informe a data de realizacao.", code="training_program_missing_realization_date")
    data_vencimento = add_months(data_realizacao, int(segment.get("periodicidade_meses") or 0))
    if int(segment.get("periodicidade_meses") or 0) == 0:
        data_vencimento = None
    if not training_dates_are_valid(data_realizacao, data_vencimento):
        raise TrainingProgramValidationError("Datas invalidas para o treinamento.", code="training_program_invalid_dates")
    try:
        db.execute(
            """
            UPDATE treinamentos
            SET tripulante_id = %s,
                tipo_treinamento_id = %s,
                segmento_teorico_id = %s,
                aeronave_modelo = %s,
                ctac_solo_horas = %s,
                ctac_voo_pic_sic_horas = %s,
                ctac_voo_crew_horas = %s,
                data_realizacao = %s,
                data_vencimento = %s,
                observacao = %s
            WHERE id = %s
            """,
            (
                tripulante_id,
                tipo_treinamento_id,
                segmento_id,
                template["aeronave_modelo"] or None,
                _optional_decimal_to_value(payload, "ctac_solo_horas", "Solo horas CTAC") if template["ctac_required"] else None,
                _optional_decimal_to_value(payload, "ctac_voo_pic_sic_horas", "Voo PIC/SIC horas CTAC") if template["ctac_required"] else None,
                _optional_decimal_to_value(payload, "ctac_voo_crew_horas", "Voo CREW horas CTAC") if template["ctac_required"] else None,
                data_realizacao,
                data_vencimento,
                get_optional_limited_text(payload, "observacao", "Observacao"),
                treinamento_id,
            ),
        )
        audit_event(
            db,
            "treinamento",
            treinamento_id,
            "update",
            anterior=current,
            novo={
                "tripulante_id": tripulante_id,
                "tripulante_nome": tripulante.get("nome"),
                "tipo_treinamento_id": tipo_treinamento_id,
                "segmento_teorico_id": segmento_id,
                "aeronave_modelo": template["aeronave_modelo"],
                "data_realizacao": data_realizacao,
                "data_vencimento": data_vencimento,
            },
        )
        db.commit()
        clear_panel_cache()
    except Exception:
        rollback_db(db)
        raise
    return {"item": fetch_training_program_record_detail(db, treinamento_id=treinamento_id)}


def delete_tripulante_training_record(*, treinamento_id: int) -> dict:
    db = get_db()
    current = fetch_training_program_record_detail(db, treinamento_id=treinamento_id)
    if not current:
        raise TrainingProgramNotFoundError("Registro de treinamento nao encontrado.", code="training_program_record_not_found")
    attachments = fetch_treinamento_attachments(db, treinamento_id=treinamento_id)
    try:
        audit_event(db, "treinamento", treinamento_id, "delete", anterior=current)
        db.execute("DELETE FROM treinamento_anexos_pdf WHERE treinamento_id = %s", (treinamento_id,))
        db.execute("DELETE FROM notificacoes_treinamento WHERE treinamento_id = %s", (treinamento_id,))
        db.execute("DELETE FROM treinamentos WHERE id = %s", (treinamento_id,))
        db.commit()
        clear_panel_cache()
    except Exception:
        rollback_db(db)
        raise
    for attachment in attachments:
        delete_media_ref(attachment.get("storage_ref"))
    return {"deleted_id": treinamento_id}
