from __future__ import annotations

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import login_required

from ...auth import permission_required
from ...core.audit_utils import audit_event
from ...core.http_utils import get_required_int, get_required_text, resolve_pagination_state
from ...db import get_db
from ...repositories.dashboard_cache import clear_catalog_options_cache
from ...service_layers.form_builders import build_equipamento_form_state, build_tipo_form_state
from . import cadastros_bp


@cadastros_bp.route("/equipamentos")
@login_required
def equipamentos_list():
    db = get_db()
    total = db.execute("SELECT COUNT(*) AS total FROM equipamentos").fetchone()["total"]
    paging = resolve_pagination_state(total, endpoint="cadastros.equipamentos_list")
    equipamentos = db.execute(
        "SELECT * FROM equipamentos ORDER BY nome LIMIT %s OFFSET %s",
        (paging["per_page"], paging["offset"]),
    ).fetchall()
    return render_template(
        "equipamentos_list.html",
        equipamentos=equipamentos,
        pagination=paging["pagination"],
    )


@cadastros_bp.route("/equipamentos/novo", methods=["GET", "POST"])
@permission_required("equipamentos:create")
def equipamentos_new():
    db = get_db()
    if request.method == "POST":
        equipamento_state = build_equipamento_form_state(request.form)
        try:
            nome = get_required_text(request.form, "nome", "Nome")
            tipo = get_required_text(request.form, "tipo", "Tipo")
            created = db.execute(
                "INSERT INTO equipamentos (nome, tipo, ativo) VALUES (%s, %s, %s) RETURNING id",
                (
                    nome,
                    tipo,
                    1 if request.form.get("ativo") else 0,
                ),
            ).fetchone()
            audit_event(db, "equipamento", created["id"], "create", novo=equipamento_state)
            db.commit()
            clear_catalog_options_cache()
            flash("Equipamento cadastrado com sucesso.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("equipamentos_form.html", equipamento=equipamento_state), 400
        return redirect(url_for("cadastros.equipamentos_list"))
    return render_template("equipamentos_form.html", equipamento=None)


@cadastros_bp.route("/equipamentos/<int:equipamento_id>/editar", methods=["GET", "POST"])
@permission_required("equipamentos:edit")
def equipamentos_edit(equipamento_id):
    db = get_db()
    equipamento = db.execute("SELECT * FROM equipamentos WHERE id = %s", (equipamento_id,)).fetchone()
    if not equipamento:
        abort(404)
    if request.method == "POST":
        equipamento_state = build_equipamento_form_state(request.form)
        try:
            nome = get_required_text(request.form, "nome", "Nome")
            tipo = get_required_text(request.form, "tipo", "Tipo")
            db.execute(
                "UPDATE equipamentos SET nome = %s, tipo = %s, ativo = %s WHERE id = %s",
                (
                    nome,
                    tipo,
                    1 if request.form.get("ativo") else 0,
                    equipamento_id,
                ),
            )
            audit_event(db, "equipamento", equipamento_id, "update", anterior=equipamento, novo=equipamento_state)
            db.commit()
            clear_catalog_options_cache()
            flash("Equipamento atualizado com sucesso.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("equipamentos_form.html", equipamento=equipamento_state), 400
        return redirect(url_for("cadastros.equipamentos_list"))
    return render_template("equipamentos_form.html", equipamento=equipamento)


@cadastros_bp.route("/equipamentos/<int:equipamento_id>/excluir", methods=["POST"])
@permission_required("equipamentos:delete")
def equipamentos_delete(equipamento_id):
    db = get_db()
    equipamento = db.execute("SELECT id FROM equipamentos WHERE id = %s", (equipamento_id,)).fetchone()
    if not equipamento:
        abort(404)
    linked_training = db.execute(
        "SELECT id FROM treinamentos WHERE equipamento_id = %s LIMIT 1",
        (equipamento_id,),
    ).fetchone()
    if linked_training:
        flash("Não é possível excluir o equipamento porque existem treinamentos vinculados.", "error")
        return redirect(url_for("cadastros.equipamentos_list"))

    audit_event(db, "equipamento", equipamento_id, "delete", anterior=equipamento)
    db.execute("DELETE FROM equipamentos WHERE id = %s", (equipamento_id,))
    db.commit()
    clear_catalog_options_cache()
    flash("Equipamento excluído com sucesso.", "success")
    return redirect(url_for("cadastros.equipamentos_list"))


@cadastros_bp.route("/tipos-treinamento")
@login_required
def tipos_list():
    db = get_db()
    total = db.execute("SELECT COUNT(*) AS total FROM tipos_treinamento").fetchone()["total"]
    paging = resolve_pagination_state(total, endpoint="cadastros.tipos_list")
    tipos = db.execute(
        "SELECT * FROM tipos_treinamento ORDER BY nome LIMIT %s OFFSET %s",
        (paging["per_page"], paging["offset"]),
    ).fetchall()
    return render_template(
        "tipos_list.html",
        tipos=tipos,
        pagination=paging["pagination"],
    )


@cadastros_bp.route("/tipos-treinamento/novo", methods=["GET", "POST"])
@permission_required("tipos_treinamento:create")
def tipos_new():
    db = get_db()
    if request.method == "POST":
        tipo_state = build_tipo_form_state(request.form)
        try:
            nome = get_required_text(request.form, "nome", "Nome")
            periodicidade_meses = get_required_int(request.form, "periodicidade_meses", "Periodicidade em meses")
            if periodicidade_meses <= 0:
                raise ValueError("O campo 'Periodicidade em meses' deve ser maior que zero.")
            created = db.execute(
                """
                INSERT INTO tipos_treinamento (nome, periodicidade_meses, exige_equipamento, ativo)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (
                    nome,
                    periodicidade_meses,
                    1 if request.form.get("exige_equipamento") else 0,
                    1 if request.form.get("ativo") else 0,
                ),
            ).fetchone()
            audit_event(db, "tipo_treinamento", created["id"], "create", novo=tipo_state)
            db.commit()
            clear_catalog_options_cache()
            flash("Tipo de treinamento cadastrado com sucesso.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("tipos_form.html", tipo=tipo_state), 400
        return redirect(url_for("cadastros.tipos_list"))
    return render_template("tipos_form.html", tipo=None)


@cadastros_bp.route("/tipos-treinamento/<int:tipo_id>/editar", methods=["GET", "POST"])
@permission_required("tipos_treinamento:edit")
def tipos_edit(tipo_id):
    db = get_db()
    tipo = db.execute("SELECT * FROM tipos_treinamento WHERE id = %s", (tipo_id,)).fetchone()
    if not tipo:
        abort(404)
    if request.method == "POST":
        tipo_state = build_tipo_form_state(request.form)
        try:
            nome = get_required_text(request.form, "nome", "Nome")
            periodicidade_meses = get_required_int(request.form, "periodicidade_meses", "Periodicidade em meses")
            if periodicidade_meses <= 0:
                raise ValueError("O campo 'Periodicidade em meses' deve ser maior que zero.")
            db.execute(
                """
                UPDATE tipos_treinamento
                SET nome = %s, periodicidade_meses = %s, exige_equipamento = %s, ativo = %s
                WHERE id = %s
                """,
                (
                    nome,
                    periodicidade_meses,
                    1 if request.form.get("exige_equipamento") else 0,
                    1 if request.form.get("ativo") else 0,
                    tipo_id,
                ),
            )
            audit_event(db, "tipo_treinamento", tipo_id, "update", anterior=tipo, novo=tipo_state)
            db.commit()
            clear_catalog_options_cache()
            flash("Tipo de treinamento atualizado com sucesso.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("tipos_form.html", tipo=tipo_state), 400
        return redirect(url_for("cadastros.tipos_list"))
    return render_template("tipos_form.html", tipo=tipo)


@cadastros_bp.route("/tipos-treinamento/<int:tipo_id>/excluir", methods=["POST"])
@permission_required("tipos_treinamento:delete")
def tipos_delete(tipo_id):
    db = get_db()
    tipo = db.execute("SELECT id FROM tipos_treinamento WHERE id = %s", (tipo_id,)).fetchone()
    if not tipo:
        abort(404)
    linked_training = db.execute(
        "SELECT id FROM treinamentos WHERE tipo_treinamento_id = %s LIMIT 1",
        (tipo_id,),
    ).fetchone()
    if linked_training:
        flash("Não é possível excluir o tipo de treinamento porque existem treinamentos vinculados.", "error")
        return redirect(url_for("cadastros.tipos_list"))

    audit_event(db, "tipo_treinamento", tipo_id, "delete", anterior=tipo)
    db.execute("DELETE FROM tipos_treinamento WHERE id = %s", (tipo_id,))
    db.commit()
    clear_catalog_options_cache()
    flash("Tipo de treinamento excluído com sucesso.", "success")
    return redirect(url_for("cadastros.tipos_list"))
