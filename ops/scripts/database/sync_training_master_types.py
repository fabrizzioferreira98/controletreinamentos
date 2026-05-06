from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import psycopg2


def _load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def _database_url(env_path: Path) -> str:
    env = _load_env_file(env_path)
    value = (env.get("DATABASE_URL") or "").strip()
    if not value:
        raise RuntimeError(f"DATABASE_URL ausente em {env_path}")
    return value


def _fetch_types(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, nome, codigo, descricao, periodicidade_meses, exige_equipamento, ativo
            FROM tipos_treinamento
            ORDER BY id
            """
        )
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def _semantic_key(row: dict) -> tuple[str, str]:
    codigo = (row.get("codigo") or "").strip().lower()
    nome = (row.get("nome") or "").strip().lower()
    if codigo:
        return ("codigo", codigo)
    return ("nome", nome)


def _find_target_id(cur, row: dict) -> int | None:
    codigo = (row.get("codigo") or "").strip()
    nome = (row.get("nome") or "").strip()
    if codigo:
        cur.execute("SELECT id FROM tipos_treinamento WHERE LOWER(COALESCE(codigo, '')) = LOWER(%s) LIMIT 1", (codigo,))
        existing = cur.fetchone()
        if existing:
            return int(existing[0])
    cur.execute("SELECT id FROM tipos_treinamento WHERE LOWER(nome) = LOWER(%s) LIMIT 1", (nome,))
    existing = cur.fetchone()
    return int(existing[0]) if existing else None


def _sync_types(source_env: Path, target_env: Path, *, apply_changes: bool) -> dict:
    source_url = _database_url(source_env)
    target_url = _database_url(target_env)

    with psycopg2.connect(source_url) as source_conn, psycopg2.connect(target_url) as target_conn:
        source_rows = _fetch_types(source_conn)
        target_rows = _fetch_types(target_conn)
        source_keys = {_semantic_key(row) for row in source_rows}
        target_keys = {_semantic_key(row) for row in target_rows}
        missing_keys = sorted(source_keys - target_keys)
        matched_keys = sorted(source_keys & target_keys)

        actions: list[dict] = []
        if apply_changes:
            with target_conn.cursor() as cur:
                for row in source_rows:
                    target_id = _find_target_id(cur, row)
                    payload = (
                        row.get("nome"),
                        row.get("codigo"),
                        row.get("descricao"),
                        row.get("periodicidade_meses"),
                        row.get("exige_equipamento"),
                        row.get("ativo"),
                    )
                    if target_id is None:
                        cur.execute(
                            """
                            INSERT INTO tipos_treinamento
                                (nome, codigo, descricao, periodicidade_meses, exige_equipamento, ativo)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            RETURNING id
                            """,
                            payload,
                        )
                        created_id = int(cur.fetchone()[0])
                        actions.append({"action": "insert", "id": created_id, "key": _semantic_key(row), "nome": row.get("nome")})
                    else:
                        cur.execute(
                            """
                            UPDATE tipos_treinamento
                            SET nome = %s,
                                codigo = %s,
                                descricao = %s,
                                periodicidade_meses = %s,
                                exige_equipamento = %s,
                                ativo = %s
                            WHERE id = %s
                            """,
                            (*payload, target_id),
                        )
                        actions.append({"action": "update", "id": target_id, "key": _semantic_key(row), "nome": row.get("nome")})
            target_conn.commit()
            target_rows = _fetch_types(target_conn)

    return {
        "source_env": str(source_env),
        "target_env": str(target_env),
        "source_total": len(source_rows),
        "target_total_before": len(target_keys),
        "target_total_after": len(target_rows),
        "missing_keys": missing_keys,
        "matched_keys": matched_keys,
        "actions": actions,
        "applied": bool(apply_changes),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Sincroniza tipos_treinamento entre ambientes por chave semantica.")
    parser.add_argument("--source-env", default=r"C:\srv\controle-treinamentos\env\prod.env")
    parser.add_argument("--target-env", default=r"C:\srv\controle-treinamentos\env\hml.env")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    result = _sync_types(Path(args.source_env), Path(args.target_env), apply_changes=args.apply)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
