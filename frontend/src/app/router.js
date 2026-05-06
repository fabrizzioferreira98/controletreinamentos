import {
  finishFrontendPhase,
  forensicTrace,
  startFrontendPhase,
} from "../lib.js";

import {
  dynamicRouteDefinitions,
  routeModuleLoaders,
  staticRouteDefinitions,
} from "./route-registry.js";

const routeModuleCache = new Map();
const STALE_ROUTE_IMPORT_RELOAD_KEY = "controle_treinamentos.route_import_reload.v1";

function routeImportReloadSignature(moduleName) {
  if (typeof window === "undefined") return "";
  return [
    moduleName,
    window.location.pathname || "",
    window.location.search || "",
    window.location.hash || "",
  ].join("|");
}

function clearStaleRouteImportReload(moduleName) {
  if (typeof window === "undefined" || !window.sessionStorage) return;
  const signature = routeImportReloadSignature(moduleName);
  if (!signature) return;
  try {
    if (window.sessionStorage.getItem(STALE_ROUTE_IMPORT_RELOAD_KEY) === signature) {
      window.sessionStorage.removeItem(STALE_ROUTE_IMPORT_RELOAD_KEY);
    }
  } catch (_error) {
    // Session storage is best-effort; route loading must remain functional without it.
  }
}

function isLikelyStaleRouteImportError(error) {
  const message = [
    error?.name || "",
    error?.message || "",
  ].join(" ");
  return /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module|ChunkLoadError|Loading chunk .* failed/i.test(message);
}

function requestStaleRouteImportReload(moduleName, error) {
  if (typeof window === "undefined" || !isLikelyStaleRouteImportError(error)) {
    return false;
  }

  const signature = routeImportReloadSignature(moduleName);
  if (!signature) return false;

  try {
    if (window.sessionStorage?.getItem(STALE_ROUTE_IMPORT_RELOAD_KEY) === signature) {
      forensicTrace("router.import.stale_reload.skip", { module: moduleName, signature });
      return false;
    }
    window.sessionStorage?.setItem(STALE_ROUTE_IMPORT_RELOAD_KEY, signature);
  } catch (_error) {
    // If storage is blocked, still attempt one reload for the visible first-load recovery.
  }

  forensicTrace("router.import.stale_reload.request", { module: moduleName, signature, error }, { assets: true });
  window.setTimeout(() => window.location.reload(), 0);
  return true;
}

export async function withFrontendPhase(name, action, detail = {}) {
  const phase = startFrontendPhase(name, detail);
  try {
    const result = await action();
    finishFrontendPhase(phase, { status: "ok" });
    return result;
  } catch (error) {
    finishFrontendPhase(phase, { status: "error", code: error?.code || error?.name || "" });
    throw error;
  }
}

async function loadRouteModule(moduleName) {
  const loader = routeModuleLoaders[moduleName];
  if (!loader) {
    forensicTrace("router.import.unregistered", { module: moduleName });
    throw new Error(`Modulo de rota nao registrado: ${moduleName}`);
  }
  if (routeModuleCache.has(moduleName)) {
    forensicTrace("router.import.cache_hit", { module: moduleName });
    return withFrontendPhase("route_import", () => routeModuleCache.get(moduleName), { module: moduleName, cache: "hit" });
  }
  forensicTrace("router.import.cache_miss", { module: moduleName });
  const promise = withFrontendPhase("route_import", loader, { module: moduleName, cache: "miss" }).catch((error) => {
    forensicTrace("router.import.error", { module: moduleName, error });
    routeModuleCache.delete(moduleName);
    if (requestStaleRouteImportReload(moduleName, error)) {
      return new Promise(() => {});
    }
    throw error;
  });
  routeModuleCache.set(moduleName, promise);
  forensicTrace("router.import.cached_promise", { module: moduleName });
  const module = await promise;
  clearStaleRouteImportReload(moduleName);
  return module;
}

async function renderLazyRoute(moduleName, exportName, args = []) {
  const module = await loadRouteModule(moduleName);
  const render = module[exportName];
  if (typeof render !== "function") {
    forensicTrace("router.render_export.missing", { module: moduleName, exportName });
    throw new Error(`Render de rota nao encontrado: ${moduleName}.${exportName}`);
  }
  forensicTrace("router.render_export.invoke", { module: moduleName, exportName, args });
  return render(...args);
}

function lazyRoute(routeDefinition, args = []) {
  const { moduleName, exportName, permissions } = routeDefinition;
  return {
    permissions,
    render: () => renderLazyRoute(moduleName, exportName, args),
  };
}

export const routes = Object.fromEntries(
  Object.entries(staticRouteDefinitions).map(([routeKey, routeDefinition]) => [
    routeKey,
    lazyRoute(routeDefinition),
  ]),
);

function resolveDynamicRoute(routeKey) {
  const routeDefinition = dynamicRouteDefinitions.find((definition) => definition.pattern.test(routeKey));
  if (!routeDefinition) {
    forensicTrace("router.resolve.dynamic_miss", { route: routeKey });
    return null;
  }
  forensicTrace("router.resolve.dynamic_hit", {
    route: routeKey,
    module: routeDefinition.moduleName,
    exportName: routeDefinition.exportName,
    permissions: routeDefinition.permissions || [],
  });
  return lazyRoute(routeDefinition, routeDefinition.args(routeKey));
}

export function resolveRoute(routeKey) {
  const staticRoute = routes[routeKey];
  if (staticRoute) {
    const staticDefinition = staticRouteDefinitions[routeKey] || {};
    forensicTrace("router.resolve.static_hit", {
      route: routeKey,
      module: staticDefinition.moduleName || "",
      exportName: staticDefinition.exportName || "",
      permissions: staticDefinition.permissions || [],
    });
    return staticRoute;
  }
  return resolveDynamicRoute(routeKey);
}

