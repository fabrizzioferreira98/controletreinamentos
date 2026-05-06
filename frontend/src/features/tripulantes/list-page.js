import {
  api,
  booleanLabel,
  buildErrorMessage,
  buildHashHref,
  capabilitySet,
  confirmAction,
  countActiveFilters,
  emptyTableRowMarkup,
  escapeAttr,
  escapeHtml,
  filterSummaryMarkup,
  hashQuery,
  renderInlineFeedback,
  showFlash,
  tripulanteStatusClass,
  whatsappUrl,
  withActionBusy,
  wireResponsiveFilterPanel,
} from "../../lib.js";
import { renderShell } from "../../shell.js";
import {
  renderTripulanteAvatar,
  wireTripulantePhotoFallbacks,
} from "./avatar.js";
import {
  adaptTripulantesListPayload,
  adaptTripulantesOptionsPayload,
} from "./data-adapters.js";

const INDIVIDUAL_REPORT_DOCUMENT_BOUNDARY = "ssr_document_read_model";
const INDIVIDUAL_REPORT_PDF_BOUNDARY = "ssr_document_pdf";

function individualReportDocumentHref(tripulanteId) {
  return `/tripulantes/${encodeURIComponent(tripulanteId)}/relatorio`;
}

function individualReportPdfHref(tripulanteId) {
  return `${individualReportDocumentHref(tripulanteId)}/export.pdf`;
}

export async function renderTripulantesListPage(viewMode = "cadastro") {
  try {
    const filters = Object.fromEntries(hashQuery().entries());
    const isReportMode = viewMode === "report";
    const baseHash = isReportMode ? "#/relatorios/individual" : "#/tripulantes";
    const pageTitle = isReportMode ? "Relatório individual" : "Tripulantes";
    const pageSubtitle = isReportMode
      ? "Seletor SPA canonico: escolha um tripulante para abrir o documento individual oficial, baixar PDF ou consultar evidências."
      : "Consulte a equipe, filtre rapidamente e abra o historico individual quando precisar.";
    if (isReportMode) {
      renderShell(
        `
          <section class="panel report-shell report-state-panel">
            <div class="feedback info" role="status" aria-live="polite">
              <strong>Carregando seletor de relatório individual</strong>
              <span>Aplicando filtros antes de abrir o documento individual oficial, PDF ou evid&ecirc;ncias.</span>
            </div>
          </section>
        `,
        pageTitle,
      );
    }
    const [listResponse, optionsResponse] = await Promise.all([
      api(`/api/v1/tripulantes?${new URLSearchParams(filters).toString()}`),
      api("/api/v1/tripulantes/options"),
    ]);
    const data = adaptTripulantesListPayload(listResponse.data);
    const options = adaptTripulantesOptionsPayload(optionsResponse.data);
    const items = data.items;
    const dataFilters = data.filters;
    const paginationPayload = data.pagination;
    const pagination = {
      page: Number(paginationPayload.page) || 1,
      pages: Number(paginationPayload.pages) || 1,
      total: Number(paginationPayload.total) || items.length,
      has_prev: Boolean(paginationPayload.has_prev),
      has_next: Boolean(paginationPayload.has_next),
    };
    const capabilities = capabilitySet();
    const canOpenReport = capabilities.has("relatorio_individual:view");
    const activeFilterCount = countActiveFilters(dataFilters);
    const tripulantesFilterLabels = {
      nome: "Nome",
      status: "Status",
      base: "Base",
      funcao: "Função",
      categoria: "Categoria",
      ativo: "Ativo",
    };
    const hasDenseTripulantesFilters = Boolean(dataFilters.funcao || dataFilters.categoria || dataFilters.ativo);

    renderShell(
      `
        <div class="${isReportMode ? "report-page-shell" : "tripulantes-page-shell priority-page-surface ui-page-shell ui-stack"}">
        <div class="page-header ${isReportMode ? "report-shell-header" : "priority-page-header ui-page-header ui-surface"}">
          <div>
            <h1>${pageTitle}</h1>
            <p class="page-subtitle">${pageSubtitle}</p>
          </div>
          ${
            isReportMode
              ? `
                <div class="page-header-actions report-export-actions">
                  <a class="button-link secondary" href="#/relatorios/habilitacoes">Consolidado de habilitações</a>
                </div>
              `
              : (!isReportMode && capabilities.has("tripulantes:create") ? '<a class="button-link" href="#/tripulantes/new">Adicionar tripulante</a>' : "")
          }
        </div>

        <section class="panel ${isReportMode ? "report-shell" : "tripulantes-list-panel ui-surface ui-stack"}">
          ${
            isReportMode
              ? `
                <section class="report-context-strip">
                  <div class="report-context-intro">
                    <strong>Seletor canonico do relatório individual</strong>
                    <span>Os filtros limitam quem aparece na lista; o documento individual e o PDF usam o cadastro completo do tripulante escolhido.</span>
                  </div>
                  <div class="report-context-items">
                    <div class="report-context-item"><span>Tripulantes encontrados</span><strong>${pagination.total}</strong></div>
                    <div class="report-context-item"><span>Busca</span><strong>${escapeHtml(dataFilters.nome || "Todos")}</strong></div>
                    <div class="report-context-item"><span>Base</span><strong>${escapeHtml(dataFilters.base || "Todas")}</strong></div>
                    <div class="report-context-item"><span>Status</span><strong>${escapeHtml(dataFilters.status || "Todos")}</strong></div>
                    <div class="report-context-item"><span>Saída</span><strong>Documento oficial, PDF e evid&ecirc;ncias</strong></div>
                  </div>
                </section>
              `
              : ""
          }
          <form class="filters-bar ui-form-toolbar ui-stack-sm" id="tripulantes-filters-form" data-responsive-filter="bar">
            <div class="filters-bar-main ui-filter-row">
              <input type="text" name="nome" placeholder="Buscar por nome" value="${escapeAttr(dataFilters.nome || "")}">
              <select name="status">
                <option value="">Status</option>
                ${options.status
                  .map((item) => `<option value="${escapeAttr(item)}" ${dataFilters.status === item ? "selected" : ""}>${escapeHtml(item)}</option>`)
                  .join("")}
              </select>
              <select name="base">
                <option value="">Base</option>
                ${options.bases
                  .map((item) => `<option value="${escapeAttr(item.nome)}" ${dataFilters.base === item.nome ? "selected" : ""}>${escapeHtml(item.uf ? `${item.nome} / ${item.uf}` : item.nome)}</option>`)
                  .join("")}
              </select>
              <button type="submit">Aplicar</button>
              <div class="filters-bar-actions ui-form-actions ui-filter-actions">
                <button type="button" class="button-link secondary filters-toggle-btn ui-filter-toggle" id="tripulantesDenseFiltersToggle" aria-expanded="${hasDenseTripulantesFilters ? "true" : "false"}" aria-controls="tripulantesDenseFiltersPanel">${hasDenseTripulantesFilters ? "Ocultar filtros densos" : "Filtros densos"}</button>
                <a class="button-link secondary" href="${baseHash}">Limpar</a>
              </div>
            </div>
            ${filterSummaryMarkup(dataFilters, tripulantesFilterLabels)}
            <div class="filters-panel ui-filter-panel ui-filter-drawer ${hasDenseTripulantesFilters ? "" : "collapsed"}" id="tripulantesDenseFiltersPanel" ${hasDenseTripulantesFilters ? "" : "hidden"}>
              <div class="filters ui-form-grid ui-filter-advanced">
                <select name="funcao">
                  <option value="">Função operacional</option>
                  ${options.funcoes
                    .map((item) => `<option value="${escapeAttr(item)}" ${dataFilters.funcao === item ? "selected" : ""}>${escapeHtml(item)}</option>`)
                    .join("")}
                </select>
                <select name="categoria">
                  <option value="">Categoria</option>
                  ${options.categorias
                    .map((item) => `<option value="${escapeAttr(item)}" ${dataFilters.categoria === item ? "selected" : ""}>${escapeHtml(item)}</option>`)
                    .join("")}
                </select>
                <select name="ativo">
                  <option value="">Ativo/Inativo</option>
                  <option value="1" ${dataFilters.ativo === "1" ? "selected" : ""}>Ativo</option>
                  <option value="0" ${dataFilters.ativo === "0" ? "selected" : ""}>Inativo</option>
                </select>
              </div>
            </div>
          </form>
          <div id="tripulantes-action-feedback" aria-live="polite"></div>

          <div class="table-wrap tripulantes-table-wrap ui-table-wrap ui-table-density-compact">
            <table class="data-table responsive-cards">
              <thead>
                <tr>
                  <th>Nome</th>
                  <th>CPF / Código ANAC</th>
                  <th>Base</th>
                  <th>Status / Perfil</th>
                  <th>Ações</th>
                </tr>
              </thead>
              <tbody>
                ${items
                  .map(
                    (item) => `
                      <tr>
                        <td data-label="Nome">
                          <div class="tripulante-inline">
                            ${renderTripulanteAvatar(item)}
                            <div class="primary-cell">${escapeHtml(item.nome)}</div>
                          </div>
                        </td>
                        <td data-label="CPF / Código ANAC">
                          <div>${escapeHtml(item.cpf)}</div>
                          <div class="secondary-cell">Código ANAC: ${escapeHtml(item.licenca_anac || "-")}</div>
                          ${item.telefone ? `<div class="secondary-cell">WhatsApp: ${escapeHtml(item.telefone)}</div>` : ""}
                        </td>
                        <td data-label="Base">${escapeHtml(item.base || "-")}</td>
                        <td data-label="Status / Perfil">
                          <span class="status-pill ${tripulanteStatusClass(item.status)}">${escapeHtml(item.status || "-")}</span>
                          <div class="secondary-cell">${escapeHtml(item.funcao_operacional || "-")} · Categoria ${escapeHtml(item.categoria_operacional || "-")}</div>
                          <div class="secondary-cell">
                            ${item.ativo ? "Ativo" : "Inativo"} ·
                            SDEA ${booleanLabel(item.sdea_ativo)} ·
                            Instrutor ${booleanLabel(item.instrutor_ativo)} ·
                            Checador ${booleanLabel(item.checador_ativo)}
                          </div>
                        </td>
                        <td class="actions ui-table-actions" data-label="Ações">
                          ${canOpenReport ? `<a href="${individualReportDocumentHref(item.id)}" data-boundary="${INDIVIDUAL_REPORT_DOCUMENT_BOUNDARY}" aria-label="Abrir documento individual de ${escapeAttr(item.nome)}">${isReportMode ? "Abrir documento" : "Documento"}</a>` : ""}
                          ${canOpenReport && isReportMode ? `<a href="${individualReportPdfHref(item.id)}" data-boundary="${INDIVIDUAL_REPORT_PDF_BOUNDARY}" aria-label="Baixar PDF do relatório individual de ${escapeAttr(item.nome)}">Baixar PDF</a>` : ""}
                          ${isReportMode && capabilities.has("tripulantes_file:view") ? `<a href="#/tripulantes/${item.id}">Evidências</a>` : ""}
                          ${whatsappUrl(item.telefone) ? `<a href="${whatsappUrl(item.telefone)}" target="_blank" rel="noopener noreferrer">WhatsApp</a>` : ""}
                          ${!isReportMode && capabilities.has("tripulantes:edit") ? `<a href="#/tripulantes/${item.id}">Editar</a>` : ""}
                          ${!isReportMode && capabilities.has("tripulantes_file:view") ? `<a href="#/tripulantes/${item.id}">Documentos</a>` : ""}
                          ${
                            !isReportMode && capabilities.has("tripulantes:delete")
                              ? `<button type="button" class="link-danger tripulante-delete" data-tripulante-id="${item.id}" data-tripulante-name="${escapeAttr(item.nome)}">Excluir</button>`
                              : ""
                          }
                        </td>
                      </tr>
                    `,
                  )
                  .join("") || emptyTableRowMarkup(5, {
                    title: activeFilterCount ? "Nenhum tripulante encontrado com os filtros atuais." : "Nenhum tripulante cadastrado.",
                    detail: activeFilterCount ? "Revise busca, status, base ou filtros densos para ampliar a lista." : "Cadastre o primeiro tripulante para iniciar a operação.",
                    actionHref: activeFilterCount ? baseHash : (!isReportMode && capabilities.has("tripulantes:create") ? "#/tripulantes/new" : ""),
                    actionLabel: activeFilterCount ? "Limpar filtros" : (!isReportMode && capabilities.has("tripulantes:create") ? "Adicionar tripulante" : ""),
                    type: activeFilterCount ? "no-results" : "structural-empty",
                  })}
              </tbody>
            </table>
          </div>

          <div class="pagination-bar ui-cluster">
            <div class="pagination-meta">Página ${pagination.page} de ${pagination.pages} · ${pagination.total} registros</div>
            <div class="pagination-actions">
              ${pagination.has_prev ? `<a class="button-link secondary" href="${buildHashHref(baseHash, { ...filters, page: pagination.page - 1 })}">Anterior</a>` : ""}
              ${pagination.has_next ? `<a class="button-link secondary" href="${buildHashHref(baseHash, { ...filters, page: pagination.page + 1 })}">Próxima</a>` : ""}
            </div>
          </div>
        </section>
        </div>
      `,
      pageTitle,
    );
    wireTripulantePhotoFallbacks();

    document.getElementById("tripulantes-filters-form")?.addEventListener("submit", (event) => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      window.location.hash = buildHashHref(baseHash, Object.fromEntries(form.entries()));
    });
    wireResponsiveFilterPanel("tripulantesDenseFiltersToggle", "tripulantesDenseFiltersPanel", "Ocultar filtros densos", "Filtros densos");

    document.querySelectorAll(".tripulante-delete").forEach((button) => {
      button.addEventListener("click", async () => {
        const feedbackEl = document.getElementById("tripulantes-action-feedback");
        if (!confirmAction({
          title: "Remover tripulante da lista?",
          subject: button.dataset.tripulanteName || "Tripulante selecionado",
          consequence: "Se houver vínculos históricos, o registro pode ser inativado em vez de excluído.",
        })) return;
        await withActionBusy(button, "Removendo...", async () => {
          try {
            const { data } = await api(`/api/v1/tripulantes/${button.dataset.tripulanteId}`, { method: "DELETE" });
            showFlash(
              data?.operation === "inactivated"
                ? "Tripulante inativado porque existem vínculos históricos."
                : "Tripulante excluído com sucesso.",
              "success",
            );
            await renderTripulantesListPage(viewMode);
          } catch (error) {
            renderInlineFeedback(feedbackEl, buildErrorMessage(error), "error");
          }
        });
      });
    });
  } catch (error) {
    showFlash(buildErrorMessage(error), "error");
    renderShell(
      viewMode === "report"
        ? "<section class='panel report-shell report-state-panel'><div class='empty'>Falha ao carregar seletor de relatório individual. Tente limpar filtros ou voltar ao menu de relatórios.</div></section>"
        : "<section class='panel'><div class='empty'>Falha ao carregar tripulantes.</div></section>",
      viewMode === "report" ? "Relatório individual" : "Tripulantes",
    );
  }
}

