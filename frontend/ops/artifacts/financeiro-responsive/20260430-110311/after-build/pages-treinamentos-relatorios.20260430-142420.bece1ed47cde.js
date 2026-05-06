import { renderRelatorioHabilitacoesPage as renderRelatorioHabilitacoesFeaturePage } from "./features/relatorios/habilitacoes-page.20260430-142420.04fd3d8e1586.js";
import { renderTrainingRootPage as renderTrainingRootFeaturePage } from "./features/training-root/page.20260430-142420.06f7e649b09d.js";
import { renderTreinamentoFormPage as renderTreinamentoFormFeaturePage } from "./features/treinamentos/form-page.20260430-142420.1cc8363987d3.js";
import { renderTreinamentosListPage as renderTreinamentosListFeaturePage } from "./features/treinamentos/list-page.20260430-142420.12771089d1c8.js";

export async function renderTreinamentosListPage() {
  return renderTreinamentosListFeaturePage();
}

export async function renderTrainingRootPage() {
  return renderTrainingRootFeaturePage();
}

export async function renderTreinamentoFormPage(treinamentoId = null) {
  return renderTreinamentoFormFeaturePage(treinamentoId);
}

export async function renderRelatorioHabilitacoesPage() {
  return renderRelatorioHabilitacoesFeaturePage();
}

