from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

try:
    import psycopg2
except ImportError:
    psycopg2 = None  # type: ignore[assignment]
from flask import current_app

from ..constants import DEFAULT_PAGE_SIZE, NAV_CACHE_TTL_SECONDS
from ..core.cache_service import cache_service
from ..core.http_utils import digits_only
from ..db import ensure_base_exists, fetch_unique_bases
from ..services import business_today, calculate_training_status, status_color


def find_tripulante_by_cpf(db, cpf: str, *, exclude_id: int | None = None):
    cpf_digits = digits_only(cpf)
    if len(cpf_digits) != 11:
        return None
    return db.execute(
        """
        SELECT id
        FROM tripulantes
        WHERE regexp_replace(COALESCE(cpf, ''), '\\D', '', 'g') = %s
          AND (%s IS NULL OR id != %s)
        LIMIT 1
        """,
        (cpf_digits, exclude_id, exclude_id),
    ).fetchone()

def fetch_base_options(db, selected_base: str | None = None):
    if selected_base:
        ensure_base_exists(db, selected_base)
    return fetch_unique_bases(db, selected_base)

def fetch_training_attachments(db, treinamento_id: int):
    rows = db.execute(
        """
        SELECT
            a.id,
            a.treinamento_id,
            a.nome_original,
            a.nome_interno,
            a.mime_type,
            a.tamanho_bytes,
            a.storage_ref,
            a.status,
            a.enviado_por,
            a.enviado_em,
            u.nome AS enviado_por_nome
        FROM treinamento_anexos_pdf a
        LEFT JOIN usuarios u ON u.id = a.enviado_por
        WHERE a.treinamento_id = %s
        ORDER BY a.enviado_em DESC, a.id DESC
        """,
        (treinamento_id,),
    ).fetchall()
    return [dict(row) for row in rows]

def fetch_navigation_counts(db):
    cached = cache_service.get_navigation_cache(ttl_seconds=NAV_CACHE_TTL_SECONDS)
    if cached is not None:
        return dict(cached)
    try:
        row = db.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM tripulantes) AS tripulantes_total,
                (SELECT COUNT(*) FROM treinamentos) AS treinamentos_total
            """
        ).fetchone()
        payload = {
            "tripulantes": row["tripulantes_total"],
            "treinamentos": row["treinamentos_total"],
        }
    except psycopg2.Error:
        current_app.logger.exception("Failed to fetch navigation counters.")
        payload = {"tripulantes": 0, "treinamentos": 0}

    cache_service.set_navigation_cache(payload)
    return dict(payload)

def fetch_training_rows(db, where_clause="", params=()):
    today = business_today()
    rows = db.execute(
        f"""
        SELECT t.*,
               c.nome AS tripulante_nome,
               e.nome AS equipamento_nome,
               tt.nome AS tipo_treinamento_nome
        FROM treinamentos t
        JOIN tripulantes c ON c.id = t.tripulante_id
        LEFT JOIN equipamentos e ON e.id = t.equipamento_id
        JOIN tipos_treinamento tt ON tt.id = t.tipo_treinamento_id
        {where_clause}
        """,
        params,
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["status_calculado"] = calculate_training_status(row["data_vencimento"], today)
        item["status_class"] = status_color(item["status_calculado"])
        result.append(item)
    return result

def fetch_upcoming_training_items_by_tripulante(db, tripulante_ids, *, limit_per_tripulante=5, window_days=90):
    ids = [int(item) for item in tripulante_ids if item]
    if not ids:
        return {}

    today = business_today()
    rows = db.execute(
        """
        SELECT *
        FROM (
            SELECT
                t.tripulante_id,
                t.data_vencimento,
                tt.nome AS tipo_treinamento_nome,
                COALESCE(e.nome, 'Sem equipamento') AS equipamento_nome,
                ROW_NUMBER() OVER (
                    PARTITION BY t.tripulante_id
                    ORDER BY t.data_vencimento, tt.nome
                ) AS row_number
            FROM treinamentos t
            JOIN tipos_treinamento tt ON tt.id = t.tipo_treinamento_id
            LEFT JOIN equipamentos e ON e.id = t.equipamento_id
            WHERE t.tripulante_id = ANY(%s)
              AND t.data_vencimento IS NOT NULL
              AND t.data_vencimento >= %s
              AND t.data_vencimento <= %s
        ) ranked
        WHERE row_number <= %s
        ORDER BY tripulante_id, data_vencimento, tipo_treinamento_nome
        """,
        (ids, today, today + timedelta(days=window_days), limit_per_tripulante),
    ).fetchall()

    grouped = defaultdict(list)
    for row in rows:
        grouped[row["tripulante_id"]].append(
            {
                "tipo_treinamento_nome": row["tipo_treinamento_nome"],
                "equipamento_nome": row["equipamento_nome"],
                "data_vencimento": row["data_vencimento"].strftime("%d/%m/%Y") if row["data_vencimento"] else "",
            }
        )
    return grouped

def _fetch_training_page_legacy(db, where_clause="", params=(), *, limit=DEFAULT_PAGE_SIZE, offset=0):
    today = business_today()
    rows = db.execute(
        f"""
        SELECT
            t.id,
            t.tripulante_id,
            t.equipamento_id,
            t.tipo_treinamento_id,
            t.segmento_teorico_id,
            t.aeronave_modelo,
            t.ctac_solo_horas,
            t.ctac_voo_pic_sic_horas,
            t.ctac_voo_crew_horas,
            t.data_realizacao,
            t.data_vencimento,
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
        {where_clause}
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
        LIMIT %s OFFSET %s
        """,
        (today, today + timedelta(days=30), *params, today, today + timedelta(days=30), limit, offset),
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["status_class"] = status_color(item["status_calculado"])
        result.append(item)
    return result


def fetch_training_page(db, where_clause="", params=(), *, limit=DEFAULT_PAGE_SIZE, offset=0):
    today = business_today()
    rows = db.execute(
        f"""
        WITH ranked AS (
            SELECT
                t.id,
                t.tripulante_id,
                t.equipamento_id,
                t.tipo_treinamento_id,
                t.segmento_teorico_id,
                t.aeronave_modelo,
                t.ctac_solo_horas,
                t.ctac_voo_pic_sic_horas,
                t.ctac_voo_crew_horas,
                t.data_realizacao,
                t.data_vencimento,
                c.nome AS tripulante_nome,
                tt.nome AS tipo_treinamento_nome,
                CASE
                    WHEN t.data_vencimento IS NULL THEN 'sem informaÃ§Ã£o'
                    WHEN t.data_vencimento < %s THEN 'vencido'
                    WHEN t.data_vencimento <= %s THEN 'a vencer'
                    ELSE 'regular'
                END AS status_calculado,
                CASE
                    WHEN t.data_vencimento IS NULL THEN 3
                    WHEN t.data_vencimento < %s THEN 0
                    WHEN t.data_vencimento <= %s THEN 1
                    ELSE 2
                END AS status_ordem
            FROM treinamentos t
            JOIN tripulantes c ON c.id = t.tripulante_id
            JOIN tipos_treinamento tt ON tt.id = t.tipo_treinamento_id
            {where_clause}
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
            LIMIT %s OFFSET %s
        )
        SELECT
            ranked.id,
            ranked.tripulante_id,
            ranked.equipamento_id,
            ranked.tipo_treinamento_id,
            ranked.segmento_teorico_id,
            ranked.aeronave_modelo,
            ranked.ctac_solo_horas,
            ranked.ctac_voo_pic_sic_horas,
            ranked.ctac_voo_crew_horas,
            ranked.data_realizacao,
            ranked.data_vencimento,
            ranked.tripulante_nome,
            e.nome AS equipamento_nome,
            ranked.tipo_treinamento_nome,
            ranked.status_calculado
        FROM ranked
        LEFT JOIN equipamentos e ON e.id = ranked.equipamento_id
        ORDER BY
            ranked.status_ordem,
            ranked.data_vencimento NULLS LAST,
            ranked.tipo_treinamento_nome,
            ranked.tripulante_nome
        """,
        (
            today,
            today + timedelta(days=30),
            today,
            today + timedelta(days=30),
            *params,
            today,
            today + timedelta(days=30),
            limit,
            offset,
        ),
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["status_class"] = status_color(item["status_calculado"])
        result.append(item)
    return result


def resolve_tripulante_pilot_matricula(db, *, tripulante_id: int, licenca_anac: str, current_pilot_id: int | None = None) -> str:
    preferred = (licenca_anac or "").strip() or f"TRIP-{tripulante_id:06d}"
    duplicate = db.execute(
        """
        SELECT id
        FROM pilotos
        WHERE matricula = %s
          AND (%s IS NULL OR id != %s)
        """,
        (preferred, current_pilot_id, current_pilot_id),
    ).fetchone()
    if not duplicate:
        return preferred

    fallback = f"TRIP-{tripulante_id:06d}"
    duplicate_fallback = db.execute(
        """
        SELECT id
        FROM pilotos
        WHERE matricula = %s
          AND (%s IS NULL OR id != %s)
        """,
        (fallback, current_pilot_id, current_pilot_id),
    ).fetchone()
    if not duplicate_fallback:
        return fallback

    return f"{fallback}-{tripulante_id}"
