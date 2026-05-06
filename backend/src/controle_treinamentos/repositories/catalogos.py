from __future__ import annotations


def count_equipamentos(db) -> int:
    row = db.execute("SELECT COUNT(*) AS total FROM equipamentos").fetchone()
    return int(row["total"] or 0)


def list_equipamentos_page(db, *, limit: int, offset: int) -> list[dict]:
    return db.execute(
        "SELECT * FROM equipamentos ORDER BY nome LIMIT %s OFFSET %s",
        (limit, offset),
    ).fetchall()


def get_equipamento_by_id(db, *, equipamento_id: int) -> dict | None:
    return db.execute("SELECT * FROM equipamentos WHERE id = %s", (equipamento_id,)).fetchone()


def fetch_equipamento_options(db, *, selected_equipment_id: int | None = None) -> list[dict]:
    rows = db.execute(
        """
        SELECT id, nome, tipo, categoria_financeira, ativo
        FROM equipamentos
        WHERE ativo = 1 OR id = %s
        ORDER BY nome
        """,
        (selected_equipment_id or 0,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_equipamento_delete_target(db, *, equipamento_id: int) -> dict | None:
    return db.execute("SELECT id FROM equipamentos WHERE id = %s", (equipamento_id,)).fetchone()


def create_equipamento(db, *, nome: str, tipo: str, categoria_financeira: str | None, ativo: int) -> dict:
    return db.execute(
        """
        INSERT INTO equipamentos (nome, tipo, categoria_financeira, ativo)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (nome, tipo, categoria_financeira, ativo),
    ).fetchone()


def update_equipamento(
    db,
    *,
    equipamento_id: int,
    nome: str,
    tipo: str,
    categoria_financeira: str | None,
    ativo: int,
) -> None:
    db.execute(
        """
        UPDATE equipamentos
        SET nome = %s, tipo = %s, categoria_financeira = %s, ativo = %s
        WHERE id = %s
        """,
        (nome, tipo, categoria_financeira, ativo, equipamento_id),
    )


def equipamento_has_linked_training(db, *, equipamento_id: int) -> bool:
    row = db.execute(
        "SELECT id FROM treinamentos WHERE equipamento_id = %s LIMIT 1",
        (equipamento_id,),
    ).fetchone()
    return bool(row)


def delete_equipamento(db, *, equipamento_id: int) -> None:
    db.execute("DELETE FROM equipamentos WHERE id = %s", (equipamento_id,))


def count_tipos_treinamento(db) -> int:
    row = db.execute("SELECT COUNT(*) AS total FROM tipos_treinamento").fetchone()
    return int(row["total"] or 0)


def list_tipos_treinamento_page(db, *, limit: int, offset: int) -> list[dict]:
    return db.execute(
        "SELECT * FROM tipos_treinamento ORDER BY nome LIMIT %s OFFSET %s",
        (limit, offset),
    ).fetchall()


def get_tipo_treinamento_by_id(db, *, tipo_id: int) -> dict | None:
    return db.execute("SELECT * FROM tipos_treinamento WHERE id = %s", (tipo_id,)).fetchone()


def get_tipo_treinamento_delete_target(db, *, tipo_id: int) -> dict | None:
    return db.execute("SELECT id FROM tipos_treinamento WHERE id = %s", (tipo_id,)).fetchone()


def create_tipo_treinamento(
    db,
    *,
    nome: str,
    periodicidade_meses: int,
    exige_equipamento: int,
    ativo: int,
) -> dict:
    return db.execute(
        """
        INSERT INTO tipos_treinamento (nome, periodicidade_meses, exige_equipamento, ativo)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (nome, periodicidade_meses, exige_equipamento, ativo),
    ).fetchone()


def update_tipo_treinamento(
    db,
    *,
    tipo_id: int,
    nome: str,
    periodicidade_meses: int,
    exige_equipamento: int,
    ativo: int,
) -> None:
    db.execute(
        """
        UPDATE tipos_treinamento
        SET nome = %s, periodicidade_meses = %s, exige_equipamento = %s, ativo = %s
        WHERE id = %s
        """,
        (nome, periodicidade_meses, exige_equipamento, ativo, tipo_id),
    )


def tipo_treinamento_has_linked_training(db, *, tipo_id: int) -> bool:
    row = db.execute(
        "SELECT id FROM treinamentos WHERE tipo_treinamento_id = %s LIMIT 1",
        (tipo_id,),
    ).fetchone()
    return bool(row)


def delete_tipo_treinamento(db, *, tipo_id: int) -> None:
    db.execute("DELETE FROM tipos_treinamento WHERE id = %s", (tipo_id,))
