from __future__ import annotations


def _pernoites_filters(*, tipo: str = "", tripulante_id: int | None = None) -> tuple[str, tuple]:
    clauses: list[str] = []
    params: list = []
    if tipo:
        clauses.append("p.tipo_pernoite = %s")
        params.append(tipo)
    if tripulante_id is not None:
        clauses.append("p.tripulante_id = %s")
        params.append(int(tripulante_id))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, tuple(params)


def fetch_pernoite(db, pernoite_id: int):
    return db.execute("SELECT * FROM pernoites_operacionais WHERE id = %s", (pernoite_id,)).fetchone()


def count_pernoites(db, *, tipo: str = "", tripulante_id: int | None = None) -> int:
    where, params = _pernoites_filters(tipo=tipo, tripulante_id=tripulante_id)
    row = db.execute(
        f"SELECT COUNT(*) AS total FROM pernoites_operacionais p {where}",
        params,
    ).fetchone()
    return int(row["total"] if row else 0)


def fetch_pernoite_list_page(
    db,
    *,
    tipo: str = "",
    tripulante_id: int | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    where, params = _pernoites_filters(tipo=tipo, tripulante_id=tripulante_id)
    rows = db.execute(
        f"""
        SELECT p.*, c.nome AS tripulante_nome
        FROM pernoites_operacionais p
        JOIN tripulantes c ON c.id = p.tripulante_id
        {where}
        ORDER BY p.data_pernoite DESC, p.id DESC
        LIMIT %s OFFSET %s
        """,
        (*params, int(limit), int(offset)),
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_pernoite_detail(db, pernoite_id: int) -> dict | None:
    row = db.execute(
        """
        SELECT p.*, c.nome AS tripulante_nome
        FROM pernoites_operacionais p
        JOIN tripulantes c ON c.id = p.tripulante_id
        WHERE p.id = %s
        """,
        (int(pernoite_id),),
    ).fetchone()
    return dict(row) if row else None


def tripulante_exists(db, tripulante_id: int) -> bool:
    return bool(db.execute("SELECT id FROM tripulantes WHERE id = %s", (tripulante_id,)).fetchone())


def insert_pernoite(db, *, data: dict):
    return db.execute(
        """
        INSERT INTO pernoites_operacionais (
            tripulante_id, data_pernoite, tipo_pernoite, quantidade, observacoes
        )
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            data["tripulante_id"],
            data["data_pernoite"],
            data["tipo_pernoite"],
            data["quantidade"],
            data["observacoes"],
        ),
    ).fetchone()


def update_pernoite(db, *, pernoite_id: int, data: dict) -> None:
    db.execute(
        """
        UPDATE pernoites_operacionais
        SET tripulante_id = %s, data_pernoite = %s,
            tipo_pernoite = %s, quantidade = %s, observacoes = %s
        WHERE id = %s
        """,
        (
            data["tripulante_id"],
            data["data_pernoite"],
            data["tipo_pernoite"],
            data["quantidade"],
            data["observacoes"],
            pernoite_id,
        ),
    )


def delete_pernoite(db, *, pernoite_id: int) -> None:
    db.execute("DELETE FROM pernoites_operacionais WHERE id = %s", (pernoite_id,))
