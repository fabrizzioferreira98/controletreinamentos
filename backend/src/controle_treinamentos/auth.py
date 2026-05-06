from __future__ import annotations

import json
from functools import wraps

from flask import abort, has_request_context, redirect, request, url_for
from flask_login import current_user
from werkzeug.routing import BuildError

from .core.auth_contract import AuthRequiredError
from .core.domain_errors import DomainForbiddenError
from .core.http_utils import (
    domain_error_payload,
    expects_binary_asset_response,
    expects_json_response,
    safe_next_url,
)

FINANCE_PERMISSION_ITEMS = (
    ("finance:missions:read", "Financeiro - Missoes: consultar"),
    ("finance:missions:create", "Financeiro - Missoes: criar"),
    ("finance:missions:update", "Financeiro - Missoes: editar"),
    ("finance:missions:cancel", "Financeiro - Missoes: cancelar"),
    ("finance:missions:delete", "Financeiro - Missoes: excluir"),
    ("finance:missions:recalculate", "Financeiro - Missoes: recalcular"),
    ("finance:bonuses:read", "Financeiro - Bonificacoes: consultar"),
    ("finance:bonuses:recalculate", "Financeiro - Bonificacoes: recalcular"),
    ("finance:parameters:read", "Financeiro - Parametros: consultar"),
    ("finance:parameters:create", "Financeiro - Parametros: criar"),
    ("finance:parameters:update", "Financeiro - Parametros: editar"),
    ("finance:periods:read", "Financeiro - Competencias: consultar"),
    ("finance:periods:recalculate", "Financeiro - Competencias: recalcular"),
    ("finance:periods:close", "Financeiro - Competencias: fechar"),
    ("finance:periods:reopen", "Financeiro - Competencias: reabrir"),
    ("finance:audit:read", "Financeiro - Auditoria: consultar"),
    ("finance:divergences:read", "Financeiro - Divergencias: consultar"),
    ("finance:exports:create", "Financeiro - Exportacoes: gerar"),
)

FINANCE_PERMISSION_KEYS = tuple(item_key for item_key, _label in FINANCE_PERMISSION_ITEMS)

FINANCE_ROLE_PERMISSION_SETS = {
    "admin": set(FINANCE_PERMISSION_KEYS),
    "gestora": set(FINANCE_PERMISSION_KEYS),
    "financeiro": set(FINANCE_PERMISSION_KEYS),
    "operacoes": {
        "finance:missions:read",
        "finance:missions:create",
        "finance:missions:update",
        "finance:bonuses:read",
    },
    "auditor": {
        "finance:missions:read",
        "finance:bonuses:read",
        "finance:parameters:read",
        "finance:periods:read",
        "finance:audit:read",
        "finance:divergences:read",
    },
    "leitura": {
        "finance:missions:read",
        "finance:bonuses:read",
        "finance:periods:read",
    },
}

MODULE_PERMISSION_GROUPS = [
    {
        "key": "dashboards",
        "label": "Dashboards",
        "items": [
            ("dashboard:view", "Visão geral"),
        ],
    },
    {
        "key": "operacoes",
        "label": "Operações",
        "items": [
            ("operacoes:view", "Acesso ao módulo Operações"),
            ("pernoites:view", "Pernoites"),
            ("pernoites:create", "Criar pernoites"),
            ("pernoites:edit", "Editar pernoites"),
            ("pernoites:delete", "Excluir pernoites"),
            ("bases:view", "Gestão de Bases"),
        ],
    },
    {
        "key": "financeiro",
        "label": "Financeiro",
        "items": list(FINANCE_PERMISSION_ITEMS),
    },
    {
        "key": "relatorios",
        "label": "Relatórios",
        "items": [
            ("relatorios:view", "Acesso ao módulo Relatórios"),
            ("relatorio_habilitacoes:view", "Consolidado de habilitações"),
            ("relatorio_individual:view", "Relatório individual"),
        ],
    },
    {
        "key": "cadastros",
        "label": "Cadastros",
        "items": [
            ("cadastros:view", "Acesso ao módulo Cadastros"),
            ("tripulantes:view", "Tripulantes"),
            ("tripulantes:create", "Criar tripulantes"),
            ("tripulantes:edit", "Editar tripulantes"),
            ("tripulantes:delete", "Excluir tripulantes"),
            ("treinamentos:view", "Treinamentos"),
            ("treinamentos:create", "Criar treinamentos"),
            ("treinamentos:edit", "Editar treinamentos"),
            ("treinamentos:delete", "Excluir treinamentos"),
            ("treinamentos_anexos:view", "Visualizar anexos PDF de treinamentos"),
            ("treinamentos_anexos:create", "Enviar anexos PDF de treinamentos"),
            ("treinamentos_anexos:delete", "Excluir anexos PDF de treinamentos"),
            ("tripulantes_file:view", "Visualizar documentos File de tripulantes"),
            ("tripulantes_file:create", "Enviar documentos PDF na aba File"),
            ("tripulantes_file:delete", "Remover documentos PDF na aba File"),
            ("tripulantes_file:replace", "Substituir documentos PDF na aba File"),
            ("equipamentos:view", "Equipamentos"),
            ("equipamentos:create", "Criar equipamentos"),
            ("equipamentos:edit", "Editar equipamentos"),
            ("equipamentos:delete", "Excluir equipamentos"),
            ("tipos_treinamento:view", "Tipos de treinamento"),
            ("tipos_treinamento:create", "Criar tipos de treinamento"),
            ("tipos_treinamento:edit", "Editar tipos de treinamento"),
            ("tipos_treinamento:delete", "Excluir tipos de treinamento"),
        ],
    },
    {
        "key": "usuarios",
        "label": "Usuários e permissões",
        "items": [
            ("usuarios:view", "Usuários"),
            ("usuarios:manage", "Editar permissões de usuários"),
            ("monitoramento:view", "Monitoramento do sistema"),
            ("backups:view", "Backups"),
            ("backups:run", "Executar backup manual"),
            ("auditoria:view", "Auditoria"),
            ("notificacoes:view", "Destinatários de e-mail"),
            ("notificacoes:edit", "Editar destinatários de e-mail"),
        ],
    },
]

ALL_PERMISSION_KEYS = {
    item_key
    for group in MODULE_PERMISSION_GROUPS
    for item_key, _label in group["items"]
}

DEFAULT_OPERATOR_PERMISSIONS = {
    "dashboard:view",
    "operacoes:view",
    "pernoites:view",
    "pernoites:create",
    "pernoites:edit",
    "pernoites:delete",
    "bases:view",
    "relatorios:view",
    "relatorio_habilitacoes:view",
    "relatorio_individual:view",
    "cadastros:view",
    "tripulantes:view",
    "tripulantes:create",
    "tripulantes:edit",
    "tripulantes:delete",
    "treinamentos:view",
    "treinamentos:create",
    "treinamentos:edit",
    "treinamentos:delete",
    "treinamentos_anexos:view",
    "treinamentos_anexos:create",
    "treinamentos_anexos:delete",
    "tripulantes_file:view",
    "tripulantes_file:create",
    "tripulantes_file:delete",
    "tripulantes_file:replace",
    "equipamentos:view",
    "equipamentos:create",
    "equipamentos:edit",
    "equipamentos:delete",
    "tipos_treinamento:view",
    "tipos_treinamento:create",
    "tipos_treinamento:edit",
    "tipos_treinamento:delete",
    "monitoramento:view",
}

ENDPOINT_PERMISSION_MAP = {
    "dashboard.home": "dashboard:view",
    # Dashboards
    "dashboard.dashboard": "dashboard:view",
    "dashboard.api_aisweb_met": "dashboard:view",
    "dashboard.api_dashboard_summary": "dashboard:view",
    "dashboard.api_dashboard_calendar": "dashboard:view",
    "dashboard.api_dashboard_critical_trainings": "dashboard:view",
    "dashboard.api_dashboard_base_operations": "dashboard:view",
    "dashboard.api_dashboard_weather_by_base": "dashboard:view",
    "dashboard.api_dashboard_relevant_notams": "dashboard:view",
    "dashboard.api_dashboard_operational_alerts": "dashboard:view",
    # Operações
    "operacoes.api_operacoes_pernoites_list": "pernoites:view",
    "operacoes.api_operacoes_pernoite_detail": "pernoites:view",
    "operacoes.pernoites_list": "pernoites:view",
    "operacoes.pernoites_new": "pernoites:create",
    "operacoes.pernoites_edit": "pernoites:edit",
    "operacoes.pernoites_delete": "pernoites:delete",
    "bases.index": "bases:view",
    "bases.api_dados": "bases:view",
    "bases.pilot_photo": "bases:view",
    "bases.adicionar_piloto": "bases:view",
    "bases.alterar_status": "bases:view",
    "bases.mover_piloto": "bases:view",
    "bases.historico_piloto": "bases:view",
    # Relatórios
    "cadastros.treinamentos_consolidado": "relatorio_habilitacoes:view",
    "cadastros.treinamentos_consolidado_export_csv": "relatorio_habilitacoes:view",
    "cadastros.treinamentos_consolidado_export_pdf": "relatorio_habilitacoes:view",
    "cadastros.treinamentos_consolidado_relatorio": "relatorio_habilitacoes:view",
    "cadastros.tripulante_report": "relatorio_individual:view",
    "cadastros.tripulante_report_export_pdf": "relatorio_individual:view",
    "relatorios.api_relatorios_habilitacoes": "relatorio_habilitacoes:view",
    # Cadastros
    "cadastros.tripulantes_list": ("tripulantes:view", "relatorio_individual:view"),
    "cadastros.tripulante_foto": ("tripulantes:view", "relatorio_individual:view"),
    "cadastros.api_tripulantes_list": ("tripulantes:view", "relatorio_individual:view"),
    "cadastros.api_tripulantes_options": ("tripulantes:view", "relatorio_individual:view"),
    "cadastros.api_tripulante_get": ("tripulantes:view", "relatorio_individual:view"),
    "cadastros.api_tripulante_create": "tripulantes:create",
    "cadastros.api_tripulante_update": "tripulantes:edit",
    "cadastros.api_tripulante_delete": "tripulantes:delete",
    "cadastros.api_tripulante_photo_get": ("tripulantes:view", "relatorio_individual:view"),
    "cadastros.api_tripulante_photo_post": "tripulantes:edit",
    "cadastros.api_tripulante_photo_delete": "tripulantes:edit",
    "cadastros.api_tripulante_files_list": "tripulantes_file:view",
    "cadastros.api_tripulante_files_upload": "tripulantes_file:create",
    "cadastros.api_tripulante_file_get": "tripulantes_file:view",
    "cadastros.api_tripulante_file_delete": "tripulantes_file:delete",
    "cadastros.api_equipamentos_options": "equipamentos:view",
    "cadastros.api_treinamentos_list": "treinamentos:view",
    "cadastros.api_treinamentos_options": "treinamentos:view",
    "cadastros.api_treinamento_get": "treinamentos:view",
    "cadastros.api_treinamento_create": "treinamentos:create",
    "cadastros.api_treinamento_update": "treinamentos:edit",
    "cadastros.api_treinamento_delete": "treinamentos:delete",
    "cadastros.api_treinamento_attachments_list": "treinamentos_anexos:view",
    "cadastros.api_treinamento_attachments_upload": "treinamentos_anexos:create",
    "cadastros.api_treinamento_attachment_get": "treinamentos_anexos:view",
    "cadastros.api_treinamento_attachment_delete": "treinamentos_anexos:delete",
    "cadastros.tripulantes_new": "tripulantes:create",
    "cadastros.tripulantes_edit": "tripulantes:edit",
    "cadastros.tripulantes_delete": "tripulantes:delete",
    "cadastros.tripulante_file_tab": "tripulantes_file:view",
    "cadastros.tripulante_file_upload": "tripulantes_file:create",
    "cadastros.tripulante_file_get": "tripulantes_file:view",
    "cadastros.tripulante_file_get_by_source": "tripulantes_file:view",
    "cadastros.tripulante_file_delete": "tripulantes_file:delete",
    "cadastros.tripulante_file_replace": "tripulantes_file:replace",
    "cadastros.treinamentos_list": "treinamentos:view",
    "cadastros.treinamentos_new": "treinamentos:create",
    "cadastros.treinamentos_edit": "treinamentos:edit",
    "cadastros.treinamentos_delete": "treinamentos:delete",
    "cadastros.treinamentos_anexo_upload": "treinamentos_anexos:create",
    "cadastros.treinamentos_anexo_get": "treinamentos_anexos:view",
    "cadastros.treinamentos_anexo_delete": "treinamentos_anexos:delete",
    "cadastros.equipamentos_list": "equipamentos:view",
    "cadastros.equipamentos_new": "equipamentos:create",
    "cadastros.equipamentos_edit": "equipamentos:edit",
    "cadastros.equipamentos_delete": "equipamentos:delete",
    "cadastros.tipos_list": "tipos_treinamento:view",
    "cadastros.tipos_new": "tipos_treinamento:create",
    "cadastros.tipos_edit": "tipos_treinamento:edit",
    "cadastros.tipos_delete": "tipos_treinamento:delete",
    "cadastros.api_training_master_options": "tipos_treinamento:view",
    "cadastros.api_training_master_types_list": "tipos_treinamento:view",
    "cadastros.api_training_master_type_get": "tipos_treinamento:view",
    "cadastros.api_training_master_type_create": "tipos_treinamento:create",
    "cadastros.api_training_master_type_update": "tipos_treinamento:edit",
    "cadastros.api_training_master_type_delete": "tipos_treinamento:delete",
    "cadastros.api_training_master_segments_list": "tipos_treinamento:view",
    "cadastros.api_training_master_segment_get": "tipos_treinamento:view",
    "cadastros.api_training_master_segment_create": "tipos_treinamento:create",
    "cadastros.api_training_master_segment_update": "tipos_treinamento:edit",
    "cadastros.api_training_master_segment_delete": "tipos_treinamento:delete",
    "cadastros.api_training_master_hours_list": "tipos_treinamento:view",
    "cadastros.api_training_master_hour_get": "tipos_treinamento:view",
    "cadastros.api_training_master_hour_create": "tipos_treinamento:create",
    "cadastros.api_training_master_hour_update": "tipos_treinamento:edit",
    "cadastros.api_training_master_hour_delete": "tipos_treinamento:delete",
    "cadastros.api_training_program_tripulantes_options": "treinamentos:view",
    "cadastros.api_training_program_template": "treinamentos:view",
    "cadastros.api_training_program_records_list": "treinamentos:view",
    "cadastros.api_training_program_record_get": "treinamentos:view",
    "cadastros.api_training_program_batch_create": "treinamentos:create",
    "cadastros.api_training_program_record_update": "treinamentos:edit",
    "cadastros.api_training_program_record_delete": "treinamentos:delete",
    "cadastros.api_training_program_record_attachments_list": "treinamentos_anexos:view",
    "cadastros.api_training_program_record_attachments_upload": "treinamentos_anexos:create",
    "cadastros.api_training_program_record_attachment_get": "treinamentos_anexos:view",
    "cadastros.api_training_program_record_attachment_delete": "treinamentos_anexos:delete",
    # Financeiro
    "financeiro.api_finance_missions_list": "finance:missions:read",
    "financeiro.api_finance_missions_create": "finance:missions:create",
    "financeiro.api_finance_mission_preview": "finance:missions:read",
    "financeiro.api_finance_mission_detail": "finance:missions:read",
    "financeiro.api_finance_mission_preflight_calculo": "finance:missions:read",
    "financeiro.api_finance_mission_update": "finance:missions:update",
    "financeiro.api_finance_mission_recalculate": "finance:missions:recalculate",
    "financeiro.api_finance_mission_cancel": "finance:missions:cancel",
    "financeiro.api_finance_mission_delete": "finance:missions:delete",
    "financeiro.api_finance_journey_grid_list": "finance:bonuses:read",
    "financeiro.api_finance_journey_line_create": "finance:missions:create",
    "financeiro.api_finance_journey_line_preview": "finance:bonuses:read",
    "financeiro.api_finance_journey_grid_recalculate": "finance:periods:recalculate",
    "financeiro.api_finance_journey_grid_pdf": "finance:exports:create",
    "financeiro.api_finance_journey_line_update": "finance:missions:update",
    "financeiro.api_finance_journey_line_recalculate": "finance:missions:recalculate",
    "financeiro.api_finance_total_flight_hours": "finance:bonuses:read",
    "financeiro.api_finance_total_flight_hours_pdf": "finance:exports:create",
    "financeiro.api_finance_hourly_bonuses_list": "finance:bonuses:read",
    "financeiro.api_finance_hourly_bonus_detail": "finance:bonuses:read",
    "financeiro.api_finance_productivity_bonuses_list": "finance:bonuses:read",
    "financeiro.api_finance_productivity_consolidated": "finance:bonuses:read",
    "financeiro.api_finance_productivity_general_report": "finance:bonuses:read",
    "financeiro.api_finance_productivity_general_report_pdf": "finance:exports:create",
    "financeiro.api_finance_productivity_bonus_by_tripulante": "finance:bonuses:read",
    "financeiro.api_finance_individual_report_pdf": "finance:exports:create",
    "financeiro.api_finance_period_extract": "finance:bonuses:read",
    "financeiro.api_finance_period_extract_pdf": "finance:exports:create",
    "financeiro.api_finance_period_detail": "finance:periods:read",
    "financeiro.api_finance_period_preflight_calculo": "finance:periods:read",
    "financeiro.api_finance_period_report_pdf": "finance:exports:create",
    "financeiro.api_finance_period_recalculate": "finance:periods:recalculate",
    "financeiro.api_finance_period_close": "finance:periods:close",
    "financeiro.api_finance_period_reopen": "finance:periods:reopen",
    "financeiro.api_finance_parameters_list": "finance:parameters:read",
    "financeiro.api_finance_parameters_create": "finance:parameters:create",
    "financeiro.api_finance_parameters_update": "finance:parameters:update",
    "financeiro.api_finance_holidays_list": "finance:parameters:read",
    "financeiro.api_finance_holidays_create": "finance:parameters:create",
    "financeiro.api_finance_holidays_update": "finance:parameters:update",
    "financeiro.api_finance_audit_list": "finance:audit:read",
    "financeiro.api_finance_divergences_list": "finance:divergences:read",
    # Usuários
    "admin.usuarios_list": "usuarios:view",
    "admin.usuarios_new": "usuarios:manage",
    "admin.usuarios_edit": "usuarios:manage",
    "admin.monitoramento_sistema": "monitoramento:view",
    "admin.manual_usuario_pdf": "monitoramento:view",
    "admin.notificacoes_list": "notificacoes:view",
    "admin.notificacoes_new": "notificacoes:edit",
    "admin.notificacoes_edit": "notificacoes:edit",
    "admin.notificacoes_manual_send": "notificacoes:edit",
    "admin.notificacoes_test_send": "notificacoes:edit",
    "admin.backups_list": "backups:view",
    "admin.backups_run": "backups:run",
    "admin.auditoria_list": "auditoria:view",
    "admin.auditoria_export_pdf": "auditoria:view",
    "admin.jobs_requeue": "usuarios:manage",
    "admin.jobs_status": "usuarios:manage",
}

PUBLIC_ENDPOINTS = {
    "static",
    "dashboard.home",
    "auth.login",
    "auth.logout",
    "auth.api_session_state",
    "auth.api_session_login",
    "auth.api_session_logout",
    "internal_metrics",
    "healthz",
    "root_favicon",
    "root_apple_touch_icon",
}

AUTHENTICATED_ENDPOINTS = {
    "auth.api_me",
    "auth.api_capabilities",
}

DEFAULT_LANDING_ENDPOINT = "dashboard.dashboard"
LANDING_ENDPOINT_CANDIDATES: tuple[tuple[str, str], ...] = (
    ("dashboard.dashboard", "dashboard:view"),
    ("cadastros.tripulantes_list", "tripulantes:view"),
    ("cadastros.tripulantes_list", "relatorio_individual:view"),
    ("cadastros.treinamentos_list", "treinamentos:view"),
    ("cadastros.equipamentos_list", "equipamentos:view"),
    ("cadastros.tipos_list", "tipos_treinamento:view"),
    ("operacoes.pernoites_list", "pernoites:view"),
    ("bases.index", "bases:view"),
    ("relatorios.habilitacoes_consolidado", "relatorio_habilitacoes:view"),
    ("admin.usuarios_list", "usuarios:view"),
)


def normalize_permissions(value, *, perfil: str = "operador") -> set[str]:
    if perfil == "gestora":
        return set(ALL_PERMISSION_KEYS)

    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return set()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return set()
    elif isinstance(value, (list, tuple, set)):
        parsed = list(value)
    else:
        return set()

    if not isinstance(parsed, (list, tuple, set)):
        return set()

    selected = {str(item) for item in parsed if str(item) in ALL_PERMISSION_KEYS}
    dependencies = {
        "usuarios:manage": {"usuarios:view"},
        "notificacoes:edit": {"notificacoes:view"},
        "backups:run": {"backups:view"},
        "pernoites:create": {"pernoites:view"},
        "pernoites:edit": {"pernoites:view"},
        "pernoites:delete": {"pernoites:view"},
        "tripulantes:create": {"tripulantes:view"},
        "tripulantes:edit": {"tripulantes:view"},
        "tripulantes:delete": {"tripulantes:view"},
        "tripulantes_file:view": {"tripulantes:view"},
        "tripulantes_file:create": {"tripulantes_file:view", "tripulantes:edit"},
        "tripulantes_file:delete": {"tripulantes_file:view", "tripulantes:edit"},
        "tripulantes_file:replace": {"tripulantes_file:view", "tripulantes:edit", "tripulantes_file:create"},
        "treinamentos:create": {"treinamentos:view"},
        "treinamentos:edit": {"treinamentos:view"},
        "treinamentos:delete": {"treinamentos:view"},
        "treinamentos_anexos:create": {"treinamentos_anexos:view", "treinamentos:edit"},
        "treinamentos_anexos:delete": {"treinamentos_anexos:view", "treinamentos:edit"},
        "equipamentos:create": {"equipamentos:view"},
        "equipamentos:edit": {"equipamentos:view"},
        "equipamentos:delete": {"equipamentos:view"},
        "tipos_treinamento:create": {"tipos_treinamento:view"},
        "tipos_treinamento:edit": {"tipos_treinamento:view"},
        "tipos_treinamento:delete": {"tipos_treinamento:view"},
        "finance:missions:create": {"finance:missions:read"},
        "finance:missions:update": {"finance:missions:read"},
        "finance:missions:cancel": {"finance:missions:read"},
        "finance:missions:delete": {"finance:missions:read"},
        "finance:missions:recalculate": {"finance:missions:read"},
        "finance:bonuses:recalculate": {"finance:bonuses:read"},
        "finance:parameters:create": {"finance:parameters:read"},
        "finance:parameters:update": {"finance:parameters:read"},
        "finance:periods:recalculate": {"finance:periods:read"},
        "finance:periods:close": {"finance:periods:read"},
        "finance:periods:reopen": {"finance:periods:read"},
        "finance:exports:create": {"finance:bonuses:read", "finance:periods:read"},
    }
    for key in list(selected):
        selected.update(dependencies.get(key, set()))
    return selected


def serialize_permissions(value, *, perfil: str = "operador") -> str:
    normalized = sorted(normalize_permissions(value, perfil=perfil))
    return json.dumps(normalized, ensure_ascii=True)


def resolve_landing_endpoint_for_user(user) -> str:
    if not getattr(user, "is_authenticated", False):
        return DEFAULT_LANDING_ENDPOINT
    if getattr(user, "perfil", "") == "gestora":
        return DEFAULT_LANDING_ENDPOINT
    if not hasattr(user, "has_permission"):
        return DEFAULT_LANDING_ENDPOINT
    for endpoint, permission_key in LANDING_ENDPOINT_CANDIDATES:
        try:
            if user.has_permission(permission_key):
                return endpoint
        except Exception:
            continue
    return DEFAULT_LANDING_ENDPOINT


def resolve_landing_url_for_user(user) -> str:
    if not has_request_context():
        return "/dashboard"
    endpoint = resolve_landing_endpoint_for_user(user)
    try:
        return url_for(endpoint)
    except BuildError:
        return url_for("dashboard.dashboard")


def endpoint_required_permission(endpoint: str | None):
    if not endpoint:
        return None
    if endpoint in PUBLIC_ENDPOINTS:
        return None
    if "." not in endpoint:
        return None
    return ENDPOINT_PERMISSION_MAP.get(endpoint)


def is_endpoint_permitted(user, endpoint: str | None) -> bool:
    if not endpoint:
        return True
    if endpoint in PUBLIC_ENDPOINTS:
        return True
    if endpoint in AUTHENTICATED_ENDPOINTS:
        return bool(getattr(user, "is_authenticated", False))
    if "." not in endpoint:
        return True
    permission_key = endpoint_required_permission(endpoint)
    if not permission_key:
        return False
    if not getattr(user, "is_authenticated", False):
        return False
    if not hasattr(user, "has_permission"):
        return False
    if isinstance(permission_key, (tuple, list, set)):
        return any(user.has_permission(item) for item in permission_key)
    return bool(user.has_permission(permission_key))


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if not current_user.is_authenticated:
                if expects_json_response():
                    return domain_error_payload(AuthRequiredError())
                if expects_binary_asset_response():
                    return "", 401
                next_url = safe_next_url(
                    request.full_path if request.method == "GET" else None,
                    url_for("dashboard.dashboard"),
                )
                return redirect(url_for("auth.login", next=next_url))
            if current_user.perfil not in roles:
                if expects_json_response():
                    return domain_error_payload(
                        DomainForbiddenError("Acesso negado para esta operação.", code="forbidden")
                    )
                abort(403)
            return view(*args, **kwargs)
        return wrapped_view
    return decorator


def permission_required(*permission_keys: str):
    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if not current_user.is_authenticated:
                if expects_json_response():
                    return domain_error_payload(AuthRequiredError())
                if expects_binary_asset_response():
                    return "", 401
                next_url = safe_next_url(
                    request.full_path if request.method == "GET" else None,
                    url_for("dashboard.dashboard"),
                )
                return redirect(url_for("auth.login", next=next_url))
            allowed = any(current_user.has_permission(permission_key) for permission_key in permission_keys)
            if not allowed:
                if expects_json_response():
                    return domain_error_payload(
                        DomainForbiddenError("Acesso negado para esta operação.", code="forbidden")
                    )
                abort(403)
            return view(*args, **kwargs)

        return wrapped_view

    return decorator
