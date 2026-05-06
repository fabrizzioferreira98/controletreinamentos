from __future__ import annotations

from ..contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT

_HOLIDAY_COLUMNS = (
    "org_id",
    "data",
    "nome",
    "tipo",
    "localidade",
    "status",
    "created_by",
    "updated_by",
)

_HOLIDAY_UPDATE_COLUMNS = (
    "data",
    "nome",
    "tipo",
    "localidade",
    "status",
    "updated_by",
)


def _resolve_org_id(org_id: str | None) -> str:
    return (org_id or "").strip() or FINANCE_ORG_SCOPE_DEFAULT


def _dict_or_none(row) -> dict | None:
    return dict(row) if row else None


def criar_feriado_nacional(db, *, data: dict, org_id: str | None = None) -> dict:
    resolved_org_id = _resolve_org_id(org_id or data.get("org_id"))
    payload = {column: data.get(column) for column in _HOLIDAY_COLUMNS}
    payload["org_id"] = resolved_org_id
    payload["tipo"] = "nacional"
    payload["localidade"] = None
    payload["status"] = payload.get("status") or "ativo"

    row = db.execute(
        """
        INSERT INTO financeiro_feriados (
            org_id,
            data,
            nome,
            tipo,
            localidade,
            status,
            created_by,
            updated_by
        )
        VALUES (
            %s, %s, %s, 'nacional', NULL, COALESCE(%s, 'ativo'), %s, %s
        )
        RETURNING *
        """,
        (
            payload["org_id"],
            payload["data"],
            payload["nome"],
            payload["status"],
            payload["created_by"],
            payload["updated_by"],
        ),
    ).fetchone()
    return dict(row)


def listar_feriados_nacionais(
    db,
    *,
    org_id: str | None = None,
    status: str | None = None,
    ano: int | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    resolved_org_id = _resolve_org_id(org_id)
    clauses = ["org_id = %s", "tipo = 'nacional'"]
    params: list = [resolved_org_id]
    if status:
        clauses.append("status = %s")
        params.append(status)
    if ano is not None:
        clauses.append("EXTRACT(YEAR FROM data) = %s")
        params.append(int(ano))
    if data_inicio:
        clauses.append("data >= %s::date")
        params.append(data_inicio)
    if data_fim:
        clauses.append("data <= %s::date")
        params.append(data_fim)
    params.extend([int(limit), int(offset)])

    rows = db.execute(
        f"""
        SELECT *
        FROM financeiro_feriados
        WHERE {" AND ".join(clauses)}
        ORDER BY data ASC, id ASC
        LIMIT %s OFFSET %s
        """,
        tuple(params),
    ).fetchall()
    return [dict(row) for row in rows]


def detalhar_feriado_nacional(db, *, feriado_id: int, org_id: str | None = None) -> dict | None:
    resolved_org_id = _resolve_org_id(org_id)
    row = db.execute(
        """
        SELECT *
        FROM financeiro_feriados
        WHERE id = %s
          AND org_id = %s
          AND tipo = 'nacional'
        LIMIT 1
        """,
        (int(feriado_id), resolved_org_id),
    ).fetchone()
    return _dict_or_none(row)


def atualizar_feriado_nacional(
    db,
    *,
    feriado_id: int,
    data: dict,
    org_id: str | None = None,
) -> dict | None:
    resolved_org_id = _resolve_org_id(org_id or data.get("org_id"))
    normalized_data = dict(data)
    if "tipo" in normalized_data:
        normalized_data["tipo"] = "nacional"
    if "localidade" in normalized_data:
        normalized_data["localidade"] = None

    assignments = []
    params = []
    for column in _HOLIDAY_UPDATE_COLUMNS:
        if column in normalized_data:
            assignments.append(f"{column} = %s")
            params.append(normalized_data[column])
    if not assignments:
        return detalhar_feriado_nacional(db, feriado_id=feriado_id, org_id=resolved_org_id)

    params.extend([int(feriado_id), resolved_org_id])
    row = db.execute(
        f"""
        UPDATE financeiro_feriados
        SET {", ".join(assignments)},
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
          AND org_id = %s
          AND tipo = 'nacional'
        RETURNING *
        """,
        tuple(params),
    ).fetchone()
    return _dict_or_none(row)


def verificar_feriado_nacional_por_data(
    db,
    *,
    data: str,
    org_id: str | None = None,
    status: str = "ativo",
) -> dict | None:
    resolved_org_id = _resolve_org_id(org_id)
    row = db.execute(
        """
        SELECT *
        FROM financeiro_feriados
        WHERE org_id = %s
          AND data = %s::date
          AND tipo = 'nacional'
          AND status = %s
        LIMIT 1
        """,
        (resolved_org_id, data, status),
    ).fetchone()
    return _dict_or_none(row)


def verificar_duplicidade_feriado_nacional(
    db,
    *,
    data: str,
    org_id: str | None = None,
    exclude_id: int | None = None,
) -> dict | None:
    resolved_org_id = _resolve_org_id(org_id)
    clauses = [
        "org_id = %s",
        "data = %s::date",
        "tipo = 'nacional'",
        "status = 'ativo'",
    ]
    params: list = [resolved_org_id, data]
    if exclude_id is not None:
        clauses.append("id <> %s")
        params.append(int(exclude_id))

    row = db.execute(
        f"""
        SELECT *
        FROM financeiro_feriados
        WHERE {" AND ".join(clauses)}
        ORDER BY id DESC
        LIMIT 1
        """,
        tuple(params),
    ).fetchone()
    return _dict_or_none(row)
