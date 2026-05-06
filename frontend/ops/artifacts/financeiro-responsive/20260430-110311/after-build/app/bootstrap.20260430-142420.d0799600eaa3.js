import {
  DEFAULT_AUTHENTICATED_ROUTE,
  LOGIN_ROUTE,
  consumeReturnRoute,
  currentHashRoute,
  finishFrontendPhase,
  forensicTrace,
  isLoginRoute,
  isRestorableRoute,
  peekLastSuccessfulRoute,
  refreshSession,
  rememberLastSuccessfulRoute,
  rememberReturnRoute,
  resetFrontendPerf,
  responsiveStateMarkup,
  routePath,
  routeFromCurrentPathname,
  routeKeyFromHash,
  startFrontendPhase,
  state,
  installForensicRuntimeHooks,
} from "../lib.20260430-142420.cf58b4b4395e.js";
import { renderLoginPage, renderShell } from "../shell.20260430-142420.eed3fe973fa2.js";

import {
  isSessionValidationUnavailable,
  registerGlobalErrorHandlers,
  renderRouteFailure,
  renderSessionValidationUnavailable,
} from "./errors.20260430-142420.a07555f0a706.js";
import { renderForbiddenRoute, routeAllowed } from "./guards.20260430-142420.608a197ed3ae.js";
import { resolveRoute, withFrontendPhase } from "./router.20260430-142420.1027e0a52be7.js";

let eventHandlersRegistered = false;

function activeRouteKey() {
  return routePath() || routeFromCurrentPathname();
}

function fullActiveRoute() {
  return currentHashRoute() || activeRouteKey();
}

function isResolvableRoute(route) {
  const routeKey = routeKeyFromHash(route);
  return Boolean(routeKey && resolveRoute(routeKey));
}

function recoverableRoute(route) {
  const normalized = currentHashRoute() === route ? currentHashRoute() : route;
  return isRestorableRoute(normalized) && isResolvableRoute(normalized) ? normalized : "";
}

function authenticatedLandingRoute() {
  const candidates = [
    consumeReturnRoute(),
    peekLastSuccessfulRoute(),
    DEFAULT_AUTHENTICATED_ROUTE,
  ];
  return candidates.find((candidate) => recoverableRoute(candidate)) || DEFAULT_AUTHENTICATED_ROUTE;
}

function redirectHash(route, detail = {}) {
  const target = route || DEFAULT_AUTHENTICATED_ROUTE;
  const current = currentHashRoute();
  if (current === target) return false;
  forensicTrace("redirect.hash", { from: current || activeRouteKey() || "", to: target, ...detail }, { assets: true });
  window.location.hash = target;
  return true;
}

function registerAppEventHandlers() {
  if (eventHandlersRegistered) return;
  installForensicRuntimeHooks();
  window.addEventListener("hashchange", () => {
    forensicTrace("bootstrap.hashchange.restart", { nextRoute: activeRouteKey() }, { assets: true });
    void startApp();
  });
  registerGlobalErrorHandlers();
  eventHandlersRegistered = true;
  forensicTrace("bootstrap.handlers.registered", { route: activeRouteKey() });
}

export async function startApp() {
  registerAppEventHandlers();
  const perf = resetFrontendPerf();
  const startupRoute = activeRouteKey();
  forensicTrace("bootstrap.start", {
    bootId: perf.bootId,
    route: startupRoute,
    authenticatedBeforeRefresh: Boolean(state.session?.authenticated),
  }, { assets: true });
  const startupPhase = startFrontendPhase("startup", { route: startupRoute });
  try {
    try {
      forensicTrace("session.refresh.begin", { bootId: perf.bootId, route: activeRouteKey() });
      await withFrontendPhase("session", () => refreshSession());
      forensicTrace("session.refresh.ok", {
        bootId: perf.bootId,
        authenticated: Boolean(state.session?.authenticated),
        permissions: state.session?.capabilities?.granted_permissions?.length || 0,
      });
    } catch (error) {
      forensicTrace("session.refresh.error", { bootId: perf.bootId, error });
      if (isSessionValidationUnavailable(error)) {
        forensicTrace("session.unavailable.render", { bootId: perf.bootId, error }, { assets: true });
        renderSessionValidationUnavailable(error, startApp);
        return;
      }
      state.session = null;
      state.csrfToken = "";
    }

    const activeRoute = activeRouteKey();
    if (!state.session?.authenticated) {
      const returnRoute = recoverableRoute(fullActiveRoute());
      if (returnRoute) {
        rememberReturnRoute(returnRoute);
      }
      if (!isLoginRoute(activeRoute)) {
        forensicTrace("redirect.to_login", {
          bootId: perf.bootId,
          from: activeRoute,
          reason: "unauthenticated_session",
          returnRoute,
        }, { assets: true });
        redirectHash(LOGIN_ROUTE, { reason: "unauthenticated_session" });
      }
      forensicTrace("render.login.begin", { bootId: perf.bootId, route: activeRouteKey() || LOGIN_ROUTE }, { assets: true });
      renderLoginPage(startApp);
      forensicTrace("render.login.end", { bootId: perf.bootId, route: activeRouteKey() || LOGIN_ROUTE }, { assets: true });
      return;
    }

    if (isLoginRoute(activeRoute)) {
      const landingRoute = authenticatedLandingRoute();
      forensicTrace("redirect.authenticated_landing", {
        bootId: perf.bootId,
        from: activeRoute,
        reason: "authenticated_login_route",
        to: landingRoute,
      }, { assets: true });
      redirectHash(landingRoute, { reason: "authenticated_login_route" });
      return;
    }

    if (!activeRoute) {
      const landingRoute = authenticatedLandingRoute();
      forensicTrace("redirect.authenticated_landing", {
        bootId: perf.bootId,
        from: "",
        reason: "empty_hash_authenticated_entry",
        to: landingRoute,
      }, { assets: true });
      redirectHash(landingRoute, { reason: "empty_hash_authenticated_entry" });
      return;
    }

    const routeKey = activeRoute;
    forensicTrace("route.resolve.begin", { bootId: perf.bootId, route: routeKey });
    const routeConfig = await withFrontendPhase(
      "route_resolve",
      () => Promise.resolve(resolveRoute(routeKey)),
      { route: routeKey },
    );
    forensicTrace("route.resolve.end", {
      bootId: perf.bootId,
      route: routeKey,
      found: Boolean(routeConfig),
      permissions: routeConfig?.permissions || [],
    });
    if (!routeConfig) {
      forensicTrace("route.not_found.render", { bootId: perf.bootId, route: routeKey }, { assets: true });
      renderShell(`
        <section class="panel ui-surface">
          ${responsiveStateMarkup({
            title: "Rota nao encontrada.",
            detail: "Esta tela nao esta registrada no frontend novo.",
            type: "empty",
            className: "empty route-state",
          })}
        </section>
      `, "Nao encontrado");
      return;
    }
    if (!routeAllowed(routeConfig)) {
      forensicTrace("route.forbidden.render", { bootId: perf.bootId, route: routeKey, permissions: routeConfig.permissions || [] });
      renderForbiddenRoute();
      return;
    }
    try {
      forensicTrace("route.render.begin", { bootId: perf.bootId, route: routeKey }, { assets: true });
      await withFrontendPhase("route_render", () => routeConfig.render(), { route: routeKey });
      rememberLastSuccessfulRoute(currentHashRoute() || routeKey);
      forensicTrace("route.render.end", { bootId: perf.bootId, route: routeKey }, { assets: true });
    } catch (error) {
      forensicTrace("route.render.error", { bootId: perf.bootId, route: routeKey, error }, { assets: true });
      renderRouteFailure(error, startApp);
    }
  } finally {
    finishFrontendPhase(startupPhase, { route: routePath() || "" });
    forensicTrace("bootstrap.end", {
      bootId: perf.bootId,
      route: routePath() || "",
      phases: state.frontendPerf?.phases || [],
    }, { assets: true });
  }
}

