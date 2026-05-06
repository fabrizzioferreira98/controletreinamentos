import pytest

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.auth import (
    ALL_PERMISSION_KEYS,
    DEFAULT_OPERATOR_PERMISSIONS,
    ENDPOINT_PERMISSION_MAP,
    FINANCE_PERMISSION_KEYS,
    FINANCE_ROLE_PERMISSION_SETS,
    MODULE_PERMISSION_GROUPS,
    is_endpoint_permitted,
    normalize_permissions,
    resolve_landing_endpoint_for_user,
    resolve_landing_url_for_user,
)
from backend.src.controle_treinamentos.contracts.financeiro import FINANCE_API_ROUTE_PREFIX
from backend.src.controle_treinamentos.contracts.financeiro_http import FINANCE_HTTP_CONTRACTS


class StubUser:
    def __init__(self, *, authenticated: bool, allowed=None):
        self.is_authenticated = authenticated
        self._allowed = allowed or set()

    def has_permission(self, key: str) -> bool:
        return key in self._allowed


class StubAnonymous:
    is_authenticated = False


def _normalize_registered_finance_path(path):
    normalized = path.replace("<string:competencia>", "{competencia}")
    normalized = normalized.replace("<int:tripulante_id>", "{tripulante_id}")
    normalized = normalized.replace("<int:mission_id>", "{id}")
    normalized = normalized.replace("<int:calculation_id>", "{id}")
    normalized = normalized.replace("<int:parameter_id>", "{id}")
    return normalized.replace("<int:holiday_id>", "{id}")


def test_normalize_permissions_applies_dependencies():
    selected = normalize_permissions(["usuarios:manage"], perfil="operador")
    assert "usuarios:manage" in selected
    assert "usuarios:view" in selected


def test_normalize_permissions_tripulante_file_dependencies():
    selected = normalize_permissions(["tripulantes_file:replace"], perfil="operador")
    assert "tripulantes_file:replace" in selected
    assert "tripulantes_file:create" in selected
    assert "tripulantes_file:view" in selected
    assert "tripulantes:edit" in selected


def test_normalize_permissions_denies_for_operator_when_empty():
    selected = normalize_permissions([], perfil="operador")
    assert selected == set()


@pytest.mark.parametrize("raw_value", ["null", "1", "true"])
def test_normalize_permissions_handles_non_iterable_json_values(raw_value):
    selected = normalize_permissions(raw_value, perfil="operador")
    assert selected == set()


def test_has_permission_denies_blank_permission_key():
    from backend.src.controle_treinamentos.models import User

    dummy = User("1", "Nome", "login", "email@test", "operador", 1, "[]")
    assert dummy.has_permission("") is False
    assert dummy.has_permission(None) is False


def test_gestora_receives_all_permissions():
    selected = normalize_permissions([], perfil="gestora")
    assert "usuarios:manage" in selected
    assert "backups:run" in selected


def test_finance_permissions_are_registered_in_catalog():
    finance_group = next(group for group in MODULE_PERMISSION_GROUPS if group["key"] == "financeiro")
    finance_group_keys = {item_key for item_key, _label in finance_group["items"]}

    assert set(FINANCE_PERMISSION_KEYS) == {
        "finance:missions:read",
        "finance:missions:create",
        "finance:missions:update",
        "finance:missions:cancel",
        "finance:missions:recalculate",
        "finance:bonuses:read",
        "finance:bonuses:recalculate",
        "finance:parameters:read",
        "finance:parameters:create",
        "finance:parameters:update",
        "finance:periods:read",
        "finance:periods:recalculate",
        "finance:periods:close",
        "finance:periods:reopen",
        "finance:audit:read",
        "finance:divergences:read",
        "finance:exports:create",
    }
    assert finance_group_keys == set(FINANCE_PERMISSION_KEYS)
    assert set(FINANCE_PERMISSION_KEYS) <= ALL_PERMISSION_KEYS


def test_gestora_receives_all_finance_permissions_as_admin_equivalent():
    selected = normalize_permissions([], perfil="gestora")

    assert set(FINANCE_PERMISSION_KEYS) <= selected
    assert FINANCE_ROLE_PERMISSION_SETS["gestora"] == set(FINANCE_PERMISSION_KEYS)
    assert FINANCE_ROLE_PERMISSION_SETS["admin"] == set(FINANCE_PERMISSION_KEYS)


def test_default_operator_permissions_do_not_grant_finance_scope():
    assert not any(permission.startswith("finance:") for permission in DEFAULT_OPERATOR_PERMISSIONS)
    assert normalize_permissions([], perfil="operador") == set()


def test_finance_permission_dependencies_are_applied():
    selected = normalize_permissions(
        [
            "finance:missions:cancel",
            "finance:missions:recalculate",
            "finance:bonuses:recalculate",
            "finance:parameters:update",
            "finance:periods:close",
            "finance:exports:create",
        ],
        perfil="operador",
    )

    assert "finance:missions:read" in selected
    assert "finance:bonuses:read" in selected
    assert "finance:parameters:read" in selected
    assert "finance:periods:read" in selected


def test_finance_role_permission_templates_match_documented_matrix():
    assert FINANCE_ROLE_PERMISSION_SETS["financeiro"] == set(FINANCE_PERMISSION_KEYS)
    assert FINANCE_ROLE_PERMISSION_SETS["operacoes"] == {
        "finance:missions:read",
        "finance:missions:create",
        "finance:missions:update",
        "finance:bonuses:read",
    }
    assert FINANCE_ROLE_PERMISSION_SETS["auditor"] == {
        "finance:missions:read",
        "finance:bonuses:read",
        "finance:parameters:read",
        "finance:periods:read",
        "finance:audit:read",
        "finance:divergences:read",
    }
    assert FINANCE_ROLE_PERMISSION_SETS["leitura"] == {
        "finance:missions:read",
        "finance:bonuses:read",
        "finance:periods:read",
    }


def test_finance_endpoint_mappings_match_runtime_http_contracts():
    app = create_app()
    expected_permissions = {
        (contract["method"], contract["path"]): contract["permission"]
        for contract in FINANCE_HTTP_CONTRACTS
    }
    registered_endpoints = {}
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith(FINANCE_API_ROUTE_PREFIX):
            continue
        normalized_path = _normalize_registered_finance_path(rule.rule)
        for method in set(rule.methods) & {"GET", "POST", "PATCH"}:
            registered_endpoints[(method, normalized_path)] = rule.endpoint

    assert set(registered_endpoints) == set(expected_permissions)
    for key, endpoint in registered_endpoints.items():
        assert ENDPOINT_PERMISSION_MAP.get(endpoint) == expected_permissions[key]

    mapped_finance_endpoints = {
        endpoint
        for endpoint in ENDPOINT_PERMISSION_MAP
        if str(endpoint).startswith("financeiro.")
    }
    assert mapped_finance_endpoints == set(registered_endpoints.values())


def test_export_pdf_endpoint_is_protected():
    assert ENDPOINT_PERMISSION_MAP.get("financeiro.api_finance_period_report_pdf") == "finance:exports:create"
    assert ENDPOINT_PERMISSION_MAP.get("financeiro.api_finance_individual_report_pdf") == "finance:exports:create"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.treinamentos_consolidado_export_pdf") == "relatorio_habilitacoes:view"
    assert ENDPOINT_PERMISSION_MAP.get("admin.monitoramento_sistema") == "monitoramento:view"
    assert ENDPOINT_PERMISSION_MAP.get("admin.manual_usuario_pdf") == "monitoramento:view"
    assert ENDPOINT_PERMISSION_MAP.get("admin.jobs_requeue") == "usuarios:manage"
    assert ENDPOINT_PERMISSION_MAP.get("bases.pilot_photo") == "bases:view"


def test_dashboard_api_endpoints_are_protected():
    assert ENDPOINT_PERMISSION_MAP.get("dashboard.api_aisweb_met") == "dashboard:view"
    assert ENDPOINT_PERMISSION_MAP.get("dashboard.api_dashboard_summary") == "dashboard:view"
    assert ENDPOINT_PERMISSION_MAP.get("dashboard.api_dashboard_calendar") == "dashboard:view"
    assert ENDPOINT_PERMISSION_MAP.get("dashboard.api_dashboard_critical_trainings") == "dashboard:view"


def test_relatorios_api_endpoints_are_protected():
    assert ENDPOINT_PERMISSION_MAP.get("relatorios.api_relatorios_habilitacoes") == "relatorio_habilitacoes:view"


def test_tripulante_file_endpoints_are_protected():
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.tripulante_file_tab") == "tripulantes_file:view"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.tripulante_file_upload") == "tripulantes_file:create"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.tripulante_file_get") == "tripulantes_file:view"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.tripulante_file_get_by_source") == "tripulantes_file:view"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.tripulante_file_delete") == "tripulantes_file:delete"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.tripulante_file_replace") == "tripulantes_file:replace"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_tripulante_files_list") == "tripulantes_file:view"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_tripulante_files_upload") == "tripulantes_file:create"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_tripulante_file_get") == "tripulantes_file:view"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_tripulante_file_delete") == "tripulantes_file:delete"


def test_tripulante_photo_api_endpoints_are_protected():
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_tripulante_photo_get") == ("tripulantes:view", "relatorio_individual:view")
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_tripulante_photo_post") == "tripulantes:edit"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_tripulante_photo_delete") == "tripulantes:edit"


def test_treinamentos_api_endpoints_are_protected():
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_equipamentos_options") == "equipamentos:view"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_treinamentos_list") == "treinamentos:view"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_treinamentos_options") == "treinamentos:view"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_treinamento_get") == "treinamentos:view"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_treinamento_create") == "treinamentos:create"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_treinamento_update") == "treinamentos:edit"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_treinamento_delete") == "treinamentos:delete"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_treinamento_attachments_list") == "treinamentos_anexos:view"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_treinamento_attachments_upload") == "treinamentos_anexos:create"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_treinamento_attachment_get") == "treinamentos_anexos:view"


def test_equipamentos_options_endpoint_uses_cadastro_permission_not_treinamentos():
    endpoint = "cadastros.api_equipamentos_options"

    assert ENDPOINT_PERMISSION_MAP.get(endpoint) == "equipamentos:view"
    assert is_endpoint_permitted(
        StubUser(authenticated=True, allowed={"equipamentos:view"}),
        endpoint,
    ) is True
    assert is_endpoint_permitted(
        StubUser(authenticated=True, allowed={"treinamentos:view"}),
        endpoint,
    ) is False


def test_training_program_api_endpoints_are_protected():
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_training_master_options") == "tipos_treinamento:view"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_training_master_type_create") == "tipos_treinamento:create"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_training_master_segment_update") == "tipos_treinamento:edit"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_training_master_hour_delete") == "tipos_treinamento:delete"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_training_program_tripulantes_options") == "treinamentos:view"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_training_program_template") == "treinamentos:view"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_training_program_batch_create") == "treinamentos:create"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_training_program_record_update") == "treinamentos:edit"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_training_program_record_delete") == "treinamentos:delete"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_training_program_record_attachments_list") == "treinamentos_anexos:view"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_training_program_record_attachments_upload") == "treinamentos_anexos:create"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_training_program_record_attachment_get") == "treinamentos_anexos:view"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_training_program_record_attachment_delete") == "treinamentos_anexos:delete"


def test_notificacoes_admin_endpoints_are_protected():
    assert ENDPOINT_PERMISSION_MAP.get("admin.notificacoes_list") == "notificacoes:view"
    assert ENDPOINT_PERMISSION_MAP.get("admin.notificacoes_new") == "notificacoes:edit"
    assert ENDPOINT_PERMISSION_MAP.get("admin.notificacoes_edit") == "notificacoes:edit"
    assert ENDPOINT_PERMISSION_MAP.get("admin.notificacoes_manual_send") == "notificacoes:edit"
    assert ENDPOINT_PERMISSION_MAP.get("admin.notificacoes_test_send") == "notificacoes:edit"


def test_is_endpoint_permitted_returns_true_for_unmapped_endpoint():
    user = StubUser(authenticated=True, allowed=set())
    assert is_endpoint_permitted(user, "healthcheck") is True


def test_is_endpoint_permitted_blocks_unmapped_namespaced_endpoint():
    user = StubUser(authenticated=True, allowed={"dashboard:view"})
    assert is_endpoint_permitted(user, "admin.endpoint_novo_sem_mapeamento") is False


def test_is_endpoint_permitted_blocks_unauthenticated_user_for_mapped_endpoint():
    user = StubUser(authenticated=False, allowed=set())
    assert is_endpoint_permitted(user, "cadastros.tripulantes_list") is False


def test_is_endpoint_permitted_blocks_user_without_permission():
    user = StubUser(authenticated=True, allowed={"dashboard:view"})
    assert is_endpoint_permitted(user, "cadastros.tripulantes_list") is False


def test_is_endpoint_permitted_allows_user_with_permission():
    user = StubUser(authenticated=True, allowed={"tripulantes:view"})
    assert is_endpoint_permitted(user, "cadastros.tripulantes_list") is True


def test_is_endpoint_permitted_allows_user_with_relatorio_individual_permission():
    user = StubUser(authenticated=True, allowed={"relatorio_individual:view"})
    assert is_endpoint_permitted(user, "cadastros.tripulantes_list") is True
    assert is_endpoint_permitted(user, "cadastros.api_tripulantes_list") is True
    assert is_endpoint_permitted(user, "cadastros.api_tripulantes_options") is True


def test_resolve_landing_endpoint_prefers_dashboard_when_available():
    user = StubUser(authenticated=True, allowed={"dashboard:view", "tripulantes:view"})
    assert resolve_landing_endpoint_for_user(user) == "dashboard.dashboard"


def test_resolve_landing_endpoint_falls_back_to_first_allowed_candidate():
    user = StubUser(authenticated=True, allowed={"tripulantes:view"})
    assert resolve_landing_endpoint_for_user(user) == "cadastros.tripulantes_list"


def test_resolve_landing_endpoint_defaults_for_anonymous():
    assert resolve_landing_endpoint_for_user(StubAnonymous()) == "dashboard.dashboard"


def test_resolve_landing_url_uses_endpoint_resolution():
    app = create_app()
    user = StubUser(authenticated=True, allowed={"tripulantes:view"})
    with app.test_request_context("/"):
        assert resolve_landing_url_for_user(user) == "/tripulantes"
