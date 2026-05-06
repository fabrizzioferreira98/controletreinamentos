from __future__ import annotations

from ..contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT


def _resolve_org_id(org_id: str | None) -> str:
    return (org_id or "").strip() or FINANCE_ORG_SCOPE_DEFAULT


def _line_select_sql(extra_where: str = "") -> str:
    where = f"WHERE {extra_where}" if extra_where else ""
    return f"""
        SELECT
            mt.id AS linha_id,
            mt.org_id AS linha_org_id,
            mt.status AS linha_status,
            mt.funcao AS linha_funcao,
            mt.tripulante_id AS linha_tripulante_id,
            mo.id AS missao_operacional_id,
            mo.org_id,
            mo.competencia,
            mo.data_missao,
            mo.data_final,
            mo.cavok_numero_voo,
            mo.contratante,
            mo.chamado,
            mo.aeronave_id,
            e.nome AS aeronave_nome,
            e.tipo AS aeronave_tipo,
            e.categoria_financeira AS aeronave_categoria_financeira,
            mo.categoria_financeira_aeronave,
            mo.comandante_tripulante_id,
            mo.copiloto_tripulante_id,
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
            mo.observacoes,
            mo.created_at AS missao_created_at,
            mo.updated_at AS missao_updated_at,
            t.nome AS tripulante_nome,
            t.cpf AS tripulante_cpf,
            t.licenca_anac AS tripulante_licenca_anac,
            t.funcao_operacional AS tripulante_funcao_operacional,
            t.categoria_operacional AS tripulante_categoria_operacional,
            ch.id AS calculo_horario_id,
            ch.jornada_total_minutos,
            ch.minutos_diurnos,
            ch.minutos_noturnos,
            ch.minutos_noturnos_reais,
            ch.horas_noturnas_convertidas,
            ch.minutos_pre,
            ch.minutos_pos,
            ch.domingo_feriado,
            ch.valor_adicional_noturno,
            ch.valor_domingo_feriado_diurno,
            ch.valor_domingo_feriado_noturno,
            ch.valor_pre,
            ch.valor_pos,
            ch.total AS calculo_total,
            ch.memoria_calculo,
            ch.parametros_usados,
            ch.status AS calculo_status,
            ch.calculation_version,
            ch.calculated_at
        FROM financeiro_missao_tripulantes mt
        JOIN financeiro_missoes_operacionais mo
          ON mo.id = mt.missao_operacional_id
         AND mo.org_id = mt.org_id
        JOIN tripulantes t
          ON t.id = mt.tripulante_id
        LEFT JOIN equipamentos e
          ON e.id = mo.aeronave_id
        LEFT JOIN financeiro_calculos_horarios ch
          ON ch.org_id = mt.org_id
         AND ch.missao_operacional_id = mt.missao_operacional_id
         AND ch.tripulante_id = mt.tripulante_id
         AND ch.funcao = mt.funcao
         AND ch.status <> 'obsoleto'
        {where}
        ORDER BY mo.data_missao ASC, mo.id ASC, CASE mt.funcao WHEN 'comandante' THEN 1 ELSE 2 END, mt.id ASC
    """


def listar_linhas_jornada(
    db,
    *,
    competencia: str,
    org_id: str | None = None,
    funcao: str | None = None,
    tripulante_id: int | None = None,
    status: str | None = None,
    limit: int = 1000,
    offset: int = 0,
) -> list[dict]:
    resolved_org_id = _resolve_org_id(org_id)
    clauses = ["mt.org_id = %s", "mo.competencia = %s", "mo.deleted_at IS NULL"]
    params: list = [resolved_org_id, competencia]
    if funcao:
        clauses.append("mt.funcao = %s")
        params.append(funcao)
    if tripulante_id:
        clauses.append("mt.tripulante_id = %s")
        params.append(int(tripulante_id))
    if status:
        normalized_status = str(status).strip().lower()
        if normalized_status in {"cancelada", "cancelado"}:
            clauses.append("(mo.status = 'cancelada' OR mt.status = 'cancelado')")
        elif normalized_status in {"calculado", "recalculo_pendente", "obsoleto"}:
            clauses.append("ch.status = %s")
            params.append(normalized_status)
        else:
            clauses.append("(mo.status = %s OR mt.status = %s)")
            params.extend([normalized_status, normalized_status])
    else:
        clauses.append("mo.status <> 'cancelada'")
        clauses.append("mt.status = 'ativo'")
    sql = _line_select_sql(" AND ".join(clauses)) + " LIMIT %s OFFSET %s"
    rows = db.execute(sql, (*params, int(limit), int(offset))).fetchall()
    return [dict(row) for row in rows]


def listar_linhas_horas_totais_voadas(
    db,
    *,
    competencia: str,
    funcao: str,
    org_id: str | None = None,
) -> list[dict]:
    resolved_org_id = _resolve_org_id(org_id)
    rows = db.execute(
        """
        WITH calculos_vigentes AS (
            SELECT
                ch.*,
                COUNT(*) OVER (
                    PARTITION BY ch.org_id, ch.missao_operacional_id, ch.tripulante_id, ch.funcao
                ) AS calculos_vigentes_count,
                ROW_NUMBER() OVER (
                    PARTITION BY ch.org_id, ch.missao_operacional_id, ch.tripulante_id, ch.funcao
                    ORDER BY ch.calculated_at DESC, ch.updated_at DESC, ch.created_at DESC, ch.id DESC
                ) AS rn
            FROM financeiro_calculos_horarios ch
            WHERE ch.org_id = %s
              AND ch.status <> 'obsoleto'
        )
        SELECT
            mt.id AS linha_id,
            mt.org_id AS linha_org_id,
            mt.status AS linha_status,
            mt.funcao AS linha_funcao,
            mt.tripulante_id AS linha_tripulante_id,
            mo.id AS missao_operacional_id,
            mo.org_id,
            mo.competencia,
            mo.data_missao,
            mo.data_final,
            mo.cavok_numero_voo,
            mo.chamado,
            mo.trecho,
            mo.status AS missao_status,
            mo.deleted_at AS missao_deleted_at,
            t.nome AS tripulante_nome,
            t.cpf AS tripulante_cpf,
            t.licenca_anac AS tripulante_licenca_anac,
            t.funcao_operacional AS tripulante_funcao_operacional,
            ch.id AS calculo_horario_id,
            ch.jornada_total_minutos,
            ch.minutos_diurnos,
            ch.minutos_noturnos,
            ch.minutos_noturnos_reais,
            ch.horas_noturnas_convertidas,
            ch.minutos_pre,
            ch.minutos_pos,
            ch.domingo_feriado,
            ch.valor_adicional_noturno,
            ch.valor_domingo_feriado_diurno,
            ch.valor_domingo_feriado_noturno,
            ch.valor_pre,
            ch.valor_pos,
            ch.total AS calculo_total,
            ch.memoria_calculo,
            ch.parametros_usados,
            ch.status AS calculo_status,
            ch.calculation_version,
            ch.calculated_at,
            COALESCE(ch.calculos_vigentes_count, 0) AS calculos_vigentes_count
        FROM financeiro_missao_tripulantes mt
        JOIN financeiro_missoes_operacionais mo
          ON mo.id = mt.missao_operacional_id
         AND mo.org_id = mt.org_id
        JOIN tripulantes t
          ON t.id = mt.tripulante_id
        LEFT JOIN calculos_vigentes ch
          ON ch.org_id = mt.org_id
         AND ch.missao_operacional_id = mt.missao_operacional_id
         AND ch.tripulante_id = mt.tripulante_id
         AND ch.funcao = mt.funcao
         AND ch.rn = 1
        WHERE mt.org_id = %s
          AND mo.competencia = %s
          AND mt.funcao = %s
          AND mt.status = 'ativo'
          AND mo.status <> 'cancelada'
          AND mo.deleted_at IS NULL
        ORDER BY t.nome ASC, mt.tripulante_id ASC, mo.data_missao ASC, mo.id ASC, mt.id ASC
        """,
        (resolved_org_id, resolved_org_id, competencia, funcao),
    ).fetchall()
    return [dict(row) for row in rows]


def contar_linhas_jornada(
    db,
    *,
    competencia: str,
    org_id: str | None = None,
    funcao: str | None = None,
    tripulante_id: int | None = None,
    status: str | None = None,
) -> int:
    resolved_org_id = _resolve_org_id(org_id)
    clauses = ["mt.org_id = %s", "mo.competencia = %s", "mo.deleted_at IS NULL"]
    params: list = [resolved_org_id, competencia]
    if funcao:
        clauses.append("mt.funcao = %s")
        params.append(funcao)
    if tripulante_id:
        clauses.append("mt.tripulante_id = %s")
        params.append(int(tripulante_id))
    if status:
        normalized_status = str(status).strip().lower()
        if normalized_status in {"cancelada", "cancelado"}:
            clauses.append("(mo.status = 'cancelada' OR mt.status = 'cancelado')")
        elif normalized_status in {"calculado", "recalculo_pendente", "obsoleto"}:
            clauses.append("ch.status = %s")
            params.append(normalized_status)
        else:
            clauses.append("(mo.status = %s OR mt.status = %s)")
            params.extend([normalized_status, normalized_status])
    else:
        clauses.append("mo.status <> 'cancelada'")
        clauses.append("mt.status = 'ativo'")
    row = db.execute(
        f"""
        SELECT COUNT(*) AS total
        FROM financeiro_missao_tripulantes mt
        JOIN financeiro_missoes_operacionais mo
          ON mo.id = mt.missao_operacional_id
         AND mo.org_id = mt.org_id
        LEFT JOIN financeiro_calculos_horarios ch
          ON ch.org_id = mt.org_id
         AND ch.missao_operacional_id = mt.missao_operacional_id
         AND ch.tripulante_id = mt.tripulante_id
         AND ch.funcao = mt.funcao
         AND ch.status <> 'obsoleto'
        WHERE {' AND '.join(clauses)}
        """,
        tuple(params),
    ).fetchone()
    return int(row["total"] or 0) if row else 0


def listar_linhas_jornada_periodo(
    db,
    *,
    data_inicio: str,
    data_fim: str,
    org_id: str | None = None,
    funcao: str | None = None,
    tripulante_id: int | None = None,
    status: str | None = None,
    limit: int = 1000,
    offset: int = 0,
) -> list[dict]:
    resolved_org_id = _resolve_org_id(org_id)
    clauses = [
        "mt.org_id = %s",
        "mo.data_missao <= %s",
        "COALESCE(mo.data_final, mo.data_missao) >= %s",
        "mo.deleted_at IS NULL",
    ]
    params: list = [resolved_org_id, data_fim, data_inicio]
    if funcao:
        clauses.append("mt.funcao = %s")
        params.append(funcao)
    if tripulante_id:
        clauses.append("mt.tripulante_id = %s")
        params.append(int(tripulante_id))
    if status:
        normalized_status = str(status).strip().lower()
        if normalized_status in {"cancelada", "cancelado"}:
            clauses.append("(mo.status = 'cancelada' OR mt.status = 'cancelado')")
        elif normalized_status in {"calculado", "recalculo_pendente", "obsoleto"}:
            clauses.append("ch.status = %s")
            params.append(normalized_status)
        else:
            clauses.append("(mo.status = %s OR mt.status = %s)")
            params.extend([normalized_status, normalized_status])
    else:
        clauses.append("mo.status <> 'cancelada'")
        clauses.append("mt.status = 'ativo'")
    sql = _line_select_sql(" AND ".join(clauses)) + " LIMIT %s OFFSET %s"
    rows = db.execute(sql, (*params, int(limit), int(offset))).fetchall()
    return [dict(row) for row in rows]


def contar_linhas_jornada_periodo(
    db,
    *,
    data_inicio: str,
    data_fim: str,
    org_id: str | None = None,
    funcao: str | None = None,
    tripulante_id: int | None = None,
    status: str | None = None,
) -> int:
    resolved_org_id = _resolve_org_id(org_id)
    clauses = [
        "mt.org_id = %s",
        "mo.data_missao <= %s",
        "COALESCE(mo.data_final, mo.data_missao) >= %s",
        "mo.deleted_at IS NULL",
    ]
    params: list = [resolved_org_id, data_fim, data_inicio]
    if funcao:
        clauses.append("mt.funcao = %s")
        params.append(funcao)
    if tripulante_id:
        clauses.append("mt.tripulante_id = %s")
        params.append(int(tripulante_id))
    if status:
        normalized_status = str(status).strip().lower()
        if normalized_status in {"cancelada", "cancelado"}:
            clauses.append("(mo.status = 'cancelada' OR mt.status = 'cancelado')")
        elif normalized_status in {"calculado", "recalculo_pendente", "obsoleto"}:
            clauses.append("ch.status = %s")
            params.append(normalized_status)
        else:
            clauses.append("(mo.status = %s OR mt.status = %s)")
            params.extend([normalized_status, normalized_status])
    else:
        clauses.append("mo.status <> 'cancelada'")
        clauses.append("mt.status = 'ativo'")
    row = db.execute(
        f"""
        SELECT COUNT(*) AS total
        FROM financeiro_missao_tripulantes mt
        JOIN financeiro_missoes_operacionais mo
          ON mo.id = mt.missao_operacional_id
         AND mo.org_id = mt.org_id
        LEFT JOIN financeiro_calculos_horarios ch
          ON ch.org_id = mt.org_id
         AND ch.missao_operacional_id = mt.missao_operacional_id
         AND ch.tripulante_id = mt.tripulante_id
         AND ch.funcao = mt.funcao
         AND ch.status <> 'obsoleto'
        WHERE {' AND '.join(clauses)}
        """,
        tuple(params),
    ).fetchone()
    return int(row["total"] or 0) if row else 0


def fetch_linha_jornada(db, *, linha_id: int, org_id: str | None = None) -> dict | None:
    resolved_org_id = _resolve_org_id(org_id)
    row = db.execute(
        _line_select_sql("mt.id = %s AND mt.org_id = %s AND mo.deleted_at IS NULL"),
        (int(linha_id), resolved_org_id),
    ).fetchone()
    return dict(row) if row else None


def listar_produtividade_jornada(
    db,
    *,
    competencia: str,
    org_id: str | None = None,
    funcao: str | None = None,
    tripulante_id: int | None = None,
) -> list[dict]:
    resolved_org_id = _resolve_org_id(org_id)
    clauses = ["cp.org_id = %s", "cp.competencia = %s", "cp.status <> 'obsoleto'"]
    params: list = [resolved_org_id, competencia]
    if funcao:
        clauses.append("cp.funcao = %s")
        params.append(funcao)
    if tripulante_id:
        clauses.append("cp.tripulante_id = %s")
        params.append(int(tripulante_id))
    rows = db.execute(
        f"""
        SELECT
            cp.*,
            t.nome AS tripulante_nome,
            t.cpf AS tripulante_cpf,
            t.licenca_anac AS tripulante_licenca_anac
        FROM financeiro_calculos_produtividade cp
        JOIN tripulantes t
          ON t.id = cp.tripulante_id
        WHERE {' AND '.join(clauses)}
        ORDER BY t.nome ASC, cp.tripulante_id ASC, cp.funcao ASC
        """,
        tuple(params),
    ).fetchall()
    return [dict(row) for row in rows]


def listar_feriados_por_datas(db, *, org_id: str | None = None, datas: list[str]) -> list[dict]:
    if not datas:
        return []
    resolved_org_id = _resolve_org_id(org_id)
    rows = db.execute(
        """
        SELECT data, nome, tipo
        FROM financeiro_feriados
        WHERE org_id = %s
          AND status = 'ativo'
          AND data::text = ANY(%s)
        """,
        (resolved_org_id, datas),
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_tripulante_basico(db, *, tripulante_id: int) -> dict | None:
    row = db.execute(
        """
        SELECT id, nome, cpf, licenca_anac, ativo, funcao_operacional, categoria_operacional
        FROM tripulantes
        WHERE id = %s
        """,
        (int(tripulante_id),),
    ).fetchone()
    return dict(row) if row else None


def fetch_equipamento_basico(db, *, aeronave_id: int) -> dict | None:
    row = db.execute(
        """
        SELECT id, nome, tipo, categoria_financeira, ativo
        FROM equipamentos
        WHERE id = %s
        """,
        (int(aeronave_id),),
    ).fetchone()
    return dict(row) if row else None
