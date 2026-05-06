from __future__ import annotations

import json

from ..contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT
from ..repositories.financeiro_calculos_horarios import listar_calculos_horarios as _listar_calculos_horarios_legacy
from ..repositories.financeiro_calculos_produtividade import (
    listar_calculos_produtividade as _listar_calculos_produtividade_legacy,
    listar_participacoes_produtividade_por_competencia as _listar_participacoes_produtividade_legacy,
)
from ..repositories.financeiro_lancamentos_jornada import (
    contar_linhas_jornada,
    contar_linhas_jornada_periodo,
    fetch_equipamento_basico,
    fetch_linha_jornada,
    fetch_tripulante_basico,
    listar_feriados_por_datas,
    listar_linhas_jornada,
    listar_linhas_jornada_periodo,
    listar_produtividade_jornada,
)
from ..repositories.tripulantes import fetch_tripulante_detail


def _resolve_org_id(org_id: str | None) -> str:
    return (org_id or "").strip() or FINANCE_ORG_SCOPE_DEFAULT


def _text(value, default: str = "") -> str:
    return str(value or "").strip() or default


def _json_value(value, fallback):
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def consultar_linhas_jornada(
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
    return listar_linhas_jornada(
        db,
        competencia=competencia,
        org_id=_resolve_org_id(org_id),
        funcao=funcao,
        tripulante_id=tripulante_id,
        status=status,
        limit=limit,
        offset=offset,
    )


def contar_linhas_jornada_recorte(
    db,
    *,
    competencia: str,
    org_id: str | None = None,
    funcao: str | None = None,
    tripulante_id: int | None = None,
    status: str | None = None,
) -> int:
    return contar_linhas_jornada(
        db,
        competencia=competencia,
        org_id=_resolve_org_id(org_id),
        funcao=funcao,
        tripulante_id=tripulante_id,
        status=status,
    )


def consultar_linhas_jornada_periodo(
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
    return listar_linhas_jornada_periodo(
        db,
        data_inicio=data_inicio,
        data_fim=data_fim,
        org_id=_resolve_org_id(org_id),
        funcao=funcao,
        tripulante_id=tripulante_id,
        status=status,
        limit=limit,
        offset=offset,
    )


def contar_linhas_jornada_periodo_recorte(
    db,
    *,
    data_inicio: str,
    data_fim: str,
    org_id: str | None = None,
    funcao: str | None = None,
    tripulante_id: int | None = None,
    status: str | None = None,
) -> int:
    return contar_linhas_jornada_periodo(
        db,
        data_inicio=data_inicio,
        data_fim=data_fim,
        org_id=_resolve_org_id(org_id),
        funcao=funcao,
        tripulante_id=tripulante_id,
        status=status,
    )


def consultar_produtividade_jornada(
    db,
    *,
    competencia: str,
    org_id: str | None = None,
    funcao: str | None = None,
    tripulante_id: int | None = None,
) -> list[dict]:
    return listar_produtividade_jornada(
        db,
        competencia=competencia,
        org_id=_resolve_org_id(org_id),
        funcao=funcao,
        tripulante_id=tripulante_id,
    )


def consultar_feriados_jornada(db, *, org_id: str | None = None, datas: list[str]) -> list[dict]:
    return listar_feriados_por_datas(db, org_id=_resolve_org_id(org_id), datas=datas)


def consultar_linha_jornada(db, *, linha_id: int, org_id: str | None = None) -> dict | None:
    return fetch_linha_jornada(db, linha_id=int(linha_id), org_id=_resolve_org_id(org_id))


def consultar_tripulante_basico(db, *, tripulante_id: int) -> dict | None:
    return fetch_tripulante_basico(db, tripulante_id=int(tripulante_id))


def consultar_equipamento_basico(db, *, aeronave_id: int) -> dict | None:
    return fetch_equipamento_basico(db, aeronave_id=int(aeronave_id))


def _row_to_hourly_calculation(row: dict) -> dict:
    status = _text(row.get("calculo_status"), "recalculo_pendente")
    memoria = _json_value(row.get("memoria_calculo"), {})
    if not row.get("calculo_horario_id"):
        memoria = {
            **(memoria if isinstance(memoria, dict) else {}),
            "warnings": [
                {
                    "code": "calculation_pending",
                    "message": "Linha salva na grade, ainda sem calculo horario vigente.",
                }
            ],
        }
    return {
        "id": row.get("calculo_horario_id") or 0,
        "org_id": row.get("org_id") or row.get("linha_org_id") or FINANCE_ORG_SCOPE_DEFAULT,
        "missao_operacional_id": row.get("missao_operacional_id"),
        "tripulante_id": row.get("linha_tripulante_id"),
        "tripulante_nome": row.get("tripulante_nome"),
        "tripulante_cpf": row.get("tripulante_cpf"),
        "tripulante_licenca_anac": row.get("tripulante_licenca_anac"),
        "funcao": row.get("linha_funcao"),
        "competencia": row.get("competencia"),
        "data_missao": row.get("data_missao"),
        "data_final": row.get("data_final") or row.get("data_missao"),
        "cavok_numero_voo": row.get("cavok_numero_voo"),
        "contratante": row.get("contratante"),
        "chamado": row.get("chamado"),
        "aeronave_id": row.get("aeronave_id"),
        "aeronave_nome": row.get("aeronave_nome"),
        "categoria_financeira_aeronave": row.get("categoria_financeira_aeronave"),
        "horario_apresentacao": row.get("horario_apresentacao"),
        "horario_abandono": row.get("horario_abandono"),
        "pos_exec_min": row.get("pos_exec_min") or 0,
        "trecho": row.get("trecho"),
        "houve_pernoite": row.get("houve_pernoite"),
        "quantidade_pernoites": row.get("quantidade_pernoites") or 0,
        "cobertura_base": row.get("cobertura_base"),
        "operacao_especial": row.get("operacao_especial"),
        "justificativa": row.get("justificativa"),
        "missao_status": row.get("missao_status"),
        "jornada_total_minutos": row.get("jornada_total_minutos") or 0,
        "minutos_diurnos": row.get("minutos_diurnos") or 0,
        "minutos_noturnos": row.get("minutos_noturnos") or row.get("minutos_noturnos_reais") or 0,
        "minutos_noturnos_reais": row.get("minutos_noturnos_reais") or row.get("minutos_noturnos") or 0,
        "horas_noturnas_convertidas": row.get("horas_noturnas_convertidas") or 0,
        "minutos_pre": row.get("minutos_pre") or 0,
        "minutos_pos": row.get("minutos_pos") or 0,
        "domingo_feriado": bool(row.get("domingo_feriado")),
        "valor_adicional_noturno": row.get("valor_adicional_noturno") or 0,
        "valor_domingo_feriado_diurno": row.get("valor_domingo_feriado_diurno") or 0,
        "valor_domingo_feriado_noturno": row.get("valor_domingo_feriado_noturno") or 0,
        "valor_pre": row.get("valor_pre") or 0,
        "valor_pos": row.get("valor_pos") or 0,
        "total": row.get("calculo_total") or 0,
        "memoria_calculo": memoria,
        "parametros_usados": _json_value(row.get("parametros_usados"), []),
        "calculation_version": row.get("calculation_version"),
        "calculated_at": row.get("calculated_at"),
        "status": status,
        "fonte_calculo": "financeiro_jornada_query",
    }


def consultar_calculos_horarios_jornada(
    db,
    *,
    org_id: str | None = None,
    competencia: str | None = None,
    missao_operacional_id: int | None = None,
    tripulante_id: int | None = None,
    funcao: str | None = None,
    status: str | None = None,
    incluir_obsoletos: bool = False,
    limit: int = 1000,
    offset: int = 0,
) -> list[dict]:
    normalized_status = _text(status).lower() or None
    if incluir_obsoletos or normalized_status == "obsoleto" or missao_operacional_id is not None:
        return _listar_calculos_horarios_legacy(
            db,
            org_id=org_id,
            competencia=competencia,
            missao_operacional_id=missao_operacional_id,
            tripulante_id=tripulante_id,
            funcao=funcao,
            status=status,
            limit=limit,
            offset=offset,
        )
    rows = consultar_linhas_jornada(
        db,
        competencia=competencia or "",
        org_id=org_id,
        funcao=funcao,
        tripulante_id=tripulante_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return [_row_to_hourly_calculation(row) for row in rows]


def consultar_calculos_produtividade_jornada(
    db,
    *,
    org_id: str | None = None,
    competencia: str | None = None,
    tripulante_id: int | None = None,
    funcao: str | None = None,
    status: str | None = None,
    incluir_obsoletos: bool = False,
    limit: int = 1000,
    offset: int = 0,
) -> list[dict]:
    normalized_status = _text(status).lower() or None
    if incluir_obsoletos or normalized_status == "obsoleto":
        return _listar_calculos_produtividade_legacy(
            db,
            org_id=org_id,
            competencia=competencia,
            tripulante_id=tripulante_id,
            funcao=funcao,
            status=status,
            limit=limit,
            offset=offset,
        )
    rows = consultar_produtividade_jornada(
        db,
        competencia=competencia or "",
        org_id=org_id,
        funcao=funcao,
        tripulante_id=tripulante_id,
    )
    if normalized_status:
        rows = [row for row in rows if _text(row.get("status")).lower() == normalized_status]
    return rows[offset : offset + limit]


def consultar_participacoes_produtividade_jornada(
    db,
    *,
    competencia: str,
    org_id: str | None = None,
    tripulante_id: int | None = None,
    funcao: str | None = None,
) -> list[dict]:
    rows = _listar_participacoes_produtividade_legacy(db, competencia=competencia, org_id=_resolve_org_id(org_id))
    return [
        row
        for row in rows
        if (tripulante_id is None or int(row.get("tripulante_id") or 0) == int(tripulante_id))
        and (not funcao or _text(row.get("funcao")) == funcao)
    ]


def consultar_tripulante_relatorio(db, *, tripulante_id: int) -> dict | None:
    return fetch_tripulante_detail(db, tripulante_id=int(tripulante_id))
