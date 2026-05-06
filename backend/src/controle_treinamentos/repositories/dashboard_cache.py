from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, timedelta

from ..constants import (
    CONSOLIDATED_STATUS_FILTERS,
    DASHBOARD_CACHE_TTL_SECONDS,
    OPTIONS_CACHE_TTL_SECONDS,
    PANEL_CACHE_TTL_SECONDS,
    PT_BR_MONTHS,
    PT_BR_WEEKDAYS,
)
from ..core.cache_service import cache_service
from ..core.utils import days_remaining_label, normalize_consolidated_sort, normalize_consolidated_status
from ..db import fetch_unique_bases
from ..services import (
    EXPIRY_STATUS_META,
    build_expiry_status,
    business_today,
    calculate_training_status,
    parse_date,
    status_color,
)


def fetch_cached_rows(db, *, cache_key: str, query: str, params: tuple = ()) -> list[dict]:
    cached = get_panel_cache(cache_key)
    if cached is not None:
        return [dict(row) for row in cached]
    rows = db.execute(query, params).fetchall()
    payload = [dict(row) for row in rows]
    set_panel_cache(cache_key, payload, ttl_seconds=OPTIONS_CACHE_TTL_SECONDS)
    return [dict(row) for row in payload]


def _operational_base_expr(*, trip_alias: str = "c", base_alias: str = "pb") -> str:
    return f"{base_alias}.nome"


def _base_habilitacoes_query_filters(*, nome: str, base: str, tipo: str):
    clauses = []
    params = []

    if nome:
        clauses.append("LOWER(c.nome) LIKE %s")
        params.append(f"%{nome.lower()}%")
    if base:
        clauses.append(f"LOWER({_operational_base_expr(trip_alias='c', base_alias='pb')}) = LOWER(%s)")
        params.append(base)
    if tipo:
        if tipo.isdigit():
            tipo = str(int(tipo))
        else:
            tipo = ""

    return tipo, clauses, params


def _append_habilitacoes_status_filter(
    clauses: list[str],
    params: list,
    *,
    normalized_status: str,
    today: date,
    status_window_15: date,
    status_window_30: date,
    status_window_60: date,
    status_window_90: date,
) -> None:
    if normalized_status == "sem_vencimento":
        clauses.append("t.data_vencimento IS NULL")
    elif normalized_status == "vencido":
        clauses.append("t.data_vencimento IS NOT NULL AND t.data_vencimento < %s")
        params.append(today)
    elif normalized_status == "critico_15":
        clauses.append("t.data_vencimento >= %s AND t.data_vencimento <= %s")
        params.extend([today, status_window_15])
    elif normalized_status == "vencer_30":
        clauses.append("t.data_vencimento > %s AND t.data_vencimento <= %s")
        params.extend([status_window_15, status_window_30])
    elif normalized_status == "vencer_60":
        clauses.append("t.data_vencimento > %s AND t.data_vencimento <= %s")
        params.extend([status_window_30, status_window_60])
    elif normalized_status == "vencer_90":
        clauses.append("t.data_vencimento > %s AND t.data_vencimento <= %s")
        params.extend([status_window_60, status_window_90])
    elif normalized_status == "em_dia":
        clauses.append("t.data_vencimento > %s")
        params.append(status_window_90)

def build_habilitacoes_consolidadas_context(db, *, nome: str, base: str, status: str, tipo: str, ordenacao: str):
    normalized_status = normalize_consolidated_status(status)
    normalized_sort = normalize_consolidated_sort(ordenacao)
    normalized_tipo, tripulante_clauses, tripulante_params = _base_habilitacoes_query_filters(
        nome=nome,
        base=base,
        tipo=tipo,
    )
    today = business_today()
    status_window_15 = today + timedelta(days=15)
    status_window_30 = today + timedelta(days=30)
    status_window_60 = today + timedelta(days=60)
    status_window_90 = today + timedelta(days=90)

    tripulante_where = f"WHERE {' AND '.join(tripulante_clauses)}" if tripulante_clauses else ""

    tripulante_rows = db.execute(
        f"""
        SELECT
            c.id AS tripulante_id,
            c.nome AS tripulante_nome,
            pb.nome AS tripulante_base,
            NULL::TEXT AS tripulante_cargo
        FROM tripulantes c
        LEFT JOIN pilotos p ON p.tripulante_id = c.id
        LEFT JOIN bases pb ON pb.id = p.base_id
        {tripulante_where}
        """,
        tuple(tripulante_params),
    ).fetchall()

    grouped: dict[int, dict] = {}
    summary = {
        "total_tripulantes": 0,
        "total_habilitacoes": 0,
        "total_em_dia": 0,
        "total_vencer_90": 0,
        "total_vencer_60": 0,
        "total_vencer_30": 0,
        "total_critico_15": 0,
        "total_vencido": 0,
    }

    for row in tripulante_rows:
        tripulante_id = row["tripulante_id"]
        grouped[tripulante_id] = {
            "tripulante_id": tripulante_id,
            "tripulante_nome": row["tripulante_nome"],
            "base": row["tripulante_base"],
            "funcao_cargo": row["tripulante_cargo"],
            "habilitacoes": [],
            "has_habilitacoes": False,
            "sort_priority": 99,
            "sort_due_date": date.max,
        }

    training_rows = []
    if grouped:
        training_clauses = ["t.tripulante_id = ANY(%s)"]
        training_params = [[*grouped.keys()]]
        if normalized_tipo:
            training_clauses.append("t.tipo_treinamento_id = %s")
            training_params.append(int(normalized_tipo))
        _append_habilitacoes_status_filter(
            training_clauses,
            training_params,
            normalized_status=normalized_status,
            today=today,
            status_window_15=status_window_15,
            status_window_30=status_window_30,
            status_window_60=status_window_60,
            status_window_90=status_window_90,
        )
        training_where = f"WHERE {' AND '.join(training_clauses)}"
        training_rows = db.execute(
            f"""
            SELECT
                t.tripulante_id,
                t.id AS treinamento_id,
                t.tipo_treinamento_id,
                tt.nome AS habilitacao_nome,
                t.data_vencimento
            FROM treinamentos t
            JOIN tipos_treinamento tt ON tt.id = t.tipo_treinamento_id
            {training_where}
            """,
            tuple(training_params),
        ).fetchall()

    for row in training_rows:
        group = grouped.get(row["tripulante_id"])
        if group is None:
            continue

        expiry = build_expiry_status(row["data_vencimento"], reference=today)
        item = {
            "treinamento_id": row["treinamento_id"],
            "tipo_treinamento_id": row["tipo_treinamento_id"],
            "habilitacao_nome": row["habilitacao_nome"] or "Habilitação não identificada",
            "data_vencimento": expiry["due_date_label"] or "Sem vencimento informado",
            "days_remaining": expiry["days_remaining"],
            "days_remaining_label": days_remaining_label(expiry["days_remaining"]),
            "status_key": expiry["key"],
            "status_label": expiry["label"],
            "pulse": bool(expiry["pulse"]),
            "priority": expiry["priority"],
            "sort_due_date": expiry["sort_due_date"],
        }
        group["habilitacoes"].append(item)
        group["has_habilitacoes"] = True
        group["sort_priority"] = min(group["sort_priority"], item["priority"])
        group["sort_due_date"] = min(group["sort_due_date"], item["sort_due_date"])

        summary["total_habilitacoes"] += 1
        status_key = item["status_key"]
        if status_key == "em_dia":
            summary["total_em_dia"] += 1
        elif status_key == "vencer_90":
            summary["total_vencer_90"] += 1
        elif status_key == "vencer_60":
            summary["total_vencer_60"] += 1
        elif status_key == "vencer_30":
            summary["total_vencer_30"] += 1
        elif status_key == "critico_15":
            summary["total_critico_15"] += 1
        elif status_key == "vencido":
            summary["total_vencido"] += 1

    visible_groups = []
    for group in grouped.values():
        if group["habilitacoes"]:
            if normalized_sort == "vencimento":
                group["habilitacoes"].sort(key=lambda item: (item["sort_due_date"], item["priority"], item["habilitacao_nome"]))
            else:
                group["habilitacoes"].sort(key=lambda item: (item["priority"], item["sort_due_date"], item["habilitacao_nome"]))
            visible_groups.append(group)
            continue

        if not (normalized_status or normalized_tipo):
            visible_groups.append(group)

    if normalized_sort == "vencimento":
        visible_groups.sort(key=lambda group: (group["sort_due_date"], group["sort_priority"], group["tripulante_nome"].lower()))
    else:
        visible_groups.sort(key=lambda group: (group["sort_priority"], group["sort_due_date"], group["tripulante_nome"].lower()))

    summary["total_tripulantes"] = len(visible_groups)

    status_options = [EXPIRY_STATUS_META[key] for key in CONSOLIDATED_STATUS_FILTERS]
    tipo_options = fetch_cached_rows(
        db,
        cache_key="options:tipos_treinamento:id_nome",
        query="SELECT id, nome FROM tipos_treinamento ORDER BY nome",
    )
    base_options_cache_key = "options:bases:unique"
    base_options = get_panel_cache(base_options_cache_key)
    if base_options is None:
        base_options = [dict(row) for row in fetch_unique_bases(db)]
        set_panel_cache(base_options_cache_key, base_options, ttl_seconds=OPTIONS_CACHE_TTL_SECONDS)

    return {
        "tripulantes_grouped": visible_groups,
        "summary": summary,
        "status_options": status_options,
        "tipo_options": tipo_options,
        "base_options": base_options,
        "filtros": {
            "nome": nome,
            "base": base,
            "status": normalized_status,
            "tipo": normalized_tipo,
            "ordenacao": normalized_sort,
        },
    }

def get_panel_cache(cache_key: str):
    return cache_service.get_panel_cache(cache_key, default_ttl_seconds=PANEL_CACHE_TTL_SECONDS)

def set_panel_cache(cache_key: str, payload, *, ttl_seconds: int | None = None):
    effective_ttl = ttl_seconds if ttl_seconds is not None else PANEL_CACHE_TTL_SECONDS
    cache_service.set_panel_cache(cache_key, payload, ttl_seconds=effective_ttl)

def clear_navigation_cache():
    cache_service.clear_navigation_cache()

def clear_dashboard_cache():
    cache_service.clear_dashboard_cache()

def clear_panel_cache(prefix: str | None = None, *, invalidate_global: bool = True):
    cache_service.clear_panel_cache(prefix, invalidate_global=invalidate_global)

def clear_catalog_options_cache():
    cache_service.clear_catalog_options_cache()

def get_dashboard_cache():
    return cache_service.get_dashboard_cache(ttl_seconds=DASHBOARD_CACHE_TTL_SECONDS)

def set_dashboard_cache(payload: dict):
    cache_service.set_dashboard_cache(payload)


def _fetch_dashboard_critical_rows(db, *, limit: int = 8):
    today = business_today()
    rows = db.execute(
        """
        SELECT
            t.*,
            c.nome AS tripulante_nome,
            e.nome AS equipamento_nome,
            tt.nome AS tipo_treinamento_nome,
            CASE
                WHEN t.data_vencimento IS NULL THEN 'sem informação'
                WHEN t.data_vencimento < %s THEN 'vencido'
                WHEN t.data_vencimento <= %s THEN 'a vencer'
                ELSE 'regular'
            END AS status_calculado
        FROM treinamentos t
        JOIN tripulantes c ON c.id = t.tripulante_id
        LEFT JOIN equipamentos e ON e.id = t.equipamento_id
        JOIN tipos_treinamento tt ON tt.id = t.tipo_treinamento_id
        ORDER BY
            CASE
                WHEN t.data_vencimento IS NULL THEN 3
                WHEN t.data_vencimento < %s THEN 0
                WHEN t.data_vencimento <= %s THEN 1
                ELSE 2
            END,
            t.data_vencimento NULLS LAST,
            tt.nome,
            c.nome
        LIMIT %s
        """,
        (today, today + timedelta(days=30), today, today + timedelta(days=30), limit),
    ).fetchall()
    payload = []
    for row in rows:
        item = dict(row)
        item["status_class"] = status_color(item["status_calculado"])
        payload.append(item)
    return payload

def build_dashboard_context(db):
    today = business_today()
    summary_row = db.execute(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE data_vencimento IS NULL) AS sem_informacao,
            COUNT(*) FILTER (WHERE data_vencimento < %s) AS vencido,
            COUNT(*) FILTER (
                WHERE data_vencimento >= %s
                  AND data_vencimento <= %s
            ) AS a_vencer,
            COUNT(*) FILTER (WHERE data_vencimento > %s) AS regular,
            COUNT(*) FILTER (WHERE data_vencimento = %s) AS vencem_hoje,
            COUNT(*) FILTER (
                WHERE data_vencimento >= %s
                  AND data_vencimento <= %s
            ) AS em_7_dias
        FROM treinamentos
        """,
        (today, today, today + timedelta(days=30), today + timedelta(days=30), today, today, today + timedelta(days=7)),
    ).fetchone()

    critical_rows = _fetch_dashboard_critical_rows(db, limit=8)
    summary = {
        "total": summary_row["total"],
        "vencido": summary_row["vencido"],
        "a vencer": summary_row["a_vencer"],
        "regular": summary_row["regular"],
        "sem informação": summary_row["sem_informacao"],
    }
    calendar_context = build_dashboard_calendar(db, today)
    totals_row = db.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM tripulantes) AS tripulantes,
            (SELECT COUNT(*) FROM equipamentos WHERE ativo = 1) AS equipamentos,
            (SELECT COUNT(*) FROM tipos_treinamento WHERE ativo = 1) AS tipos
        """
    ).fetchone()

    return {
        "totals": {
            "tripulantes": totals_row["tripulantes"],
            "equipamentos": totals_row["equipamentos"],
            "tipos": totals_row["tipos"],
            "treinamentos": summary_row["total"],
        },
        "summary": summary,
        "alerts": {
            "vencidos": summary["vencido"],
            "vencem_hoje": summary_row["vencem_hoje"],
            "em_7_dias": summary_row["em_7_dias"],
            "em_30_dias": summary["a vencer"],
        },
        "calendar": calendar_context,
        "critical_rows": critical_rows,
    }

def build_dashboard_calendar(db, today: date | None = None):
    reference = today or business_today()

    first_day = reference.replace(day=1)
    _, days_in_month = monthrange(reference.year, reference.month)
    last_day = reference.replace(day=days_in_month)
    grid_start = first_day - timedelta(days=first_day.weekday())
    grid_end = last_day + timedelta(days=(6 - last_day.weekday()))

    rows = db.execute(
        """
        SELECT
            t.id,
            t.tripulante_id,
            t.data_vencimento,
            c.nome AS tripulante_nome,
            e.nome AS equipamento_nome,
            tt.nome AS tipo_treinamento_nome
        FROM treinamentos t
        JOIN tripulantes c ON c.id = t.tripulante_id
        LEFT JOIN equipamentos e ON e.id = t.equipamento_id
        JOIN tipos_treinamento tt ON tt.id = t.tipo_treinamento_id
        WHERE t.data_vencimento IS NOT NULL
          AND t.data_vencimento BETWEEN %s AND %s
        ORDER BY t.data_vencimento, c.nome, tt.nome
        """,
        (grid_start, grid_end),
    ).fetchall()

    items_by_date = defaultdict(list)
    upcoming_rows = []
    for row in rows:
        due_date = parse_date(row["data_vencimento"])
        if due_date is None:
            continue
        status = calculate_training_status(due_date, reference)
        item = {
            "training_id": row["id"],
            "tripulante_id": row["tripulante_id"],
            "tripulante_nome": row["tripulante_nome"],
            "equipamento_nome": row["equipamento_nome"] or "Sem equipamento",
            "tipo_treinamento_nome": row["tipo_treinamento_nome"],
            "data_vencimento": due_date.strftime("%d/%m/%Y"),
            "status": status,
            "status_class": status_color(status),
            "training_url": "",
            "tripulante_url": "",
        }
        items_by_date[due_date].append(item)
        if due_date >= reference and len(upcoming_rows) < 5:
            upcoming_rows.append(item)

    weeks = []
    cursor = grid_start
    while cursor <= grid_end:
        week = []
        for _ in range(7):
            day_items = items_by_date.get(cursor, [])
            week.append(
                {
                    "iso_date": cursor.isoformat(),
                    "day_number": cursor.day,
                    "is_current_month": cursor.month == reference.month,
                    "is_today": cursor == reference,
                    "has_due": bool(day_items),
                    "pulse": bool(day_items),
                    "items": day_items,
                    "count": len(day_items),
                }
            )
            cursor += timedelta(days=1)
        weeks.append(week)

    return {
        "month_label": f"{PT_BR_MONTHS[reference.month - 1]} {reference.year}",
        "weekday_labels": PT_BR_WEEKDAYS,
        "weeks": weeks,
        "today_label": reference.strftime("%d/%m/%Y"),
        "items_total": sum(len(items) for items in items_by_date.values()),
        "upcoming_rows": upcoming_rows,
    }
