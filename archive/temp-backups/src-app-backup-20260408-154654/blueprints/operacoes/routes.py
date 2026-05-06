
try:
    import psycopg2
except ImportError:
    psycopg2 = None  # type: ignore[assignment]
from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import login_required

from ...auth import permission_required
from ...constants import PERNOITE_TIPO_OPTIONS
from ...core.audit_utils import audit_event, rollback_db
from ...core.http_utils import (
    get_optional_date,
    get_optional_int,
    get_optional_limited_text,
    get_optional_text,
    get_required_date,
    get_required_int,
    get_required_text,
    resolve_pagination_state,
)
from ...db import get_db
from ...repositories.dashboard_cache import clear_panel_cache, fetch_cached_rows
from ...service_layers.domain_validation import (
    _sync_auto_pernoites_for_missao,
    parse_tripulante_ids,
    validate_missao_tripulantes_exist,
    validate_pernoite_references,
)
from ...service_layers.form_builders import build_missao_form_state, build_pernoite_form_state
from ...service_layers.form_options import get_missao_form_options, get_pernoite_form_options
from ...services import parse_date
from . import operacoes_bp


def _render_missao_form_legacy(missao=None, *, options: dict):
    state = dict(missao) if missao else None
    selected_ids = []
    if state and state.get("tripulante_ids"):
        selected_ids = [str(item) for item in state.get("tripulante_ids", [])]
    elif state and state.get("id"):
        selected_ids = [
            str(item["tripulante_id"])
            for item in options.get("missao_tripulantes", [])
        ]
    if state is not None:
        state["tripulante_ids"] = selected_ids
    return render_template(
        "missoes_form.html",
        missao=state,
        tipo_pernoite_options=options.get("tipo_pernoite_options", PERNOITE_TIPO_OPTIONS),
        tripulantes=options.get("tripulantes", []),
    )


def _render_pernoite_form_legacy(pernoite=None, *, options: dict):
    return render_template(
        "pernoites_form.html",
        pernoite=dict(pernoite) if pernoite else None,
        tripulantes=options.get("tripulantes", []),
        missoes=options.get("missoes", []),
        tipo_options=options.get("tipo_options", PERNOITE_TIPO_OPTIONS),
    )


@operacoes_bp.route("/missoes")
@login_required
def missoes_list():
    db = get_db()
    busca = request.args.get("busca", "").strip()
    contratante = request.args.get("contratante", "").strip()
    clauses = []
    params = []
    if busca:
        clauses.append("(LOWER(m.codigo_voo) LIKE %s OR LOWER(m.tipo_operacao) LIKE %s)")
        params.extend([f"%{busca.lower()}%", f"%{busca.lower()}%"])
    if contratante:
        clauses.append("LOWER(m.contratante) LIKE %s")
        params.append(f"%{contratante.lower()}%")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    total = db.execute(
        f"SELECT COUNT(*) AS total FROM missoes_operacionais m {where}",
        tuple(params),
    ).fetchone()["total"]
    paging = resolve_pagination_state(
        total,
        endpoint="operacoes.missoes_list",
        busca=busca,
        contratante=contratante,
    )
    rows = db.execute(
        f"""
        WITH paged_ids AS (
            SELECT m.id
            FROM missoes_operacionais m
            {where}
            ORDER BY m.data_inicio DESC, m.id DESC
            LIMIT %s OFFSET %s
        )
        SELECT
            m.id,
            m.codigo_voo,
            m.contratante,
            m.data_inicio,
            m.data_fim,
            m.origem,
            m.destino,
            m.tipo_operacao,
            m.conta_missao_produtividade,
            COALESCE(array_remove(array_agg(c.nome ORDER BY c.nome), NULL), ARRAY[]::text[]) AS tripulantes_nomes
        FROM paged_ids p
        JOIN missoes_operacionais m ON m.id = p.id
        LEFT JOIN missao_tripulantes mt ON mt.missao_id = m.id
        LEFT JOIN tripulantes c ON c.id = mt.tripulante_id
        GROUP BY m.id
        ORDER BY m.data_inicio DESC, m.id DESC
        """,
        (*params, paging["per_page"], paging["offset"]),
    ).fetchall()
    missoes = [dict(row) for row in rows]
    return render_template(
        "missoes_list.html",
        missoes=missoes,
        filtros={"busca": busca, "contratante": contratante},
        pagination=paging["pagination"],
    )


@operacoes_bp.route("/missoes/novo", methods=["GET", "POST"])
@permission_required("missoes:create")
def missoes_new():
    db = get_db()
    if request.method == "POST":
        state = build_missao_form_state(request.form)
        tripulante_ids_raw = request.form.getlist("tripulante_ids")
        try:
            codigo_voo = get_required_text(request.form, "codigo_voo", "Número do voo")
            contratante = get_required_text(request.form, "contratante", "Contratante")
            data_inicio = get_required_date(request.form, "data_inicio", "Data de início")
            data_fim = get_optional_date(request.form, "data_fim", "Data de fim")
            if data_fim and parse_date(data_fim) < parse_date(data_inicio):
                raise ValueError("A data de fim não pode ser anterior à data de início.")
            tripulante_ids = parse_tripulante_ids(tripulante_ids_raw)
            validate_missao_tripulantes_exist(db, tripulante_ids)
            gerar_pernoites_automaticos = bool(request.form.get("gerar_pernoites_automaticos"))
            tipo_pernoite_auto = get_optional_text(request.form, "tipo_pernoite_auto") or "cobertura_base"
            data_pernoite_auto = get_optional_date(request.form, "data_pernoite_auto", "Data do pernoite automático") or data_inicio
            quantidade_pernoite_auto = get_optional_int(request.form, "quantidade_pernoite_auto", "Quantidade de pernoite automático") or 1
            if tipo_pernoite_auto not in PERNOITE_TIPO_OPTIONS:
                raise ValueError("Tipo de pernoite automático inválido.")
            if quantidade_pernoite_auto <= 0:
                raise ValueError("Quantidade de pernoite automático deve ser maior que zero.")
        except ValueError as exc:
            flash(str(exc), "error")
            state["tripulante_ids"] = tripulante_ids_raw
            db = get_db()
            opts = get_missao_form_options(db)
            return _render_missao_form_legacy(missao=state, options=opts), 400
        created = db.execute(
            """
            INSERT INTO missoes_operacionais (
                codigo_voo, contratante, data_inicio, data_fim, origem, destino, tipo_operacao,
                conta_missao_produtividade, observacoes
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                codigo_voo,
                contratante,
                data_inicio,
                data_fim,
                get_optional_text(request.form, "origem"),
                get_optional_text(request.form, "destino"),
                get_optional_text(request.form, "tipo_operacao"),
                bool(request.form.get("conta_missao_produtividade")),
                get_optional_limited_text(request.form, "observacoes", "Observações"),
            ),
        ).fetchone()
        for tripulante_id in tripulante_ids:
            db.execute(
                "INSERT INTO missao_tripulantes (missao_id, tripulante_id) VALUES (%s, %s) ON CONFLICT (missao_id, tripulante_id) DO NOTHING",
                (created["id"], tripulante_id),
            )
        if gerar_pernoites_automaticos:
            _sync_auto_pernoites_for_missao(
                db,
                missao_id=created["id"],
                tripulante_ids=tripulante_ids,
                data_pernoite=data_pernoite_auto,
                tipo_pernoite=tipo_pernoite_auto,
                quantidade=quantidade_pernoite_auto,
            )
        audit_event(db, "missao_operacional", created["id"], "create", novo=state)
        db.commit()
        clear_panel_cache("produtividade:")
        clear_panel_cache("options:missoes:")
        flash("Missão cadastrada com sucesso.", "success")
        return redirect(url_for("operacoes.missoes_list"))
    db = get_db()
    opts = get_missao_form_options(db)
    return _render_missao_form_legacy(missao=None, options=opts)


@operacoes_bp.route("/missoes/<int:missao_id>/editar", methods=["GET", "POST"])
@permission_required("missoes:edit")
def missoes_edit(missao_id):
    db = get_db()
    missao = db.execute("SELECT * FROM missoes_operacionais WHERE id = %s", (missao_id,)).fetchone()
    if not missao:
        abort(404)
    if request.method == "POST":
        state = build_missao_form_state(request.form)
        tripulante_ids_raw = request.form.getlist("tripulante_ids")
        try:
            codigo_voo = get_required_text(request.form, "codigo_voo", "Número do voo")
            contratante = get_required_text(request.form, "contratante", "Contratante")
            data_inicio = get_required_date(request.form, "data_inicio", "Data de início")
            data_fim = get_optional_date(request.form, "data_fim", "Data de fim")
            if data_fim and parse_date(data_fim) < parse_date(data_inicio):
                raise ValueError("A data de fim não pode ser anterior à data de início.")
            tripulante_ids = parse_tripulante_ids(tripulante_ids_raw)
            validate_missao_tripulantes_exist(db, tripulante_ids)
            gerar_pernoites_automaticos = bool(request.form.get("gerar_pernoites_automaticos"))
            tipo_pernoite_auto = get_optional_text(request.form, "tipo_pernoite_auto") or "cobertura_base"
            data_pernoite_auto = get_optional_date(request.form, "data_pernoite_auto", "Data do pernoite automático") or data_inicio
            quantidade_pernoite_auto = get_optional_int(request.form, "quantidade_pernoite_auto", "Quantidade de pernoite automático") or 1
            if tipo_pernoite_auto not in PERNOITE_TIPO_OPTIONS:
                raise ValueError("Tipo de pernoite automático inválido.")
            if quantidade_pernoite_auto <= 0:
                raise ValueError("Quantidade de pernoite automático deve ser maior que zero.")
        except ValueError as exc:
            flash(str(exc), "error")
            state["id"] = missao_id
            state["tripulante_ids"] = tripulante_ids_raw
            db = get_db()
            opts = get_missao_form_options(db)
            return _render_missao_form_legacy(missao=state, options=opts), 400
        db.execute(
            """
            UPDATE missoes_operacionais
            SET codigo_voo = %s, contratante = %s, data_inicio = %s, data_fim = %s,
                origem = %s, destino = %s, tipo_operacao = %s, conta_missao_produtividade = %s, observacoes = %s
            WHERE id = %s
            """,
            (
                codigo_voo,
                contratante,
                data_inicio,
                data_fim,
                get_optional_text(request.form, "origem"),
                get_optional_text(request.form, "destino"),
                get_optional_text(request.form, "tipo_operacao"),
                bool(request.form.get("conta_missao_produtividade")),
                get_optional_limited_text(request.form, "observacoes", "Observações"),
                missao_id,
            ),
        )
        db.execute("DELETE FROM missao_tripulantes WHERE missao_id = %s", (missao_id,))
        for tripulante_id in tripulante_ids:
            db.execute(
                "INSERT INTO missao_tripulantes (missao_id, tripulante_id) VALUES (%s, %s) ON CONFLICT (missao_id, tripulante_id) DO NOTHING",
                (missao_id, tripulante_id),
            )
        if gerar_pernoites_automaticos:
            _sync_auto_pernoites_for_missao(
                db,
                missao_id=missao_id,
                tripulante_ids=tripulante_ids,
                data_pernoite=data_pernoite_auto,
                tipo_pernoite=tipo_pernoite_auto,
                quantidade=quantidade_pernoite_auto,
            )
        audit_event(db, "missao_operacional", missao_id, "update", anterior=missao, novo=state)
        db.commit()
        clear_panel_cache("produtividade:")
        clear_panel_cache("options:missoes:")
        flash("Missão atualizada com sucesso.", "success")
        return redirect(url_for("operacoes.missoes_list"))
    db = get_db()
    opts = get_missao_form_options(db)
    return _render_missao_form_legacy(missao=missao, options=opts)


@operacoes_bp.route("/missoes/<int:missao_id>/excluir", methods=["POST"])
@permission_required("missoes:delete")
def missoes_delete(missao_id):
    db = get_db()
    missao = db.execute("SELECT * FROM missoes_operacionais WHERE id = %s", (missao_id,)).fetchone()
    if not missao:
        abort(404)
    audit_event(db, "missao_operacional", missao_id, "delete", anterior=missao)
    db.execute("DELETE FROM missoes_operacionais WHERE id = %s", (missao_id,))
    db.commit()
    clear_panel_cache("produtividade:")
    clear_panel_cache("options:missoes:")
    flash("Missão excluída com sucesso.", "success")
    return redirect(url_for("operacoes.missoes_list"))


@operacoes_bp.route("/pernoites")
@login_required
def pernoites_list():
    db = get_db()
    tipo = request.args.get("tipo", "").strip()
    tripulante = request.args.get("tripulante", "").strip()
    clauses = []
    params = []
    if tipo in PERNOITE_TIPO_OPTIONS:
        clauses.append("p.tipo_pernoite = %s")
        params.append(tipo)
    if tripulante.isdigit():
        clauses.append("p.tripulante_id = %s")
        params.append(int(tripulante))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    total = db.execute(
        f"SELECT COUNT(*) AS total FROM pernoites_operacionais p {where}",
        tuple(params),
    ).fetchone()["total"]
    paging = resolve_pagination_state(
        total,
        endpoint="operacoes.pernoites_list",
        tipo=tipo,
        tripulante=tripulante,
    )
    rows = db.execute(
        f"""
        SELECT p.*, c.nome AS tripulante_nome, m.codigo_voo, m.contratante
        FROM pernoites_operacionais p
        JOIN tripulantes c ON c.id = p.tripulante_id
        LEFT JOIN missoes_operacionais m ON m.id = p.missao_id
        {where}
        ORDER BY p.data_pernoite DESC, p.id DESC
        LIMIT %s OFFSET %s
        """,
        (*params, paging["per_page"], paging["offset"]),
    ).fetchall()
    return render_template(
        "pernoites_list.html",
        pernoites=rows,
        filtros={"tipo": tipo, "tripulante": tripulante},
        tripulantes=fetch_cached_rows(
            db,
            cache_key="options:tripulantes:id_nome",
            query="SELECT id, nome FROM tripulantes ORDER BY nome",
        ),
        tipo_options=PERNOITE_TIPO_OPTIONS,
        pagination=paging["pagination"],
    )


@operacoes_bp.route("/pernoites/novo", methods=["GET", "POST"])
@permission_required("pernoites:create")
def pernoites_new():
    db = get_db()
    if request.method == "POST":
        state = build_pernoite_form_state(request.form)
        try:
            tripulante_id = get_required_int(request.form, "tripulante_id", "Tripulante")
            missao_id = get_optional_int(request.form, "missao_id", "Missão")
            data_pernoite = get_required_date(request.form, "data_pernoite", "Data do pernoite")
            tipo_pernoite = get_required_text(request.form, "tipo_pernoite", "Tipo de pernoite")
            if tipo_pernoite not in PERNOITE_TIPO_OPTIONS:
                raise ValueError("Tipo de pernoite inválido.")
            quantidade = get_required_int(request.form, "quantidade", "Quantidade")
            if quantidade <= 0:
                raise ValueError("A quantidade deve ser maior que zero.")
            validate_pernoite_references(db, tripulante_id=tripulante_id, missao_id=missao_id)
        except ValueError as exc:
            flash(str(exc), "error")
            db = get_db()
            opts = get_pernoite_form_options(db)
            return _render_pernoite_form_legacy(pernoite=state, options=opts), 400
        try:
            created = db.execute(
                """
                INSERT INTO pernoites_operacionais (
                    tripulante_id, missao_id, data_pernoite, tipo_pernoite, quantidade, observacoes
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    tripulante_id,
                    missao_id,
                    data_pernoite,
                    tipo_pernoite,
                    quantidade,
                    get_optional_limited_text(request.form, "observacoes", "Observações"),
                ),
            ).fetchone()
            audit_event(db, "pernoite_operacional", created["id"], "create", novo=state)
            db.commit()
            clear_panel_cache("produtividade:")
            flash("Pernoite registrado com sucesso.", "success")
            return redirect(url_for("operacoes.pernoites_list"))
        except psycopg2.Error:
            rollback_db(db)
            flash("Não foi possível salvar o pernoite. Verifique os dados e tente novamente.", "error")
            db = get_db()
            opts = get_pernoite_form_options(db)
            return _render_pernoite_form_legacy(pernoite=state, options=opts), 400
    db = get_db()
    opts = get_pernoite_form_options(db)
    return _render_pernoite_form_legacy(pernoite=None, options=opts)


@operacoes_bp.route("/pernoites/<int:pernoite_id>/editar", methods=["GET", "POST"])
@permission_required("pernoites:edit")
def pernoites_edit(pernoite_id):
    db = get_db()
    pernoite = db.execute("SELECT * FROM pernoites_operacionais WHERE id = %s", (pernoite_id,)).fetchone()
    if not pernoite:
        abort(404)
    if request.method == "POST":
        state = build_pernoite_form_state(request.form)
        try:
            tripulante_id = get_required_int(request.form, "tripulante_id", "Tripulante")
            missao_id = get_optional_int(request.form, "missao_id", "Missão")
            data_pernoite = get_required_date(request.form, "data_pernoite", "Data do pernoite")
            tipo_pernoite = get_required_text(request.form, "tipo_pernoite", "Tipo de pernoite")
            if tipo_pernoite not in PERNOITE_TIPO_OPTIONS:
                raise ValueError("Tipo de pernoite inválido.")
            quantidade = get_required_int(request.form, "quantidade", "Quantidade")
            if quantidade <= 0:
                raise ValueError("A quantidade deve ser maior que zero.")
            validate_pernoite_references(db, tripulante_id=tripulante_id, missao_id=missao_id)
        except ValueError as exc:
            flash(str(exc), "error")
            state["id"] = pernoite_id
            db = get_db()
            opts = get_pernoite_form_options(db)
            return _render_pernoite_form_legacy(pernoite=state, options=opts), 400
        try:
            db.execute(
                """
                UPDATE pernoites_operacionais
                SET tripulante_id = %s, missao_id = %s, data_pernoite = %s,
                    tipo_pernoite = %s, quantidade = %s, observacoes = %s
                WHERE id = %s
                """,
                (
                    tripulante_id,
                    missao_id,
                    data_pernoite,
                    tipo_pernoite,
                    quantidade,
                    get_optional_limited_text(request.form, "observacoes", "Observações"),
                    pernoite_id,
                ),
            )
            audit_event(db, "pernoite_operacional", pernoite_id, "update", anterior=pernoite, novo=state)
            db.commit()
            clear_panel_cache("produtividade:")
            flash("Pernoite atualizado com sucesso.", "success")
            return redirect(url_for("operacoes.pernoites_list"))
        except psycopg2.Error:
            rollback_db(db)
            flash("Não foi possível atualizar o pernoite. Verifique os dados e tente novamente.", "error")
            state["id"] = pernoite_id
            db = get_db()
            opts = get_pernoite_form_options(db)
            return _render_pernoite_form_legacy(pernoite=state, options=opts), 400
    db = get_db()
    opts = get_pernoite_form_options(db)
    return _render_pernoite_form_legacy(pernoite=pernoite, options=opts)


@operacoes_bp.route("/pernoites/<int:pernoite_id>/excluir", methods=["POST"])
@permission_required("pernoites:delete")
def pernoites_delete(pernoite_id):
    db = get_db()
    pernoite = db.execute("SELECT * FROM pernoites_operacionais WHERE id = %s", (pernoite_id,)).fetchone()
    if not pernoite:
        abort(404)
    audit_event(db, "pernoite_operacional", pernoite_id, "delete", anterior=pernoite)
    db.execute("DELETE FROM pernoites_operacionais WHERE id = %s", (pernoite_id,))
    db.commit()
    clear_panel_cache("produtividade:")
    flash("Pernoite excluído com sucesso.", "success")
    return redirect(url_for("operacoes.pernoites_list"))
