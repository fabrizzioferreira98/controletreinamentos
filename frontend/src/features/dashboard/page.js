import {
  api,
  buildErrorMessage,
  buildHashHref,
  capabilitySet,
  emptyTableRowMarkup,
  escapeAttr,
  escapeHtml,
  formatDateBr,
  responsiveAlertMarkup,
  responsiveStateMarkup,
  showFlash,
  state,
  trainingStatusClass,
  wireResponsiveMasterDetail,
} from "../../lib.js";
import { renderShell } from "../../shell.js";
import { BACKEND_LINKS } from "../../compat/backend-links.js";

let dashboardSummarySnapshot = {};

function resolveDashboardGreetingName() {
  const user = state.session?.user || {};
  const candidates = [user.nome, user.login, user.perfil];
  const resolved = candidates
    .map((value) => String(value || "").trim())
    .find(Boolean);
  return resolved || "Usuário";
}

function resolveDashboardGreetingPeriod(now = new Date()) {
  const hour = Number(now?.getHours?.() ?? Number.NaN);
  if (!Number.isFinite(hour)) return "Bom dia";
  if (hour >= 12 && hour < 18) return "Boa tarde";
  if (hour >= 18 || hour < 5) return "Boa noite";
  return "Bom dia";
}

function formatDashboardCountLabel(value, singular, plural) {
  const total = asDashboardNumber(value);
  return `${total} ${total === 1 ? singular : plural}`;
}

function formatTrainingStatusLabel(status) {
  const normalized = String(status || "")
    .trim()
    .toLowerCase();
  const statusLabelMap = {
    vencido: "Vencido",
    "a vencer": "A vencer",
    regular: "Regular",
    "sem informacao": "Sem informação",
    "sem informação": "Sem informação",
  };
  return statusLabelMap[normalized] || String(status || "");
}

function renderDashboardSparkline(tone) {
  const paths = {
    critical: "M3 24 L17 40 L30 26 L44 22 L57 34 L71 29 L84 37 L98 33 L112 39 L126 35",
    warning: "M3 37 L17 35 L30 39 L44 28 L57 33 L71 24 L84 31 L98 29 L112 34 L126 22",
    stable: "M3 39 L17 33 L30 35 L44 27 L57 31 L71 24 L84 33 L98 30 L112 35 L126 29",
    neutral: "M3 30 L17 42 L30 34 L44 24 L57 26 L71 37 L84 32 L98 39 L112 36 L126 33",
  };
  const line = paths[tone] || paths.neutral;
  return `
    <span class="dashboard-kpi-sparkline" aria-hidden="true">
      <svg viewBox="0 0 130 48" role="presentation" focusable="false" fill="none">
        <path
          d="${line}"
          fill="none"
          stroke="currentColor"
          stroke-width="2.8"
          stroke-linecap="round"
          stroke-linejoin="round"
          vector-effect="non-scaling-stroke"
        />
      </svg>
    </span>
  `;
}

function renderDashboardActions(_capabilities) {
  return "";
}

function renderDashboardHeader(capabilities) {
  const actionsMarkup = renderDashboardActions(capabilities);
  const displayName = resolveDashboardGreetingName();
  const greetingPeriod = resolveDashboardGreetingPeriod();
  // Shared header contract: priority-page-header ui-page-header ui-surface.
  return `
    <div class="page-header priority-page-header dashboard-page-header ui-page-header ui-surface">
      <div class="dashboard-header-main">
        <h1>${escapeHtml(greetingPeriod)}, ${escapeHtml(displayName)}</h1>
        <p class="page-subtitle">Aqui est&aacute; o panorama geral dos treinamentos e vencimentos.</p>
      </div>
      ${
        actionsMarkup
          ? `
            <div class="page-header-actions dashboard-header-actions">
              ${actionsMarkup}
            </div>
          `
          : ""
      }
    </div>
  `;
}

function renderDashboardPriorityStrip() {
  return `
    <section class="dashboard-priority-strip ui-surface dashboard-above-fold" data-dashboard-priority="p0" aria-label="Prioridade operacional do dia">
      <div class="dashboard-priority-copy">
        <span class="dashboard-priority-caption">Ritmo de execução</span>
        <p class="dashboard-priority-text">Comece pelo que venceu, proteja a janela curta e use os blocos abaixo para manter a semana sob controle.</p>
      </div>
      <div class="dashboard-priority-steps" aria-hidden="true">
        <span class="dashboard-priority-step dashboard-priority-step--critical"><strong>1</strong><span>Agir nos vencidos</span></span>
        <span class="dashboard-priority-step dashboard-priority-step--warning"><strong>2</strong><span>Proteger até 7 dias</span></span>
        <span class="dashboard-priority-step dashboard-priority-step--stable"><strong>3</strong><span>Planejar até 30 dias</span></span>
      </div>
    </section>
  `;
}

function renderDashboardEntryContext(alerts = {}, options = {}) {
  const loading = Boolean(options.loading);
  const immediateBacklog = asDashboardNumber(alerts.vencidos) + asDashboardNumber(alerts.em_7_dias);
  const planningBacklog = asDashboardNumber(alerts.em_30_dias);
  const items = [
    {
      label: "Risco imediato",
      value: immediateBacklog,
      href: "#/treinamentos",
      tone: "critical",
      hint: "vencidos + até 7 dias",
    },
    {
      label: "Planejamento",
      value: planningBacklog,
      href: buildHashHref("#/treinamentos", { periodo: "30" }),
      tone: "stable",
      hint: "janela de 30 dias",
    },
  ];
  const mostUrgent = immediateBacklog > 0 ? items[0] : items[1];
  const contextMessage = loading
    ? "Carregando panorama imediato da operação."
    : `${formatDashboardCountLabel(mostUrgent.value, "item", "itens")} em ${mostUrgent.label.toLowerCase()} neste momento.`;
  return `
    <section class="dashboard-entry-context ui-surface" aria-label="Contexto operacional imediato">
      <div class="dashboard-entry-context-main">
        <span class="dashboard-entry-context-caption">Contexto imediato</span>
        <p class="dashboard-entry-context-text">${escapeHtml(contextMessage)}</p>
      </div>
      <div class="dashboard-entry-context-list">
        ${items
          .map(
            (item) => `
              <a class="dashboard-entry-context-chip dashboard-entry-context-chip--${item.tone}" href="${escapeAttr(item.href)}">
                <span class="dashboard-entry-context-chip-label">${escapeHtml(item.label)}</span>
                <strong>${item.value}</strong>
                <span class="dashboard-entry-context-chip-hint">${escapeHtml(item.hint)}</span>
              </a>
            `,
          )
          .join("")}
      </div>
    </section>
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
  return responsiveAlertMarkup(message, "warning", "dashboard-widget-feedback");
}

function renderDashboardWidgetEmpty(title, detail = "", actionHref = "", actionLabel = "") {
  return responsiveStateMarkup({
    title,
    detail,
    actionHref,
    actionLabel,
    type: "empty",
    className: "empty dashboard-widget-empty",
    compact: true,
  });
}

function asDashboardNumber(value) {
  const numericValue = Number(value ?? 0);
  return Number.isFinite(numericValue) ? numericValue : 0;
}

function dashboardPercent(value, total) {
  const numericTotal = asDashboardNumber(total);
  if (numericTotal <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((asDashboardNumber(value) / numericTotal) * 100)));
}

function renderDashboardStatCards(alerts) {
  const summary = dashboardSummarySnapshot || {};
  const monitoredTotal =
    asDashboardNumber(summary.vencido) +
    asDashboardNumber(summary.a_vencer) +
    asDashboardNumber(summary.regular) +
    asDashboardNumber(summary.sem_informacao);
  const cards = [
    {
      label: "Vencidos",
      value: alerts.vencidos,
      href: buildHashHref("#/treinamentos", { status: "vencido" }),
      tone: "critical",
      action: "Ver vencidos",
    },
    {
      label: "Até 7 dias",
      value: alerts.em_7_dias,
      href: buildHashHref("#/treinamentos", { periodo: "7" }),
      tone: "warning",
      action: "Ver até 7 dias",
    },
    {
      label: "Até 30 dias",
      value: alerts.em_30_dias,
      href: buildHashHref("#/treinamentos", { periodo: "30" }),
      tone: "stable",
      action: "Ver até 30 dias",
    },
    {
      label: "Sem informação",
      value: summary.sem_informacao ?? 0,
      href: buildHashHref("#/treinamentos", { status: "sem informacao" }),
      tone: "neutral",
      action: "Revisar cadastros",
    },
  ];
  const statusItems = [
    { label: "Vencidos", value: asDashboardNumber(summary.vencido), tone: "critical", href: buildHashHref("#/treinamentos", { status: "vencido" }) },
    { label: "Até 7 dias", value: asDashboardNumber(alerts.em_7_dias), tone: "warning", href: buildHashHref("#/treinamentos", { periodo: "7" }) },
    { label: "Até 30 dias", value: asDashboardNumber(alerts.em_30_dias), tone: "stable", href: buildHashHref("#/treinamentos", { periodo: "30" }) },
    { label: "Sem informação", value: asDashboardNumber(summary.sem_informacao), tone: "neutral", href: buildHashHref("#/treinamentos", { status: "sem informacao" }) },
  ];
  const priorityTotal = cards.reduce((acc, card) => acc + asDashboardNumber(card.value), 0);
  const shareBaseTotal = monitoredTotal > 0 ? monitoredTotal : priorityTotal;

  return `
    <section class="dashboard-stat-grid ui-card-grid ui-card-equal-height dashboard-kpi-priority-row" data-dashboard-zone="kpi-priority" aria-label="Triagem rápida de vencimentos">
      ${cards
        .map(
          (card) => {
            const cardValue = asDashboardNumber(card.value);
            const share = dashboardPercent(cardValue, shareBaseTotal);
            return `
            <a class="dashboard-kpi-card dashboard-kpi-card--${card.tone} ui-surface ui-card" data-dashboard-priority="${card.tone === "critical" ? "p0" : card.tone === "warning" ? "p1" : "p2"}" href="${escapeAttr(card.href)}">
              <span class="dashboard-kpi-head">
                <span class="dashboard-kpi-eyebrow"><span class="dashboard-kpi-dot"></span>${escapeHtml(card.label)}</span>
              </span>
              <strong class="dashboard-kpi-value">${cardValue}</strong>
              <span class="dashboard-kpi-meta">
                <span class="dashboard-kpi-share">${share}% da base</span>
              </span>
              ${renderDashboardSparkline(card.tone)}
              <span class="dashboard-kpi-action">${escapeHtml(card.action)} &#8594;</span>
            </a>
          `;
          },
        )
        .join("")}
      <article class="dashboard-monitor-card dashboard-kpi-card ui-surface ui-card" aria-label="Base monitorada">
        <div class="dashboard-monitor-head">
          <span class="dashboard-monitor-eyebrow">Base monitorada</span>
          <strong class="dashboard-monitor-total">${monitoredTotal}</strong>
          <span class="dashboard-monitor-caption">Total de treinamentos acompanhados</span>
        </div>
        <div class="dashboard-monitor-bar" aria-hidden="true">
          ${statusItems
            .map((item) => `<span class="dashboard-monitor-segment dashboard-monitor-segment--${item.tone}" style="width:${dashboardPercent(item.value, monitoredTotal)}%"></span>`)
            .join("")}
        </div>
        <div class="dashboard-monitor-list">
          ${statusItems
            .map(
              (item) => `
                <a class="dashboard-monitor-item dashboard-monitor-item--${item.tone}" href="${escapeAttr(item.href)}">
                  <span class="dashboard-monitor-item-label">
                    <span class="dashboard-monitor-item-dot"></span>
                    ${escapeHtml(item.label)}
                  </span>
                  <strong>${item.value} (${dashboardPercent(item.value, monitoredTotal)}%)</strong>
                </a>
              `,
            )
            .join("")}
        </div>
      </article>
    </section>
  `;
}

function renderDashboardStatusOverview(summary) {
  const statusToneCopy = {
    critical: "Tratativa imediata",
    warning: "Janela curta de atenção",
    stable: "Base em rotina",
    neutral: "Revisar cadastros",
  };
  const items = [
    {
      label: "Vencidos",
      value: asDashboardNumber(summary.vencido),
      href: buildHashHref("#/treinamentos", { status: "vencido" }),
      tone: "critical",
    },
    {
      label: "A vencer",
      value: asDashboardNumber(summary.a_vencer),
      href: buildHashHref("#/treinamentos", { status: "a vencer" }),
      tone: "warning",
    },
    {
      label: "Regulares",
      value: asDashboardNumber(summary.regular),
      href: buildHashHref("#/treinamentos", { status: "regular" }),
      tone: "stable",
    },
    {
      label: "Sem informação",
      value: asDashboardNumber(summary.sem_informacao),
      href: buildHashHref("#/treinamentos", { status: "sem informacao" }),
      tone: "neutral",
    },
  ];
  const total = items.reduce((acc, item) => acc + item.value, 0);
  const itemsWithShare = items.map((item) => ({
    ...item,
    share: dashboardPercent(item.value, total),
  }));

  return `
    <section class="dashboard-status-overview" aria-label="Distribuição dos treinamentos por situação">
      <div class="dashboard-status-summary">
        <div class="dashboard-status-summary-copy">
          <span class="dashboard-status-summary-label">Base monitorada</span>
          <strong>${total}</strong>
        </div>
        <p class="dashboard-status-summary-text">Leitura rápida da distribuição atual dos treinamentos acompanhados nesta visão.</p>
      </div>
      <div class="dashboard-status-distribution" aria-hidden="true">
        ${itemsWithShare
          .map(
            (item) =>
              `<span class="dashboard-status-segment dashboard-status-segment--${item.tone}" style="width:${item.share}%"></span>`,
          )
          .join("")}
      </div>
      <div class="dashboard-status-list dashboard-status-bars dashboard-status-grid ui-card-grid ui-card-grid-compact ui-card-equal-height">
        ${itemsWithShare
          .map(
            (item) => `
              <a class="dashboard-status-item dashboard-status-item--${item.tone} ui-card ui-card-compact" href="${escapeAttr(item.href)}">
                <span class="dashboard-status-item-head">
                  <span class="dashboard-status-label-row">
                    <span class="dashboard-status-dot" aria-hidden="true"></span>
                    <span class="dashboard-status-label">${escapeHtml(item.label)}</span>
                  </span>
                  <span class="dashboard-status-metric">
                    <strong class="dashboard-status-value">${item.value}</strong>
                    <span class="dashboard-status-share">${item.share}% da base</span>
                  </span>
                </span>
                <span class="dashboard-status-state">${statusToneCopy[item.tone]}</span>
              </a>
            `,
          )
          .join("")}
      </div>
    </section>
  `;
}

function renderDashboardBaseCards(totals) {
  const cards = [
    {
      label: "Tripulantes",
      value: asDashboardNumber(totals.tripulantes),
      href: "#/tripulantes",
      support: "Cadastro principal",
      action: "Abrir lista",
      icon: "users",
      tone: "sky",
    },
    {
      label: "Equipamentos ativos",
      value: asDashboardNumber(totals.equipamentos),
      href: BACKEND_LINKS.equipamentos,
      support: "Base ativa",
      action: "Abrir base",
      icon: "home",
      tone: "mint",
    },
    {
      label: "Tipos ativos",
      value: asDashboardNumber(totals.tipos),
      href: "#/treinamentos/raiz",
      support: "Referência operacional",
      action: "Abrir tipos",
      icon: "tag",
      tone: "lilac",
    },
    {
      label: "Treinamentos",
      value: asDashboardNumber(totals.treinamentos),
      href: "#/treinamentos",
      support: "Lista completa",
      action: "Abrir cadastros",
      icon: "book",
      tone: "indigo",
    },
  ];
  const total = cards.reduce((acc, card) => acc + card.value, 0);

  const iconMarkup = {
    users: `<svg viewBox="0 0 24 24" role="presentation" focusable="false"><path d="M9.8 11a3.1 3.1 0 1 1 0-6.2 3.1 3.1 0 0 1 0 6.2Zm6.3 1.6a2.5 2.5 0 1 1 0-5 2.5 2.5 0 0 1 0 5ZM3.7 18.4c.3-3 2.8-5 6.1-5s5.7 2 6 5M14.3 18.4c.2-1.7 1.6-3 3.4-3 1.8 0 3.1 1.1 3.4 3" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    home: `<svg viewBox="0 0 24 24" role="presentation" focusable="false"><path d="M4.6 11.2 12 5l7.4 6.2M7.2 10.2v8.2h9.6v-8.2M10 18.4v-4.3h4v4.3" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    tag: `<svg viewBox="0 0 24 24" role="presentation" focusable="false"><path d="m12.6 4.8 6.6 6.6a2.1 2.1 0 0 1 0 3l-4.8 4.8a2.1 2.1 0 0 1-3 0L4.8 12.6a2.1 2.1 0 0 1 0-3l4.8-4.8a2.1 2.1 0 0 1 3 0Zm-2 3.1h.1" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    book: `<svg viewBox="0 0 24 24" role="presentation" focusable="false"><path d="M4.6 6.2a2 2 0 0 1 2-2H12v14.9H6.6a2 2 0 0 0-2 2V6.2Zm14.8 0a2 2 0 0 0-2-2H12v14.9h5.4a2 2 0 0 1 2 2V6.2Z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  };

  return `
    <section class="dashboard-base-overview" aria-label="Inventário operacional navegável">
      <div class="dashboard-base-summary">
        <div class="dashboard-base-summary-copy">
          <span class="dashboard-base-summary-label">Inventário ativo</span>
          <strong>${total}</strong>
          <span class="dashboard-base-summary-context">${cards.length} frentes com navegação direta</span>
        </div>
        <p class="dashboard-base-summary-text">Camada de apoio para abrir cadastros essenciais com um clique, sem interromper a tratativa diária.</p>
      </div>
      <section class="summary-grid dashboard-secondary-summary dashboard-base-grid ui-card-grid ui-card-grid-compact ui-card-equal-height">
      ${cards
        .map(
          (card) => `
            <a class="summary-card summary-link-card dashboard-base-card ui-card ui-card-compact" href="${escapeAttr(card.href)}">
              <span class="dashboard-base-card-top">
                <span class="dashboard-base-card-label">${escapeHtml(card.label)}</span>
                <span class="dashboard-base-card-icon dashboard-base-card-icon--${card.tone}" aria-hidden="true">${iconMarkup[card.icon] || ""}</span>
              </span>
              <strong class="dashboard-base-card-value">${card.value}</strong>
              <span class="dashboard-base-card-support">${escapeHtml(card.support)}</span>
              <span class="dashboard-base-card-action-row">
                <span class="dashboard-base-card-action">${escapeHtml(card.action)} &#8250;</span>
              </span>
            </a>
          `,
        )
        .join("")}
      </section>
    </section>
  `;
}

function dashboardCriticalActionLabel(status) {
  return trainingStatusClass(status) === "status-red" ? "Regularizar" : "Abrir";
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
        <tr class="dashboard-critical-row ${trainingStatusClass(item.status)}">
          <td data-label="Tripulante"><div class="primary-cell">${escapeHtml(item.tripulante_nome)}</div></td>
          <td data-label="Equipamento">${escapeHtml(item.equipamento_nome || "-")}</td>
          <td data-label="Tipo">${escapeHtml(item.tipo_treinamento_nome)}</td>
          <td data-label="Vencimento"><span class="date-strong">${escapeHtml(formatDateBr(item.data_vencimento))}</span></td>
          <td data-label="Status"><span class="status-pill ${trainingStatusClass(item.status)}">${escapeHtml(formatTrainingStatusLabel(item.status))}</span></td>
          <td class="actions" data-label="Ação"><a class="dashboard-row-action" href="#/treinamentos/${item.id}">${dashboardCriticalActionLabel(item.status)}</a></td>
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
            <div class="dashboard-agenda-list dashboard-agenda-responsive-list">
      ${
        items.length
          ? items
              .slice(0, 6)
              .map(
                (item) => `
                  <a class="dashboard-agenda-item ui-surface ui-card ui-card-compact" href="#/treinamentos/${item.id}">
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

function renderDashboardCalendarSupportBlock(items, hasError) {
  if (hasError) {
    return `
      <section class="dashboard-calendar-support-block" data-dashboard-surface="calendar-support">
        <header class="dashboard-calendar-support-head">
          <div>
            <h3>Próximos vencimentos</h3>
            <p>Resumo tático indisponível no momento.</p>
          </div>
        </header>
        <div class="dashboard-calendar-support-empty">
          ${responsiveStateMarkup({
            title: "Não foi possível carregar os próximos vencimentos.",
            detail: "A grade mensal segue disponível para navegação.",
            type: "empty",
            className: "empty dashboard-widget-empty",
            compact: true,
          })}
        </div>
      </section>
    `;
  }
  const nextItems = Array.isArray(items) ? items.slice(0, 4) : [];
  return `
    <section class="dashboard-calendar-support-block" data-dashboard-surface="calendar-support">
      <header class="dashboard-calendar-support-head">
        <div>
          <h3>Próximos vencimentos</h3>
          <p>${nextItems.length ? `${formatDashboardCountLabel(nextItems.length, "item", "itens")} para tratativa imediata.` : "Sem vencimentos futuros no recorte atual."}</p>
        </div>
        <a class="button-link secondary dashboard-calendar-support-link" href="#/treinamentos">Abrir lista</a>
      </header>
      ${
        nextItems.length
          ? `
            <div class="dashboard-calendar-support-list">
              ${nextItems
                .map(
                  (item) => `
                    <a class="dashboard-calendar-support-item ${trainingStatusClass(item.status)}" href="#/treinamentos/${item.id}">
                      <span class="dashboard-calendar-support-date">${escapeHtml(formatDateBr(item.data_vencimento))}</span>
                      <span class="dashboard-calendar-support-main">
                        <strong>${escapeHtml(item.tripulante_nome)}</strong>
                        <small>${escapeHtml(item.tipo_treinamento_nome)}</small>
                      </span>
                      <span class="status-pill ${trainingStatusClass(item.status)}">${escapeHtml(formatTrainingStatusLabel(item.status))}</span>
                    </a>
                  `,
                )
                .join("")}
            </div>
          `
          : `
            <div class="dashboard-calendar-support-empty">
              ${responsiveStateMarkup({
                title: "Nenhum vencimento futuro no calendário atual.",
                detail: "Este bloco será preenchido quando houver novos registros.",
                type: "empty",
                className: "empty dashboard-widget-empty",
                compact: true,
              })}
            </div>
          `
      }
    </section>
  `;
}

function renderDashboardLoadingMarkup(capabilities) {
  return `
    <div class="dashboard-page-shell priority-page-surface ui-page-shell ui-stack dashboard-reference-target dashboard-responsive-surface" data-dashboard-layout="responsive-operational">
    <div class="dashboard-top-cluster dashboard-fold-priority" data-dashboard-zone="above-fold">
      ${renderDashboardHeader(capabilities)}

      ${renderDashboardPriorityStrip()}
      ${renderDashboardEntryContext({ vencidos: 0, em_7_dias: 0, em_30_dias: 0 }, { loading: true })}

      <section class="dashboard-stat-grid ui-card-grid ui-card-equal-height dashboard-kpi-priority-row" data-dashboard-zone="kpi-priority" aria-label="Triagem rápida de vencimentos">
        <div class="dashboard-kpi-card dashboard-kpi-card--critical dashboard-kpi-card--loading ui-surface ui-card" data-dashboard-priority="p0">
          <span class="dashboard-kpi-head">
            <span class="dashboard-kpi-eyebrow"><span class="dashboard-kpi-dot"></span>Vencidos</span>
          </span>
          <strong class="dashboard-kpi-value">...</strong>
          <span class="dashboard-kpi-meta">
            <span class="dashboard-kpi-share">Carregando base</span>
            <span class="dashboard-kpi-state is-active">...</span>
          </span>
          <span class="dashboard-kpi-action">Carregando atalho</span>
        </div>
        <div class="dashboard-kpi-card dashboard-kpi-card--warning dashboard-kpi-card--loading ui-surface ui-card" data-dashboard-priority="p1">
          <span class="dashboard-kpi-head">
            <span class="dashboard-kpi-eyebrow"><span class="dashboard-kpi-dot"></span>Até 7 dias</span>
          </span>
          <strong class="dashboard-kpi-value">...</strong>
          <span class="dashboard-kpi-meta">
            <span class="dashboard-kpi-share">Carregando base</span>
            <span class="dashboard-kpi-state is-clear">...</span>
          </span>
          <span class="dashboard-kpi-action">Carregando atalho</span>
        </div>
        <div class="dashboard-kpi-card dashboard-kpi-card--stable dashboard-kpi-card--loading ui-surface ui-card" data-dashboard-priority="p2">
          <span class="dashboard-kpi-head">
            <span class="dashboard-kpi-eyebrow"><span class="dashboard-kpi-dot"></span>Até 30 dias</span>
          </span>
          <strong class="dashboard-kpi-value">...</strong>
          <span class="dashboard-kpi-meta">
            <span class="dashboard-kpi-share">Carregando base</span>
            <span class="dashboard-kpi-state is-clear">...</span>
          </span>
          <span class="dashboard-kpi-action">Carregando atalho</span>
        </div>
        <div class="dashboard-kpi-card dashboard-kpi-card--neutral dashboard-kpi-card--loading ui-surface ui-card" data-dashboard-priority="p2">
          <span class="dashboard-kpi-head">
            <span class="dashboard-kpi-eyebrow"><span class="dashboard-kpi-dot"></span>Sem informação</span>
          </span>
          <strong class="dashboard-kpi-value">...</strong>
          <span class="dashboard-kpi-meta">
            <span class="dashboard-kpi-share">Carregando base</span>
            <span class="dashboard-kpi-state is-clear">...</span>
          </span>
          <span class="dashboard-kpi-action">Carregando atalho</span>
        </div>
        <article class="dashboard-monitor-card dashboard-kpi-card ui-surface ui-card">
          <div class="dashboard-monitor-head">
            <span class="dashboard-monitor-eyebrow">Base monitorada</span>
            <strong class="dashboard-monitor-total">...</strong>
            <span class="dashboard-monitor-caption">Carregando total de treinamentos</span>
          </div>
          <div class="dashboard-monitor-bar" aria-hidden="true">
            <span class="dashboard-monitor-segment dashboard-monitor-segment--critical" style="width:25%"></span>
            <span class="dashboard-monitor-segment dashboard-monitor-segment--warning" style="width:25%"></span>
            <span class="dashboard-monitor-segment dashboard-monitor-segment--stable" style="width:25%"></span>
            <span class="dashboard-monitor-segment dashboard-monitor-segment--neutral" style="width:25%"></span>
          </div>
        </article>
      </section>
    </div>

    <section class="panel dashboard-panel dashboard-critical-panel ui-surface dashboard-critical-zone" data-dashboard-priority="p0" data-dashboard-surface="critical-queue">
      <div class="page-header dashboard-subheader">
        <div class="dashboard-critical-header-copy">
          <h2>Fila crítica</h2>
          <p class="page-subtitle">Coração operacional da tratativa diária.</p>
        </div>
      </div>
      <div class="flash loading dashboard-widget-feedback ui-alert" data-kind="loading" role="status" aria-live="polite">Carregando treinamentos críticos...</div>
    </section>

    <section class="dashboard-secondary-grid dashboard-mid-surface-grid dashboard-mid-zone" data-dashboard-priority="p1" data-dashboard-surface="mid-summary">
      <div class="panel dashboard-panel dashboard-status-panel dashboard-mid-surface-panel ui-surface">
        <div class="dashboard-mid-surface-head dashboard-status-panel-head">
          <div class="section-title">Visão geral dos status</div>
          <p class="page-subtitle">Distribuição atual dos treinamentos monitorados por situação.</p>
        </div>
        <div class="flash loading dashboard-widget-feedback dashboard-mid-surface-loading ui-alert" data-kind="loading" role="status" aria-live="polite">Carregando resumo de status...</div>
      </div>
      <div class="panel dashboard-panel dashboard-base-panel dashboard-mid-surface-panel ui-surface">
        <div class="dashboard-mid-surface-head dashboard-base-panel-head">
          <div class="section-title">Base operacional</div>
          <p class="page-subtitle">Inventário navegável dos cadastros ativos usados na operação.</p>
        </div>
        <div class="flash loading dashboard-widget-feedback dashboard-mid-surface-loading ui-alert" data-kind="loading" role="status" aria-live="polite">Carregando base cadastral...</div>
      </div>
    </section>

    <section class="panel dashboard-calendar-panel ui-surface dashboard-calendar-zone" data-dashboard-priority="p1" data-dashboard-surface="calendar">
      <div class="section-title">Calendário de vencimentos</div>
      <div class="flash loading dashboard-widget-feedback ui-alert" data-kind="loading" role="status" aria-live="polite">Carregando grade mensal...</div>
    </section>

    <section class="panel dashboard-panel dashboard-agenda-panel ui-surface dashboard-agenda-zone" data-dashboard-priority="p2" data-dashboard-surface="agenda">
      <div class="section-title">Próximos vencimentos</div>
      <div class="flash loading dashboard-widget-feedback ui-alert" data-kind="loading" role="status" aria-live="polite">Carregando agenda compacta...</div>
    </section>
    </div>
  `;
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
  const masterDetail = wireResponsiveMasterDetail({
    root: "#dashboardCalendarMasterDetail",
    master: "#dashboardCalendarMaster",
    detail: "#dashboardCalendarDetail",
    triggers: "[data-calendar-day]",
    backTrigger: "#dashboardCalendarBack",
    detailFocus: "#dashboardCalendarDetailSubtitle",
  });
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
    detailList.dataset.detailContext = isoDate;
    detailSubtitle.dataset.detailContext = isoDate;
    if (!selected.items || !selected.items.length) {
      detailSubtitle.textContent = `${formatDateBr(isoDate)} · sem vencimentos no dia`;
      detailList.innerHTML = responsiveStateMarkup({
        title: "Nenhum vencimento cadastrado para esta data.",
        type: "empty",
        className: "empty dashboard-widget-empty",
        compact: true,
      });
      return;
    }
    detailSubtitle.textContent = `${formatDateBr(isoDate)} · ${formatDashboardCountLabel(selected.items.length, "vencimento", "vencimentos")} em foco`;
    detailList.innerHTML = selected.items
      .map(
        (item) => `
          <article class="dashboard-calendar-detail-card ui-surface ui-card ui-card-compact ${trainingStatusClass(item.status)}">
            <div class="dashboard-calendar-detail-top">
              <span class="status-pill ${trainingStatusClass(item.status)}">${escapeHtml(formatDateBr(item.data_vencimento))}</span>
              <a class="dashboard-calendar-event-pilot" href="#/tripulantes/${item.tripulante_id}">Ver tripulante</a>
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
  if (firstDay) {
    renderDayDetails(firstDay.iso_date);
    masterDetail?.activate(
      dayButtons.find((button) => button.dataset.calendarDay === firstDay.iso_date),
      { focus: false, revealDetail: false, shouldScroll: false },
    );
  }
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
    dashboardSummarySnapshot = dashboardSummary;
    renderShell(
      `
        <div class="dashboard-page-shell priority-page-surface ui-page-shell ui-stack dashboard-reference-target dashboard-responsive-surface" data-dashboard-layout="responsive-operational">
        <div class="dashboard-top-cluster dashboard-fold-priority" data-dashboard-zone="above-fold">
          ${renderDashboardHeader(capabilities)}

          ${renderDashboardPriorityStrip()}
          ${renderDashboardEntryContext(dashboardAlerts)}

          ${renderDashboardWidgetFeedback(summaryBlock.error, "")}
          ${renderDashboardStatCards(dashboardAlerts)}
        </div>

        <section class="dashboard-core-grid">
          <section class="panel dashboard-panel dashboard-critical-panel ui-surface dashboard-critical-zone" data-dashboard-priority="p0" data-dashboard-surface="critical-queue">
            <div class="page-header dashboard-subheader">
              <div class="dashboard-critical-header-copy">
                <h2>Fila crítica <span class="dashboard-critical-badge">${criticalItems.length}</span></h2>
                <p class="page-subtitle">Vencidos primeiro, depois os mais próximos do vencimento.</p>
              </div>
              <a class="button-link secondary dashboard-critical-open-inline" href="#/treinamentos">Abrir lista completa</a>
            </div>
            ${renderDashboardWidgetFeedback(criticalBlock.error, "")}

            <div class="dashboard-critical-toolbar">
              <div class="dashboard-critical-toolbar-main">
                <div class="dashboard-critical-volume" aria-live="polite">
                  <span class="dashboard-toolbar-label">Tratativa do turno</span>
                  <strong class="dashboard-critical-volume-value">${criticalItems.length}</strong>
                  <span class="dashboard-critical-volume-support">${formatDashboardCountLabel(criticalItems.length, "registro prioritário", "registros prioritários")}</span>
                </div>
                <p class="dashboard-critical-toolbar-note">Regularize primeiro os vencidos e use os atalhos para abrir lotes na lista completa.</p>
              </div>
              <nav class="dashboard-critical-filters" aria-label="Atalhos de filtro da lista completa">
                <a class="dashboard-critical-filter dashboard-critical-filter--critical" href="${buildHashHref("#/treinamentos", { status: "vencido" })}">
                  <span>Vencidos</span>
                  <strong>${dashboardAlerts.vencidos ?? 0}</strong>
                </a>
                <a class="dashboard-critical-filter dashboard-critical-filter--warning" href="${buildHashHref("#/treinamentos", { periodo: "7" })}">
                  <span>Até 7 dias</span>
                  <strong>${dashboardAlerts.em_7_dias ?? 0}</strong>
                </a>
                <a class="dashboard-critical-filter dashboard-critical-filter--stable" href="${buildHashHref("#/treinamentos", { periodo: "30" })}">
                  <span>Até 30 dias</span>
                  <strong>${dashboardAlerts.em_30_dias ?? 0}</strong>
                </a>
              </nav>
            </div>

            <div class="dashboard-critical-table-head">
              <span class="dashboard-critical-table-kicker">Fila de decisão</span>
              <p class="dashboard-critical-table-caption">Cada linha direciona a próxima regularização sem alterar o fluxo atual de treinamentos.</p>
            </div>

            <div class="table-wrap dashboard-critical-table-wrap ui-table-wrap ui-table-density-compact" data-dashboard-surface="critical-list">
              <table class="data-table responsive-cards dashboard-critical-table">
                <thead>
                  <tr>
                    <th scope="col">Tripulante</th>
                    <th scope="col">Equipamento</th>
                    <th scope="col">Tipo</th>
                    <th scope="col">Vencimento</th>
                    <th scope="col">Status</th>
                    <th scope="col">A&ccedil;&atilde;o</th>
                  </tr>
                </thead>
                <tbody>
                  ${renderDashboardCriticalRows(criticalItems, Boolean(criticalBlock.error))}
                </tbody>
              </table>
            </div>

            <a class="button-link secondary dashboard-critical-open-bottom" href="#/treinamentos">Abrir lista completa</a>
          </section>

          <section class="panel dashboard-calendar-panel ui-surface dashboard-calendar-zone" data-dashboard-priority="p1" data-dashboard-surface="calendar">
            <div class="page-header dashboard-subheader dashboard-calendar-header">
              <div class="dashboard-calendar-head-copy">
                <h2>Calendário de vencimentos</h2>
              </div>
            </div>
            ${renderDashboardWidgetFeedback(calendarBlock.error, "")}
            <p class="dashboard-calendar-support-note">Leitura mensal dos vencimentos para apoio tático da operação.</p>

            <div class="dashboard-calendar-layout dashboard-calendar-responsive-layout" data-dashboard-surface="calendar-detail">
              <div class="dashboard-calendar-master-detail ui-master-detail" id="dashboardCalendarMasterDetail" data-master-detail-pattern="calendar">
              <div class="dashboard-calendar-shell ui-master-pane" id="dashboardCalendarMaster">
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
                          <span class="dashboard-calendar-day-label">${day.count ? `${day.count} venc.` : ""}</span>
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

              <aside class="dashboard-calendar-aside ui-detail-pane" id="dashboardCalendarDetail" data-detail-sticky="true" tabindex="-1">
                <button type="button" class="button-link secondary ui-detail-back dashboard-calendar-back" id="dashboardCalendarBack">Voltar ao calendário</button>
                <div class="dashboard-calendar-detail-head">
                  <div class="section-title">Detalhes do dia</div>
                  <p class="page-subtitle" id="dashboardCalendarDetailSubtitle">Selecione um dia para expandir os vencimentos.</p>
                </div>
                <div class="dashboard-calendar-detail-list" id="dashboardCalendarDetailList">
                  ${responsiveStateMarkup({
                    title: "Selecione um dia com vencimento para ver os detalhes.",
                    type: "empty",
                    className: "empty dashboard-widget-empty",
                    compact: true,
                  })}
                </div>
              </aside>
              </div>
            </div>

            <div class="dashboard-calendar-legend">
              <span class="dashboard-calendar-legend-item dashboard-calendar-legend-item--critical"><span></span>Vencidos</span>
              <span class="dashboard-calendar-legend-item dashboard-calendar-legend-item--warning"><span></span>Até 7 dias</span>
              <span class="dashboard-calendar-legend-item dashboard-calendar-legend-item--stable"><span></span>Até 30 dias</span>
            </div>
            ${renderDashboardCalendarSupportBlock(upcomingItems, Boolean(calendarBlock.error))}
          </section>
        </section>

        <section class="dashboard-secondary-grid dashboard-mid-surface-grid dashboard-mid-zone" data-dashboard-priority="p1" data-dashboard-surface="mid-summary">
          <div class="panel dashboard-panel dashboard-status-panel dashboard-mid-surface-panel ui-surface">
            <div class="dashboard-mid-surface-head dashboard-status-panel-head">
              <div class="section-title">Visão geral dos status</div>
              <p class="page-subtitle">Distribuição atual dos treinamentos monitorados por situação.</p>
            </div>
            ${renderDashboardWidgetFeedback(summaryBlock.error, "")}
            ${renderDashboardStatusOverview(dashboardSummary)}
          </div>

          <div class="panel dashboard-panel dashboard-base-panel dashboard-mid-surface-panel ui-surface">
            <div class="dashboard-mid-surface-head dashboard-base-panel-head">
              <div class="section-title">Base operacional</div>
              <p class="page-subtitle">Inventário navegável dos cadastros ativos usados na operação.</p>
            </div>
            ${renderDashboardWidgetFeedback(summaryBlock.error, "")}
            ${renderDashboardBaseCards(dashboardTotals)}
          </div>
        </section>

        <section class="panel dashboard-panel dashboard-agenda-panel ui-surface dashboard-agenda-zone" data-dashboard-priority="p2" data-dashboard-surface="agenda">
            <div class="dashboard-widget-head ui-cluster">
              <div>
                <div class="section-title">Próximos vencimentos</div>
                <p class="page-subtitle">Lista cronológica dos vencimentos futuros do mês.</p>
              </div>
            </div>
          ${renderDashboardCompactAgenda(upcomingItems, Boolean(calendarBlock.error))}
        </section>
        </div>
      `,
      "Dashboard",
    );
    wireDashboardCalendar(calendarData);
  } catch (error) {
    showFlash(buildErrorMessage(error), "error");
    renderShell(`
      <section class="panel ui-surface">
        ${responsiveStateMarkup({
          title: "Falha ao carregar dashboard.",
          detail: buildErrorMessage(error),
          type: "error",
          className: "empty route-state",
        })}
      </section>
    `, "Dashboard");
  }
}


