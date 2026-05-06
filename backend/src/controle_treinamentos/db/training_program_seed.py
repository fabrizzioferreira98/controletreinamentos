from __future__ import annotations

import csv
from pathlib import Path

HISTORICAL_TRAINING_PROGRAM_SEED_FROZEN = True
HISTORICAL_TRAINING_PROGRAM_SEED_ACK = "seed-training-program-reference-historico"
HISTORICAL_TRAINING_PROGRAM_SEED_CLASSIFICATION = {
    "group": "seed_import_historico",
    "default_path": False,
    "frozen": HISTORICAL_TRAINING_PROGRAM_SEED_FROZEN,
    "required_ack": HISTORICAL_TRAINING_PROGRAM_SEED_ACK,
}


def training_program_seed_root() -> Path:
    return Path(__file__).resolve().parent.parent / "bootstrap_data" / "training_program"


def _read_semicolon_csv(file_name: str) -> list[dict[str, str]]:
    path = training_program_seed_root() / file_name
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        return [{key: (value or "").strip() for key, value in row.items()} for row in reader]


def load_training_program_reference() -> dict[str, list[dict[str, str]]]:
    return {
        "tipos": [
            row
            for row in _read_semicolon_csv("01_tipos_treinamento.csv")
            if (row.get("id") or "").isdigit() and (row.get("nome") or "")
        ],
        "segmentos": [
            row
            for row in _read_semicolon_csv("02_segmentos_teoricos.csv")
            if (row.get("id") or "").isdigit() and (row.get("tipo_treinamento_id") or "").isdigit()
        ],
        "horas_voo": [
            row
            for row in _read_semicolon_csv("03_horas_voo_aeronave.csv")
            if (row.get("id") or "").isdigit() and (row.get("tipo_treinamento_id") or "").isdigit()
        ],
    }


def _safe_int(value: str, *, default: int = 0) -> int:
    try:
        return int(str(value or "").strip())
    except (TypeError, ValueError):
        return int(default)


def _safe_float(value: str, *, default: float = 0.0) -> float:
    try:
        return float(str(value or "").strip().replace(",", "."))
    except (TypeError, ValueError):
        return float(default)


def _infer_type_periodicity(segmentos: list[dict[str, str]], tipo_referencia_id: int) -> int:
    values = [
        _safe_int(row.get("periodicidade_meses"), default=0)
        for row in segmentos
        if _safe_int(row.get("tipo_treinamento_id")) == int(tipo_referencia_id)
    ]
    positive = [value for value in values if value > 0]
    return max(positive) if positive else 0


def _infer_requires_aircraft(horas_voo: list[dict[str, str]], tipo_referencia_id: int) -> int:
    return 1 if any(_safe_int(row.get("tipo_treinamento_id")) == int(tipo_referencia_id) for row in horas_voo) else 0


def seed_training_program_reference(db, *, historical_seed_ack: str = "") -> dict[str, int]:
    if historical_seed_ack != HISTORICAL_TRAINING_PROGRAM_SEED_ACK:
        raise RuntimeError(
            "Seed historico de programa esta congelado e fora da trilha principal. "
            "Use o ack explicito apenas em importacao/reconciliacao historica controlada."
        )

    reference = load_training_program_reference()
    tipos = reference["tipos"]
    segmentos = reference["segmentos"]
    horas_voo = reference["horas_voo"]

    type_id_map: dict[int, int] = {}
    inserted = {"tipos": 0, "segmentos": 0, "horas_voo": 0}

    for row in tipos:
        referencia_id = _safe_int(row.get("id"))
        nome = row.get("nome") or ""
        codigo = row.get("codigo") or ""
        ativo = 1 if (row.get("status") or "").strip().lower() == "ativo" else 0
        periodicidade = _infer_type_periodicity(segmentos, referencia_id)
        exige_equipamento = _infer_requires_aircraft(horas_voo, referencia_id)

        existing = None
        if codigo:
            existing = db.execute(
                "SELECT id FROM tipos_treinamento WHERE codigo = %s",
                (codigo,),
            ).fetchone()
        if not existing:
            existing = db.execute(
                "SELECT id FROM tipos_treinamento WHERE LOWER(nome) = LOWER(%s) LIMIT 1",
                (nome,),
            ).fetchone()

        if existing:
            db.execute(
                """
                UPDATE tipos_treinamento
                SET nome = %s,
                    codigo = %s,
                    descricao = COALESCE(descricao, ''),
                    periodicidade_meses = %s,
                    exige_equipamento = %s,
                    ativo = %s
                WHERE id = %s
                """,
                (
                    nome,
                    codigo,
                    periodicidade,
                    exige_equipamento,
                    ativo,
                    existing["id"],
                ),
            )
            type_id_map[referencia_id] = int(existing["id"])
            continue

        created = db.execute(
            """
            INSERT INTO tipos_treinamento
            (nome, codigo, descricao, periodicidade_meses, exige_equipamento, ativo)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                nome,
                codigo,
                "",
                periodicidade,
                exige_equipamento,
                ativo,
            ),
        ).fetchone()
        type_id_map[referencia_id] = int(created["id"])
        inserted["tipos"] += 1

    for row in segmentos:
        referencia_id = _safe_int(row.get("id"))
        tipo_referencia_id = _safe_int(row.get("tipo_treinamento_id"))
        tipo_treinamento_id = type_id_map.get(tipo_referencia_id)
        if not tipo_treinamento_id:
            continue

        existing = db.execute(
            "SELECT id FROM segmentos_teoricos WHERE referencia_original_id = %s",
            (referencia_id,),
        ).fetchone()

        params = (
            tipo_treinamento_id,
            referencia_id,
            row.get("modelo_segmento") or "",
            row.get("nome_segmento") or "",
            _safe_float(row.get("carga_horaria")),
            _safe_float(row.get("carga_teorica")),
            _safe_float(row.get("carga_pratica")),
            _safe_int(row.get("periodicidade_meses")),
            row.get("observacao") or "",
            1,
        )
        if existing:
            db.execute(
                """
                UPDATE segmentos_teoricos
                SET tipo_treinamento_id = %s,
                    referencia_original_id = %s,
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
                (*params, existing["id"]),
            )
            continue

        db.execute(
            """
            INSERT INTO segmentos_teoricos
            (
                tipo_treinamento_id,
                referencia_original_id,
                modelo_segmento,
                nome_segmento,
                carga_horaria,
                carga_teorica,
                carga_pratica,
                periodicidade_meses,
                observacao,
                ativo
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            params,
        )
        inserted["segmentos"] += 1

    for row in horas_voo:
        referencia_id = _safe_int(row.get("id"))
        tipo_referencia_id = _safe_int(row.get("tipo_treinamento_id"))
        tipo_treinamento_id = type_id_map.get(tipo_referencia_id)
        if not tipo_treinamento_id:
            continue

        existing = db.execute(
            "SELECT id FROM horas_voo_aeronave WHERE referencia_original_id = %s",
            (referencia_id,),
        ).fetchone()

        params = (
            tipo_treinamento_id,
            referencia_id,
            row.get("aeronave_modelo") or "",
            _safe_float(row.get("solo_horas")),
            _safe_float(row.get("voo_pic_sic_horas")),
            _safe_float(row.get("voo_crew_horas")),
            row.get("observacao") or "",
            1,
        )
        if existing:
            db.execute(
                """
                UPDATE horas_voo_aeronave
                SET tipo_treinamento_id = %s,
                    referencia_original_id = %s,
                    aeronave_modelo = %s,
                    solo_horas = %s,
                    voo_pic_sic_horas = %s,
                    voo_crew_horas = %s,
                    observacao = %s,
                    ativo = %s
                WHERE id = %s
                """,
                (*params, existing["id"]),
            )
            continue

        db.execute(
            """
            INSERT INTO horas_voo_aeronave
            (
                tipo_treinamento_id,
                referencia_original_id,
                aeronave_modelo,
                solo_horas,
                voo_pic_sic_horas,
                voo_crew_horas,
                observacao,
                ativo
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            params,
        )
        inserted["horas_voo"] += 1

    return inserted
