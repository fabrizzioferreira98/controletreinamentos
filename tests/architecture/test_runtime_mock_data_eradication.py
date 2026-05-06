from __future__ import annotations

from pathlib import Path

from backend.src.controle_treinamentos.contracts.financeiro import FINANCE_STUB_API_PATHS
from backend.src.controle_treinamentos.contracts.financeiro_http import FINANCE_STUB_HTTP_CONTRACTS

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
BACKEND_SRC = ROOT / "backend" / "src" / "controle_treinamentos"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_operational_dashboard_does_not_import_or_export_runtime_business_mocks():
    feature_dir = FRONTEND_SRC / "features" / "dashboard-operacional"
    page = _read(feature_dir / "page.js")
    upper_data = _read(feature_dir / "upper-section-data.js")
    lower_data = _read(feature_dir / "lower-section-data.js")
    combined = "\n".join([page, upper_data, lower_data])

    for forbidden in (
        "DASHBOARD_UPPER_SECTION_MOCK",
        "DASHBOARD_LOWER_SECTION_MOCK",
        "BASE_MOCK_BLUEPRINTS",
        "createMockPilot",
        "createMockPilots",
    ):
        assert forbidden not in combined

    assert "DASHBOARD_UPPER_SECTION_EMPTY" in upper_data
    assert "DASHBOARD_LOWER_SECTION_EMPTY" in lower_data
    assert "DASHBOARD_OPERATIONAL_QUICK_ACTIONS" in lower_data
    assert 'from "./upper-section-data.js"' in page
    assert 'from "./lower-section-data.js"' in page


def test_operational_dashboard_initial_render_uses_real_endpoints_or_honest_empty_states():
    page = _read(FRONTEND_SRC / "features" / "dashboard-operacional" / "page.js")

    assert 'api("/api/v1/dashboard/summary")' in page
    assert 'api("/api/v1/dashboard/critical-trainings?limit=20")' in page
    assert "api(DASHBOARD_BASES_MAP_ENDPOINT" in page
    assert "api(DASHBOARD_WEATHER_BY_BASE_ENDPOINT" in page
    assert "api(DASHBOARD_RELEVANT_NOTAMS_ENDPOINT" in page
    assert "api(DASHBOARD_OPERATIONAL_ALERTS_ENDPOINT" in page
    assert "buildDashboardUpperRuntimeData" in page
    assert "buildDashboardLowerRuntimeData" in page
    assert "renderDashboardOperationalTicker" in page
    assert "data-dashboard-cnn-ticker" in page
    assert "dashboardCardStateFromBlock" in page
    assert "Mapa com dados locais de apoio" not in page
    assert "fallbackSnapshot" not in page


def test_habilitacoes_runtime_no_longer_creates_business_placeholder_records():
    repository = _read(BACKEND_SRC / "repositories" / "dashboard_cache.py")
    relatorios_contract = _read(BACKEND_SRC / "contracts" / "relatorios.py")

    assert "Sem habilita" not in repository
    assert '"is_placeholder": True' not in repository
    assert "has_habilitacoes" in repository
    assert '"has_habilitacoes"' in relatorios_contract


def test_finance_stub_contracts_are_dead_and_not_runtime_routes():
    finance_init = _read(BACKEND_SRC / "api" / "http" / "financeiro" / "__init__.py")

    assert FINANCE_STUB_API_PATHS == ()
    assert FINANCE_STUB_HTTP_CONTRACTS == ()
    assert "stub routes" not in finance_init.lower()


def test_runtime_mock_eradication_is_documented_and_indexed():
    migration = _read(ROOT / "docs" / "migration" / "91.runtime-mock-data-eradication.md")
    migration_readme = _read(ROOT / "docs" / "migration" / "README.md")
    project_readme = _read(ROOT / "README.md")

    for expected in (
        "DASHBOARD_UPPER_SECTION_MOCK",
        "DASHBOARD_LOWER_SECTION_MOCK",
        "vazio honesto",
        "Sem habilitacoes cadastradas",
        "FINANCE_STUB_HTTP_CONTRACTS",
    ):
        assert expected in migration

    assert "91.runtime-mock-data-eradication.md" in migration_readme
    assert "91.runtime-mock-data-eradication.md" in project_readme
