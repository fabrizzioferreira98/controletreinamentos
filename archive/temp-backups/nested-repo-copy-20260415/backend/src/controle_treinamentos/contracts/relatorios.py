from __future__ import annotations

from decimal import Decimal

from ..core.utils import format_competencia_label


def _as_int(value) -> int:
    return int(value or 0)


def _as_float(value) -> float:
    if isinstance(value, Decimal):
        return float(value)
    return float(value or 0)


def serialize_habilitacoes_report(context: dict) -> dict:
    summary = context.get("summary", {})
    filtros = context.get("filtros", {})
    return {
        "summary": {
            "total_tripulantes": _as_int(summary.get("total_tripulantes")),
            "total_habilitacoes": _as_int(summary.get("total_habilitacoes")),
            "total_em_dia": _as_int(summary.get("total_em_dia")),
            "total_vencer_90": _as_int(summary.get("total_vencer_90")),
            "total_vencer_60": _as_int(summary.get("total_vencer_60")),
            "total_vencer_30": _as_int(summary.get("total_vencer_30")),
            "total_critico_15": _as_int(summary.get("total_critico_15")),
            "total_vencido": _as_int(summary.get("total_vencido")),
        },
        "filters": {
            "nome": filtros.get("nome") or "",
            "base": filtros.get("base") or "",
            "status": filtros.get("status") or "",
            "tipo": filtros.get("tipo") or "",
            "ordenacao": filtros.get("ordenacao") or "criticidade",
        },
        "options": {
            "status": list(context.get("status_options", [])),
            "tipos": [
                {
                    "id": int(item["id"]),
                    "nome": item.get("nome") or "",
                }
                for item in context.get("tipo_options", [])
            ],
            "bases": [
                {
                    "nome": item.get("nome") or "",
                }
                for item in context.get("base_options", [])
            ],
        },
        "items": [
            {
                "tripulante_id": int(group["tripulante_id"]),
                "tripulante_nome": group.get("tripulante_nome") or "",
                "base": group.get("base") or "",
                "funcao_cargo": group.get("funcao_cargo") or "",
                "habilitacoes": [
                    {
                        "treinamento_id": item.get("treinamento_id"),
                        "tipo_treinamento_id": item.get("tipo_treinamento_id"),
                        "habilitacao_nome": item.get("habilitacao_nome") or "",
                        "data_vencimento": item.get("data_vencimento") or "",
                        "days_remaining": item.get("days_remaining"),
                        "days_remaining_label": item.get("days_remaining_label") or "",
                        "status_key": item.get("status_key") or "",
                        "status_label": item.get("status_label") or "",
                        "pulse": bool(item.get("pulse")),
                        "is_placeholder": bool(item.get("is_placeholder")),
                    }
                    for item in group.get("habilitacoes", [])
                ],
            }
            for group in context.get("tripulantes_grouped", [])
        ],
    }


def serialize_produtividade_report(
    *,
    competencia: str,
    summary: dict,
    rows: list[dict],
    filtros: dict,
    competencias_disponiveis: list[str],
    bases: list[str],
    funcoes: list,
    categorias: list,
    emitted_at: str,
) -> dict:
    return {
        "competencia": competencia,
        "competencia_label": format_competencia_label(competencia),
        "emitted_at": emitted_at,
        "filters": {
            "nome": filtros.get("nome") or "",
            "base": filtros.get("base") or "",
            "funcao": filtros.get("funcao") or "",
            "categoria": filtros.get("categoria") or "",
            "ordenacao": filtros.get("ordenacao") or "valor_final",
        },
        "options": {
            "competencias": list(competencias_disponiveis),
            "bases": list(bases),
            "funcoes": list(funcoes),
            "categorias": list(categorias),
        },
        "summary": {
            key: _as_float(value)
            for key, value in summary.items()
        },
        "items": [
            {
                "tripulante_id": int(row["tripulante_id"]),
                "tripulante_nome": row.get("tripulante_nome") or "",
                "base": row.get("base") or "",
                "categoria": row.get("categoria") or "",
                "funcao": row.get("funcao") or "",
                "total_missoes_validas": _as_int(row.get("total_missoes_validas")),
                "total_pernoites": _as_int(row.get("total_pernoites_cobertura"))
                + _as_int(row.get("total_pernoites_operacionais_elegiveis")),
                "piso_minimo_mensal": _as_float(row.get("piso_minimo_mensal")),
                "total_produtividade": _as_float(row.get("total_produtividade")),
                "valor_final_mes": _as_float(row.get("valor_final_mes")),
                "criterio_fechamento": row.get("criterio_fechamento") or "",
                "conferencia": serialize_produtividade_conferencia(row.get("conferencia")),
            }
            for row in rows
        ],
    }


def serialize_produtividade_conferencia(row: dict | None) -> dict | None:
    if not row:
        return None
    return {
        "tripulante_id": int(row["tripulante_id"]),
        "competencia": row.get("competencia") or "",
        "conferido_por": row.get("conferido_por"),
        "conferido_por_nome": row.get("conferido_por_nome") or "",
        "conferido_em": row.get("conferido_em"),
    }
