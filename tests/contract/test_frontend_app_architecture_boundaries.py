from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
APP_DIR = FRONTEND_SRC / "app"


APP_MODULES = {
    "bootstrap.js",
    "router.js",
    "route-registry.js",
    "guards.js",
    "errors.js",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_app_entrypoint_is_thin_and_delegates_to_bootstrap():
    app_source = _read(FRONTEND_SRC / "app.js")

    assert 'import { startApp } from "./app/bootstrap.js";' in app_source
    assert "void startApp();" in app_source
    assert "routeModuleLoaders" not in app_source
    assert "staticRouteDefinitions" not in app_source
    assert "renderLoginPage" not in app_source
    assert len([line for line in app_source.splitlines() if line.strip()]) <= 3


def test_app_core_modules_exist_with_explicit_responsibilities():
    assert {path.name for path in APP_DIR.glob("*.js")} == APP_MODULES

    bootstrap_source = _read(APP_DIR / "bootstrap.js")
    router_source = _read(APP_DIR / "router.js")
    registry_source = _read(APP_DIR / "route-registry.js")
    guards_source = _read(APP_DIR / "guards.js")
    errors_source = _read(APP_DIR / "errors.js")

    assert "export async function startApp()" in bootstrap_source
    assert "refreshSession" in bootstrap_source
    assert "resolveRoute(routeKey)" in bootstrap_source
    assert "renderLoginPage(startApp)" in bootstrap_source

    assert "const routeModuleCache = new Map();" in router_source
    assert "export async function withFrontendPhase" in router_source
    assert "export function resolveRoute(routeKey)" in router_source
    assert "route_import" in router_source

    assert "export const routeModuleLoaders" in registry_source
    assert "export const staticRouteDefinitions" in registry_source
    assert "export const dynamicRouteDefinitions" in registry_source

    assert "export function routeAllowed" in guards_source
    assert "capabilitySet()" in guards_source

    assert "export function registerGlobalErrorHandlers" in errors_source
    assert "export function renderRouteFailure" in errors_source
    assert "export function renderSessionValidationUnavailable" in errors_source


def test_router_recovers_once_from_stale_lazy_route_imports():
    router_source = _read(APP_DIR / "router.js")

    assert "STALE_ROUTE_IMPORT_RELOAD_KEY" in router_source
    assert "isLikelyStaleRouteImportError" in router_source
    assert "requestStaleRouteImportReload(moduleName, error)" in router_source
    assert "window.location.reload()" in router_source
    assert "new Promise(() => {})" in router_source
    assert "clearStaleRouteImportReload(moduleName)" in router_source
    assert "router.import.stale_reload.request" in router_source
    assert "Failed to fetch dynamically imported module" in router_source
    assert "ChunkLoadError" in router_source


def test_route_registry_preserves_current_routes_loaders_exports_and_permissions():
    registry_source = _read(APP_DIR / "route-registry.js")

    expected_static_routes = {
        "#/dashboard",
        "#/dashboard-operacional",
        "#/dashboard-operacional-tv",
        "#/tripulantes",
        "#/relatorios/individual",
        "#/tripulantes/new",
        "#/treinamentos",
        "#/treinamentos/new",
        "#/treinamentos/raiz",
        "#/relatorios/habilitacoes",
        "#/financeiro/missoes",
        "#/financeiro/bonificacoes",
        "#/financeiro/fechamento-parametros",
    }
    registered_static_routes = set(re.findall(r'"(#[^"]+)":\s*{', registry_source))

    assert registered_static_routes == expected_static_routes
    assert 'financeiro: () => import("../pages-financeiro.js"),' in registry_source
    assert 'tripulantes: () => import("../pages-dashboard-tripulantes.js"),' in registry_source
    assert 'treinamentos: () => import("../pages-treinamentos-relatorios.js"),' in registry_source
    assert 'pattern: /^#\\/tripulantes\\/\\d+$/' in registry_source
    assert 'pattern: /^#\\/treinamentos\\/\\d+$/' in registry_source
    for permission in (
        "dashboard:view",
        "tripulantes:view",
        "relatorio_individual:view",
        "tripulantes:create",
        "tripulantes:edit",
        "treinamentos:view",
        "treinamentos:create",
        "treinamentos:edit",
        "tipos_treinamento:view",
        "relatorio_habilitacoes:view",
        "finance:missions:read",
        "finance:bonuses:read",
        "finance:parameters:read",
        "finance:periods:read",
    ):
        assert permission in registry_source


def test_app_router_boundaries_are_documented():
    architecture = _read(ROOT / "docs" / "architecture" / "FRONTEND_ARCHITECTURE.md")

    for expected in (
        "`frontend/src/app/bootstrap.js`",
        "`frontend/src/app/router.js`",
        "`frontend/src/app/route-registry.js`",
        "`frontend/src/app/guards.js`",
        "`frontend/src/app/errors.js`",
        "entrypoint fino",
    ):
        assert expected in architecture
