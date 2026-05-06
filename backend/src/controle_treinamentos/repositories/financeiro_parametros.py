from __future__ import annotations

from ..contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT

_PARAMETER_COLUMNS = (
    "org_id",
    "tipo",
    "funcao",
    "categoria",
    "valor",
    "unidade",
    "vigencia_inicio",
    "vigencia_fim",
    "status",
    "motivo",
    "created_by",
    "updated_by",
)

_PARAMETER_UPDATE_COLUMNS = (
    "tipo",
    "funcao",
    "categoria",
    "valor",
    "unidade",
    "vigencia_inicio",
    "vigencia_fim",
    "status",
    "motivo",
    "updated_by",
)


def _resolve_org_id(org_id: str | None) -> str:
    return (org_id or "").strip() or FINANCE_ORG_SCOPE_DEFAULT


def _dict_or_none(row) -> dict | None:
    return dict(row) if row else None


def criar_parametro_financeiro(db, *, data: dict, org_id: str | None = None) -> dict:
    resolved_org_id = _resolve_org_id(org_id or data.get("org_id"))
    payload = {column: data.get(column) for column in _PARAMETER_COLUMNS}
    payload["org_id"] = resolved_org_id
    payload["status"] = payload.get("status") or "ativo"

    row = db.execute(
        """
        INSERT INTO financeiro_parametros (
            org_id,
            tipo,
            funcao,
            categoria,
            valor,
            unidade,
            vigencia_inicio,
            vigencia_fim,
            status,
            motivo,
            created_by,
            updated_by
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s,
            COALESCE(%s, 'ativo'),
            %s, %s, %s
        )
        RETURNING *
        """,
        tuple(payload[column] for column in _PARAMETER_COLUMNS),
    ).fetchone()
    return dict(row)


def listar_parametros_financeiros(
    db,
    *,
    org_id: str | None = None,
    tipo: str | None = None,
    status: str | None = None,
    funcao: str | None = None,
    categoria: str | None = None,
    unidade: str | None = None,
    vigencia_em: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    resolved_org_id = _resolve_org_id(org_id)
    clauses = ["org_id = %s"]
    params: list = [resolved_org_id]
    if tipo:
        clauses.append("tipo = %s")
        params.append(tipo)
    if status:
        clauses.append("status = %s")
        params.append(status)
    if funcao is not None:
        clauses.append("LOWER(COALESCE(funcao, '')) = LOWER(COALESCE(%s, ''))")
        params.append(funcao)
    if categoria is not None:
        clauses.append("COALESCE(categoria, '') = COALESCE(%s, '')")
        params.append(categoria)
    if unidade:
        clauses.append("unidade = %s")
        params.append(unidade)
    if vigencia_em:
        clauses.append("vigencia_inicio <= %s::date")
        clauses.append("(vigencia_fim IS NULL OR vigencia_fim >= %s::date)")
        params.extend([vigencia_em, vigencia_em])
    params.extend([int(limit), int(offset)])

    rows = db.execute(
        f"""
        SELECT *
        FROM financeiro_parametros
        WHERE {" AND ".join(clauses)}
        ORDER BY tipo, COALESCE(funcao, ''), COALESCE(categoria, ''), vigencia_inicio DESC, id DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params),
    ).fetchall()
    return [dict(row) for row in rows]


def listar_parametros_financeiros_por_ids(
    db,
    *,
    parameter_ids: list[int] | tuple[int, ...] | set[int],
    org_id: str | None = None,
) -> list[dict]:
    resolved_org_id = _resolve_org_id(org_id)
    normalized_ids = sorted({int(item) for item in (parameter_ids or [])})
    if not normalized_ids:
        return []
    placeholders = ", ".join(["%s"] * len(normalized_ids))
    rows = db.execute(
        f"""
        SELECT *
        FROM financeiro_parametros
        WHERE org_id = %s
          AND id IN ({placeholders})
        ORDER BY id
        """,
        tuple([resolved_org_id, *normalized_ids]),
    ).fetchall()
    return [dict(row) for row in rows]


def detalhar_parametro_financeiro(db, *, parametro_id: int, org_id: str | None = None) -> dict | None:
    resolved_org_id = _resolve_org_id(org_id)
    row = db.execute(
        """
        SELECT *
        FROM financeiro_parametros
        WHERE id = %s
          AND org_id = %s
        LIMIT 1
        """,
        (int(parametro_id), resolved_org_id),
    ).fetchone()
    return _dict_or_none(row)


def atualizar_parametro_financeiro(
    db,
    *,
    parametro_id: int,
    data: dict,
    org_id: str | None = None,
) -> dict | None:
    resolved_org_id = _resolve_org_id(org_id or data.get("org_id"))
    assignments = []
    params = []
    for column in _PARAMETER_UPDATE_COLUMNS:
        if column in data:
            assignments.append(f"{column} = %s")
            params.append(data[column])
    if not assignments:
        return detalhar_parametro_financeiro(db, parametro_id=parametro_id, org_id=resolved_org_id)

    params.extend([int(parametro_id), resolved_org_id])
    row = db.execute(
        f"""
        UPDATE financeiro_parametros
        SET {", ".join(assignments)},
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
          AND org_id = %s
        RETURNING *
        """,
        tuple(params),
    ).fetchone()
    return _dict_or_none(row)


def verificar_sobreposicao_vigencia(
    db,
    *,
    org_id: str | None = None,
    tipo: str,
    funcao: str | None = None,
    categoria: str | None = None,
    unidade: str,
    vigencia_inicio: str,
    vigencia_fim: str | None = None,
    exclude_id: int | None = None,
) -> dict | None:
    resolved_org_id = _resolve_org_id(org_id)
    clauses = [
        "org_id = %s",
        "tipo = %s",
        "LOWER(COALESCE(funcao, '')) = LOWER(COALESCE(%s, ''))",
        "COALESCE(categoria, '') = COALESCE(%s, '')",
        "unidade = %s",
        "status = 'ativo'",
        """
        NOT (
            COALESCE(vigencia_fim, '9999-12-31'::date) < %s::date
            OR COALESCE(%s::date, '9999-12-31'::date) < vigencia_inicio
        )
        """,
    ]
    params: list = [
        resolved_org_id,
        tipo,
        funcao,
        categoria,
        unidade,
        vigencia_inicio,
        vigencia_fim,
    ]
    if exclude_id is not None:
        clauses.append("id <> %s")
        params.append(int(exclude_id))

    row = db.execute(
        f"""
        SELECT *
        FROM financeiro_parametros
        WHERE {" AND ".join(clauses)}
        ORDER BY vigencia_inicio DESC, id DESC
        LIMIT 1
        """,
        tuple(params),
    ).fetchone()
    return _dict_or_none(row)


def buscar_parametro_vigente(
    db,
    *,
    org_id: str | None = None,
    tipo: str,
    vigencia_em: str,
    funcao: str | None = None,
    categoria: str | None = None,
    unidade: str | None = None,
) -> dict | None:
    resolved_org_id = _resolve_org_id(org_id)
    clauses = [
        "org_id = %s",
        "tipo = %s",
        "status = 'ativo'",
        "vigencia_inicio <= %s::date",
        "(vigencia_fim IS NULL OR vigencia_fim >= %s::date)",
    ]
    params: list = [resolved_org_id, tipo, vigencia_em, vigencia_em]
    if funcao is not None:
        clauses.append("LOWER(COALESCE(funcao, '')) = LOWER(COALESCE(%s, ''))")
        params.append(funcao)
    if categoria is not None:
        clauses.append("COALESCE(categoria, '') = COALESCE(%s, '')")
        params.append(categoria)
    if unidade:
        clauses.append("unidade = %s")
        params.append(unidade)

    row = db.execute(
        f"""
        SELECT *
        FROM financeiro_parametros
        WHERE {" AND ".join(clauses)}
        ORDER BY vigencia_inicio DESC, id DESC
        LIMIT 1
        """,
        tuple(params),
    ).fetchone()
    return _dict_or_none(row)
