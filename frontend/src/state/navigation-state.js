import { resolveFrontendHashForBackendPath } from "../compat/backend-links.js";

export const DEFAULT_AUTHENTICATED_ROUTE = "#/dashboard";
export const LOGIN_ROUTE = "#/login";

const LAST_SUCCESSFUL_ROUTE_KEY = "controle_treinamentos.navigation.last_successful_route.v1";
const RETURN_ROUTE_KEY = "controle_treinamentos.navigation.return_route.v1";

function storageGet(key) {
  try {
    return window.sessionStorage?.getItem(key) || "";
  } catch (_error) {
    return "";
  }
}

function storageSet(key, value) {
  try {
    window.sessionStorage?.setItem(key, value);
  } catch (_error) {
    // Navigation memory is a resilience layer; routing must still work without storage.
  }
}

function storageRemove(key) {
  try {
    window.sessionStorage?.removeItem(key);
  } catch (_error) {
    // Ignore storage restrictions.
  }
}

export function normalizeHashRoute(value) {
  const route = String(value || "").trim();
  return route.startsWith("#/") ? route : "";
}

export function routeKeyFromHash(value) {
  return normalizeHashRoute(value).split("?")[0] || "";
}

export function currentHashRoute() {
  return normalizeHashRoute(window.location.hash || "");
}

export function routeFromCurrentPathname() {
  const pathname = String(window.location.pathname || "").replace(/\/+$/, "") || "/";
  const canonicalHash = resolveFrontendHashForBackendPath(pathname);
  if (canonicalHash) return canonicalHash;
  if (pathname === "/login") return LOGIN_ROUTE;
  return "";
}

export function isLoginRoute(value) {
  return routeKeyFromHash(value) === LOGIN_ROUTE;
}

export function isRestorableRoute(value) {
  const routeKey = routeKeyFromHash(value);
  return Boolean(routeKey && routeKey !== LOGIN_ROUTE);
}

export function rememberReturnRoute(value = currentHashRoute()) {
  const route = normalizeHashRoute(value);
  if (!isRestorableRoute(route)) return "";
  storageSet(RETURN_ROUTE_KEY, route);
  return route;
}

export function rememberCurrentRouteForLogin() {
  return rememberReturnRoute(currentHashRoute());
}

export function consumeReturnRoute() {
  const route = normalizeHashRoute(storageGet(RETURN_ROUTE_KEY));
  storageRemove(RETURN_ROUTE_KEY);
  return isRestorableRoute(route) ? route : "";
}

export function peekLastSuccessfulRoute() {
  const route = normalizeHashRoute(storageGet(LAST_SUCCESSFUL_ROUTE_KEY));
  return isRestorableRoute(route) ? route : "";
}

export function rememberLastSuccessfulRoute(value = currentHashRoute()) {
  const route = normalizeHashRoute(value);
  if (!isRestorableRoute(route)) return "";
  storageSet(LAST_SUCCESSFUL_ROUTE_KEY, route);
  return route;
}
