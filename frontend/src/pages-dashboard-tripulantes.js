import { renderDashboardPage as renderDashboardFeaturePage } from "./features/dashboard/page.js";
import { renderDashboardPage as renderOperationalDashboardFeaturePage } from "./features/dashboard-operacional/page.js";
import { renderRelatorioIndividualPage as renderRelatorioIndividualFeaturePage } from "./features/relatorio-individual/page.js";
import { renderTripulanteFormPage as renderTripulanteFormFeaturePage } from "./features/tripulantes/form-page.js";
import { renderTripulantesListPage as renderTripulantesListFeaturePage } from "./features/tripulantes/list-page.js";

export async function renderDashboardPage() {
  return renderDashboardFeaturePage();
}

export async function renderOperationalDashboardPage() {
  return renderOperationalDashboardFeaturePage();
}

export async function renderOperationalDashboardTvPage() {
  return renderOperationalDashboardFeaturePage({ tv: true });
}

export async function renderTripulantesListPage(viewMode = "cadastro") {
  return renderTripulantesListFeaturePage(viewMode);
}

export async function renderRelatorioIndividualPage() {
  return renderRelatorioIndividualFeaturePage();
}

export async function renderTripulanteFormPage(tripulanteId = null) {
  return renderTripulanteFormFeaturePage(tripulanteId);
}

