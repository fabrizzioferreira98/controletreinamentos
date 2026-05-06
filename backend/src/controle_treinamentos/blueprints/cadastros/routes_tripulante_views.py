from datetime import datetime

from flask import abort, flash, redirect, render_template, url_for
from flask_login import login_required

from ...application.tripulantes import delete_tripulante
from ...auth import permission_required
from ...core.audit_utils import audit_document_generation
from ...core.domain_errors import DomainError
from ...core.http_utils import safe_pdf_filename
from ...core.pdf_document_policy import (
    TRIPULANTE_TREINAMENTOS_EXPORT_PDF_POLICY,
    build_pdf_document_response,
)
from ...db import get_db
from ...reports import build_tripulante_treinamentos_pdf
from ...repositories.queries import (
    fetch_training_rows,
    fetch_upcoming_training_items_by_tripulante,
)
from ...repositories.tripulantes import fetch_tripulante_detail
from ...services import summarize_training_status, training_sort_key, whatsapp_tripulante_link
from . import cadastros_bp


@cadastros_bp.route("/tripulantes/<int:tripulante_id>/excluir", methods=["POST"])
@permission_required("tripulantes:delete")
def tripulantes_delete(tripulante_id):
    try:
        result = delete_tripulante(tripulante_id=tripulante_id)
    except DomainError as exc:
        if exc.status == 404:
            abort(404)
        flash(exc.message, "error")
        return redirect(url_for("cadastros.tripulantes_list"))

    flash(result["message"], "success")
    return redirect(url_for("cadastros.tripulantes_list"))


@cadastros_bp.route("/tripulantes/<int:tripulante_id>/relatorio")
@login_required
def tripulante_report(tripulante_id):
    db = get_db()
    tripulante = fetch_tripulante_detail(db, tripulante_id=tripulante_id)
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
    tripulante = fetch_tripulante_detail(db, tripulante_id=tripulante_id)
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
    audit_document_generation(
        db,
        policy=TRIPULANTE_TREINAMENTOS_EXPORT_PDF_POLICY,
        filename=filename,
        entity_id=tripulante_id,
        details={
            "tripulante_id": tripulante_id,
            "tripulante_nome": tripulante.get("nome"),
            "rows_count": len(rows),
            "resumo": resumo,
        },
        commit=True,
    )
    return build_pdf_document_response(
        policy=TRIPULANTE_TREINAMENTOS_EXPORT_PDF_POLICY,
        payload_bytes=pdf_bytes,
        filename=filename,
        entity_id=tripulante_id,
    )
