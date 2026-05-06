import { refreshSession, routePath, showFlash, state } from "./lib.js?v=20260408-161023";
import { renderLoginPage, renderShell } from "./shell.js?v=20260408-161023";
import { renderDashboardPage, renderRelatorioIndividualPage, renderTripulanteFormPage, renderTripulantesListPage } from "./pages-dashboard-tripulantes.js?v=20260408-161023";
import {
  renderRelatorioHabilitacoesPage,
  renderRelatorioProdutividadePage,
  renderTrainingRootPage,
  renderTreinamentoFormPage,
  renderTreinamentosListPage,
} from "./pages-treinamentos-relatorios.js?v=20260408-161023";

const routes = {
  "#/dashboard": renderDashboardPage,
  "#/tripulantes": renderTripulantesListPage,
  "#/relatorios/individual": renderRelatorioIndividualPage,
  "#/tripulantes/new": () => renderTripulanteFormPage(),
  "#/treinamentos": renderTreinamentosListPage,
  "#/treinamentos/new": renderTreinamentosListPage,
  "#/treinamentos/raiz": renderTrainingRootPage,
  "#/relatorios/habilitacoes": renderRelatorioHabilitacoesPage,
  "#/relatorios/produtividade": renderRelatorioProdutividadePage,
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
    return () => renderTripulanteFormPage(Number(routeKey.split("/").pop()));
  }
  if (/^#\/treinamentos\/\d+$/.test(routeKey)) {
    return () => renderTreinamentoFormPage(Number(routeKey.split("/").pop()));
  }
  return null;
}

async function boot() {
  try {
    await refreshSession();
  } catch (_error) {
    state.session = null;
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
  const render = routes[routeKey] || resolveDynamicRoute(routeKey);
  if (!render) {
    renderShell("<section class='panel'><div class='empty'>Rota não encontrada no frontend novo.</div></section>", "Não encontrado");
    return;
  }
  await render();
}

void boot();



