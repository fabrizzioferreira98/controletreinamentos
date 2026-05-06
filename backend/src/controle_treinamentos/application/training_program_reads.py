from __future__ import annotations

from typing import Any, Literal

from ..db import get_db
from ..infra.document_blobs import annotate_document_blob_state
from ..repositories.training_program import (
    fetch_training_master_hour_detail,
    fetch_training_master_hours,
    fetch_training_master_segment_detail,
    fetch_training_master_segments,
    fetch_training_master_type_detail,
    fetch_training_master_types,
    fetch_training_program_active_types,
    fetch_training_program_aircraft_models,
    fetch_training_program_record_detail,
    fetch_training_program_record_list,
    fetch_training_program_tripulantes,
)
from ..repositories.treinamentos import fetch_treinamento_attachments

TrainingMasterEntity = Literal["types", "segments", "hours"]


def get_training_master_options_read_model() -> dict[str, Any]:
    db = get_db()
    return {
        "tipos": fetch_training_master_types(db),
        "modelos_aeronave": fetch_training_program_aircraft_models(db),
    }


def list_training_master_entities_read_model(
    *,
    entity: TrainingMasterEntity,
    tipo_treinamento_id: int | None = None,
) -> list[dict]:
    db = get_db()
    if entity == "types":
        return fetch_training_master_types(db)
    if entity == "segments":
        return fetch_training_master_segments(db, tipo_treinamento_id=tipo_treinamento_id)
    return fetch_training_master_hours(db, tipo_treinamento_id=tipo_treinamento_id)


def get_training_master_entity_detail_read_model(
    *,
    entity: TrainingMasterEntity,
    entity_id: int,
) -> dict | None:
    db = get_db()
    if entity == "types":
        return fetch_training_master_type_detail(db, tipo_treinamento_id=entity_id)
    if entity == "segments":
        return fetch_training_master_segment_detail(db, segmento_id=entity_id)
    return fetch_training_master_hour_detail(db, hora_id=entity_id)


def get_tripulante_program_options_read_model(*, base: str | None) -> dict[str, Any]:
    db = get_db()
    return {
        "tripulantes": fetch_training_program_tripulantes(db, base=base),
        "tipos": fetch_training_program_active_types(db),
        "modelos_aeronave": fetch_training_program_aircraft_models(db),
    }


def list_tripulante_program_records_read_model(
    *,
    tripulante_id: int | None,
    tipo_treinamento_id: int | None,
    aeronave_modelo_snapshot: str | None,
    base: str | None,
) -> list[dict]:
    db = get_db()
    return fetch_training_program_record_list(
        db,
        tripulante_id=tripulante_id,
        tipo_treinamento_id=tipo_treinamento_id,
        aeronave_modelo_snapshot=aeronave_modelo_snapshot,
        base=base,
    )


def get_tripulante_program_record_detail_read_model(*, treinamento_id: int) -> dict[str, Any]:
    db = get_db()
    row = fetch_training_program_record_detail(db, treinamento_id=treinamento_id)
    if not row:
        return {"item": None, "attachments": []}
    attachments = [
        annotate_document_blob_state(item)
        for item in fetch_treinamento_attachments(db, treinamento_id=treinamento_id)
    ]
    return {"item": row, "attachments": attachments}
