import {
  finishFrontendPhase,
  forensicTrace,
  startFrontendPhase,
} from "../lib.20260430-142420.cf58b4b4395e.js";

import {
  dynamicRouteDefinitions,
  routeModuleLoaders,
  staticRouteDefinitions,
} from "./route-registry.20260430-142420.cc8ea7ca18a7.js";

const routeModuleCache = new Map();

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
    throw error;
  });
  routeModuleCache.set(moduleName, promise);
  forensicTrace("router.import.cached_promise", { module: moduleName });
  return promise;
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

