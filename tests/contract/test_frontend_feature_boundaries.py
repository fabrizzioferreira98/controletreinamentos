from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
FEATURES_DIR = FRONTEND_SRC / "features"


EXPECTED_FEATURE_FILES = {
    "dashboard": {"page.js"},
    "dashboard-operacional": {"lower-section-data.js", "page.js", "upper-section-data.js"},
    "financeiro": {"bonificacoes-page.js", "fechamento-parametros-page.js", "missoes-page.js"},
    "relatorios": {
        "habilitacoes-page.js",
        "report-ui.js",
    },
    "training-root": {"page.js"},
    "treinamentos": {
        "attachments.js",
        "form-page.js",
        "list-page.js",
        "program-helpers.js",
    },
    "tripulantes": {
        "avatar.js",
        "data-adapters.js",
        "form-page.js",
        "list-page.js",
    },
    "relatorio-individual": {"page.js"},
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_dashboard_tripulantes_page_module_is_thin_compat_entrypoint():
    source = _read(FRONTEND_SRC / "pages-dashboard-tripulantes.js")
    meaningful_lines = [line for line in source.splitlines() if line.strip()]

    assert len(source) < 5000
    assert len(meaningful_lines) <= 24
    assert 'from "./features/dashboard/page.js";' in source
    assert 'from "./features/dashboard-operacional/page.js";' in source
    assert 'from "./features/tripulantes/list-page.js";' in source
    assert 'from "./features/tripulantes/form-page.js";' in source
    assert 'from "./features/relatorio-individual/page.js";' in source

    for exported in (
        "export async function renderDashboardPage()",
        "export async function renderOperationalDashboardPage()",
        "export async function renderOperationalDashboardTvPage()",
        "export async function renderTripulantesListPage",
        "export async function renderRelatorioIndividualPage()",
        "export async function renderTripulanteFormPage",
    ):
        assert exported in source
    for forbidden in (
        "api(",
        "renderShell(",
        "innerHTML",
        "NAV_GROUPS",
        "Promise.allSettled",
        "tripulante-form-feedback",
    ):
        assert forbidden not in source


def test_dashboard_tripulantes_feature_files_exist_with_explicit_owners():
    assert {path.name for path in FEATURES_DIR.iterdir() if path.is_dir()} >= set(EXPECTED_FEATURE_FILES)
    for directory, expected_files in EXPECTED_FEATURE_FILES.items():
        assert {path.name for path in (FEATURES_DIR / directory).glob("*.js")} == expected_files

    dashboard_source = _read(FEATURES_DIR / "dashboard" / "page.js")
    operational_dashboard_source = _read(FEATURES_DIR / "dashboard-operacional" / "page.js")
    tripulantes_list_source = _read(FEATURES_DIR / "tripulantes" / "list-page.js")
    tripulantes_form_source = _read(FEATURES_DIR / "tripulantes" / "form-page.js")
    tripulantes_avatar_source = _read(FEATURES_DIR / "tripulantes" / "avatar.js")
    tripulantes_adapters_source = _read(FEATURES_DIR / "tripulantes" / "data-adapters.js")
    relatorio_source = _read(FEATURES_DIR / "relatorio-individual" / "page.js")

    assert "export async function renderDashboardPage()" in dashboard_source
    assert "adaptDashboardSummary" in dashboard_source
    assert "wireDashboardCalendar" in dashboard_source
    assert "DASHBOARD_WEATHER_ROTATION_BASES" not in dashboard_source

    assert "export async function renderDashboardPage(options = {})" in operational_dashboard_source
    assert "DASHBOARD_WEATHER_ROTATION_BASES" in operational_dashboard_source
    assert "dashboardWeatherEndpoint" in operational_dashboard_source
    assert "Dashboard Operacional" in operational_dashboard_source

    assert "export async function renderTripulantesListPage" in tripulantes_list_source
    assert "tripulantes-action-feedback" in tripulantes_list_source
    assert "tripulante-delete" in tripulantes_list_source

    assert "export async function renderTripulanteFormPage" in tripulantes_form_source
    assert "tripulante-form-feedback" in tripulantes_form_source
    assert "tripulante-file-form" in tripulantes_form_source

    assert "export function renderTripulanteAvatar" in tripulantes_avatar_source
    assert "export function wireTripulantePhotoFallbacks" in tripulantes_avatar_source

    assert "export function adaptTripulantesListPayload" in tripulantes_adapters_source
    assert "export function adaptTripulantesOptionsPayload" in tripulantes_adapters_source

    assert "export async function renderRelatorioIndividualPage" in relatorio_source
    assert 'renderTripulantesListPage("report")' in relatorio_source


def test_features_do_not_import_page_modules_or_lateral_training_feature():
    for path in FEATURES_DIR.rglob("*.js"):
        source = _read(path)
        assert "pages-dashboard-tripulantes.js" not in source
        assert "pages-treinamentos-relatorios.js" not in source
        assert "pages-training-workspace.js" not in source


def test_feature_slicing_is_documented():
    architecture = _read(ROOT / "docs" / "architecture" / "FRONTEND_ARCHITECTURE.md")

    for expected in (
        "`frontend/src/features/dashboard/page.js`",
        "`frontend/src/features/dashboard-operacional/page.js`",
        "`frontend/src/features/tripulantes/list-page.js`",
        "`frontend/src/features/tripulantes/form-page.js`",
        "`frontend/src/features/tripulantes/avatar.js`",
        "`frontend/src/features/tripulantes/data-adapters.js`",
        "`frontend/src/features/relatorio-individual/page.js`",
        "wrapper compativel temporario",
    ):
        assert expected in architecture


def test_training_reports_page_module_is_thin_compat_entrypoint():
    source = _read(FRONTEND_SRC / "pages-treinamentos-relatorios.js")
    meaningful_lines = [line for line in source.splitlines() if line.strip()]

    assert len(source) < 6000
    assert len(meaningful_lines) <= 28
    assert 'from "./features/treinamentos/list-page.js";' in source
    assert 'from "./features/treinamentos/form-page.js";' in source
    assert 'from "./features/training-root/page.js";' in source
    assert 'from "./features/relatorios/habilitacoes-page.js";' in source

    for exported in (
        "export async function renderTreinamentosListPage()",
        "export async function renderTrainingRootPage()",
        "export async function renderTreinamentoFormPage",
        "export async function renderRelatorioHabilitacoesPage()",
    ):
        assert exported in source
    for forbidden in (
        "api(",
        "renderShell(",
        "innerHTML",
        "Promise.all",
        "training-program-feedback",
        "training-root-type-form",
    ):
        assert forbidden not in source


def test_training_reports_feature_files_exist_with_explicit_owners():
    treinamentos_list_source = _read(FEATURES_DIR / "treinamentos" / "list-page.js")
    treinamentos_form_source = _read(FEATURES_DIR / "treinamentos" / "form-page.js")
    treinamentos_helpers_source = _read(FEATURES_DIR / "treinamentos" / "program-helpers.js")
    training_root_source = _read(FEATURES_DIR / "training-root" / "page.js")
    habilitacoes_source = _read(FEATURES_DIR / "relatorios" / "habilitacoes-page.js")
    report_ui_source = _read(FEATURES_DIR / "relatorios" / "report-ui.js")

    assert "export async function renderTreinamentosListPage" in treinamentos_list_source
    assert "training-program-feedback" in treinamentos_list_source
    assert "trainingProgramSelectionFeedback" in treinamentos_list_source

    assert "export async function renderTreinamentoFormPage" in treinamentos_form_source
    assert "training-record-feedback" in treinamentos_form_source
    assert "legacyRenderTreinamentoFormPage" not in treinamentos_form_source
    assert "/api/v1/treinamentos-tripulantes" in treinamentos_form_source
    assert "/api/v1/treinamentos/" not in treinamentos_form_source

    assert "export function readTrainingProgramFilters" in treinamentos_helpers_source
    assert "export function adaptTrainingProgramOptions" in treinamentos_helpers_source
    assert "export async function loadRequiredItem" in treinamentos_helpers_source

    assert "export async function renderTrainingRootPage" in training_root_source
    assert "editingTypePromise" in training_root_source
    assert 'wireExplicitSubmit("training-root-type-form"' in training_root_source

    assert "export async function renderRelatorioHabilitacoesPage" in habilitacoes_source
    assert "Consolidado de habilitações" in habilitacoes_source

    assert "export function renderReportContextStrip" in report_ui_source
    assert "export function wireResponsiveFilters" in report_ui_source


def test_training_reports_feature_slicing_is_documented():
    architecture = _read(ROOT / "docs" / "architecture" / "FRONTEND_ARCHITECTURE.md")

    for expected in (
        "`frontend/src/features/treinamentos/list-page.js`",
        "`frontend/src/features/treinamentos/form-page.js`",
        "`frontend/src/features/treinamentos/program-helpers.js`",
        "`frontend/src/features/training-root/page.js`",
        "`frontend/src/features/relatorios/habilitacoes-page.js`",
        "`frontend/src/features/relatorios/report-ui.js`",
    ):
        assert expected in architecture


def test_financeiro_missoes_feature_file_exists_with_explicit_owner():
    source = _read(FEATURES_DIR / "financeiro" / "missoes-page.js")

    assert "export async function renderFinanceiroMissoesPage()" in source
    assert "Miss" in source and "Operacionais" in source
    assert "finance:missions:create" in source
    assert "finance:missions:update" in source
    assert "finance:missions:cancel" in source


def test_financeiro_feature_slicing_is_documented():
    architecture = _read(ROOT / "docs" / "architecture" / "FRONTEND_ARCHITECTURE.md")

    for expected in (
        "`frontend/src/features/financeiro/missoes-page.js`",
        "`frontend/src/services/financeiro-missoes-api.js`",
        "Missoes Operacionais",
    ):
        assert expected in architecture
