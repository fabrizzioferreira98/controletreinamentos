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
  fileToDataUrl,
  formatDateBr,
  formatDateTimeBr,
  formatFileSize,
  filterSummaryMarkup,
  hashQuery,
  initialsForName,
  renderInlineFeedback,
  trainingStatusClass,
  tripulanteStatusClass,
  whatsappUrl,
  showFlash,
  withActionBusy,
} from "./lib.js?v=20260422-095412";
import { renderShell } from "./shell.js?v=20260422-095412";

function resolveTripulantePhotoUrl(item) {
  const tripulanteId = Number(item?.id || 0);
  if (!tripulanteId) return "";
  const hasConfirmedPhoto = Boolean(item?.possui_foto || item?.foto_storage_ref || item?.photo_url);
  if (!hasConfirmedPhoto) return "";
  return item?.photo_url || `/api/v1/tripulantes/${tripulanteId}/photo`;
}

function renderPhotoImage({ src, name, size = "sm", stateTarget = "" }) {
  const initials = initialsForName(name || "");
  const targetAttr = stateTarget ? ` data-photo-state-target="${escapeAttr(stateTarget)}"` : "";
  return `
    <div class="avatar avatar-${escapeAttr(size)}" data-photo-state="loaded" title="Foto carregada">
      <img
        class="tripulante-photo-img"
        src="${escapeAttr(src)}"
        alt="${escapeAttr(name || "Tripulante")}"
        loading="lazy"
        decoding="async"
        data-photo-fallback="initials"
        data-initials="${escapeAttr(initials)}"${targetAttr}
      >
    </div>
  `;
}

function renderInitialsAvatar(name, size = "sm", state = "empty") {
  const title = state === "unavailable" ? "Foto indisponivel" : "Sem foto vinculada";
  return `
    <div class="avatar avatar-${escapeAttr(size)}" data-photo-state="${escapeAttr(state)}" title="${escapeAttr(title)}">
      <span>${escapeHtml(initialsForName(name || ""))}</span>
    </div>
  `;
}

function renderTripulanteAvatar(item) {
  const photoUrl = resolveTripulantePhotoUrl(item);
  if (photoUrl) return renderPhotoImage({ src: photoUrl, name: item.nome, size: "sm" });
  return renderInitialsAvatar(item.nome, "sm", "empty");
}

function wireTripulantePhotoFallbacks(root = document) {
  root.querySelectorAll("img[data-photo-fallback='initials']").forEach((image) => {
    if (image.dataset.photoFallbackBound === "true") return;
    image.dataset.photoFallbackBound = "true";
    image.addEventListener("error", () => {
      const wrapper = image.closest(".avatar, .tripulante-photo-preview");
      const stateTarget = image.dataset.photoStateTarget
        ? document.getElementById(image.dataset.photoStateTarget)
        : null;
      if (wrapper) {
        wrapper.dataset.photoState = "unavailable";
        wrapper.title = "Foto indisponivel";
        wrapper.innerHTML = `<span>${escapeHtml(image.dataset.initials || "?")}</span>`;
      }
      if (stateTarget) {
        stateTarget.textContent = "Foto indisponivel. A referencia existe, mas o arquivo nao carregou.";
        stateTarget.dataset.kind = "warning";
      }
    }, { once: true });
    image.addEventListener("load", () => {
      const wrapper = image.closest(".avatar, .tripulante-photo-preview");
      const stateTarget = image.dataset.photoStateTarget
        ? document.getElementById(image.dataset.photoStateTarget)
        : null;
      if (wrapper) {
        wrapper.dataset.photoState = "loaded";
        wrapper.title = "Foto carregada";
      }
      if (stateTarget && !stateTarget.dataset.userUploadState) {
        stateTarget.textContent = "Foto carregada com sucesso.";
        stateTarget.dataset.kind = "success";
      }
    }, { once: true });
  });
}

function renderDashboardActions(capabilities) {
  const registerActions = [];
  const monitorActions = [];
  if (capabilities.has("missoes:create")) registerActions.push('<a class="button-link secondary" href="/missoes/novo">+ Missão</a>');
  if (capabilities.has("pernoites:create")) registerActions.push('<a class="button-link secondary" href="/pernoites/novo">+ Pernoite</a>');
  if (capabilities.has("relatorio_produtividade:view")) monitorActions.push('<a class="button-link secondary" href="#/relatorios/produtividade">Produtividade</a>');
  if (capabilities.has("tv_vencimentos:view")) monitorActions.push('<a class="button-link secondary" href="/painel-tv">Painel TV</a>');
  if (!registerActions.length && !monitorActions.length) return "";
  return `
    <div class="dashboard-action-groups">
      ${
        registerActions.length
          ? `<div class="dashboard-action-group"><span>Registrar</span><div>${registerActions.join("")}</div></div>`
          : ""
      }
      ${
        monitorActions.length
          ? `<div class="dashboard-action-group"><span>Consultar/Monitorar</span><div>${monitorActions.join("")}</div></div>`
          : ""
      }
    </div>
  `;
}

function assertObject(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`Resposta inesperada em ${label}.`);
  }
  return value;
}

function assertArray(value, label) {
  if (!Array.isArray(value)) {
    throw new Error(`Resposta inesperada em ${label}.`);
  }
  return value;
}

function adaptDashboardSummary(payload) {
  const dashboard = assertObject(payload?.dashboard, "dashboard.summary");
  return {
    totals: assertObject(dashboard.totals, "dashboard.totals"),
    alerts: assertObject(dashboard.alerts, "dashboard.alerts"),
    summary: assertObject(dashboard.summary, "dashboard.summary"),
  };
}

function adaptDashboardCalendar(payload) {
  const calendar = assertObject(payload?.calendar, "dashboard.calendar");
  return {
    ...calendar,
    weekday_labels: assertArray(calendar.weekday_labels, "calendar.weekday_labels"),
    weeks: assertArray(calendar.weeks, "calendar.weeks"),
    upcoming: assertArray(calendar.upcoming, "calendar.upcoming"),
  };
}

function adaptDashboardCriticalTrainings(payload) {
  const criticalTrainings = assertObject(payload?.critical_trainings, "dashboard.critical_trainings");
  return assertArray(criticalTrainings.items, "critical_trainings.items");
}

function dashboardBlockFromResult(result, label, adapter, fallback) {
  if (result.status !== "fulfilled") {
    return { data: fallback, error: `${label}: ${buildErrorMessage(result.reason)}` };
  }
  try {
    return { data: adapter(result.value.data), error: "" };
  } catch (error) {
    return { data: fallback, error: `${label}: ${buildErrorMessage(error)}` };
  }
}

function renderDashboardPartialFeedback(errors) {
  const items = errors.filter(Boolean);
  if (!items.length) return "";
  return `
    <div class="dashboard-partial-feedback">
      ${items.map((item) => `<div class="flash warning" role="alert" aria-live="assertive">${escapeHtml(item)}</div>`).join("")}
    </div>
  `;
}

function renderDashboardWidgetFeedback(error, fallbackMessage = "") {
  const message = error || fallbackMessage;
  if (!message) return "";
  return `<div class="flash warning dashboard-widget-feedback" role="alert" aria-live="assertive">${escapeHtml(message)}</div>`;
}

function renderDashboardWidgetEmpty(title, detail = "", actionHref = "", actionLabel = "") {
  return `
    <div class="empty dashboard-widget-empty">
      <strong>${escapeHtml(title)}</strong>
      ${detail ? `<span>${escapeHtml(detail)}</span>` : ""}
      ${actionHref && actionLabel ? `<a class="button-link secondary" href="${escapeAttr(actionHref)}">${escapeHtml(actionLabel)}</a>` : ""}
    </div>
  `;
}

function renderDashboardCriticalRows(items, hasError) {
  if (hasError) {
    return emptyTableRowMarkup(6, {
      title: "Fila crítica indisponível.",
      detail: "Não foi possível carregar os treinamentos que exigem ação agora. Os demais blocos continuam disponíveis.",
      actionHref: "#/treinamentos",
      actionLabel: "Abrir lista completa",
      type: "partial-unavailable",
    });
  }
  return items
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
    .join("") || emptyTableRowMarkup(6, {
      title: "Nenhum treinamento crítico agora.",
      detail: "Não há vencidos ou vencimentos prioritários suficientes para formar uma fila crítica.",
      actionHref: "#/treinamentos",
      actionLabel: "Abrir lista completa",
      type: "structural-empty",
    });
}

function renderDashboardCompactAgenda(items, hasError) {
  if (hasError) {
    return renderDashboardWidgetEmpty(
      "Agenda indisponível.",
      "Não foi possível carregar os próximos vencimentos do calendário.",
      "#/treinamentos",
      "Abrir treinamentos",
    );
  }
  return `
    <div class="dashboard-agenda-list">
      ${
        items.length
          ? items
              .slice(0, 6)
              .map(
                (item) => `
                  <a class="dashboard-agenda-item" href="#/treinamentos/${item.id}">
                    <span class="status-pill ${trainingStatusClass(item.status)}">${escapeHtml(formatDateBr(item.data_vencimento))}</span>
                    <strong>${escapeHtml(item.tripulante_nome)}</strong>
                    <span>${escapeHtml(item.tipo_treinamento_nome)}</span>
                    <small>${escapeHtml(item.equipamento_nome || "Sem equipamento")}</small>
                  </a>
                `,
              )
              .join("")
          : renderDashboardWidgetEmpty(
              "Nenhum vencimento futuro no calendário atual.",
              "A agenda compacta será preenchida assim que houver vencimentos previstos.",
            )
      }
    </div>
  `;
}

function renderDashboardLoadingMarkup(capabilities) {
  return `
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
      A fila crítica abaixo é o ponto principal de tratativa diária.
    </div>

    <section class="dashboard-priority-grid">
      <div class="panel dashboard-panel">
        <div class="section-title">Ação imediata</div>
        <div class="flash loading dashboard-widget-feedback" role="status" aria-live="polite">Carregando alertas operacionais...</div>
      </div>
      <div class="panel dashboard-panel dashboard-critical-panel">
        <div class="section-title">Fila crítica</div>
        <div class="flash loading dashboard-widget-feedback" role="status" aria-live="polite">Carregando treinamentos críticos...</div>
      </div>
    </section>

    <section class="panel dashboard-calendar-panel">
      <div class="section-title">Calendário de vencimentos</div>
      <div class="flash loading dashboard-widget-feedback" role="status" aria-live="polite">Carregando agenda e grade mensal...</div>
    </section>

    <section class="dashboard-secondary-grid">
      <div class="panel dashboard-panel">
        <div class="section-title">Visão geral dos status</div>
        <div class="flash loading dashboard-widget-feedback" role="status" aria-live="polite">Carregando resumo de status...</div>
      </div>
      <div class="panel dashboard-panel dashboard-base-panel">
        <div class="section-title">Base operacional</div>
        <div class="flash loading dashboard-widget-feedback" role="status" aria-live="polite">Carregando base cadastral...</div>
      </div>
    </section>
  `;
}

function adaptTripulantesListPayload(payload) {
  const data = assertObject(payload, "tripulantes.list");
  return {
    items: assertArray(data.items, "tripulantes.items"),
    filters: assertObject(data.filters, "tripulantes.filters"),
    pagination: assertObject(data.pagination, "tripulantes.pagination"),
  };
}

function adaptTripulantesOptionsPayload(payload) {
  const options = assertObject(payload?.options, "tripulantes.options");
  return {
    status: assertArray(options.status, "tripulantes.options.status"),
    bases: assertArray(options.bases, "tripulantes.options.bases"),
    funcoes: assertArray(options.funcoes, "tripulantes.options.funcoes"),
    categorias: assertArray(options.categorias, "tripulantes.options.categorias"),
  };
}

function optionsContainBase(options, baseName) {
  const target = String(baseName || "").trim();
  if (!target) return true;
  return options.bases.some((item) => String(item?.nome || "").trim() === target);
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
    renderShell(renderDashboardLoadingMarkup(capabilities), "Dashboard");
    const [summaryResult, calendarResult, criticalResult] = await Promise.allSettled([
      api("/api/v1/dashboard/summary"),
      api("/api/v1/dashboard/calendar"),
      api("/api/v1/dashboard/critical-trainings"),
    ]);
    const summaryBlock = dashboardBlockFromResult(summaryResult, "Resumo", adaptDashboardSummary, { totals: {}, alerts: {}, summary: {} });
    const calendarBlock = dashboardBlockFromResult(calendarResult, "Calendário", adaptDashboardCalendar, { weekday_labels: [], weeks: [], upcoming: [] });
    const criticalBlock = dashboardBlockFromResult(criticalResult, "Treinamentos críticos", adaptDashboardCriticalTrainings, []);
    const dashboardTotals = summaryBlock.data.totals;
    const dashboardAlerts = summaryBlock.data.alerts;
    const dashboardSummary = summaryBlock.data.summary;
    const calendarData = calendarBlock.data;
    const calendarWeekdays = calendarData.weekday_labels;
    const calendarWeeks = calendarData.weeks;
    const flattenedCalendarDays = flattenCalendarWeeks(calendarWeeks);
    const upcomingItems = calendarData.upcoming;
    const criticalItems = criticalBlock.data;
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
          A fila crítica abaixo é o ponto principal de tratativa diária.
        </div>

        <section class="dashboard-priority-grid">
          <div class="panel dashboard-panel">
            <div class="dashboard-widget-head">
              <div>
                <div class="section-title">Ação imediata</div>
                <p class="page-subtitle">Alertas que abrem a lista filtrada para tratativa.</p>
              </div>
            </div>
            ${renderDashboardWidgetFeedback(summaryBlock.error, "")}
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

          <div class="panel dashboard-panel dashboard-critical-panel">
            <div class="page-header dashboard-subheader">
              <div>
                <h2>Fila crítica</h2>
                <p class="page-subtitle">Vencidos primeiro, depois os mais próximos do vencimento.</p>
              </div>
              <a class="button-link secondary" href="#/treinamentos">Abrir lista completa</a>
            </div>
            ${renderDashboardWidgetFeedback(criticalBlock.error, "")}

            <div class="table-wrap">
              <table class="data-table responsive-cards dashboard-critical-table">
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
                  ${renderDashboardCriticalRows(criticalItems, Boolean(criticalBlock.error))}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        <section class="panel dashboard-calendar-panel">
          <div class="page-header dashboard-subheader dashboard-calendar-header">
            <div>
              <h2>Calendário de vencimentos</h2>
              <p class="page-subtitle">Agenda compacta primeiro; grade mensal como visão exploratória.</p>
            </div>
            <div class="dashboard-calendar-meta">
              <span class="dashboard-calendar-chip">Mês atual: <strong>${escapeHtml(calendarData.month_label || "-")}</strong></span>
              <span class="dashboard-calendar-chip">Vencimentos no mês: <strong>${calendarData.items_total ?? 0}</strong></span>
            </div>
          </div>
          ${renderDashboardWidgetFeedback(calendarBlock.error, "")}

          <section class="dashboard-compact-agenda">
            <div class="dashboard-widget-head">
              <div>
                <div class="section-title">Agenda compacta</div>
                <p class="page-subtitle">Próximos vencimentos para leitura rápida antes da grade mensal.</p>
              </div>
            </div>
            ${renderDashboardCompactAgenda(upcomingItems, Boolean(calendarBlock.error))}
          </section>

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
            </aside>
          </div>
        </section>

        <section class="dashboard-secondary-grid">
          <div class="panel dashboard-panel">
            <div class="section-title">Visão geral dos status</div>
            ${renderDashboardWidgetFeedback(summaryBlock.error, "")}
            <div class="dashboard-status-list">
              <a href="${buildHashHref("#/treinamentos", { status: "vencido" })}"><span>Vencidos</span><strong>${dashboardSummary.vencido ?? 0}</strong></a>
              <a href="${buildHashHref("#/treinamentos", { status: "a vencer" })}"><span>A vencer</span><strong>${dashboardSummary.a_vencer ?? 0}</strong></a>
              <a href="${buildHashHref("#/treinamentos", { status: "regular" })}"><span>Regulares</span><strong>${dashboardSummary.regular ?? 0}</strong></a>
              <a href="${buildHashHref("#/treinamentos", { status: "sem informacao" })}"><span>Sem informação</span><strong>${dashboardSummary.sem_informacao ?? 0}</strong></a>
            </div>
          </div>

          <div class="panel dashboard-panel dashboard-base-panel">
            <div class="section-title">Base operacional</div>
            ${renderDashboardWidgetFeedback(summaryBlock.error, "")}
            <section class="summary-grid dashboard-secondary-summary">
              <a class="summary-card summary-link-card" href="#/tripulantes"><strong>Tripulantes</strong><span>${dashboardTotals.tripulantes ?? 0}</span></a>
              <a class="summary-card summary-link-card" href="/equipamentos"><strong>Equipamentos ativos</strong><span>${dashboardTotals.equipamentos ?? 0}</span></a>
              <a class="summary-card summary-link-card" href="/tipos"><strong>Tipos ativos</strong><span>${dashboardTotals.tipos ?? 0}</span></a>
              <a class="summary-card summary-link-card" href="#/treinamentos"><strong>Treinamentos</strong><span>${dashboardTotals.treinamentos ?? 0}</span></a>
            </section>
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
    const isReportMode = viewMode === "report";
    const baseHash = isReportMode ? "#/relatorios/individual" : "#/tripulantes";
    const pageTitle = isReportMode ? "Relatório individual" : "Tripulantes";
    const pageSubtitle = isReportMode
      ? "Selecione um tripulante para abrir relatório, PDF e evidências vinculadas."
      : "Consulte a equipe, filtre rapidamente e abra o historico individual quando precisar.";
    if (isReportMode) {
      renderShell(
        `
          <section class="panel report-shell report-state-panel">
            <div class="feedback info" role="status" aria-live="polite">
              <strong>Carregando seletor de relatório individual</strong>
              <span>Aplicando filtros para manter contexto antes de abrir visualização, PDF ou produtividade.</span>
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
    const canOpenProductivity = capabilities.has("relatorio_produtividade:view");
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
        <div class="page-header ${isReportMode ? "report-shell-header" : ""}">
          <div>
            <h1>${pageTitle}</h1>
            <p class="page-subtitle">${pageSubtitle}</p>
          </div>
          ${
            isReportMode
              ? `
                <div class="page-header-actions report-export-actions">
                  <a class="button-link secondary" href="#/relatorios/habilitacoes">Consolidado de habilitações</a>
                  <a class="button-link secondary" href="#/relatorios/produtividade">Consolidado de produtividade</a>
                </div>
              `
              : (!isReportMode && capabilities.has("tripulantes:create") ? '<a class="button-link" href="#/tripulantes/new">Adicionar tripulante</a>' : "")
          }
        </div>

        <section class="panel ${isReportMode ? "report-shell" : ""}">
          ${
            isReportMode
              ? `
                <section class="report-context-strip">
                  <div class="report-context-intro">
                    <strong>Contexto do seletor individual</strong>
                    <span>Os filtros limitam quem aparece na lista; a visualização e o PDF continuam usando o cadastro completo do tripulante escolhido.</span>
                  </div>
                  <div class="report-context-items">
                    <div class="report-context-item"><span>Tripulantes encontrados</span><strong>${pagination.total}</strong></div>
                    <div class="report-context-item"><span>Busca</span><strong>${escapeHtml(dataFilters.nome || "Todos")}</strong></div>
                    <div class="report-context-item"><span>Base</span><strong>${escapeHtml(dataFilters.base || "Todas")}</strong></div>
                    <div class="report-context-item"><span>Status</span><strong>${escapeHtml(dataFilters.status || "Todos")}</strong></div>
                    <div class="report-context-item"><span>Saída</span><strong>Tela, PDF e produtividade individual</strong></div>
                  </div>
                </section>
              `
              : ""
          }
          <form class="filters-bar" id="tripulantes-filters-form">
            <div class="filters-bar-main">
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
              <div class="filters-bar-actions">
                <button type="button" class="button-link secondary filters-toggle-btn" id="tripulantesDenseFiltersToggle" aria-expanded="${hasDenseTripulantesFilters ? "true" : "false"}" aria-controls="tripulantesDenseFiltersPanel">${hasDenseTripulantesFilters ? "Ocultar filtros densos" : "Filtros densos"}</button>
                <a class="button-link secondary" href="${baseHash}">Limpar</a>
              </div>
            </div>
            ${filterSummaryMarkup(dataFilters, tripulantesFilterLabels)}
            <div class="filters-panel ${hasDenseTripulantesFilters ? "" : "collapsed"}" id="tripulantesDenseFiltersPanel" ${hasDenseTripulantesFilters ? "" : "hidden"}>
              <div class="filters">
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
                          ${canOpenReport ? `<a href="/tripulantes/${item.id}/relatorio">${isReportMode ? "Visualizar" : "Relatório"}</a>` : ""}
                          ${canOpenReport && isReportMode ? `<a href="/tripulantes/${item.id}/relatorio/export.pdf">PDF</a>` : ""}
                          ${isReportMode && capabilities.has("tripulantes_file:view") ? `<a href="#/tripulantes/${item.id}">Evidências</a>` : ""}
                          ${canOpenProductivity ? `<a href="/produtividade/tripulantes/${item.id}">Produtividade</a>` : ""}
                          ${whatsappUrl(item.telefone) ? `<a href="${whatsappUrl(item.telefone)}" target="_blank" rel="noopener noreferrer">WhatsApp</a>` : ""}
                          ${!isReportMode && capabilities.has("tripulantes:edit") ? `<a href="#/tripulantes/${item.id}">Editar</a>` : ""}
                          ${!isReportMode && capabilities.has("tripulantes_file:view") ? `<a href="#/tripulantes/${item.id}">File</a>` : ""}
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
    wireTripulantePhotoFallbacks();

    document.getElementById("tripulantes-filters-form")?.addEventListener("submit", (event) => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      window.location.hash = buildHashHref(baseHash, Object.fromEntries(form.entries()));
    });
    document.getElementById("tripulantesDenseFiltersToggle")?.addEventListener("click", (event) => {
      const panel = document.getElementById("tripulantesDenseFiltersPanel");
      if (!panel) return;
      panel.classList.toggle("collapsed");
      const expanded = !panel.classList.contains("collapsed");
      panel.hidden = !expanded;
      event.currentTarget.setAttribute("aria-expanded", String(expanded));
      event.currentTarget.textContent = expanded ? "Ocultar filtros densos" : "Filtros densos";
    });

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

export async function renderRelatorioIndividualPage() {
  return renderTripulantesListPage("report");
}

function renderTripulanteFilesSection(tripulanteId, files, capabilities = capabilitySet()) {
  if (!tripulanteId) {
    return `
      <section class="panel" style="margin-top: 1rem;">
        <div class="hint">Salve o tripulante primeiro para habilitar anexos PDF.</div>
      </section>
    `;
  }
  const activeFiles = files.filter((item) => item.status !== "removido");
  const primaryFile = activeFiles.find((item) => item.status === "ativo") || activeFiles[0] || null;
  const canReplace = capabilities.has("tripulantes_file:replace") && activeFiles.some((item) => item.status === "ativo");
  const statusClass = (status) => {
    if (status === "ativo") return "status-green";
    if (status === "substituido") return "status-yellow";
    if (status === "removido") return "status-dark";
    return "status-gray";
  };
  const previewMarkup = primaryFile
    ? `
      <div class="document-preview-card" id="tripulanteDocumentPreview" data-preview-state="ready">
        <div class="document-preview-frame">
          <iframe
            id="tripulanteDocumentPreviewFrame"
            src="${escapeAttr(primaryFile.links?.self || "")}"
            title="Preview do documento ${escapeAttr(primaryFile.nome_original)}"
            loading="lazy"
          ></iframe>
        </div>
        <div class="document-preview-meta">
          <span class="eyebrow">Preview persistido</span>
          <h3 id="tripulanteDocumentPreviewName">${escapeHtml(primaryFile.nome_original)}</h3>
          <p id="tripulanteDocumentPreviewDescription">
            ${escapeHtml(primaryFile.tipo_documento || primaryFile.mime_type || "application/pdf")} ·
            ${escapeHtml(formatFileSize(primaryFile.tamanho_bytes))} ·
            ${escapeHtml(primaryFile.status_label || primaryFile.status || "-")}
          </p>
          <div class="document-preview-actions">
            <a id="tripulanteDocumentPreviewOpen" href="${escapeAttr(primaryFile.links?.self || "#")}" target="_blank" rel="noopener noreferrer">Abrir em nova aba</a>
            <a id="tripulanteDocumentPreviewDownload" href="${escapeAttr(primaryFile.links?.download || "#")}" target="_blank" rel="noopener noreferrer">Baixar PDF</a>
          </div>
          <div class="upload-state compact" id="tripulanteDocumentPreviewState" aria-live="polite" data-kind="ready">
            Arquivo salvo e disponivel para visualizacao.
          </div>
        </div>
      </div>
    `
    : `
      <div class="document-preview-card document-preview-empty" id="tripulanteDocumentPreview" data-preview-state="empty">
        <div class="document-preview-fallback">
          <strong>Nenhum PDF persistido para preview.</strong>
          <span>Quando um documento for anexado, o preview e os metadados aparecem aqui antes da tabela historica.</span>
        </div>
      </div>
    `;

  return `
    <section class="panel entity-document-panel" style="margin-top: 1rem;">
      <div class="page-header" style="margin-bottom: 12px;">
        <div>
          <h2 style="margin:0;">Aba File</h2>
          <p class="page-subtitle" style="margin-top:4px;">Documentos PDF vinculados ao tripulante.</p>
        </div>
      </div>

      <form id="tripulante-file-form" class="filters filters-wide document-upload-form" style="margin-bottom: 12px;">
        <label>
          Tipo de documento
          <input type="text" name="tipo_documento" placeholder="Ex.: CMA, contrato, comprovante">
        </label>
        ${
          canReplace
            ? `
              <label>
                Persistencia
                <select name="substitui_arquivo_id" id="tripulanteFileReplaceSelect" aria-describedby="tripulanteFileReplaceFeedback">
                  <option value="">Novo documento</option>
                  ${activeFiles
                    .filter((item) => item.status === "ativo")
                    .map((item) => `<option value="${escapeAttr(item.id)}">Substituir: ${escapeHtml(item.nome_original)}</option>`)
                    .join("")}
                </select>
                <span class="field-feedback" id="tripulanteFileReplaceFeedback" aria-live="polite"></span>
              </label>
            `
            : ""
        }
        <label class="document-upload-input">
          PDF do tripulante
          <input type="file" name="arquivo_pdf" id="tripulanteFileInput" accept="application/pdf" required aria-describedby="tripulanteFileUploadState">
          <span class="field-help">Limite por arquivo: 20 MB. Apenas PDF.</span>
        </label>
        <button type="submit" id="tripulanteFileSubmit">Anexar PDF</button>
      </form>
      <div class="upload-state" id="tripulanteFileUploadState" aria-live="polite">Nenhum PDF selecionado.</div>
      ${previewMarkup}

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
                        <div class="secondary-cell">${escapeHtml(item.tipo_documento || item.mime_type || "application/pdf")} · ${escapeHtml(formatFileSize(item.tamanho_bytes))}</div>
                      </td>
                      <td data-label="Status"><span class="status-pill ${statusClass(item.status)}">${escapeHtml(item.status_label || item.status || "-")}</span></td>
                      <td data-label="Enviado em">${escapeHtml(formatDateTimeBr(item.enviado_em))}</td>
                      <td class="actions" data-label="Ações">
                        ${
                          item.status !== "removido"
                            ? `
                              <button
                                type="button"
                                class="button-link secondary tripulante-file-preview"
                                data-preview-url="${escapeAttr(item.links?.self || "")}"
                                data-download-url="${escapeAttr(item.links?.download || "")}"
                                data-file-name="${escapeAttr(item.nome_original)}"
                                data-file-meta="${escapeAttr(`${item.tipo_documento || item.mime_type || "application/pdf"} · ${formatFileSize(item.tamanho_bytes)} · ${item.status_label || item.status || "-"}`)}"
                              >Preview</button>
                              <a href="${item.links.self}" target="_blank" rel="noopener noreferrer">Visualizar</a>
                              <a href="${item.links.download}" target="_blank" rel="noopener noreferrer">Baixar</a>
                            `
                            : ""
                        }
                        ${
                          item.substitui_arquivo_id
                            ? `<span class="secondary-cell">Substitui #${escapeHtml(item.substitui_arquivo_id)}</span>`
                            : ""
                        }
                        ${
                          item.motivo_status
                            ? `<span class="secondary-cell">${escapeHtml(item.motivo_status)}</span>`
                            : ""
                        }
                        ${item.status !== "removido" ? `<button type="button" class="link-danger tripulante-file-delete" data-file-id="${item.id}" data-file-name="${escapeAttr(item.nome_original)}">Excluir</button>` : ""}
                      </td>
                    </tr>
                  `,
                )
                .join("") || '<tr><td colspan="4" class="empty">Nenhum PDF anexado a este tripulante. Use o upload acima quando houver documento comprobatório.</td></tr>'
            }
          </tbody>
        </table>
      </div>
    </section>
  `;
}

export async function renderTripulanteFormPage(tripulanteId = null) {
  try {
    const detailPromise = tripulanteId ? api(`/api/v1/tripulantes/${tripulanteId}`) : Promise.resolve({ data: { tripulante: null } });
    const filesPromise = tripulanteId ? api(`/api/v1/tripulantes/${tripulanteId}/files`) : Promise.resolve({ data: { items: [] } });
    const defaultOptionsPromise = api("/api/v1/tripulantes/options");
    const [detailPayload, filesPayload, defaultOptionsResponse] = await Promise.all([
      detailPromise,
      filesPromise,
      defaultOptionsPromise,
    ]);
    const tripulante = detailPayload.data.tripulante;
    const files = assertArray(filesPayload.data?.items, "tripulantes.files");
    let options = adaptTripulantesOptionsPayload(defaultOptionsResponse.data);
    if (tripulante?.base && !optionsContainBase(options, tripulante.base)) {
      const selectedBaseOptionsResponse = await api(`/api/v1/tripulantes/options?base=${encodeURIComponent(tripulante.base)}`);
      options = adaptTripulantesOptionsPayload(selectedBaseOptionsResponse.data);
    }
    const photoUrl = resolveTripulantePhotoUrl(tripulante);
    const photoStateMessage = photoUrl
      ? "Foto vinculada ao tripulante."
      : "Sem foto vinculada.";
    const capabilities = capabilitySet();

    renderShell(
      `
        <div class="page-header entity-detail-header">
          <div>
            <h1>${tripulanteId ? "Atualizar dados do tripulante" : "Cadastrar novo tripulante"}</h1>
            <p class="page-subtitle">${tripulanteId ? "Detalhe e edição compartilham o mesmo contexto operacional." : "Crie o cadastro e depois anexe documentos PDF."}</p>
            <div class="entity-status-row">
              <span class="status-pill ${tripulanteStatusClass(tripulante?.status || "ativo")}">${escapeHtml(tripulante?.status || "novo cadastro")}</span>
              <span class="status-pill ${tripulante?.ativo === false ? "status-gray" : "status-green"}">${tripulante?.ativo === false ? "Indisponível na operação" : "Disponível para operação"}</span>
              ${tripulanteId ? `<span class="status-pill status-gray">${files.length} PDF${files.length === 1 ? "" : "s"} anexado${files.length === 1 ? "" : "s"}</span>` : ""}
            </div>
          </div>
          <div class="page-header-actions">
            <a class="button-link secondary" href="#/tripulantes">Voltar para a lista</a>
          </div>
        </div>

        <div id="tripulante-form-feedback" aria-live="polite"></div>

        <form id="tripulante-form" class="form-grid entity-form-grid" novalidate>
          <section class="form-section entity-form-section">
            <div class="form-section-header">
              <h2>Identificação</h2>
              <p>Dados usados para localizar, validar e acionar o tripulante.</p>
              <div class="section-feedback" id="tripulanteIdentitySectionFeedback" aria-live="polite"></div>
            </div>
            <div class="form-grid form-grid-compact">
              <label>Nome<input type="text" name="nome" id="tripulanteNome" value="${escapeAttr(tripulante?.nome || "")}" required aria-describedby="tripulanteNomeFeedback"><span class="field-feedback" id="tripulanteNomeFeedback" aria-live="polite"></span></label>
              <label>CPF<input type="text" name="cpf" id="tripulanteCpf" value="${escapeAttr(tripulante?.cpf || "")}" inputmode="numeric" maxlength="14" placeholder="000.000.000-00" required aria-describedby="tripulanteCpfFeedback"><span class="field-feedback" id="tripulanteCpfFeedback" aria-live="polite"></span></label>
              <label>Código ANAC<input type="text" name="licenca_anac" id="tripulanteAnac" value="${escapeAttr(tripulante?.licenca_anac || "")}" inputmode="numeric" maxlength="6" placeholder="000000" required aria-describedby="tripulanteAnacFeedback"><span class="field-feedback" id="tripulanteAnacFeedback" aria-live="polite"></span></label>
              <label>E-mail<input type="email" name="email" id="tripulanteEmail" value="${escapeAttr(tripulante?.email || "")}" maxlength="254" placeholder="tripulante@empresa.com" aria-describedby="tripulanteEmailFeedback"><span class="field-feedback" id="tripulanteEmailFeedback" aria-live="polite"></span></label>
              <label>Telefone / WhatsApp<input type="text" name="telefone" id="tripulanteTelefone" value="${escapeAttr(tripulante?.telefone || "")}" inputmode="tel" maxlength="16" placeholder="(91) 99999-9999" aria-describedby="tripulanteTelefoneFeedback"><span class="field-feedback" id="tripulanteTelefoneFeedback" aria-live="polite"></span></label>
            </div>
          </section>
          <section class="form-section entity-form-section">
            <div class="form-section-header">
              <h2>Operação</h2>
              <p>Status, base e função que impactam escala, relatórios e produtividade.</p>
              <div class="section-feedback" id="tripulanteOperationSectionFeedback" aria-live="polite"></div>
            </div>
            <div class="form-grid form-grid-compact">
          <label>
            Base
            <select name="base" id="tripulanteBase" required aria-describedby="tripulanteBaseFeedback">
              <option value="">Selecione</option>
              ${options.bases
                .map((item) => `<option value="${escapeAttr(item.nome)}" ${tripulante?.base === item.nome ? "selected" : ""}>${escapeHtml(item.uf ? `${item.nome} / ${item.uf}` : item.nome)}</option>`)
                .join("")}
            </select>
            <span class="field-feedback" id="tripulanteBaseFeedback" aria-live="polite"></span>
          </label>
          <label>
            Status
            <select name="status" id="tripulanteStatus" required aria-describedby="tripulanteStatusFeedback">
              <option value="">Selecione</option>
              ${options.status
                .map((item) => `<option value="${escapeAttr(item)}" ${tripulante?.status === item ? "selected" : ""}>${escapeHtml(item)}</option>`)
                .join("")}
            </select>
            <span class="field-feedback" id="tripulanteStatusFeedback" aria-live="polite"></span>
          </label>
          <label>
            Função operacional
            <select name="funcao_operacional" id="tripulanteFuncao" required aria-describedby="tripulanteFuncaoFeedback">
              ${options.funcoes
                .map((item) => `<option value="${escapeAttr(item)}" ${tripulante?.funcao_operacional === item || (!tripulante && item === "outro") ? "selected" : ""}>${escapeHtml(item)}</option>`)
                .join("")}
            </select>
            <span class="field-feedback" id="tripulanteFuncaoFeedback" aria-live="polite"></span>
          </label>
          <label>
            Categoria operacional
            <select name="categoria_operacional" id="tripulanteCategoria" required aria-describedby="tripulanteCategoriaFeedback">
              ${options.categorias
                .map((item) => `<option value="${escapeAttr(item)}" ${tripulante?.categoria_operacional === item || (!tripulante && item === "N/A") ? "selected" : ""}>${escapeHtml(item)}</option>`)
                .join("")}
            </select>
            <span class="field-feedback" id="tripulanteCategoriaFeedback" aria-live="polite"></span>
            <span class="field-help">
              <strong>Legenda de porte:</strong><br>
              A - C525 ou aeronave do mesmo porte.<br>
              B - LRJ serie 30, C560, LRJ45, WW, G100 ou aeronave do mesmo porte.
            </span>
          </label>
            </div>
          </section>
          <section class="full-width flags-section entity-form-section">
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
          <section class="form-section entity-form-section">
            <div class="form-section-header">
              <h2>Arquivos visuais e observações</h2>
              <p>Informações de apoio que completam o cadastro sem competir com a operação principal.</p>
            </div>
            <div class="tripulante-photo-field">
              <div class="tripulante-photo-preview-card">
                <div class="tripulante-photo-preview" id="tripulantePhotoPreview">
                  ${
                    photoUrl
                      ? `<img class="tripulante-photo-img" src="${escapeAttr(photoUrl)}" alt="${escapeAttr(tripulante?.nome || "Tripulante")}" data-photo-fallback="initials" data-initials="${escapeAttr(initialsForName(tripulante?.nome || ""))}" data-photo-state-target="tripulantePhotoState">`
                      : `<span>${escapeHtml(initialsForName(tripulante?.nome || ""))}</span>`
                  }
                </div>
                <div class="tripulante-photo-meta">
                  <div class="checkbox-title">Foto do tripulante</div>
                  <div class="checkbox-description">Envie JPG, PNG ou WEBP. A imagem será exibida no cadastro, relatório e gestão de bases.</div>
                  <div class="upload-state compact" id="tripulantePhotoState" aria-live="polite" data-kind="${photoUrl ? "ready" : ""}">${photoStateMessage}</div>
                </div>
              </div>
              <div class="tripulante-photo-actions">
                <input type="file" id="tripulantePhotoInput" accept="image/png,image/jpeg,image/webp" aria-label="Foto do tripulante" aria-describedby="tripulantePhotoState">
                <button type="button" class="button-link secondary" id="tripulantePhotoUpload" ${tripulanteId ? "" : "disabled"}>Enviar foto</button>
                <button type="button" class="button-link secondary" id="tripulantePhotoRemove" ${tripulanteId ? "" : "disabled"}>Remover foto</button>
              </div>
            </div>
            <label class="full-width">Observações<textarea name="observacoes" rows="4">${escapeHtml(tripulante?.observacoes || "")}</textarea></label>
          </section>
          <div class="form-actions full-width entity-sticky-actions">
            <button type="submit" id="tripulanteFormSubmit">Salvar alterações</button>
            ${tripulanteId && capabilities.has("tripulantes:delete") ? '<button type="button" class="button-link secondary" id="tripulanteDeleteButton">Excluir tripulante</button>' : ""}
            <a class="button-link secondary" href="#/tripulantes">Voltar sem salvar</a>
          </div>
        </form>

        ${renderTripulanteFilesSection(tripulanteId, files, capabilities)}
      `,
      tripulanteId ? "Editar Tripulante" : "Novo Tripulante",
    );
    wireTripulantePhotoFallbacks();

    const photoInput = document.getElementById("tripulantePhotoInput");
    const photoPreview = document.getElementById("tripulantePhotoPreview");
    const nameInput = document.querySelector("input[name='nome']");
    const cpfInput = document.getElementById("tripulanteCpf");
    const anacInput = document.getElementById("tripulanteAnac");
    const phoneInput = document.getElementById("tripulanteTelefone");
    const formFeedback = document.getElementById("tripulante-form-feedback");
    const photoState = document.getElementById("tripulantePhotoState");
    const documentInput = document.getElementById("tripulanteFileInput");
    const documentState = document.getElementById("tripulanteFileUploadState");
    const documentReplaceSelect = document.getElementById("tripulanteFileReplaceSelect");
    const documentReplaceFeedback = document.getElementById("tripulanteFileReplaceFeedback");
    const documentSubmit = document.getElementById("tripulanteFileSubmit");

    function setFieldFeedback(input, message = "", kind = "error") {
      if (!input) return true;
      const feedbackId = input.getAttribute("aria-describedby");
      const feedback = feedbackId ? document.getElementById(feedbackId) : null;
      input.setAttribute("aria-invalid", message && kind === "error" ? "true" : "false");
      if (feedback) {
        feedback.textContent = message;
        feedback.dataset.kind = message ? kind : "";
      }
      return !message || kind !== "error";
    }

    function validateRequiredInput(input, message) {
      return setFieldFeedback(input, String(input?.value || "").trim() ? "" : message);
    }

    function setUploadState(target, message, kind = "") {
      if (!target) return;
      target.textContent = message;
      target.dataset.kind = kind;
    }

    function setSectionFeedback(id, message = "", kind = "error") {
      const target = document.getElementById(id);
      if (!target) return;
      target.textContent = message;
      target.dataset.kind = message ? kind : "";
    }

    function validatePdfFile(file, target) {
      if (!file) {
        setUploadState(target, "Selecione um PDF antes de anexar.", "error");
        return false;
      }
      if (file.type !== "application/pdf" && !String(file.name || "").toLowerCase().endsWith(".pdf")) {
        setUploadState(target, "Arquivo inválido. Envie apenas PDF.", "error");
        return false;
      }
      if (file.size > 20 * 1024 * 1024) {
        setUploadState(target, "Arquivo maior que 20 MB. Escolha um PDF menor.", "error");
        return false;
      }
      return true;
    }

    function renderDocumentReplaceFeedback() {
      if (!documentReplaceSelect || !documentReplaceFeedback) return;
      const selectedOption = documentReplaceSelect.selectedOptions?.[0];
      const replacing = Boolean(documentReplaceSelect.value);
      documentReplaceFeedback.textContent = replacing
        ? `${selectedOption?.textContent || "Documento selecionado"} sera marcado como substituido apos persistencia.`
        : "O envio criara um novo documento persistido.";
      documentReplaceFeedback.dataset.kind = replacing ? "warning" : "";
      if (documentSubmit) documentSubmit.textContent = replacing ? "Substituir PDF" : "Anexar PDF";
    }

    function renderDocumentPreview({ url, downloadUrl, name, meta }) {
      const frame = document.getElementById("tripulanteDocumentPreviewFrame");
      const title = document.getElementById("tripulanteDocumentPreviewName");
      const description = document.getElementById("tripulanteDocumentPreviewDescription");
      const openLink = document.getElementById("tripulanteDocumentPreviewOpen");
      const downloadLink = document.getElementById("tripulanteDocumentPreviewDownload");
      const state = document.getElementById("tripulanteDocumentPreviewState");
      if (!frame || !title || !description || !openLink || !downloadLink || !state) return;
      if (!url) {
        setUploadState(state, "Preview indisponivel para este documento. Use baixar PDF como fallback.", "error");
        return;
      }
      frame.src = url;
      title.textContent = name || "Documento PDF";
      description.textContent = meta || "application/pdf";
      openLink.href = url;
      downloadLink.href = downloadUrl || url;
      setUploadState(state, "Arquivo persistido carregado para preview.", "ready");
    }

    function validateTripulanteForm() {
      const identityValidations = [
        validateRequiredInput(nameInput, "Informe o nome do tripulante."),
        validateRequiredInput(cpfInput, "Informe o CPF."),
        setFieldFeedback(cpfInput, String(cpfInput?.value || "").replace(/\D/g, "").length === 11 ? "" : "CPF deve ter 11 dígitos."),
        validateRequiredInput(anacInput, "Informe o código ANAC."),
        setFieldFeedback(anacInput, String(anacInput?.value || "").replace(/\D/g, "").length >= 4 ? "" : "Código ANAC deve ter ao menos 4 dígitos."),
      ];
      const operationValidations = [
        validateRequiredInput(document.getElementById("tripulanteBase"), "Selecione a base."),
        validateRequiredInput(document.getElementById("tripulanteStatus"), "Selecione o status."),
        validateRequiredInput(document.getElementById("tripulanteFuncao"), "Selecione a função."),
        validateRequiredInput(document.getElementById("tripulanteCategoria"), "Selecione a categoria."),
      ];
      const validations = [...identityValidations, ...operationValidations];
      const emailInput = document.getElementById("tripulanteEmail");
      if (emailInput?.value && !emailInput.validity.valid) {
        const emailValid = setFieldFeedback(emailInput, "Informe um e-mail válido.");
        identityValidations.push(emailValid);
        validations.push(emailValid);
      } else {
        setFieldFeedback(emailInput, "");
      }
      setSectionFeedback(
        "tripulanteIdentitySectionFeedback",
        identityValidations.every(Boolean) ? "" : "Revise identificação antes de salvar.",
      );
      setSectionFeedback(
        "tripulanteOperationSectionFeedback",
        operationValidations.every(Boolean) ? "" : "Complete os campos operacionais obrigatórios.",
      );
      return validations.every(Boolean);
    }

    function renderPhotoPreview(src = "") {
      photoPreview.innerHTML = src
        ? `<img class="tripulante-photo-img" src="${escapeAttr(src)}" alt="${escapeAttr(nameInput?.value || "Tripulante")}" data-photo-fallback="initials" data-initials="${escapeAttr(initialsForName(nameInput?.value || ""))}" data-photo-state-target="tripulantePhotoState">`
        : `<span>${escapeHtml(initialsForName(nameInput?.value || ""))}</span>`;
      wireTripulantePhotoFallbacks(photoPreview);
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
      setFieldFeedback(cpfInput, String(cpfInput.value || "").replace(/\D/g, "").length === 11 || !cpfInput.value ? "" : "CPF deve ter 11 dígitos.");
    });
    anacInput?.addEventListener("input", () => {
      anacInput.value = String(anacInput.value || "").replace(/\D/g, "").slice(0, 6);
      setFieldFeedback(anacInput, String(anacInput.value || "").length >= 4 || !anacInput.value ? "" : "Código ANAC deve ter ao menos 4 dígitos.");
    });
    phoneInput?.addEventListener("input", () => {
      phoneInput.value = formatPhone(phoneInput.value);
    });
    nameInput?.addEventListener("input", () => {
      setFieldFeedback(nameInput, "");
      if (!photoPreview.querySelector("img")) renderPhotoPreview("");
    });
    document.querySelectorAll("#tripulante-form [required]").forEach((input) => {
      input.addEventListener("blur", () => validateRequiredInput(input, "Campo obrigatório."));
      input.addEventListener("change", () => setFieldFeedback(input, ""));
    });
    document.querySelectorAll(".toggle-switch input[type='checkbox']").forEach((input) => {
      input.addEventListener("change", () => {
        const textNode = input.closest(".toggle-switch")?.querySelector(".toggle-text");
        if (textNode) textNode.textContent = input.checked ? "Ativo" : "Inativo";
      });
    });

    document.getElementById("tripulante-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!validateTripulanteForm()) {
        renderInlineFeedback(formFeedback, "Revise os campos destacados antes de salvar.", "error");
        document.querySelector("#tripulante-form [aria-invalid='true']")?.focus();
        return;
      }
      const form = new FormData(event.currentTarget);
      const payload = Object.fromEntries(form.entries());
      ["ativo", "sdea_ativo", "instrutor_ativo", "checador_ativo", "elegivel_adicional_excepcional"].forEach((key) => {
        payload[key] = form.has(key);
      });
      const submitButton = document.getElementById("tripulanteFormSubmit");
      await withActionBusy(submitButton, "Salvando...", async () => {
        try {
          renderInlineFeedback(formFeedback, "");
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
          renderInlineFeedback(formFeedback, buildErrorMessage(error), "error");
        }
      });
    });

    document.getElementById("tripulanteDeleteButton")?.addEventListener("click", async () => {
      const deleteButton = document.getElementById("tripulanteDeleteButton");
      if (!confirmAction({
        title: "Remover este tripulante?",
        subject: tripulante?.nome || nameInput?.value || "Tripulante selecionado",
        consequence: "Se houver vínculos históricos, o registro pode ser inativado em vez de excluído.",
      })) return;
      await withActionBusy(deleteButton, "Removendo...", async () => {
        try {
          const { data } = await api(`/api/v1/tripulantes/${tripulanteId}`, { method: "DELETE" });
          showFlash(
            data?.operation === "inactivated"
              ? "Tripulante inativado porque existem vínculos históricos."
              : "Tripulante excluído com sucesso.",
            "success",
          );
          window.location.hash = "#/tripulantes";
        } catch (error) {
          renderInlineFeedback(formFeedback, buildErrorMessage(error), "error");
        }
      });
    });

    photoInput?.addEventListener("change", async () => {
      const file = photoInput.files?.[0];
      if (!file) {
        photoState.dataset.userUploadState = "";
        setUploadState(photoState, "Nenhuma nova foto selecionada.");
        return;
      }
      if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
        photoState.dataset.userUploadState = "error";
        setUploadState(photoState, "Arquivo inválido. Envie JPG, PNG ou WEBP.", "error");
        renderInlineFeedback(formFeedback, "Envie uma imagem JPG, PNG ou WEBP.", "error");
        photoInput.value = "";
        return;
      }
      photoState.dataset.userUploadState = "ready";
      setUploadState(photoState, `${file.name} · ${formatFileSize(file.size)} · pronto para envio`, "ready");
      renderPhotoPreview(await fileToDataUrl(file));
    });

    document.getElementById("tripulantePhotoUpload")?.addEventListener("click", async () => {
      const uploadButton = document.getElementById("tripulantePhotoUpload");
      const file = photoInput?.files?.[0];
      if (!tripulanteId || !file) {
        photoState.dataset.userUploadState = "error";
        setUploadState(photoState, "Selecione uma foto antes de enviar.", "error");
        renderInlineFeedback(formFeedback, "Selecione uma foto antes de enviar.", "error");
        return;
      }
      photoState.dataset.userUploadState = "busy";
      setUploadState(photoState, `${file.name} · enviando...`, "busy");
      await withActionBusy(uploadButton, "Enviando...", async () => {
        try {
          await api(`/api/v1/tripulantes/${tripulanteId}/photo`, {
            method: "POST",
            json: { foto_base64: await fileToDataUrl(file) },
          });
          showFlash("Foto atualizada com sucesso.", "success");
          await renderTripulanteFormPage(tripulanteId);
        } catch (error) {
          photoState.dataset.userUploadState = "error";
          setUploadState(photoState, `${file.name} · falha no envio`, "error");
          renderInlineFeedback(formFeedback, buildErrorMessage(error), "error");
        }
      });
    });

    document.getElementById("tripulantePhotoRemove")?.addEventListener("click", async () => {
      if (!tripulanteId) return;
      const removeButton = document.getElementById("tripulantePhotoRemove");
      if (!confirmAction({
        title: "Remover foto do tripulante?",
        subject: tripulante?.nome || nameInput?.value || "Tripulante selecionado",
        consequence: "A foto deixará de aparecer no cadastro e nos relatórios vinculados.",
      })) return;
      await withActionBusy(removeButton, "Removendo...", async () => {
        try {
          await api(`/api/v1/tripulantes/${tripulanteId}/photo`, { method: "DELETE" });
          showFlash("Foto removida com sucesso.", "success");
          await renderTripulanteFormPage(tripulanteId);
        } catch (error) {
          renderInlineFeedback(formFeedback, buildErrorMessage(error), "error");
        }
      });
    });

    document.getElementById("tripulante-file-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const submitButton = event.currentTarget.querySelector('button[type="submit"]');
      const file = documentInput?.files?.[0];
      if (!validatePdfFile(file, documentState)) {
        documentInput?.focus();
        return;
      }
      const replacing = Boolean(documentReplaceSelect?.value);
      setUploadState(
        documentState,
        `${file.name} · ${formatFileSize(file.size)} · ${replacing ? "substituindo documento persistido..." : "anexando..."}`,
        "busy",
      );
      await withActionBusy(submitButton, replacing ? "Substituindo..." : "Anexando...", async () => {
        try {
          await api(`/api/v1/tripulantes/${tripulanteId}/files`, {
            method: "POST",
            body: new FormData(event.currentTarget),
          });
          showFlash(replacing ? "PDF substituido com sucesso." : "PDF anexado com sucesso.", "success");
          await renderTripulanteFormPage(tripulanteId);
        } catch (error) {
          setUploadState(documentState, `${file.name} · ${replacing ? "falha ao substituir" : "falha ao anexar"}`, "error");
          renderInlineFeedback(formFeedback, buildErrorMessage(error), "error");
        }
      });
    });
    documentInput?.addEventListener("change", () => {
      const file = documentInput.files?.[0];
      if (!file) {
        setUploadState(documentState, "Nenhum PDF selecionado.");
        return;
      }
      if (validatePdfFile(file, documentState)) {
        const replacing = Boolean(documentReplaceSelect?.value);
        setUploadState(
          documentState,
          `${file.name} · ${formatFileSize(file.size)} · ${file.type || "application/pdf"} · ${replacing ? "pronto para substituir" : "pronto para anexar"}`,
          "ready",
        );
      }
    });
    documentReplaceSelect?.addEventListener("change", () => {
      renderDocumentReplaceFeedback();
      const file = documentInput?.files?.[0];
      if (file && validatePdfFile(file, documentState)) {
        setUploadState(
          documentState,
          `${file.name} · ${formatFileSize(file.size)} · ${file.type || "application/pdf"} · ${documentReplaceSelect.value ? "pronto para substituir" : "pronto para anexar"}`,
          "ready",
        );
      }
    });
    renderDocumentReplaceFeedback();

    document.querySelectorAll(".tripulante-file-preview").forEach((button) => {
      button.addEventListener("click", () => {
        renderDocumentPreview({
          url: button.dataset.previewUrl || "",
          downloadUrl: button.dataset.downloadUrl || "",
          name: button.dataset.fileName || "Documento PDF",
          meta: button.dataset.fileMeta || "application/pdf",
        });
      });
    });

    document.querySelectorAll(".tripulante-file-delete").forEach((button) => {
      button.addEventListener("click", async () => {
        if (!confirmAction({
          title: "Excluir este documento PDF?",
          subject: button.dataset.fileName || "Documento selecionado",
          consequence: "O arquivo deixará de ficar disponível no cadastro do tripulante.",
        })) return;
        await withActionBusy(button, "Excluindo...", async () => {
          try {
            await api(`/api/v1/tripulantes/${tripulanteId}/files/${button.dataset.fileId}`, { method: "DELETE" });
            showFlash("Documento removido com sucesso.", "success");
            await renderTripulanteFormPage(tripulanteId);
          } catch (error) {
            renderInlineFeedback(formFeedback, buildErrorMessage(error), "error");
          }
        });
      });
    });
  } catch (error) {
    showFlash(buildErrorMessage(error), "error");
    renderShell("<section class='panel'><div class='empty'>Falha ao carregar formulario de tripulante.</div></section>", "Tripulantes");
  }
}
