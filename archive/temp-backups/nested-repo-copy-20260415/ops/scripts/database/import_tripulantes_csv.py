from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


import argparse
import csv
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.db import get_db


PLACEHOLDER_VALUES = {"", "-", "***", "****", "*****", "N/A", "n/a"}
FIXED_COLUMNS = 10


@dataclass(frozen=True)
class TrainingColumn:
    index: int
    raw_title: str
    tipo_nome: str
    equipamento_nome: str | None
    periodicidade_meses: int


def normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\n", " ")).strip()


def is_placeholder(value: str | None) -> bool:
    return normalize_text(value) in PLACEHOLDER_VALUES


def parse_date(value: str | None) -> str | None:
    raw = normalize_text(value)
    if not raw or raw in PLACEHOLDER_VALUES:
        return None

    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def infer_equipment_name(title: str, current_equipment: str | None) -> str | None:
    upper = title.upper()
    known_names = (
        "KING 200",
        "CITATION JET - 525",
        "CITATION V - 560",
        "WESTWIND - WW24 (AI24)",
        "LEARJET - LR 20 / 30",
        "ASTRA G100 - AI25",
        "LEAR 45",
    )
    for item in known_names:
        if item in upper:
            return item.title().replace("Ai24", "AI24").replace("Ai25", "AI25").replace("Lr", "LR")
    if "SIMULADOR" in upper:
        return current_equipment
    return current_equipment


def infer_periodicity_months(title: str) -> int:
    match = re.search(r"(\d+)\s*M\b", title, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return 12


def normalize_type_name(title: str, equipment_name: str | None) -> str:
    collapsed = normalize_text(title)
    if collapsed.upper().startswith("SIMULADOR") and equipment_name:
        return f"{equipment_name} - {collapsed}"
    return collapsed


def parse_training_columns(header: list[str]) -> list[TrainingColumn]:
    columns: list[TrainingColumn] = []
    current_equipment = None
    for idx, raw_title in enumerate(header[FIXED_COLUMNS:], start=FIXED_COLUMNS):
        title = normalize_text(raw_title)
        if not title or title.upper() == "TRIPULANTE":
            continue
        current_equipment = infer_equipment_name(title, current_equipment)
        tipo_nome = normalize_type_name(title, current_equipment)
        columns.append(
            TrainingColumn(
                index=idx,
                raw_title=title,
                tipo_nome=tipo_nome,
                equipamento_nome=current_equipment,
                periodicidade_meses=infer_periodicity_months(title),
            )
        )
    return columns


def build_tripulante_observacoes(row: dict[str, str]) -> str:
    parts = []
    for label in ("ICAO", "LIC. ANAC", "CMA", "TSA"):
        value = normalize_text(row.get(label, ""))
        if value and value not in PLACEHOLDER_VALUES:
            parts.append(f"{label}: {value}")
    return " | ".join(parts)


def upsert_tripulante(db, row: dict[str, str], default_status: str) -> int:
    cpf = normalize_text(row["CPF"])
    nome = normalize_text(row["TRIPULANTE"])
    licenca_anac = normalize_text(row["COD. ANAC"])
    base = normalize_text(row["BASE"])
    observacoes = build_tripulante_observacoes(row)

    if not base or base in PLACEHOLDER_VALUES:
        base = "Nao informado"
    if not licenca_anac or licenca_anac in PLACEHOLDER_VALUES:
        licenca_anac = normalize_text(row.get("LIC. ANAC")) or "Nao informado"

    existing = db.execute("SELECT id FROM tripulantes WHERE cpf = %s", (cpf,)).fetchone()
    if existing:
        db.execute(
            """
            UPDATE tripulantes
            SET nome = %s, licenca_anac = %s, base = %s, status = %s, observacoes = %s
            WHERE id = %s
            """,
            (nome, licenca_anac, base, default_status, observacoes, existing["id"]),
        )
        return existing["id"]

    created = db.execute(
        """
        INSERT INTO tripulantes (nome, cpf, licenca_anac, base, status, observacoes)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (nome, cpf, licenca_anac, base, default_status, observacoes),
    ).fetchone()
    return created["id"]


def ensure_equipamento(db, equipment_name: str | None) -> int | None:
    if not equipment_name:
        return None
    existing = db.execute("SELECT id FROM equipamentos WHERE nome = %s", (equipment_name,)).fetchone()
    if existing:
        return existing["id"]

    created = db.execute(
        "INSERT INTO equipamentos (nome, tipo, ativo) VALUES (%s, %s, 1) RETURNING id",
        (equipment_name, "Aeronave"),
    ).fetchone()
    return created["id"]


def ensure_tipo_treinamento(db, column: TrainingColumn) -> int:
    existing = db.execute("SELECT id FROM tipos_treinamento WHERE nome = %s", (column.tipo_nome,)).fetchone()
    if existing:
        db.execute(
            "UPDATE tipos_treinamento SET periodicidade_meses = %s, ativo = 1 WHERE id = %s",
            (column.periodicidade_meses, existing["id"]),
        )
        return existing["id"]

    created = db.execute(
        """
        INSERT INTO tipos_treinamento (nome, periodicidade_meses, ativo)
        VALUES (%s, %s, 1)
        RETURNING id
        """,
        (column.tipo_nome, column.periodicidade_meses),
    ).fetchone()
    return created["id"]


def upsert_treinamento(db, tripulante_id: int, equipamento_id: int | None, tipo_id: int, data_vencimento: str, source_label: str) -> None:
    observacao = f"Importado de planilha: {source_label}"
    existing = db.execute(
        """
        SELECT id
        FROM treinamentos
        WHERE tripulante_id = %s
          AND tipo_treinamento_id = %s
          AND (
            (equipamento_id IS NULL AND %s IS NULL)
            OR equipamento_id = %s
          )
        ORDER BY id DESC
        LIMIT 1
        """,
        (tripulante_id, tipo_id, equipamento_id, equipamento_id),
    ).fetchone()

    if existing:
        db.execute(
            """
            UPDATE treinamentos
            SET data_vencimento = %s, observacao = %s
            WHERE id = %s
            """,
            (data_vencimento, observacao, existing["id"]),
        )
        return

    db.execute(
        """
        INSERT INTO treinamentos
        (tripulante_id, equipamento_id, tipo_treinamento_id, data_realizacao, data_vencimento, observacao)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (tripulante_id, equipamento_id, tipo_id, None, data_vencimento, observacao),
    )


def import_csv(csv_path: Path, default_status: str, source_label: str, dry_run: bool) -> dict[str, int]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))

    if not rows:
        raise ValueError("CSV vazio.")

    header = rows[0]
    columns = parse_training_columns(header)
    data_rows = [row for row in rows[1:] if row and normalize_text(row[0]).upper() != "ID"]

    app = create_app()
    summary = {
        "tripulantes": 0,
        "equipamentos": 0,
        "tipos": 0,
        "treinamentos": 0,
        "linhas_lidas": len(data_rows),
    }

    with app.app_context():
        db = get_db()
        known_equipments: dict[str, int | None] = {}
        known_types: dict[str, int] = {}

        for raw_row in data_rows:
            padded_row = raw_row + [""] * (len(header) - len(raw_row))
            row_map = {header[idx]: padded_row[idx] for idx in range(len(header))}

            if is_placeholder(row_map.get("CPF")) or is_placeholder(row_map.get("TRIPULANTE")):
                continue

            tripulante_id = upsert_tripulante(db, row_map, default_status)
            summary["tripulantes"] += 1

            for column in columns:
                date_value = parse_date(padded_row[column.index])
                if not date_value:
                    continue

                if column.equipamento_nome not in known_equipments:
                    known_equipments[column.equipamento_nome or ""] = ensure_equipamento(db, column.equipamento_nome)
                    if column.equipamento_nome:
                        summary["equipamentos"] += 1
                if column.tipo_nome not in known_types:
                    known_types[column.tipo_nome] = ensure_tipo_treinamento(db, column)
                    summary["tipos"] += 1

                equipamento_id = known_equipments[column.equipamento_nome or ""]
                tipo_id = known_types[column.tipo_nome]
                upsert_treinamento(db, tripulante_id, equipamento_id, tipo_id, date_value, source_label)
                summary["treinamentos"] += 1

        if dry_run:
            db.conn.rollback()
        else:
            db.commit()

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Importa a planilha matricial de treinamentos para o banco do sistema.")
    parser.add_argument("csv_path", help="Caminho do arquivo CSV exportado da planilha")
    parser.add_argument("--default-status", default="Ativo", help="Status padrão aplicado aos tripulantes importados")
    parser.add_argument("--source-label", default="controle_tn_tripulantes_csv", help="Rótulo salvo em observacao dos treinamentos")
    parser.add_argument("--dry-run", action="store_true", help="Processa e valida sem efetivar alterações no banco")
    args = parser.parse_args()

    summary = import_csv(Path(args.csv_path), args.default_status, args.source_label, args.dry_run)
    mode = "DRY RUN" if args.dry_run else "IMPORTACAO"
    print(mode)
    print(f"Linhas lidas: {summary['linhas_lidas']}")
    print(f"Tripulantes processados: {summary['tripulantes']}")
    print(f"Equipamentos referenciados: {summary['equipamentos']}")
    print(f"Tipos de treinamento referenciados: {summary['tipos']}")
    print(f"Treinamentos processados: {summary['treinamentos']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
