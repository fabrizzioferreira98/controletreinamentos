from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
MIGRATION_DIR = ROOT / "docs" / "migration"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_dashboard_markup_declares_responsive_information_priority_without_api_drift():
    source = _read(FRONTEND_SRC / "features" / "dashboard" / "page.js")

    for expected in (
        'dashboard-responsive-surface" data-dashboard-layout="responsive-operational"',
        'dashboard-top-cluster dashboard-fold-priority" data-dashboard-zone="above-fold"',
        'dashboard-priority-strip ui-surface dashboard-above-fold" data-dashboard-priority="p0"',
        'dashboard-stat-grid ui-card-grid ui-card-equal-height dashboard-kpi-priority-row" data-dashboard-zone="kpi-priority"',
        'data-dashboard-priority="${card.tone === "critical" ? "p0" : card.tone === "warning" ? "p1" : "p2"}"',
        'data-dashboard-priority="p0"',
        'data-dashboard-priority="p1"',
        'data-dashboard-priority="p2"',
        'dashboard-critical-panel ui-surface dashboard-critical-zone" data-dashboard-priority="p0" data-dashboard-surface="critical-queue"',
        'data-dashboard-surface="critical-list"',
        'dashboard-secondary-grid dashboard-mid-surface-grid dashboard-mid-zone" data-dashboard-priority="p1" data-dashboard-surface="mid-summary"',
        'dashboard-calendar-panel ui-surface dashboard-calendar-zone" data-dashboard-priority="p1" data-dashboard-surface="calendar"',
        'dashboard-calendar-layout dashboard-calendar-responsive-layout" data-dashboard-surface="calendar-detail"',
        'dashboard-agenda-panel ui-surface dashboard-agenda-zone" data-dashboard-priority="p2" data-dashboard-surface="agenda"',
        "dashboard-agenda-list dashboard-agenda-responsive-list",
    ):
        assert expected in source

    for preserved in (
        'api("/api/v1/dashboard/summary")',
        'api("/api/v1/dashboard/calendar")',
        'api("/api/v1/dashboard/critical-trainings")',
        "renderDashboardStatCards(dashboardAlerts)",
        "renderDashboardCriticalRows(criticalItems, Boolean(criticalBlock.error))",
        "wireDashboardCalendar(calendarData)",
        'buildHashHref("#/treinamentos", { status: "vencido" })',
        'buildHashHref("#/treinamentos", { periodo: "7" })',
        'buildHashHref("#/treinamentos", { periodo: "30" })',
        'href: "#/treinamentos/raiz"',
        "BACKEND_LINKS.equipamentos",
    ):
        assert preserved in source


def test_dashboard_responsive_policy_css_prioritizes_fold_critical_calendar_and_agenda():
    css = _read(FRONTEND_SRC / "app.css")
    policy_block = css.split("34.2.9: dashboard responsive policy", 1)[1].split(
        "/* Entity detail/form phase",
        1,
    )[0]

    for expected in (
        "keeps executive priority above the fold across breakpoints",
        '.dashboard-responsive-surface[data-dashboard-layout="responsive-operational"]',
        '.dashboard-fold-priority[data-dashboard-zone="above-fold"]',
        '.dashboard-above-fold[data-dashboard-priority="p0"]',
        '.dashboard-kpi-priority-row[data-dashboard-zone="kpi-priority"]',
        '.dashboard-kpi-priority-row .dashboard-kpi-card[data-dashboard-priority="p0"]',
        '.dashboard-critical-zone[data-dashboard-priority="p0"]',
        '.dashboard-mid-zone[data-dashboard-priority="p1"]',
        '.dashboard-calendar-zone[data-dashboard-priority="p1"]',
        '.dashboard-agenda-zone[data-dashboard-priority="p2"]',
        '.dashboard-calendar-responsive-layout[data-dashboard-surface="calendar-detail"]',
        '.dashboard-calendar-zone[data-dashboard-surface="calendar"] .dashboard-calendar-shell',
        ".dashboard-agenda-responsive-list",
        '.dashboard-critical-table-wrap[data-dashboard-surface="critical-list"]',
        "@media (max-width: 1180px)",
        "@media (max-width: 900px)",
        "@media (max-width: 640px)",
        "overscroll-behavior-x: contain;",
        "scroll-margin-top:",
    ):
        assert expected in policy_block

    for forbidden in (
        ".sidebar",
        ".topbar",
        "NAV_GROUPS",
        "api(",
        "renderShell",
    ):
        assert forbidden not in policy_block


def test_dashboard_policy_preserves_existing_visual_contracts_and_shared_boundaries():
    source = _read(FRONTEND_SRC / "features" / "dashboard" / "page.js")
    primitives = _read(FRONTEND_SRC / "shared" / "ui" / "primitives.css")

    for expected in (
        "dashboard-page-shell priority-page-surface ui-page-shell ui-stack",
        "page-header priority-page-header dashboard-page-header ui-page-header ui-surface",
        "dashboard-priority-strip ui-surface",
        "dashboard-stat-grid ui-card-grid ui-card-equal-height",
        "panel dashboard-calendar-panel ui-surface",
        "dashboard-agenda-item ui-surface ui-card ui-card-compact",
        "summary-card summary-link-card dashboard-base-card ui-card ui-card-compact",
    ):
        assert expected in source

    for forbidden in (
        "dashboard",
        "tripulante",
        "treinamento",
        "relatorio",
    ):
        assert forbidden not in primitives


def test_dashboard_policy_is_registered_in_migration_readme():
    migration = _read(MIGRATION_DIR / "34.2.9-politica-dashboards-responsivos.md")
    index = _read(MIGRATION_DIR / "README.md")

    for expected in (
        "Politica oficial de dashboards responsivos",
        "`p0`: faixa superior, prioridade operacional e fila critica",
        "`p1`: faixas intermediarias, status/base e calendario",
        "`p2`: agenda e leitura complementar",
        "`dashboard-fold-priority`: zona acima da dobra",
        "`dashboard-kpi-priority-row`: linha de KPIs",
        "`dashboard-critical-zone`: fila critica",
        "`dashboard-calendar-zone`: calendario/agenda detalhada",
        "`dashboard-agenda-zone`: proximos vencimentos",
        "backend, contratos, rotas e regras de dominio permanecem intactos",
    ):
        assert expected in migration

    assert "34.2.9-politica-dashboards-responsivos.md" in index
