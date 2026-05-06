import {
  buildErrorMessage,
  capabilitySet,
  escapeHtml,
  finishFrontendPhase,
  refreshSession,
  resetFrontendPerf,
  routePath,
  showFlash,
  startFrontendPhase,
  state,
} from "./lib.js?v=20260422-095412";
import { renderLoginPage, renderShell } from "./shell.js?v=20260422-095412";

const routeModuleLoaders = {
  tripulantes: () => import("./pages-dashboard-tripulantes.js?v=20260422-095412"),
  treinamentos: () => import("./pages-treinamentos-relatorios.js?v=20260422-095412"),
};

const routeModuleCache = new Map();

async function withFrontendPhase(name, action, detail = {}) {
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
    throw new Error(`Modulo de rota nao registrado: ${moduleName}`);
  }
  if (routeModuleCache.has(moduleName)) {
    return withFrontendPhase("route_import", () => routeModuleCache.get(moduleName), { module: moduleName, cache: "hit" });
  }
  const promise = withFrontendPhase("route_import", loader, { module: moduleName, cache: "miss" }).catch((error) => {
    routeModuleCache.delete(moduleName);
    throw error;
  });
  routeModuleCache.set(moduleName, promise);
  return promise;
}

async function renderLazyRoute(moduleName, exportName, args = []) {
  const module = await loadRouteModule(moduleName);
  const render = module[exportName];
  if (typeof render !== "function") {
    throw new Error(`Render de rota nao encontrado: ${moduleName}.${exportName}`);
  }
  return render(...args);
}

function lazyRoute(moduleName, exportName, permissions, args = []) {
  return {
    permissions,
    render: () => renderLazyRoute(moduleName, exportName, args),
  };
}

const routes = {
  "#/dashboard": lazyRoute("tripulantes", "renderDashboardPage", ["dashboard:view"]),
  "#/tripulantes": lazyRoute("tripulantes", "renderTripulantesListPage", ["tripulantes:view", "relatorio_individual:view"]),
  "#/relatorios/individual": lazyRoute("tripulantes", "renderRelatorioIndividualPage", ["relatorio_individual:view"]),
  "#/tripulantes/new": lazyRoute("tripulantes", "renderTripulanteFormPage", ["tripulantes:create"]),
  "#/treinamentos": lazyRoute("treinamentos", "renderTreinamentosListPage", ["treinamentos:view"]),
  "#/treinamentos/new": lazyRoute("treinamentos", "renderTreinamentosListPage", ["treinamentos:create"]),
  "#/treinamentos/raiz": lazyRoute("treinamentos", "renderTrainingRootPage", ["tipos_treinamento:view"]),
  "#/relatorios/habilitacoes": lazyRoute("treinamentos", "renderRelatorioHabilitacoesPage", ["relatorio_habilitacoes:view"]),
  "#/relatorios/produtividade": lazyRoute("treinamentos", "renderRelatorioProdutividadePage", ["relatorio_produtividade:view"]),
};

window.addEventListener("hashchange", () => void boot());
window.addEventListener("error", (event) => {
  showFlash(`Falha no frontend: ${event.message}`, "error");
});
window.addEventListener("unhandledrejection", (event) => {
  showFlash(`Falha no frontend: ${event.reason?.message || "Promise rejeitada."}`, "error");
});

function resolveDynamicRoute(routeKey) {
  if (/^#\/tripulantes\/\d+$/.test(routeKey)) {
    return lazyRoute("tripulantes", "renderTripulanteFormPage", ["tripulantes:edit"], [Number(routeKey.split("/").pop())]);
  }
  if (/^#\/treinamentos\/\d+$/.test(routeKey)) {
    return lazyRoute("treinamentos", "renderTreinamentoFormPage", ["treinamentos:edit"], [Number(routeKey.split("/").pop())]);
  }
  return null;
}

function routeAllowed(routeConfig) {
  const permissions = routeConfig?.permissions || [];
  if (!permissions.length) return true;
  const granted = capabilitySet();
  return permissions.some((permission) => granted.has(permission));
}

function renderForbiddenRoute() {
  renderShell("<section class='panel'><div class='empty'>Você não tem permissão para acessar esta funcionalidade.</div></section>", "Acesso negado");
}

function isSessionValidationUnavailable(error) {
  return ["auth_backend_unavailable", "service_unavailable", "network_error", "timeout"].includes(error?.code)
    || error?.status === 503;
}

function renderSessionValidationUnavailable(error) {
  document.body.className = "";
  document.title = `Sessão indisponível`;
  document.getElementById("app").innerHTML = `
    <main class="content">
      <section class="panel">
        <div class="empty">
          <strong>Não foi possível validar sua sessão agora.</strong>
          <span>${escapeHtml(buildErrorMessage(error))}</span>
          <button type="button" class="button-link secondary" id="session-retry-button">Tentar novamente</button>
        </div>
      </section>
    </main>
  `;
  document.getElementById("session-retry-button")?.addEventListener("click", () => void boot());
}

function renderRouteFailure(error) {
  const message = buildErrorMessage(error);
  showFlash(message, "error");
  renderShell(`
    <section class="panel">
      <div class="empty">
        <strong>Não foi possível carregar esta tela.</strong>
        <span>${escapeHtml(message)}</span>
        <button type="button" class="button-link secondary" id="route-retry-button">Tentar novamente</button>
      </div>
    </section>
  `, "Falha ao carregar");
  document.getElementById("route-retry-button")?.addEventListener("click", () => void boot());
}

async function boot() {
  resetFrontendPerf();
  const startupPhase = startFrontendPhase("startup", { route: routePath() || "#/dashboard" });
  try {
  try {
    await withFrontendPhase("session", () => refreshSession());
  } catch (error) {
    if (isSessionValidationUnavailable(error)) {
      renderSessionValidationUnavailable(error);
      return;
    }
    state.session = null;
    state.csrfToken = "";
  }
  const activeRoute = routePath() || "#/dashboard";
  if (!state.session?.authenticated) {
    if (activeRoute !== "#/login") {
      window.location.hash = "#/login";
    }
    renderLoginPage(boot);
    return;
  }
  if (activeRoute === "#/login") {
    window.location.hash = "#/dashboard";
    return;
  }
  const routeKey = activeRoute || "#/dashboard";
  const routeConfig = await withFrontendPhase(
    "route_resolve",
    () => Promise.resolve(routes[routeKey] || resolveDynamicRoute(routeKey)),
    { route: routeKey },
  );
  if (!routeConfig) {
    renderShell("<section class='panel'><div class='empty'>Rota não encontrada no frontend novo.</div></section>", "Não encontrado");
    return;
  }
  if (!routeAllowed(routeConfig)) {
    renderForbiddenRoute();
    return;
  }
  try {
    await withFrontendPhase("route_render", () => routeConfig.render(), { route: routeKey });
  } catch (error) {
    renderRouteFailure(error);
  }
  } finally {
    finishFrontendPhase(startupPhase, { route: routePath() || "" });
  }
}

void boot();
