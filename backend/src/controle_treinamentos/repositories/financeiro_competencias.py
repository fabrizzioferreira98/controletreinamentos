from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

from ..contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT


def _resolve_org_id(org_id: str | None) -> str:
    return (org_id or "").strip() or FINANCE_ORG_SCOPE_DEFAULT


def _dict_or_none(row) -> dict | None:
    return dict(row) if row else None


def _json_default(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)


def _json_text(value) -> str:
    return json.dumps(value or {}, default=_json_default, ensure_ascii=False)


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


def upsert_competencia_em_conferencia(
    db,
    *,
    competencia: str,
    totals: dict,
    org_id: str | None = None,
) -> dict:
    resolved_org_id = _resolve_org_id(org_id)
    row = db.execute(
        """
        INSERT INTO financeiro_competencias (
            org_id,
            competencia,
            status,
            totals_snapshot
        )
        VALUES (%s, %s, 'em_conferencia', %s::jsonb)
        ON CONFLICT (org_id, competencia)
        DO UPDATE SET
            status = 'em_conferencia',
            totals_snapshot = EXCLUDED.totals_snapshot,
            updated_at = CURRENT_TIMESTAMP
        RETURNING *
        """,
        (resolved_org_id, competencia, _json_text(totals)),
    ).fetchone()
    return dict(row)


def fechar_competencia_financeira(
    db,
    *,
    competencia: str,
    totals: dict,
    snapshot: dict,
    closed_by: int,
    org_id: str | None = None,
) -> dict:
    resolved_org_id = _resolve_org_id(org_id)
    row = db.execute(
        """
        INSERT INTO financeiro_competencias (
            org_id,
            competencia,
            status,
            totals_snapshot,
            fechamento_snapshot,
            closed_by,
            closed_at
        )
        VALUES (%s, %s, 'fechada', %s::jsonb, %s::jsonb, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (org_id, competencia)
        DO UPDATE SET
            status = 'fechada',
            totals_snapshot = EXCLUDED.totals_snapshot,
            fechamento_snapshot = EXCLUDED.fechamento_snapshot,
            closed_by = EXCLUDED.closed_by,
            closed_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        RETURNING *
        """,
        (resolved_org_id, competencia, _json_text(totals), _json_text(snapshot), closed_by),
    ).fetchone()
    return dict(row)


def reabrir_competencia_financeira(
    db,
    *,
    competencia: str,
    motivo: str,
    reopened_by: int,
    org_id: str | None = None,
) -> dict | None:
    resolved_org_id = _resolve_org_id(org_id)
    row = db.execute(
        """
        UPDATE financeiro_competencias
        SET status = 'reaberta',
            reopen_reason = %s,
            reopened_by = %s,
            reopened_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE org_id = %s
          AND competencia = %s
        RETURNING *
        """,
        (motivo, reopened_by, resolved_org_id, competencia),
    ).fetchone()
    return _dict_or_none(row)


def listar_divergencias_competencia(
    db,
    *,
    competencia: str,
    org_id: str | None = None,
) -> list[dict]:
    resolved_org_id = _resolve_org_id(org_id)
    rows = db.execute(
        """
        SELECT *
        FROM financeiro_divergencias
        WHERE org_id = %s
          AND competencia = %s
        ORDER BY
            CASE severidade
                WHEN 'bloqueante' THEN 1
                WHEN 'alta' THEN 2
                WHEN 'media' THEN 3
                ELSE 4
            END,
            created_at DESC,
            id DESC
        """,
        (resolved_org_id, competencia),
    ).fetchall()
    return [dict(row) for row in rows]
