import pytest

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.auth import (
    ENDPOINT_PERMISSION_MAP,
    is_endpoint_permitted,
    normalize_permissions,
    resolve_landing_endpoint_for_user,
    resolve_landing_url_for_user,
)


class StubUser:
    def __init__(self, *, authenticated: bool, allowed=None):
        self.is_authenticated = authenticated
        self._allowed = allowed or set()

    def has_permission(self, key: str) -> bool:
        return key in self._allowed


class StubAnonymous:
    is_authenticated = False


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


def test_normalize_permissions_defaults_for_operator_when_empty():
    selected = normalize_permissions([], perfil="operador")
    assert "dashboard:view" in selected
    assert "tripulantes:view" in selected


@pytest.mark.parametrize("raw_value", ["null", "1", "true"])
def test_normalize_permissions_handles_non_iterable_json_values(raw_value):
    selected = normalize_permissions(raw_value, perfil="operador")
    assert "dashboard:view" in selected
    assert "tripulantes:view" in selected


def test_gestora_receives_all_permissions():
    selected = normalize_permissions([], perfil="gestora")
    assert "usuarios:manage" in selected
    assert "backups:run" in selected


def test_export_pdf_endpoint_is_protected():
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.treinamentos_consolidado_export_pdf") == "relatorio_habilitacoes:view"
    assert ENDPOINT_PERMISSION_MAP.get("relatorios.produtividade_consolidado_export_pdf") == "relatorio_produtividade:view"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.produtividade_tripulante_export_pdf") == "relatorio_produtividade:view"
    assert ENDPOINT_PERMISSION_MAP.get("relatorios.produtividade_conferencia_set") == "relatorio_produtividade:view"
    assert ENDPOINT_PERMISSION_MAP.get("admin.monitoramento_sistema") == "monitoramento:view"
    assert ENDPOINT_PERMISSION_MAP.get("admin.manual_usuario_pdf") == "monitoramento:view"
    assert ENDPOINT_PERMISSION_MAP.get("admin.jobs_requeue") == "usuarios:manage"
    assert ENDPOINT_PERMISSION_MAP.get("bases.pilot_photo") == "bases:view"


def test_dashboard_api_endpoints_are_protected():
    assert ENDPOINT_PERMISSION_MAP.get("dashboard.api_dashboard_summary") == "dashboard:view"
    assert ENDPOINT_PERMISSION_MAP.get("dashboard.api_dashboard_calendar") == "dashboard:view"
    assert ENDPOINT_PERMISSION_MAP.get("dashboard.api_dashboard_critical_trainings") == "dashboard:view"
    assert ENDPOINT_PERMISSION_MAP.get("dashboard.api_tv_vencimentos") == "tv_vencimentos:view"
    assert ENDPOINT_PERMISSION_MAP.get("dashboard.api_tv_produtividade") == "tv_produtividade:view"


def test_relatorios_api_endpoints_are_protected():
    assert ENDPOINT_PERMISSION_MAP.get("relatorios.api_relatorios_habilitacoes") == "relatorio_habilitacoes:view"
    assert ENDPOINT_PERMISSION_MAP.get("relatorios.api_relatorios_produtividade") == "relatorio_produtividade:view"
    assert ENDPOINT_PERMISSION_MAP.get("relatorios.api_relatorios_produtividade_conferencias") == "relatorio_produtividade:view"


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
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_treinamentos_list") == "treinamentos:view"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_treinamentos_options") == "treinamentos:view"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_treinamento_get") == "treinamentos:view"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_treinamento_create") == "treinamentos:create"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_treinamento_update") == "treinamentos:edit"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_treinamento_delete") == "treinamentos:delete"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_treinamento_attachments_list") == "treinamentos_anexos:view"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_treinamento_attachments_upload") == "treinamentos_anexos:create"
    assert ENDPOINT_PERMISSION_MAP.get("cadastros.api_treinamento_attachment_get") == "treinamentos_anexos:view"


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
