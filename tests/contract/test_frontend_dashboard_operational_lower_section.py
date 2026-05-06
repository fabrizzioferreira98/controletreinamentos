from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_operational_dashboard_lower_section_uses_centralized_contract_and_empty_state():
    data_source = _read(FRONTEND_SRC / "features" / "dashboard-operacional" / "lower-section-data.js")

    for expected in (
        "BaseWeatherStatus",
        "RelevantNotam",
        "QuickAction",
        "DashboardLowerSectionData",
        "DASHBOARD_LOWER_SECTION_EMPTY",
        "DASHBOARD_OPERATIONAL_QUICK_ACTIONS",
        "weatherByBase",
        "relevantNotams",
        "quickActions",
        'id: "new-flight"',
        'icon: "plane"',
        'id: "calendar"',
    ):
        assert expected in data_source

    for forbidden in (
        "DASHBOARD_LOWER_SECTION_MOCK",
        'id: "notam-1"',
        "Pista 17R/35L fechada",
        'icao: "SBBR"',
        'icao: "SBRF"',
        'city: "Bras\\u00edlia"',
        'city: "Recife"',
    ):
        assert forbidden not in data_source


def test_operational_dashboard_renders_lower_section_after_upper_section_without_new_external_integrations():
    source = _read(FRONTEND_SRC / "features" / "dashboard-operacional" / "page.js")

    for expected in (
        'import { DASHBOARD_LOWER_SECTION_EMPTY, DASHBOARD_OPERATIONAL_QUICK_ACTIONS } from "./lower-section-data.js"',
        'const DASHBOARD_WEATHER_BY_BASE_ENDPOINT = "/api/v1/dashboard/weather-by-base"',
        'const DASHBOARD_RELEVANT_NOTAMS_ENDPOINT = "/api/v1/dashboard/notams"',
        'const DASHBOARD_OPERATIONAL_ALERTS_ENDPOINT = "/api/v1/dashboard/operational-alerts"',
        "api(DASHBOARD_WEATHER_BY_BASE_ENDPOINT",
        "api(DASHBOARD_RELEVANT_NOTAMS_ENDPOINT",
        "api(DASHBOARD_OPERATIONAL_ALERTS_ENDPOINT",
        "adaptDashboardWeatherByBase",
        "adaptDashboardRelevantNotams",
        "adaptDashboardOperationalAlerts",
        "renderDashboardLowerSection",
        "renderDashboardOperationalTicker",
        "renderBaseWeatherCard",
        "renderRelevantNotamsCard",
        "renderQuickActionsCard",
        "renderDashboardLowerCollectionStateBanner",
        "renderWeatherConditionBadge",
        "renderNotamSeverityBadge",
        "data-dashboard-zone=\"lower-operational-context\"",
        "data-dashboard-lower-card=\"weather-by-base\"",
        "data-dashboard-lower-card=\"relevant-notams\"",
        "data-dashboard-lower-card=\"quick-actions\"",
        "data-dashboard-cnn-ticker",
        'const DASHBOARD_WEATHER_ROTATION_BASES = ["SBGO", "SBSP", "SBPJ", "SBSV", "SBEG", "SBBE", "SBSN"]',
        "Meteorologia por Base",
        "NOTAMs Relevantes",
        "A\\u00e7\\u00f5es R\\u00e1pidas",
        "Alertas operacionais indispon",
        "Falha ao carregar meteorologia",
        "NOTAMs indispon",
        "Nenhuma base monitorada.",
        "Nenhum NOTAM relevante no momento.",
        "Nenhuma a\\u00e7\\u00e3o dispon",
        "${renderDashboardUpperSection({ data: upperRuntimeData, cardStates: upperCardStates })}",
        "${renderDashboardLowerSection({ data: lowerRuntimeData, cardStates: lowerCardStates })}",
        "${renderDashboardOperationalTicker(operationalAlertsBlockTv.data, tickerState)}",
    ):
        assert expected in source

    for forbidden in (
        "DASHBOARD_LOWER_SECTION_MOCK",
        "DASHBOARD_UPPER_SECTION_MOCK",
        'api("/api/aisweb/notam")',
        'api("/api/notams")',
        "area=notam",
        "fetch(\"http://aisweb",
        "leaflet-notam",
    ):
        assert forbidden not in source


def test_operational_dashboard_keeps_safe_lower_blocks_visible_when_integrations_are_unavailable():
    source = _read(FRONTEND_SRC / "features" / "dashboard-operacional" / "page.js")

    for expected in (
        "weatherByBaseMeta",
        "relevantNotamsMeta",
        "weatherByBaseMeta: source.weatherByBaseMeta",
        "relevantNotamsMeta: source.relevantNotamsMeta",
        "const hasRows = items.length > 0",
        "? `${statusBanner}${bodyMarkup()}`",
        "data.weatherByBaseMeta",
        "data.relevantNotamsMeta",
        "NOTAMs indispon\\u00edveis no momento.",
        "Integra\\u00e7\\u00e3o real de NOTAM indispon\\u00edvel no momento.",
    ):
        assert expected in source


def test_operational_dashboard_lower_section_css_is_scoped_and_responsive():
    css = _read(FRONTEND_SRC / "app.css")

    for expected in (
        ".dashboard-operational-page-shell .dashboard-lower-section",
        ".dashboard-operational-page-shell .dashboard-lower-grid",
        ".dashboard-operational-page-shell .dashboard-lower-card.ui-surface",
        ".dashboard-operational-page-shell .dashboard-lower-card-header",
        ".dashboard-operational-page-shell .dashboard-lower-card-action",
        ".dashboard-operational-page-shell .dashboard-lower-collection-state",
        ".dashboard-operational-page-shell .dashboard-lower-collection-state--error",
        ".dashboard-operational-page-shell .dashboard-base-weather-table",
        ".dashboard-operational-page-shell .dashboard-base-weather-row",
        ".dashboard-operational-page-shell .dashboard-weather-condition--normal",
        ".dashboard-operational-page-shell .dashboard-weather-condition--attention",
        ".dashboard-operational-page-shell .dashboard-weather-condition--critical",
        ".dashboard-operational-page-shell .dashboard-notam-item",
        ".dashboard-operational-page-shell .dashboard-notam-code--critical",
        ".dashboard-operational-page-shell .dashboard-notam-code--warning",
        ".dashboard-operational-page-shell .dashboard-notam-code--attention",
        ".dashboard-operational-page-shell .dashboard-notam-code--info",
        ".dashboard-operational-page-shell .dashboard-quick-action-grid",
        ".dashboard-operational-page-shell .dashboard-quick-action",
        ".dashboard-operational-page-shell .dashboard-operational-ticker",
        ".dashboard-operational-page-shell .dashboard-operational-ticker-track",
        "dashboardOperationalTickerScroll",
        "grid-template-columns: repeat(3, minmax(0, 1fr))",
        "grid-template-columns: repeat(2, minmax(0, 1fr))",
        "grid-template-columns: 1fr",
        "@media (max-width: 1180px)",
        "@media (max-width: 780px)",
        "@media (max-width: 520px)",
        "prefers-reduced-motion",
    ):
        assert expected in css


def test_operational_dashboard_fullscreen_tv_layout_has_no_scroll_compact_breakpoints():
    css = _read(FRONTEND_SRC / "app.css")

    for expected in (
        ".dashboard-operational-page-shell.dashboard-operational-tv-shell,\n  .dashboard-operational-page-shell:fullscreen",
        "grid-template-rows: auto minmax(0, 1fr) minmax(0, 0.78fr) 44px",
        "height: 100dvh",
        "overflow: hidden",
        "@media (min-width: 1024px) and (max-height: 900px)",
        "grid-template-rows: auto minmax(0, 1fr) minmax(0, 0.7fr) 40px",
        "@media (min-width: 1024px) and (max-height: 760px)",
        "grid-template-rows: auto minmax(0, 1fr) minmax(0, 0.68fr) 36px",
        ".dashboard-operational-page-shell.dashboard-operational-tv-shell .dashboard-upper-grid",
        "grid-template-columns: minmax(0, 0.95fr) minmax(0, 1.12fr) minmax(0, 1fr)",
        ".dashboard-operational-page-shell.dashboard-operational-tv-shell .dashboard-lower-grid",
        "grid-template-columns: repeat(3, minmax(0, 1fr))",
        ".dashboard-operational-page-shell.dashboard-operational-tv-shell .dashboard-base-map-stage",
        "height: 100%",
        ".dashboard-operational-page-shell.dashboard-operational-tv-shell .dashboard-base-pin-marker",
        ".dashboard-operational-page-shell.dashboard-operational-tv-shell .dashboard-operational-ticker",
        ".dashboard-operational-page-shell.dashboard-operational-tv-shell .dashboard-alert-card.ui-surface",
        "height: 62px",
    ):
        assert expected in css
