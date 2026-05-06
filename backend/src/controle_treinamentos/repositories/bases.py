from __future__ import annotations


def fetch_active_base(db, base_id: int):
    return db.execute(
        "SELECT id, nome, uf FROM bases WHERE id = %s AND ativa = TRUE",
        (base_id,),
    ).fetchone()


def fetch_pilot_detail(db, pilot_id: int):
    return db.execute(
        """
        SELECT p.*, b.nome AS base_nome, b.uf AS base_uf
        FROM pilotos p
        JOIN bases b ON b.id = p.base_id
        WHERE p.id = %s
        """,
        (pilot_id,),
    ).fetchone()


def fetch_tripulante_for_pilot_link(db, tripulante_id: int):
    return db.execute(
        """
        SELECT id, nome, licenca_anac
        FROM tripulantes
        WHERE id = %s
        """,
        (tripulante_id,),
    ).fetchone()


def find_pilot_by_tripulante_id(db, tripulante_id: int):
    return db.execute("SELECT id FROM pilotos WHERE tripulante_id = %s", (tripulante_id,)).fetchone()


def find_pilot_by_matricula(db, matricula: str):
    return db.execute(
        "SELECT id FROM pilotos WHERE UPPER(TRIM(matricula)) = UPPER(%s)",
        (matricula,),
    ).fetchone()


def insert_pilot(db, *, nome: str, matricula: str, tripulante_id: int | None, base_id: int, status: str):
    return db.execute(
        """
        INSERT INTO pilotos (nome, matricula, tripulante_id, base_id, status)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (nome, matricula, tripulante_id, base_id, status),
    ).fetchone()


def update_pilot_status(db, *, pilot_id: int, status: str) -> None:
    db.execute("UPDATE pilotos SET status = %s WHERE id = %s", (status, pilot_id))


def update_pilot_base(db, *, pilot_id: int, base_id: int) -> None:
    db.execute("UPDATE pilotos SET base_id = %s WHERE id = %s", (base_id, pilot_id))


def update_tripulante_from_pilot(
    db,
    *,
    tripulante_id: int,
    nome: str,
    base_snapshot_compat_nome: str,
    status_snapshot_compat_label: str,
    ativo: int,
) -> None:
    db.execute(
        """
        UPDATE tripulantes
        SET nome = %s, base = %s, status = %s, ativo = %s
        WHERE id = %s
        """,
        (nome, base_snapshot_compat_nome, status_snapshot_compat_label, ativo, tripulante_id),
    )


def insert_pilot_history(
    db,
    *,
    pilot_id: int,
    status_anterior,
    status_novo,
    base_anterior_id,
    base_nova_id,
    alterado_por: int,
    observacao: str | None,
) -> None:
    db.execute(
        """
        INSERT INTO historico_status_piloto
        (piloto_id, status_anterior, status_novo, base_anterior_id, base_nova_id, alterado_por, observacao)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            pilot_id,
            status_anterior,
            status_novo,
            base_anterior_id,
            base_nova_id,
            alterado_por,
            (observacao or "").strip() or None,
        ),
    )


def fetch_pilot_history(db, pilot_id: int):
    return db.execute(
        """
        SELECT
            h.*,
            u.nome AS alterado_por_nome,
            ba.nome AS base_anterior_nome,
            bn.nome AS base_nova_nome
        FROM historico_status_piloto h
        LEFT JOIN usuarios u ON u.id = h.alterado_por
        LEFT JOIN bases ba ON ba.id = h.base_anterior_id
        LEFT JOIN bases bn ON bn.id = h.base_nova_id
        WHERE h.piloto_id = %s
        ORDER BY h.alterado_em DESC, h.id DESC
        """,
        (pilot_id,),
    ).fetchall()
