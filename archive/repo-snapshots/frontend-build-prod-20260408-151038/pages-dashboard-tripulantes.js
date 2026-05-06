import {
  api,
  booleanLabel,
  buildErrorMessage,
  buildHashHref,
  capabilitySet,
  escapeAttr,
  escapeHtml,
  fileToDataUrl,
  formatDateBr,
  formatDateTimeBr,
  hashQuery,
  initialsForName,
  trainingStatusClass,
  tripulanteStatusClass,
  whatsappUrl,
  showFlash,
} from "./lib.js?v=20260408-151038";
import { renderShell } from "./shell.js?v=20260408-151038";

function resolveTripulantePhotoUrl(item) {
  const tripulanteId = Number(item?.id || 0);
  if (!tripulanteId) return "";
  if (!(item?.possui_foto || item?.photo_url || item?.foto_storage_ref)) return "";
  return `/api/v1/tripulantes/${tripulanteId}/photo`;
}

function renderTripulanteAvatar(item) {
  const photoUrl = resolveTripulantePhotoUrl(item);
  if (photoUrl) {
    return `
      <div class="avatar avatar-sm">
        <img src="${escapeAttr(photoUrl)}" alt="${escapeAttr(item.nome)}" loading="lazy" decoding="async">
      </div>
    `;
  }
  return `<div class="avatar avatar-sm"><span>${escapeHtml(initialsForName(item.nome))}</span></div>`;
}

function renderDashboardActions(capabilities) {
  const actions = [];
  if (capabilities.has("missoes:create")) actions.push('<a class="button-link secondary" href="/missoes/novo">+ Missão</a>');
  if (capabilities.has("pernoites:create")) actions.push('<a class="button-link secondary" href="/pernoites/novo">+ Pernoite</a>');
  if (capabilities.has("relatorio_produtividade:view")) actions.push('<a class="button-link secondary" href="#/relatorios/produtividade">Produtividade</a>');
  if (capabilities.has("tv_vencimentos:view")) actions.push('<a class="button-link secondary" href="/painel-tv">Painel TV</a>');
  return actions.join("");
}

function flattenCalendarWeeks(weeks) {
  if (!Array.isArray(weeks)) return [];
  return weeks.reduce((acc, week) => {
    if (Array.isArray(week)) {
      acc.push(...week);
    }
    return acc;
  }, []);
}

function wireDashboardCalendar(calendarData) {
  const detailList = document.getElementById("dashboardCalendarDetailList");
  const detailSubtitle = document.getElementById("dashboardCalendarDetailSubtitle");
  const dayButtons = [...document.querySelectorAll("[data-calendar-day]")];
  const dayMap = {};
  const flattenedDays = flattenCalendarWeeks(calendarData.weeks);

  if (!detailList || !detailSubtitle) return;

  (calendarData.weeks || []).forEach((week) => {
    week.forEach((day) => {
      dayMap[day.iso_date] = day;
    });
  });

  function renderDayDetails(isoDate) {
    const selected = dayMap[isoDate];
    if (!selected) return;
    dayButtons.forEach((button) => {
      button.classList.toggle("is-selected", button.dataset.calendarDay === isoDate);
    });
    if (!selected.items || !selected.items.length) {
      detailSubtitle.textContent = `${formatDateBr(isoDate)} · nenhum vencimento neste dia`;
      detailList.innerHTML = '<div class="empty">Nenhum vencimento cadastrado para esta data.</div>';
      return;
    }
    detailSubtitle.textContent = `${formatDateBr(isoDate)} · ${selected.items.length} vencimento(s)`;
    detailList.innerHTML = selected.items
      .map(
        (item) => `
          <article class="dashboard-calendar-detail-card ${trainingStatusClass(item.status)}">
            <div class="dashboard-calendar-detail-top">
              <span class="status-pill ${trainingStatusClass(item.status)}">${escapeHtml(formatDateBr(item.data_vencimento))}</span>
              <a class="dashboard-calendar-event-pilot" href="#/tripulantes/${item.tripulante_id}">Ver piloto</a>
            </div>
            <a class="dashboard-calendar-event-main" href="#/treinamentos/${item.id}">
              <strong>${escapeHtml(item.tripulante_nome)}</strong>
              <span>${escapeHtml(item.tipo_treinamento_nome)}</span>
              <small>${escapeHtml(item.equipamento_nome || "Sem equipamento")}</small>
            </a>
          </article>
        `,
      )
      .join("");
  }

  dayButtons.forEach((button) => {
    button.addEventListener("click", () => renderDayDetails(button.dataset.calendarDay));
  });

  const firstDueDay = flattenedDays.find((day) => Array.isArray(day.items) && day.items.length);
  const firstToday = flattenedDays.find((day) => day.is_today);
  const firstDay = firstDueDay || firstToday || flattenedDays[0];
  if (firstDay) renderDayDetails(firstDay.iso_date);
}

export async function renderDashboardPage() {
  try {
    const capabilities = capabilitySet();
    const [{ data: summary }, { data: calendar }, { data: critical }] = await Promise.all([
      api("/api/v1/dashboard/summary"),
      api("/api/v1/dashboard/calendar"),
      api("/api/v1/dashboard/critical-trainings"),
    ]);
    const dashboard = summary.dashboard || {};
    const dashboardTotals = dashboard.totals || {};
    const dashboardAlerts = dashboard.alerts || {};
    const dashboardSummary = dashboard.summary || {};
    const calendarData = calendar.calendar || {};
    const calendarWeekdays = Array.isArray(calendarData.weekday_labels) ? calendarData.weekday_labels : [];
    const calendarWeeks = Array.isArray(calendarData.weeks) ? calendarData.weeks : [];
    const flattenedCalendarDays = flattenCalendarWeeks(calendarWeeks);
    const upcomingItems = Array.isArray(calendarData.upcoming) ? calendarData.upcoming : [];
    const criticalItems = Array.isArray(critical.critical_trainings?.items) ? critical.critical_trainings.items : [];
    renderShell(
      `
        <div class="page-header">
          <div>
            <h1>Dashboard</h1>
            <p class="page-subtitle">Visão operacional diária com foco no que exige ação imediata.</p>
          </div>
          <div class="page-header-actions">
            ${renderDashboardActions(capabilities)}
          </div>
        </div>

        <div class="state-note">
          Prioridade de leitura: <strong>Vencidos</strong> -> <strong>7 dias</strong> -> <strong>30 dias</strong>.
          Use os atalhos para tratativa imediata.
        </div>

        <section class="summary-grid">
          <a class="summary-card summary-link-card" href="#/tripulantes"><strong>Tripulantes</strong><span>${dashboardTotals.tripulantes ?? 0}</span></a>
          <a class="summary-card summary-link-card" href="/equipamentos"><strong>Equipamentos ativos</strong><span>${dashboardTotals.equipamentos ?? 0}</span></a>
          <a class="summary-card summary-link-card" href="/tipos"><strong>Tipos ativos</strong><span>${dashboardTotals.tipos ?? 0}</span></a>
          <a class="summary-card summary-link-card" href="#/treinamentos"><strong>Treinamentos</strong><span>${dashboardTotals.treinamentos ?? 0}</span></a>
        </section>

        <section class="dashboard-grid">
          <div class="panel dashboard-panel">
            <div class="section-title">O que precisa de atenção</div>
            <div class="dashboard-alerts">
              <a class="alert-card alert-red" href="${buildHashHref("#/treinamentos", { status: "vencido" })}">
                <strong>Vencidos</strong>
                <span>${dashboardAlerts.vencidos ?? 0}</span>
                <span class="alert-link-text">Abrir lista</span>
              </a>
              <a class="alert-card alert-yellow" href="${buildHashHref("#/treinamentos", { periodo: "7" })}">
                <strong>Vencem em até 7 dias</strong>
                <span>${dashboardAlerts.em_7_dias ?? 0}</span>
                <span class="alert-link-text">Abrir lista</span>
              </a>
              <a class="alert-card alert-soft" href="${buildHashHref("#/treinamentos", { periodo: "30" })}">
                <strong>Vencem em até 30 dias</strong>
                <span>${dashboardAlerts.em_30_dias ?? 0}</span>
                <span class="alert-link-text">Abrir lista</span>
              </a>
            </div>
          </div>

          <div class="panel dashboard-panel">
            <div class="section-title">Visão geral dos status</div>
            <div class="dashboard-status-list">
              <a href="${buildHashHref("#/treinamentos", { status: "vencido" })}"><span>Vencidos</span><strong>${dashboardSummary.vencido ?? 0}</strong></a>
              <a href="${buildHashHref("#/treinamentos", { status: "a vencer" })}"><span>A vencer</span><strong>${dashboardSummary.a_vencer ?? 0}</strong></a>
              <a href="${buildHashHref("#/treinamentos", { status: "regular" })}"><span>Regulares</span><strong>${dashboardSummary.regular ?? 0}</strong></a>
              <a href="${buildHashHref("#/treinamentos", { status: "sem informacao" })}"><span>Sem informação</span><strong>${dashboardSummary.sem_informacao ?? 0}</strong></a>
            </div>
          </div>
        </section>

        <section class="panel dashboard-calendar-panel">
          <div class="page-header dashboard-subheader dashboard-calendar-header">
            <div>
              <h2>Calendário de vencimentos</h2>
              <p class="page-subtitle">Clique no dia ou no cartão do vencimento para abrir o treinamento e acessar o tripulante vinculado.</p>
            </div>
            <div class="dashboard-calendar-meta">
              <span class="dashboard-calendar-chip">Mês atual: <strong>${escapeHtml(calendarData.month_label || "-")}</strong></span>
              <span class="dashboard-calendar-chip">Vencimentos no mês: <strong>${calendarData.items_total ?? 0}</strong></span>
            </div>
          </div>

          <div class="dashboard-calendar-layout">
            <div class="dashboard-calendar-shell">
              <div class="dashboard-calendar-weekdays">
                ${calendarWeekdays.map((label) => `<div>${escapeHtml(label)}</div>`).join("")}
              </div>
              <div class="dashboard-calendar-grid">
                ${flattenedCalendarDays
                  .map(
                    (day) => `
                      <button
                        type="button"
                        class="dashboard-calendar-day${!day.is_current_month ? " is-muted" : ""}${day.is_today ? " is-today" : ""}${day.has_due ? " has-due" : ""}"
                        data-calendar-day="${day.iso_date}"
                        aria-label="Dia ${day.day_number} com ${day.count} vencimento(s)"
                      >
                        <span class="dashboard-calendar-day-number${day.pulse ? " pulse" : ""}">${day.day_number}</span>
                        ${day.count ? `<span class="dashboard-calendar-day-counter">${day.count}</span>` : ""}
                        <span class="dashboard-calendar-day-label">${day.count ? `${day.count} venc.` : "Sem eventos"}</span>
                        <span class="dashboard-calendar-day-dots">
                          ${(day.items || [])
                            .slice(0, 3)
                            .map((item) => `<span class="dashboard-calendar-day-dot ${trainingStatusClass(item.status)}"></span>`)
                            .join("")}
                        </span>
                      </button>
                    `,
                  )
                  .join("")}
              </div>
            </div>

            <aside class="dashboard-calendar-aside" id="dashboardCalendarDetail">
              <div class="section-title">Detalhes do dia</div>
              <p class="page-subtitle" id="dashboardCalendarDetailSubtitle">Selecione um dia para expandir os vencimentos.</p>
              <div class="dashboard-calendar-detail-list" id="dashboardCalendarDetailList">
                <div class="empty">Selecione um dia com vencimento para ver os detalhes.</div>
              </div>
              <div class="dashboard-calendar-divider"></div>
              <div class="section-title">Próximos vencimentos</div>
              <div class="dashboard-calendar-upcoming">
                ${upcomingItems
                  .map(
                    (item) => `
                      <a class="dashboard-calendar-upcoming-card" href="#/treinamentos/${item.id}">
                        <span class="status-pill ${trainingStatusClass(item.status)}">${escapeHtml(formatDateBr(item.data_vencimento))}</span>
                        <strong>${escapeHtml(item.tripulante_nome)}</strong>
                        <span>${escapeHtml(item.tipo_treinamento_nome)}</span>
                        <small>${escapeHtml(item.equipamento_nome || "Sem equipamento")}</small>
                      </a>
                    `,
                  )
                .join("") || '<div class="empty">Nenhum vencimento futuro no calendário atual.</div>'}
              </div>
            </aside>
          </div>
        </section>

        <section class="panel">
          <div class="page-header dashboard-subheader">
            <div>
              <h2>Treinamentos mais criticos</h2>
              <p class="page-subtitle">Vencidos primeiro, depois os mais próximos do vencimento.</p>
            </div>
            <a class="button-link secondary" href="#/treinamentos">Abrir lista completa</a>
          </div>

          <div class="table-wrap">
            <table class="data-table responsive-cards">
              <thead>
                <tr>
                  <th>Tripulante</th>
                  <th>Equipamento</th>
                  <th>Tipo</th>
                  <th>Vencimento</th>
                  <th>Status</th>
                  <th>Ação</th>
                </tr>
              </thead>
              <tbody>
                ${criticalItems
                  .map(
                    (item) => `
                      <tr>
                        <td data-label="Tripulante"><div class="primary-cell">${escapeHtml(item.tripulante_nome)}</div></td>
                        <td data-label="Equipamento">${escapeHtml(item.equipamento_nome || "-")}</td>
                        <td data-label="Tipo">${escapeHtml(item.tipo_treinamento_nome)}</td>
                        <td data-label="Vencimento"><span class="date-strong">${escapeHtml(formatDateBr(item.data_vencimento))}</span></td>
                        <td data-label="Status"><span class="status-pill ${trainingStatusClass(item.status)}">${escapeHtml(item.status)}</span></td>
                        <td class="actions" data-label="Ação"><a href="#/treinamentos/${item.id}">Abrir</a></td>
                      </tr>
                    `,
                  )
                  .join("") || '<tr><td colspan="6" class="empty">Ainda não há treinamentos suficientes para mostrar aqui.</td></tr>'}
              </tbody>
            </table>
          </div>
        </section>
      `,
      "Dashboard",
    );
    wireDashboardCalendar(calendarData);
  } catch (error) {
    showFlash(buildErrorMessage(error), "error");
    renderShell("<section class='panel'><div class='empty'>Falha ao carregar dashboard.</div></section>", "Dashboard");
  }
}

export async function renderTripulantesListPage(viewMode = "cadastro") {
  try {
    const filters = Object.fromEntries(hashQuery().entries());
    const [listResponse, optionsResponse] = await Promise.all([
      api(`/api/v1/tripulantes?${new URLSearchParams(filters).toString()}`),
      api("/api/v1/tripulantes/options"),
    ]);
    const data = listResponse.data || {};
    const optionsPayload = optionsResponse.data?.options || {};
    const options = {
      status: Array.isArray(optionsPayload.status) ? optionsPayload.status : [],
      bases: Array.isArray(optionsPayload.bases) ? optionsPayload.bases : [],
      funcoes: Array.isArray(optionsPayload.funcoes) ? optionsPayload.funcoes : [],
      categorias: Array.isArray(optionsPayload.categorias) ? optionsPayload.categorias : [],
    };
    const items = Array.isArray(data.items) ? data.items : [];
    const dataFilters = data.filters || {};
    const paginationPayload = data.pagination || {};
    const pagination = {
      page: Number(paginationPayload.page) || 1,
      pages: Number(paginationPayload.pages) || 1,
      total: Number(paginationPayload.total) || items.length,
      has_prev: Boolean(paginationPayload.has_prev),
      has_next: Boolean(paginationPayload.has_next),
    };
    const capabilities = capabilitySet();
    const isReportMode = viewMode === "report";
    const baseHash = isReportMode ? "#/relatorios/individual" : "#/tripulantes";
    const pageTitle = isReportMode ? "Relatório individual" : "Tripulantes";
    const pageSubtitle = isReportMode
      ? "Selecione um tripulante para abrir o relatório individual de treinamentos."
      : "Consulte a equipe, filtre rapidamente e abra o historico individual quando precisar.";
    const canOpenReport = capabilities.has("relatorio_individual:view");
    const canOpenProductivity = capabilities.has("relatorio_produtividade:view");

    renderShell(
      `
        <div class="page-header">
          <div>
            <h1>${pageTitle}</h1>
            <p class="page-subtitle">${pageSubtitle}</p>
          </div>
          ${!isReportMode && capabilities.has("tripulantes:create") ? '<a class="button-link" href="#/tripulantes/new">Adicionar tripulante</a>' : ""}
        </div>

        <section class="panel">
          <form class="filters" id="tripulantes-filters-form">
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
            <button type="submit">Aplicar filtros</button>
            <a class="button-link secondary" href="${baseHash}">Limpar filtros</a>
          </form>

          <div class="table-wrap">
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
                        <td class="actions" data-label="Ações">
                          ${canOpenReport ? `<a href="/tripulantes/${item.id}/relatorio">Relatório</a>` : ""}
                          ${canOpenProductivity ? `<a href="/produtividade/tripulantes/${item.id}">Produtividade</a>` : ""}
                          ${whatsappUrl(item.telefone) ? `<a href="${whatsappUrl(item.telefone)}" target="_blank" rel="noopener noreferrer">WhatsApp</a>` : ""}
                          ${!isReportMode && capabilities.has("tripulantes:edit") ? `<a href="#/tripulantes/${item.id}">Editar</a>` : ""}
                          ${!isReportMode && capabilities.has("tripulantes_file:view") ? `<a href="#/tripulantes/${item.id}">File</a>` : ""}
                          ${
                            !isReportMode && capabilities.has("tripulantes:delete")
                              ? `<button type="button" class="link-danger tripulante-delete" data-tripulante-id="${item.id}">Excluir</button>`
                              : ""
                          }
                        </td>
                      </tr>
                    `,
                  )
                  .join("") || '<tr><td colspan="5" class="empty">Nenhum tripulante encontrado com esses filtros.</td></tr>'}
              </tbody>
            </table>
          </div>

          <div class="pagination-bar">
            <div class="pagination-meta">Página ${pagination.page} de ${pagination.pages} · ${pagination.total} registros</div>
            <div class="pagination-actions">
              ${pagination.has_prev ? `<a class="button-link secondary" href="${buildHashHref(baseHash, { ...filters, page: pagination.page - 1 })}">Anterior</a>` : ""}
              ${pagination.has_next ? `<a class="button-link secondary" href="${buildHashHref(baseHash, { ...filters, page: pagination.page + 1 })}">Próxima</a>` : ""}
            </div>
          </div>
        </section>
      `,
      pageTitle,
    );

    document.getElementById("tripulantes-filters-form")?.addEventListener("submit", (event) => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      window.location.hash = buildHashHref(baseHash, Object.fromEntries(form.entries()));
    });

    document.querySelectorAll(".tripulante-delete").forEach((button) => {
      button.addEventListener("click", async () => {
        if (!window.confirm("Excluir este tripulante?")) return;
        try {
          await api(`/api/v1/tripulantes/${button.dataset.tripulanteId}`, { method: "DELETE" });
          showFlash("Tripulante removido com sucesso.", "success");
        } catch (error) {
          showFlash(buildErrorMessage(error), "error");
        }
        window.location.reload();
      });
    });
  } catch (error) {
    showFlash(buildErrorMessage(error), "error");
    renderShell("<section class='panel'><div class='empty'>Falha ao carregar tripulantes.</div></section>", "Tripulantes");
  }
}

export async function renderRelatorioIndividualPage() {
  return renderTripulantesListPage("report");
}

function renderTripulanteFilesSection(tripulanteId, files) {
  if (!tripulanteId) {
    return `
      <section class="panel" style="margin-top: 1rem;">
        <div class="hint">Salve o tripulante primeiro para habilitar anexos PDF.</div>
      </section>
    `;
  }

  return `
    <section class="panel" style="margin-top: 1rem;">
      <div class="page-header" style="margin-bottom: 12px;">
        <div>
          <h2 style="margin:0;">Aba File</h2>
          <p class="page-subtitle" style="margin-top:4px;">Documentos PDF vinculados ao tripulante.</p>
        </div>
      </div>

      <form id="tripulante-file-form" class="filters filters-wide" style="margin-bottom: 12px;">
        <input type="text" name="tipo_documento" placeholder="Tipo de documento">
        <input type="file" name="arquivo_pdf" accept="application/pdf" required>
        <button type="submit">Anexar PDF</button>
      </form>

      <div class="table-wrap" style="margin-top: 12px;">
        <table class="data-table responsive-cards">
          <thead>
            <tr>
              <th>Arquivo</th>
              <th>Status</th>
              <th>Enviado em</th>
              <th>Ações</th>
            </tr>
          </thead>
          <tbody>
            ${
              files
                .map(
                  (item) => `
                    <tr>
                      <td data-label="Arquivo">
                        <div class="primary-cell">${escapeHtml(item.nome_original)}</div>
                        <div class="secondary-cell">${escapeHtml(item.tipo_documento || item.mime_type || "application/pdf")}</div>
                      </td>
                      <td data-label="Status"><span class="status-pill ${item.status === "ativo" ? "status-green" : "status-gray"}">${escapeHtml(item.status_label || item.status || "-")}</span></td>
                      <td data-label="Enviado em">${escapeHtml(formatDateTimeBr(item.enviado_em))}</td>
                      <td class="actions" data-label="Ações">
                        <a href="${item.links.self}" target="_blank" rel="noopener noreferrer">Visualizar</a>
                        <a href="${item.links.download}" target="_blank" rel="noopener noreferrer">Baixar</a>
                        <button type="button" class="link-danger tripulante-file-delete" data-file-id="${item.id}">Excluir</button>
                      </td>
                    </tr>
                  `,
                )
                .join("") || '<tr><td colspan="4" class="empty">Nenhum PDF anexado a este tripulante.</td></tr>'
            }
          </tbody>
        </table>
      </div>
    </section>
  `;
}

export async function renderTripulanteFormPage(tripulanteId = null) {
  try {
    const detailResponse = tripulanteId ? api(`/api/v1/tripulantes/${tripulanteId}`) : Promise.resolve({ data: { tripulante: null } });
    const detailPayload = await detailResponse;
    const tripulante = detailPayload.data.tripulante;
    const [optionsResponse, filesPayload] = await Promise.all([
      api(`/api/v1/tripulantes/options${tripulante?.base ? `?base=${encodeURIComponent(tripulante.base)}` : ""}`),
      tripulanteId ? api(`/api/v1/tripulantes/${tripulanteId}/files`) : Promise.resolve({ data: { items: [] } }),
    ]);
    const files = filesPayload.data.items || [];
    const optionsPayload = optionsResponse.data?.options || {};
    const options = {
      status: Array.isArray(optionsPayload.status) ? optionsPayload.status : [],
      bases: Array.isArray(optionsPayload.bases) ? optionsPayload.bases : [],
      funcoes: Array.isArray(optionsPayload.funcoes) ? optionsPayload.funcoes : [],
      categorias: Array.isArray(optionsPayload.categorias) ? optionsPayload.categorias : [],
    };
    const photoUrl = resolveTripulantePhotoUrl(tripulante) || (tripulanteId ? `/api/v1/tripulantes/${tripulanteId}/photo` : "");
    const capabilities = capabilitySet();

    renderShell(
      `
        <div class="page-header">
          <h1>${tripulanteId ? "Atualizar dados do tripulante" : "Cadastrar novo tripulante"}</h1>
        </div>

        <form id="tripulante-form" class="form-grid">
          <label>Nome<input type="text" name="nome" value="${escapeAttr(tripulante?.nome || "")}" required></label>
          <label>CPF<input type="text" name="cpf" id="tripulanteCpf" value="${escapeAttr(tripulante?.cpf || "")}" inputmode="numeric" maxlength="14" placeholder="000.000.000-00" required></label>
          <label>Código ANAC<input type="text" name="licenca_anac" id="tripulanteAnac" value="${escapeAttr(tripulante?.licenca_anac || "")}" inputmode="numeric" maxlength="6" placeholder="000000" required></label>
          <label>E-mail<input type="email" name="email" value="${escapeAttr(tripulante?.email || "")}" maxlength="254" placeholder="tripulante@empresa.com"></label>
          <label>Telefone / WhatsApp<input type="text" name="telefone" id="tripulanteTelefone" value="${escapeAttr(tripulante?.telefone || "")}" inputmode="tel" maxlength="16" placeholder="(91) 99999-9999"></label>
          <label>
            Base
            <select name="base" required>
              <option value="">Selecione</option>
              ${options.bases
                .map((item) => `<option value="${escapeAttr(item.nome)}" ${tripulante?.base === item.nome ? "selected" : ""}>${escapeHtml(item.uf ? `${item.nome} / ${item.uf}` : item.nome)}</option>`)
                .join("")}
            </select>
          </label>
          <label>
            Status
            <select name="status" required>
              <option value="">Selecione</option>
              ${options.status
                .map((item) => `<option value="${escapeAttr(item)}" ${tripulante?.status === item ? "selected" : ""}>${escapeHtml(item)}</option>`)
                .join("")}
            </select>
          </label>
          <label>
            Função operacional
            <select name="funcao_operacional" required>
              ${options.funcoes
                .map((item) => `<option value="${escapeAttr(item)}" ${tripulante?.funcao_operacional === item || (!tripulante && item === "outro") ? "selected" : ""}>${escapeHtml(item)}</option>`)
                .join("")}
            </select>
          </label>
          <label>
            Categoria operacional
            <select name="categoria_operacional" required>
              ${options.categorias
                .map((item) => `<option value="${escapeAttr(item)}" ${tripulante?.categoria_operacional === item || (!tripulante && item === "N/A") ? "selected" : ""}>${escapeHtml(item)}</option>`)
                .join("")}
            </select>
            <span class="field-help">
              <strong>Legenda de porte:</strong><br>
              A - C525 ou aeronave do mesmo porte.<br>
              B - LRJ serie 30, C560, LRJ45, WW, G100 ou aeronave do mesmo porte.
            </span>
          </label>
          <section class="full-width flags-section">
            <div class="flags-section-header">
              <h2>Elegibilidade operacional</h2>
              <p>Defina rapidamente os indicadores que impactam calculo, escala e produtividade.</p>
            </div>
            <div class="flags-grid">
              <label class="checkbox-field"><span class="checkbox-label-group"><span class="checkbox-title">Tripulante ativo</span><span class="checkbox-description">Controla disponibilidade geral no sistema.</span></span><span class="toggle-switch"><input type="checkbox" name="ativo" ${!tripulante || tripulante.ativo ? "checked" : ""}><span class="toggle-slider" aria-hidden="true"></span><span class="toggle-text">${!tripulante || tripulante.ativo ? "Ativo" : "Inativo"}</span></span></label>
              <label class="checkbox-field"><span class="checkbox-label-group"><span class="checkbox-title">SDEA ativo</span><span class="checkbox-description">Aplica adicional mensal de idioma quando habilitado.</span></span><span class="toggle-switch"><input type="checkbox" name="sdea_ativo" ${tripulante?.sdea_ativo ? "checked" : ""}><span class="toggle-slider" aria-hidden="true"></span><span class="toggle-text">${tripulante?.sdea_ativo ? "Ativo" : "Inativo"}</span></span></label>
              <label class="checkbox-field"><span class="checkbox-label-group"><span class="checkbox-title">Instrutor designado</span><span class="checkbox-description">Considera adicional fixo de instrutoria na competencia.</span></span><span class="toggle-switch"><input type="checkbox" name="instrutor_ativo" ${tripulante?.instrutor_ativo ? "checked" : ""}><span class="toggle-slider" aria-hidden="true"></span><span class="toggle-text">${tripulante?.instrutor_ativo ? "Ativo" : "Inativo"}</span></span></label>
              <label class="checkbox-field"><span class="checkbox-label-group"><span class="checkbox-title">Checador designado</span><span class="checkbox-description">Considera adicional fixo de checagem na competencia.</span></span><span class="toggle-switch"><input type="checkbox" name="checador_ativo" ${tripulante?.checador_ativo ? "checked" : ""}><span class="toggle-slider" aria-hidden="true"></span><span class="toggle-text">${tripulante?.checador_ativo ? "Ativo" : "Inativo"}</span></span></label>
              <label class="checkbox-field"><span class="checkbox-label-group"><span class="checkbox-title">Elegivel para adicional excepcional</span><span class="checkbox-description">Permite aplicar valor excepcional parametrizado ou manual.</span></span><span class="toggle-switch"><input type="checkbox" name="elegivel_adicional_excepcional" ${tripulante?.elegivel_adicional_excepcional ? "checked" : ""}><span class="toggle-slider" aria-hidden="true"></span><span class="toggle-text">${tripulante?.elegivel_adicional_excepcional ? "Ativo" : "Inativo"}</span></span></label>
            </div>
          </section>
          <div class="full-width tripulante-photo-field">
            <div class="tripulante-photo-preview-card">
              <div class="tripulante-photo-preview" id="tripulantePhotoPreview">
                ${photoUrl ? `<img src="${escapeAttr(photoUrl)}" alt="${escapeAttr(tripulante?.nome || "Tripulante")}">` : `<span>${escapeHtml(initialsForName(tripulante?.nome || ""))}</span>`}
              </div>
              <div class="tripulante-photo-meta">
                <div class="checkbox-title">Foto do tripulante</div>
                <div class="checkbox-description">Envie JPG ou PNG. A imagem será exibida no cadastro, relatório e gestão de bases.</div>
              </div>
            </div>
            <div class="tripulante-photo-actions">
              <input type="file" id="tripulantePhotoInput" accept="image/png,image/jpeg">
              <button type="button" class="button-link secondary" id="tripulantePhotoUpload" ${tripulanteId ? "" : "disabled"}>Enviar foto</button>
              <button type="button" class="button-link secondary" id="tripulantePhotoRemove" ${tripulanteId ? "" : "disabled"}>Remover foto</button>
            </div>
          </div>
          <label class="full-width">Observações<textarea name="observacoes">${escapeHtml(tripulante?.observacoes || "")}</textarea></label>
          <div class="form-actions full-width">
            <button type="submit">Salvar alterações</button>
            ${tripulanteId && capabilities.has("tripulantes:delete") ? '<button type="button" class="button-link secondary" id="tripulanteDeleteButton">Excluir tripulante</button>' : ""}
            <a class="button-link secondary" href="#/tripulantes">Voltar sem salvar</a>
          </div>
        </form>

        ${renderTripulanteFilesSection(tripulanteId, files)}
      `,
      tripulanteId ? "Editar Tripulante" : "Novo Tripulante",
    );

    const photoInput = document.getElementById("tripulantePhotoInput");
    const photoPreview = document.getElementById("tripulantePhotoPreview");
    const nameInput = document.querySelector("input[name='nome']");
    const cpfInput = document.getElementById("tripulanteCpf");
    const anacInput = document.getElementById("tripulanteAnac");
    const phoneInput = document.getElementById("tripulanteTelefone");

    function renderPhotoPreview(src = "") {
      photoPreview.innerHTML = src
        ? `<img src="${escapeAttr(src)}" alt="${escapeAttr(nameInput?.value || "Tripulante")}">`
        : `<span>${escapeHtml(initialsForName(nameInput?.value || ""))}</span>`;
    }

    function formatCpf(value) {
      const digits = String(value || "").replace(/\D/g, "").slice(0, 11);
      if (digits.length <= 3) return digits;
      if (digits.length <= 6) return `${digits.slice(0, 3)}.${digits.slice(3)}`;
      if (digits.length <= 9) return `${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6)}`;
      return `${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6, 9)}-${digits.slice(9)}`;
    }

    function formatPhone(value) {
      const digits = String(value || "").replace(/\D/g, "").slice(0, 11);
      if (digits.length <= 2) return digits ? `(${digits}` : "";
      if (digits.length <= 6) return `(${digits.slice(0, 2)}) ${digits.slice(2)}`;
      if (digits.length <= 10) return `(${digits.slice(0, 2)}) ${digits.slice(2, 6)}-${digits.slice(6)}`;
      return `(${digits.slice(0, 2)}) ${digits.slice(2, 7)}-${digits.slice(7)}`;
    }

    cpfInput?.addEventListener("input", () => {
      cpfInput.value = formatCpf(cpfInput.value);
    });
    anacInput?.addEventListener("input", () => {
      anacInput.value = String(anacInput.value || "").replace(/\D/g, "").slice(0, 6);
    });
    phoneInput?.addEventListener("input", () => {
      phoneInput.value = formatPhone(phoneInput.value);
    });
    nameInput?.addEventListener("input", () => {
      if (!photoPreview.querySelector("img")) renderPhotoPreview("");
    });
    document.querySelectorAll(".toggle-switch input[type='checkbox']").forEach((input) => {
      input.addEventListener("change", () => {
        const textNode = input.closest(".toggle-switch")?.querySelector(".toggle-text");
        if (textNode) textNode.textContent = input.checked ? "Ativo" : "Inativo";
      });
    });

    document.getElementById("tripulante-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      const payload = Object.fromEntries(form.entries());
      ["ativo", "sdea_ativo", "instrutor_ativo", "checador_ativo", "elegivel_adicional_excepcional"].forEach((key) => {
        payload[key] = form.has(key);
      });
      try {
        const result = await api(tripulanteId ? `/api/v1/tripulantes/${tripulanteId}` : "/api/v1/tripulantes", {
          method: tripulanteId ? "PUT" : "POST",
          json: payload,
        });
        showFlash("Tripulante salvo com sucesso.", "success");
        const nextId = Number(result.data.tripulante.id);
        if (Number(tripulanteId || 0) === nextId) {
          await renderTripulanteFormPage(nextId);
        } else {
          window.location.hash = `#/tripulantes/${nextId}`;
        }
      } catch (error) {
        showFlash(buildErrorMessage(error), "error");
        window.location.reload();
      }
    });

    document.getElementById("tripulanteDeleteButton")?.addEventListener("click", async () => {
      if (!window.confirm("Excluir este tripulante?")) return;
      try {
        await api(`/api/v1/tripulantes/${tripulanteId}`, { method: "DELETE" });
        showFlash("Tripulante removido com sucesso.", "success");
        window.location.hash = "#/tripulantes";
      } catch (error) {
        showFlash(buildErrorMessage(error), "error");
        window.location.reload();
      }
    });

    photoInput?.addEventListener("change", async () => {
      const file = photoInput.files?.[0];
      if (!file) return;
      if (!["image/png", "image/jpeg"].includes(file.type)) {
        showFlash("Envie uma imagem JPG ou PNG.", "error");
        window.location.reload();
        return;
      }
      renderPhotoPreview(await fileToDataUrl(file));
    });

    document.getElementById("tripulantePhotoUpload")?.addEventListener("click", async () => {
      const file = photoInput?.files?.[0];
      if (!tripulanteId || !file) {
        showFlash("Selecione uma foto antes de enviar.", "error");
        window.location.reload();
        return;
      }
      try {
        await api(`/api/v1/tripulantes/${tripulanteId}/photo`, {
          method: "POST",
          json: { foto_base64: await fileToDataUrl(file) },
        });
        showFlash("Foto atualizada com sucesso.", "success");
      } catch (error) {
        showFlash(buildErrorMessage(error), "error");
      }
      window.location.reload();
    });

    document.getElementById("tripulantePhotoRemove")?.addEventListener("click", async () => {
      if (!tripulanteId) return;
      try {
        await api(`/api/v1/tripulantes/${tripulanteId}/photo`, { method: "DELETE" });
        showFlash("Foto removida com sucesso.", "success");
      } catch (error) {
        showFlash(buildErrorMessage(error), "error");
      }
      window.location.reload();
    });

    document.getElementById("tripulante-file-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await api(`/api/v1/tripulantes/${tripulanteId}/files`, {
          method: "POST",
          body: new FormData(event.currentTarget),
        });
        showFlash("PDF anexado com sucesso.", "success");
      } catch (error) {
        showFlash(buildErrorMessage(error), "error");
      }
      window.location.reload();
    });

    document.querySelectorAll(".tripulante-file-delete").forEach((button) => {
      button.addEventListener("click", async () => {
        if (!window.confirm("Excluir este documento PDF?")) return;
        try {
          await api(`/api/v1/tripulantes/${tripulanteId}/files/${button.dataset.fileId}`, { method: "DELETE" });
          showFlash("Documento removido com sucesso.", "success");
        } catch (error) {
          showFlash(buildErrorMessage(error), "error");
        }
        window.location.reload();
      });
    });
  } catch (error) {
    showFlash(buildErrorMessage(error), "error");
    renderShell("<section class='panel'><div class='empty'>Falha ao carregar formulario de tripulante.</div></section>", "Tripulantes");
  }
}




