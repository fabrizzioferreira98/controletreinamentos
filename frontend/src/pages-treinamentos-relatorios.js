import { renderRelatorioHabilitacoesPage as renderRelatorioHabilitacoesFeaturePage } from "./features/relatorios/habilitacoes-page.js";
import { renderTrainingRootPage as renderTrainingRootFeaturePage } from "./features/training-root/page.js";
import { renderTreinamentoFormPage as renderTreinamentoFormFeaturePage } from "./features/treinamentos/form-page.js";
import { renderTreinamentosListPage as renderTreinamentosListFeaturePage } from "./features/treinamentos/list-page.js";

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

