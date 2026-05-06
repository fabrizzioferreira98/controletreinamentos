
import time
from datetime import datetime

try:
    import psycopg2
except ImportError:
    psycopg2 = None  # type: ignore[assignment]
from flask import Response, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from werkzeug.security import generate_password_hash

from ...auth import MODULE_PERMISSION_GROUPS, normalize_permissions, permission_required, serialize_permissions
from ...core.audit_utils import (
    audit_action_label,
    audit_entity_label,
    audit_event,
    build_audit_preview,
    build_audit_simple_sentence,
    ensure_user_permissions_column,
    rollback_db,
)
from ...core.http_utils import get_optional_text, get_required_text, get_validated_email, resolve_pagination_state, safe_pdf_filename
from ...db import get_db
from ...infra.jobs import build_bucketed_idempotency_key
from ...jobs import (
    enqueue_notifications_job,
)
from ...mailer import generate_notification_payload, get_smtp_config, validate_notification_dispatch_readiness
from ...reports import build_auditoria_pdf
from ...repositories.dashboard_cache import get_panel_cache, set_panel_cache
from ...repositories.queries import fetch_navigation_counts
from ...service_layers.form_builders import build_notificacao_form_state, build_usuario_form_state
from ...services import name_initials, whatsapp_tripulante_link
from . import admin_bp


@admin_bp.context_processor
def inject_globals():
    nav_counts = {}
    if current_user.is_authenticated:
        try:
            db = get_db()
            nav_counts = fetch_navigation_counts(db)
        except Exception:
            current_app.logger.exception("Falha ao carregar contadores de navegação do admin.")
            nav_counts = {}
    return {
        "nav_counts": nav_counts,
        "avatar_initials": name_initials,
        "tripulante_whatsapp_url": whatsapp_tripulante_link,
    }


@admin_bp.route("/usuarios")
@permission_required("usuarios:view")
def usuarios_list():
    db = get_db()
    ensure_user_permissions_column(db)
    total = db.execute("SELECT COUNT(*) AS total FROM usuarios").fetchone()["total"]
    paging = resolve_pagination_state(total, endpoint="admin.usuarios_list")
    usuarios = db.execute(
        "SELECT id, nome, login, email, perfil, ativo, permissao_modulos_json FROM usuarios ORDER BY nome LIMIT %s OFFSET %s",
        (paging["per_page"], paging["offset"]),
    ).fetchall()
    usuarios_view = []
    for row in usuarios:
        item = dict(row)
        item["permissions_total"] = len(normalize_permissions(item.get("permissao_modulos_json"), perfil=item.get("perfil")))
        usuarios_view.append(item)
    return render_template(
        "usuarios_list.html",
        usuarios=usuarios_view,
        pagination=paging["pagination"],
    )


@admin_bp.route("/auditoria")
@permission_required("auditoria:view")
def auditoria_list():
    db = get_db()
    entidade = request.args.get("entidade", "").strip()
    acao = request.args.get("acao", "").strip()
    autor = request.args.get("autor", "").strip()
    busca = request.args.get("busca", "").strip()

    clauses = []
    params = []
    if entidade:
        clauses.append("a.entidade = %s")
        params.append(entidade)
    if acao:
        clauses.append("a.acao = %s")
        params.append(acao)
    if autor:
        clauses.append("CAST(a.realizado_por AS TEXT) = %s")
        params.append(autor)
    if busca:
        clauses.append(
            """
            (
                COALESCE(u.nome, '') ILIKE %s
                OR COALESCE(a.entidade, '') ILIKE %s
                OR COALESCE(a.acao, '') ILIKE %s
                OR COALESCE(a.observacao, '') ILIKE %s
                OR COALESCE(CAST(a.entidade_id AS TEXT), '') ILIKE %s
                OR COALESCE(CAST(a.payload_anterior AS TEXT), '') ILIKE %s
                OR COALESCE(CAST(a.payload_novo AS TEXT), '') ILIKE %s
            )
            """
        )
        search_term = f"%{busca}%"
        params.extend([search_term] * 7)

    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    total = db.execute(
        f"""
        SELECT COUNT(*) AS total
        FROM auditoria_eventos a
        LEFT JOIN usuarios u ON u.id = a.realizado_por
        {where_clause}
        """,
        tuple(params),
    ).fetchone()["total"]
    paging = resolve_pagination_state(
        total,
        endpoint="admin.auditoria_list",
        entidade=entidade,
        acao=acao,
        autor=autor,
        busca=busca,
    )
    rows = db.execute(
        f"""
        SELECT
            a.*,
            u.nome AS realizado_por_nome,
            u.login AS realizado_por_login
        FROM auditoria_eventos a
        LEFT JOIN usuarios u ON u.id = a.realizado_por
        {where_clause}
        ORDER BY a.realizado_em DESC, a.id DESC
        LIMIT %s OFFSET %s
        """,
        (*params, paging["per_page"], paging["offset"]),
    ).fetchall()

    audit_rows = []
    for row in rows:
        item = dict(row)
        item["entidade_label"] = audit_entity_label(item.get("entidade"))
        item["acao_label"] = audit_action_label(item.get("acao"))
        item["realizado_em_label"] = item["realizado_em"].strftime("%d/%m/%Y %H:%M") if item.get("realizado_em") else ""
        item["preview_anterior"] = build_audit_preview(item.get("payload_anterior"))
        item["preview_novo"] = build_audit_preview(item.get("payload_novo"))
        item["resumo_simples"] = build_audit_simple_sentence(item)
        audit_rows.append(item)

    options_cache_key = "auditoria:filters"
    cached_options = get_panel_cache(options_cache_key)
    if cached_options is None:
        autores = db.execute(
            """
            SELECT DISTINCT u.id, u.nome
            FROM auditoria_eventos a
            JOIN usuarios u ON u.id = a.realizado_por
            ORDER BY u.nome
            """
        ).fetchall()
        entity_options = [
            {"value": key, "label": audit_entity_label(key)}
            for key in sorted(
                {
                    row["entidade"]
                    for row in db.execute("SELECT DISTINCT entidade FROM auditoria_eventos ORDER BY entidade").fetchall()
                }
            )
        ]
        action_options = [
            {"value": key, "label": audit_action_label(key)}
            for key in sorted({row["acao"] for row in db.execute("SELECT DISTINCT acao FROM auditoria_eventos ORDER BY acao").fetchall()})
        ]
        cached_options = {
            "autores": [dict(row) for row in autores],
            "entity_options": entity_options,
            "action_options": action_options,
        }
        set_panel_cache(options_cache_key, cached_options)
    autores = cached_options["autores"]
    entity_options = cached_options["entity_options"]
    action_options = cached_options["action_options"]

    return render_template(
        "auditoria_list.html",
        audit_rows=audit_rows,
        filtros={"entidade": entidade, "acao": acao, "autor": autor, "busca": busca},
        entity_options=entity_options,
        action_options=action_options,
        autores=autores,
        pagination=paging["pagination"],
    )


@admin_bp.route("/auditoria/export.pdf")
@permission_required("auditoria:view")
def auditoria_export_pdf():
    db = get_db()
    entidade = request.args.get("entidade", "").strip()
    acao = request.args.get("acao", "").strip()
    autor = request.args.get("autor", "").strip()
    busca = request.args.get("busca", "").strip()

    clauses = []
    params = []
    if entidade:
        clauses.append("a.entidade = %s")
        params.append(entidade)
    if acao:
        clauses.append("a.acao = %s")
        params.append(acao)
    if autor:
        clauses.append("CAST(a.realizado_por AS TEXT) = %s")
        params.append(autor)
    if busca:
        clauses.append(
            """
            (
                COALESCE(u.nome, '') ILIKE %s
                OR COALESCE(a.entidade, '') ILIKE %s
                OR COALESCE(a.acao, '') ILIKE %s
                OR COALESCE(a.observacao, '') ILIKE %s
                OR COALESCE(CAST(a.entidade_id AS TEXT), '') ILIKE %s
                OR COALESCE(CAST(a.payload_anterior AS TEXT), '') ILIKE %s
                OR COALESCE(CAST(a.payload_novo AS TEXT), '') ILIKE %s
            )
            """
        )
        search_term = f"%{busca}%"
        params.extend([search_term] * 7)

    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = db.execute(
        f"""
        SELECT
            a.*,
            u.nome AS realizado_por_nome,
            u.login AS realizado_por_login
        FROM auditoria_eventos a
        LEFT JOIN usuarios u ON u.id = a.realizado_por
        {where_clause}
        ORDER BY a.realizado_em DESC, a.id DESC
        """,
        tuple(params),
    ).fetchall()

    audit_rows = []
    for row in rows:
        item = dict(row)
        item["entidade_label"] = audit_entity_label(item.get("entidade"))
        item["acao_label"] = audit_action_label(item.get("acao"))
        item["realizado_em_label"] = item["realizado_em"].strftime("%d/%m/%Y %H:%M") if item.get("realizado_em") else ""
        item["preview_anterior"] = build_audit_preview(item.get("payload_anterior"))
        item["preview_novo"] = build_audit_preview(item.get("payload_novo"))
        item["resumo_simples"] = build_audit_simple_sentence(item)
        audit_rows.append(item)

    emitted_at = datetime.now().strftime("%d/%m/%Y %H:%M")
    pdf_bytes = build_auditoria_pdf(
        emitted_at=emitted_at,
        filtros_aplicados={
            "entidade": entidade or "-",
            "acao": acao or "-",
            "autor": autor or "-",
            "busca": busca or "-",
        },
        rows=audit_rows,
    )
    filename = safe_pdf_filename(
        f"log_acoes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
        fallback="log_acoes.pdf",
    )
    response = Response(pdf_bytes, mimetype="application/pdf")
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Cache-Control"] = "no-store"
    return response


@admin_bp.route("/usuarios/novo", methods=["GET", "POST"])
@permission_required("usuarios:manage")
def usuarios_new():
    db = get_db()
    ensure_user_permissions_column(db)
    if request.method == "POST":
        usuario_state = build_usuario_form_state(request.form)
        try:
            nome = get_required_text(request.form, "nome", "Nome")
            login = get_required_text(request.form, "login", "Login")
            email = get_validated_email(request.form, "email", "E-mail")
            senha = get_required_text(request.form, "senha", "Senha")
            perfil = get_required_text(request.form, "perfil", "Perfil")
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("usuarios_form.html", usuario=usuario_state, permission_groups=MODULE_PERMISSION_GROUPS), 400
        if perfil not in {"operador", "gestora"}:
            flash("O perfil informado é inválido.", "error")
            return render_template("usuarios_form.html", usuario=usuario_state, permission_groups=MODULE_PERMISSION_GROUPS), 400
        duplicate = db.execute("SELECT id FROM usuarios WHERE login = %s", (login,)).fetchone()
        if duplicate:
            flash("Já existe um usuário cadastrado com este login.", "error")
            return render_template("usuarios_form.html", usuario=usuario_state, permission_groups=MODULE_PERMISSION_GROUPS), 400
        permission_keys = normalize_permissions(request.form.getlist("permission_keys"), perfil=perfil)
        permissions_json = serialize_permissions(permission_keys, perfil=perfil)
        try:
            created = db.execute(
                """
                INSERT INTO usuarios (nome, login, email, senha_hash, perfil, ativo, permissao_modulos_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    nome,
                    login,
                    email,
                    generate_password_hash(senha, method="pbkdf2:sha256"),
                    perfil,
                    1 if request.form.get("ativo") else 0,
                    permissions_json,
                ),
            ).fetchone()
            audit_event(db, "usuario", created["id"], "create", novo=usuario_state)
            db.commit()
            flash("Usuário cadastrado com sucesso.", "success")
        except psycopg2.IntegrityError:
            rollback_db(db)
            flash("Não foi possível salvar o usuário. Verifique se o login já está em uso.", "error")
            return render_template("usuarios_form.html", usuario=usuario_state, permission_groups=MODULE_PERMISSION_GROUPS), 400
        except Exception:
            rollback_db(db)
            current_app.logger.exception("Failed to create user.")
            flash("Não foi possível salvar o usuário no momento. Tente novamente.", "error")
            return render_template("usuarios_form.html", usuario=usuario_state, permission_groups=MODULE_PERMISSION_GROUPS), 500
        return redirect(url_for("admin.usuarios_list"))
    return render_template(
        "usuarios_form.html",
        usuario={"perfil": "operador", "ativo": True, "permission_keys": sorted(normalize_permissions([], perfil="operador"))},
        permission_groups=MODULE_PERMISSION_GROUPS,
    )


@admin_bp.route("/usuarios/<int:usuario_id>/editar", methods=["GET", "POST"])
@permission_required("usuarios:manage")
def usuarios_edit(usuario_id):
    db = get_db()
    ensure_user_permissions_column(db)
    usuario = db.execute(
        "SELECT id, nome, login, email, perfil, ativo, permissao_modulos_json FROM usuarios WHERE id = %s",
        (usuario_id,),
    ).fetchone()
    if not usuario:
        abort(404)
    usuario_dict = dict(usuario)
    usuario_dict["permission_keys"] = sorted(
        normalize_permissions(usuario_dict.get("permissao_modulos_json"), perfil=usuario_dict.get("perfil"))
    )
    if request.method == "POST":
        usuario_state = build_usuario_form_state(request.form)
        senha_nova = get_optional_text(request.form, "senha")
        try:
            nome = get_required_text(request.form, "nome", "Nome")
            login = get_required_text(request.form, "login", "Login")
            email = get_validated_email(request.form, "email", "E-mail")
            perfil = get_required_text(request.form, "perfil", "Perfil")
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("usuarios_form.html", usuario=usuario_state, permission_groups=MODULE_PERMISSION_GROUPS), 400
        if perfil not in {"operador", "gestora"}:
            flash("O perfil informado é inválido.", "error")
            return render_template("usuarios_form.html", usuario=usuario_state, permission_groups=MODULE_PERMISSION_GROUPS), 400
        novo_ativo = 1 if request.form.get("ativo") else 0
        if int(current_user.id) == usuario_id and novo_ativo == 0:
            flash("Você não pode inativar o próprio usuário.", "error")
            return render_template("usuarios_form.html", usuario=usuario_state, permission_groups=MODULE_PERMISSION_GROUPS), 400
        duplicate = db.execute(
            "SELECT id FROM usuarios WHERE login = %s AND id != %s",
            (login, usuario_id),
        ).fetchone()
        if duplicate:
            flash("Já existe um usuário cadastrado com este login.", "error")
            return render_template("usuarios_form.html", usuario=usuario_state, permission_groups=MODULE_PERMISSION_GROUPS), 400
        permission_keys = normalize_permissions(request.form.getlist("permission_keys"), perfil=perfil)
        permissions_json = serialize_permissions(permission_keys, perfil=perfil)
        if senha_nova:
            query = """
                UPDATE usuarios
                SET nome = %s, login = %s, email = %s, senha_hash = %s, perfil = %s, ativo = %s, permissao_modulos_json = %s
                WHERE id = %s
                """
            params = (
                nome,
                login,
                email,
                generate_password_hash(senha_nova, method="pbkdf2:sha256"),
                perfil,
                novo_ativo,
                permissions_json,
                usuario_id,
            )
        else:
            query = """
                UPDATE usuarios
                SET nome = %s, login = %s, email = %s, perfil = %s, ativo = %s, permissao_modulos_json = %s
                WHERE id = %s
                """
            params = (
                nome,
                login,
                email,
                perfil,
                novo_ativo,
                permissions_json,
                usuario_id,
            )
        try:
            db.execute(query, params)
            audit_event(db, "usuario", usuario_id, "update", anterior=usuario, novo=usuario_state)
            db.commit()
            flash("Usuário atualizado com sucesso.", "success")
        except psycopg2.IntegrityError:
            rollback_db(db)
            flash("Não foi possível atualizar o usuário. Verifique se o login já está em uso.", "error")
            return render_template("usuarios_form.html", usuario=usuario_state, permission_groups=MODULE_PERMISSION_GROUPS), 400
        except Exception:
            rollback_db(db)
            current_app.logger.exception("Failed to update user.")
            flash("Não foi possível atualizar o usuário no momento. Tente novamente.", "error")
            return render_template("usuarios_form.html", usuario=usuario_state, permission_groups=MODULE_PERMISSION_GROUPS), 500
        return redirect(url_for("admin.usuarios_list"))
    return render_template("usuarios_form.html", usuario=usuario_dict, permission_groups=MODULE_PERMISSION_GROUPS)


@admin_bp.route("/notificacoes-email")
@permission_required("notificacoes:view")
def notificacoes_list():
    try:
        db = get_db()
        total = db.execute("SELECT COUNT(*) AS total FROM notificacoes_email").fetchone()["total"]
        paging = resolve_pagination_state(total, endpoint="admin.notificacoes_list")
        notificacoes = db.execute(
            """
            SELECT id, email_destinatario, ativo
            FROM notificacoes_email
            ORDER BY email_destinatario
            LIMIT %s OFFSET %s
            """,
            (paging["per_page"], paging["offset"]),
        ).fetchall()
        preview_enabled = (request.args.get("preview", "") or "").strip().lower() in {"1", "true", "yes", "on"}
        payload = {
            "recipients": [],
            "blocks": {"vencidos": [], "em_30_dias": [], "em_60_dias": [], "em_90_dias": []},
            "blocks_all": {"vencidos": [], "em_30_dias": [], "em_60_dias": [], "em_90_dias": []},
            "body": "",
            "total_items": 0,
            "total_items_all": 0,
            "total_items_sent_today": 0,
            "provider": "smtp",
            "email_ready": False,
        }
        try:
            payload = generate_notification_payload(
                include_diagnostics=True,
                include_preview_tables=preview_enabled,
                include_body=preview_enabled,
            )
        except Exception:
            current_app.logger.exception("Falha ao gerar payload de notificações para tela administrativa.")
            flash(
                "Não foi possível carregar o preview de notificações agora. Verifique as configurações de e-mail e tente novamente.",
                "error",
            )
        controle = db.execute(
            "SELECT chave, valor FROM sistema_controle WHERE chave IN ('notification_last_run', 'notification_last_sent_at')"
        ).fetchall()
        controle_map = {row["chave"]: row["valor"] for row in controle}
        return render_template(
            "notificacoes_list.html",
            notificacoes=notificacoes,
            email_preview=payload,
            preview_enabled=preview_enabled,
            smtp_config=get_smtp_config(),
            last_run=controle_map.get("notification_last_run", ""),
            last_sent_at=controle_map.get("notification_last_sent_at", ""),
            pagination=paging["pagination"],
        )
    except Exception:
        current_app.logger.exception("Falha inesperada ao carregar a tela de notificações.")
        flash("Não foi possível carregar a tela de notificações neste momento. Tente novamente.", "error")
        return redirect(url_for("dashboard.dashboard"))


@admin_bp.route("/notificacoes-email/novo", methods=["GET", "POST"])
@permission_required("notificacoes:edit")
def notificacoes_new():
    db = get_db()
    if request.method == "POST":
        notificacao_state = build_notificacao_form_state(request.form)
        try:
            email_destinatario = get_validated_email(request.form, "email_destinatario", "E-mail destinatário")
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("notificacoes_form.html", notificacao=notificacao_state), 400
        duplicate = db.execute(
            "SELECT id FROM notificacoes_email WHERE email_destinatario = %s",
            (email_destinatario,),
        ).fetchone()
        if duplicate:
            flash("Este destinatário de e-mail já está cadastrado.", "error")
            return render_template("notificacoes_form.html", notificacao=notificacao_state), 400
        try:
            created = db.execute(
                "INSERT INTO notificacoes_email (email_destinatario, ativo) VALUES (%s, %s) RETURNING id",
                (email_destinatario, 1 if request.form.get("ativo") else 0),
            ).fetchone()
            audit_event(db, "notificacao_email", created["id"], "create", novo=notificacao_state)
            db.commit()
            flash("Destinatário cadastrado com sucesso.", "success")
        except psycopg2.IntegrityError:
            rollback_db(db)
            flash("Não foi possível salvar o destinatário. Verifique se o e-mail já está cadastrado.", "error")
            return render_template("notificacoes_form.html", notificacao=notificacao_state), 400
        return redirect(url_for("admin.notificacoes_list"))
    return render_template("notificacoes_form.html", notificacao=None)


@admin_bp.route("/notificacoes-email/<int:notificacao_id>/editar", methods=["GET", "POST"])
@permission_required("notificacoes:edit")
def notificacoes_edit(notificacao_id):
    db = get_db()
    notificacao = db.execute("SELECT * FROM notificacoes_email WHERE id = %s", (notificacao_id,)).fetchone()
    if not notificacao:
        abort(404)
    if request.method == "POST":
        notificacao_state = build_notificacao_form_state(request.form)
        try:
            email_destinatario = get_validated_email(request.form, "email_destinatario", "E-mail destinatário")
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("notificacoes_form.html", notificacao=notificacao_state), 400
        duplicate = db.execute(
            "SELECT id FROM notificacoes_email WHERE email_destinatario = %s AND id != %s",
            (email_destinatario, notificacao_id),
        ).fetchone()
        if duplicate:
            flash("Este destinatário de e-mail já está cadastrado.", "error")
            return render_template("notificacoes_form.html", notificacao=notificacao_state), 400
        try:
            db.execute(
                """
                UPDATE notificacoes_email
                SET email_destinatario = %s, ativo = %s
                WHERE id = %s
                """,
                (
                    email_destinatario,
                    1 if request.form.get("ativo") else 0,
                    notificacao_id,
                ),
            )
            audit_event(db, "notificacao_email", notificacao_id, "update", anterior=notificacao, novo=notificacao_state)
            db.commit()
            flash("Destinatário atualizado com sucesso.", "success")
        except psycopg2.IntegrityError:
            rollback_db(db)
            flash("Não foi possível atualizar o destinatário. Verifique se o e-mail já está cadastrado.", "error")
            return render_template("notificacoes_form.html", notificacao=notificacao_state), 400
        return redirect(url_for("admin.notificacoes_list"))
    return render_template("notificacoes_form.html", notificacao=notificacao)


@admin_bp.route("/notificacoes-email/disparo-manual", methods=["POST"])
@permission_required("notificacoes:edit")
def notificacoes_manual_send():
    try:
        try:
            readiness = validate_notification_dispatch_readiness()
        except Exception:
            current_app.logger.exception("Falha ao validar pré-requisitos para disparo manual de notificações.")
            flash(
                "Não foi possível validar os pré-requisitos de envio agora. Tente novamente em instantes.",
                "error",
            )
            return redirect(url_for("admin.notificacoes_list"))
        if int(readiness.get("recipients_count", 0) or 0) <= 0:
            flash("Nenhum destinatário ativo configurado para o envio.", "error")
            return redirect(url_for("admin.notificacoes_list"))
        if not readiness.get("email_ready"):
            missing_fields = readiness.get("missing_config_fields") or []
            missing_details = f" Campos ausentes: {', '.join(missing_fields)}." if missing_fields else ""
            if (readiness.get("provider") or "").strip().lower() == "resend":
                flash(
                    "Resend não configurado. Defina RESEND_API_KEY e RESEND_FROM antes do disparo manual."
                    f"{missing_details}",
                    "error",
                )
            else:
                flash(
                    "SMTP não configurado. Defina SMTP_HOST, SMTP_USER e SMTP_PASSWORD antes do disparo manual."
                    f"{missing_details}",
                    "error",
                )
            return redirect(url_for("admin.notificacoes_list"))

        db = get_db()
        idempotency_key = build_bucketed_idempotency_key(
            "manual-notifications",
            granularity="minute",
            suffix=str(current_user.id),
        )
        try:
            from flask import g as flask_g
            enqueue_result = enqueue_notifications_job(
                db,
                source="manual",
                requested_by=int(current_user.id),
                idempotency_key=idempotency_key,
                request_id=getattr(flask_g, "request_id", None),
            )
            db.commit()
        except Exception:
            rollback_db(db)
            current_app.logger.exception("Falha ao enfileirar disparo manual de notificações.")
            flash("Não foi possível enfileirar o disparo manual neste momento. Tente novamente.", "error")
            return redirect(url_for("admin.notificacoes_list"))

        if not enqueue_result.created and enqueue_result.status in {"queued", "running"}:
            flash("Já existe um disparo manual em processamento para esta janela. Aguarde a conclusão.", "error")
            return redirect(url_for("admin.notificacoes_list"))
        if not enqueue_result.created and enqueue_result.status == "succeeded":
            flash("Disparo manual já concluído nesta janela de execução.", "success")
            return redirect(url_for("admin.notificacoes_list"))
        if not enqueue_result.created and enqueue_result.status in {"dead_letter", "failed", "canceled"}:
            retry_key = f"{idempotency_key}:retry:{int(time.time())}"
            try:
                enqueue_result = enqueue_notifications_job(
                    db,
                    source="manual",
                    requested_by=int(current_user.id),
                    idempotency_key=retry_key,
                    request_id=getattr(flask_g, "request_id", None),
                )
                db.commit()
            except Exception:
                rollback_db(db)
                current_app.logger.exception("Falha ao reenfileirar disparo manual de notificações.")
                flash("O disparo anterior falhou e não foi possível reenfileirar agora. Tente novamente.", "error")
                return redirect(url_for("admin.notificacoes_list"))

        flash(
            f"Disparo manual enfileirado com sucesso (job #{enqueue_result.job_id}). "
            "Acompanhe o status no monitoramento de jobs.",
            "success",
        )
        return redirect(url_for("admin.notificacoes_list"))
    except Exception:
        current_app.logger.exception("Falha inesperada no disparo manual de notificações.")
        flash("Não foi possível concluir o disparo manual neste momento. Tente novamente.", "error")
        return redirect(url_for("dashboard.dashboard"))
