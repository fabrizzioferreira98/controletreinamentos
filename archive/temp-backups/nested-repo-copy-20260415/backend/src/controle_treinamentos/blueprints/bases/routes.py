from __future__ import annotations

import base64
import binascii
import re
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

from ...audit import record_audit_event
from ...auth import role_required
from ...core.http_contract import programmatic_json
from ...core.utils import json_response_with_etag
from ...db import fetch_unique_bases, get_db
from ...infra.media_storage import read_media_bytes
from ...repositories.dashboard_cache import clear_panel_cache, get_panel_cache, set_panel_cache
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

_PHOTO_DATA_URI_RE = re.compile(r"^data:image/(png|jpe?g|webp);base64,", re.IGNORECASE)


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


def _decode_photo_data_uri(raw_value: str):
    foto_base64 = (raw_value or "").strip()
    match = _PHOTO_DATA_URI_RE.match(foto_base64)
    if not match:
        return None
    image_format = match.group(1).lower()
    mime_type = "image/jpeg" if image_format in {"jpg", "jpeg"} else f"image/{image_format}"
    try:
        raw = base64.b64decode(foto_base64.split(",", 1)[1], validate=True)
    except (ValueError, binascii.Error):
        return None
    return raw, mime_type


def _build_pilot_photo_response(row):
    payload_bytes = read_media_bytes(
        row.get("foto_storage_ref"),
        fallback_bytes=None,
    )
    if payload_bytes:
        mime_type = (row.get("foto_mime_type") or "").strip() or "image/jpeg"
        response = Response(payload_bytes, mimetype=mime_type)
        response.headers["Cache-Control"] = "private, max-age=300"
        return response

    if not row.get("foto_base64"):
        return None
    decoded = _decode_photo_data_uri(row["foto_base64"])
    if not decoded:
        return None
    raw, mime_type = decoded
    response = Response(raw, mimetype=mime_type)
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


def _get_active_base(base_id):
    db = get_db()
    return db.execute(
        "SELECT id, nome, uf FROM bases WHERE id = %s AND ativa = TRUE",
        (base_id,),
    ).fetchone()


def _get_pilot(pilot_id):
    db = get_db()
    return db.execute(
        """
        SELECT p.*, b.nome AS base_nome, b.uf AS base_uf
        FROM pilotos p
        JOIN bases b ON b.id = p.base_id
        WHERE p.id = %s
        """,
        (pilot_id,),
    ).fetchone()


def _record_history(db, *, pilot_id, status_anterior, status_novo, base_anterior_id, base_nova_id, observacao=None):
    db.execute(
        """
        INSERT INTO historico_status_piloto
        (piloto_id, status_anterior, status_novo, base_anterior_id, base_nova_id, alterado_por, observacao)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            pilot_id,
            status_anterior,
            status_novo,
            base_anterior_id,
            base_nova_id,
            int(current_user.id),
            (observacao or "").strip() or None,
        ),
    )


def _audit_event(db, entidade, entidade_id, acao, anterior=None, novo=None, observacao=None):
    strict_mode = bool(current_app.config.get("AUDIT_STRICT_MODE", False))
    try:
        db.execute("SAVEPOINT audit_event_bases_sp")
        record_audit_event(
            db,
            entidade=entidade,
            entidade_id=entidade_id,
            acao=acao,
            realizado_por=int(current_user.id),
            payload_anterior=anterior,
            payload_novo=novo,
            observacao=observacao,
        )
        db.execute("RELEASE SAVEPOINT audit_event_bases_sp")
    except Exception as exc:
        try:
            db.execute("ROLLBACK TO SAVEPOINT audit_event_bases_sp")
        except Exception:
            db.conn.rollback()
        if strict_mode:
            current_app.logger.exception("Falha ao registrar auditoria em bases; modo estrito abortou operação.")
            raise RuntimeError("Falha ao persistir auditoria em modo estrito.") from exc
        current_app.logger.exception("Falha ao registrar evento de auditoria em bases.")


def _sync_tripulante_from_pilot(db, *, tripulante_id, nome, base_id, status):
    base = _get_active_base(base_id)
    if not base:
        return
    canonical_status = _canonical_status_key(status)
    if canonical_status:
        status_label = STATUS_META[canonical_status]["label"]
    else:
        status_label = (status or "").strip() or UNKNOWN_STATUS_META["label"]
        if has_app_context():
            current_app.logger.warning(
                "Status legado mantido ao sincronizar tripulante a partir de piloto. tripulante_id=%s status_raw=%r",
                tripulante_id,
                status,
            )
    is_active = 0 if canonical_status == "afastado" else 1
    db.execute(
        """
        UPDATE tripulantes
        SET nome = %s, base = %s, status = %s, ativo = %s
        WHERE id = %s
        """,
        (nome, base["nome"], status_label, is_active, tripulante_id),
    )


@bases_bp.get("")
@login_required
def index():
    cache_key = _payload_cache_key()
    payload = get_panel_cache(cache_key)
    if payload is None:
        payload = _fetch_bases_payload()
        # Snapshot inicial da tela de bases para reduzir TTFB em acessos repetidos.
        set_panel_cache(cache_key, payload, ttl_seconds=15)
    return render_template(
        "bases/index.html",
        bases_data=payload["bases"],
        pilotos_data=payload["pilotos"],
        status_options=payload["status_options"],
        initial_payload=payload,
        can_manage_bases=current_user.perfil == "gestora",
    )


@bases_bp.get("/api/dados")
@login_required
@programmatic_json
def api_dados():
    status_filter = request.args.get("status", "").strip().lower()
    cache_key = _payload_cache_key(status_filter)
    payload = get_panel_cache(cache_key)
    if payload is None:
        payload = _fetch_bases_payload(status_filter=status_filter)
        set_panel_cache(cache_key, payload, ttl_seconds=15)
    return json_response_with_etag(payload, max_age=15)


@bases_bp.get("/pilotos/<int:pilot_id>/foto")
@login_required
def pilot_photo(pilot_id):
    db = get_db()
    row = db.execute(
        """
        SELECT t.foto_base64, t.foto_storage_ref, t.foto_mime_type
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
    db = get_db()
    nome = (request.form.get("nome", "") or "").strip()
    matricula = (request.form.get("matricula", "") or "").strip().upper()
    status = (request.form.get("status", "ativo") or "").strip().lower()
    base_raw = (request.form.get("base_id", "") or "").strip()
    tripulante_raw = (request.form.get("tripulante_id", "") or "").strip()

    if not nome:
        return jsonify({"success": False, "message": "Nome do piloto é obrigatório."}), 400
    if len(nome) > 160:
        return jsonify({"success": False, "message": "Nome do piloto excede o limite de 160 caracteres."}), 400
    if status not in STATUS_META:
        return jsonify({"success": False, "message": "Status inválido para o piloto."}), 400

    try:
        base_id = int(base_raw)
    except ValueError:
        return jsonify({"success": False, "message": "Base inválida."}), 400

    base = _get_active_base(base_id)
    if not base:
        return jsonify({"success": False, "message": "A base informada não existe ou está inativa."}), 400

    tripulante_id = None
    tripulante = None
    if tripulante_raw:
        try:
            tripulante_id = int(tripulante_raw)
        except ValueError:
            return jsonify({"success": False, "message": "Tripulante inválido."}), 400
        tripulante = db.execute(
            """
            SELECT id, nome, licenca_anac
            FROM tripulantes
            WHERE id = %s
            """,
            (tripulante_id,),
        ).fetchone()
        if not tripulante:
            return jsonify({"success": False, "message": "Tripulante informado não existe."}), 400
        existing_link = db.execute("SELECT id FROM pilotos WHERE tripulante_id = %s", (tripulante_id,)).fetchone()
        if existing_link:
            return jsonify({"success": False, "message": "Este tripulante já está vinculado a um piloto."}), 409
        if not matricula:
            matricula = ((tripulante["licenca_anac"] or "").strip() or f"TRIP-{tripulante_id:06d}").upper()

    if not matricula:
        return jsonify({"success": False, "message": "Matrícula é obrigatória para cadastro de piloto."}), 400
    if len(matricula) > 32:
        return jsonify({"success": False, "message": "Matrícula excede o limite de 32 caracteres."}), 400

    duplicate_matricula = db.execute(
        "SELECT id FROM pilotos WHERE UPPER(TRIM(matricula)) = UPPER(%s)",
        (matricula,),
    ).fetchone()
    if duplicate_matricula:
        return jsonify({"success": False, "message": "Já existe piloto com esta matrícula."}), 409

    try:
        created = db.execute(
            """
            INSERT INTO pilotos (nome, matricula, tripulante_id, base_id, status)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (nome, matricula, tripulante_id, base_id, status),
        ).fetchone()

        if tripulante_id:
            _sync_tripulante_from_pilot(
                db,
                tripulante_id=tripulante_id,
                nome=nome,
                base_id=base_id,
                status=status,
            )

        _record_history(
            db,
            pilot_id=created["id"],
            status_anterior=None,
            status_novo=status,
            base_anterior_id=None,
            base_nova_id=base_id,
            observacao=(request.form.get("observacao", "") or "").strip() or "Cadastro inicial de piloto",
        )
        _audit_event(
            db,
            "piloto",
            created["id"],
            "create",
            anterior=None,
            novo={
                "nome": nome,
                "matricula": matricula,
                "tripulante_id": tripulante_id,
                "base_id": base_id,
                "status": status,
            },
            observacao=request.form.get("observacao"),
        )
        db.commit()
        clear_panel_cache("bases:payload:")
    except Exception:
        db.conn.rollback()
        current_app.logger.exception("Falha ao cadastrar piloto na gestão de bases.")
        return jsonify({"success": False, "message": "Não foi possível cadastrar o piloto."}), 500

    return jsonify(
        {
            "success": True,
            "message": "Piloto cadastrado com sucesso.",
            "pilot_id": created["id"],
        }
    ), 201


@bases_bp.post("/pilotos/<int:pilot_id>/status")
@role_required("gestora")
@programmatic_json
def alterar_status(pilot_id):
    db = get_db()
    pilot = _get_pilot(pilot_id)
    if not pilot:
        return jsonify({"success": False, "message": "Piloto não encontrado."}), 404

    status_novo = request.form.get("status_novo", "").strip().lower()
    if status_novo not in STATUS_META:
        return jsonify({"success": False, "message": "Status inválido."}), 400
    if status_novo == pilot["status"]:
        return jsonify({"success": False, "message": "O piloto já está com esse status."}), 400

    try:
        db.execute("UPDATE pilotos SET status = %s WHERE id = %s", (status_novo, pilot_id))
        if pilot["tripulante_id"]:
            _sync_tripulante_from_pilot(
                db,
                tripulante_id=pilot["tripulante_id"],
                nome=pilot["nome"],
                base_id=pilot["base_id"],
                status=status_novo,
            )
        _record_history(
            db,
            pilot_id=pilot_id,
            status_anterior=pilot["status"],
            status_novo=status_novo,
            base_anterior_id=pilot["base_id"],
            base_nova_id=pilot["base_id"],
            observacao=request.form.get("observacao"),
        )
        _audit_event(
            db,
            "piloto",
            pilot_id,
            "status_update",
            anterior={"status": pilot["status"], "base_id": pilot["base_id"]},
            novo={"status": status_novo, "base_id": pilot["base_id"]},
            observacao=request.form.get("observacao"),
        )
        db.commit()
        clear_panel_cache("bases:payload:")
    except Exception:
        db.conn.rollback()
        current_app.logger.exception("Falha ao atualizar status de piloto na gestão de bases.")
        return jsonify({"success": False, "message": "Não foi possível atualizar o status do piloto."}), 500
    return jsonify({"success": True, "message": "Status atualizado com sucesso."})


@bases_bp.post("/pilotos/<int:pilot_id>/mover")
@role_required("gestora")
@programmatic_json
def mover_piloto(pilot_id):
    db = get_db()
    pilot = _get_pilot(pilot_id)
    if not pilot:
        return jsonify({"success": False, "message": "Piloto não encontrado."}), 404

    base_raw = request.form.get("base_nova_id", "").strip()
    try:
        base_nova_id = int(base_raw)
    except ValueError:
        return jsonify({"success": False, "message": "Base de destino inválida."}), 400
    if base_nova_id == pilot["base_id"]:
        return jsonify({"success": False, "message": "Selecione uma base diferente da atual."}), 400

    base_nova = _get_active_base(base_nova_id)
    if not base_nova:
        return jsonify({"success": False, "message": "A base de destino não existe ou está inativa."}), 400

    try:
        db.execute("UPDATE pilotos SET base_id = %s WHERE id = %s", (base_nova_id, pilot_id))
        if pilot["tripulante_id"]:
            _sync_tripulante_from_pilot(
                db,
                tripulante_id=pilot["tripulante_id"],
                nome=pilot["nome"],
                base_id=base_nova_id,
                status=pilot["status"],
            )
        _record_history(
            db,
            pilot_id=pilot_id,
            status_anterior=pilot["status"],
            status_novo=pilot["status"],
            base_anterior_id=pilot["base_id"],
            base_nova_id=base_nova_id,
            observacao=request.form.get("observacao"),
        )
        _audit_event(
            db,
            "piloto",
            pilot_id,
            "move",
            anterior={"status": pilot["status"], "base_id": pilot["base_id"]},
            novo={"status": pilot["status"], "base_id": base_nova_id},
            observacao=request.form.get("observacao"),
        )
        db.commit()
        clear_panel_cache("bases:payload:")
    except Exception:
        db.conn.rollback()
        current_app.logger.exception("Falha ao mover piloto na gestão de bases.")
        return jsonify({"success": False, "message": "Não foi possível mover o piloto para a nova base."}), 500
    return jsonify({"success": True, "message": "Piloto movido com sucesso."})


@bases_bp.get("/pilotos/<int:pilot_id>/historico")
@login_required
@programmatic_json
def historico_piloto(pilot_id):
    db = get_db()
    pilot = _get_pilot(pilot_id)
    if not pilot:
        return jsonify({"success": False, "message": "Piloto não encontrado."}), 404

    rows = db.execute(
        """
        SELECT
            h.*,
            u.nome AS alterado_por_nome,
            ba.nome AS base_anterior_nome,
            bn.nome AS base_nova_nome
        FROM historico_status_piloto h
        LEFT JOIN usuarios u ON u.id = h.alterado_por
        LEFT JOIN bases ba ON ba.id = h.base_anterior_id
        LEFT JOIN bases bn ON bn.id = h.base_nova_id
        WHERE h.piloto_id = %s
        ORDER BY h.alterado_em DESC, h.id DESC
        """,
        (pilot_id,),
    ).fetchall()

    history = []
    for row in rows:
        base_changed = row["base_anterior_id"] != row["base_nova_id"]
        status_changed = row["status_anterior"] != row["status_novo"]
        if row["status_anterior"] is None and row["base_anterior_id"] is None:
            event_type = "Cadastro inicial"
        elif base_changed and status_changed:
            event_type = "Movimentação e atualização de status"
        elif base_changed:
            event_type = "Movimentação de base"
        else:
            event_type = "Mudança de status"
        history.append(
            {
                "id": row["id"],
                "event_type": event_type,
                "status_anterior": row["status_anterior"],
                "status_novo": row["status_novo"],
                "base_anterior_nome": row["base_anterior_nome"],
                "base_nova_nome": row["base_nova_nome"],
                "alterado_por": row["alterado_por_nome"] or "Sistema",
                "alterado_em": _parse_timestamp(row["alterado_em"]),
                "observacao": row["observacao"] or "",
            }
        )

    return jsonify(
        {
            "success": True,
            "piloto": {"id": pilot["id"], "nome": pilot["nome"], "matricula": pilot["matricula"]},
            "historico": history,
        }
    )
