from __future__ import annotations

from datetime import timedelta
from typing import Any

from ..constants import DEFAULT_PAGE_SIZE
from ..core.http_utils import build_pagination, normalize_page
from ..db import get_db
from ..repositories.dashboard_cache import fetch_cached_rows
from ..repositories.treinamentos import (
    get_treinamento_for_edit,
    get_treinamentos_summary,
    list_treinamentos_ssr_page,
)
from ..service_layers.form_options import get_training_form_options


class TreinamentoSsrNotFoundError(LookupError):
    pass


def _parse_page(page: int | str | None) -> int:
    try:
        parsed = int(str(page or "1").strip())
    except ValueError:
        return 1
    return max(1, parsed)


def _build_filter_state(raw_filters: dict[str, str], *, today) -> dict[str, Any]:
    tripulante = (raw_filters.get("tripulante") or "").strip()
    equipamento = (raw_filters.get("equipamento") or "").strip()
    tipo = (raw_filters.get("tipo") or "").strip()
    status = (raw_filters.get("status") or "").strip()
    periodo = (raw_filters.get("periodo") or "").strip()

    clauses: list[str] = []
    params: list[Any] = []
    flash_messages: list[tuple[str, str]] = []

    if tripulante:
        if not tripulante.isdigit():
            flash_messages.append(("Filtro de tripulante inválido.", "error"))
            tripulante = ""
        else:
            clauses.append("c.id = %s")
            params.append(int(tripulante))
    if equipamento:
        if not equipamento.isdigit():
            flash_messages.append(("Filtro de equipamento inválido.", "error"))
            equipamento = ""
        else:
            clauses.append("e.id = %s")
            params.append(int(equipamento))
    if tipo:
        if not tipo.isdigit():
            flash_messages.append(("Filtro de tipo inválido.", "error"))
            tipo = ""
        else:
            clauses.append("tt.id = %s")
            params.append(int(tipo))

    if periodo == "7":
        clauses.append("t.data_vencimento IS NOT NULL AND t.data_vencimento BETWEEN %s AND %s")
        params.extend([today, today + timedelta(days=7)])
    elif periodo == "30":
        clauses.append("t.data_vencimento IS NOT NULL AND t.data_vencimento BETWEEN %s AND %s")
        params.extend([today, today + timedelta(days=30)])
    elif periodo == "60":
        clauses.append("t.data_vencimento IS NOT NULL AND t.data_vencimento BETWEEN %s AND %s")
        params.extend([today, today + timedelta(days=60)])
    elif periodo == "90":
        clauses.append("t.data_vencimento IS NOT NULL AND t.data_vencimento BETWEEN %s AND %s")
        params.extend([today, today + timedelta(days=90)])
    elif periodo == "expired":
        clauses.append("t.data_vencimento IS NOT NULL AND t.data_vencimento < %s")
        params.append(today)

    if status in {"vencido", "a vencer", "regular", "sem informação"}:
        if status == "sem informação":
            clauses.append("t.data_vencimento IS NULL")
        elif status == "vencido":
            clauses.append("t.data_vencimento < %s")
            params.append(today)
        elif status == "a vencer":
            clauses.append("t.data_vencimento >= %s AND t.data_vencimento <= %s")
            params.extend([today, today + timedelta(days=30)])
        elif status == "regular":
            clauses.append("t.data_vencimento > %s")
            params.append(today + timedelta(days=30))

    filters = {
        "tripulante": tripulante,
        "equipamento": equipamento,
        "tipo": tipo,
        "status": status,
        "periodo": periodo,
    }
    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return {
        "filters": filters,
        "where_clause": where_clause,
        "params": tuple(params),
        "flash_messages": flash_messages,
    }


def _pagination_state(*, total: int, page: int | str | None, filters: dict[str, str]) -> dict[str, Any]:
    normalized_page = normalize_page(_parse_page(page), DEFAULT_PAGE_SIZE, total)
    return {
        "page": normalized_page,
        "per_page": DEFAULT_PAGE_SIZE,
        "offset": (normalized_page - 1) * DEFAULT_PAGE_SIZE,
        "pagination": build_pagination(
            "cadastros.treinamentos_list",
            normalized_page,
            DEFAULT_PAGE_SIZE,
            total,
            **filters,
        ),
    }


def get_treinamentos_list_context(*, raw_filters: dict[str, str], page: int | str | None, today) -> dict[str, Any]:
    db = get_db()
    filter_state = _build_filter_state(raw_filters, today=today)
    resumo_row = get_treinamentos_summary(
        db,
        where_clause=filter_state["where_clause"],
        params=filter_state["params"],
        today=today,
    )
    total = resumo_row["total"]
    paging = _pagination_state(total=total, page=page, filters=filter_state["filters"])
    treinamentos = list_treinamentos_ssr_page(
        db,
        where_clause=filter_state["where_clause"],
        params=filter_state["params"],
        limit=paging["per_page"],
        offset=paging["offset"],
    )

    return {
        "flash_messages": filter_state["flash_messages"],
        "context": {
            "treinamentos": treinamentos,
            "resumo": {
                "total": resumo_row["total"],
                "vencido": resumo_row["vencido"],
                "a vencer": resumo_row["a_vencer"],
                "regular": resumo_row["regular"],
                "sem informação": resumo_row["sem_informacao"],
            },
            "filtros": filter_state["filters"],
            "tripulantes": fetch_cached_rows(
                db,
                cache_key="options:tripulantes:id_nome",
                query="SELECT id, nome FROM tripulantes ORDER BY nome",
            ),
            "equipamentos": fetch_cached_rows(
                db,
                cache_key="options:equipamentos:id_nome",
                query="SELECT id, nome FROM equipamentos ORDER BY nome",
            ),
            "tipos": fetch_cached_rows(
                db,
                cache_key="options:tipos_treinamento:id_nome",
                query="SELECT id, nome FROM tipos_treinamento ORDER BY nome",
            ),
            "pagination": paging["pagination"],
        },
    }


def get_treinamento_edit_context(*, treinamento_id: int) -> dict[str, Any]:
    db = get_db()
    treinamento = get_treinamento_for_edit(db, treinamento_id=treinamento_id)
    if not treinamento:
        raise TreinamentoSsrNotFoundError("Treinamento não encontrado.")
    options = get_training_form_options(
        db,
        treinamento_id=treinamento_id,
        selected_equipment_id=treinamento.get("equipamento_id"),
        selected_tipo_id=treinamento.get("tipo_treinamento_id"),
    )
    return {"treinamento": treinamento, "options": options}
