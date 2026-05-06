from __future__ import annotations

from datetime import date, datetime

from ..constants import (
    TRAINING_MASTER_STATUS_OPTIONS,
    TRAINING_PERIODICITY_OPTIONS,
    TRAINING_SEGMENT_MODEL_OPTIONS,
)
from ..service_layers.training_completeness import (
    TRAINING_COMPLETENESS_MODE_FIELD,
    resolve_training_structural_mode,
    resolve_training_template_mode,
)
from ..training_aircraft_model import (
    TRAINING_RECORD_ORIGIN_PROGRAM,
    build_training_aircraft_reference_contract,
    build_training_aircraft_snapshot_contract,
)


def _as_iso_date_or_none(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _status_label(is_active) -> str:
    return "Ativo" if bool(is_active) else "Inativo"


def _periodicity_label(value) -> str:
    mapping = {int(item["value"]): item["label"] for item in TRAINING_PERIODICITY_OPTIONS}
    return mapping.get(int(value or 0), "Sem validade")


def serialize_training_program_master_options(*, tipos: list[dict], modelos_aeronave: list[dict]) -> dict:
    return {
        "status": list(TRAINING_MASTER_STATUS_OPTIONS),
        "modelos_segmento": list(TRAINING_SEGMENT_MODEL_OPTIONS),
        "periodicidades": list(TRAINING_PERIODICITY_OPTIONS),
        "exige_aeronave": ["Sim", "Nao"],
        "tipos_treinamento": [serialize_training_master_type_summary(item) for item in tipos],
        "modelos_aeronave": [
            {
                **build_training_aircraft_reference_contract(item.get("aeronave_modelo_referencia") or item.get("aeronave_modelo")),
                "total_registros": int(item.get("total_registros") or 0),
            }
            for item in modelos_aeronave
        ],
    }


def serialize_training_master_type_summary(row: dict) -> dict:
    return {
        "id": int(row["id"]),
        "nome": row.get("nome") or "",
        "codigo": row.get("codigo") or "",
        "descricao": row.get("descricao") or "",
        "periodicidade_meses": int(row.get("periodicidade_meses") or 0),
        "periodicidade_label": _periodicity_label(row.get("periodicidade_meses")),
        "exige_aeronave": bool(row.get("exige_equipamento")),
        "exige_aeronave_label": "Sim" if bool(row.get("exige_equipamento")) else "Nao",
        "ativo": bool(row.get("ativo")),
        "status": _status_label(row.get("ativo")),
        "total_segmentos": int(row.get("total_segmentos") or 0),
        "total_horas_voo": int(row.get("total_horas_voo") or 0),
        "links": {
            "self": f"/api/v1/treinamento-raiz/tipos/{int(row['id'])}",
        },
    }


def serialize_training_master_segment(row: dict) -> dict:
    return {
        "id": int(row["id"]),
        "tipo_treinamento_id": int(row["tipo_treinamento_id"]),
        "tipo_treinamento_nome": row.get("tipo_treinamento_nome") or "",
        "tipo_treinamento_codigo": row.get("tipo_treinamento_codigo") or "",
        "referencia_original_id": row.get("referencia_original_id"),
        "modelo_segmento": row.get("modelo_segmento") or "",
        "nome_segmento": row.get("nome_segmento") or "",
        "carga_horaria": float(row.get("carga_horaria") or 0),
        "carga_teorica": float(row.get("carga_teorica") or 0),
        "carga_pratica": float(row.get("carga_pratica") or 0),
        "periodicidade_meses": int(row.get("periodicidade_meses") or 0),
        "periodicidade_label": _periodicity_label(row.get("periodicidade_meses")),
        "observacao": row.get("observacao") or "",
        "ativo": bool(row.get("ativo")),
        "status": _status_label(row.get("ativo")),
        "links": {
            "self": f"/api/v1/treinamento-raiz/segmentos/{int(row['id'])}",
        },
    }


def serialize_training_master_hour(row: dict) -> dict:
    observacao = row.get("observacao") or ""
    return {
        "id": int(row["id"]),
        "tipo_treinamento_id": int(row["tipo_treinamento_id"]),
        "tipo_treinamento_nome": row.get("tipo_treinamento_nome") or "",
        "tipo_treinamento_codigo": row.get("tipo_treinamento_codigo") or "",
        "referencia_original_id": row.get("referencia_original_id"),
        **build_training_aircraft_reference_contract(row.get("aeronave_modelo_referencia") or row.get("aeronave_modelo")),
        "solo_horas": float(row.get("solo_horas") or 0),
        "voo_pic_sic_horas": float(row.get("voo_pic_sic_horas") or 0),
        "voo_crew_horas": float(row.get("voo_crew_horas") or 0),
        "observacao": observacao,
        "conforme_ctac": "conforme ctac" in observacao.lower(),
        "ativo": bool(row.get("ativo")),
        "status": _status_label(row.get("ativo")),
        "links": {
            "self": f"/api/v1/treinamento-raiz/horas-voo/{int(row['id'])}",
        },
    }


def serialize_training_program_tripulante_options(*, tripulantes: list[dict], tipos: list[dict], modelos_aeronave: list[dict]) -> dict:
    return {
        "tripulantes": [
            {
                "id": int(item["id"]),
                "nome": item.get("nome") or "",
                "matricula": item.get("matricula") or "",
                "label": f"{item.get('nome') or ''} ({item.get('matricula') or '-'})",
            }
            for item in tripulantes
        ],
        "tipos_treinamento": [serialize_training_master_type_summary(item) for item in tipos],
        "modelos_aeronave": [
            {
                **build_training_aircraft_reference_contract(item.get("aeronave_modelo_referencia") or item.get("aeronave_modelo")),
                "total_registros": int(item.get("total_registros") or 0),
            }
            for item in modelos_aeronave
        ],
    }


def serialize_training_program_template(template: dict) -> dict:
    grouped: dict[str, list[dict]] = {}
    for row in template.get("segmentos", []):
        key = row.get("modelo_segmento") or "Outros"
        grouped.setdefault(key, []).append(
            {
                "id": int(row["id"]),
                "tipo_treinamento_id": int(row["tipo_treinamento_id"]),
                "modelo_segmento": row.get("modelo_segmento") or "",
                "nome_segmento": row.get("nome_segmento") or "",
                "carga_horaria": float(row.get("carga_horaria") or 0),
                "carga_teorica": float(row.get("carga_teorica") or 0),
                "carga_pratica": float(row.get("carga_pratica") or 0),
                "periodicidade_meses": int(row.get("periodicidade_meses") or 0),
                "periodicidade_label": _periodicity_label(row.get("periodicidade_meses")),
                "observacao": row.get("observacao") or "",
            }
        )
    horas_voo = template.get("horas_voo")
    return {
        "tipo": serialize_training_master_type_summary(template["tipo"]),
        TRAINING_COMPLETENESS_MODE_FIELD: resolve_training_template_mode(ctac_required=bool(template.get("ctac_required"))),
        **build_training_aircraft_reference_contract(
            template.get("aeronave_modelo_referencia") or template.get("aeronave_modelo")
        ),
        "ctac_required": bool(template.get("ctac_required")),
        "horas_voo": (
            {
                "id": int(horas_voo["id"]),
                **build_training_aircraft_reference_contract(
                    horas_voo.get("aeronave_modelo_referencia") or horas_voo.get("aeronave_modelo")
                ),
                "solo_horas": float(horas_voo.get("solo_horas") or 0),
                "voo_pic_sic_horas": float(horas_voo.get("voo_pic_sic_horas") or 0),
                "voo_crew_horas": float(horas_voo.get("voo_crew_horas") or 0),
                "observacao": horas_voo.get("observacao") or "",
            }
            if horas_voo
            else None
        ),
        "segmentos": [item for rows in grouped.values() for item in rows],
        "segmentos_por_modelo": grouped,
    }


def serialize_training_program_record_summary(row: dict) -> dict:
    return {
        "id": int(row["id"]),
        "origem_registro": TRAINING_RECORD_ORIGIN_PROGRAM,
        TRAINING_COMPLETENESS_MODE_FIELD: resolve_training_structural_mode(row),
        "tripulante_id": int(row["tripulante_id"]),
        "tripulante_nome": row.get("tripulante_nome") or "",
        "tripulante_matricula": row.get("tripulante_matricula") or "",
        "tipo_treinamento_id": int(row["tipo_treinamento_id"]),
        "tipo_treinamento_nome": row.get("tipo_treinamento_nome") or "",
        "tipo_treinamento_codigo": row.get("tipo_treinamento_codigo") or "",
        "segmento_teorico_id": int(row["segmento_teorico_id"]),
        "segmento_nome": row.get("nome_segmento") or "",
        "modelo_segmento": row.get("modelo_segmento") or "",
        **build_training_aircraft_snapshot_contract(row),
        "data_realizacao": _as_iso_date_or_none(row.get("data_realizacao")),
        "data_vencimento": _as_iso_date_or_none(row.get("data_vencimento")),
        "observacao": row.get("observacao") or "",
        "periodicidade_meses": int(row.get("periodicidade_meses") or 0),
        "periodicidade_label": _periodicity_label(row.get("periodicidade_meses")),
        "status_calculado": row.get("status_calculado") or "",
        "ctac_required": bool(row.get("ctac_required")),
        "ctac_solo_horas": float(row.get("ctac_solo_horas") or 0) if row.get("ctac_solo_horas") is not None else None,
        "ctac_voo_pic_sic_horas": float(row.get("ctac_voo_pic_sic_horas") or 0) if row.get("ctac_voo_pic_sic_horas") is not None else None,
        "ctac_voo_crew_horas": float(row.get("ctac_voo_crew_horas") or 0) if row.get("ctac_voo_crew_horas") is not None else None,
        "total_anexos": int(row.get("total_anexos") or 0),
        "links": {
            "self": f"/api/v1/treinamentos-tripulantes/{int(row['id'])}",
            "attachments": f"/api/v1/treinamentos-tripulantes/{int(row['id'])}/attachments",
        },
    }


def serialize_training_program_record_detail(row: dict, *, attachments: list[dict] | None = None) -> dict:
    payload = serialize_training_program_record_summary(row)
    payload.update(
        {
            "carga_horaria": float(row.get("carga_horaria") or 0) if row.get("carga_horaria") is not None else 0,
            "carga_teorica": float(row.get("carga_teorica") or 0) if row.get("carga_teorica") is not None else 0,
            "carga_pratica": float(row.get("carga_pratica") or 0) if row.get("carga_pratica") is not None else 0,
            "solo_horas_referencia": float(row.get("solo_horas_referencia") or 0) if row.get("solo_horas_referencia") is not None else 0,
            "voo_pic_sic_horas_referencia": float(row.get("voo_pic_sic_horas_referencia") or 0) if row.get("voo_pic_sic_horas_referencia") is not None else 0,
            "voo_crew_horas_referencia": float(row.get("voo_crew_horas_referencia") or 0) if row.get("voo_crew_horas_referencia") is not None else 0,
            "horas_voo_observacao": row.get("horas_voo_observacao") or "",
        }
    )
    if attachments is not None:
        payload["attachments"] = attachments
    return payload
