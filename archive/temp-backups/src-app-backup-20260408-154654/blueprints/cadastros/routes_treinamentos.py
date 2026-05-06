from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta

try:
    import psycopg2
except ImportError:
    psycopg2 = None  # type: ignore[assignment]
from flask import Response, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ...auth import permission_required
from ...core.audit_utils import audit_event, rollback_db
from ...core.frontend_routes import frontend_compat_enabled, redirect_to_frontend
from ...core.http_utils import (
    get_optional_date,
    get_optional_int,
    get_optional_limited_text,
    get_optional_text,
    get_required_int,
    resolve_pagination_state,
    safe_pdf_filename,
)
from ...db import get_db
from ...infra.media_storage import delete_media_ref, read_media_bytes, write_training_attachment
from ...reports import build_habilitacoes_consolidado_pdf
from ...repositories.dashboard_cache import (
    build_habilitacoes_consolidadas_context,
    clear_panel_cache,
    fetch_cached_rows,
    get_panel_cache,
    set_panel_cache,
)
from ...repositories.queries import fetch_training_page
from ...service_layers.domain_validation import (
    resolve_due_date,
    training_dates_are_valid,
    validate_pdf_upload,
    validate_training_references,
)
from ...service_layers.form_builders import build_treinamento_form_state
from ...service_layers.form_options import get_training_form_options
from ...services import business_today
from . import cadastros_bp


def _render_training_form_legacy(treinamento=None, *, options: dict):
    training_data = dict(treinamento) if treinamento else None
    if training_data is not None:
        training_data.setdefault("due_date_mode", "manual" if training_data.get("data_vencimento") else "auto")
    attachments = options.get("attachments", [])
    return render_template(
        "treinamentos_form.html",
        treinamento=training_data,
        attachments=attachments,
        attachment_max_mb=8,
        tripulantes=options.get("tripulantes", []),
        equipamentos=options.get("equipamentos", []),
        tipos=options.get("tipos", []),
    )


@cadastros_bp.route("/treinamentos")
@login_required
def treinamentos_list():
    if frontend_compat_enabled():
        return redirect_to_frontend(
            "#/treinamentos",
            query={
                "tripulante": request.args.get("tripulante", "").strip(),
                "equipamento": request.args.get("equipamento", "").strip(),
                "tipo": request.args.get("tipo", "").strip(),
                "status": request.args.get("status", "").strip(),
                "periodo": request.args.get("periodo", "").strip(),
            },
        )
    db = get_db()
    tripulante = request.args.get("tripulante", "").strip()
    equipamento = request.args.get("equipamento", "").strip()
    tipo = request.args.get("tipo", "").strip()
    status = request.args.get("status", "").strip()
    periodo = request.args.get("periodo", "").strip()

    clauses = []
    params = []
    if tripulante:
        if not tripulante.isdigit():
            flash("Filtro de tripulante inválido.", "error")
            tripulante = ""
        else:
            clauses.append("c.id = %s")
            params.append(int(tripulante))
    if equipamento:
        if not equipamento.isdigit():
            flash("Filtro de equipamento inválido.", "error")
            equipamento = ""
        else:
            clauses.append("e.id = %s")
            params.append(int(equipamento))
    if tipo:
        if not tipo.isdigit():
            flash("Filtro de tipo inválido.", "error")
            tipo = ""
        else:
            clauses.append("tt.id = %s")
            params.append(int(tipo))
    today = business_today()
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

    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    resumo_row = db.execute(
        f"""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE t.data_vencimento IS NULL) AS sem_informacao,
            COUNT(*) FILTER (WHERE t.data_vencimento < %s) AS vencido,
            COUNT(*) FILTER (
                WHERE t.data_vencimento >= %s
                  AND t.data_vencimento <= %s
            ) AS a_vencer,
            COUNT(*) FILTER (WHERE t.data_vencimento > %s) AS regular
        FROM treinamentos t
        JOIN tripulantes c ON c.id = t.tripulante_id
        LEFT JOIN equipamentos e ON e.id = t.equipamento_id
        JOIN tipos_treinamento tt ON tt.id = t.tipo_treinamento_id
        {where_clause}
        """,
        (today, today, today + timedelta(days=30), today + timedelta(days=30), *tuple(params)),
    ).fetchone()

    total = resumo_row["total"]
    paging = resolve_pagination_state(
        total,
        endpoint="cadastros.treinamentos_list",
        tripulante=tripulante,
        equipamento=equipamento,
        tipo=tipo,
        status=status,
        periodo=periodo,
    )
    db = get_db()
    treinamentos = fetch_training_page(db,
        where_clause,
        tuple(params),
        limit=paging["per_page"],
        offset=paging["offset"],
    )

    resumo = {
        "total": resumo_row["total"],
        "vencido": resumo_row["vencido"],
        "a vencer": resumo_row["a_vencer"],
        "regular": resumo_row["regular"],
        "sem informação": resumo_row["sem_informacao"],
    }
    return render_template(
        "treinamentos_list.html",
        treinamentos=treinamentos,
        resumo=resumo,
        filtros={
            "tripulante": tripulante,
            "equipamento": equipamento,
            "tipo": tipo,
            "status": status,
            "periodo": periodo,
        },
        tripulantes=fetch_cached_rows(
            db,
            cache_key="options:tripulantes:id_nome",
            query="SELECT id, nome FROM tripulantes ORDER BY nome",
        ),
        equipamentos=fetch_cached_rows(
            db,
            cache_key="options:equipamentos:id_nome",
            query="SELECT id, nome FROM equipamentos ORDER BY nome",
        ),
        tipos=fetch_cached_rows(
            db,
            cache_key="options:tipos_treinamento:id_nome",
            query="SELECT id, nome FROM tipos_treinamento ORDER BY nome",
        ),
        pagination=paging["pagination"],
    )


@cadastros_bp.route("/treinamentos/consolidado")
@login_required
def treinamentos_consolidado():
    if frontend_compat_enabled():
        return redirect_to_frontend(
            "#/relatorios/habilitacoes",
            query={
                "nome": request.args.get("nome", "").strip(),
                "base": request.args.get("base", "").strip(),
                "status": request.args.get("status", "").strip(),
                "tipo": request.args.get("tipo", "").strip(),
                "ordenacao": request.args.get("ordenacao", "").strip(),
            },
        )
    db = get_db()
    nome = request.args.get("nome", "").strip()
    base = request.args.get("base", "").strip()
    status = request.args.get("status", "").strip()
    tipo = request.args.get("tipo", "").strip()
    ordenacao = request.args.get("ordenacao", "").strip()

    cache_key = (
        f"habilitacoes:consolidado:{nome.lower()}:{base.lower()}:"
        f"{status.lower()}:{tipo.lower()}:{ordenacao.lower()}"
    )
    context = get_panel_cache(cache_key)
    if context is None:
        context = build_habilitacoes_consolidadas_context(
            db,
            nome=nome,
            base=base,
            status=status,
            tipo=tipo,
            ordenacao=ordenacao,
        )
        set_panel_cache(cache_key, context)
    context["emitted_at"] = datetime.now().strftime("%d/%m/%Y %H:%M")
    return render_template("treinamentos_consolidado.html", **context)


@cadastros_bp.route("/treinamentos/consolidado/relatorio")
@login_required
def treinamentos_consolidado_relatorio():
    db = get_db()
    nome = request.args.get("nome", "").strip()
    base = request.args.get("base", "").strip()
    status = request.args.get("status", "").strip()
    tipo = request.args.get("tipo", "").strip()
    ordenacao = request.args.get("ordenacao", "").strip()

    cache_key = (
        f"habilitacoes:consolidado:{nome.lower()}:{base.lower()}:"
        f"{status.lower()}:{tipo.lower()}:{ordenacao.lower()}"
    )
    context = get_panel_cache(cache_key)
    if context is None:
        context = build_habilitacoes_consolidadas_context(
            db,
            nome=nome,
            base=base,
            status=status,
            tipo=tipo,
            ordenacao=ordenacao,
        )
        set_panel_cache(cache_key, context)
    context["emitted_at"] = datetime.now().strftime("%d/%m/%Y %H:%M")
    context["filtros_aplicados"] = {
        "nome": nome or "-",
        "base": base or "-",
        "status": status or "-",
        "tipo": tipo or "-",
        "ordenacao": ordenacao or "criticidade",
    }
    return render_template("treinamentos_consolidado_relatorio.html", **context)


@cadastros_bp.route("/treinamentos/consolidado/export.pdf")
@login_required
def treinamentos_consolidado_export_pdf():
    db = get_db()
    nome = request.args.get("nome", "").strip()
    base = request.args.get("base", "").strip()
    status = request.args.get("status", "").strip()
    tipo = request.args.get("tipo", "").strip()
    ordenacao = request.args.get("ordenacao", "").strip()

    context = build_habilitacoes_consolidadas_context(
        db,
        nome=nome,
        base=base,
        status=status,
        tipo=tipo,
        ordenacao=ordenacao,
    )
    emitted_at = datetime.now().strftime("%d/%m/%Y %H:%M")
    pdf_bytes = build_habilitacoes_consolidado_pdf(
        summary=context["summary"],
        tripulantes_grouped=context["tripulantes_grouped"],
        filtros_aplicados={
            "nome": nome or "-",
            "base": base or "-",
            "status": status or "-",
            "tipo": tipo or "-",
        },
        emitted_at=emitted_at,
    )
    filename = safe_pdf_filename(
        f"consolidado_habilitacoes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
        fallback="consolidado_habilitacoes.pdf",
    )
    response = Response(pdf_bytes, mimetype="application/pdf")
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Cache-Control"] = "no-store"
    return response


@cadastros_bp.route("/treinamentos/consolidado/export.csv")
@login_required
def treinamentos_consolidado_export_csv():
    db = get_db()
    nome = request.args.get("nome", "").strip()
    base = request.args.get("base", "").strip()
    status = request.args.get("status", "").strip()
    tipo = request.args.get("tipo", "").strip()
    ordenacao = request.args.get("ordenacao", "").strip()

    context = build_habilitacoes_consolidadas_context(
        db,
        nome=nome,
        base=base,
        status=status,
        tipo=tipo,
        ordenacao=ordenacao,
    )

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(
        [
            "Tripulante",
            "Base",
            "Funcao/Cargo",
            "Habilitacao",
            "Data de vencimento",
            "Dias restantes",
            "Status",
        ]
    )

    for group in context["tripulantes_grouped"]:
        for item in group["habilitacoes"]:
            if item.get("is_placeholder"):
                continue
            writer.writerow(
                [
                    group["tripulante_nome"],
                    group.get("base") or "-",
                    group.get("funcao_cargo") or "-",
                    item.get("habilitacao_nome") or "-",
                    item.get("data_vencimento") or "Sem vencimento informado",
                    item.get("days_remaining_label") or "Sem vencimento informado",
                    item.get("status_label") or "-",
                ]
            )

    filename = f"consolidado_habilitacoes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    csv_content = output.getvalue()
    response = Response(f"\ufeff{csv_content}", content_type="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response


@cadastros_bp.route("/treinamentos/novo", methods=["GET", "POST"])
@login_required
def treinamentos_new():
    if request.method == "GET" and frontend_compat_enabled():
        return redirect_to_frontend("#/treinamentos/new")
    db = get_db()
    if request.method == "POST":
        treinamento_state = build_treinamento_form_state(request.form)
        try:
            tripulante_id = get_required_int(request.form, "tripulante_id", "Tripulante")
            equipamento_id = get_optional_int(request.form, "equipamento_id", "Equipamento")
            tipo_treinamento_id = get_required_int(request.form, "tipo_treinamento_id", "Tipo de treinamento")
            data_realizacao = get_optional_date(request.form, "data_realizacao", "Data de realização")
            due_date_mode = get_optional_text(request.form, "due_date_mode") or "auto"
            validate_training_references(db, tripulante_id, tipo_treinamento_id, equipamento_id)
            data_vencimento = resolve_due_date(
                db,
                tipo_treinamento_id,
                data_realizacao,
                get_optional_date(request.form, "data_vencimento", "Data de vencimento"),
                due_date_mode,
            )
            treinamento_state["data_vencimento"] = data_vencimento
            treinamento_state["due_date_mode"] = due_date_mode
        except ValueError as exc:
            flash(str(exc), "error")
            db = get_db()
            opts = get_training_form_options(db, selected_equipment_id=treinamento_state.get("equipamento_id"), selected_tipo_id=treinamento_state.get("tipo_treinamento_id"))
            return _render_training_form_legacy(treinamento=treinamento_state, options=opts), 400
        if not training_dates_are_valid(data_realizacao, data_vencimento):
            flash("A data de realização não pode ser posterior à data de vencimento.", "error")
            db = get_db()
            opts = get_training_form_options(db, selected_equipment_id=treinamento_state.get("equipamento_id"), selected_tipo_id=treinamento_state.get("tipo_treinamento_id"))
            return _render_training_form_legacy(treinamento=treinamento_state, options=opts), 400
        try:
            created = db.execute(
                """
                INSERT INTO treinamentos
                (tripulante_id, equipamento_id, tipo_treinamento_id, data_realizacao, data_vencimento, observacao)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    tripulante_id,
                    equipamento_id,
                    tipo_treinamento_id,
                    data_realizacao,
                    data_vencimento,
                    get_optional_limited_text(request.form, "observacao", "Observação"),
                ),
            ).fetchone()
            audit_event(db, "treinamento", created["id"], "create", novo=treinamento_state)
            db.commit()
            clear_panel_cache()
            flash("Treinamento cadastrado com sucesso.", "success")
        except psycopg2.IntegrityError:
            rollback_db(db)
            flash("Não foi possível salvar o treinamento com os dados informados.", "error")
            db = get_db()
            opts = get_training_form_options(db, selected_equipment_id=treinamento_state.get("equipamento_id"), selected_tipo_id=treinamento_state.get("tipo_treinamento_id"))
            return _render_training_form_legacy(treinamento=treinamento_state, options=opts), 400
        return redirect(url_for("cadastros.treinamentos_list"))

    db = get_db()
    opts = get_training_form_options(db)
    return _render_training_form_legacy(treinamento=None, options=opts)


@cadastros_bp.route("/treinamentos/<int:treinamento_id>/editar", methods=["GET", "POST"])
@login_required
def treinamentos_edit(treinamento_id):
    if request.method == "GET" and frontend_compat_enabled():
        return redirect_to_frontend(f"#/treinamentos/{treinamento_id}")
    db = get_db()
    treinamento = db.execute("SELECT * FROM treinamentos WHERE id = %s", (treinamento_id,)).fetchone()
    if not treinamento:
        abort(404)
    if request.method == "POST":
        treinamento_state = build_treinamento_form_state(request.form)
        try:
            tripulante_id = get_required_int(request.form, "tripulante_id", "Tripulante")
            equipamento_id = get_optional_int(request.form, "equipamento_id", "Equipamento")
            tipo_treinamento_id = get_required_int(request.form, "tipo_treinamento_id", "Tipo de treinamento")
            data_realizacao = get_optional_date(request.form, "data_realizacao", "Data de realização")
            due_date_mode = get_optional_text(request.form, "due_date_mode") or "auto"
            validate_training_references(db, tripulante_id, tipo_treinamento_id, equipamento_id, current_training=treinamento)
            data_vencimento = resolve_due_date(
                db,
                tipo_treinamento_id,
                data_realizacao,
                get_optional_date(request.form, "data_vencimento", "Data de vencimento"),
                due_date_mode,
            )
            treinamento_state["data_vencimento"] = data_vencimento
            treinamento_state["due_date_mode"] = due_date_mode
        except ValueError as exc:
            flash(str(exc), "error")
            db = get_db()
            opts = get_training_form_options(db, treinamento_id=treinamento_id, selected_equipment_id=treinamento_state.get("equipamento_id"), selected_tipo_id=treinamento_state.get("tipo_treinamento_id"))
            return _render_training_form_legacy(treinamento=treinamento_state, options=opts), 400
        if not training_dates_are_valid(data_realizacao, data_vencimento):
            flash("A data de realização não pode ser posterior à data de vencimento.", "error")
            db = get_db()
            opts = get_training_form_options(db, treinamento_id=treinamento_id, selected_equipment_id=treinamento_state.get("equipamento_id"), selected_tipo_id=treinamento_state.get("tipo_treinamento_id"))
            return _render_training_form_legacy(treinamento=treinamento_state, options=opts), 400
        try:
            db.execute(
                """
                UPDATE treinamentos
                SET tripulante_id = %s, equipamento_id = %s, tipo_treinamento_id = %s,
                    data_realizacao = %s, data_vencimento = %s, observacao = %s
                WHERE id = %s
                """,
                (
                    tripulante_id,
                    equipamento_id,
                    tipo_treinamento_id,
                    data_realizacao,
                    data_vencimento,
                    get_optional_limited_text(request.form, "observacao", "Observação"),
                    treinamento_id,
                ),
            )
            audit_event(db, "treinamento", treinamento_id, "update", anterior=treinamento, novo=treinamento_state)
            db.commit()
            clear_panel_cache()
            flash("Treinamento atualizado com sucesso.", "success")
        except psycopg2.IntegrityError:
            rollback_db(db)
            flash("Não foi possível atualizar o treinamento com os dados informados.", "error")
            db = get_db()
            opts = get_training_form_options(db, treinamento_id=treinamento_id, selected_equipment_id=treinamento_state.get("equipamento_id"), selected_tipo_id=treinamento_state.get("tipo_treinamento_id"))
            return _render_training_form_legacy(treinamento=treinamento_state, options=opts), 400
        return redirect(url_for("cadastros.treinamentos_list"))

    db = get_db()
    opts = get_training_form_options(db, treinamento_id=treinamento_id, selected_equipment_id=treinamento.get("equipamento_id"), selected_tipo_id=treinamento.get("tipo_treinamento_id"))
    return _render_training_form_legacy(treinamento=treinamento, options=opts)


@cadastros_bp.route("/treinamentos/<int:treinamento_id>/excluir", methods=["POST"])
@permission_required("treinamentos:delete")
def treinamentos_delete(treinamento_id):
    db = get_db()
    treinamento = db.execute(
        """
        SELECT t.id, t.tripulante_id, c.nome AS tripulante_nome
        FROM treinamentos t
        JOIN tripulantes c ON c.id = t.tripulante_id
        WHERE t.id = %s
        """,
        (treinamento_id,),
    ).fetchone()
    if not treinamento:
        abort(404)
    try:
        # Backward-compatible cleanup if legacy FK still blocks training delete.
        db.execute("DELETE FROM notificacoes_treinamento WHERE treinamento_id = %s", (treinamento_id,))
        audit_event(db, "treinamento", treinamento_id, "delete", anterior=treinamento)
        db.execute("DELETE FROM treinamentos WHERE id = %s", (treinamento_id,))
        db.commit()
        clear_panel_cache()
        flash("Treinamento excluído com sucesso.", "success")
    except psycopg2.Error:
        rollback_db(db)
        flash("Não foi possível excluir o treinamento no momento.", "error")
    return redirect(url_for("cadastros.treinamentos_list"))


@cadastros_bp.route("/treinamentos/<int:treinamento_id>/anexos/upload", methods=["POST"])
@permission_required("treinamentos_anexos:create")
def treinamentos_anexo_upload(treinamento_id):
    db = get_db()
    treinamento = db.execute("SELECT id FROM treinamentos WHERE id = %s", (treinamento_id,)).fetchone()
    if not treinamento:
        abort(404)

    payload = None
    try:
        payload = validate_pdf_upload(request.files.get("arquivo_pdf"))
        payload["storage_ref"] = write_training_attachment(
            treinamento["tripulante_id"],
            treinamento.get("tripulante_nome"),
            treinamento_id,
            payload["nome_interno"],
            payload["arquivo_pdf"],
        )
        created = db.execute(
            """
            INSERT INTO treinamento_anexos_pdf
            (
                treinamento_id, nome_original, nome_interno, mime_type, tamanho_bytes,
                storage_ref, arquivo_pdf, arquivo_hash, status, enviado_por
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'ativo', %s)
            RETURNING id
            """,
            (
                treinamento_id,
                payload["nome_original"],
                payload["nome_interno"],
                payload["mime_type"],
                payload["tamanho_bytes"],
                payload["storage_ref"],
                payload["arquivo_pdf"],
                payload["arquivo_hash"],
                int(current_user.id),
            ),
        ).fetchone()
        audit_event(
            db,
            "treinamento_anexo_pdf",
            created["id"],
            "create",
            novo={
                "treinamento_id": treinamento_id,
                "nome_original": payload["nome_original"],
                "mime_type": payload["mime_type"],
                "tamanho_bytes": payload["tamanho_bytes"],
            },
        )
        db.commit()
        flash("PDF anexado com sucesso.", "success")
    except ValueError as exc:
        rollback_db(db)
        delete_media_ref(payload.get("storage_ref") if payload else None)
        flash(str(exc), "error")
    except Exception:
        rollback_db(db)
        delete_media_ref(payload.get("storage_ref") if payload else None)
        current_app.logger.exception("Failed to upload training PDF attachment.")
        flash("Não foi possível anexar o PDF no momento.", "error")
    return redirect(url_for("cadastros.treinamentos_edit", treinamento_id=treinamento_id))


@cadastros_bp.route("/treinamentos/<int:treinamento_id>/anexos/<int:anexo_id>")
@permission_required("treinamentos_anexos:view")
def treinamentos_anexo_get(treinamento_id, anexo_id):
    db = get_db()
    row = db.execute(
        """
        SELECT id, treinamento_id, nome_original, mime_type, storage_ref, arquivo_pdf
        FROM treinamento_anexos_pdf
        WHERE id = %s AND treinamento_id = %s
        """,
        (anexo_id, treinamento_id),
    ).fetchone()
    if not row:
        abort(404)

    safe_name = safe_pdf_filename(row["nome_original"], fallback=f"treinamento_{treinamento_id}_anexo.pdf")
    disposition = "attachment" if request.args.get("download", "").strip() == "1" else "inline"
    payload_bytes = read_media_bytes(
        row.get("storage_ref"),
        fallback_bytes=bytes(row["arquivo_pdf"]) if row.get("arquivo_pdf") is not None else None,
    )
    if not payload_bytes:
        abort(404)
    response = Response(payload_bytes, mimetype=row["mime_type"] or "application/pdf")
    response.headers["Content-Disposition"] = f"{disposition}; filename={safe_name}"
    response.headers["Cache-Control"] = "private, no-store"
    return response


@cadastros_bp.route("/treinamentos/<int:treinamento_id>/anexos/<int:anexo_id>/excluir", methods=["POST"])
@permission_required("treinamentos_anexos:delete")
def treinamentos_anexo_delete(treinamento_id, anexo_id):
    db = get_db()
    row = db.execute(
        """
        SELECT id, treinamento_id, nome_original, mime_type, tamanho_bytes, enviado_por, enviado_em, storage_ref
        FROM treinamento_anexos_pdf
        WHERE id = %s AND treinamento_id = %s
        """,
        (anexo_id, treinamento_id),
    ).fetchone()
    if not row:
        abort(404)
    audit_event(db, "treinamento_anexo_pdf", anexo_id, "delete", anterior=row)
    db.execute("DELETE FROM treinamento_anexos_pdf WHERE id = %s AND treinamento_id = %s", (anexo_id, treinamento_id))
    db.commit()
    delete_media_ref(row.get("storage_ref"))
    flash("Anexo removido com sucesso.", "success")
    return redirect(url_for("cadastros.treinamentos_edit", treinamento_id=treinamento_id))
