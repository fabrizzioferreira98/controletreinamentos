from datetime import datetime
from decimal import Decimal

try:
    import psycopg2
except ImportError:
    psycopg2 = None  # type: ignore[assignment]
from flask import Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ...auth import permission_required
from ...constants import TRIPULANTE_FUNCAO_OPTIONS
from ...core.audit_utils import audit_event, rollback_db
from ...core.frontend_routes import frontend_compat_enabled, redirect_to_frontend
from ...core.http_contract import programmatic_json
from ...core.http_utils import (
    get_optional_decimal,
    get_optional_limited_text,
    get_required_int,
    get_required_text,
    safe_next_url,
    safe_pdf_filename,
)
from ...core.utils import format_competencia_label, json_response_with_etag
from ...db import fetch_unique_bases, get_db
from ...produtividade import BONIFICACAO_CATEGORIAS_ATIVAS, calculate_competencia_consolidada, moeda, parse_competencia
from ...reports import build_produtividade_consolidado_pdf
from ...repositories.dashboard_cache import (
    clear_panel_cache,
    get_panel_cache,
    set_panel_cache,
)
from ...repositories.queries import fetch_competencias_disponiveis, fetch_produtividade_conferencias_map
from ...service_layers.domain_validation import find_duplicate_adicional_excepcional
from ...service_layers.form_builders import build_adicional_excepcional_form_state
from ...service_layers.form_options import get_adicional_excepcional_form_options
from . import relatorios_bp


def _render_adicional_excepcional_form_legacy(adicional=None, *, options: dict):
    state = dict(adicional) if adicional else None
    if state and state.get("valor") is not None:
        state["valor"] = f"{Decimal(str(state['valor'])):.2f}".replace(".", ",")
    return render_template(
        "produtividade_adicional_form.html",
        adicional=state,
        tripulantes=options.get("tripulantes", []),
    )


@relatorios_bp.route("/produtividade/adicionais")
@permission_required("produtividade_adicionais:view")
def produtividade_adicionais_list():
    db = get_db()
    competencia = parse_competencia(request.args.get("competencia", ""))
    rows = db.execute(
        """
        SELECT a.*, c.nome AS tripulante_nome, c.base
        FROM produtividade_adicionais_excepcionais a
        JOIN tripulantes c ON c.id = a.tripulante_id
        WHERE a.competencia = %s
        ORDER BY c.nome
        """,
        (competencia,),
    ).fetchall()
    return render_template("produtividade_adicionais_list.html", rows=rows, competencia=competencia)


@relatorios_bp.route("/produtividade/adicionais/novo", methods=["GET", "POST"])
@permission_required("produtividade_adicionais:create")
def produtividade_adicionais_new():
    db = get_db()
    if request.method == "POST":
        state = build_adicional_excepcional_form_state(request.form)
        try:
            tripulante_id = get_required_int(request.form, "tripulante_id", "Tripulante")
            competencia = parse_competencia(get_required_text(request.form, "competencia", "Competência"))
            valor = get_optional_decimal(request.form, "valor", "Valor")
            if valor < 0:
                raise ValueError("O valor não pode ser negativo.")
            ativo = bool(request.form.get("ativo"))
            if ativo and find_duplicate_adicional_excepcional(
                db,
                tripulante_id=tripulante_id,
                competencia=competencia,
            ):
                raise ValueError("Já existe adicional excepcional ativo para este tripulante na competência informada.")
        except ValueError as exc:
            flash(str(exc), "error")
            db = get_db()
            opts = get_adicional_excepcional_form_options(db)
            return _render_adicional_excepcional_form_legacy(adicional=state, options=opts), 400
        try:
            created = db.execute(
                """
                INSERT INTO produtividade_adicionais_excepcionais
                (tripulante_id, competencia, valor, observacao, ativo)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    tripulante_id,
                    competencia,
                    valor,
                    get_optional_limited_text(request.form, "observacao", "Observação"),
                    ativo,
                ),
            ).fetchone()
            audit_event(db, "produtividade_adicional_excepcional", created["id"], "create", novo=state)
            db.commit()
            clear_panel_cache("produtividade:")
            flash("Adicional excepcional cadastrado.", "success")
            return redirect(url_for("relatorios.produtividade_adicionais_list", competencia=competencia))
        except psycopg2.IntegrityError:
            rollback_db(db)
            flash("Já existe adicional excepcional ativo para este tripulante na competência informada.", "error")
            db = get_db()
            opts = get_adicional_excepcional_form_options(db)
            return _render_adicional_excepcional_form_legacy(adicional=state, options=opts), 400
    db = get_db()
    opts = get_adicional_excepcional_form_options(db)
    return _render_adicional_excepcional_form_legacy(adicional=None, options=opts)


@relatorios_bp.route("/produtividade/adicionais/<int:adicional_id>/editar", methods=["GET", "POST"])
@permission_required("produtividade_adicionais:edit")
def produtividade_adicionais_edit(adicional_id):
    db = get_db()
    adicional = db.execute("SELECT * FROM produtividade_adicionais_excepcionais WHERE id = %s", (adicional_id,)).fetchone()
    if not adicional:
        abort(404)
    if request.method == "POST":
        state = build_adicional_excepcional_form_state(request.form)
        try:
            tripulante_id = get_required_int(request.form, "tripulante_id", "Tripulante")
            competencia = parse_competencia(get_required_text(request.form, "competencia", "Competência"))
            valor = get_optional_decimal(request.form, "valor", "Valor")
            if valor < 0:
                raise ValueError("O valor não pode ser negativo.")
            ativo = bool(request.form.get("ativo"))
            if ativo and find_duplicate_adicional_excepcional(
                db,
                tripulante_id=tripulante_id,
                competencia=competencia,
                exclude_id=adicional_id,
            ):
                raise ValueError("Já existe adicional excepcional ativo para este tripulante na competência informada.")
        except ValueError as exc:
            flash(str(exc), "error")
            state["id"] = adicional_id
            db = get_db()
            opts = get_adicional_excepcional_form_options(db)
            return _render_adicional_excepcional_form_legacy(adicional=state, options=opts), 400
        try:
            db.execute(
                """
                UPDATE produtividade_adicionais_excepcionais
                SET tripulante_id = %s, competencia = %s, valor = %s, observacao = %s, ativo = %s
                WHERE id = %s
                """,
                (
                    tripulante_id,
                    competencia,
                    valor,
                    get_optional_limited_text(request.form, "observacao", "Observação"),
                    ativo,
                    adicional_id,
                ),
            )
            audit_event(db, "produtividade_adicional_excepcional", adicional_id, "update", anterior=adicional, novo=state)
            db.commit()
            clear_panel_cache("produtividade:")
            flash("Adicional excepcional atualizado.", "success")
            return redirect(url_for("relatorios.produtividade_adicionais_list", competencia=competencia))
        except psycopg2.IntegrityError:
            rollback_db(db)
            flash("Já existe adicional excepcional ativo para este tripulante na competência informada.", "error")
            state["id"] = adicional_id
            db = get_db()
            opts = get_adicional_excepcional_form_options(db)
            return _render_adicional_excepcional_form_legacy(adicional=state, options=opts), 400
    db = get_db()
    opts = get_adicional_excepcional_form_options(db)
    return _render_adicional_excepcional_form_legacy(adicional=adicional, options=opts)


@relatorios_bp.route("/produtividade/adicionais/<int:adicional_id>/excluir", methods=["POST"])
@permission_required("produtividade_adicionais:delete")
def produtividade_adicionais_delete(adicional_id):
    db = get_db()
    adicional = db.execute("SELECT * FROM produtividade_adicionais_excepcionais WHERE id = %s", (adicional_id,)).fetchone()
    if not adicional:
        abort(404)
    competencia = adicional["competencia"]
    audit_event(db, "produtividade_adicional_excepcional", adicional_id, "delete", anterior=adicional)
    db.execute("DELETE FROM produtividade_adicionais_excepcionais WHERE id = %s", (adicional_id,))
    db.commit()
    clear_panel_cache("produtividade:")
    flash("Adicional excepcional excluído.", "success")
    return redirect(url_for("relatorios.produtividade_adicionais_list", competencia=competencia))


@relatorios_bp.route("/produtividade")
@login_required
def produtividade_consolidado():
    if frontend_compat_enabled():
        return redirect_to_frontend(
            "#/relatorios/produtividade",
            query={
                "competencia": request.args.get("competencia", "").strip(),
                "nome": request.args.get("nome", "").strip(),
                "base": request.args.get("base", "").strip(),
                "funcao": request.args.get("funcao", "").strip(),
                "categoria": request.args.get("categoria", "").strip(),
                "ordenacao": request.args.get("ordenacao", "valor_final").strip(),
            },
        )
    db = get_db()
    competencia = parse_competencia(request.args.get("competencia", ""))
    nome = request.args.get("nome", "").strip()
    base = request.args.get("base", "").strip()
    funcao = request.args.get("funcao", "").strip()
    categoria = request.args.get("categoria", "").strip()
    ordenacao = request.args.get("ordenacao", "valor_final").strip()

    cache_key = (
        f"produtividade:list:{competencia}:{nome.lower()}:{base.lower()}:"
        f"{funcao.lower()}:{categoria.lower()}:{ordenacao.lower()}"
    )
    cached_payload = get_panel_cache(cache_key)
    if cached_payload is not None:
        return render_template("produtividade_consolidado.html", **cached_payload)

    context = calculate_competencia_consolidada(
        db,
        competencia=competencia,
        base=base,
        funcao=funcao,
        categoria=categoria,
        nome=nome,
    )
    rows = context["rows"]
    if ordenacao == "produtividade":
        rows.sort(key=lambda item: (item["total_produtividade"], item["valor_final_mes"]), reverse=True)
    elif ordenacao == "nome":
        rows.sort(key=lambda item: item["tripulante_nome"].lower())
    elif ordenacao == "base":
        rows.sort(key=lambda item: (item["base"], item["tripulante_nome"].lower()))

    conferencias_map = fetch_produtividade_conferencias_map(
        db,
        competencia=context["competencia"],
        tripulante_ids=[row["tripulante_id"] for row in rows],
    )
    for row in rows:
        row["conferencia"] = conferencias_map.get(row["tripulante_id"])

    competencias_disponiveis = fetch_competencias_disponiveis(db)
    if competencia not in competencias_disponiveis:
        competencias_disponiveis.insert(0, competencia)
    bases_cache_key = "produtividade:bases"
    bases = get_panel_cache(bases_cache_key)
    if bases is None:
        bases = [row["nome"] for row in fetch_unique_bases(db)]
        set_panel_cache(bases_cache_key, list(bases))

    payload = {
        "competencia": context["competencia"],
        "competencia_label": format_competencia_label(context["competencia"]),
        "competencias_disponiveis": competencias_disponiveis,
        "emitted_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "format_competencia_label": format_competencia_label,
        "rows": rows,
        "summary": context["summary"],
        "filtros": {"nome": nome, "base": base, "funcao": funcao, "categoria": categoria, "ordenacao": ordenacao},
        "funcoes": TRIPULANTE_FUNCAO_OPTIONS,
        "categorias": BONIFICACAO_CATEGORIAS_ATIVAS,
        "bases": bases,
        "moeda": moeda,
    }
    set_panel_cache(cache_key, payload)
    return render_template("produtividade_consolidado.html", **payload)


@relatorios_bp.route("/produtividade/conferencia", methods=["POST"])
@login_required
def produtividade_conferencia_set():
    db = get_db()
    next_url = safe_next_url(request.form.get("next"), url_for("relatorios.produtividade_consolidado"))
    try:
        tripulante_id = get_required_int(request.form, "tripulante_id", "Tripulante")
        competencia = parse_competencia(get_required_text(request.form, "competencia", "Competência"))
        action = (request.form.get("action", "") or "").strip().lower()
        if action not in {"mark", "unmark"}:
            raise ValueError("Ação de conferência inválida.")
        tripulante = db.execute("SELECT id FROM tripulantes WHERE id = %s", (tripulante_id,)).fetchone()
        if not tripulante:
            raise ValueError("Tripulante inválido para conferência.")
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(next_url)

    if action == "mark":
        previous = db.execute(
            "SELECT * FROM produtividade_conferencias WHERE tripulante_id = %s AND competencia = %s",
            (tripulante_id, competencia),
        ).fetchone()
        db.execute(
            """
            INSERT INTO produtividade_conferencias (tripulante_id, competencia, conferido_por, conferido_em)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (tripulante_id, competencia)
            DO UPDATE SET conferido_por = EXCLUDED.conferido_por, conferido_em = NOW()
            """,
            (tripulante_id, competencia, int(current_user.id)),
        )
        current = db.execute(
            "SELECT * FROM produtividade_conferencias WHERE tripulante_id = %s AND competencia = %s",
            (tripulante_id, competencia),
        ).fetchone()
        audit_event(
            db,
            "produtividade_conferencia",
            tripulante_id,
            "update" if previous else "create",
            anterior=dict(previous) if previous else None,
            novo=dict(current) if current else None,
            observacao=f"competencia={competencia}",
        )
        db.commit()
        flash("Conferência registrada com sucesso.", "success")
        return redirect(next_url)

    previous = db.execute(
        "SELECT * FROM produtividade_conferencias WHERE tripulante_id = %s AND competencia = %s",
        (tripulante_id, competencia),
    ).fetchone()
    if previous:
        db.execute(
            "DELETE FROM produtividade_conferencias WHERE tripulante_id = %s AND competencia = %s",
            (tripulante_id, competencia),
        )
        audit_event(
            db,
            "produtividade_conferencia",
            tripulante_id,
            "delete",
            anterior=dict(previous),
            observacao=f"competencia={competencia}",
        )
        db.commit()
    flash("Conferência removida.", "success")
    return redirect(next_url)


@relatorios_bp.route("/produtividade/export.pdf")
@login_required
def produtividade_consolidado_export_pdf():
    db = get_db()
    competencia = parse_competencia(request.args.get("competencia", ""))
    nome = request.args.get("nome", "").strip()
    base = request.args.get("base", "").strip()
    funcao = request.args.get("funcao", "").strip()
    categoria = request.args.get("categoria", "").strip()
    ordenacao = request.args.get("ordenacao", "valor_final").strip()

    context = calculate_competencia_consolidada(
        db,
        competencia=competencia,
        base=base,
        funcao=funcao,
        categoria=categoria,
        nome=nome,
    )
    rows = context["rows"]
    if ordenacao == "produtividade":
        rows.sort(key=lambda item: (item["total_produtividade"], item["valor_final_mes"]), reverse=True)
    elif ordenacao == "nome":
        rows.sort(key=lambda item: item["tripulante_nome"].lower())
    elif ordenacao == "base":
        rows.sort(key=lambda item: (item["base"], item["tripulante_nome"].lower()))

    emitted_at = datetime.now().strftime("%d/%m/%Y %H:%M")
    pdf_bytes = build_produtividade_consolidado_pdf(
        competencia=context["competencia"],
        filtros_aplicados={
            "nome": nome or "-",
            "base": base or "-",
            "funcao": funcao or "-",
            "categoria": categoria or "-",
        },
        summary=context["summary"],
        rows=rows,
        emitted_at=emitted_at,
    )
    filename = safe_pdf_filename(
        f"produtividade_consolidada_{context['competencia']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
        fallback="produtividade_consolidada.pdf",
    )
    response = Response(pdf_bytes, mimetype="application/pdf")
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Cache-Control"] = "no-store"
    return response


@relatorios_bp.route("/produtividade/painel-tv")
@login_required
def produtividade_painel_tv():
    db = get_db()
    competencia = parse_competencia(request.args.get("competencia", ""))
    context = calculate_competencia_consolidada(db, competencia=competencia)
    initial_payload = {
        "competencia": context["competencia"],
        "summary": {
            key: float(value) if isinstance(value, Decimal) else value
            for key, value in context["summary"].items()
        },
        "rows": [
            {
                "tripulante_id": row["tripulante_id"],
                "tripulante_nome": row["tripulante_nome"],
                "base": row["base"],
                "categoria": row["categoria"],
                "funcao": row["funcao"],
                "total_missoes_validas": row["total_missoes_validas"],
                "total_produtividade": float(row["total_produtividade"]),
                "valor_final_mes": float(row["valor_final_mes"]),
            }
            for row in context["rows"]
        ],
        "updated_at": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
    }
    return render_template(
        "produtividade_painel_tv.html",
        competencia=competencia,
        initial_payload=initial_payload,
    )


@relatorios_bp.route("/produtividade/painel-tv/dados")
@login_required
@programmatic_json
def produtividade_painel_tv_dados():
    db = get_db()
    competencia = parse_competencia(request.args.get("competencia", ""))
    cache_key = f"produtividade:{competencia}"
    cached = get_panel_cache(cache_key)
    if cached is not None:
        return json_response_with_etag(cached, max_age=20)
    context = calculate_competencia_consolidada(db, competencia=competencia)
    payload = {
        "competencia": context["competencia"],
        "summary": {
            key: float(value) if isinstance(value, Decimal) else value
            for key, value in context["summary"].items()
        },
        "rows": [
            {
                "tripulante_id": row["tripulante_id"],
                "tripulante_nome": row["tripulante_nome"],
                "base": row["base"],
                "categoria": row["categoria"],
                "funcao": row["funcao"],
                "total_missoes_validas": row["total_missoes_validas"],
                "total_pernoites": row["total_pernoites_cobertura"] + row["total_pernoites_operacionais_elegiveis"],
                "total_produtividade": float(row["total_produtividade"]),
                "valor_final_mes": float(row["valor_final_mes"]),
                "criterio_fechamento": row["criterio_fechamento"],
            }
            for row in context["rows"]
        ],
        "updated_at": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
    }
    set_panel_cache(cache_key, payload)
    return json_response_with_etag(payload, max_age=20)
