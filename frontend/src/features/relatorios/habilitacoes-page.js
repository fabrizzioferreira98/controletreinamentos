import {
  api,
  buildErrorMessage,
  buildHashHref,
  countActiveFilters,
  emptyTableRowMarkup,
  escapeAttr,
  escapeHtml,
  filterSummaryMarkup,
  hashQuery,
  showFlash,
  trainingStatusClass,
} from "../../lib.js";
import { renderShell } from "../../shell.js";
import {
  formatInteger,
  renderReportContextStrip,
  renderReportErrorState,
  renderReportEvidencePanel,
  renderReportLoadingState,
  reportValue,
  wireResponsiveFilters,
} from "./report-ui.js";
import { BACKEND_LINKS, buildBackendHref } from "../../compat/backend-links.js";
import { STATIC_ASSETS } from "../../compat/static-assets.js";
export async function renderRelatorioHabilitacoesPage() {
  const filters = Object.fromEntries(hashQuery().entries());
  renderShell(
    renderReportLoadingState(
      "Carregando consolidado de habilitações",
      "Aplicando filtros e preparando a mesma base para tela, CSV, PDF e impressão.",
    ),
    "Relatório de Habilitações",
  );
  try {
    const { data } = await api(`/api/v1/relatorios/habilitacoes?${new URLSearchParams(filters).toString()}`);
    const report = data.report || {};
    const reportFilters = report.filters || {};
    const reportOptionsPayload = report.options || {};
    const reportOptions = {
      bases: Array.isArray(reportOptionsPayload.bases) ? reportOptionsPayload.bases : [],
      tipos: Array.isArray(reportOptionsPayload.tipos) ? reportOptionsPayload.tipos : [],
      status: Array.isArray(reportOptionsPayload.status) ? reportOptionsPayload.status : [],
    };
    const reportSummary = report.summary || {};
    const reportItems = Array.isArray(report.items) ? report.items : [];
    const activeFilterCount = countActiveFilters(reportFilters, { ordenacao: "criticidade" });
    const hasDenseFilters = Boolean(reportFilters.tipo || reportFilters.status || reportFilters.ordenacao !== "criticidade");
    const orderLabels = {
      criticidade: "Criticidade",
      vencimento: "Vencimento",
    };
    const exportContext = {
      ...reportFilters,
      ordenacao: reportFilters.ordenacao || "criticidade",
    };
    const selectedTipoOption = reportOptions.tipos.find((item) => String(item.id) === String(reportFilters.tipo || ""));
    const selectedStatusOption = reportOptions.status.find((item) => {
      const key = typeof item === "string" ? item : item.key;
      return String(key || "") === String(reportFilters.status || "");
    });
    const selectedStatusLabel = selectedStatusOption
      ? (typeof selectedStatusOption === "string" ? selectedStatusOption : selectedStatusOption.label)
      : "";
    const habilitacoesCsvHref = buildBackendHref(BACKEND_LINKS.treinamentosConsolidadoExportCsv, exportContext);
    const habilitacoesPdfHref = buildBackendHref(BACKEND_LINKS.treinamentosConsolidadoExportPdf, exportContext);
    const habilitacoesPrintHref = buildBackendHref(BACKEND_LINKS.treinamentosConsolidadoRelatorio, exportContext);
    const habilitacoesAutoPrintHref = buildBackendHref(BACKEND_LINKS.treinamentosConsolidadoRelatorio, { ...exportContext, auto_print: 1 });
    const filterLabels = {
      nome: "Tripulante",
      base: "Base",
      tipo: "Tipo",
      status: "Status",
      ordenacao: "Ordenação",
    };

    renderShell(
      `
        <div class="training-reports-page-shell report-priority-page-shell priority-page-surface ui-page-shell ui-stack">
        <div class="page-header report-shell-header priority-page-header ui-page-header ui-surface">
          <div>
            <h1>Consolidado de habilitações</h1>
            <p class="page-subtitle">Visão operacional consolidada de vencimentos de habilitações por tripulante.</p>
          </div>
          <div class="page-header-actions report-export-actions print-hide">
            <a class="button-link secondary" href="#/treinamentos">Voltar para treinamentos</a>
            <a class="button-link secondary" href="${habilitacoesCsvHref}">CSV do recorte</a>
            <a class="button-link secondary" href="${habilitacoesPdfHref}">PDF do recorte</a>
            <a class="button-link" target="_blank" rel="noopener noreferrer" href="${habilitacoesAutoPrintHref}">Imprimir recorte</a>
            <a class="button-link secondary" target="_blank" rel="noopener noreferrer" href="${habilitacoesPrintHref}">Visualizar impressão</a>
          </div>
        </div>

        <section class="panel report-shell training-report-panel ui-surface ui-stack">
          <section class="consolidated-brand-banner print-hide">
            <div class="consolidated-brand-left">
              <img class="consolidated-brand-logo" src="${STATIC_ASSETS.logoBrasilVida}" alt="Brasilvida">
              <div>
                <div class="consolidated-brand-kicker">Treinamentos Brasil Vida</div>
                <div class="consolidated-brand-title">Relatório consolidado de habilitações</div>
                <div class="consolidated-brand-subtitle">Padrão operacional corporativo para vencimentos e criticidade.</div>
              </div>
            </div>
            <div class="consolidated-brand-meta">
              <div class="consolidated-brand-meta-label">Emissão</div>
              <div class="consolidated-brand-meta-value">${escapeHtml(report.emitted_at || new Date().toLocaleString("pt-BR"))}</div>
            </div>
          </section>

          <header class="report-print-header report-only">
            <div class="report-brand-row">
              <img class="report-logo" src="${STATIC_ASSETS.logoBrasilVida}" alt="Brasilvida">
              <div class="report-brand-meta">
                <div class="report-doc-title">Consolidado de Habilitações</div>
                <div class="report-doc-subtitle">Relatório operacional de vencimentos por tripulante</div>
              </div>
            </div>
            <div class="report-issued-at">Emissão: ${escapeHtml(report.emitted_at || new Date().toLocaleString("pt-BR"))}</div>
          </header>

          <div class="state-note print-hide ui-block-end-sm ui-feedback" data-kind="info">
            Emissão operacional: CSV, PDF e impressão usam o mesmo recorte aplicado nesta tela.
          </div>

          ${renderReportContextStrip({
            title: "Contexto aplicado ao relatório",
            detail: "Este contexto governa leitura em tela, impressão e exportações.",
            items: [
              { label: "Tripulante", value: reportValue(reportFilters.nome) },
              { label: "Base", value: reportValue(reportFilters.base) },
              { label: "Status", value: reportValue(selectedStatusLabel || reportFilters.status) },
              { label: "Tipo", value: reportValue(selectedTipoOption?.nome || reportFilters.tipo) },
              { label: "Ordenação", value: orderLabels[reportFilters.ordenacao] || orderLabels.criticidade },
              { label: "Resultado", value: `${formatInteger(reportSummary.total_habilitacoes)} habilitações / ${formatInteger(reportSummary.total_tripulantes)} tripulantes` },
            ],
          })}

          <form class="filters-bar print-hide ui-form-toolbar ui-stack-sm ui-filter-bar" id="habilitacoes-filter-form" data-responsive-filter="bar">
            <div class="filters-bar-main ui-filter-row">
              <input type="text" name="nome" placeholder="Buscar tripulante" value="${escapeAttr(reportFilters.nome)}">
              <select name="base">
                <option value="">Base</option>
                ${reportOptions.bases
                  .map((item) => `<option value="${escapeAttr(item.nome)}" ${reportFilters.base === item.nome ? "selected" : ""}>${escapeHtml(item.nome)}</option>`)
                  .join("")}
              </select>
              <button type="submit">Aplicar</button>
              <div class="filters-bar-actions ui-form-actions ui-filter-actions">
                <button type="button" class="button-link secondary filters-toggle-btn ui-filter-toggle" id="consolidatedFiltersToggle" aria-expanded="${hasDenseFilters ? "true" : "false"}" aria-controls="consolidatedFiltersPanel">${hasDenseFilters ? "Ocultar filtros densos" : "Filtros densos"}</button>
                <a class="button-link secondary" href="#/relatorios/habilitacoes">Limpar</a>
              </div>
            </div>
            ${filterSummaryMarkup(reportFilters, filterLabels, { ordenacao: "criticidade" })}
            <div class="filters-panel ui-filter-panel ui-filter-drawer ${hasDenseFilters ? "" : "collapsed"}" id="consolidatedFiltersPanel">
              <div class="filters filters-wide ui-form-grid ui-filter-advanced">
                <select name="tipo">
                  <option value="">Tipo de habilitação</option>
                  ${reportOptions.tipos
                    .map((item) => `<option value="${item.id}" ${String(reportFilters.tipo || "") === String(item.id) ? "selected" : ""}>${escapeHtml(item.nome)}</option>`)
                    .join("")}
                </select>
                <select name="status">
                  <option value="">Status</option>
                  ${reportOptions.status
                    .map((item) => {
                      const key = typeof item === "string" ? item : item.key;
                      const label = typeof item === "string" ? item : item.label;
                      return `<option value="${escapeAttr(key)}" ${reportFilters.status === key ? "selected" : ""}>${escapeHtml(label)}</option>`;
                    })
                    .join("")}
                </select>
                <select name="ordenacao">
                  <option value="criticidade" ${reportFilters.ordenacao === "criticidade" ? "selected" : ""}>Ordenar por criticidade</option>
                  <option value="vencimento" ${reportFilters.ordenacao === "vencimento" ? "selected" : ""}>Ordenar por vencimento</option>
                </select>
              </div>
            </div>
            </form>

          <section class="summary-grid consolidated-summary-grid ui-card-grid ui-card-grid-compact ui-card-equal-height">
            <div class="summary-card ui-surface"><strong>Total de tripulantes</strong><span>${formatInteger(reportSummary.total_tripulantes)}</span></div>
            <div class="summary-card ui-surface"><strong>Total de habilitações</strong><span>${formatInteger(reportSummary.total_habilitacoes)}</span></div>
            <div class="summary-card ui-surface"><strong>Em dia</strong><span>${formatInteger(reportSummary.total_em_dia)}</span></div>
            <div class="summary-card ui-surface"><strong>A vencer até 90 dias</strong><span>${formatInteger(reportSummary.total_vencer_90)}</span></div>
            <div class="summary-card ui-surface"><strong>A vencer até 60 dias</strong><span>${formatInteger(reportSummary.total_vencer_60)}</span></div>
            <div class="summary-card ui-surface"><strong>A vencer até 30 dias</strong><span>${formatInteger(reportSummary.total_vencer_30)}</span></div>
            <div class="summary-card ui-surface"><strong>Crítico até 15 dias</strong><span>${formatInteger(reportSummary.total_critico_15)}</span></div>
            <div class="summary-card ui-surface"><strong>Vencido</strong><span>${formatInteger(reportSummary.total_vencido)}</span></div>
          </section>

          <div class="consolidated-table-wrap">
            <div class="table-wrap training-reports-table-wrap ui-table-wrap ui-table-density-compact">
              <table class="data-table consolidated-table responsive-cards">
                <thead>
                  <tr>
                    <th>Habilitação</th>
                    <th>Data de vencimento</th>
                    <th>Dias restantes</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  ${
                    reportItems.length
                      ? reportItems
                          .map(
                            (group) => `
                              <tr class="consolidated-group-row">
                                <td colspan="4">
                                  <div class="consolidated-group-header">
                                    <div>
                                      <strong>${escapeHtml(group.tripulante_nome)}</strong>
                                      <span>Base: ${escapeHtml(group.base || "-")}</span>
                                    </div>
                                    <div class="consolidated-group-meta">Função/Cargo: ${escapeHtml(group.funcao_cargo || "-")}</div>
                                  </div>
                                </td>
                              </tr>
                              ${
                                (Array.isArray(group.habilitacoes) ? group.habilitacoes : []).length
                                  ? group.habilitacoes
                                      .map(
                                        (item) => `
                                          <tr class="${["vencido", "critico_15"].includes(item.status_key) ? "consolidated-row-critical" : ""}">
                                            <td data-label="Habilitação">${escapeHtml(item.habilitacao_nome)}</td>
                                            <td data-label="Data de vencimento"><span class="date-strong">${escapeHtml(item.data_vencimento || "-")}</span></td>
                                            <td data-label="Dias restantes">${escapeHtml(item.days_remaining_label || "-")}</td>
                                            <td data-label="Status"><span class="status-pill ${trainingStatusClass(item.status_label)}${item.pulse ? " status-pill-pulse" : ""}">${escapeHtml(item.status_label || "-")}</span></td>
                                          </tr>
                                        `,
                                      )
                                      .join("")
                                  : emptyTableRowMarkup(4, {
                                      title: "Tripulante sem habilitações cadastradas.",
                                      detail: "Este é um estado vazio real; nenhum registro de habilitação foi retornado para este tripulante.",
                                      type: "structural-empty",
                                    })
                              }
                            `,
                          )
                          .join("")
                      : emptyTableRowMarkup(4, {
                          title: activeFilterCount ? "Nenhuma habilitação encontrada para os filtros atuais." : "Nenhuma habilitação disponível no consolidado.",
                          detail: activeFilterCount ? "Ajuste busca, base ou filtros densos para recuperar os registros." : "Quando houver treinamentos com vencimento, eles aparecerão nesta visão.",
                          actionHref: activeFilterCount ? "#/relatorios/habilitacoes" : "",
                          actionLabel: activeFilterCount ? "Limpar filtros" : "",
                          type: activeFilterCount ? "no-results" : "structural-empty",
                        })
                  }
                </tbody>
              </table>
            </div>
          </div>

          ${renderReportEvidencePanel({
            title: "Exportações do recorte",
            detail: reportItems.length
              ? "Use as saídas abaixo para arquivar, auditar ou analisar exatamente o mesmo resultado exibido na tabela."
              : "Sem registros no recorte atual, os arquivos exportados também ficarão vazios.",
            items: [
              { label: "Documento PDF", value: "Baixar consolidado", href: habilitacoesPdfHref },
              { label: "Visualização de impressão", value: "Abrir espelho do documento", href: habilitacoesPrintHref, target: "_blank" },
              { label: "Arquivo CSV", value: "Exportar dados tabulares", href: habilitacoesCsvHref },
            ],
          })}

          <footer class="report-print-footer report-only">
            Treinamentos Brasil Vida · Consolidado de habilitações · Emissão ${escapeHtml(report.emitted_at || new Date().toLocaleString("pt-BR"))}
          </footer>
        </section>
        </div>
      `,
      "Relatório de Habilitações",
    );

    wireResponsiveFilters("consolidatedFiltersToggle", "consolidatedFiltersPanel", "Ocultar filtros densos", "Filtros densos");

    document.getElementById("habilitacoes-filter-form")?.addEventListener("submit", (event) => {
      event.preventDefault();
      window.location.hash = buildHashHref("#/relatorios/habilitacoes", Object.fromEntries(new FormData(event.currentTarget).entries()));
    });
  } catch (error) {
    showFlash(buildErrorMessage(error), "error");
    renderShell(
      renderReportErrorState(
        "Falha ao carregar o consolidado de habilitações.",
        buildErrorMessage(error),
        "#/relatorios/habilitacoes",
        "Voltar ao relatório",
      ),
      "Relatório de Habilitações",
    );
  }
}

