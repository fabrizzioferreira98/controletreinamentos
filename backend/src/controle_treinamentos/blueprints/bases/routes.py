from __future__ import annotations

import unicodedata
from collections import defaultdict
from datetime import datetime

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    has_app_context,
    has_request_context,
    jsonify,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from ...application.base_operations import add_pilot_to_base, change_pilot_status, get_pilot_history, move_pilot_to_base
from ...application.tripulante_media import load_tripulante_photo_payload
from ...auth import role_required
from ...contracts.bases import (
    parse_base_pilot_add_request,
    parse_base_pilot_move_request,
    parse_base_pilot_status_request,
    parse_bases_status_filter,
    serialize_base_pilot_added,
    serialize_base_pilot_history,
    serialize_base_pilot_mutation,
    serialize_bases_payload,
)
from ...core.domain_errors import DomainError
from ...core.http_contract import programmatic_json
from ...core.http_utils import domain_error_payload
from ...core.utils import json_response_with_etag
from ...db import fetch_unique_bases, get_db
from ...repositories.dashboard_cache import get_panel_cache, set_panel_cache
from ...services import build_expiry_indicator, business_today, name_initials

bases_bp = Blueprint("bases", __name__, url_prefix="/bases")

STATUS_META = {
    "ativo": {"key": "ativo", "label": "Ativo", "class": "status-green", "marker_class": "status-marker-green"},
    "folga": {"key": "folga", "label": "Folga", "class": "status-yellow", "marker_class": "status-marker-yellow"},
    "ferias": {"key": "ferias", "label": "Férias", "class": "status-blue", "marker_class": "status-marker-blue"},
    "atestado": {"key": "atestado", "label": "Atestado", "class": "status-red", "marker_class": "status-marker-red"},
    "afastado": {"key": "afastado", "label": "Afastado", "class": "status-dark", "marker_class": "status-marker-dark"},
    "treinamento": {"key": "treinamento", "label": "Treinamento", "class": "status-purple", "marker_class": "status-marker-purple"},
}
UNKNOWN_STATUS_KEY = "desconhecido"
UNKNOWN_STATUS_META = {
    "key": UNKNOWN_STATUS_KEY,
    "label": "Status não mapeado",
    "class": "status-dark",
    "marker_class": "status-marker-dark",
}
_STATUS_CANONICAL_MAP = {
    "ativo": "ativo",
    "folga": "folga",
    "ferias": "ferias",
    "atestado": "atestado",
    "afastado": "afastado",
    "treinamento": "treinamento",
}

def _apply_statement_timeout(db, config_key: str, default_ms: int) -> None:
    raw = default_ms
    if has_app_context():
        raw = current_app.config.get(config_key, default_ms)
    try:
        timeout_ms = int(raw)
    except (TypeError, ValueError):
        timeout_ms = default_ms
    timeout_ms = max(0, timeout_ms)
    if timeout_ms <= 0:
        return
    try:
        db.execute("SET LOCAL statement_timeout = %s", (timeout_ms,))
    except Exception:
        if has_app_context():
            current_app.logger.debug("Não foi possível aplicar statement_timeout local para %s.", config_key)


def _parse_timestamp(value):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M")
    return str(value)


def _parse_timestamp_iso(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    raw = str(value).strip()
    return raw or None


def _canonical_status_key(value: str | None) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    normalized = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.strip().lower()
    return _STATUS_CANONICAL_MAP.get(normalized)


def _status_meta_for(value: str | None, *, pilot_id: int | None = None) -> dict:
    canonical = _canonical_status_key(value)
    if canonical:
        return STATUS_META[canonical]
    if has_app_context():
        current_app.logger.warning(
            "Status de piloto não canônico detectado em Gestão de Bases. pilot_id=%s status_raw=%r",
            pilot_id,
            value,
        )
    return UNKNOWN_STATUS_META


def _build_pilot_photo_response(row):
    payload = load_tripulante_photo_payload(dict(row or {}))
    if not payload:
        return None
    response = Response(payload["payload_bytes"], mimetype=payload["mime_type"])
    response.headers["Cache-Control"] = "private, max-age=300"
    return response


def _fetch_earliest_due_by_tripulante(db, tripulante_ids):
    ids = sorted({int(item) for item in tripulante_ids if item})
    if not ids:
        return {}
    rows = db.execute(
        """
        SELECT tripulante_id, MIN(data_vencimento) AS first_due_date
        FROM treinamentos
        WHERE tripulante_id = ANY(%s)
          AND data_vencimento IS NOT NULL
        GROUP BY tripulante_id
        """,
        (ids,),
    ).fetchall()
    return {row["tripulante_id"]: row["first_due_date"] for row in rows}


def _serialize_pilot(row, *, earliest_due_by_tripulante, reference_date):
    row_data = row if isinstance(row, dict) else dict(row)
    status_meta = _status_meta_for(row_data.get("status"), pilot_id=row_data.get("id"))
    status_key = status_meta["key"]
    due_date = earliest_due_by_tripulante.get(row_data["tripulante_id"]) if row_data["tripulante_id"] else None
    expiry_indicator = build_expiry_indicator(due_date, reference=reference_date)
    has_photo = bool(row_data.get("possui_foto"))
    return {
        "id": row_data["id"],
        "nome": row_data["nome"],
        "matricula": row_data["matricula"],
        "tripulante_id": row_data["tripulante_id"],
        "base_id": row_data["base_id"],
        "base_nome": row_data["base_nome"],
        "base_uf": row_data["base_uf"],
        "status": status_key,
        "status_label": status_meta["label"],
        "status_class": status_meta["class"],
        "status_raw": row_data.get("status"),
        "possui_foto": has_photo,
        "foto_url": url_for("bases.pilot_photo", pilot_id=row_data["id"]) if has_photo and has_request_context() else "",
        "iniciais": name_initials(row_data["nome"]),
        "expiry_indicator": expiry_indicator,
        "criado_em": _parse_timestamp(row_data["criado_em"]),
        "criado_em_iso": _parse_timestamp_iso(row_data["criado_em"]),
    }


def _empty_counts():
    counts = {key: 0 for key in STATUS_META}
    counts[UNKNOWN_STATUS_KEY] = 0
    return counts


def _fetch_bases_payload(status_filter=None):
    db = get_db()
    _apply_statement_timeout(db, "BASES_PAYLOAD_STATEMENT_TIMEOUT_MS", 2500)
    params = []
    where = ""
    normalized_filter = _canonical_status_key(status_filter)
    if normalized_filter:
        if normalized_filter == "ferias":
            where = "WHERE LOWER(TRIM(COALESCE(p.status, ''))) IN (%s, %s)"
            params.extend(["ferias", "férias"])
        else:
            where = "WHERE LOWER(TRIM(COALESCE(p.status, ''))) = %s"
            params.append(normalized_filter)
    else:
        # Regra operacional: no modo "Todos" a gestão de bases lista apenas pilotos disponíveis
        # para operação corrente; afastados ficam acessíveis via filtro específico.
        where = "WHERE LOWER(TRIM(COALESCE(p.status, ''))) <> %s"
        params.append("afastado")

    bases_rows = fetch_unique_bases(db)
    pilot_rows = db.execute(
        f"""
        SELECT
            p.*,
            b.nome AS base_nome,
            b.uf AS base_uf,
            COALESCE(
                (
                    (t.foto_base64 IS NOT NULL AND TRIM(t.foto_base64) <> '')
                    OR (t.foto_storage_ref IS NOT NULL AND TRIM(t.foto_storage_ref) <> '')
                ),
                FALSE
            ) AS possui_foto
        FROM pilotos p
        JOIN bases b ON b.id = p.base_id
        LEFT JOIN tripulantes t ON t.id = p.tripulante_id
        {where}
        ORDER BY b.nome, p.nome
        """,
        tuple(params),
    ).fetchall()

    earliest_due_by_tripulante = _fetch_earliest_due_by_tripulante(
        db, [row["tripulante_id"] for row in pilot_rows if row["tripulante_id"]]
    )
    reference_date = business_today()

    grouped_pilots = defaultdict(list)
    grouped_counts = defaultdict(_empty_counts)

    pilotos = []
    for row in pilot_rows:
        row_data = row if isinstance(row, dict) else dict(row)
        status_meta = _status_meta_for(row_data.get("status"), pilot_id=row_data.get("id"))
        status_key = status_meta["key"]
        pilot_data = _serialize_pilot(
            row_data,
            earliest_due_by_tripulante=earliest_due_by_tripulante,
            reference_date=reference_date,
        )
        grouped_pilots[row_data["base_id"]].append(pilot_data)
        grouped_counts[row_data["base_id"]][status_key] = grouped_counts[row_data["base_id"]].get(status_key, 0) + 1
        pilotos.append(pilot_data)

    bases = []
    for row in bases_rows:
        counts = grouped_counts[row["id"]]
        base_data = {
            "id": row["id"],
            "nome": row["nome"],
            "uf": row["uf"],
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "ativa": row["ativa"],
            "total_pilotos": sum(counts.values()),
            "counts": counts,
            "pilotos": grouped_pilots[row["id"]],
        }
        bases.append(base_data)

    return {
        "bases": bases,
        "pilotos": pilotos,
        "status_options": list(STATUS_META.values()),
        "status_filter": normalized_filter if normalized_filter in STATUS_META else "",
    }


def _payload_cache_key(status_filter: str | None = None) -> str:
    normalized = _canonical_status_key(status_filter)
    if not normalized:
        normalized = "all"
    return f"bases:payload:{normalized}"


def _domain_json_error(exc: DomainError):
    return domain_error_payload(exc)


def _bases_api_payload(payload: dict) -> dict:
    return serialize_bases_payload(payload)


def build_bases_api_payload(status_filter=None) -> dict:
    cache_key = _payload_cache_key(status_filter)
    payload = get_panel_cache(cache_key)
    if payload is None:
        payload = _fetch_bases_payload(status_filter=status_filter)
        set_panel_cache(cache_key, payload, ttl_seconds=15)
    return _bases_api_payload(payload)


def _request_contract_payload():
    json_payload = request.get_json(silent=True)
    if isinstance(json_payload, dict):
        return json_payload
    return request.form


@bases_bp.get("")
@login_required
def index():
    cache_key = _payload_cache_key()
    payload = get_panel_cache(cache_key)
    if payload is None:
        payload = _fetch_bases_payload()
        # Snapshot inicial da tela de bases para reduzir TTFB em acessos repetidos.
        set_panel_cache(cache_key, payload, ttl_seconds=15)
    initial_payload = _bases_api_payload(payload)
    return render_template(
        "bases/index.html",
        bases_data=payload["bases"],
        pilotos_data=payload["pilotos"],
        status_options=payload["status_options"],
        initial_payload=initial_payload,
        can_manage_bases=current_user.perfil == "gestora",
    )


@bases_bp.get("/api/dados")
@login_required
@programmatic_json
def api_dados():
    status_filter = parse_bases_status_filter(request.args)
    return json_response_with_etag(build_bases_api_payload(status_filter=status_filter), max_age=15)


@bases_bp.get("/pilotos/<int:pilot_id>/foto")
@login_required
def pilot_photo(pilot_id):
    db = get_db()
    row = db.execute(
        """
        SELECT t.id AS tripulante_id, t.foto_base64, t.foto_storage_ref, t.foto_mime_type
        FROM pilotos p
        JOIN tripulantes t ON t.id = p.tripulante_id
        WHERE p.id = %s
        """,
        (pilot_id,),
    ).fetchone()
    if not row:
        abort(404)
    response = _build_pilot_photo_response(row)
    if not response:
        abort(404)
    return response


@bases_bp.post("/pilotos/adicionar")
@role_required("gestora")
@programmatic_json
def adicionar_piloto():
    try:
        result = add_pilot_to_base(
            parse_base_pilot_add_request(_request_contract_payload()),
            actor_user_id=int(current_user.id),
        )
    except DomainError as exc:
        return _domain_json_error(exc)
    return jsonify(serialize_base_pilot_added(result)), 201


@bases_bp.post("/pilotos/<int:pilot_id>/status")
@role_required("gestora")
@programmatic_json
def alterar_status(pilot_id):
    try:
        result = change_pilot_status(
            pilot_id,
            parse_base_pilot_status_request(_request_contract_payload()),
            actor_user_id=int(current_user.id),
        )
    except DomainError as exc:
        return _domain_json_error(exc)
    return jsonify(serialize_base_pilot_mutation(result, code="base_pilot_status_updated", pilot_id=pilot_id))


@bases_bp.post("/pilotos/<int:pilot_id>/mover")
@role_required("gestora")
@programmatic_json
def mover_piloto(pilot_id):
    try:
        result = move_pilot_to_base(
            pilot_id,
            parse_base_pilot_move_request(_request_contract_payload()),
            actor_user_id=int(current_user.id),
        )
    except DomainError as exc:
        return _domain_json_error(exc)
    return jsonify(serialize_base_pilot_mutation(result, code="base_pilot_moved", pilot_id=pilot_id))


@bases_bp.get("/pilotos/<int:pilot_id>/historico")
@login_required
@programmatic_json
def historico_piloto(pilot_id):
    try:
        payload = get_pilot_history(pilot_id)
    except DomainError as exc:
        return _domain_json_error(exc)
    return jsonify(serialize_base_pilot_history(payload))
