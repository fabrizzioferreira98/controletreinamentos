from __future__ import annotations

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import login_required

from ...application.catalogos_ssr import (
    CatalogoNotFoundError,
    CatalogoValidationError,
    create_equipamento_from_form,
    create_tipo_treinamento_from_form,
    delete_equipamento_with_guards,
    delete_tipo_treinamento_with_guards,
    get_equipamento_form_context,
    get_equipamentos_list_context,
    get_tipo_treinamento_form_context,
    get_tipos_treinamento_list_context,
    update_equipamento_from_form,
    update_tipo_treinamento_from_form,
)
from ...auth import permission_required
from ...core.frontend_routes import frontend_compat_enabled, redirect_to_frontend
from ...core.http_utils import get_page_arg
from . import cadastros_bp


def _redirect_to_training_root():
    return redirect_to_frontend("#/treinamentos/raiz")


def _redirect_after_tipo_mutation():
    if frontend_compat_enabled():
        return _redirect_to_training_root()
    return redirect(url_for("cadastros.tipos_list"))


@cadastros_bp.route("/equipamentos")
@login_required
def equipamentos_list():
    context = get_equipamentos_list_context(page=get_page_arg())
    return render_template(
        "equipamentos_list.html",
        **context,
    )


@cadastros_bp.route("/equipamentos/novo", methods=["GET", "POST"])
@permission_required("equipamentos:create")
def equipamentos_new():
    if request.method == "POST":
        try:
            create_equipamento_from_form(request.form)
            flash("Equipamento cadastrado com sucesso.", "success")
        except CatalogoValidationError as exc:
            flash(str(exc), "error")
            return render_template("equipamentos_form.html", equipamento=exc.state), 400
        return redirect(url_for("cadastros.equipamentos_list"))
    return render_template("equipamentos_form.html", **get_equipamento_form_context())


@cadastros_bp.route("/equipamentos/<int:equipamento_id>/editar", methods=["GET", "POST"])
@permission_required("equipamentos:edit")
def equipamentos_edit(equipamento_id):
    if request.method == "POST":
        try:
            update_equipamento_from_form(equipamento_id=equipamento_id, form_data=request.form)
            flash("Equipamento atualizado com sucesso.", "success")
        except CatalogoNotFoundError:
            abort(404)
        except CatalogoValidationError as exc:
            flash(str(exc), "error")
            return render_template("equipamentos_form.html", equipamento=exc.state), 400
        return redirect(url_for("cadastros.equipamentos_list"))
    try:
        context = get_equipamento_form_context(equipamento_id=equipamento_id)
    except CatalogoNotFoundError:
        abort(404)
    return render_template("equipamentos_form.html", **context)


@cadastros_bp.route("/equipamentos/<int:equipamento_id>/excluir", methods=["POST"])
@permission_required("equipamentos:delete")
def equipamentos_delete(equipamento_id):
    try:
        result = delete_equipamento_with_guards(equipamento_id=equipamento_id)
    except CatalogoNotFoundError:
        abort(404)
    if result["blocked"]:
        flash("Não é possível excluir o equipamento porque existem treinamentos vinculados.", "error")
        return redirect(url_for("cadastros.equipamentos_list"))

    flash("Equipamento excluído com sucesso.", "success")
    return redirect(url_for("cadastros.equipamentos_list"))


@cadastros_bp.route("/tipos-treinamento")
@login_required
def tipos_list():
    if frontend_compat_enabled():
        return _redirect_to_training_root()
    context = get_tipos_treinamento_list_context(page=get_page_arg())
    return render_template(
        "tipos_list.html",
        **context,
    )


@cadastros_bp.route("/tipos-treinamento/novo", methods=["GET", "POST"])
@permission_required("tipos_treinamento:create")
def tipos_new():
    if request.method == "GET" and frontend_compat_enabled():
        return _redirect_to_training_root()
    if request.method == "POST":
        try:
            create_tipo_treinamento_from_form(request.form)
            flash("Tipo de treinamento cadastrado com sucesso.", "success")
        except CatalogoValidationError as exc:
            flash(str(exc), "error")
            return render_template("tipos_form.html", tipo=exc.state), 400
        return _redirect_after_tipo_mutation()
    return render_template("tipos_form.html", **get_tipo_treinamento_form_context())


@cadastros_bp.route("/tipos-treinamento/<int:tipo_id>/editar", methods=["GET", "POST"])
@permission_required("tipos_treinamento:edit")
def tipos_edit(tipo_id):
    if request.method == "GET" and frontend_compat_enabled():
        return _redirect_to_training_root()
    if request.method == "POST":
        try:
            update_tipo_treinamento_from_form(tipo_id=tipo_id, form_data=request.form)
            flash("Tipo de treinamento atualizado com sucesso.", "success")
        except CatalogoNotFoundError:
            abort(404)
        except CatalogoValidationError as exc:
            flash(str(exc), "error")
            return render_template("tipos_form.html", tipo=exc.state), 400
        return _redirect_after_tipo_mutation()
    try:
        context = get_tipo_treinamento_form_context(tipo_id=tipo_id)
    except CatalogoNotFoundError:
        abort(404)
    return render_template("tipos_form.html", **context)


@cadastros_bp.route("/tipos-treinamento/<int:tipo_id>/excluir", methods=["POST"])
@permission_required("tipos_treinamento:delete")
def tipos_delete(tipo_id):
    try:
        result = delete_tipo_treinamento_with_guards(tipo_id=tipo_id)
    except CatalogoNotFoundError:
        abort(404)
    if result["blocked"]:
        flash("Não é possível excluir o tipo de treinamento porque existem treinamentos vinculados.", "error")
        return _redirect_after_tipo_mutation()

    flash("Tipo de treinamento excluído com sucesso.", "success")
    return _redirect_after_tipo_mutation()
