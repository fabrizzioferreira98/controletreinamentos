from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_dashboard_top_consumes_internal_aisweb_endpoint_only():
    source = _read(FRONTEND_SRC / "features" / "dashboard-operacional" / "page.js")

    for expected in (
        'DASHBOARD_WEATHER_ROTATION_BASES = ["SBGO", "SBSP", "SBPJ", "SBSV", "SBEG", "SBBE", "SBSN"]',
        "dashboardWeatherEndpoint",
        "api(dashboardWeatherEndpoint(DASHBOARD_WEATHER_ROTATION_BASES[0]))",
        'const DASHBOARD_WEATHER_BY_BASE_ENDPOINT = "/api/v1/dashboard/weather-by-base"',
        "api(DASHBOARD_WEATHER_BY_BASE_ENDPOINT",
        "adaptDashboardWeatherByBase",
        "dashboardWeatherToBaseWeatherRow",
        "fetchDashboardWeatherForBase",
        "startDashboardWeatherRotation",
        "adaptDashboardWeather",
        "dashboardWeatherFallback",
        "dashboard-operational-weather-strip",
        "Meteorologia indispon",
        "rawMetar",
        "rawTaf",
    ):
        assert expected in source

    for forbidden in (
        "aisweb.decea.gov.br",
        "AISWEB_API_KEY",
        "AISWEB_API_PASS",
        "apiKey=",
        "apiPass=",
        "localStorage",
    ):
        assert forbidden not in source


def test_dashboard_weather_header_has_css_states():
    css = _read(FRONTEND_SRC / "app.css")

    for expected in (
        "dashboard-operational-page-shell",
        "dashboard-operational-tv-shell",
        ".app-shell:has(.dashboard-operational-tv-shell)",
        ".dashboard-weather-rail",
        ".dashboard-weather-summary",
        ".dashboard-system-badge--available",
        ".dashboard-system-badge--stale",
        ".dashboard-system-badge--unavailable",
        ".dashboard-system-badge--error",
        "is-weather-transitioning",
        "dashboardWeatherContentIn",
        "dashboardWeatherPulse",
        "prefers-reduced-motion",
    ):
        assert expected in css


def test_operational_dashboard_keeps_tv_surface_top_only():
    source = _read(FRONTEND_SRC / "features" / "dashboard-operacional" / "page.js")

    for expected in (
        "Dashboard Operacional",
        "dashboardOperationalShellClass",
        'api("/api/v1/dashboard/summary")',
        "api(dashboardWeatherEndpoint(DASHBOARD_WEATHER_ROTATION_BASES[0]))",
        "api(DASHBOARD_WEATHER_BY_BASE_ENDPOINT",
        "api(DASHBOARD_RELEVANT_NOTAMS_ENDPOINT",
        "api(DASHBOARD_OPERATIONAL_ALERTS_ENDPOINT",
        "data-dashboard-alert-surface=\"dashboard-operational-alert-grid\"",
        "data-dashboard-cnn-ticker",
    ):
        assert expected in source

    for forbidden in (
        'api("/api/v1/dashboard/calendar")',
        'api("/api/v1/dashboard/critical-trainings")',
        "dashboard-critical-panel",
        "dashboard-calendar-panel",
        "dashboard-agenda-panel",
        "dashboard-mid-surface-grid",
        "dashboard-monitor-card",
    ):
        assert forbidden not in source


def test_operational_dashboard_header_has_realtime_clock_and_fullscreen_control():
    source = _read(FRONTEND_SRC / "features" / "dashboard-operacional" / "page.js")
    css = _read(FRONTEND_SRC / "app.css")

    for expected in (
        "DASHBOARD_REALTIME_CLOCK_INTERVAL_MS = 1000",
        'second: "2-digit"',
        "data-dashboard-date-label",
        "data-dashboard-time-label",
        "startDashboardRealtimeClock",
        "stopDashboardRealtimeClock",
        "updateDashboardRealtimeClock",
        "data-dashboard-fullscreen-action",
        "wireDashboardFullscreenControl",
        "requestFullscreen",
        "exitFullscreen",
        "fullscreenchange",
    ):
        assert expected in source

    for expected in (
        ".dashboard-operational-page-shell:fullscreen",
        ".dashboard-operational-page-shell:-webkit-full-screen",
        ".dashboard-operational-page-shell .dashboard-fullscreen-button",
        ".dashboard-operational-page-shell .dashboard-fullscreen-button:focus-visible",
    ):
        assert expected in css
