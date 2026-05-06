from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_dashboard_priority_surface_adopts_shared_ui_without_route_or_api_drift():
    dashboard = _read(FRONTEND_SRC / "features" / "dashboard" / "page.js")

    for expected in (
        "dashboard-page-shell priority-page-surface ui-page-shell ui-stack",
        "dashboard-top-cluster",
        "page-header priority-page-header dashboard-page-header ui-page-header ui-surface",
        "dashboard-header-main",
        "dashboard-priority-strip ui-surface",
        "dashboard-priority-step",
        "dashboard-action-rail",
        "dashboard-status-overview",
        "dashboard-status-distribution",
        "dashboard-status-summary",
        "dashboard-status-value",
        "dashboard-mid-surface-grid",
        "dashboard-mid-surface-panel",
        "dashboard-mid-surface-head",
        "panel dashboard-panel dashboard-status-panel dashboard-mid-surface-panel ui-surface",
        "panel dashboard-calendar-panel ui-surface",
        "dashboard-agenda-item ui-surface",
        "summary-card summary-link-card dashboard-base-card",
        "dashboard-base-card-label",
        "dashboard-base-card-value",
        "dashboard-base-overview",
        "dashboard-base-summary",
    ):
        assert expected in dashboard

    for preserved in (
        'api("/api/v1/dashboard/summary")',
        'api("/api/v1/dashboard/calendar")',
        'api("/api/v1/dashboard/critical-trainings")',
        "wireDashboardCalendar(calendarData)",
        'href: "#/tripulantes"',
        'href="#/treinamentos"',
        "BACKEND_LINKS.equipamentos",
    ):
        assert preserved in dashboard


def test_dashboard_redesign_is_scoped_to_dashboard_surface_and_preserves_contracts():
    dashboard = _read(FRONTEND_SRC / "features" / "dashboard" / "page.js")
    app_css = _read(FRONTEND_SRC / "app.css")
    redesign_block = app_css.split("Dashboard redesign: isolated executive-operational surface", 1)[1].split(
        "/* Entity detail/form phase",
        1,
    )[0]

    for expected in (
        "renderDashboardStatCards(dashboardAlerts)",
        "renderDashboardHeader(capabilities)",
        "renderDashboardPriorityStrip()",
        "dashboard-critical-toolbar",
        "dashboard-status-bars",
        "renderDashboardBaseCards(dashboardTotals)",
        "dashboard-agenda-panel",
        "wireDashboardCalendar(calendarData)",
    ):
        assert expected in dashboard

    for preserved in (
        'api("/api/v1/dashboard/summary")',
        'api("/api/v1/dashboard/calendar")',
        'api("/api/v1/dashboard/critical-trainings")',
        'buildHashHref("#/treinamentos", { status: "vencido" })',
        'buildHashHref("#/treinamentos", { periodo: "7" })',
        'buildHashHref("#/treinamentos", { periodo: "30" })',
        'href: "#/treinamentos/raiz"',
        "BACKEND_LINKS.equipamentos",
    ):
        assert preserved in dashboard

    for expected in (
        ".dashboard-page-shell",
        ".dashboard-top-cluster",
        ".dashboard-header-main",
        ".dashboard-priority-strip.ui-surface",
        ".dashboard-priority-step",
        ".dashboard-header-actions",
        ".dashboard-action-rail",
        ".dashboard-action-list",
        ".dashboard-status-overview",
        ".dashboard-status-distribution",
        ".dashboard-status-summary",
        ".dashboard-status-value",
        ".dashboard-status-grid",
        ".dashboard-mid-surface-grid",
        ".dashboard-page-shell .dashboard-mid-surface-panel.ui-surface",
        ".dashboard-mid-surface-panel",
        ".dashboard-mid-surface-head",
        ".dashboard-mid-surface-loading",
        ".dashboard-base-panel-head",
        ".dashboard-base-overview",
        ".dashboard-base-summary",
        ".dashboard-base-card",
        ".dashboard-base-card-value",
        "@media (max-width: 1120px)",
    ):
        assert expected in app_css

    for expected in (
        ".dashboard-stat-grid",
        ".dashboard-kpi-card",
        ".dashboard-critical-panel.ui-surface",
        ".dashboard-critical-table-wrap.ui-table-wrap",
        ".dashboard-calendar-layout",
        ".dashboard-agenda-panel",
    ):
        assert expected in redesign_block

    for removed in (
        "dashboard-page-kicker",
        "dashboard-action-groups",
        'class="state-note ui-feedback"',
        "dashboard-note-marker",
    ):
        assert removed not in dashboard

    for forbidden in (
        ".sidebar",
        ".nav",
        ".topbar",
        "routeModuleLoaders",
        "staticRouteDefinitions",
    ):
        assert forbidden not in redesign_block


def test_tripulantes_priority_surface_adopts_shared_ui_without_functional_drift():
    tripulantes = _read(FRONTEND_SRC / "features" / "tripulantes" / "list-page.js")

    for expected in (
        "tripulantes-page-shell priority-page-surface ui-page-shell ui-stack",
        "priority-page-header ui-page-header ui-surface",
        "tripulantes-list-panel ui-surface ui-stack",
        'class="filters-bar ui-form-toolbar ui-stack-sm"',
        'class="table-wrap tripulantes-table-wrap ui-table-wrap ui-table-density-compact"',
        'class="pagination-bar ui-cluster"',
        'class="actions ui-table-actions"',
    ):
        assert expected in tripulantes

    for preserved in (
        'api(`/api/v1/tripulantes?${new URLSearchParams(filters).toString()}`)',
        'api("/api/v1/tripulantes/options")',
        'id="tripulantes-filters-form"',
        'id="tripulantesDenseFiltersToggle"',
        "tripulante-delete",
        "renderTripulantesListPage(viewMode)",
    ):
        assert preserved in tripulantes


def test_priority_page_visual_css_uses_tokens_and_stays_page_scoped():
    app_css = _read(FRONTEND_SRC / "app.css")

    for expected in (
        "G03: priority dashboard/tripulantes surface adopts shared/ui",
        ".priority-page-surface",
        ".dashboard-page-shell > .priority-page-header",
        ".tripulantes-page-shell > .priority-page-header",
        ".dashboard-page-shell .dashboard-panel.ui-surface",
        ".tripulantes-page-shell .tripulantes-list-panel.ui-surface",
        "var(--space-panel-gap)",
        "var(--radius-surface)",
        "var(--shadow-surface)",
        "var(--color-state-default-surface)",
        "var(--transition-state)",
    ):
        assert expected in app_css

    assert "pages-treinamentos-relatorios" not in app_css
