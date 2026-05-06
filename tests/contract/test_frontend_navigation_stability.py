from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
BACKEND_SRC = ROOT / "backend" / "src" / "controle_treinamentos"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_bootstrap_does_not_use_dashboard_as_generic_missing_hash_fallback() -> None:
    source = _read(FRONTEND_SRC / "app" / "bootstrap.js")

    assert 'routePath() || "#/dashboard"' not in source
    assert 'window.location.hash = "#/dashboard"' not in source
    assert "redirect.to_dashboard" not in source
    assert "routeFromCurrentPathname()" in source
    assert "authenticatedLandingRoute()" in source
    assert "rememberReturnRoute(returnRoute)" in source
    assert "rememberLastSuccessfulRoute(currentHashRoute() || routeKey)" in source


def test_auth_redirects_preserve_return_route_before_login_navigation() -> None:
    api_client = _read(FRONTEND_SRC / "services" / "api-client.js")
    login = _read(FRONTEND_SRC / "shell" / "login.js")

    assert "rememberCurrentRouteForLogin()" in api_client
    assert 'window.location.hash = "#/login"' in api_client
    assert "hashQuery().get(\"next\")" in login
    assert "consumeReturnRoute()" in login
    assert "resolveLoginDestination(hashNext, { fallbackHash: \"\" })" in login


def test_login_destination_resolver_can_decline_invalid_next_and_preserve_query() -> None:
    redirects = _read(FRONTEND_SRC / "compat" / "backend-links.js")

    assert 'fallbackHash = "#/dashboard"' in redirects
    assert 'if (!fallbackHash) return { kind: "none", value: "" };' in redirects
    assert 'return { kind: "hash", value: query ? `${hash}?${query}` : hash };' in redirects
    assert '"/tipos": CANONICAL_FRONTEND_HASHES.trainingRoot' in redirects
    assert "[BACKEND_LINKS.tipos]: CANONICAL_FRONTEND_HASHES.trainingRoot" in redirects
    assert "resolveFrontendHashForBackendPath(path)" in redirects


def test_navigation_state_canonicalizes_backend_path_before_restore_or_fallback() -> None:
    navigation_state = _read(FRONTEND_SRC / "state" / "navigation-state.js")
    bootstrap = _read(FRONTEND_SRC / "app" / "bootstrap.js")

    assert 'import { resolveFrontendHashForBackendPath } from "../compat/backend-links.js";' in navigation_state
    assert "const canonicalHash = resolveFrontendHashForBackendPath(pathname);" in navigation_state
    assert "if (canonicalHash) return canonicalHash;" in navigation_state
    assert "return route.startsWith(\"#/\") ? route : \"\";" in navigation_state
    assert "routePath() || routeFromCurrentPathname()" in bootstrap
    assert "peekLastSuccessfulRoute()" in bootstrap
    assert "DEFAULT_AUTHENTICATED_ROUTE" in bootstrap


def test_backend_frontend_login_entry_targets_login_not_dashboard() -> None:
    auth_routes = _read(BACKEND_SRC / "blueprints" / "auth" / "routes.py")

    assert 'redirect_to_frontend("#/login", query=_frontend_login_query())' in auth_routes
    assert 'return redirect_to_frontend("#/dashboard")' not in auth_routes
    assert "def _frontend_login_query()" in auth_routes
    assert "safe_next_url(request.args.get(\"next\") or request.form.get(\"next\"), \"\")" in auth_routes


def test_route_and_guard_failures_render_in_place_without_navigation_side_effect() -> None:
    errors = _read(FRONTEND_SRC / "app" / "errors.js")
    guards = _read(FRONTEND_SRC / "app" / "guards.js")

    assert "renderRouteFailure" in errors
    assert "window.location" not in errors
    assert "renderForbiddenRoute" in guards
    assert "window.location.hash =" not in guards


def test_shell_skips_stale_async_route_renders_after_hash_change() -> None:
    app_state = _read(FRONTEND_SRC / "state" / "app-state.js")
    bootstrap = _read(FRONTEND_SRC / "app" / "bootstrap.js")
    render_shell = _read(FRONTEND_SRC / "shell" / "render-shell.js")

    assert "navigationRender" in app_state
    assert "state.navigationRender = {" in bootstrap
    assert "routeKey: startupRoute" in bootstrap
    assert "const expectedRoute = state.navigationRender?.routeKey || activeRoute;" in render_shell
    assert "expectedRoute !== activeRoute" in render_shell
    assert "shell.render.skip_stale_route" in render_shell
    assert "return false;" in render_shell


def test_bootstrap_registers_single_hashchange_renderer_listener() -> None:
    source = _read(FRONTEND_SRC / "app" / "bootstrap.js")

    assert "let eventHandlersRegistered = false;" in source
    assert "if (eventHandlersRegistered) return;" in source
    assert "eventHandlersRegistered = true;" in source
    assert source.count('window.addEventListener("hashchange"') == 1
    assert "void startApp()" in source


def test_shell_replaces_single_root_and_aborts_previous_shell_listeners() -> None:
    source = _read(FRONTEND_SRC / "shell" / "render-shell.js")

    assert "let shellInteractionAbortController = null;" in source
    assert "shellInteractionAbortController?.abort();" in source
    assert 'shellInteractionAbortController = typeof AbortController === "function" ? new AbortController() : null;' in source
    assert "const listenerOptions = shellInteractionAbortController ? { signal: shellInteractionAbortController.signal } : undefined;" in source
    assert source.count('document.getElementById("app").innerHTML =') == 1


def test_trace_hashchange_listener_is_observability_only() -> None:
    source = _read(FRONTEND_SRC / "services" / "trace-service.js")

    assert 'window.addEventListener("hashchange", (event) =>' in source
    assert "startApp(" not in source
    assert "renderShell(" not in source
    assert "innerHTML =" not in source
    assert "window.location.hash =" not in source


def test_navigation_fallback_migration_is_indexed() -> None:
    readme = _read(ROOT / "README.md")
    migration = ROOT / "docs" / "migration" / "77.frontend-navigation-dashboard-fallback-integrity.md"

    assert migration.exists()
    assert "77.frontend-navigation-dashboard-fallback-integrity.md" in readme


def test_canonical_surface_navigation_hardening_migration_is_indexed() -> None:
    readme = _read(ROOT / "README.md")
    migration = ROOT / "docs" / "migration" / "89.canonical-surface-navigation-hardening.md"

    assert migration.exists()
    assert "89.canonical-surface-navigation-hardening.md" in readme


def test_training_root_reentry_canonicalization_migration_is_indexed() -> None:
    readme = _read(ROOT / "README.md")
    migration = ROOT / "docs" / "migration" / "92.training-root-reentry-canonicalization.md"

    assert migration.exists()
    assert "92.training-root-reentry-canonicalization.md" in readme


def test_training_root_router_state_hardening_migration_is_indexed() -> None:
    readme = _read(ROOT / "README.md")
    migration = ROOT / "docs" / "migration" / "93.training-root-router-state-hardening.md"

    assert migration.exists()
    assert "93.training-root-router-state-hardening.md" in readme
