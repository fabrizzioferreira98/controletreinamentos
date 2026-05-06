import {
  buildErrorMessage,
  emptyTableRowMarkup,
  escapeAttr,
  escapeHtml,
  formatCompetenciaLabel,
  formatCurrencyBr,
  responsiveStateMarkup,
} from "../../lib.20260430-142420.cf58b4b4395e.js";
import { renderShell } from "../../shell.20260430-142420.eed3fe973fa2.js";
import {
  getFinanceiroBonificacaoHoraria,
  getFinanceiroBonificacaoProdutividade,
  listFinanceiroBonificacoesHorarias,
  listFinanceiroBonificacoesProdutividade,
} from "../../services/financeiro-bonificacoes-api.20260430-142420.85536ef9311a.js";

const DEFAULT_FILTERS = {
  competencia: currentCompetencia(),
  tripulanteId: "",
  funcao: "",
  status: "calculado",
};

const DEFAULT_PRODUCTIVITY_FILTERS = { ...DEFAULT_FILTERS };

let currentBonusesState = {
  filters: { ...DEFAULT_FILTERS },
  items: [],
  selected: null,
  status: "loading",
  detailStatus: "idle",
  message: "",
};

let currentProductivityState = {
  filters: { ...DEFAULT_PRODUCTIVITY_FILTERS },
  items: [],
  selected: null,
  status: "loading",
  detailStatus: "idle",
  message: "",
};

let activeBonusesMobileSection = "hourly";

function currentCompetencia() {
  return new Date().toISOString().slice(0, 7);
}

function normalizeItems(payload) {
  return Array.isArray(payload?.items) ? payload.items : [];
}

function statusClass(status) {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "calculado") return "status-green";
  if (normalized === "obsoleto") return "status-dark";
  return "status-yellow";
}

function formatMinutes(value) {
  const amount = Number(value || 0);
  if (!Number.isFinite(amount)) return "0 min";
  return `${amount.toLocaleString("pt-BR", { maximumFractionDigits: 0 })} min`;
}

function formatDecimal(value) {
  const amount = Number(value || 0);
  if (!Number.isFinite(amount)) return "0";
  return amount.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 4 });
}

function tripulanteLabel(item) {
  return item?.tripulante?.nome || `Tripulante #${item?.tripulante_id || "-"}`;
}

function missionLabel(item) {
  const mission = item?.missao || {};
  return [mission.cavok_numero_voo, mission.chamado, mission.contratante].filter(Boolean).join(" / ") || `Missao #${item?.mission_id || "-"}`;
}

function memoryStepMarkup(step) {
  return `
    <li class="financeiro-memory-step">
      <strong>${escapeHtml(step.rule_label || step.rule_key || "Regra aplicada")}</strong>
      <span>${escapeHtml(step.formula_conceitual || "Formula registrada na memoria do backend.")}</span>
      <code>${escapeHtml(JSON.stringify(step.resultado_final || step.resultado_intermediario || {}))}</code>
    </li>
  `;
}

function parametersMarkup(parameters) {
  return parameters.length
    ? `<div class="financeiro-parameter-chips">${parameters
        .map((parameter) => `<span class="filters-state-chip ui-filter-chip">${escapeHtml(parameter.tipo)}: ${escapeHtml(parameter.valor)} ${escapeHtml(parameter.unidade)}</span>`)
        .join("")}</div>`
    : responsiveStateMarkup({
        title: "Parametros nao informados",
        detail: "A API nao retornou parametros usados para este calculo.",
        type: "empty",
        compact: true,
      });
}

function renderDetailPanel() {
  if (currentBonusesState.detailStatus === "loading") {
    return responsiveStateMarkup({
      title: "Carregando memoria",
      detail: "Buscando detalhe da bonificacao horaria.",
      type: "loading",
      compact: true,
    });
  }
  const item = currentBonusesState.selected;
  if (!item) {
    return responsiveStateMarkup({
      title: "Selecione um calculo",
      detail: "A memoria de calculo aparece aqui exatamente como retornada pela API.",
      type: "info",
      compact: true,
    });
  }
  const memory = item.memoria_calculo || {};
  const steps = Array.isArray(memory.steps) ? memory.steps : [];
  const parameters = Array.isArray(item.parametros_usados) ? item.parametros_usados : [];
  return `
    <article class="financeiro-settings-card financeiro-hourly-detail" data-hourly-detail>
      <span class="status-pill ${statusClass(item.status)}">${escapeHtml(item.status || "calculado")}</span>
      <h2>${escapeHtml(missionLabel(item))}</h2>
      <p>${escapeHtml(tripulanteLabel(item))} - ${escapeHtml(item.funcao || "-")}</p>
      <dl class="financeiro-detail-grid">
        <div><dt>Jornada</dt><dd>${escapeHtml(formatMinutes(item.jornada_total_minutos))}</dd></div>
        <div><dt>Minutos noturnos reais</dt><dd>${escapeHtml(formatMinutes(item.minutos_noturnos_reais))}</dd></div>
        <div><dt>Horas noturnas convertidas</dt><dd>${escapeHtml(formatDecimal(item.horas_noturnas_convertidas))}</dd></div>
        <div><dt>Total</dt><dd>${escapeHtml(formatCurrencyBr(item.total))}</dd></div>
      </dl>
      <div class="financeiro-settings-notice">
        <strong>Hora noturna</strong>
        <span>Quando aplicavel, a hora noturna convertida usa o parametro vigente de 52,5 minutos registrado pelo backend.</span>
      </div>
      <h3>Memoria de calculo</h3>
      ${steps.length
        ? `<ol class="financeiro-memory-list">${steps.map(memoryStepMarkup).join("")}</ol>`
        : responsiveStateMarkup({
            title: "Memoria nao detalhada",
            detail: "Este calculo nao trouxe etapas detalhadas.",
            type: "empty",
            compact: true,
          })}
      <h3>Parametros usados</h3>
      ${parametersMarkup(parameters)}
    </article>
  `;
}

function renderProductivityDetailPanel() {
  if (currentProductivityState.detailStatus === "loading") {
    return responsiveStateMarkup({
      title: "Carregando memoria",
      detail: "Buscando detalhe da bonificacao por funcao/produtividade.",
      type: "loading",
      compact: true,
    });
  }
  const item = currentProductivityState.selected;
  if (!item) {
    return responsiveStateMarkup({
      title: "Selecione um consolidado",
      detail: "A memoria de produtividade aparece aqui exatamente como retornada pela API.",
      type: "info",
      compact: true,
    });
  }
  const memory = item.memoria_calculo || {};
  const steps = Array.isArray(memory.steps) ? memory.steps : [];
  const parameters = Array.isArray(item.parametros_usados) ? item.parametros_usados : [];
  return `
    <article class="financeiro-settings-card financeiro-hourly-detail" data-productivity-detail>
      <span class="status-pill ${statusClass(item.status)}">${escapeHtml(item.status || "calculado")}</span>
      <h2>${escapeHtml(tripulanteLabel(item))}</h2>
      <p>${escapeHtml(formatCompetenciaLabel(item.competencia))} - ${escapeHtml(item.funcao || "-")}</p>
      <dl class="financeiro-detail-grid">
        <div><dt>ICAO/SDEA</dt><dd>${escapeHtml(formatCurrencyBr(item.valor_icao))}</dd></div>
        <div><dt>Instrutor</dt><dd>${escapeHtml(formatCurrencyBr(item.valor_instrutor))}</dd></div>
        <div><dt>Checador</dt><dd>${escapeHtml(formatCurrencyBr(item.valor_checador))}</dd></div>
        <div><dt>Categoria A</dt><dd>${escapeHtml(formatCurrencyBr(item.valor_missoes_categoria_a))}</dd></div>
        <div><dt>Categoria B</dt><dd>${escapeHtml(formatCurrencyBr(item.valor_missoes_categoria_b))}</dd></div>
        <div><dt>Cobertura de base</dt><dd>${escapeHtml(formatCurrencyBr(item.valor_cobertura_base))}</dd></div>
        <div><dt>Excecao Palmas</dt><dd>${escapeHtml(formatCurrencyBr(item.valor_excecao_palmas))}</dd></div>
        <div><dt>Produtividade</dt><dd>${escapeHtml(formatCurrencyBr(item.produtividade_calculada))}</dd></div>
        <div><dt>Garantia minima</dt><dd>${escapeHtml(formatCurrencyBr(item.garantia_minima))}</dd></div>
        <div><dt>Total devido</dt><dd>${escapeHtml(formatCurrencyBr(item.total_devido))}</dd></div>
      </dl>
      <div class="financeiro-settings-notice">
        <strong>Somente exibicao</strong>
        <span>Os valores, regras e totais desta memoria foram calculados e persistidos pelo backend.</span>
      </div>
      <h3>Memoria de calculo</h3>
      ${steps.length
        ? `<ol class="financeiro-memory-list">${steps.map(memoryStepMarkup).join("")}</ol>`
        : responsiveStateMarkup({
            title: "Memoria nao detalhada",
            detail: "Este consolidado nao trouxe etapas detalhadas.",
            type: "empty",
            compact: true,
          })}
      <h3>Parametros usados</h3>
      ${parametersMarkup(parameters)}
    </article>
  `;
}

function rowMarkup(item) {
  const mission = item.missao || {};
  return `
    <tr>
      <td>${escapeHtml(formatCompetenciaLabel(item.competencia))}</td>
      <td>${escapeHtml(missionLabel(item))}</td>
      <td>${escapeHtml(tripulanteLabel(item))}</td>
      <td>${escapeHtml(item.funcao || "-")}</td>
      <td>${escapeHtml(formatMinutes(item.jornada_total_minutos))}</td>
      <td>${escapeHtml(formatMinutes(item.minutos_noturnos_reais))}</td>
      <td>${escapeHtml(formatDecimal(item.horas_noturnas_convertidas))}</td>
      <td>${item.domingo_feriado ? "Sim" : "Nao"}</td>
      <td>${escapeHtml(formatCurrencyBr(item.total))}</td>
      <td><span class="status-pill ${statusClass(item.status)}">${escapeHtml(item.status || "calculado")}</span></td>
      <td><button type="button" class="button-link secondary" data-hourly-detail-id="${escapeAttr(item.id)}">Memoria</button></td>
    </tr>
  `;
}

function tableBodyMarkup() {
  if (currentBonusesState.status === "loading") {
    return emptyTableRowMarkup(11, {
      title: "Carregando bonificacoes horarias",
      detail: "Consultando calculos persistidos pelo backend.",
      type: "loading",
    });
  }
  if (currentBonusesState.status === "error") {
    return emptyTableRowMarkup(11, {
      title: "Nao foi possivel carregar bonificacoes",
      detail: currentBonusesState.message,
      actionLabel: "Tentar novamente",
      actionId: "finance-hourly-retry",
      type: "error",
    });
  }
  if (!currentBonusesState.items.length) {
    return emptyTableRowMarkup(11, {
      title: "Nenhuma bonificacao horaria encontrada",
      detail: "Execute o recalculo de uma Missao Operacional para gerar registros de bonificacao horaria.",
      type: "empty",
    });
  }
  return currentBonusesState.items.map(rowMarkup).join("");
}

function productivityRowMarkup(item) {
  return `
    <tr>
      <td>${escapeHtml(formatCompetenciaLabel(item.competencia))}</td>
      <td>${escapeHtml(tripulanteLabel(item))}</td>
      <td>${escapeHtml(item.funcao || "-")}</td>
      <td>${escapeHtml(item.categoria_aplicavel || "-")}</td>
      <td>${escapeHtml(formatCurrencyBr(item.valor_icao))}</td>
      <td>${escapeHtml(formatCurrencyBr(item.valor_instrutor))}</td>
      <td>${escapeHtml(formatCurrencyBr(item.valor_checador))}</td>
      <td>${escapeHtml(formatCurrencyBr(item.valor_missoes_categoria_a))}</td>
      <td>${escapeHtml(formatCurrencyBr(item.valor_missoes_categoria_b))}</td>
      <td>${escapeHtml(formatCurrencyBr(item.produtividade_calculada))}</td>
      <td>${escapeHtml(formatCurrencyBr(item.garantia_minima))}</td>
      <td>${escapeHtml(formatCurrencyBr(item.total_devido))}</td>
      <td><span class="status-pill ${statusClass(item.status)}">${escapeHtml(item.status || "calculado")}</span></td>
      <td><button type="button" class="button-link secondary" data-productivity-detail-id="${escapeAttr(item.tripulante_id)}">Memoria</button></td>
    </tr>
  `;
}

function productivityTableBodyMarkup() {
  if (currentProductivityState.status === "loading") {
    return emptyTableRowMarkup(14, {
      title: "Carregando produtividade",
      detail: "Consultando consolidados persistidos pelo backend.",
      type: "loading",
    });
  }
  if (currentProductivityState.status === "error") {
    return emptyTableRowMarkup(14, {
      title: "Nao foi possivel carregar produtividade",
      detail: currentProductivityState.message,
      actionLabel: "Tentar novamente",
      actionId: "finance-productivity-retry",
      type: "error",
    });
  }
  if (!currentProductivityState.items.length) {
    return emptyTableRowMarkup(14, {
      title: "Nenhuma bonificacao por funcao/produtividade encontrada",
      detail: "O consolidado aparecera apos recalc da competencia pelo backend.",
      type: "empty",
    });
  }
  return currentProductivityState.items.map(productivityRowMarkup).join("");
}

function filtersMarkup() {
  const filters = currentBonusesState.filters;
  return `
    <form class="filters-grid ui-filter-panel" data-hourly-filters>
      <label>
        <span>Competencia</span>
        <input type="month" name="competencia" value="${escapeAttr(filters.competencia)}">
      </label>
      <label>
        <span>Tripulante ID</span>
        <input type="number" name="tripulanteId" min="1" value="${escapeAttr(filters.tripulanteId)}" placeholder="Opcional">
      </label>
      <label>
        <span>Funcao</span>
        <select name="funcao">
          <option value="">Todas</option>
          <option value="comandante" ${filters.funcao === "comandante" ? "selected" : ""}>Comandante</option>
          <option value="copiloto" ${filters.funcao === "copiloto" ? "selected" : ""}>Copiloto</option>
        </select>
      </label>
      <label>
        <span>Status</span>
        <select name="status">
          <option value="">Todos</option>
          <option value="calculado" ${filters.status === "calculado" ? "selected" : ""}>Calculado</option>
          <option value="recalculo_pendente" ${filters.status === "recalculo_pendente" ? "selected" : ""}>Recalculo pendente</option>
          <option value="obsoleto" ${filters.status === "obsoleto" ? "selected" : ""}>Obsoleto</option>
        </select>
      </label>
      <div class="filter-actions">
        <button type="submit" class="button-link primary">Filtrar</button>
        <button type="button" class="button-link secondary" data-hourly-clear>Limpar</button>
      </div>
    </form>
  `;
}

function productivityFiltersMarkup() {
  const filters = currentProductivityState.filters;
  return `
    <form class="filters-grid ui-filter-panel" data-productivity-filters>
      <label>
        <span>Competencia</span>
        <input type="month" name="competencia" value="${escapeAttr(filters.competencia)}">
      </label>
      <label>
        <span>Tripulante ID</span>
        <input type="number" name="tripulanteId" min="1" value="${escapeAttr(filters.tripulanteId)}" placeholder="Opcional">
      </label>
      <label>
        <span>Funcao</span>
        <select name="funcao">
          <option value="">Todas</option>
          <option value="comandante" ${filters.funcao === "comandante" ? "selected" : ""}>Comandante</option>
          <option value="copiloto" ${filters.funcao === "copiloto" ? "selected" : ""}>Copiloto</option>
        </select>
      </label>
      <label>
        <span>Status</span>
        <select name="status">
          <option value="">Todos</option>
          <option value="calculado" ${filters.status === "calculado" ? "selected" : ""}>Calculado</option>
          <option value="recalculo_pendente" ${filters.status === "recalculo_pendente" ? "selected" : ""}>Recalculo pendente</option>
          <option value="obsoleto" ${filters.status === "obsoleto" ? "selected" : ""}>Obsoleto</option>
        </select>
      </label>
      <div class="filter-actions">
        <button type="submit" class="button-link primary">Filtrar</button>
        <button type="button" class="button-link secondary" data-productivity-clear>Limpar</button>
      </div>
    </form>
  `;
}

function renderFinanceiroBonificacoes(state = currentBonusesState) {
  currentBonusesState = state;
  renderShell(
    `
      <div class="financeiro-settings-page priority-page-surface ui-page-shell ui-stack" data-finance-page="bonificacoes" data-mobile-active-section="${escapeAttr(activeBonusesMobileSection)}">
        <div class="page-header priority-page-header ui-page-header ui-surface">
          <div>
            <h1>Bonificacoes</h1>
            <p class="page-subtitle">Visualize resultados de bonificacao horaria calculados e persistidos pelo backend.</p>
          </div>
          <div class="page-header-actions">
            <a class="button-link secondary" href="#/financeiro/missoes">Missoes Operacionais</a>
          </div>
        </div>

        <section class="panel ui-surface financeiro-settings-notice">
          <strong>Sem calculo no frontend</strong>
          <span>Esta tela apenas exibe resultados, parametros usados e memoria retornados pela API.</span>
        </section>

        <nav class="financeiro-mobile-section-tabs" aria-label="Secoes de bonificacoes" data-finance-mobile-tabs="bonificacoes">
          <button type="button" data-finance-bonus-tab="hourly" aria-selected="${activeBonusesMobileSection === "hourly" ? "true" : "false"}">Horaria</button>
          <button type="button" data-finance-bonus-tab="productivity" aria-selected="${activeBonusesMobileSection === "productivity" ? "true" : "false"}">Produtividade</button>
        </nav>

        <section class="panel ui-surface ui-stack">
          <div class="financeiro-settings-card-grid">
            <article class="financeiro-settings-card">
              <span class="status-pill status-green">Disponivel</span>
              <h2>Bonificacao Horaria</h2>
              <p>Consulta dos calculos por participante gerados no recalculo da Missao Operacional.</p>
            </article>
            <article class="financeiro-settings-card">
              <span class="status-pill status-green">Disponivel</span>
              <h2>Funcao / Produtividade</h2>
              <p>Consulta da consolidacao por competencia, tripulante e funcao calculada pelo backend.</p>
            </article>
          </div>
        </section>

        <section class="panel ui-surface ui-stack" data-hourly-tab data-finance-bonus-section="hourly">
          <div class="section-header">
            <div>
              <h2>Horaria</h2>
              <p>Filtros e tabela usam apenas os calculos horarios ja persistidos.</p>
            </div>
          </div>
          ${filtersMarkup()}
          <div class="table-responsive ui-table-wrap">
            <table class="data-table ui-data-table">
              <thead>
                <tr>
                  <th>Competencia</th>
                  <th>Missao</th>
                  <th>Tripulante</th>
                  <th>Funcao</th>
                  <th>Jornada</th>
                  <th>Min. noturnos reais</th>
                  <th>Horas noturnas convertidas</th>
                  <th>Domingo/feriado</th>
                  <th>Total</th>
                  <th>Status</th>
                  <th>Acoes</th>
                </tr>
              </thead>
              <tbody>${tableBodyMarkup()}</tbody>
            </table>
          </div>
        </section>

        <section class="panel ui-surface ui-stack" data-finance-bonus-section="hourly">
          ${renderDetailPanel()}
        </section>

        <section class="panel ui-surface ui-stack" data-productivity-tab data-finance-bonus-section="productivity">
          <div class="section-header">
            <div>
              <h2>Funcao / Produtividade</h2>
              <p>Filtros e tabela usam apenas consolidados de produtividade ja persistidos.</p>
            </div>
          </div>
          ${productivityFiltersMarkup()}
          <div class="table-responsive ui-table-wrap">
            <table class="data-table ui-data-table">
              <thead>
                <tr>
                  <th>Competencia</th>
                  <th>Tripulante</th>
                  <th>Funcao</th>
                  <th>Categoria</th>
                  <th>ICAO/SDEA</th>
                  <th>Instrutor</th>
                  <th>Checador</th>
                  <th>Cat. A</th>
                  <th>Cat. B</th>
                  <th>Produtividade</th>
                  <th>Garantia minima</th>
                  <th>Total devido</th>
                  <th>Status</th>
                  <th>Acoes</th>
                </tr>
              </thead>
              <tbody>${productivityTableBodyMarkup()}</tbody>
            </table>
          </div>
        </section>

        <section class="panel ui-surface ui-stack" data-finance-bonus-section="productivity">
          ${renderProductivityDetailPanel()}
        </section>
      </div>
    `,
    "Bonificacoes",
  );
  wireBonificacoesInteractions();
}

async function loadHourlyBonuses(filters = currentBonusesState.filters) {
  currentBonusesState = {
    ...currentBonusesState,
    filters: { ...filters },
    status: "loading",
    message: "",
  };
  renderFinanceiroBonificacoes(currentBonusesState);
  try {
    const payload = await listFinanceiroBonificacoesHorarias(filters);
    currentBonusesState = {
      ...currentBonusesState,
      items: normalizeItems(payload),
      selected: null,
      status: "ready",
      message: "",
    };
  } catch (error) {
    currentBonusesState = {
      ...currentBonusesState,
      items: [],
      selected: null,
      status: "error",
      message: buildErrorMessage(error),
    };
  }
  renderFinanceiroBonificacoes(currentBonusesState);
}

async function loadHourlyDetail(calculationId) {
  currentBonusesState = {
    ...currentBonusesState,
    detailStatus: "loading",
  };
  renderFinanceiroBonificacoes(currentBonusesState);
  try {
    const payload = await getFinanceiroBonificacaoHoraria(calculationId);
    currentBonusesState = {
      ...currentBonusesState,
      selected: payload.calculation || null,
      detailStatus: "ready",
    };
  } catch (error) {
    currentBonusesState = {
      ...currentBonusesState,
      selected: null,
      detailStatus: "idle",
      message: buildErrorMessage(error),
    };
  }
  renderFinanceiroBonificacoes(currentBonusesState);
}

async function loadProductivityBonuses(filters = currentProductivityState.filters) {
  currentProductivityState = {
    ...currentProductivityState,
    filters: { ...filters },
    status: "loading",
    message: "",
  };
  renderFinanceiroBonificacoes(currentBonusesState);
  try {
    const payload = await listFinanceiroBonificacoesProdutividade(filters);
    currentProductivityState = {
      ...currentProductivityState,
      items: normalizeItems(payload),
      selected: null,
      status: "ready",
      message: "",
    };
  } catch (error) {
    currentProductivityState = {
      ...currentProductivityState,
      items: [],
      selected: null,
      status: "error",
      message: buildErrorMessage(error),
    };
  }
  renderFinanceiroBonificacoes(currentBonusesState);
}

async function loadProductivityDetail(tripulanteId) {
  currentProductivityState = {
    ...currentProductivityState,
    detailStatus: "loading",
  };
  renderFinanceiroBonificacoes(currentBonusesState);
  try {
    const payload = await getFinanceiroBonificacaoProdutividade(tripulanteId, {
      competencia: currentProductivityState.filters.competencia,
      funcao: currentProductivityState.filters.funcao,
    });
    currentProductivityState = {
      ...currentProductivityState,
      selected: payload.calculation || null,
      detailStatus: "ready",
    };
  } catch (error) {
    currentProductivityState = {
      ...currentProductivityState,
      selected: null,
      detailStatus: "idle",
      message: buildErrorMessage(error),
    };
  }
  renderFinanceiroBonificacoes(currentBonusesState);
}

function wireBonificacoesInteractions() {
  wireBonificacoesMobileTabs();

  document.querySelector("[data-hourly-filters]")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    loadHourlyBonuses({
      competencia: String(formData.get("competencia") || "").trim(),
      tripulanteId: String(formData.get("tripulanteId") || "").trim(),
      funcao: String(formData.get("funcao") || "").trim(),
      status: String(formData.get("status") || "").trim(),
    });
  });
  document.querySelector("[data-hourly-clear]")?.addEventListener("click", () => {
    loadHourlyBonuses({ ...DEFAULT_FILTERS });
  });
  document.querySelector("#finance-hourly-retry")?.addEventListener("click", () => {
    loadHourlyBonuses(currentBonusesState.filters);
  });
  document.querySelectorAll("[data-hourly-detail-id]").forEach((button) => {
    button.addEventListener("click", () => {
      loadHourlyDetail(button.dataset.hourlyDetailId);
    });
  });
  document.querySelector("[data-productivity-filters]")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    loadProductivityBonuses({
      competencia: String(formData.get("competencia") || "").trim(),
      tripulanteId: String(formData.get("tripulanteId") || "").trim(),
      funcao: String(formData.get("funcao") || "").trim(),
      status: String(formData.get("status") || "").trim(),
    });
  });
  document.querySelector("[data-productivity-clear]")?.addEventListener("click", () => {
    loadProductivityBonuses({ ...DEFAULT_PRODUCTIVITY_FILTERS });
  });
  document.querySelector("#finance-productivity-retry")?.addEventListener("click", () => {
    loadProductivityBonuses(currentProductivityState.filters);
  });
  document.querySelectorAll("[data-productivity-detail-id]").forEach((button) => {
    button.addEventListener("click", () => {
      loadProductivityDetail(button.dataset.productivityDetailId);
    });
  });
}

function wireBonificacoesMobileTabs() {
  document.querySelectorAll("[data-finance-bonus-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      const nextSection = button.dataset.financeBonusTab || "hourly";
      activeBonusesMobileSection = nextSection === "productivity" ? "productivity" : "hourly";
      const root = document.querySelector("[data-finance-page=\"bonificacoes\"]");
      if (root) root.dataset.mobileActiveSection = activeBonusesMobileSection;
      document.querySelectorAll("[data-finance-bonus-tab]").forEach((tabButton) => {
        tabButton.setAttribute("aria-selected", tabButton.dataset.financeBonusTab === activeBonusesMobileSection ? "true" : "false");
      });
    });
  });
}

export async function renderFinanceiroBonificacoesPage() {
  await loadHourlyBonuses(currentBonusesState.filters || DEFAULT_FILTERS);
  await loadProductivityBonuses(currentProductivityState.filters || DEFAULT_PRODUCTIVITY_FILTERS);
}
