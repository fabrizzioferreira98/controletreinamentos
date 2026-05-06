import {
  buildErrorMessage,
  buildHashHref,
  capabilitySet,
  confirmAction,
  emptyTableRowMarkup,
  escapeAttr,
  escapeHtml,
  formatCompetenciaLabel,
  formatCurrencyBr,
  formatDateBr,
  formatDateTimeBr,
  hashQuery,
  renderInlineFeedback,
  responsiveStateMarkup,
  showFlash,
  withActionBusy,
} from "../../lib.js";
import { renderShell } from "../../shell.js";
import {
  closeFinanceiroCompetencia,
  createFinanceiroFeriado,
  createFinanceiroParametro,
  downloadFinanceiroCompetenciaPdf,
  getFinanceiroCompetencia,
  getFinanceiroCompetenciaPreflight,
  listFinanceiroAuditoria,
  listFinanceiroDivergencias,
  listFinanceiroFeriados,
  listFinanceiroParametros,
  recalculateFinanceiroCompetencia,
  reopenFinanceiroCompetencia,
  updateFinanceiroFeriado,
  updateFinanceiroParametro,
} from "../../services/financeiro-parametros-api.js";

const FINANCEIRO_FECHAMENTO_PARAMETROS_ROUTE = "#/financeiro/fechamento-parametros";
const PARAMETER_READ_PERMISSION = "finance:parameters:read";
const PARAMETER_CREATE_PERMISSION = "finance:parameters:create";
const PARAMETER_UPDATE_PERMISSION = "finance:parameters:update";
const PERIOD_READ_PERMISSION = "finance:periods:read";
const PERIOD_RECALCULATE_PERMISSION = "finance:periods:recalculate";
const PERIOD_CLOSE_PERMISSION = "finance:periods:close";
const PERIOD_REOPEN_PERMISSION = "finance:periods:reopen";
const EXPORT_CREATE_PERMISSION = "finance:exports:create";
const AUDIT_READ_PERMISSION = "finance:audit:read";
const DIVERGENCES_READ_PERMISSION = "finance:divergences:read";

const PARAMETER_TYPES = [
  "duracao_hora_noturna_minutos",
  "adicional_noturno",
  "domingo_feriado_diurno",
  "domingo_feriado_noturno",
  "periodo_diurno_inicio",
  "periodo_diurno_fim",
  "icao_sdea",
  "instrutor",
  "checador",
  "missao_categoria_a",
  "missao_categoria_b",
  "cobertura_base",
  "pernoite_comum_sem_cobertura",
  "garantia_minima",
  "excecao_palmas_turbohelice",
];

const PARAMETER_UNITS = [
  "minutos",
  "minutos_do_dia",
  "percentual",
  "valor",
  "horario",
  "quantidade",
  "texto",
];

const DAY_PERIOD_PARAMETER_TYPES = new Set(["periodo_diurno_inicio", "periodo_diurno_fim"]);
const GLOBAL_HOURLY_PARAMETER_TYPES = new Set(["duracao_hora_noturna_minutos", "periodo_diurno_inicio", "periodo_diurno_fim"]);
const PARAMETER_DEFAULT_UNITS = {
  duracao_hora_noturna_minutos: "minutos",
  periodo_diurno_inicio: "minutos_do_dia",
  periodo_diurno_fim: "minutos_do_dia",
  adicional_noturno: "valor",
  domingo_feriado_diurno: "valor",
  domingo_feriado_noturno: "valor",
  icao_sdea: "valor",
  instrutor: "valor",
  checador: "valor",
  missao_categoria_a: "valor",
  missao_categoria_b: "valor",
  cobertura_base: "valor",
  pernoite_comum_sem_cobertura: "valor",
  garantia_minima: "valor",
  excecao_palmas_turbohelice: "valor",
};

const STATUS_OPTIONS = ["ativo", "inativo"];
let currentSettingsState = {
  parameters: [],
  holidays: [],
  parametersState: { status: "ready", items: [] },
  holidaysState: { status: "ready", items: [] },
  periodState: { status: "ready", period: null, totals: {}, snapshot: null, divergences: [] },
  preflightState: { status: "ready", data: null, error: null },
  auditState: { status: "ready", items: [], pagination: {}, filters: {} },
  divergencesState: { status: "ready", items: [], pagination: {}, filters: {} },
  pdfState: { status: "idle", kind: "", message: "" },
  competencia: "",
};

let activeSettingsMobileSection = "monthly-closing";

function currentYear() {
  return String(new Date().getFullYear());
}

function currentCompetencia() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  return `${now.getFullYear()}-${month}`;
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function normalizeItems(payload) {
  return Array.isArray(payload?.items) ? payload.items : [];
}

function statusClass(status) {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "ativo") return "status-green";
  if (normalized === "inativo") return "status-dark";
  if (normalized === "aberta") return "status-green";
  if (normalized === "em_conferencia") return "status-yellow";
  if (normalized === "reaberta") return "status-yellow";
  if (normalized === "fechada") return "status-dark";
  if (normalized === "bloqueante" || normalized === "alta") return "status-red";
  if (normalized === "media" || normalized === "warning") return "status-yellow";
  if (normalized === "info" || normalized === "informativa") return "status-gray";
  return "status-yellow";
}

function optionMarkup(values, selected = "") {
  return values
    .map((value) => `<option value="${escapeAttr(value)}" ${String(selected) === value ? "selected" : ""}>${escapeHtml(value)}</option>`)
    .join("");
}

function nullableValue(value) {
  const normalized = String(value ?? "").trim();
  return normalized || null;
}

function fieldValue(item, key, fallback = "") {
  return escapeAttr(item?.[key] ?? fallback);
}

function displayValue(value, fallback = "-") {
  const normalized = String(value ?? "").trim();
  return normalized || fallback;
}

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function preflightPayloadFromApi(payload) {
  const source = payload?.data && typeof payload.data === "object" ? payload.data : payload;
  const canExecuteActions = source?.can_execute_actions && typeof source.can_execute_actions === "object"
    ? source.can_execute_actions
    : {};
  return {
    calculavel: source?.calculavel === true,
    fechavel: source?.fechavel === true,
    competenciaStatus: displayValue(source?.competencia_status, ""),
    bloqueios: asArray(source?.bloqueios),
    avisos: asArray(source?.avisos),
    parametrosFaltantes: asArray(source?.parametros_faltantes),
    parametrosInvalidos: asArray(source?.parametros_invalidos),
    parametrosNaoElegiveis: asArray(source?.parametros_nao_elegiveis),
    parametrosAmbiguos: asArray(source?.parametros_ambiguos),
    dadosQaDetectados: asArray(source?.dados_qa_detectados),
    divergencias: asArray(source?.divergencias),
    nextAction: displayValue(source?.next_action, ""),
    canExecuteActions,
  };
}

function boolLabel(value) {
  return value ? "Sim" : "Nao";
}

function paragraphListMarkup(items = []) {
  if (!items.length) return "<p>-</p>";
  return `<ul>${items.map((item) => `<li>${escapeHtml(displayValue(item?.message || item?.codigo || item?.tipo || String(item), "-"))}</li>`).join("")}</ul>`;
}

function periodStatusIsClosed(status) {
  return String(status || "").trim().toLowerCase() === "fechada";
}

function resolvePdfKindLabel(period, filename = "") {
  const normalized = String(filename || "").trim().toLowerCase();
  if (normalized.includes("previa")) return "PDF de previa";
  if (normalized.includes("fechamento")) return "PDF de fechamento";
  if (periodStatusIsClosed(period?.status)) return "PDF de fechamento";
  return "PDF de previa";
}

function defaultAuditFilters(competencia) {
  return {
    competencia,
    entityType: "",
    eventName: "",
    limit: 20,
    offset: 0,
  };
}

function defaultDivergenceFilters(competencia) {
  return {
    competencia,
    status: "",
    severidade: "",
    codigo: "",
    limit: 20,
    offset: 0,
  };
}

function shouldOpenHeavySection() {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia("(min-width: 1200px)").matches;
}

function periodPayloadFromApi(payload) {
  const period = payload?.period || null;
  const snapshot = payload?.snapshot || period?.snapshot || null;
  return {
    status: "ready",
    period,
    totals: payload?.totals || period?.totals || snapshot?.totals || {},
    snapshot,
    divergences: Array.isArray(payload?.divergences) ? payload.divergences : [],
  };
}

function downloadBlob(blob, filename) {
  const objectUrl = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename || "relatorio-financeiro.pdf";
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 0);
}

function parameterDraft() {
  return {
    tipo: "duracao_hora_noturna_minutos",
    valor: "52.5",
    unidade: "minutos",
    status: "ativo",
    vigencia_inicio: todayIso(),
  };
}

function holidayDraft() {
  return {
    tipo: "nacional",
    status: "ativo",
  };
}

function financeSettingsIcon(type) {
  const icons = {
    closing: `
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <rect x="4" y="5" width="16" height="15" rx="2"></rect>
        <path d="M8 3v4"></path>
        <path d="M16 3v4"></path>
        <path d="M4 10h16"></path>
        <path d="M8 14h3"></path>
        <path d="M13 14h3"></path>
      </svg>
    `,
    parameters: `
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path d="M4 7h10"></path>
        <path d="M4 17h10"></path>
        <path d="M10 12h10"></path>
        <circle cx="17" cy="7" r="2"></circle>
        <circle cx="7" cy="12" r="2"></circle>
        <circle cx="17" cy="17" r="2"></circle>
      </svg>
    `,
    holidays: `
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <rect x="4" y="5" width="16" height="15" rx="2"></rect>
        <path d="M8 3v4"></path>
        <path d="M16 3v4"></path>
        <path d="M4 10h16"></path>
        <path d="M9 15h6"></path>
      </svg>
    `,
    audit: `
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path d="M12 3l7 3v5c0 5-3 8-7 10-4-2-7-5-7-10V6l7-3Z"></path>
        <path d="M9 12l2 2 4-5"></path>
      </svg>
    `,
  };
  return icons[type] || icons.closing;
}

function renderSettingsOverview() {
  return `
    <section class="financeiro-product-alert financeiro-product-alert-warning">
      <strong>Fechamento e Parametros</strong>
      <span>Controle de competencia, parametros financeiros, feriados e auditoria operacional do modulo Financeiro.</span>
    </section>

    <section class="financeiro-overview-grid financeiro-overview-grid-four" aria-label="Areas de fechamento e parametros">
      <article class="financeiro-overview-card financeiro-overview-card-blue">
        <div class="financeiro-overview-icon">${financeSettingsIcon("closing")}</div>
        <h2>Fechamento Mensal</h2>
        <p>Realize a conferencia da competencia e consolide os dados para calculo.</p>
        <span class="financeiro-overview-pill">Operacional</span>
      </article>
      <article class="financeiro-overview-card financeiro-overview-card-green">
        <div class="financeiro-overview-icon">${financeSettingsIcon("parameters")}</div>
        <h2>Parametros Financeiros</h2>
        <p>Configure regras, percentuais, valores e parametros para calculos das bonificacoes.</p>
        <span class="financeiro-overview-pill">Operacional</span>
      </article>
      <article class="financeiro-overview-card financeiro-overview-card-orange">
        <div class="financeiro-overview-icon">${financeSettingsIcon("holidays")}</div>
        <h2>Feriados</h2>
        <p>Cadastre e gerencie feriados nacionais usados nas regras financeiras.</p>
        <span class="financeiro-overview-pill">Operacional</span>
      </article>
      <article class="financeiro-overview-card financeiro-overview-card-purple">
        <div class="financeiro-overview-icon">${financeSettingsIcon("audit")}</div>
        <h2>Auditoria e Divergencias</h2>
        <p>Acompanhe pendencias, ajustes e memoria dos dados financeiros.</p>
        <span class="financeiro-overview-pill">Resumo</span>
      </article>
    </section>

    <section class="financeiro-product-alert financeiro-product-alert-info">
      <strong>Importante</strong>
      <span>Os totais sao consumidos da API junto com snapshots e memorias; esta tela nao calcula valores financeiros.</span>
    </section>
  `;
}

function requestStateFromError(error, resourceLabel) {
  if (error?.status === 401 || error?.code === "unauthorized") {
    return {
      type: "no-permission",
      title: "Sessao expirada",
      detail: `Entre novamente para carregar ${resourceLabel}.`,
    };
  }
  if (error?.status === 403 || error?.code === "forbidden") {
    return {
      type: "no-permission",
      title: "Acesso negado",
      detail: `Seu perfil nao possui permissao para carregar ${resourceLabel}.`,
    };
  }
  if (error?.status === 501) {
    return {
      type: "warning",
      title: "Recurso ainda nao implementado",
      detail: `${resourceLabel} ainda nao esta disponivel neste ambiente.`,
    };
  }
  return {
    type: "error",
    title: `Nao foi possivel carregar ${resourceLabel}`,
    detail: buildErrorMessage(error),
  };
}

function governanceClassFromMotivo(motivo = "") {
  const match = String(motivo || "").match(/GOV_CLASS=([a-z0-9_-]+)/i);
  return match ? match[1].toLowerCase() : "";
}

function isActiveStatus(status = "") {
  return ["ativo", "active"].includes(String(status || "").trim().toLowerCase());
}

function parameterLegacyBadges(parameter) {
  const badges = [];
  const governanceClass = governanceClassFromMotivo(parameter?.motivo);
  if (!isActiveStatus(parameter?.status)) badges.push("inativo");
  if (String(parameter?.unidade || "").trim().toUpperCase() === "BRL") badges.push("BRL legado");
  if (["legacy", "deprecated", "qa-smoke"].includes(governanceClass)) badges.push(governanceClass);
  return badges;
}

function isLegacyOrInactiveParameter(parameter) {
  return parameterLegacyBadges(parameter).length > 0;
}

function renderParameterRows(parameters, canUpdate, { legacyMode = false } = {}) {
  if (!parameters.length) {
    return emptyTableRowMarkup(9, {
      title: "Nenhum parametro financeiro cadastrado.",
      detail: "Cadastre os parametros vigentes antes da etapa de calculo no backend.",
      type: "empty",
    });
  }
  return parameters
    .map((parameter) => {
      const badges = parameterLegacyBadges(parameter);
      return `
      <tr class="${legacyMode ? "financeiro-legacy-parameter-row" : ""}">
        <td><strong>${escapeHtml(parameter.tipo || "-")}</strong></td>
        <td>${escapeHtml(parameter.funcao || "-")}</td>
        <td>${escapeHtml(parameter.categoria || "-")}</td>
        <td>${escapeHtml(parameter.valor ?? "-")}</td>
        <td>
          ${escapeHtml(parameter.unidade || "-")}
          ${badges.length
            ? `<div class="financeiro-legacy-badges">${badges.map((badge) => `<span class="status-pill status-dark">${escapeHtml(badge)}</span>`).join("")}</div>`
            : ""}
        </td>
        <td>${escapeHtml(formatDateBr(parameter.vigencia_inicio))}</td>
        <td>${escapeHtml(formatDateBr(parameter.vigencia_fim))}</td>
        <td><span class="status-pill ${statusClass(parameter.status)}">${escapeHtml(parameter.status || "-")}</span></td>
        <td>
          <div class="ui-table-actions">
            <button
              type="button"
              class="button-link secondary ${legacyMode ? "financeiro-legacy-edit-button" : ""}"
              data-edit-parameter-id="${escapeAttr(parameter.id)}"
              title="${legacyMode ? "Parametro historico/legado: revise com cautela e mantenha trilha de governanca." : "Editar parametro ativo"}"
              ${canUpdate ? "" : "disabled"}
            >${legacyMode ? "Revisar legado" : "Editar"}</button>
          </div>
        </td>
      </tr>
    `;
    })
    .join("");
}

function renderHolidayRows(holidays, canUpdate) {
  if (!holidays.length) {
    return emptyTableRowMarkup(6, {
      title: "Nenhum feriado nacional cadastrado.",
      detail: "Apenas feriados nacionais entram nesta fase de parametrizacao.",
      type: "empty",
    });
  }
  return holidays
    .map((holiday) => `
      <tr>
        <td>${escapeHtml(formatDateBr(holiday.data))}</td>
        <td><strong>${escapeHtml(holiday.nome || "-")}</strong></td>
        <td>${escapeHtml(holiday.tipo || "nacional")}</td>
        <td>${escapeHtml(holiday.localidade || "-")}</td>
        <td><span class="status-pill ${statusClass(holiday.status)}">${escapeHtml(holiday.status || "-")}</span></td>
        <td>
          <div class="ui-table-actions">
            <button type="button" class="button-link secondary" data-edit-holiday-id="${escapeAttr(holiday.id)}" ${canUpdate ? "" : "disabled"}>Editar</button>
          </div>
        </td>
      </tr>
    `)
    .join("");
}

function recommendedUnitForParameterType(tipo) {
  return PARAMETER_DEFAULT_UNITS[String(tipo || "").trim()] || "";
}

function syncParameterUnitForType(form) {
  const typeInput = form?.elements?.tipo;
  const unitInput = form?.elements?.unidade;
  const valueInput = form?.elements?.valor;
  const functionInput = form?.elements?.funcao;
  if (!typeInput || !unitInput) return;
  const type = String(typeInput.value || "").trim();
  const recommendedUnit = recommendedUnitForParameterType(type);
  if (recommendedUnit) {
    unitInput.value = recommendedUnit;
  }
  if (valueInput) {
    valueInput.step = DAY_PERIOD_PARAMETER_TYPES.has(type) ? "1" : "0.01";
    valueInput.placeholder = DAY_PERIOD_PARAMETER_TYPES.has(type) ? "360" : "";
  }
  if (functionInput) {
    const globalParameter = GLOBAL_HOURLY_PARAMETER_TYPES.has(type);
    if (globalParameter) {
      functionInput.value = "";
    }
    functionInput.disabled = globalParameter;
    functionInput.placeholder = globalParameter ? "Nao se aplica" : "Opcional";
  }
}

function renderParameterForm(parameter, { canCreate, canUpdate }) {
  const editing = Boolean(parameter?.id);
  const canSubmit = editing ? canUpdate : canCreate;
  return `
    <form id="financeParameterForm" class="financeiro-settings-form ui-stack-sm" data-editing="${editing ? "true" : "false"}">
      <input type="hidden" name="id" value="${fieldValue(parameter, "id")}">
      <div class="financeiro-settings-form-head">
        <div>
          <h3>${editing ? "Editar parametro" : "Novo parametro"}</h3>
          <p>Vigencia e valores cadastrais para uso futuro pelo backend.</p>
        </div>
        ${editing ? `<button type="button" class="button-link secondary" data-clear-parameter-form>Cancelar edicao</button>` : ""}
      </div>
      <div id="financeParameterFormFeedback" aria-live="polite"></div>
      <div class="financeiro-settings-form-grid">
        <label>
          <span>Tipo</span>
          <select name="tipo" required>
            ${optionMarkup(PARAMETER_TYPES, parameter?.tipo)}
          </select>
        </label>
        <label>
          <span>Valor</span>
          <input type="number" step="0.01" name="valor" value="${fieldValue(parameter, "valor")}" required>
        </label>
        <label>
          <span>Unidade</span>
          <select name="unidade" required>
            ${optionMarkup(PARAMETER_UNITS, parameter?.unidade)}
          </select>
        </label>
        <label>
          <span>Status</span>
          <select name="status" required>
            ${optionMarkup(STATUS_OPTIONS, parameter?.status || "ativo")}
          </select>
        </label>
        <label>
          <span>Funcao</span>
          <input name="funcao" value="${fieldValue(parameter, "funcao")}" placeholder="Opcional">
        </label>
        <label>
          <span>Categoria</span>
          <input name="categoria" value="${fieldValue(parameter, "categoria")}" placeholder="Opcional">
        </label>
        <label>
          <span>Vigencia inicio</span>
          <input type="date" name="vigencia_inicio" value="${fieldValue(parameter, "vigencia_inicio")}" required>
        </label>
        <label>
          <span>Vigencia fim</span>
          <input type="date" name="vigencia_fim" value="${fieldValue(parameter, "vigencia_fim")}">
        </label>
        <label class="financeiro-settings-wide">
          <span>Motivo</span>
          <textarea name="motivo" rows="2" placeholder="Justificativa operacional da alteracao">${escapeHtml(parameter?.motivo || "")}</textarea>
        </label>
      </div>
      <p class="ui-field-help">Use minutos_do_dia para periodo_diurno_inicio/fim (ex.: 360 para 06:00 e 1080 para 18:00). O parametro duracao_hora_noturna_minutos aceita valor 52.5 e unidade minutos. Esta tela apenas cadastra parametros.</p>
      <div class="form-actions ui-form-actions">
        <button type="submit" ${canSubmit ? "" : "disabled"}>${editing ? "Salvar parametro" : "Cadastrar parametro"}</button>
      </div>
    </form>
  `;
}

function renderHolidayForm(holiday, { canCreate, canUpdate }) {
  const editing = Boolean(holiday?.id);
  const canSubmit = editing ? canUpdate : canCreate;
  return `
    <form id="financeHolidayForm" class="financeiro-settings-form ui-stack-sm" data-editing="${editing ? "true" : "false"}">
      <input type="hidden" name="id" value="${fieldValue(holiday, "id")}">
      <div class="financeiro-settings-form-head">
        <div>
          <h3>${editing ? "Editar feriado nacional" : "Novo feriado nacional"}</h3>
          <p>Nesta fase somente feriados nacionais sao aceitos.</p>
        </div>
        ${editing ? `<button type="button" class="button-link secondary" data-clear-holiday-form>Cancelar edicao</button>` : ""}
      </div>
      <div id="financeHolidayFormFeedback" aria-live="polite"></div>
      <div class="financeiro-settings-form-grid">
        <label>
          <span>Data</span>
          <input type="date" name="data" value="${fieldValue(holiday, "data")}" required>
        </label>
        <label>
          <span>Nome</span>
          <input name="nome" value="${fieldValue(holiday, "nome")}" required>
        </label>
        <label>
          <span>Tipo</span>
          <select name="tipo" required>
            <option value="nacional" selected>nacional</option>
          </select>
        </label>
        <label>
          <span>Status</span>
          <select name="status" required>
            ${optionMarkup(STATUS_OPTIONS, holiday?.status || "ativo")}
          </select>
        </label>
        <label class="financeiro-settings-wide">
          <span>Localidade</span>
          <input name="localidade" value="${fieldValue(holiday, "localidade")}" placeholder="Vazio para feriado nacional">
        </label>
      </div>
      <p class="ui-field-help">Localidade permanece vazia para feriado nacional; feriados estaduais, municipais e operacionais ficam fora desta etapa.</p>
      <div class="form-actions ui-form-actions">
        <button type="submit" ${canSubmit ? "" : "disabled"}>${editing ? "Salvar feriado" : "Cadastrar feriado"}</button>
      </div>
    </form>
  `;
}

function renderPeriodSummaryCards(totals = {}, divergenceCount = null) {
  const resolvedDivergenceCount = divergenceCount === null
    ? displayValue(totals.divergence_count, "0")
    : String(divergenceCount);
  const cards = [
    {
      label: "Total horario",
      value: formatCurrencyBr(totals.total_horario),
      detail: "Retornado pela API de competencia.",
    },
    {
      label: "Total produtividade",
      value: formatCurrencyBr(totals.total_produtividade),
      detail: "Consolidado pelo backend.",
    },
    {
      label: "Total geral",
      value: formatCurrencyBr(totals.total_geral),
      detail: "Snapshot mensal da API.",
    },
    {
      label: "Pendencias",
      value: resolvedDivergenceCount,
      detail: "Divergencias retornadas no fechamento.",
    },
  ];
  return `
    <div class="financeiro-settings-card-grid" data-finance-period-totals>
      ${cards
        .map((card) => `
          <article class="financeiro-settings-card">
            <h3>${escapeHtml(card.label)}</h3>
            <strong>${escapeHtml(card.value)}</strong>
            <p>${escapeHtml(card.detail)}</p>
          </article>
        `)
        .join("")}
    </div>
  `;
}

function renderDivergenceRows(divergences = []) {
  if (!divergences.length) {
    return emptyTableRowMarkup(6, {
      title: "Sem divergencias registradas",
      detail: "Nenhuma divergencia financeira retornada para os filtros atuais.",
      type: "empty",
    });
  }
  return divergences
    .map((item) => {
      const details = item.details || item.detalhes || item.contexto || "";
      const detailText = typeof details === "string" ? details : JSON.stringify(details);
      return `
        <tr>
          <td><span class="status-pill ${statusClass(item.severity || item.severidade)}">${escapeHtml(displayValue(item.severity || item.severidade))}</span></td>
          <td>${escapeHtml(displayValue(item.status))}</td>
          <td>${escapeHtml(displayValue(item.code || item.codigo))}</td>
          <td>${escapeHtml(displayValue(item.message || item.mensagem))}</td>
          <td>${escapeHtml(displayValue(detailText))}</td>
          <td>${escapeHtml(displayValue(item.next_action || item.acao_sugerida))}</td>
        </tr>
      `;
    })
    .join("");
}

function renderSnapshotSummary(period = {}, snapshot = {}, totals = {}) {
  const rows = [
    ["Versao", snapshot?.snapshot_version],
    ["Gerado em", formatDateTimeBr(snapshot?.generated_at)],
    ["Gerado por", snapshot?.generated_by],
    ["Missoes consideradas", totals?.mission_count],
    ["Calculos horarios", totals?.hourly_calculation_count],
    ["Calculos produtividade", totals?.productivity_calculation_count],
    ["Parametros usados", Array.isArray(snapshot?.parametros_usados) ? snapshot.parametros_usados.length : "-"],
    ["Fechado por", period?.closed_by],
    ["Fechado em", formatDateTimeBr(period?.closed_at)],
  ];
  return `
    <div class="financeiro-settings-card" data-finance-period-snapshot>
      <h3>Snapshot resumido</h3>
      <p>Resumo retornado pela API para memoria de fechamento.</p>
      <dl class="financeiro-detail-grid">
        ${rows
          .map(([label, value]) => `
            <div>
              <dt>${escapeHtml(label)}</dt>
              <dd>${escapeHtml(displayValue(value))}</dd>
            </div>
          `)
          .join("")}
      </dl>
    </div>
  `;
}

function renderPreflightItemLabel(item) {
  const message = displayValue(item?.message || item?.mensagem || item?.code || item?.codigo || item?.tipo || item?.field, "");
  const nextAction = displayValue(item?.next_action || item?.nextAction || item?.acao_sugerida, "");
  if (message && nextAction) return `${message} | Proxima acao: ${nextAction}`;
  return message || nextAction || displayValue(item, "-");
}

function renderPreflightCollection(title, items = [], emptyLabel) {
  if (!items.length) {
    return `
      <article class="financeiro-settings-card financeiro-gate-card">
        <h4>${escapeHtml(title)}</h4>
        <p>${escapeHtml(emptyLabel)}</p>
      </article>
    `;
  }
  return `
    <article class="financeiro-settings-card financeiro-gate-card">
      <h4>${escapeHtml(title)}</h4>
      <ul class="financeiro-preflight-list">
        ${items.map((item) => `<li>${escapeHtml(renderPreflightItemLabel(item))}</li>`).join("")}
      </ul>
    </article>
  `;
}

function renderGateSummary({ preflightState, period }) {
  if (preflightState.status === "loading") {
    return responsiveStateMarkup({
      title: "Carregando gate de elegibilidade",
      detail: "Consultando preflight de competencia no backend.",
      type: "loading",
      compact: true,
    });
  }
  if (preflightState.status === "forbidden") {
    return responsiveStateMarkup({
      title: "Sem permissao para preflight",
      detail: "Seu perfil nao possui acesso ao preflight da competencia.",
      type: "no-permission",
      compact: true,
    });
  }
  if (preflightState.status === "error") {
    return responsiveStateMarkup({
      title: "Gate indisponivel",
      detail: buildErrorMessage(preflightState.error),
      type: "error",
      compact: true,
    });
  }

  const preflight = preflightState.data || preflightPayloadFromApi({});
  const gateApproved = preflight.fechavel === true;
  const gateStatusClass = gateApproved ? "status-green" : "status-red";
  const gateStatusLabel = gateApproved ? "gate aprovado" : "gate reprovado";
  const statusLabel = displayValue(preflight.competenciaStatus || period?.status || "aberta");
  return `
    <section class="financeiro-gate-section ui-stack-sm" data-finance-period-gate>
      <div class="financeiro-settings-section-head">
        <div>
          <h3>Gate de elegibilidade / preflight</h3>
          <p>A elegibilidade para fechamento real e decidida exclusivamente pelo backend.</p>
        </div>
        <span class="status-pill ${gateStatusClass}">${escapeHtml(gateStatusLabel)}</span>
      </div>
      <div class="financeiro-settings-card-grid">
        <article class="financeiro-settings-card">
          <h4>Competencia selecionada</h4>
          <strong>${escapeHtml(formatCompetenciaLabel(period?.competencia || currentSettingsState.competencia))}</strong>
          <p>Status: ${escapeHtml(statusLabel)}</p>
        </article>
        <article class="financeiro-settings-card">
          <h4>Calculavel?</h4>
          <strong>${escapeHtml(boolLabel(preflight.calculavel))}</strong>
          <p>Retorno do endpoint preflight.</p>
        </article>
        <article class="financeiro-settings-card">
          <h4>Fechavel?</h4>
          <strong>${escapeHtml(boolLabel(preflight.fechavel))}</strong>
          <p>Se for "Nao", o botao Fechar fica bloqueado.</p>
        </article>
        <article class="financeiro-settings-card">
          <h4>Next action</h4>
          <strong>${escapeHtml(displayValue(preflight.nextAction))}</strong>
          <p>Orientacao operacional entregue pelo backend.</p>
        </article>
      </div>
      <div class="financeiro-settings-card-grid">
        ${renderPreflightCollection("Bloqueios", preflight.bloqueios, "Sem bloqueios retornados.")}
        ${renderPreflightCollection("Parametros faltantes", preflight.parametrosFaltantes, "Nenhum parametro faltante.")}
        ${renderPreflightCollection("Parametros invalidos", preflight.parametrosInvalidos, "Nenhum parametro invalido.")}
        ${renderPreflightCollection("Parametros nao elegiveis", preflight.parametrosNaoElegiveis, "Nenhum parametro nao elegivel.")}
        ${renderPreflightCollection("Parametros ambiguos", preflight.parametrosAmbiguos, "Nenhum parametro ambiguo.")}
        ${renderPreflightCollection("Dados QA detectados", preflight.dadosQaDetectados, "Nenhum dado QA detectado.")}
        ${renderPreflightCollection("Divergencias do gate", preflight.divergencias, "Sem divergencias no gate.")}
      </div>
    </section>
  `;
}

function renderAuditRows(items = []) {
  if (!items.length) {
    return emptyTableRowMarkup(5, {
      title: "Sem eventos de auditoria para a competencia",
      detail: "Nao houve eventos no recorte atual.",
      type: "empty",
    });
  }
  return items
    .map((item) => {
      const eventName = displayValue(item.event_name || item.acao);
      const entity = `${displayValue(item.entity_type || item.entidade_tipo, "-")} #${displayValue(item.entity_id || item.entidade_id, "-")}`;
      const actor = displayValue(item.actor_user_name || item.actor_name || item.usuario || item.actor_user_id);
      const requestLabel = displayValue(item.request_id, "-");
      const correlationLabel = displayValue(item.correlation_id, "-");
      const requestCell = requestLabel !== "-" || correlationLabel !== "-" ? `${requestLabel} / ${correlationLabel}` : "-";
      return `
        <tr>
          <td>${escapeHtml(eventName)}</td>
          <td>${escapeHtml(formatDateTimeBr(item.occurred_at || item.created_at || item.data_evento))}</td>
          <td>${escapeHtml(entity)}</td>
          <td>${escapeHtml(actor)}</td>
          <td>${escapeHtml(requestCell)}</td>
        </tr>
      `;
    })
    .join("");
}

function renderAuditSection({ auditState, competencia, capabilities }) {
  const canRead = capabilities.has(AUDIT_READ_PERMISSION);
  const filters = auditState.filters || defaultAuditFilters(competencia);
  const openAttr = shouldOpenHeavySection() ? "open" : "";
  return `
    <section class="panel ui-surface ui-stack" data-finance-audit-section>
      <details class="financeiro-heavy-section-disclosure" ${openAttr}>
        <summary>Auditoria</summary>
        <div class="financeiro-heavy-section-disclosure-body ui-stack-sm">
          <p>Eventos recentes da competencia retornados por endpoint real.</p>
          <form id="financeAuditFiltersForm" class="financeiro-settings-form-grid">
            <label><span>Event name</span><input name="eventName" value="${escapeAttr(filters.eventName || "")}" placeholder="finance.period.closed"></label>
            <label><span>Entity type</span><input name="entityType" value="${escapeAttr(filters.entityType || "")}" placeholder="finance_period"></label>
            <label><span>Limite</span><input type="number" min="1" max="200" name="limit" value="${escapeAttr(filters.limit || 20)}"></label>
            <div class="form-actions ui-form-actions">
              <button type="submit" ${canRead ? "" : "disabled"}>Atualizar auditoria</button>
            </div>
          </form>
          ${!canRead
            ? responsiveStateMarkup({
              title: "Auditoria indisponivel",
              detail: "Seu perfil nao possui finance:audit:read.",
              type: "no-permission",
              compact: true,
            })
            : auditState.status === "loading"
              ? responsiveStateMarkup({
                title: "Carregando auditoria",
                detail: "Consultando endpoint real de auditoria financeira.",
                type: "loading",
                compact: true,
              })
              : auditState.status === "error"
                ? responsiveStateMarkup({
                  title: "Auditoria indisponivel",
                  detail: buildErrorMessage(auditState.error),
                  type: "error",
                  compact: true,
                })
                : `
                  <div class="table-wrap ui-table-wrap ui-table-density-compact">
                    <table class="data-table responsive-cards">
                      <thead>
                        <tr>
                          <th>Evento</th>
                          <th>Data</th>
                          <th>Entidade</th>
                          <th>Usuario/ator</th>
                          <th>Request/Correlation</th>
                        </tr>
                      </thead>
                      <tbody>${renderAuditRows(auditState.items)}</tbody>
                    </table>
                  </div>
                `}
        </div>
      </details>
    </section>
  `;
}

function renderDivergencesSection({ divergencesState, competencia, capabilities }) {
  const canRead = capabilities.has(DIVERGENCES_READ_PERMISSION);
  const filters = divergencesState.filters || defaultDivergenceFilters(competencia);
  const openAttr = shouldOpenHeavySection() ? "open" : "";
  return `
    <section class="panel ui-surface ui-stack" data-finance-divergences-section>
      <details class="financeiro-heavy-section-disclosure" ${openAttr}>
        <summary>Pendencias e divergencias</summary>
        <div class="financeiro-heavy-section-disclosure-body ui-stack-sm">
          <p>Leitura direta do endpoint real de divergencias financeiras.</p>
          <form id="financeDivergencesFiltersForm" class="financeiro-settings-form-grid">
            <label><span>Status</span><input name="status" value="${escapeAttr(filters.status || "")}" placeholder="aberta"></label>
            <label><span>Severidade</span><input name="severidade" value="${escapeAttr(filters.severidade || "")}" placeholder="alta/media"></label>
            <label><span>Codigo</span><input name="codigo" value="${escapeAttr(filters.codigo || "")}" placeholder="parametro_ausente"></label>
            <label><span>Limite</span><input type="number" min="1" max="200" name="limit" value="${escapeAttr(filters.limit || 20)}"></label>
            <div class="form-actions ui-form-actions">
              <button type="submit" ${canRead ? "" : "disabled"}>Atualizar divergencias</button>
            </div>
          </form>
          ${!canRead
            ? responsiveStateMarkup({
              title: "Divergencias indisponiveis",
              detail: "Seu perfil nao possui finance:divergences:read.",
              type: "no-permission",
              compact: true,
            })
            : divergencesState.status === "loading"
              ? responsiveStateMarkup({
                title: "Carregando divergencias",
                detail: "Consultando endpoint real de divergencias.",
                type: "loading",
                compact: true,
              })
              : divergencesState.status === "error"
                ? responsiveStateMarkup({
                  title: "Divergencias indisponiveis",
                  detail: buildErrorMessage(divergencesState.error),
                  type: "error",
                  compact: true,
                })
                : `
                  <div class="table-wrap ui-table-wrap ui-table-density-compact">
                    <table class="data-table responsive-cards">
                      <thead>
                        <tr>
                          <th>Severidade</th>
                          <th>Status</th>
                          <th>Codigo</th>
                          <th>Mensagem</th>
                          <th>Detalhes</th>
                          <th>Acao sugerida</th>
                        </tr>
                      </thead>
                      <tbody>${renderDivergenceRows(divergencesState.items)}</tbody>
                    </table>
                  </div>
                `}
        </div>
      </details>
    </section>
  `;
}

function renderPdfSection({ period, pdfState }) {
  const kindLabel = resolvePdfKindLabel(period, pdfState?.kind || "");
  return `
    <section class="panel ui-surface ui-stack" data-finance-pdf-section>
      <div class="financeiro-settings-section-head">
        <div>
          <h3>PDF</h3>
          <p>Download de ${escapeHtml(kindLabel)} consumindo endpoint real da competencia.</p>
        </div>
      </div>
      ${pdfState?.status === "error"
        ? responsiveStateMarkup({
          title: "PDF indisponivel",
          detail: displayValue(pdfState.message, "Nao foi possivel baixar o PDF."),
          type: "error",
          compact: true,
        })
        : responsiveStateMarkup({
          title: kindLabel,
          detail: displayValue(pdfState?.message, "O PDF e gerado no backend sem recalculo no frontend."),
          type: "info",
          compact: true,
        })}
    </section>
  `;
}

function renderPeriodActions({ period, competencia, capabilities, preflightState }) {
  const status = String(period?.status || "aberta").trim().toLowerCase();
  const isClosed = status === "fechada";
  const preflight = preflightState.status === "ready" ? preflightState.data : null;
  const gateAllowsClose = preflight?.fechavel === true
    && preflight?.canExecuteActions?.fechar_competencia !== false;
  const canRecalculate = capabilities.has(PERIOD_RECALCULATE_PERMISSION)
    && !isClosed
    && (preflight ? preflight.canExecuteActions?.recalcular_competencia !== false : true);
  const canClose = capabilities.has(PERIOD_CLOSE_PERMISSION) && !isClosed && gateAllowsClose;
  const canReopen = capabilities.has(PERIOD_REOPEN_PERMISSION) && isClosed;
  const canExportPdf = capabilities.has(EXPORT_CREATE_PERMISSION);

  let closeBlockReason = "";
  if (!capabilities.has(PERIOD_CLOSE_PERMISSION)) {
    closeBlockReason = "Seu perfil nao possui permissao para fechar competencia.";
  } else if (isClosed) {
    closeBlockReason = "A competencia ja esta fechada.";
  } else if (preflightState.status !== "ready") {
    closeBlockReason = "Nao foi possivel validar o gate de fechamento.";
  } else if (!gateAllowsClose) {
    closeBlockReason = renderPreflightItemLabel((preflight?.bloqueios || [])[0] || { message: preflight?.nextAction || "Gate reprovado para fechamento." });
  }

  return `
    <section class="ui-stack-sm" data-finance-period-actions-section>
      <div class="financeiro-settings-form-head">
        <div>
          <h3>Acoes principais</h3>
          <p>Recalcular, Fechar, Baixar PDF e Reabrir seguem gate e RBAC do backend.</p>
        </div>
      </div>
      <div id="financePeriodActionFeedback" aria-live="polite"></div>
      <div class="form-actions ui-form-actions" data-finance-period-actions>
        <button type="button" id="financePeriodRecalculateButton" data-required-permission="${PERIOD_RECALCULATE_PERMISSION}" ${canRecalculate ? "" : "disabled"}>Recalcular competencia</button>
        <button type="button" id="financePeriodCloseButton" data-required-permission="${PERIOD_CLOSE_PERMISSION}" ${canClose ? "" : "disabled"}>Fechar competencia</button>
        <button type="button" class="button-link secondary" id="financePeriodPdfButton" data-required-permission="${EXPORT_CREATE_PERMISSION}" ${canExportPdf ? "" : "disabled"}>Baixar relatorio PDF</button>
        <button type="button" class="button-link secondary" id="financePeriodReopenButton" data-required-permission="${PERIOD_REOPEN_PERMISSION}" ${canReopen ? "" : "disabled"}>Reabrir competencia</button>
      </div>
      ${closeBlockReason
        ? `<p class="ui-field-help">Fechar bloqueado: ${escapeHtml(closeBlockReason)}</p>`
        : `<p class="ui-field-help">Competencia selecionada: ${escapeHtml(formatCompetenciaLabel(competencia))}. O frontend nao calcula nem decide gate.</p>`}
    </section>
  `;
}

function renderMonthlyClosingSection({
  periodState,
  preflightState,
  divergencesState,
  auditState,
  pdfState,
  competencia,
  capabilities,
}) {
  const canReadPeriods = capabilities.has(PERIOD_READ_PERMISSION);
  const period = periodState.period || { competencia, status: "aberta" };
  const snapshot = periodState.snapshot || {};
  const totals = periodState.totals || {};
  const divergenceCount = divergencesState.status === "ready"
    ? divergencesState.items.length
    : Number(totals?.divergence_count || 0);
  return `
    <section class="panel ui-surface ui-stack" data-finance-section="monthly-closing">
      <div class="financeiro-settings-section-head">
        <div>
          <h2>Fechamento Mensal</h2>
          <p>Operacao mensal com gate de elegibilidade, observabilidade real e trilha de auditoria.</p>
        </div>
        <span class="status-pill ${statusClass(period.status)}">${escapeHtml(period.status || "aberta")}</span>
      </div>
      <form id="financePeriodSelectorForm" class="financeiro-settings-form-grid">
        <label>
          <span>Competencia</span>
          <input type="month" name="competencia" value="${escapeAttr(competencia)}" required>
        </label>
        <div class="form-actions ui-form-actions">
          <button type="submit">Consultar</button>
          <a class="button-link secondary" href="${escapeAttr(buildHashHref(FINANCEIRO_FECHAMENTO_PARAMETROS_ROUTE, { competencia: currentCompetencia() }))}">Mes atual</a>
        </div>
      </form>
      ${canReadPeriods
        ? renderLoadState(periodState, "fechamento mensal")
        : responsiveStateMarkup({
          title: "Acesso restrito",
          detail: "Seu perfil ainda nao possui finance:periods:read para acompanhar esta area.",
          type: "no-permission",
          compact: true,
        })}
      ${periodState.status === "ready" && canReadPeriods ? renderGateSummary({ preflightState, period }) : ""}
      ${periodState.status === "ready" && canReadPeriods ? renderPeriodActions({ period, competencia, capabilities, preflightState }) : ""}
      ${periodState.status === "ready" && canReadPeriods ? renderPeriodSummaryCards(totals, divergenceCount) : ""}
      ${periodState.status === "ready" && canReadPeriods ? renderDivergencesSection({ divergencesState, competencia, capabilities }) : ""}
      ${periodState.status === "ready" && canReadPeriods ? renderPdfSection({ period, pdfState }) : ""}
      ${periodState.status === "ready" && canReadPeriods ? renderAuditSection({ auditState, competencia, capabilities }) : ""}
      ${periodState.status === "ready" && canReadPeriods
        ? `
          <div class="financeiro-settings-layout">
            <aside class="financeiro-settings-side ui-stack-sm">
              ${renderSnapshotSummary(period, snapshot, totals)}
            </aside>
          </div>
        `
        : ""}
    </section>
  `;
}

function renderLoadState(state, resourceLabel) {
  if (state.status === "forbidden") {
    return responsiveStateMarkup({
      title: "Acesso negado",
      detail: `Seu perfil nao possui permissao para carregar ${resourceLabel}.`,
      type: "no-permission",
      compact: true,
    });
  }
  if (state.status === "error") {
    return responsiveStateMarkup({
      ...requestStateFromError(state.error, resourceLabel),
      compact: true,
    });
  }
  return "";
}

function renderParametersSection({ parametersState, selectedParameter, capabilities }) {
  const canCreate = capabilities.has(PARAMETER_CREATE_PERMISSION);
  const canUpdate = capabilities.has(PARAMETER_UPDATE_PERMISSION);
  const parameters = Array.isArray(parametersState.items) ? parametersState.items : [];
  const operationalParameters = parameters.filter((parameter) => !isLegacyOrInactiveParameter(parameter));
  const legacyParameters = parameters.filter(isLegacyOrInactiveParameter);
  return `
    <section class="panel ui-surface ui-stack" data-finance-section="parameters">
      <div class="financeiro-settings-section-head">
        <div>
          <h2>Parametros Financeiros</h2>
          <p>Cadastro de vigencias consumido futuramente pelos calculos do backend.</p>
        </div>
        <span class="status-pill status-green">API ativa</span>
      </div>
      ${renderLoadState(parametersState, "parametros financeiros")}
      <div class="financeiro-settings-layout">
        <div class="table-wrap ui-table-wrap ui-table-density-compact">
          <table class="data-table responsive-cards">
            <thead>
              <tr>
                <th>Tipo</th>
                <th>Funcao</th>
                <th>Categoria</th>
                <th>Valor</th>
                <th>Unidade</th>
                <th>Inicio</th>
                <th>Fim</th>
                <th>Status</th>
              <th>Acoes</th>
              </tr>
            </thead>
            <tbody>
              ${renderParameterRows(operationalParameters, canUpdate)}
            </tbody>
          </table>
          <details class="financeiro-legacy-parameters-disclosure">
            <summary>Historico/Legado (${legacyParameters.length})</summary>
            <p class="ui-field-help">Parametros inativos, BRL ou classificados como legado ficam separados do fluxo operacional. Eles sao preservados para auditoria e devem ser revisados com cautela.</p>
            <table class="data-table responsive-cards">
              <thead>
                <tr>
                  <th>Tipo</th>
                  <th>Funcao</th>
                  <th>Categoria</th>
                  <th>Valor</th>
                  <th>Unidade</th>
                  <th>Inicio</th>
                  <th>Fim</th>
                  <th>Status</th>
                  <th>Acoes</th>
                </tr>
              </thead>
              <tbody>
                ${renderParameterRows(legacyParameters, canUpdate, { legacyMode: true })}
              </tbody>
            </table>
          </details>
        </div>
        <aside class="financeiro-settings-side">
          ${renderParameterForm(selectedParameter || parameterDraft(), { canCreate, canUpdate })}
        </aside>
      </div>
    </section>
  `;
}

function renderHolidaysSection({ holidaysState, selectedHoliday, capabilities }) {
  const canCreate = capabilities.has(PARAMETER_CREATE_PERMISSION);
  const canUpdate = capabilities.has(PARAMETER_UPDATE_PERMISSION);
  return `
    <section class="panel ui-surface ui-stack" data-finance-section="holidays">
      <div class="financeiro-settings-section-head">
        <div>
          <h2>Feriados</h2>
          <p>Feriados nacionais usados como referencia operacional para etapas futuras.</p>
        </div>
        <span class="status-pill status-green">Nacionais</span>
      </div>
      ${renderLoadState(holidaysState, "feriados nacionais")}
      <div class="financeiro-settings-layout">
        <div class="table-wrap ui-table-wrap ui-table-density-compact">
          <table class="data-table responsive-cards">
            <thead>
              <tr>
                <th>Data</th>
                <th>Nome</th>
                <th>Tipo</th>
                <th>Localidade</th>
                <th>Status</th>
                <th>Acoes</th>
              </tr>
            </thead>
            <tbody>
              ${renderHolidayRows(holidaysState.items, canUpdate)}
            </tbody>
          </table>
        </div>
        <aside class="financeiro-settings-side">
          ${renderHolidayForm(selectedHoliday || holidayDraft(), { canCreate, canUpdate })}
        </aside>
      </div>
    </section>
  `;
}

function parameterPayload(form) {
  const data = Object.fromEntries(new FormData(form).entries());
  return {
    tipo: String(data.tipo || "").trim(),
    funcao: nullableValue(data.funcao),
    categoria: nullableValue(data.categoria),
    valor: String(data.valor || "").trim(),
    unidade: String(data.unidade || "").trim(),
    vigencia_inicio: String(data.vigencia_inicio || "").trim(),
    vigencia_fim: nullableValue(data.vigencia_fim),
    status: String(data.status || "ativo").trim(),
    motivo: nullableValue(data.motivo),
  };
}

function holidayPayload(form) {
  const data = Object.fromEntries(new FormData(form).entries());
  return {
    data: String(data.data || "").trim(),
    nome: String(data.nome || "").trim(),
    tipo: "nacional",
    localidade: null,
    status: String(data.status || "ativo").trim(),
  };
}

async function refreshPage() {
  await renderFinanceiroFechamentoParametrosPage();
}

function wireParameterForm() {
  const form = document.getElementById("financeParameterForm");
  const feedback = document.getElementById("financeParameterFormFeedback");
  if (form) {
    syncParameterUnitForType(form);
    form.elements.tipo?.addEventListener("change", () => syncParameterUnitForType(form));
  }
  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector("button[type='submit']");
    const parameterId = Number(form.elements.id?.value || 0);
    const capabilities = capabilitySet();
    const allowed = parameterId
      ? capabilities.has(PARAMETER_UPDATE_PERMISSION)
      : capabilities.has(PARAMETER_CREATE_PERMISSION);
    if (!allowed) {
      renderInlineFeedback(feedback, "Seu perfil nao possui permissao para salvar parametros financeiros.", "warning");
      return;
    }
    await withActionBusy(button, "Salvando...", async () => {
      try {
        const payload = parameterPayload(form);
        if (parameterId) {
          await updateFinanceiroParametro(parameterId, payload);
          showFlash("Parametro financeiro atualizado.", "success");
        } else {
          await createFinanceiroParametro(payload);
          showFlash("Parametro financeiro cadastrado.", "success");
        }
        await refreshPage();
      } catch (error) {
        renderInlineFeedback(feedback, buildErrorMessage(error), error.status === 403 ? "warning" : "error");
      }
    });
  });
  document.querySelector("[data-clear-parameter-form]")?.addEventListener("click", () => {
    renderFinanceiroFechamentoParametros(currentSettingsState, { selectedParameter: null, selectedHoliday: null });
  });
}

function wireHolidayForm() {
  const form = document.getElementById("financeHolidayForm");
  const feedback = document.getElementById("financeHolidayFormFeedback");
  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector("button[type='submit']");
    const holidayId = Number(form.elements.id?.value || 0);
    const capabilities = capabilitySet();
    const allowed = holidayId
      ? capabilities.has(PARAMETER_UPDATE_PERMISSION)
      : capabilities.has(PARAMETER_CREATE_PERMISSION);
    if (!allowed) {
      renderInlineFeedback(feedback, "Seu perfil nao possui permissao para salvar feriados nacionais.", "warning");
      return;
    }
    await withActionBusy(button, "Salvando...", async () => {
      try {
        const payload = holidayPayload(form);
        if (holidayId) {
          await updateFinanceiroFeriado(holidayId, payload);
          showFlash("Feriado nacional atualizado.", "success");
        } else {
          await createFinanceiroFeriado(payload);
          showFlash("Feriado nacional cadastrado.", "success");
        }
        await refreshPage();
      } catch (error) {
        renderInlineFeedback(feedback, buildErrorMessage(error), error.status === 403 ? "warning" : "error");
      }
    });
  });
  document.querySelector("[data-clear-holiday-form]")?.addEventListener("click", () => {
    renderFinanceiroFechamentoParametros(currentSettingsState, { selectedParameter: null, selectedHoliday: null });
  });
}

function wireEditButtons() {
  document.querySelectorAll("[data-edit-parameter-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const selectedParameter = currentSettingsState.parameters.find((item) => String(item.id) === String(button.dataset.editParameterId));
      activeSettingsMobileSection = "parameters";
      renderFinanceiroFechamentoParametros(currentSettingsState, { selectedParameter, selectedHoliday: null });
    });
  });
  document.querySelectorAll("[data-edit-holiday-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const selectedHoliday = currentSettingsState.holidays.find((item) => String(item.id) === String(button.dataset.editHolidayId));
      activeSettingsMobileSection = "holidays";
      renderFinanceiroFechamentoParametros(currentSettingsState, { selectedParameter: null, selectedHoliday });
    });
  });
}

function wirePeriodControls() {
  document.getElementById("financePeriodSelectorForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const competencia = String(new FormData(event.currentTarget).get("competencia") || "").trim();
    const nextHash = buildHashHref(FINANCEIRO_FECHAMENTO_PARAMETROS_ROUTE, { competencia });
    if (window.location.hash === nextHash) {
      await renderFinanceiroFechamentoParametrosPage();
      return;
    }
    window.location.hash = nextHash;
  });

  const feedback = document.getElementById("financePeriodActionFeedback");
  const runAction = async (button, busyLabel, action) => {
    if (!button || button.disabled) return;
    await withActionBusy(button, busyLabel, async () => {
      try {
        await action();
        await refreshPage();
      } catch (error) {
        renderInlineFeedback(feedback, buildErrorMessage(error), error.status === 403 ? "warning" : "error");
      }
    });
  };

  document.getElementById("financePeriodRecalculateButton")?.addEventListener("click", async (event) => {
    await runAction(event.currentTarget, "Recalculando...", async () => {
      await recalculateFinanceiroCompetencia(currentSettingsState.competencia);
      showFlash("Competencia recalculada pelo backend.", "success");
    });
  });

  document.getElementById("financePeriodPdfButton")?.addEventListener("click", async (event) => {
    await withActionBusy(event.currentTarget, "Gerando PDF...", async () => {
      try {
        const result = await downloadFinanceiroCompetenciaPdf(currentSettingsState.competencia);
        const kindLabel = resolvePdfKindLabel(currentSettingsState.periodState?.period, result.filename);
        downloadBlob(result.blob, result.filename);
        currentSettingsState.pdfState = {
          status: "ready",
          kind: result.filename,
          message: `${kindLabel} baixado com sucesso (${result.filename}).`,
        };
        renderInlineFeedback(feedback, `${kindLabel} baixado com sucesso.`, "success");
        showFlash(`${kindLabel} baixado.`, "success");
      } catch (error) {
        let message = buildErrorMessage(error);
        if (error?.status === 401) message = "Sessao expirada para gerar PDF. Entre novamente.";
        if (error?.status === 403) message = "Seu perfil nao possui permissao para gerar PDF.";
        if (error?.status === 404) message = "PDF indisponivel para esta competencia no momento.";
        if (error?.status === 409) message = "PDF bloqueado pelo backend para o estado atual da competencia.";
        if (error?.status >= 500) message = "Falha operacional ao gerar PDF no backend.";
        currentSettingsState.pdfState = {
          status: "error",
          kind: "",
          message,
        };
        renderInlineFeedback(feedback, message, error.status === 403 ? "warning" : "error");
        renderFinanceiroFechamentoParametros(currentSettingsState);
      }
    });
  });

  document.getElementById("financePeriodCloseButton")?.addEventListener("click", async (event) => {
    const preflight = currentSettingsState.preflightState?.data || null;
    if (!preflight || preflight.fechavel !== true) {
      const firstBlock = (preflight?.bloqueios || [])[0] || {};
      const reason = renderPreflightItemLabel(firstBlock) || preflight?.nextAction || "Gate de elegibilidade reprovado.";
      renderInlineFeedback(feedback, `Fechamento bloqueado: ${reason}`, "warning");
      return;
    }
    if (!confirmAction({
      title: "Fechar competencia financeira?",
      subject: formatCompetenciaLabel(currentSettingsState.competencia),
      consequence: "O backend vai congelar snapshot, totais e memoria de calculo da competencia.",
    })) {
      return;
    }
    await runAction(event.currentTarget, "Fechando...", async () => {
      await closeFinanceiroCompetencia(currentSettingsState.competencia, {
        motivo: "Fechamento confirmado pela interface operacional.",
      });
      showFlash("Competencia financeira fechada.", "success");
    });
  });

  document.getElementById("financePeriodReopenButton")?.addEventListener("click", async (event) => {
    const motivo = String(window.prompt("Informe o motivo da reabertura da competencia:") || "").trim();
    if (!motivo) {
      renderInlineFeedback(feedback, "Motivo de reabertura e obrigatorio.", "warning");
      return;
    }
    if (!confirmAction({
      title: "Reabrir competencia financeira?",
      subject: formatCompetenciaLabel(currentSettingsState.competencia),
      consequence: "A competencia voltara a aceitar mutacoes autorizadas conforme regra do backend.",
    })) {
      return;
    }
    await runAction(event.currentTarget, "Reabrindo...", async () => {
      await reopenFinanceiroCompetencia(currentSettingsState.competencia, { motivo });
      showFlash("Competencia financeira reaberta.", "success");
    });
  });
}

function wireObservabilityFilters() {
  document.getElementById("financeAuditFiltersForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
    currentSettingsState.auditState = {
      ...currentSettingsState.auditState,
      filters: {
        ...currentSettingsState.auditState.filters,
        competencia: currentSettingsState.competencia,
        eventName: String(payload.eventName || "").trim(),
        entityType: String(payload.entityType || "").trim(),
        limit: Math.max(1, Number(payload.limit || 20) || 20),
        offset: 0,
      },
    };
    await refreshPage();
  });

  document.getElementById("financeDivergencesFiltersForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
    currentSettingsState.divergencesState = {
      ...currentSettingsState.divergencesState,
      filters: {
        ...currentSettingsState.divergencesState.filters,
        competencia: currentSettingsState.competencia,
        status: String(payload.status || "").trim(),
        severidade: String(payload.severidade || "").trim(),
        codigo: String(payload.codigo || "").trim(),
        limit: Math.max(1, Number(payload.limit || 20) || 20),
        offset: 0,
      },
    };
    await refreshPage();
  });
}

function wireFinanceiroFechamentoParametrosInteractions() {
  wireSettingsMobileTabs();
  wireEditButtons();
  wireParameterForm();
  wireHolidayForm();
  wirePeriodControls();
  wireObservabilityFilters();
}

function renderSettingsMobileTabs() {
  const tabs = [
    ["monthly-closing", "Fechamento"],
    ["parameters", "Parametros"],
    ["holidays", "Feriados"],
  ];
  return `
    <nav class="financeiro-mobile-section-tabs" aria-label="Secoes de fechamento e parametros" data-finance-mobile-tabs="fechamento-parametros">
      ${tabs
        .map(([section, label]) => `
          <button type="button" data-finance-settings-tab="${escapeAttr(section)}" aria-selected="${activeSettingsMobileSection === section ? "true" : "false"}">${escapeHtml(label)}</button>
        `)
        .join("")}
    </nav>
  `;
}

function wireSettingsMobileTabs() {
  document.querySelectorAll("[data-finance-settings-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      const nextSection = button.dataset.financeSettingsTab || "monthly-closing";
      activeSettingsMobileSection = ["parameters", "holidays"].includes(nextSection) ? nextSection : "monthly-closing";
      const root = document.querySelector("[data-finance-page=\"fechamento-parametros\"]");
      if (root) root.dataset.mobileActiveSection = activeSettingsMobileSection;
      document.querySelectorAll("[data-finance-settings-tab]").forEach((tabButton) => {
        tabButton.setAttribute("aria-selected", tabButton.dataset.financeSettingsTab === activeSettingsMobileSection ? "true" : "false");
      });
    });
  });
}

function renderFinanceiroFechamentoParametros(state, { selectedParameter = null, selectedHoliday = null } = {}) {
  currentSettingsState = {
    ...state,
    parameters: state.parametersState.items,
    holidays: state.holidaysState.items,
    preflightState: state.preflightState || { status: "ready", data: null, error: null },
    auditState: state.auditState || { status: "ready", items: [], pagination: {}, filters: defaultAuditFilters(state.competencia || currentCompetencia()) },
    divergencesState: state.divergencesState || { status: "ready", items: [], pagination: {}, filters: defaultDivergenceFilters(state.competencia || currentCompetencia()) },
    pdfState: state.pdfState || { status: "idle", kind: "", message: "" },
    competencia: state.competencia || currentCompetencia(),
  };
  const capabilities = capabilitySet();
  renderShell(
    `
      <div class="financeiro-settings-page priority-page-surface ui-page-shell ui-stack" data-finance-page="fechamento-parametros" data-mobile-active-section="${escapeAttr(activeSettingsMobileSection)}">
        <div class="page-header priority-page-header ui-page-header ui-surface">
          <div>
            <h1>Fechamento e Parametros</h1>
            <p class="page-subtitle">Gestao operacional de parametros financeiros, feriados nacionais e preparacao de competencia.</p>
          </div>
          <div class="page-header-actions">
            <a class="button-link secondary" href="${escapeAttr(FINANCEIRO_FECHAMENTO_PARAMETROS_ROUTE)}">Atualizar</a>
          </div>
        </div>

        ${renderSettingsOverview()}

        ${renderSettingsMobileTabs()}

        ${renderMonthlyClosingSection({
          periodState: state.periodState,
          preflightState: currentSettingsState.preflightState,
          divergencesState: currentSettingsState.divergencesState,
          auditState: currentSettingsState.auditState,
          pdfState: currentSettingsState.pdfState,
          competencia: currentSettingsState.competencia,
          capabilities,
        })}
        ${renderParametersSection({ parametersState: state.parametersState, selectedParameter, capabilities })}
        ${renderHolidaysSection({ holidaysState: state.holidaysState, selectedHoliday, capabilities })}
      </div>
    `,
    "Fechamento e Parametros",
  );
  wireFinanceiroFechamentoParametrosInteractions();
}

function dataStateFromError(error, resourceLabel) {
  return {
    status: error?.status === 403 ? "forbidden" : "error",
    error,
    items: [],
    resourceLabel,
  };
}

function preflightStateFromError(error) {
  return {
    status: error?.status === 403 ? "forbidden" : "error",
    data: null,
    error,
  };
}

function listStateFromPayload(payload, filters) {
  return {
    status: "ready",
    items: normalizeItems(payload),
    pagination: payload?.pagination || {},
    filters,
  };
}

export async function renderFinanceiroFechamentoParametrosPage() {
  const capabilities = capabilitySet();
  const query = hashQuery();
  const competencia = String(query.get("competencia") || currentCompetencia()).trim();
  renderShell(
    `
      <div class="financeiro-settings-page priority-page-surface ui-page-shell">
        <section class="panel ui-surface">
          ${responsiveStateMarkup({
            title: "Carregando Fechamento e Parametros",
            detail: "Buscando fechamento mensal, parametros financeiros e feriados nacionais.",
            type: "loading",
          })}
        </section>
      </div>
    `,
    "Fechamento e Parametros",
  );

  const canReadParameters = capabilities.has(PARAMETER_READ_PERMISSION);
  const canReadPeriods = capabilities.has(PERIOD_READ_PERMISSION);
  const canReadAudit = capabilities.has(AUDIT_READ_PERMISSION);
  const canReadDivergences = capabilities.has(DIVERGENCES_READ_PERMISSION);
  const previousAuditFilters = currentSettingsState.auditState?.filters?.competencia === competencia
    ? currentSettingsState.auditState.filters
    : defaultAuditFilters(competencia);
  const previousDivergenceFilters = currentSettingsState.divergencesState?.filters?.competencia === competencia
    ? currentSettingsState.divergencesState.filters
    : defaultDivergenceFilters(competencia);

  const parametersPromise = canReadParameters
    ? listFinanceiroParametros({ pageSize: 100 })
      .then((payload) => ({ status: "ready", items: normalizeItems(payload) }))
      .catch((error) => dataStateFromError(error, "parametros financeiros"))
    : Promise.resolve({ status: "forbidden", items: [] });
  const holidaysPromise = canReadParameters
    ? listFinanceiroFeriados({ ano: currentYear(), pageSize: 100 })
      .then((payload) => ({ status: "ready", items: normalizeItems(payload) }))
      .catch((error) => dataStateFromError(error, "feriados nacionais"))
    : Promise.resolve({ status: "forbidden", items: [] });

  const periodPromise = canReadPeriods
    ? getFinanceiroCompetencia(competencia)
      .then(periodPayloadFromApi)
      .catch((error) => ({
        status: error?.status === 403 ? "forbidden" : "error",
        error,
        period: null,
        totals: {},
        snapshot: null,
        divergences: [],
      }))
    : Promise.resolve({ status: "forbidden", period: null, totals: {}, snapshot: null, divergences: [] });

  const preflightPromise = canReadPeriods
    ? getFinanceiroCompetenciaPreflight(competencia)
      .then((payload) => ({
        status: "ready",
        data: preflightPayloadFromApi(payload),
        error: null,
      }))
      .catch(preflightStateFromError)
    : Promise.resolve({ status: "forbidden", data: null, error: null });

  const auditPromise = canReadAudit
    ? listFinanceiroAuditoria({
      competencia,
      entityType: previousAuditFilters.entityType,
      eventName: previousAuditFilters.eventName,
      limit: previousAuditFilters.limit,
      offset: previousAuditFilters.offset,
    })
      .then((payload) => listStateFromPayload(payload, { ...previousAuditFilters, competencia }))
      .catch((error) => ({
        status: error?.status === 403 ? "forbidden" : "error",
        items: [],
        pagination: {},
        filters: { ...previousAuditFilters, competencia },
        error,
      }))
    : Promise.resolve({
      status: "forbidden",
      items: [],
      pagination: {},
      filters: { ...previousAuditFilters, competencia },
    });

  const divergencesPromise = canReadDivergences
    ? listFinanceiroDivergencias({
      competencia,
      status: previousDivergenceFilters.status,
      severidade: previousDivergenceFilters.severidade,
      codigo: previousDivergenceFilters.codigo,
      limit: previousDivergenceFilters.limit,
      offset: previousDivergenceFilters.offset,
    })
      .then((payload) => listStateFromPayload(payload, { ...previousDivergenceFilters, competencia }))
      .catch((error) => ({
        status: error?.status === 403 ? "forbidden" : "error",
        items: [],
        pagination: {},
        filters: { ...previousDivergenceFilters, competencia },
        error,
      }))
    : Promise.resolve({
      status: "forbidden",
      items: [],
      pagination: {},
      filters: { ...previousDivergenceFilters, competencia },
    });

  const [parametersState, holidaysState, periodState, preflightState, auditState, divergencesState] = await Promise.all([
    parametersPromise,
    holidaysPromise,
    periodPromise,
    preflightPromise,
    auditPromise,
    divergencesPromise,
  ]);
  renderFinanceiroFechamentoParametros({
    parametersState,
    holidaysState,
    periodState,
    preflightState,
    auditState,
    divergencesState,
    pdfState: currentSettingsState.competencia === competencia
      ? currentSettingsState.pdfState
      : { status: "idle", kind: "", message: "" },
    competencia,
  });
}

