from datetime import datetime

from flask import Response, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import login_required

from ...core.audit_utils import audit_event, rollback_db, tripulante_audit_payload
from ...core.http_utils import safe_pdf_filename
from ...core.utils import format_competencia_label
from ...db import get_db
from ...infra.media_storage import delete_media_ref
from ...produtividade import bool_label, calculate_tripulante_competencia, moeda, parse_competencia
from ...reports import build_produtividade_tripulante_pdf, build_tripulante_treinamentos_pdf
from ...repositories.dashboard_cache import clear_panel_cache
from ...repositories.queries import (
    fetch_competencias_tripulante,
    fetch_training_rows,
    fetch_upcoming_training_items_by_tripulante,
)
from ...services import summarize_training_status, training_sort_key, whatsapp_tripulante_link
from ...auth import permission_required
from ...service_layers.domain_validation import sync_linked_pilot_from_tripulante
from . import cadastros_bp


@cadastros_bp.route("/tripulantes/<int:tripulante_id>/excluir", methods=["POST"])
@permission_required("tripulantes:delete")
def tripulantes_delete(tripulante_id):
    db = get_db()
    tripulante = db.execute(
        """
        SELECT id, nome, cpf, licenca_anac, base, status, ativo, foto_storage_ref
        FROM tripulantes
        WHERE id = %s
        """,
        (tripulante_id,),
    ).fetchone()
    if not tripulante:
        abort(404)
    dependency_counts = db.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM treinamentos WHERE tripulante_id = %s) AS treinamentos,
            (SELECT COUNT(*) FROM missao_tripulantes WHERE tripulante_id = %s) AS missoes,
            (SELECT COUNT(*) FROM pernoites_operacionais WHERE tripulante_id = %s) AS pernoites,
            (SELECT COUNT(*) FROM produtividade_adicionais_excepcionais WHERE tripulante_id = %s) AS adicionais,
            (SELECT COUNT(*) FROM produtividade_conferencias WHERE tripulante_id = %s) AS conferencias,
            (SELECT COUNT(*) FROM tripulante_arquivos_pdf WHERE tripulante_id = %s) AS arquivos_file
        """,
        (tripulante_id, tripulante_id, tripulante_id, tripulante_id, tripulante_id, tripulante_id),
    ).fetchone()
    has_business_dependencies = any(
        int(dependency_counts[key] or 0) > 0
        for key in ("treinamentos", "missoes", "pernoites", "adicionais", "conferencias", "arquivos_file")
    )

    try:
        # Preserva histórico operacional quando já existem vínculos de negócio.
        if has_business_dependencies:
            if int(tripulante["ativo"] or 0) == 0:
                flash(
                    "Este tripulante já está inativo e possui vínculos históricos; a exclusão física foi bloqueada para preservar integridade.",
                    "error",
                )
                return redirect(url_for("cadastros.tripulantes_list"))

            db.execute(
                "UPDATE tripulantes SET ativo = 0, status = %s WHERE id = %s",
                ("Afastado", tripulante_id),
            )
            sync_linked_pilot_from_tripulante(
                db,
                tripulante_id=tripulante_id,
                nome=tripulante["nome"],
                licenca_anac=tripulante["licenca_anac"],
                base_nome=tripulante["base"],
                status_text="Afastado",
                is_active=False,
            )
            audit_event(
                db,
                "tripulante",
                tripulante_id,
                "status_change",
                anterior=tripulante_audit_payload(tripulante),
                novo={**tripulante_audit_payload(tripulante), "ativo": False, "status": "Afastado"},
                observacao="Inativação automática aplicada porque existem vínculos históricos.",
            )
            db.commit()
            clear_panel_cache()
            flash(
                "Tripulante inativado com sucesso. A exclusão física foi bloqueada porque existem vínculos históricos.",
                "success",
            )
            return redirect(url_for("cadastros.tripulantes_list"))

        linked_pilot_ids = [
            int(row["id"])
            for row in db.execute(
                "SELECT id FROM pilotos WHERE tripulante_id = %s",
                (tripulante_id,),
            ).fetchall()
        ]
        if linked_pilot_ids:
            db.execute("DELETE FROM historico_status_piloto WHERE piloto_id = ANY(%s)", (linked_pilot_ids,))
            db.execute("DELETE FROM pilotos WHERE id = ANY(%s)", (linked_pilot_ids,))

        audit_event(db, "tripulante", tripulante_id, "delete", anterior=tripulante_audit_payload(tripulante))
        db.execute("DELETE FROM tripulantes WHERE id = %s", (tripulante_id,))
        db.commit()
        delete_media_ref(tripulante.get("foto_storage_ref"))
    except Exception:
        rollback_db(db)
        current_app.logger.exception("Falha ao excluir tripulante.")
        flash("Não foi possível concluir a exclusão do tripulante.", "error")
        return redirect(url_for("cadastros.tripulantes_list"))

    clear_panel_cache()
    flash("Tripulante excluído com sucesso.", "success")
    return redirect(url_for("cadastros.tripulantes_list"))


@cadastros_bp.route("/produtividade/tripulantes/<int:tripulante_id>")
@login_required
def produtividade_tripulante(tripulante_id):
    db = get_db()
    tripulante = db.execute(
        """
        SELECT
            id,
            nome,
            base,
            funcao_operacional,
            categoria_operacional,
            sdea_ativo,
            instrutor_ativo,
            checador_ativo,
            elegivel_adicional_excepcional
        FROM tripulantes
        WHERE id = %s
        """,
        (tripulante_id,),
    ).fetchone()
    if not tripulante:
        abort(404)
    competencia = parse_competencia(request.args.get("competencia", ""))
    calculo = calculate_tripulante_competencia(db, tripulante=dict(tripulante), competencia=competencia)
    conferencia = db.execute(
        """
        SELECT pc.*, u.nome AS conferido_por_nome
        FROM produtividade_conferencias pc
        JOIN usuarios u ON u.id = pc.conferido_por
        WHERE pc.tripulante_id = %s
          AND pc.competencia = %s
        """,
        (tripulante_id, competencia),
    ).fetchone()
    competencias_disponiveis = fetch_competencias_tripulante(db, tripulante_id=tripulante_id)
    if competencia not in competencias_disponiveis:
        competencias_disponiveis.insert(0, competencia)
    return render_template(
        "produtividade_tripulante.html",
        calculo=calculo,
        competencia=competencia,
        competencia_label=format_competencia_label(competencia),
        competencias_disponiveis=competencias_disponiveis,
        conferencia=conferencia,
        emitted_at=datetime.now().strftime("%d/%m/%Y %H:%M"),
        format_competencia_label=format_competencia_label,
        moeda=moeda,
        bool_label=bool_label,
    )


@cadastros_bp.route("/produtividade/tripulantes/<int:tripulante_id>/export.pdf")
@login_required
def produtividade_tripulante_export_pdf(tripulante_id):
    db = get_db()
    tripulante = db.execute(
        """
        SELECT
            id,
            nome,
            base,
            funcao_operacional,
            categoria_operacional,
            sdea_ativo,
            instrutor_ativo,
            checador_ativo,
            elegivel_adicional_excepcional
        FROM tripulantes
        WHERE id = %s
        """,
        (tripulante_id,),
    ).fetchone()
    if not tripulante:
        abort(404)
    competencia = parse_competencia(request.args.get("competencia", ""))
    calculo = calculate_tripulante_competencia(db, tripulante=dict(tripulante), competencia=competencia)
    emitted_at = datetime.now().strftime("%d/%m/%Y %H:%M")
    pdf_bytes = build_produtividade_tripulante_pdf(
        competencia=competencia,
        calculo=calculo,
        emitted_at=emitted_at,
    )
    filename = safe_pdf_filename(
        f"produtividade_{calculo.get('tripulante_nome') or tripulante_id}_{competencia}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
        fallback=f"produtividade_tripulante_{tripulante_id}.pdf",
    )
    response = Response(pdf_bytes, mimetype="application/pdf")
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Cache-Control"] = "no-store"
    return response


@cadastros_bp.route("/tripulantes/<int:tripulante_id>/relatorio")
@login_required
def tripulante_report(tripulante_id):
    db = get_db()
    tripulante = db.execute(
        """
        SELECT
            id,
            nome,
            cpf,
            licenca_anac,
            email,
            telefone,
            base,
            status,
            COALESCE(
                (
                    (foto_base64 IS NOT NULL AND TRIM(foto_base64) <> '')
                    OR (foto_storage_ref IS NOT NULL AND TRIM(foto_storage_ref) <> '')
                ),
                FALSE
            ) AS possui_foto
        FROM tripulantes
        WHERE id = %s
        """,
        (tripulante_id,),
    ).fetchone()
    if not tripulante:
        abort(404)
    rows = fetch_training_rows(db, "WHERE c.id = %s", (tripulante_id,))
    rows = sorted(rows, key=training_sort_key)
    resumo = summarize_training_status(rows)
    whatsapp_url = whatsapp_tripulante_link(
        tripulante["nome"],
        tripulante.get("telefone"),
        fetch_upcoming_training_items_by_tripulante(db, [tripulante_id]).get(tripulante_id, []),
    )
    return render_template(
        "relatorio_tripulante.html",
        tripulante=tripulante,
        tripulante_foto_url=url_for("cadastros.tripulante_foto", tripulante_id=tripulante_id) if tripulante.get("possui_foto") else "",
        treinamentos=rows,
        resumo=resumo,
        emitted_at=datetime.now().strftime("%d/%m/%Y %H:%M"),
        whatsapp_url=whatsapp_url,
    )


@cadastros_bp.route("/tripulantes/<int:tripulante_id>/relatorio/export.pdf")
@login_required
def tripulante_report_export_pdf(tripulante_id):
    db = get_db()
    tripulante = db.execute(
        """
        SELECT
            id,
            nome,
            cpf,
            licenca_anac,
            email,
            telefone,
            base,
            status,
            COALESCE(
                (
                    (foto_base64 IS NOT NULL AND TRIM(foto_base64) <> '')
                    OR (foto_storage_ref IS NOT NULL AND TRIM(foto_storage_ref) <> '')
                ),
                FALSE
            ) AS possui_foto
        FROM tripulantes
        WHERE id = %s
        """,
        (tripulante_id,),
    ).fetchone()
    if not tripulante:
        abort(404)
    rows = fetch_training_rows(db, "WHERE c.id = %s", (tripulante_id,))
    rows = sorted(rows, key=training_sort_key)
    resumo = summarize_training_status(rows)
    emitted_at = datetime.now().strftime("%d/%m/%Y %H:%M")
    pdf_bytes = build_tripulante_treinamentos_pdf(
        tripulante=dict(tripulante),
        treinamentos=rows,
        resumo=resumo,
        emitted_at=emitted_at,
    )
    filename = safe_pdf_filename(
        f"treinamentos_{tripulante.get('nome') or tripulante_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
        fallback=f"treinamentos_tripulante_{tripulante_id}.pdf",
    )
    response = Response(pdf_bytes, mimetype="application/pdf")
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Cache-Control"] = "no-store"
    return response
