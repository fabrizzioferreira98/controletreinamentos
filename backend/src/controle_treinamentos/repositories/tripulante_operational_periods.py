from __future__ import annotations


def tripulante_exists(db, *, tripulante_id: int) -> bool:
    return bool(db.execute("SELECT id FROM tripulantes WHERE id = %s", (int(tripulante_id),)).fetchone())


def fetch_operational_periods_by_tripulante(db, *, tripulante_id: int) -> list[dict]:
    rows = db.execute(
        """
        SELECT *
        FROM tripulante_periodos_operacionais
        WHERE tripulante_id = %s
        ORDER BY data_inicio DESC, id DESC
        """,
        (int(tripulante_id),),
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_operational_period(db, *, tripulante_id: int, periodo_id: int) -> dict | None:
    row = db.execute(
        """
        SELECT *
        FROM tripulante_periodos_operacionais
        WHERE tripulante_id = %s AND id = %s
        """,
        (int(tripulante_id), int(periodo_id)),
    ).fetchone()
    return dict(row) if row else None


def find_overlapping_operational_period(db, *, tripulante_id: int, data_inicio: str, data_fim: str) -> dict | None:
    row = db.execute(
        """
        SELECT *
        FROM tripulante_periodos_operacionais
        WHERE tripulante_id = %s
          AND status <> 'cancelado'
          AND data_inicio <= %s
          AND data_fim >= %s
        ORDER BY data_inicio DESC, id DESC
        LIMIT 1
        """,
        (int(tripulante_id), data_fim, data_inicio),
    ).fetchone()
    return dict(row) if row else None


def insert_operational_period(db, *, data: dict) -> dict:
    row = db.execute(
        """
        INSERT INTO tripulante_periodos_operacionais (
            tripulante_id,
            tipo,
            data_inicio,
            data_fim,
            status,
            observacao,
            criado_por
        )
        VALUES (%s, %s, %s, %s, 'ativo', %s, %s)
        RETURNING *
        """,
        (
            int(data["tripulante_id"]),
            data["tipo"],
            data["data_inicio"],
            data["data_fim"],
            data["observacao"],
            data.get("criado_por"),
        ),
    ).fetchone()
    return dict(row)


def cancel_operational_period(db, *, tripulante_id: int, periodo_id: int, cancelado_por: int | None) -> dict | None:
    row = db.execute(
        """
        UPDATE tripulante_periodos_operacionais
        SET status = 'cancelado',
            cancelado_por = %s,
            cancelado_em = CURRENT_TIMESTAMP,
            motivo_status = COALESCE(motivo_status, 'Cancelado via API.')
        WHERE tripulante_id = %s
          AND id = %s
          AND status <> 'cancelado'
        RETURNING *
        """,
        (cancelado_por, int(tripulante_id), int(periodo_id)),
    ).fetchone()
    return dict(row) if row else None
