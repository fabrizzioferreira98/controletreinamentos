import { renderFinanceiroMissoesPage as renderFinanceiroMissoesFeaturePage } from "./features/financeiro/missoes-page.js";
import {
  renderFinanceiroLancamentosJornadaPage as renderFinanceiroLancamentosJornadaFeaturePage,
} from "./features/financeiro/bonificacoes-page.js";
import { renderFinanceiroFechamentoParametrosPage as renderFinanceiroFechamentoParametrosFeaturePage } from "./features/financeiro/fechamento-parametros-page.js";

export async function renderFinanceiroMissoesPage() {
  return renderFinanceiroMissoesFeaturePage();
}

export async function renderFinanceiroLancamentosJornadaPage() {
  return renderFinanceiroLancamentosJornadaFeaturePage();
}

export async function renderFinanceiroFechamentoParametrosPage() {
  return renderFinanceiroFechamentoParametrosFeaturePage();
}
