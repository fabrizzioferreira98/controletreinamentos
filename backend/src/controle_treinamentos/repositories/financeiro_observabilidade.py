from __future__ import annotations

from ..contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT

_AUDIT_COMPETENCIA_EXPR = """
COALESCE(
    ae.payload_novo->'audit_metadata'->>'competencia',
    ae.payload_novo->'metadata'->>'competencia',
    ae.payload_anterior->'audit_metadata'->>'competencia',
    ae.payload_anterior->'metadata'->>'competencia'
)
"""

_AUDIT_PERMISSION_EXPR = """
COALESCE(
    ae.payload_novo->'audit_metadata'->>'permission',
    ae.payload_novo->'metadata'->>'permission',
    ae.payload_anterior->'audit_metadata'->>'permission',
    ae.payload_anterior->'metadata'->>'permission'
)
"""

_AUDIT_ORG_ID_EXPR = """
COALESCE(
    ae.payload_novo->'audit_metadata'->>'org_id',
    ae.payload_novo->'metadata'->>'org_id',
    ae.payload_anterior->'audit_metadata'->>'org_id',
    ae.payload_anterior->'metadata'->>'org_id'
)
"""

_AUDIT_METADATA_EXPR = """
COALESCE(
    ae.payload_novo->'audit_metadata',
    ae.payload_novo->'metadata',
    ae.payload_anterior->'audit_metadata',
    ae.payload_anterior->'metadata',
    '{}'::jsonb
)
"""


def _resolve_org_id(org_id: str | None) -> str:
    return (org_id or "").strip() or FINANCE_ORG_SCOPE_DEFAULT


def _row_to_dict(row, columns: list[str]) -> dict:
    if isinstance(row, dict):
        return dict(row)

    if hasattr(row, "keys"):
        try:
            return {str(key): row[key] for key in row.keys()}
        except Exception:
            pass

    if isinstance(row, (tuple, list)) and columns:
        return {column: row[index] for index, column in enumerate(columns)}

    return dict(row)


def _fetchall_as_dicts(cursor) -> list[dict]:
    rows = cursor.fetchall()
    columns = [description[0] for description in (getattr(cursor, "description", None) or [])]
    return [_row_to_dict(row, columns) for row in rows]


def listar_eventos_auditoria_financeira(
    db,
    *,
    org_id: str | None = None,
    competencia: str | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    event_name: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    resolved_org_id = _resolve_org_id(org_id)
    clauses = [
        "ae.acao LIKE %s",
        f"COALESCE({_AUDIT_ORG_ID_EXPR}, %s) = %s",
    ]
    params: list = [
        resolved_org_id,  # SELECT %s AS org_id
        "finance.%",
        resolved_org_id,
        resolved_org_id,
    ]

    if competencia:
        clauses.append(f"{_AUDIT_COMPETENCIA_EXPR} = %s")
        params.append(competencia)
    if entity_type:
        clauses.append("ae.entidade = %s")
        params.append(entity_type)
    if entity_id is not None:
        clauses.append("ae.entidade_id = %s")
        params.append(int(entity_id))
    if event_name:
        clauses.append("ae.acao = %s")
        params.append(event_name)

    params.extend([int(limit), int(offset)])
    cursor = db.execute(
        f"""
        SELECT
            ae.id,
            %s AS org_id,
            ae.acao AS event_name,
            ae.entidade AS entity_type,
            ae.entidade_id AS entity_id,
            {_AUDIT_COMPETENCIA_EXPR} AS competencia,
            {_AUDIT_PERMISSION_EXPR} AS permission,
            ae.realizado_por AS actor_user_id,
            ae.payload_anterior AS before,
            ae.payload_novo AS after,
            {_AUDIT_METADATA_EXPR} AS metadata,
            ae.realizado_em AS created_at
        FROM auditoria_eventos ae
        WHERE {" AND ".join(clauses)}
        ORDER BY ae.realizado_em DESC, ae.id DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params),
    )
    return _fetchall_as_dicts(cursor)


def listar_divergencias_financeiras(
    db,
    *,
    org_id: str | None = None,
    competencia: str | None = None,
    status: str | None = None,
    severidade: str | None = None,
    codigo: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    resolved_org_id = _resolve_org_id(org_id)
    clauses = ["fd.org_id = %s"]
    params: list = [resolved_org_id]

    if competencia:
        clauses.append("fd.competencia = %s")
        params.append(competencia)
    if status:
        clauses.append("fd.status = %s")
        params.append(status)
    if severidade:
        clauses.append("fd.severidade = %s")
        params.append(severidade)
    if codigo:
        clauses.append("fd.codigo = %s")
        params.append(codigo)

    params.extend([int(limit), int(offset)])
    cursor = db.execute(
        f"""
        SELECT
            fd.id,
            fd.org_id,
            fd.competencia,
            fd.entidade_tipo AS entity_type,
            fd.entidade_id AS entity_id,
            fd.severidade AS severity,
            fd.codigo AS code,
            fd.mensagem AS message,
            fd.status,
            fd.detalhes AS metadata,
            CASE
                WHEN COALESCE(fd.detalhes->>'mission_id', fd.detalhes->>'missao_operacional_id', '') ~ '^[0-9]+$'
                    THEN COALESCE(fd.detalhes->>'mission_id', fd.detalhes->>'missao_operacional_id')::bigint
                ELSE NULL
            END AS mission_id,
            CASE
                WHEN COALESCE(fd.detalhes->>'tripulante_id', '') ~ '^[0-9]+$'
                    THEN (fd.detalhes->>'tripulante_id')::bigint
                ELSE NULL
            END AS tripulante_id,
            fd.created_at AS detected_at
        FROM financeiro_divergencias fd
        WHERE {" AND ".join(clauses)}
        ORDER BY
            CASE fd.severidade
                WHEN 'bloqueante' THEN 1
                WHEN 'alta' THEN 2
                WHEN 'media' THEN 3
                ELSE 4
            END,
            fd.created_at DESC,
            fd.id DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params),
    )
    return _fetchall_as_dicts(cursor)
