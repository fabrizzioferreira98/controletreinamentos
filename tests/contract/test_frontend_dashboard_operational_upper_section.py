from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_operational_dashboard_upper_section_uses_centralized_contract_and_empty_state():
    data_source = _read(FRONTEND_SRC / "features" / "dashboard-operacional" / "upper-section-data.js")

    for expected in (
        "LicenseExpirationSummary",
        "BaseOperationalStatus",
        "BaseOperationsSnapshot",
        "CriticalQualification",
        "DashboardUpperSectionData",
        "DASHBOARD_UPPER_SECTION_EMPTY",
        "DASHBOARD_EMPTY_BASE_OPERATIONS",
        "@property {string} icao",
        "licenseSummary",
        "baseOperations",
        "statusOptions",
        "BasePilotPreview",
        "criticalQualifications",
        "basesActive: 0",
        "crew: 0",
        "alerts: 0",
        "restrictions: 0",
        "latitude",
        "longitude",
        "total_pilotos",
        "pilotos",
    ):
        assert expected in data_source

    for forbidden in (
        "DASHBOARD_UPPER_SECTION_MOCK",
        "Bras\\u00edlia",
        "Recife",
        "Confins",
        'uf: "DF"',
        'uf: "PE"',
        'uf: "MG"',
    ):
        assert forbidden not in data_source


def test_operational_dashboard_renders_upper_section_below_approved_top():
    source = _read(FRONTEND_SRC / "features" / "dashboard-operacional" / "page.js")

    for expected in (
        'import { DASHBOARD_EMPTY_BASE_OPERATIONS, DASHBOARD_UPPER_SECTION_EMPTY } from "./upper-section-data.js"',
        "renderDashboardUpperSection",
        "renderLicenseExpirationCard",
        "renderBaseManagementCard",
        "renderCriticalQualificationsCard",
        "renderDashboardSeverityBadge",
        "renderDashboardMiniProgress",
        "renderDashboardLicenseDonut",
        "DASHBOARD_BASES_MAP_ENDPOINT",
        "DASHBOARD_LEAFLET_SCRIPT_SRC",
        "DASHBOARD_BASES_MAP_ROTATION_INTERVAL_MS",
        "wireDashboardBaseMirrorMap",
        "loadDashboardLeaflet",
        "renderDashboardBaseMarkerHtml",
        "buildDashboardBaseMarkerEntities",
        "dashboardBaseRotationTargets",
        "dashboardBaseMapViewportProfile",
        "fitDashboardBaseMapToBounds",
        "wireDashboardBaseMapResize",
        "ResizeObserver",
        "invalidateSize({ animate: false })",
        "fitBounds(bounds",
        "zoomControl: false",
        "scrollWheelZoom: false",
        'window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"',
        "data-dashboard-base-map",
        "dashboard-base-pin-marker",
        "base-marker-card base-marker-card-peek",
        "data-dashboard-zone=\"upper-operational-diagnostics\"",
        "data-dashboard-upper-card=\"license-expiration\"",
        "data-dashboard-upper-card=\"base-management\"",
        "data-dashboard-upper-card=\"critical-qualifications\"",
        "Gest\\u00e3o de Base",
        "Mapa operacional das bases e tripulantes",
        "Nenhum vencimento cr",
        "N\\u00e3o foi poss\\u00edvel carregar os indicadores.",
        'api("/api/v1/dashboard/summary")',
        'api("/api/v1/dashboard/critical-trainings?limit=20")',
        'const DASHBOARD_BASES_MAP_ENDPOINT = "/api/v1/dashboard/base-operations"',
        "${renderDashboardStatCards(dashboardAlertsTv)}\n          </div>\n          ${renderDashboardUpperSection",
    ):
        assert expected in source

    for forbidden in (
        "DASHBOARD_UPPER_SECTION_MOCK",
        'api("/api/v1/dashboard/calendar")',
        "dashboard-critical-panel",
        "dashboard-calendar-panel",
        "dashboard-mid-surface-grid",
    ):
        assert forbidden not in source


def test_operational_dashboard_upper_section_css_is_scoped_and_responsive():
    css = _read(FRONTEND_SRC / "app.css")

    for expected in (
        ".app-shell:has(.dashboard-operational-page-shell) .content.ui-content-region",
        "box-sizing: border-box",
        ".dashboard-operational-page-shell .dashboard-upper-section",
        ".dashboard-operational-page-shell .dashboard-upper-grid",
        ".dashboard-operational-page-shell .dashboard-upper-card.ui-surface",
        ".dashboard-operational-page-shell .dashboard-upper-card--licenses",
        ".dashboard-operational-page-shell .dashboard-upper-card--base-management",
        ".dashboard-operational-page-shell .dashboard-license-donut",
        ".dashboard-operational-page-shell .dashboard-base-map-stage",
        ".dashboard-operational-page-shell .dashboard-base-map.bases-map",
        ".dashboard-operational-page-shell .dashboard-base-map-status",
        ".dashboard-operational-page-shell .dashboard-base-map .leaflet-control-zoom",
        ".dashboard-operational-page-shell .dashboard-base-pin-marker",
        ".dashboard-operational-page-shell .dashboard-base-pin-marker-alert",
        ".dashboard-operational-page-shell .dashboard-base-marker-active",
        ".dashboard-operational-page-shell .dashboard-base-summary",
        ".dashboard-operational-page-shell .dashboard-qualification-item",
        ".dashboard-operational-page-shell .dashboard-mini-progress",
        ".dashboard-operational-page-shell .dashboard-severity-badge--critical",
        ".dashboard-operational-page-shell .dashboard-severity-badge--warning",
        ".dashboard-operational-page-shell .dashboard-severity-badge--planning",
        ".dashboard-operational-page-shell .dashboard-severity-badge--normal",
        "@media (max-width: 1180px)",
        "@media (max-width: 780px)",
        "@media (max-width: 520px)",
        "grid-template-columns: repeat(2, minmax(0, 1fr))",
        "grid-template-columns: 1fr",
        "dashboardUpperSkeleton",
        "dashboardBaseMarkerPulse",
        "contain: layout paint",
        "prefers-reduced-motion",
    ):
        assert expected in css
