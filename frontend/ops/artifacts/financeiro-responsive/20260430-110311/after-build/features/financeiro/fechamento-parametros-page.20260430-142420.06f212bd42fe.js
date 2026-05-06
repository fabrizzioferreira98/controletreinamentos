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
} from "../../lib.20260430-142420.cf58b4b4395e.js";
import { renderShell } from "../../shell.20260430-142420.eed3fe973fa2.js";
import {
  closeFinanceiroCompetencia,
  createFinanceiroFeriado,
  createFinanceiroParametro,
  getFinanceiroCompetencia,
  listFinanceiroFeriados,
  listFinanceiroParametros,
  recalculateFinanceiroCompetencia,
  reopenFinanceiroCompetencia,
  updateFinanceiroFeriado,
  updateFinanceiroParametro,
} from "../../services/financeiro-parametros-api.20260430-142420.909d4fd70b6a.js";

const FINANCEIRO_FECHAMENTO_PARAMETROS_ROUTE = "#/financeiro/fechamento-parametros";
const PARAMETER_READ_PERMISSION = "finance:parameters:read";
const PARAMETER_CREATE_PERMISSION = "finance:parameters:create";
const PARAMETER_UPDATE_PERMISSION = "finance:parameters:update";
const PERIOD_READ_PERMISSION = "finance:periods:read";
const PERIOD_RECALCULATE_PERMISSION = "finance:periods:recalculate";
const PERIOD_CLOSE_PERMISSION = "finance:periods:close";
const PERIOD_REOPEN_PERMISSION = "finance:periods:reopen";

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
  "garantia_minima",
  "excecao_palmas_turbohelice",
];

const PARAMETER_UNITS = [
  "minutos",
  "percentual",
  "valor",
  "horario",
  "quantidade",
  "texto",
];

const STATUS_OPTIONS = ["ativo", "inativo"];
let currentSettingsState = {
  parameters: [],
  holidays: [],
  parametersState: { status: "ready", items: [] },
  holidaysState: { status: "ready", items: [] },
  periodState: { status: "ready", period: null, totals: {}, snapshot: null, divergences: [] },
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

function renderParameterRows(parameters, canUpdate) {
  if (!parameters.length) {
    return emptyTableRowMarkup(9, {
      title: "Nenhum parametro financeiro cadastrado.",
      detail: "Cadastre os parametros vigentes antes da etapa de calculo no backend.",
      type: "empty",
    });
  }
  return parameters
    .map((parameter) => `
      <tr>
        <td><strong>${escapeHtml(parameter.tipo || "-")}</strong></td>
        <td>${escapeHtml(parameter.funcao || "-")}</td>
        <td>${escapeHtml(parameter.categoria || "-")}</td>
        <td>${escapeHtml(parameter.valor ?? "-")}</td>
        <td>${escapeHtml(parameter.unidade || "-")}</td>
        <td>${escapeHtml(formatDateBr(parameter.vigencia_inicio))}</td>
        <td>${escapeHtml(formatDateBr(parameter.vigencia_fim))}</td>
        <td><span class="status-pill ${statusClass(parameter.status)}">${escapeHtml(parameter.status || "-")}</span></td>
        <td>
          <div class="ui-table-actions">
            <button type="button" class="button-link secondary" data-edit-parameter-id="${escapeAttr(parameter.id)}" ${canUpdate ? "" : "disabled"}>Editar</button>
          </div>
        </td>
      </tr>
    `)
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
      <p class="ui-field-help">O parametro duracao_hora_noturna_minutos aceita valor 52.5 e unidade minutos. Esta tela apenas cadastra parametros.</p>
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

function renderPeriodSummaryCards(totals = {}) {
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
      value: displayValue(totals.divergence_count, "0"),
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
    return emptyTableRowMarkup(5, {
      title: "Nenhuma pendencia retornada pela API.",
      detail: "A competencia pode seguir conferencia conforme permissoes do perfil.",
      type: "empty",
    });
  }
  return divergences
    .map((item) => `
      <tr>
        <td><span class="status-pill ${statusClass(item.severity || item.severidade)}">${escapeHtml(item.severity || item.severidade || "-")}</span></td>
        <td>${escapeHtml(item.code || item.codigo || "-")}</td>
        <td>${escapeHtml(item.message || item.mensagem || "-")}</td>
        <td>${escapeHtml(item.entity_type || item.entidade_tipo || "-")}</td>
        <td>${escapeHtml(item.status || "-")}</td>
      </tr>
    `)
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

function renderAuditSummary(period = {}, snapshot = {}) {
  return `
    <div class="financeiro-settings-card" data-finance-period-audit>
      <h3>Historico / Auditoria</h3>
      <p>Eventos de fechar e reabrir sao registrados pelo backend. A consulta detalhada do log sera exibida quando a API de auditoria financeira for liberada.</p>
      <dl class="financeiro-detail-grid">
        <div><dt>Status atual</dt><dd>${escapeHtml(period?.status || "aberta")}</dd></div>
        <div><dt>Fechado por</dt><dd>${escapeHtml(displayValue(period?.closed_by))}</dd></div>
        <div><dt>Fechado em</dt><dd>${escapeHtml(formatDateTimeBr(period?.closed_at))}</dd></div>
        <div><dt>Motivo da reabertura</dt><dd>${escapeHtml(displayValue(period?.reopen_reason))}</dd></div>
        <div><dt>Snapshot gerado em</dt><dd>${escapeHtml(formatDateTimeBr(snapshot?.generated_at))}</dd></div>
      </dl>
    </div>
  `;
}

function renderPeriodActions({ period, competencia, capabilities }) {
  const status = String(period?.status || "aberta").trim().toLowerCase();
  const isClosed = status === "fechada";
  const canRecalculate = capabilities.has(PERIOD_RECALCULATE_PERMISSION) && !isClosed;
  const canClose = capabilities.has(PERIOD_CLOSE_PERMISSION) && !isClosed;
  const canReopen = capabilities.has(PERIOD_REOPEN_PERMISSION) && isClosed;
  return `
    <div class="financeiro-settings-form-head">
      <div>
        <h3>Acoes da competencia</h3>
        <p>Botoes bloqueiam por status e permissao; os totais continuam sendo calculados somente pelo backend.</p>
      </div>
    </div>
    <div id="financePeriodActionFeedback" aria-live="polite"></div>
    <div class="form-actions ui-form-actions" data-finance-period-actions>
      <button type="button" id="financePeriodRecalculateButton" data-required-permission="${PERIOD_RECALCULATE_PERMISSION}" ${canRecalculate ? "" : "disabled"}>Recalcular</button>
      <button type="button" id="financePeriodCloseButton" data-required-permission="${PERIOD_CLOSE_PERMISSION}" ${canClose ? "" : "disabled"}>Fechar</button>
      <button type="button" class="button-link secondary" id="financePeriodReopenButton" data-required-permission="${PERIOD_REOPEN_PERMISSION}" ${canReopen ? "" : "disabled"}>Reabrir</button>
    </div>
    <p class="ui-field-help">Competencia selecionada: ${escapeHtml(formatCompetenciaLabel(competencia))}. Reabertura exige motivo informado pelo usuario.</p>
  `;
}

function renderMonthlyClosingSection({ periodState, competencia, capabilities }) {
  const canReadPeriods = capabilities.has(PERIOD_READ_PERMISSION);
  const period = periodState.period || { competencia, status: "aberta" };
  const snapshot = periodState.snapshot || {};
  const totals = periodState.totals || {};
  return `
    <section class="panel ui-surface ui-stack" data-finance-section="monthly-closing">
      <div class="financeiro-settings-section-head">
        <div>
          <h2>Fechamento Mensal</h2>
          <p>Conferencia de competencia, totais, pendencias e snapshot mensal retornados pela API.</p>
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
      ${periodState.status === "ready" && canReadPeriods ? renderPeriodSummaryCards(totals) : ""}
      ${periodState.status === "ready" && canReadPeriods ? renderPeriodActions({ period, competencia, capabilities }) : ""}
      ${periodState.status === "ready" && canReadPeriods
        ? `
          <div class="financeiro-settings-layout">
            <div class="table-wrap ui-table-wrap ui-table-density-compact">
              <div class="financeiro-settings-section-head">
                <div>
                  <h3>Pendencias</h3>
                  <p>Divergencias da competencia retornadas pelo backend.</p>
                </div>
              </div>
              <table class="data-table responsive-cards">
                <thead>
                  <tr>
                    <th>Severidade</th>
                    <th>Codigo</th>
                    <th>Mensagem</th>
                    <th>Entidade</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>${renderDivergenceRows(periodState.divergences)}</tbody>
              </table>
            </div>
            <aside class="financeiro-settings-side ui-stack-sm">
              ${renderSnapshotSummary(period, snapshot, totals)}
              ${renderAuditSummary(period, snapshot)}
            </aside>
          </div>
        `
        : ""}
      <div class="financeiro-settings-card-grid">
        <article class="financeiro-settings-card">
          <h3>Auditoria e Divergencias</h3>
          <p>A trilha detalhada permanece no backend; esta tela exibe o resumo disponivel na competencia.</p>
        </article>
      </div>
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
              ${renderParameterRows(parametersState.items, canUpdate)}
            </tbody>
          </table>
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

  document.getElementById("financePeriodCloseButton")?.addEventListener("click", async (event) => {
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

function wireFinanceiroFechamentoParametrosInteractions() {
  wireSettingsMobileTabs();
  wireEditButtons();
  wireParameterForm();
  wireHolidayForm();
  wirePeriodControls();
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

        <section class="panel ui-surface financeiro-settings-notice">
          <strong>Sem calculo nesta tela</strong>
          <span>Parametros e feriados sao cadastros de referencia; fechamento e totais sao consumidos da API.</span>
        </section>

        ${renderSettingsMobileTabs()}

        ${renderMonthlyClosingSection({ periodState: state.periodState, competencia: currentSettingsState.competencia, capabilities })}
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
  const canReadPeriods = capabilities.has(PERIOD_READ_PERMISSION);
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

  const [parametersState, holidaysState, periodState] = await Promise.all([parametersPromise, holidaysPromise, periodPromise]);
  renderFinanceiroFechamentoParametros({
    parametersState,
    holidaysState,
    periodState,
    competencia,
  });
}
