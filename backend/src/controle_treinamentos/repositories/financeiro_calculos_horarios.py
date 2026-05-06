from __future__ import annotations

import json
from decimal import Decimal

from ..contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT

_CALCULATION_COLUMNS = (
    "org_id",
    "missao_operacional_id",
    "tripulante_id",
    "funcao",
    "jornada_total_minutos",
    "minutos_diurnos",
    "minutos_noturnos",
    "minutos_noturnos_reais",
    "horas_noturnas_convertidas",
    "minutos_pre",
    "minutos_pos",
    "domingo_feriado",
    "valor_adicional_noturno",
    "valor_domingo_feriado_diurno",
    "valor_domingo_feriado_noturno",
    "valor_pre",
    "valor_pos",
    "total",
    "memoria_calculo",
    "parametros_usados",
    "calculation_version",
    "status",
)


def _resolve_org_id(org_id: str | None) -> str:
    return (org_id or "").strip() or FINANCE_ORG_SCOPE_DEFAULT


def _dict_or_none(row) -> dict | None:
    return dict(row) if row else None


def _json_default(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def _json_text(value) -> str:
    return json.dumps(value or {}, default=_json_default, ensure_ascii=False)


def salvar_calculo_horario(db, *, data: dict, org_id: str | None = None) -> dict:
    resolved_org_id = _resolve_org_id(org_id or data.get("org_id"))
    payload = {column: data.get(column) for column in _CALCULATION_COLUMNS}
    payload["org_id"] = resolved_org_id
    payload["missao_operacional_id"] = int(data.get("missao_operacional_id") or data.get("mission_id"))
    minutos_noturnos_reais = int(data.get("minutos_noturnos_reais", data.get("minutos_noturnos", 0)) or 0)
    payload["minutos_noturnos"] = int(data.get("minutos_noturnos", minutos_noturnos_reais) or 0)
    payload["minutos_noturnos_reais"] = minutos_noturnos_reais
    payload["memoria_calculo"] = _json_text(data.get("memoria_calculo"))
    payload["parametros_usados"] = _json_text(data.get("parametros_usados"))
    payload["calculation_version"] = data.get("calculation_version") or "finance-hourly-v1"
    payload["status"] = data.get("status") or "calculado"

    row = db.execute(
        """
        INSERT INTO financeiro_calculos_horarios (
            org_id,
            missao_operacional_id,
            tripulante_id,
            funcao,
            jornada_total_minutos,
            minutos_diurnos,
            minutos_noturnos,
            minutos_noturnos_reais,
            horas_noturnas_convertidas,
            minutos_pre,
            minutos_pos,
            domingo_feriado,
            valor_adicional_noturno,
            valor_domingo_feriado_diurno,
            valor_domingo_feriado_noturno,
            valor_pre,
            valor_pos,
            total,
            memoria_calculo,
            parametros_usados,
            calculation_version,
            status
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s::jsonb,
            %s::jsonb,
            %s,
            COALESCE(%s, 'calculado')
        )
        RETURNING *
        """,
        tuple(payload[column] for column in _CALCULATION_COLUMNS),
    ).fetchone()
    return dict(row)


def _calculo_payload(data: dict, *, org_id: str | None = None) -> dict:
    resolved_org_id = _resolve_org_id(org_id or data.get("org_id"))
    payload = {column: data.get(column) for column in _CALCULATION_COLUMNS}
    payload["org_id"] = resolved_org_id
    payload["missao_operacional_id"] = int(data.get("missao_operacional_id") or data.get("mission_id"))
    payload["tripulante_id"] = int(data.get("tripulante_id"))
    payload["funcao"] = str(data.get("funcao") or "").strip()
    minutos_noturnos_reais = int(data.get("minutos_noturnos_reais", data.get("minutos_noturnos", 0)) or 0)
    payload["minutos_noturnos"] = int(data.get("minutos_noturnos", minutos_noturnos_reais) or 0)
    payload["minutos_noturnos_reais"] = minutos_noturnos_reais
    payload["memoria_calculo"] = _json_text(data.get("memoria_calculo"))
    payload["parametros_usados"] = _json_text(data.get("parametros_usados"))
    payload["calculation_version"] = data.get("calculation_version") or "finance-hourly-v1"
    payload["status"] = data.get("status") or "calculado"
    return payload


def salvar_ou_atualizar_calculo_horario_vigente(db, *, data: dict, org_id: str | None = None) -> dict:
    payload = _calculo_payload(data, org_id=org_id)
    update_columns = [
        column
        for column in _CALCULATION_COLUMNS
        if column not in {"org_id", "missao_operacional_id", "tripulante_id", "funcao"}
    ]
    assignments = [
        f"{column} = %s::jsonb" if column in {"memoria_calculo", "parametros_usados"} else f"{column} = %s"
        for column in update_columns
    ]
    updated = db.execute(
        f"""
        UPDATE financeiro_calculos_horarios
        SET {", ".join(assignments)},
            calculated_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE org_id = %s
          AND missao_operacional_id = %s
          AND tripulante_id = %s
          AND funcao = %s
          AND status <> 'obsoleto'
        RETURNING *, 'updated' AS persistence_action
        """,
        tuple(payload[column] for column in update_columns)
        + (
            payload["org_id"],
            payload["missao_operacional_id"],
            payload["tripulante_id"],
            payload["funcao"],
        ),
    ).fetchone()
    if updated:
        return dict(updated)

    row = db.execute(
        """
        INSERT INTO financeiro_calculos_horarios (
            org_id,
            missao_operacional_id,
            tripulante_id,
            funcao,
            jornada_total_minutos,
            minutos_diurnos,
            minutos_noturnos,
            minutos_noturnos_reais,
            horas_noturnas_convertidas,
            minutos_pre,
            minutos_pos,
            domingo_feriado,
            valor_adicional_noturno,
            valor_domingo_feriado_diurno,
            valor_domingo_feriado_noturno,
            valor_pre,
            valor_pos,
            total,
            memoria_calculo,
            parametros_usados,
            calculation_version,
            status
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s::jsonb,
            %s::jsonb,
            %s,
            COALESCE(%s, 'calculado')
        )
        ON CONFLICT (org_id, missao_operacional_id, tripulante_id, funcao)
        WHERE status <> 'obsoleto'
        DO UPDATE SET
            jornada_total_minutos = EXCLUDED.jornada_total_minutos,
            minutos_diurnos = EXCLUDED.minutos_diurnos,
            minutos_noturnos = EXCLUDED.minutos_noturnos,
            minutos_noturnos_reais = EXCLUDED.minutos_noturnos_reais,
            horas_noturnas_convertidas = EXCLUDED.horas_noturnas_convertidas,
            minutos_pre = EXCLUDED.minutos_pre,
            minutos_pos = EXCLUDED.minutos_pos,
            domingo_feriado = EXCLUDED.domingo_feriado,
            valor_adicional_noturno = EXCLUDED.valor_adicional_noturno,
            valor_domingo_feriado_diurno = EXCLUDED.valor_domingo_feriado_diurno,
            valor_domingo_feriado_noturno = EXCLUDED.valor_domingo_feriado_noturno,
            valor_pre = EXCLUDED.valor_pre,
            valor_pos = EXCLUDED.valor_pos,
            total = EXCLUDED.total,
            memoria_calculo = EXCLUDED.memoria_calculo,
            parametros_usados = EXCLUDED.parametros_usados,
            calculation_version = EXCLUDED.calculation_version,
            status = EXCLUDED.status,
            calculated_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        RETURNING *,
            CASE WHEN xmax = 0 THEN 'inserted' ELSE 'updated' END AS persistence_action
        """,
        tuple(payload[column] for column in _CALCULATION_COLUMNS),
    ).fetchone()
    return dict(row)


def obsoletar_calculos_vigentes_duplicados_da_missao(db, *, missao_operacional_id: int, org_id: str | None = None) -> list[dict]:
    resolved_org_id = _resolve_org_id(org_id)
    rows = db.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY org_id, missao_operacional_id, tripulante_id, funcao
                    ORDER BY updated_at DESC, created_at DESC, id DESC
                ) AS rn
            FROM financeiro_calculos_horarios
            WHERE org_id = %s
              AND missao_operacional_id = %s
              AND status <> 'obsoleto'
        )
        UPDATE financeiro_calculos_horarios ch
        SET status = 'obsoleto',
            updated_at = CURRENT_TIMESTAMP
        FROM ranked r
        WHERE ch.id = r.id
          AND r.rn > 1
        RETURNING ch.*
        """,
        (resolved_org_id, int(missao_operacional_id)),
    ).fetchall()
    return [dict(row) for row in rows]


def listar_calculos_horarios_vigentes_da_missao(db, *, missao_operacional_id: int, org_id: str | None = None) -> list[dict]:
    resolved_org_id = _resolve_org_id(org_id)
    rows = db.execute(
        """
        SELECT *
        FROM financeiro_calculos_horarios
        WHERE org_id = %s
          AND missao_operacional_id = %s
          AND status <> 'obsoleto'
        ORDER BY tripulante_id, funcao, updated_at DESC, id DESC
        """,
        (resolved_org_id, int(missao_operacional_id)),
    ).fetchall()
    return [dict(row) for row in rows]


def invalidar_calculos_horarios_vigentes_da_missao(db, *, missao_operacional_id: int, org_id: str | None = None) -> list[dict]:
    resolved_org_id = _resolve_org_id(org_id)
    rows = db.execute(
        """
        WITH candidates AS (
            SELECT *
            FROM financeiro_calculos_horarios
            WHERE org_id = %s
              AND missao_operacional_id = %s
              AND status <> 'obsoleto'
            FOR UPDATE
        )
        UPDATE financeiro_calculos_horarios ch
        SET status = 'obsoleto',
            updated_at = CURRENT_TIMESTAMP
        FROM candidates c
        WHERE ch.id = c.id
        RETURNING ch.*, c.status AS previous_status
        """,
        (resolved_org_id, int(missao_operacional_id)),
    ).fetchall()
    return [dict(row) for row in rows]


def listar_calculos_horarios(
    db,
    *,
    org_id: str | None = None,
    competencia: str | None = None,
    missao_operacional_id: int | None = None,
    tripulante_id: int | None = None,
    funcao: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    resolved_org_id = _resolve_org_id(org_id)
    clauses = ["ch.org_id = %s", "mo.deleted_at IS NULL"]
    params: list = [resolved_org_id]
    if competencia:
        clauses.append("mo.competencia = %s")
        params.append(competencia)
    if missao_operacional_id is not None:
        clauses.append("ch.missao_operacional_id = %s")
        params.append(int(missao_operacional_id))
    if tripulante_id is not None:
        clauses.append("ch.tripulante_id = %s")
        params.append(int(tripulante_id))
    if funcao:
        clauses.append("ch.funcao = %s")
        params.append(funcao)
    if status:
        clauses.append("ch.status = %s")
        params.append(status)
    params.extend([int(limit), int(offset)])

    rows = db.execute(
        f"""
        SELECT
            ch.*,
            mo.competencia,
            mo.data_missao,
            mo.data_final,
            mo.cavok_numero_voo,
            mo.contratante,
            mo.chamado,
            mo.aeronave_id,
            e.nome AS aeronave_nome,
            mo.categoria_financeira_aeronave,
            mo.horario_apresentacao,
            mo.horario_abandono,
            mo.pos_exec_min,
            mo.trecho,
            mo.houve_pernoite,
            mo.quantidade_pernoites,
            mo.cobertura_base,
            mo.operacao_especial,
            mo.justificativa,
            mo.status AS missao_status,
            t.nome AS tripulante_nome,
            t.cpf AS tripulante_cpf,
            t.licenca_anac AS tripulante_licenca_anac
        FROM financeiro_calculos_horarios ch
        JOIN financeiro_missoes_operacionais mo
          ON mo.id = ch.missao_operacional_id
         AND mo.org_id = ch.org_id
        LEFT JOIN equipamentos e
          ON e.id = mo.aeronave_id
        JOIN tripulantes t
          ON t.id = ch.tripulante_id
        WHERE {" AND ".join(clauses)}
        ORDER BY mo.data_missao DESC, ch.created_at DESC, ch.id DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params),
    ).fetchall()
    return [dict(row) for row in rows]


def detalhar_calculo_horario(db, *, calculo_horario_id: int, org_id: str | None = None) -> dict | None:
    resolved_org_id = _resolve_org_id(org_id)
    row = db.execute(
        """
        SELECT
            ch.*,
            mo.competencia,
            mo.data_missao,
            mo.data_final,
            mo.cavok_numero_voo,
            mo.contratante,
            mo.chamado,
            mo.aeronave_id,
            e.nome AS aeronave_nome,
            mo.categoria_financeira_aeronave,
            mo.horario_apresentacao,
            mo.horario_abandono,
            mo.pos_exec_min,
            mo.trecho,
            mo.houve_pernoite,
            mo.quantidade_pernoites,
            mo.cobertura_base,
            mo.operacao_especial,
            mo.justificativa,
            mo.status AS missao_status,
            t.nome AS tripulante_nome,
            t.cpf AS tripulante_cpf,
            t.licenca_anac AS tripulante_licenca_anac
        FROM financeiro_calculos_horarios ch
        JOIN financeiro_missoes_operacionais mo
          ON mo.id = ch.missao_operacional_id
         AND mo.org_id = ch.org_id
        LEFT JOIN equipamentos e
          ON e.id = mo.aeronave_id
        JOIN tripulantes t
          ON t.id = ch.tripulante_id
        WHERE ch.id = %s
          AND ch.org_id = %s
          AND mo.deleted_at IS NULL
        LIMIT 1
        """,
        (int(calculo_horario_id), resolved_org_id),
    ).fetchone()
    return _dict_or_none(row)


def substituir_calculos_da_missao(db, *, missao_operacional_id: int, org_id: str | None = None) -> int:
    resolved_org_id = _resolve_org_id(org_id)
    row = db.execute(
        """
        UPDATE financeiro_calculos_horarios
        SET status = 'obsoleto',
            updated_at = CURRENT_TIMESTAMP
        WHERE org_id = %s
          AND missao_operacional_id = %s
          AND status <> 'obsoleto'
        RETURNING id
        """,
        (resolved_org_id, int(missao_operacional_id)),
    ).fetchall()
    return len(row)
