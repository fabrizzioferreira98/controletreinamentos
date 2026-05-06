from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras


TRIPULANTES_TABLE_QUERIES = {
    "bases": """
        SELECT
            id,
            nome,
            uf,
            latitude,
            longitude,
            ativa
        FROM bases
        ORDER BY nome, id
    """,
    "tripulantes": """
        SELECT
            id,
            nome,
            cpf,
            licenca_anac,
            email,
            telefone,
            base,
            status,
            ativo,
            funcao_operacional,
            categoria_operacional,
            sdea_ativo,
            instrutor_ativo,
            checador_ativo,
            elegivel_adicional_excepcional,
            observacoes,
            foto_base64,
            foto_storage_ref,
            foto_mime_type,
            possui_foto
        FROM tripulantes
        ORDER BY nome, id
    """,
    "pilotos": """
        SELECT
            id,
            nome,
            matricula,
            tripulante_id,
            base_id,
            status,
            criado_em
        FROM pilotos
        WHERE tripulante_id IS NOT NULL
        ORDER BY nome, id
    """,
}


def _load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def _sanitize_database_target(database_url: str) -> dict[str, Any]:
    parsed = urlparse(database_url)
    return {
        "host": parsed.hostname,
        "port": parsed.port,
        "database": (parsed.path or "").lstrip("/"),
        "user": parsed.username,
    }


def _json_default(value: Any):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Tipo não serializável: {type(value)!r}")


def _connect(database_url: str):
    return psycopg2.connect(
        database_url,
        connect_timeout=10,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def _fetch_rows(conn, query: str) -> list[dict]:
    with conn.cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()
    return [dict(row) for row in rows]


def _snapshot_tripulantes_domain(conn, *, database_url: str) -> dict[str, Any]:
    tables = {name: _fetch_rows(conn, query) for name, query in TRIPULANTES_TABLE_QUERIES.items()}
    return {
        "captured_at": datetime.utcnow().isoformat() + "Z",
        "source": _sanitize_database_target(database_url),
        "counts": {name: len(rows) for name, rows in tables.items()},
        "tables": tables,
    }


def _write_snapshot(snapshot: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )


def _upsert_base(conn, row: dict) -> int:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO bases (nome, uf, latitude, longitude, ativa)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (nome)
            DO UPDATE SET
                uf = EXCLUDED.uf,
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude,
                ativa = EXCLUDED.ativa
            RETURNING id
            """,
            (
                row["nome"],
                row["uf"],
                row["latitude"],
                row["longitude"],
                bool(row["ativa"]),
            ),
        )
        created = cursor.fetchone()
    return int(created["id"])


def _upsert_tripulante(conn, row: dict) -> int:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO tripulantes (
                nome,
                cpf,
                licenca_anac,
                email,
                telefone,
                base,
                status,
                ativo,
                funcao_operacional,
                categoria_operacional,
                sdea_ativo,
                instrutor_ativo,
                checador_ativo,
                elegivel_adicional_excepcional,
                observacoes,
                foto_base64,
                foto_storage_ref,
                foto_mime_type,
                possui_foto
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (cpf)
            DO UPDATE SET
                nome = EXCLUDED.nome,
                licenca_anac = EXCLUDED.licenca_anac,
                email = EXCLUDED.email,
                telefone = EXCLUDED.telefone,
                base = EXCLUDED.base,
                status = EXCLUDED.status,
                ativo = EXCLUDED.ativo,
                funcao_operacional = EXCLUDED.funcao_operacional,
                categoria_operacional = EXCLUDED.categoria_operacional,
                sdea_ativo = EXCLUDED.sdea_ativo,
                instrutor_ativo = EXCLUDED.instrutor_ativo,
                checador_ativo = EXCLUDED.checador_ativo,
                elegivel_adicional_excepcional = EXCLUDED.elegivel_adicional_excepcional,
                observacoes = EXCLUDED.observacoes,
                foto_base64 = EXCLUDED.foto_base64,
                foto_storage_ref = EXCLUDED.foto_storage_ref,
                foto_mime_type = EXCLUDED.foto_mime_type,
                possui_foto = EXCLUDED.possui_foto
            RETURNING id
            """,
            (
                row["nome"],
                row["cpf"],
                row["licenca_anac"],
                row.get("email"),
                row.get("telefone"),
                row["base"],
                row["status"],
                int(row.get("ativo") or 0),
                row.get("funcao_operacional") or "outro",
                row.get("categoria_operacional") or "N/A",
                int(row.get("sdea_ativo") or 0),
                int(row.get("instrutor_ativo") or 0),
                int(row.get("checador_ativo") or 0),
                int(row.get("elegivel_adicional_excepcional") or 0),
                row.get("observacoes"),
                row.get("foto_base64"),
                row.get("foto_storage_ref"),
                row.get("foto_mime_type"),
                bool(row.get("possui_foto")),
            ),
        )
        created = cursor.fetchone()
    return int(created["id"])


def _upsert_piloto(conn, row: dict, *, target_tripulante_id: int, target_base_id: int) -> int:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO pilotos (
                nome,
                matricula,
                tripulante_id,
                base_id,
                status,
                criado_em
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (matricula)
            DO UPDATE SET
                nome = EXCLUDED.nome,
                tripulante_id = EXCLUDED.tripulante_id,
                base_id = EXCLUDED.base_id,
                status = EXCLUDED.status,
                criado_em = EXCLUDED.criado_em
            RETURNING id
            """,
            (
                row["nome"],
                row["matricula"],
                target_tripulante_id,
                target_base_id,
                row["status"],
                row["criado_em"],
            ),
        )
        created = cursor.fetchone()
    return int(created["id"])


def _restore_tripulantes_domain(conn, snapshot: dict[str, Any]) -> dict[str, int]:
    base_id_map: dict[int, int] = {}
    tripulante_id_map: dict[int, int] = {}
    restored = {"bases": 0, "tripulantes": 0, "pilotos": 0}

    for row in snapshot["tables"]["bases"]:
        base_id_map[int(row["id"])] = _upsert_base(conn, row)
        restored["bases"] += 1

    for row in snapshot["tables"]["tripulantes"]:
        tripulante_id_map[int(row["id"])] = _upsert_tripulante(conn, row)
        restored["tripulantes"] += 1

    for row in snapshot["tables"]["pilotos"]:
        source_tripulante_id = int(row["tripulante_id"])
        source_base_id = int(row["base_id"])
        target_tripulante_id = tripulante_id_map.get(source_tripulante_id)
        target_base_id = base_id_map.get(source_base_id)
        if target_tripulante_id is None or target_base_id is None:
            continue
        _upsert_piloto(
            conn,
            row,
            target_tripulante_id=target_tripulante_id,
            target_base_id=target_base_id,
        )
        restored["pilotos"] += 1

    return restored


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gera snapshot do domínio de tripulantes e sincroniza produção -> homologação sem compartilhar banco.",
    )
    parser.add_argument("--source-env-file", required=True, help="Arquivo .env do ambiente de origem.")
    parser.add_argument("--target-env-file", required=True, help="Arquivo .env do ambiente de destino.")
    parser.add_argument(
        "--snapshot-dir",
        default=str(Path("ops") / "backups" / "tripulantes_sync"),
        help="Diretório para salvar snapshots de origem e backup do destino.",
    )
    parser.add_argument("--apply", action="store_true", help="Aplica a sincronização no banco de destino.")
    args = parser.parse_args(argv)

    source_env = _load_env_file(Path(args.source_env_file))
    target_env = _load_env_file(Path(args.target_env_file))
    source_url = (source_env.get("DATABASE_URL") or "").strip()
    target_url = (target_env.get("DATABASE_URL") or "").strip()
    if not source_url:
        raise SystemExit("DATABASE_URL ausente no arquivo de origem.")
    if not target_url:
        raise SystemExit("DATABASE_URL ausente no arquivo de destino.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_dir = Path(args.snapshot_dir)
    source_snapshot_path = snapshot_dir / f"tripulantes_snapshot_source_{timestamp}.json"
    target_snapshot_path = snapshot_dir / f"tripulantes_snapshot_target_backup_{timestamp}.json"

    source_conn = _connect(source_url)
    target_conn = _connect(target_url)

    try:
        source_snapshot = _snapshot_tripulantes_domain(source_conn, database_url=source_url)
        target_snapshot = _snapshot_tripulantes_domain(target_conn, database_url=target_url)
        _write_snapshot(source_snapshot, source_snapshot_path)
        _write_snapshot(target_snapshot, target_snapshot_path)

        restored_counts = None
        if args.apply:
            try:
                restored_counts = _restore_tripulantes_domain(target_conn, source_snapshot)
                target_conn.commit()
            except Exception:
                target_conn.rollback()
                raise

        print(
            json.dumps(
                {
                    "ok": True,
                    "applied": bool(args.apply),
                    "source": source_snapshot["source"],
                    "target": target_snapshot["source"],
                    "source_counts": source_snapshot["counts"],
                    "target_backup_counts": target_snapshot["counts"],
                    "restored_counts": restored_counts,
                    "artifacts": {
                        "source_snapshot": str(source_snapshot_path.resolve()),
                        "target_backup_snapshot": str(target_snapshot_path.resolve()),
                    },
                },
                ensure_ascii=False,
                indent=2,
                default=_json_default,
            )
        )
        return 0
    finally:
        source_conn.close()
        target_conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
