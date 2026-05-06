from __future__ import annotations

from pathlib import Path

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.contracts.operacoes import (
    OPERACOES_FUTURE_API_CONTRACT,
    OPERACOES_READ_API_ENDPOINTS,
    OPERACOES_SSR_CURRENT_ENDPOINTS,
)

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
BACKEND_SRC = ROOT / "backend" / "src" / "controle_treinamentos"
TEMPLATES = BACKEND_SRC / "templates"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_training_program_is_the_spa_runtime_contract_and_generic_training_is_residual():
    list_page = _read(FRONTEND_SRC / "features" / "treinamentos" / "list-page.js")
    form_page = _read(FRONTEND_SRC / "features" / "treinamentos" / "form-page.js")
    root_page = _read(FRONTEND_SRC / "features" / "training-root" / "page.js")
    route_registry = _read(FRONTEND_SRC / "app" / "route-registry.js")
    backend_generic_routes = _read(BACKEND_SRC / "api" / "http" / "cadastros" / "routes.py")

    assert "#/treinamentos" in route_registry
    assert "/api/v1/treinamentos-tripulantes" in list_page
    assert "/api/v1/treinamentos-tripulantes" in form_page
    assert "/api/v1/treinamento-raiz" in root_page
    assert "legacyRenderTreinamentoFormPage" not in form_page
    assert "/api/v1/treinamentos/" not in form_page

    # Generic training remains registered only as residual/historical API; it is not consumed by the routed SPA.
    assert '@cadastros_bp.route("/api/v1/treinamentos", methods=["GET"])' in backend_generic_routes
    assert '@cadastros_bp.route("/api/v1/treinamentos/<int:treinamento_id>", methods=["GET"])' in backend_generic_routes


def test_training_program_attachment_contract_is_canonical_for_routed_spa():
    app = create_app()
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    form_page = _read(FRONTEND_SRC / "features" / "treinamentos" / "form-page.js")
    training_program_contract = _read(BACKEND_SRC / "contracts" / "training_program.py")

    assert "/api/v1/treinamentos-tripulantes/<int:treinamento_id>/attachments" in rules
    assert "/api/v1/treinamentos-tripulantes/<int:treinamento_id>/attachments/<int:attachment_id>" in rules
    assert "/api/v1/treinamentos-tripulantes/${treinamentoId}/attachments" in form_page
    assert 'f"/api/v1/treinamentos-tripulantes/{int(row[\'id\'])}/attachments"' in training_program_contract


def test_tripulante_files_api_is_the_spa_contract_and_ssr_file_is_direct_compat_only():
    tripulante_form = _read(FRONTEND_SRC / "features" / "tripulantes" / "form-page.js")
    shell_navigation = _read(FRONTEND_SRC / "shell" / "navigation.js")
    backend_links = _read(FRONTEND_SRC / "compat" / "backend-links.js")
    base_template = _read(TEMPLATES / "base.html")
    ssr_file_routes = _read(BACKEND_SRC / "blueprints" / "cadastros" / "routes_file.py")

    assert "/api/v1/tripulantes/${tripulanteId}/files" in tripulante_form
    assert "tripulante_file_tab" in ssr_file_routes
    assert "tripulante_file_upload" in ssr_file_routes
    assert "tripulante_file_tab" not in shell_navigation
    assert "tripulante_file_tab" not in backend_links
    assert "url_for('cadastros.tripulante_file_tab')" not in base_template


def test_operacoes_are_not_ambiguous_between_future_api_and_current_ssr():
    dashboard_data = _read(FRONTEND_SRC / "features" / "dashboard-operacional" / "lower-section-data.js")
    dashboard_page = _read(FRONTEND_SRC / "features" / "dashboard-operacional" / "page.js")

    assert {item["classification"] for item in OPERACOES_SSR_CURRENT_ENDPOINTS} == {"ssr_canonical_current_direct"}
    assert {item["classification"] for item in OPERACOES_READ_API_ENDPOINTS} == {"api_read_canonical_registered"}
    assert OPERACOES_FUTURE_API_CONTRACT["status"] == "read_api_registered_write_ssr_canonical_current"
    assert OPERACOES_FUTURE_API_CONTRACT["canonical_current"] == "ssr_ui_and_write_current_with_api_read_model"
    assert OPERACOES_FUTURE_API_CONTRACT["write_policy"].startswith("Create/edit/delete remain SSR canonical current")
    assert "futureHref" not in dashboard_data
    assert "data-future-href" not in dashboard_page
    assert "/operacoes/voos" not in dashboard_data
    assert "/operacoes/ocorrencias" not in dashboard_data


def test_contract_route_deduplication_is_documented_and_indexed():
    migration = _read(ROOT / "docs" / "migration" / "90.contract-route-deduplication-governance.md")
    migration_readme = _read(ROOT / "docs" / "migration" / "README.md")
    project_readme = _read(ROOT / "README.md")

    for expected in (
        "Treinamentos por tripulante",
        "Arquivos de tripulante",
        "Operacoes/Pernoites",
        "ssr_canonical_current_direct",
        "/api/v1/treinamentos-tripulantes/<id>/attachments",
    ):
        assert expected in migration

    assert "90.contract-route-deduplication-governance.md" in migration_readme
    assert "90.contract-route-deduplication-governance.md" in project_readme
