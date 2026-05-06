from __future__ import annotations

from ..contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT

_MISSION_COLUMNS = (
    "org_id",
    "competencia",
    "data_missao",
    "data_final",
    "cavok_numero_voo",
    "contratante",
    "chamado",
    "aeronave_id",
    "categoria_financeira_aeronave",
    "comandante_tripulante_id",
    "copiloto_tripulante_id",
    "horario_apresentacao",
    "horario_abandono",
    "pos_exec_min",
    "trecho",
    "houve_pernoite",
    "quantidade_pernoites",
    "cobertura_base",
    "operacao_especial",
    "justificativa",
    "status",
    "observacoes",
    "created_by",
    "updated_by",
)

_MISSION_UPDATE_COLUMNS = (
    "competencia",
    "data_missao",
    "data_final",
    "cavok_numero_voo",
    "contratante",
    "chamado",
    "aeronave_id",
    "categoria_financeira_aeronave",
    "comandante_tripulante_id",
    "copiloto_tripulante_id",
    "horario_apresentacao",
    "horario_abandono",
    "pos_exec_min",
    "trecho",
    "houve_pernoite",
    "quantidade_pernoites",
    "cobertura_base",
    "operacao_especial",
    "justificativa",
    "status",
    "observacoes",
    "updated_by",
)


def _resolve_org_id(org_id: str | None) -> str:
    return (org_id or "").strip() or FINANCE_ORG_SCOPE_DEFAULT


def _dict_or_none(row) -> dict | None:
    return dict(row) if row else None


def create_missao_operacional(db, *, data: dict, org_id: str | None = None) -> dict:
    resolved_org_id = _resolve_org_id(org_id or data.get("org_id"))
    payload = {column: data.get(column) for column in _MISSION_COLUMNS}
    payload["org_id"] = resolved_org_id
    payload["houve_pernoite"] = bool(data.get("houve_pernoite", False))
    payload["quantidade_pernoites"] = int(data.get("quantidade_pernoites") or 0)
    payload["cobertura_base"] = bool(data.get("cobertura_base", False)) and payload["quantidade_pernoites"] > 0
    payload["pos_exec_min"] = int(data.get("pos_exec_min") or 0)
    payload["data_final"] = data.get("data_final") or data.get("data_missao")
    payload["status"] = data.get("status") or "rascunho"
    columns_sql = ", ".join(_MISSION_COLUMNS)
    placeholders = ", ".join(["%s"] * len(_MISSION_COLUMNS))

    row = db.execute(
        f"""
        INSERT INTO financeiro_missoes_operacionais ({columns_sql})
        VALUES ({placeholders})
        RETURNING *
        """,
        tuple(payload[column] for column in _MISSION_COLUMNS),
    ).fetchone()
    return dict(row)


def insert_missao_tripulante(
    db,
    *,
    missao_operacional_id: int,
    tripulante_id: int,
    funcao: str,
    org_id: str | None = None,
    status: str = "ativo",
) -> dict | None:
    resolved_org_id = _resolve_org_id(org_id)
    row = db.execute(
        """
        INSERT INTO financeiro_missao_tripulantes (
            org_id,
            missao_operacional_id,
            tripulante_id,
            funcao,
            status
        )
        SELECT %s, mo.id, %s, %s, %s
        FROM financeiro_missoes_operacionais mo
        WHERE mo.id = %s
          AND mo.org_id = %s
          AND mo.deleted_at IS NULL
        RETURNING *
        """,
        (
            resolved_org_id,
            int(tripulante_id),
            funcao,
            status,
            int(missao_operacional_id),
            resolved_org_id,
        ),
    ).fetchone()
    return _dict_or_none(row)


def insert_tripulantes_missao(
    db,
    *,
    missao_operacional_id: int,
    comandante_tripulante_id: int,
    copiloto_tripulante_id: int,
    org_id: str | None = None,
) -> list[dict]:
    resolved_org_id = _resolve_org_id(org_id)
    participantes = [
        insert_missao_tripulante(
            db,
            missao_operacional_id=missao_operacional_id,
            tripulante_id=comandante_tripulante_id,
            funcao="comandante",
            org_id=resolved_org_id,
        ),
        insert_missao_tripulante(
            db,
            missao_operacional_id=missao_operacional_id,
            tripulante_id=copiloto_tripulante_id,
            funcao="copiloto",
            org_id=resolved_org_id,
        ),
    ]
    return [participante for participante in participantes if participante is not None]


def replace_missao_tripulantes(
    db,
    *,
    missao_operacional_id: int,
    comandante_tripulante_id: int,
    copiloto_tripulante_id: int,
    org_id: str | None = None,
) -> list[dict]:
    resolved_org_id = _resolve_org_id(org_id)
    db.execute(
        """
        DELETE FROM financeiro_missao_tripulantes
        WHERE missao_operacional_id = %s
          AND org_id = %s
        """,
        (int(missao_operacional_id), resolved_org_id),
    )
    return insert_tripulantes_missao(
        db,
        missao_operacional_id=missao_operacional_id,
        comandante_tripulante_id=comandante_tripulante_id,
        copiloto_tripulante_id=copiloto_tripulante_id,
        org_id=resolved_org_id,
    )


def create_missao_operacional_with_tripulantes(db, *, data: dict, org_id: str | None = None) -> dict:
    mission = create_missao_operacional(db, data=data, org_id=org_id)
    participants = insert_tripulantes_missao(
        db,
        missao_operacional_id=mission["id"],
        comandante_tripulante_id=mission["comandante_tripulante_id"],
        copiloto_tripulante_id=mission["copiloto_tripulante_id"],
        org_id=mission["org_id"],
    )
    mission["participantes"] = participants
    return mission


def list_missoes_operacionais(
    db,
    *,
    competencia: str,
    org_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    resolved_org_id = _resolve_org_id(org_id)
    clauses = ["org_id = %s", "competencia = %s", "deleted_at IS NULL"]
    params: list = [resolved_org_id, competencia]
    if status:
        clauses.append("status = %s")
        params.append(status)
    params.extend([int(limit), int(offset)])

    rows = db.execute(
        f"""
        SELECT *
        FROM financeiro_missoes_operacionais
        WHERE {" AND ".join(clauses)}
        ORDER BY data_missao DESC, id DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params),
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_missao_operacional(
    db,
    *,
    missao_operacional_id: int,
    org_id: str | None = None,
    include_deleted: bool = False,
) -> dict | None:
    resolved_org_id = _resolve_org_id(org_id)
    deleted_clause = "" if include_deleted else "AND deleted_at IS NULL"
    row = db.execute(
        f"""
        SELECT *
        FROM financeiro_missoes_operacionais
        WHERE id = %s
          AND org_id = %s
          {deleted_clause}
        LIMIT 1
        """,
        (int(missao_operacional_id), resolved_org_id),
    ).fetchone()
    return _dict_or_none(row)


def lock_missao_operacional(
    db,
    *,
    missao_operacional_id: int,
    org_id: str | None = None,
    include_deleted: bool = False,
) -> dict | None:
    resolved_org_id = _resolve_org_id(org_id)
    deleted_clause = "" if include_deleted else "AND deleted_at IS NULL"
    row = db.execute(
        f"""
        SELECT *
        FROM financeiro_missoes_operacionais
        WHERE id = %s
          AND org_id = %s
          {deleted_clause}
        FOR UPDATE
        """,
        (int(missao_operacional_id), resolved_org_id),
    ).fetchone()
    return _dict_or_none(row)


def list_missao_tripulantes(
    db,
    *,
    missao_operacional_id: int,
    org_id: str | None = None,
    include_deleted: bool = False,
) -> list[dict]:
    resolved_org_id = _resolve_org_id(org_id)
    deleted_clause = "" if include_deleted else "AND mo.deleted_at IS NULL"
    rows = db.execute(
        f"""
        SELECT
            mt.id,
            mt.org_id,
            mt.missao_operacional_id,
            mt.tripulante_id,
            mt.funcao,
            mt.status,
            mt.created_at,
            t.nome AS tripulante_nome,
            t.cpf AS tripulante_cpf,
            t.licenca_anac AS tripulante_licenca_anac
        FROM financeiro_missao_tripulantes mt
        JOIN financeiro_missoes_operacionais mo
          ON mo.id = mt.missao_operacional_id
         AND mo.org_id = mt.org_id
        JOIN tripulantes t ON t.id = mt.tripulante_id
        WHERE mt.missao_operacional_id = %s
          AND mt.org_id = %s
          {deleted_clause}
        ORDER BY
            CASE mt.funcao
                WHEN 'comandante' THEN 1
                WHEN 'copiloto' THEN 2
                ELSE 3
            END,
            mt.id
        """,
        (int(missao_operacional_id), resolved_org_id),
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_missao_operacional_detail(
    db,
    *,
    missao_operacional_id: int,
    org_id: str | None = None,
    include_deleted: bool = False,
) -> dict | None:
    mission = fetch_missao_operacional(
        db,
        missao_operacional_id=missao_operacional_id,
        org_id=org_id,
        include_deleted=include_deleted,
    )
    if not mission:
        return None
    mission["participantes"] = list_missao_tripulantes(
        db,
        missao_operacional_id=missao_operacional_id,
        org_id=mission["org_id"],
        include_deleted=include_deleted,
    )
    return mission


def update_missao_operacional(
    db,
    *,
    missao_operacional_id: int,
    data: dict,
    org_id: str | None = None,
) -> dict | None:
    resolved_org_id = _resolve_org_id(org_id or data.get("org_id"))
    assignments = []
    params = []
    for column in _MISSION_UPDATE_COLUMNS:
        if column in data:
            assignments.append(f"{column} = %s")
            params.append(data[column])
    if not assignments:
        return fetch_missao_operacional(db, missao_operacional_id=missao_operacional_id, org_id=resolved_org_id)

    params.extend([int(missao_operacional_id), resolved_org_id])
    row = db.execute(
        f"""
        UPDATE financeiro_missoes_operacionais
        SET {", ".join(assignments)},
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
          AND org_id = %s
        RETURNING *
        """,
        tuple(params),
    ).fetchone()
    return _dict_or_none(row)


def cancel_missao_operacional(
    db,
    *,
    missao_operacional_id: int,
    org_id: str | None = None,
    updated_by: int | None = None,
) -> dict | None:
    resolved_org_id = _resolve_org_id(org_id)
    row = db.execute(
        """
        UPDATE financeiro_missoes_operacionais
        SET status = 'cancelada',
            updated_by = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
          AND org_id = %s
        RETURNING *
        """,
        (updated_by, int(missao_operacional_id), resolved_org_id),
    ).fetchone()
    return _dict_or_none(row)


def cancel_missao_tripulantes(
    db,
    *,
    missao_operacional_id: int,
    org_id: str | None = None,
) -> list[dict]:
    resolved_org_id = _resolve_org_id(org_id)
    rows = db.execute(
        """
        UPDATE financeiro_missao_tripulantes
        SET status = 'cancelado'
        WHERE missao_operacional_id = %s
          AND org_id = %s
          AND status <> 'cancelado'
        RETURNING *
        """,
        (int(missao_operacional_id), resolved_org_id),
    ).fetchall()
    return [dict(row) for row in rows]


def remover_missao_tripulantes(
    db,
    *,
    missao_operacional_id: int,
    org_id: str | None = None,
) -> list[dict]:
    resolved_org_id = _resolve_org_id(org_id)
    rows = db.execute(
        """
        UPDATE financeiro_missao_tripulantes
        SET status = 'removido'
        WHERE missao_operacional_id = %s
          AND org_id = %s
          AND status <> 'removido'
        RETURNING *
        """,
        (int(missao_operacional_id), resolved_org_id),
    ).fetchall()
    return [dict(row) for row in rows]


def soft_delete_missao_operacional(
    db,
    *,
    missao_operacional_id: int,
    org_id: str | None = None,
    deleted_by: int | None = None,
    delete_reason: str | None = None,
) -> dict | None:
    resolved_org_id = _resolve_org_id(org_id)
    row = db.execute(
        """
        UPDATE financeiro_missoes_operacionais
        SET deleted_at = CURRENT_TIMESTAMP,
            deleted_by = %s,
            delete_reason = %s,
            updated_by = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
          AND org_id = %s
          AND deleted_at IS NULL
        RETURNING *
        """,
        (deleted_by, delete_reason, deleted_by, int(missao_operacional_id), resolved_org_id),
    ).fetchone()
    return _dict_or_none(row)


def mission_delete_dependency_summary(
    db,
    *,
    missao_operacional_id: int,
    competencia: str,
    org_id: str | None = None,
) -> dict:
    resolved_org_id = _resolve_org_id(org_id)
    hourly_row = db.execute(
        """
        SELECT COUNT(*) AS total
        FROM financeiro_calculos_horarios
        WHERE org_id = %s
          AND missao_operacional_id = %s
        """,
        (resolved_org_id, int(missao_operacional_id)),
    ).fetchone()
    productivity_row = db.execute(
        """
        SELECT COUNT(*) AS total
        FROM financeiro_calculos_produtividade cp
        WHERE cp.org_id = %s
          AND cp.competencia = %s
          AND EXISTS (
              SELECT 1
              FROM financeiro_missao_tripulantes mt
              WHERE mt.org_id = cp.org_id
                AND mt.missao_operacional_id = %s
                AND mt.tripulante_id = cp.tripulante_id
                AND mt.funcao = cp.funcao
          )
        """,
        (resolved_org_id, competencia, int(missao_operacional_id)),
    ).fetchone()
    divergence_row = db.execute(
        """
        SELECT COUNT(*) AS total
        FROM financeiro_divergencias
        WHERE org_id = %s
          AND (
              (entidade_tipo IN ('finance_mission', 'finance_journey_line') AND entidade_id = %s)
              OR detalhes ->> 'mission_id' = %s
              OR detalhes ->> 'missao_operacional_id' = %s
          )
        """,
        (
            resolved_org_id,
            int(missao_operacional_id),
            str(int(missao_operacional_id)),
            str(int(missao_operacional_id)),
        ),
    ).fetchone()
    return {
        "calculos_horarios": int(hourly_row["total"] or 0) if hourly_row else 0,
        "calculos_produtividade": int(productivity_row["total"] or 0) if productivity_row else 0,
        "divergencias": int(divergence_row["total"] or 0) if divergence_row else 0,
    }


def find_duplicate_missao_operacional(
    db,
    *,
    cavok_numero_voo: str | None = None,
    contratante: str | None = None,
    chamado: str | None = None,
    org_id: str | None = None,
    exclude_id: int | None = None,
) -> dict | None:
    resolved_org_id = _resolve_org_id(org_id)
    if not any(str(value or "").strip() for value in (cavok_numero_voo, contratante, chamado)):
        return None

    clauses = [
        "org_id = %s",
        "deleted_at IS NULL",
        "COALESCE(NULLIF(TRIM(cavok_numero_voo), ''), '') = COALESCE(NULLIF(TRIM(%s), ''), '')",
        "COALESCE(NULLIF(TRIM(contratante), ''), '') = COALESCE(NULLIF(TRIM(%s), ''), '')",
        "COALESCE(NULLIF(TRIM(chamado), ''), '') = COALESCE(NULLIF(TRIM(%s), ''), '')",
    ]
    params: list = [resolved_org_id, cavok_numero_voo, contratante, chamado]
    if exclude_id is not None:
        clauses.append("id <> %s")
        params.append(int(exclude_id))

    row = db.execute(
        f"""
        SELECT *
        FROM financeiro_missoes_operacionais
        WHERE {" AND ".join(clauses)}
        ORDER BY id DESC
        LIMIT 1
        """,
        tuple(params),
    ).fetchone()
    return _dict_or_none(row)


def fetch_competencia_financeira(db, *, competencia: str, org_id: str | None = None) -> dict | None:
    resolved_org_id = _resolve_org_id(org_id)
    row = db.execute(
        """
        SELECT *
        FROM financeiro_competencias
        WHERE org_id = %s
          AND competencia = %s
        LIMIT 1
        """,
        (resolved_org_id, competencia),
    ).fetchone()
    return _dict_or_none(row)
