import { renderDashboardPage as renderDashboardFeaturePage } from "./features/dashboard/page.20260430-142420.2476e7d3f4ad.js";
import { renderRelatorioIndividualPage as renderRelatorioIndividualFeaturePage } from "./features/relatorio-individual/page.20260430-142420.1e9b0e7a6174.js";
import { renderTripulanteFormPage as renderTripulanteFormFeaturePage } from "./features/tripulantes/form-page.20260430-142420.f69dcff544ab.js";
import { renderTripulantesListPage as renderTripulantesListFeaturePage } from "./features/tripulantes/list-page.20260430-142420.bca078bcb0c0.js";

export async function renderDashboardPage() {
  return renderDashboardFeaturePage();
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

