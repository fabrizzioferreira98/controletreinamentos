import {
  booleanLabel,
  buildErrorMessage,
  buildHashHref,
  capabilitySet,
  confirmAction,
  escapeAttr,
  escapeHtml,
  filterSummaryMarkup,
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
  cancelFinanceiroMissao,
  createFinanceiroMissao,
  deleteFinanceiroMissao,
  getFinanceiroMissao,
  listFinanceiroEquipamentoOptions,
  listFinanceiroMissoes,
  listFinanceiroTripulanteOptions,
  preflightFinanceiroMissaoCalculo,
  previewFinanceiroMissao,
  recalculateFinanceiroMissao,
  updateFinanceiroMissao,
} from "../../services/financeiro-missoes-api.js";
import { listFinanceiroBonificacoesHorarias } from "../../services/financeiro-bonificacoes-api.js";

const FINANCEIRO_MISSOES_ROUTE = "#/financeiro/missoes";
const FINANCEIRO_BONIFICACOES_ROUTE = "#/financeiro/bonificacoes";
const FINANCEIRO_BONIFICACOES_HORARIA_ROUTE = "#/financeiro/bonificacoes/horaria";
const PAGE_SIZE = 50;
const HOURLY_PAGE_SIZE = 300;
const PREFLIGHT_BATCH_LIMIT = 50;
const PREVIEW_DEBOUNCE_MS = 650;
const TRIPULANTE_OPTION_PERMISSIONS = ["tripulantes:view", "relatorio_individual:view"];
const EQUIPAMENTO_OPTION_PERMISSIONS = ["equipamentos:view"];
const MISSION_EMPTY_TITLE = "Nenhuma missão operacional encontrada";
const MISSION_EMPTY_DETAIL = "Ajuste os filtros ou cadastre uma nova missão para iniciar o acompanhamento financeiro da competência.";
const PREVIEW_INSUFFICIENT_TEXT = "Informe data, aeronave, tripulação e categoria operacional para gerar a prévia financeira.";
const PREVIEW_LOADING_TEXT = "Calculando prévia financeira...";
const PREVIEW_REQUIRED_FIELDS = [
  { key: "data_missao", label: "data da missão" },
  { key: "aeronave_id", label: "aeronave" },
  { key: "categoria_financeira_aeronave", label: "categoria operacional" },
  { key: "comandante_tripulante_id", label: "comandante" },
  { key: "copiloto_tripulante_id", label: "copiloto" },
  { key: "horario_apresentacao", label: "horário de apresentação" },
  { key: "horario_abandono", label: "horário de abandono" },
];

const CALCULATION_STATUS_LABELS = {
  calculado: "calculado",
  pendente: "pendente",
  bloqueada: "bloqueada",
  cancelada: "cancelada",
  obsoleto: "obsoleto",
};
const financeMissionOperationLocks = new Set();

function beginFinanceMissionOperation(key, feedback) {
  if (financeMissionOperationLocks.has(key)) {
    renderInlineFeedback(feedback, "Operação em andamento. Aguarde a conclusão antes de tentar novamente.", "warning");
    return false;
  }
  financeMissionOperationLocks.add(key);
  return true;
}

function endFinanceMissionOperation(key) {
  financeMissionOperationLocks.delete(key);
}

function currentCompetencia() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  return `${now.getFullYear()}-${month}`;
}

function normalizeId(value) {
  const numeric = Number(value || 0);
  return Number.isFinite(numeric) && numeric > 0 ? numeric : null;
}

function readFilters() {
  const query = hashQuery();
  return {
    competencia: String(query.get("competencia") || currentCompetencia()).trim(),
    status: String(query.get("status") || "").trim(),
    calculoStatus: String(query.get("calculo_status") || "").trim(),
    busca: String(query.get("busca") || "").trim(),
    page: Math.max(1, Number(query.get("page") || 1) || 1),
    missionId: normalizeId(query.get("mission_id")),
    previewStatus: String(query.get("preview_status") || "").trim(),
  };
}

function missionStatusClass(status) {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "ativa") return "status-green";
  if (normalized === "cancelada") return "status-red";
  if (normalized === "recalculo_pendente") return "status-yellow";
  return "status-dark";
}

function missionCalculationStatusClass(status) {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "calculado") return "status-green";
  if (normalized === "bloqueada") return "status-red";
  if (normalized === "obsoleto") return "status-dark";
  if (normalized === "cancelada") return "status-dark";
  return "status-yellow";
}

function preflightDataFromPayload(payload) {
  if (!payload || typeof payload !== "object") return {};
  const data = payload.data;
  if (data && typeof data === "object" && !Array.isArray(data)) {
    return data;
  }
  return payload;
}

function preflightBlockList(preflightPayload) {
  const preflight = preflightDataFromPayload(preflightPayload);
  const bloqueios = Array.isArray(preflight?.bloqueios) ? preflight.bloqueios : [];
  if (bloqueios.length) return bloqueios;
  const naoElegiveis = Array.isArray(preflight?.parametros_nao_elegiveis) ? preflight.parametros_nao_elegiveis : [];
  if (!naoElegiveis.length) return [];
  return naoElegiveis.map((parameter) => ({
    code: "finance_parameters_not_release_eligible",
    message: `O parametro ${String(parameter?.tipo || "desconhecido")}/${String(parameter?.funcao || "geral")} nao esta elegivel para fechamento real.`,
    severity: "alta",
    entity_type: "finance_parameter",
    entity_id: parameter?.id || "",
    field: parameter?.tipo || "",
    next_action: "Revise a classificacao e vigencia do parametro no cadastro financeiro.",
  }));
}

function extractMissionIdFromCalculation(item) {
  return normalizeId(item?.mission_id || item?.missao_operacional_id || item?.missao?.id);
}

function latestCalculation(items) {
  if (!items.length) return null;
  return [...items].sort((left, right) => Number(right?.id || 0) - Number(left?.id || 0))[0] || null;
}

function buildHourlyByMission(items) {
  const byMission = new Map();
  items.forEach((item) => {
    const missionId = extractMissionIdFromCalculation(item);
    if (!missionId) return;
    if (!byMission.has(missionId)) byMission.set(missionId, []);
    byMission.get(missionId).push(item);
  });
  return byMission;
}

function deriveCalculationStatus(mission, hourlyItems, preflightPayload) {
  const operationalStatus = String(mission?.status || "").trim().toLowerCase();
  if (operationalStatus === "cancelada") return "cancelada";
  const preflight = preflightDataFromPayload(preflightPayload);
  if (preflight?.calculavel === false) return "bloqueada";

  if (hourlyItems.length) {
    const statuses = new Set(
      hourlyItems
        .map((item) => String(item?.status || "").trim().toLowerCase())
        .filter(Boolean),
    );
    if (statuses.has("calculado")) return "calculado";
    if (statuses.has("obsoleto")) return "obsoleto";
  }

  if (operationalStatus === "recalculo_pendente") return "pendente";
  return "pendente";
}

function buildMissionRuntimeMap(items, { hourlyItems = [], preflightByMission = new Map() } = {}) {
  const hourlyByMission = buildHourlyByMission(hourlyItems);
  const runtimeMap = new Map();
  items.forEach((mission) => {
    const missionId = normalizeId(mission?.id);
    const calculations = missionId ? (hourlyByMission.get(missionId) || []) : [];
    const preflightPayload = missionId ? preflightByMission.get(missionId) : null;
    const calcStatus = deriveCalculationStatus(mission, calculations, preflightPayload);
    const blocks = preflightBlockList(preflightPayload);
    runtimeMap.set(missionId, {
      missionId,
      calcStatus,
      calcLabel: CALCULATION_STATUS_LABELS[calcStatus] || "pendente",
      blocks,
      blocked: calcStatus === "bloqueada",
      calculations,
      calculationCount: calculations.length,
      latestCalculation: latestCalculation(calculations),
      preflightPayload: preflightDataFromPayload(preflightPayload),
    });
  });
  return runtimeMap;
}

function normalizeSearchText(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

function canonicalFinanceCategoryLabel(value) {
  const normalized = normalizeSearchText(value);
  if (normalized === "a" || normalized === "categoria a") return "categoria a";
  if (normalized === "b" || normalized === "categoria b") return "categoria b";
  return String(value || "").trim();
}

function renderOperationalCategoryLabel(value) {
  const raw = String(value || "").trim();
  const canonical = canonicalFinanceCategoryLabel(raw);
  if (!raw) {
    return '<span class="secondary-cell">Categoria operacional nao informada</span>';
  }
  return `
    <div class="primary-cell">${escapeHtml(raw)}</div>
    ${canonical && canonical !== raw
      ? `<div class="secondary-cell">Normaliza no calculo: ${escapeHtml(canonical)}</div>`
      : '<div class="secondary-cell">Categoria financeira canonica ja informada</div>'}
  `;
}

function missionMatchesSearch(mission, search) {
  const term = normalizeSearchText(search);
  if (!term) return true;
  const haystack = [
    mission?.cavok_numero_voo,
    mission?.chamado,
    mission?.contratante,
    mission?.trecho,
    mission?.categoria_financeira_aeronave,
  ].map(normalizeSearchText).join(" ");
  return haystack.includes(term);
}

function missionIsDeleted(mission) {
  return Boolean(mission?.is_deleted || mission?.deleted_at);
}

function visibleMissions(items, filters, runtimeMap) {
  return items.filter((mission) => {
    if (missionIsDeleted(mission)) return false;
    const operationalStatus = String(mission?.status || "").trim().toLowerCase();
    const requestedStatus = String(filters.status || "").trim().toLowerCase();
    if (!missionMatchesSearch(mission, filters.busca)) return false;
    if (requestedStatus && operationalStatus !== requestedStatus) return false;
    if (!requestedStatus && operationalStatus === "cancelada") return false;
    if (!filters.calculoStatus) return true;
    const runtime = runtimeMap.get(normalizeId(mission?.id));
    return String(runtime?.calcStatus || "").toLowerCase() === filters.calculoStatus.toLowerCase();
  });
}

function missionSummary(items, runtimeMap) {
  const activeItems = items.filter((mission) => !missionIsDeleted(mission));
  const total = activeItems.length;
  const calculated = activeItems.filter((mission) => runtimeMap.get(normalizeId(mission?.id))?.calcStatus === "calculado").length;
  const blocked = activeItems.filter((mission) => runtimeMap.get(normalizeId(mission?.id))?.calcStatus === "bloqueada").length;
  const obsolete = activeItems.filter((mission) => runtimeMap.get(normalizeId(mission?.id))?.calcStatus === "obsoleto").length;
  const cancelled = activeItems.filter((mission) => runtimeMap.get(normalizeId(mission?.id))?.calcStatus === "cancelada").length;
  const pending = Math.max(0, total - calculated - blocked - cancelled);
  return { total, calculated, pending, blocked, cancelled, obsolete };
}

function ratioLabel(part, total) {
  if (!total) return "0%";
  return `${((Number(part) / Number(total)) * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
}

function formatTimeBr(value) {
  const raw = String(value || "").trim();
  if (!raw) return "-";
  const match = raw.match(/[T\s](\d{2}):(\d{2})/);
  return match ? `${match[1]}:${match[2]}` : formatDateTimeBr(raw);
}

function formatPreviewTimestamp(value) {
  const formatted = formatDateTimeBr(value);
  return formatted === "-" ? "" : formatted;
}

function formatPreviewMoney(value) {
  const raw = String(value ?? "").trim();
  if (!raw) return "-";
  const numeric = Number(raw.replace(",", "."));
  if (!Number.isFinite(numeric)) return escapeHtml(raw);
  return numeric.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function formatPreviewMinutes(value) {
  const minutes = Number(value || 0);
  if (!Number.isFinite(minutes) || minutes <= 0) return "-";
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return `${hours}h${String(remainder).padStart(2, "0")} (${minutes} min)`;
}

function previewStatusClass(status) {
  const normalized = String(status || "").trim().toLowerCase();
  if (["disponivel", "salva", "recalculada"].includes(normalized)) return "status-green";
  if (["bloqueada", "erro"].includes(normalized)) return "status-red";
  if (["carregando", "pendente_dados"].includes(normalized)) return "status-yellow";
  return "status-dark";
}

function previewStatusLabel(status) {
  const labels = {
    sem_dados_suficientes: "Sem dados suficientes",
    carregando: "Prévia carregando",
    disponivel: "Prévia disponível",
    pendente_dados: "Pendente de dados",
    bloqueada: "Bloqueada por inconsistência",
    erro: "Erro de cálculo",
    salva: "Prévia atualizada",
    recalculada: "Recalculada com sucesso",
  };
  return labels[String(status || "").trim()] || "Sem dados suficientes";
}

function previewListMarkup(items = [], className = "financeiro-missoes-preview-list") {
  const values = (Array.isArray(items) ? items : [])
    .map((item) => String(item?.message || item?.label || item || "").trim())
    .filter(Boolean);
  if (!values.length) return '<span class="secondary-cell">Nenhuma pendência informada.</span>';
  return `<ul class="${escapeAttr(className)}">${values.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function previewTripulantesLabel(items = []) {
  const values = (Array.isArray(items) ? items : [])
    .map((item) => {
      const funcao = String(item?.funcao || "").trim();
      const id = item?.tripulante_id ? `#${item.tripulante_id}` : "";
      return [funcao, id].filter(Boolean).join(" ");
    })
    .filter(Boolean);
  return values.length ? values.join(", ") : "-";
}

function renderPreviewSummary(preview) {
  const horas = preview?.horas_consideradas || {};
  const pendencias = Array.isArray(preview?.pendencias) ? preview.pendencias : [];
  const inconsistencias = Array.isArray(preview?.inconsistencias) ? preview.inconsistencias : [];
  const observations = Array.isArray(preview?.observacoes) ? preview.observacoes : [];
  return `
    <div class="financeiro-missoes-preview-summary">
      <div><span>Estado do cálculo</span><strong>${escapeHtml(preview?.estado_calculo || preview?.status || "estimado")}</strong></div>
      <div><span>Base de cálculo</span><strong>${escapeHtml(preview?.base_calculo || "Bonificação horária operacional")}</strong></div>
      <div><span>Horas consideradas</span><strong>${escapeHtml(formatPreviewMinutes(horas.jornada_total_minutos))}</strong></div>
      <div><span>Tripulantes</span><strong>${escapeHtml(previewTripulantesLabel(preview?.tripulantes_considerados))}</strong></div>
      <div><span>Valor estimado</span><strong>${formatPreviewMoney(preview?.valor_estimado)}</strong></div>
      <div><span>Atualização</span><strong>${escapeHtml(formatPreviewTimestamp(preview?.generated_at) || "-")}</strong></div>
    </div>
    <div class="financeiro-missoes-preview-block">
      <strong>Pendências</strong>
      ${previewListMarkup(pendencias)}
    </div>
    ${inconsistencias.length
      ? `<div class="financeiro-missoes-preview-block" data-tone="danger"><strong>Inconsistências</strong>${previewListMarkup(inconsistencias)}</div>`
      : ""}
    <div class="financeiro-missoes-preview-note">
      ${previewListMarkup(observations, "financeiro-missoes-preview-notes")}
    </div>
  `;
}

function renderPreviewPending(missingFields) {
  return `
    <p>${escapeHtml(PREVIEW_INSUFFICIENT_TEXT)}</p>
    <div class="financeiro-missoes-preview-block">
      <strong>Campos faltantes</strong>
      ${previewListMarkup((missingFields || []).map((field) => `Informe ${field.label}.`))}
    </div>
  `;
}

function renderPreviewInitialContent(state = "sem_dados_suficientes", preview = null) {
  if (state === "disponivel" && preview) return renderPreviewSummary(preview);
  if (state === "carregando") return `<p>${escapeHtml(PREVIEW_LOADING_TEXT)}</p>`;
  if (state === "bloqueada" && preview) {
    return `
      <p>A prévia foi bloqueada por inconsistências retornadas pelo backend.</p>
      <div class="financeiro-missoes-preview-block" data-tone="danger">
        <strong>Inconsistências</strong>
        ${previewListMarkup(preview.inconsistencias)}
      </div>
    `;
  }
  return `<p>${escapeHtml(PREVIEW_INSUFFICIENT_TEXT)}</p>`;
}

function fieldValue(mission, key, fallback = "") {
  return escapeAttr(mission?.[key] ?? fallback);
}

function datetimeLocalValue(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  return raw.replace(" ", "T").slice(0, 16);
}

function checkboxAttr(value) {
  return value ? "checked" : "";
}

function hasAnyCapability(capabilities, permissions) {
  return permissions.some((permission) => capabilities.has(permission));
}

function normalizeOptionItem(item, { fallbackName = "Registro", categoryKeys = [] } = {}) {
  const id = normalizeId(item?.id);
  if (!id) return null;
  const name = String(item?.nome || item?.label || item?.name || `${fallbackName} ${id}`).trim();
  const details = [
    item?.base,
    item?.funcao_operacional,
    item?.categoria_operacional,
  ]
    .map((value) => String(value || "").trim())
    .filter(Boolean);
  const category = categoryKeys
    .map((key) => String(item?.[key] || "").trim())
    .find(Boolean) || "";
  const suffix = details.length ? ` (${details.join(" / ")})` : "";
  return {
    id: String(id),
    label: name,
    display: `${id} - ${name}${suffix}`,
    category,
  };
}

function normalizeTripulanteOptions(payload) {
  const source = Array.isArray(payload?.items) ? payload.items : [];
  return source
    .map((item) => normalizeOptionItem(item, { fallbackName: "Tripulante" }))
    .filter(Boolean);
}

function normalizeEquipamentoOptions(payload) {
  const source = Array.isArray(payload?.options)
    ? payload.options
    : (Array.isArray(payload?.options?.equipamentos) ? payload.options.equipamentos : []);
  return source
    .map((item) => normalizeOptionItem(item, {
      fallbackName: "Equipamento",
      categoryKeys: ["categoria_financeira", "categoria_financeira_aeronave"],
    }))
    .filter(Boolean);
}

function optionStateReady(items, endpoint) {
  return {
    status: items.length ? "ready" : "empty",
    endpoint,
    items,
    detail: items.length ? "" : "Nenhuma opcao disponivel; informe o ID manualmente.",
  };
}

function optionStateUnavailable({ status = "unavailable", endpoint, detail }) {
  return {
    status,
    endpoint,
    items: [],
    detail,
  };
}

function optionStateFromError(error, endpoint) {
  if (error?.status === 401) {
    return optionStateUnavailable({
      status: "forbidden",
      endpoint,
      detail: "Sessao expirada ao carregar opcoes; informe o ID manualmente.",
    });
  }
  if (error?.status === 403) {
    return optionStateUnavailable({
      status: "forbidden",
      endpoint,
      detail: "Seu perfil nao possui permissao para carregar estas opcoes; informe o ID manualmente.",
    });
  }
  if (error?.status === 501) {
    return optionStateUnavailable({
      status: "not-implemented",
      endpoint,
      detail: "Endpoint de opcoes ainda nao implementado; informe o ID manualmente.",
    });
  }
  return optionStateUnavailable({
    status: "error",
    endpoint,
    detail: buildErrorMessage(error),
  });
}

async function loadTripulanteOptions(capabilities) {
  const endpoint = "/api/v1/tripulantes";
  if (!hasAnyCapability(capabilities, TRIPULANTE_OPTION_PERMISSIONS)) {
    return optionStateUnavailable({
      status: "forbidden",
      endpoint,
      detail: "Sem permissao de leitura de tripulantes; informe o ID manualmente.",
    });
  }
  try {
    const payload = await listFinanceiroTripulanteOptions({ ativo: "1" });
    return optionStateReady(normalizeTripulanteOptions(payload), endpoint);
  } catch (error) {
    return optionStateFromError(error, endpoint);
  }
}

async function loadEquipamentoOptions(capabilities) {
  const endpoint = "/api/v1/equipamentos/options";
  if (!hasAnyCapability(capabilities, EQUIPAMENTO_OPTION_PERMISSIONS)) {
    return optionStateUnavailable({
      status: "forbidden",
      endpoint,
      detail: "Sem permissao de leitura de equipamentos. Informe o ID manualmente.",
    });
  }
  try {
    const payload = await listFinanceiroEquipamentoOptions();
    return optionStateReady(normalizeEquipamentoOptions(payload), endpoint);
  } catch (error) {
    return optionStateFromError(error, endpoint);
  }
}

async function loadFinanceiroMissionOptions(capabilities) {
  const [tripulantes, equipamentos] = await Promise.all([
    loadTripulanteOptions(capabilities),
    loadEquipamentoOptions(capabilities),
  ]);
  return { tripulantes, equipamentos };
}

function optionById(optionsState, id) {
  const target = String(id || "").trim();
  if (!target) return null;
  return (optionsState?.items || []).find((item) => String(item.id) === target) || null;
}

function optionLabel(optionsState, id, fallbackPrefix) {
  const option = optionById(optionsState, id);
  if (option) return option.label;
  return id ? `${fallbackPrefix} ${escapeHtml(id)}` : "-";
}

function optionDisplayValue(optionsState, id) {
  const option = optionById(optionsState, id);
  if (option) return option.display;
  return id ? String(id) : "";
}

function requestErrorState(error) {
  if (error?.status === 401 || error?.code === "unauthorized") {
    return {
      type: "no-permission",
      title: "Sessao expirada",
      detail: "Entre novamente para acessar as Missoes Operacionais.",
    };
  }
  if (error?.status === 403 || error?.code === "forbidden") {
    return {
      type: "no-permission",
      title: "Acesso negado",
      detail: "Seu perfil nao possui permissao para acessar esta area do Financeiro.",
    };
  }
  if (error?.status === 501) {
    return {
      type: "warning",
      title: "Recurso ainda nao implementado",
      detail: "Esta parte do Financeiro ainda esta planejada para uma proxima etapa.",
    };
  }
  return {
    type: "error",
    title: "Nao foi possivel carregar Missoes Operacionais",
    detail: buildErrorMessage(error),
  };
}

function renderPageState(state) {
  renderShell(
    `
      <div class="financeiro-missoes-page ui-page-shell ui-stack">
        <section class="panel ui-surface">
          ${responsiveStateMarkup({
            title: state.title,
            detail: state.detail,
            type: state.type,
            className: "financeiro-missoes-state",
          })}
        </section>
      </div>
    `,
    "Missoes Operacionais",
  );
}

function missionParticipantName(mission, key) {
  if (key === "comandante_tripulante_id") {
    return mission?.comandante_nome || mission?.comandante_tripulante_nome || "";
  }
  if (key === "copiloto_tripulante_id") {
    return mission?.copiloto_nome || mission?.copiloto_tripulante_nome || "";
  }
  return "";
}

function renderParticipantLabel(mission, key, optionsState) {
  const value = mission?.[key];
  const explicitName = missionParticipantName(mission, key);
  if (explicitName) return escapeHtml(explicitName);
  return escapeHtml(optionLabel(optionsState, value, "Tripulante ID"));
}

function renderEquipmentLabel(mission, optionsState) {
  const explicitName = mission?.aeronave_nome || mission?.equipamento_nome || "";
  if (explicitName) return escapeHtml(explicitName);
  return escapeHtml(optionLabel(optionsState, mission?.aeronave_id, "Equipamento ID"));
}

function renderMissionSummaryCards(items, runtimeMap) {
  const summary = missionSummary(items, runtimeMap);
  const cards = [
    { label: "Missoes da competencia", value: summary.total, detail: "Registros carregados", tone: "neutral" },
    { label: "Calculadas", value: summary.calculated, detail: ratioLabel(summary.calculated, summary.total), tone: "positive" },
    { label: "Pendentes", value: summary.pending, detail: ratioLabel(summary.pending, summary.total), tone: "warning" },
    { label: "Bloqueadas", value: summary.blocked, detail: ratioLabel(summary.blocked, summary.total), tone: "danger" },
    { label: "Canceladas", value: summary.cancelled, detail: ratioLabel(summary.cancelled, summary.total), tone: "danger" },
  ];
  if (summary.obsolete > 0) {
    cards.push({
      label: "Obsoletas",
      value: summary.obsolete,
      detail: ratioLabel(summary.obsolete, summary.total),
      tone: "neutral",
    });
  }
  return `
    <section class="financeiro-missoes-summary-grid" aria-label="Resumo da competencia">
      ${cards
        .map((card) => `
          <article class="financeiro-missoes-summary-card ui-surface" data-tone="${escapeAttr(card.tone)}">
            <span>${escapeHtml(card.label)}</span>
            <strong>${escapeHtml(card.value)}</strong>
            <small>${escapeHtml(card.detail)}</small>
          </article>
        `)
        .join("")}
    </section>
  `;
}

function missionRuntimeEntry(runtimeMap, mission) {
  const runtime = runtimeMap.get(normalizeId(mission?.id));
  if (runtime) return runtime;
  return {
    calcStatus: "pendente",
    calcLabel: CALCULATION_STATUS_LABELS.pendente,
    blocks: [],
    blocked: false,
    calculations: [],
    calculationCount: 0,
    latestCalculation: null,
    preflightPayload: {},
  };
}

function missionPendingDetail(mission, runtime) {
  if (runtime.calcStatus === "cancelada") return "Missao cancelada.";
  if (runtime.calcStatus === "bloqueada" && runtime.blocks.length) {
    const firstBlock = runtime.blocks[0];
    const message = String(firstBlock?.message || "").trim();
    return message || "Bloqueio identificado no preflight.";
  }
  if (runtime.calcStatus === "calculado") return "Sem bloqueios; resultado pronto.";
  if (runtime.calcStatus === "obsoleto") return "Calculo obsoleto; recalcule para atualizar.";
  return "Pendente de preflight e recalculo.";
}

function missionHasFinancialHistory(runtime) {
  return Boolean((runtime?.calculationCount || 0) > 0 || runtime?.latestCalculation?.id);
}

function missionDestructiveAction(mission, runtime, capabilities = new Set()) {
  if (!mission?.id || missionIsDeleted(mission)) return null;
  if (missionHasFinancialHistory(runtime) || String(mission.status || "").trim().toLowerCase() === "cancelada") {
    if (!capabilities.has("finance:missions:cancel")) return null;
    return {
      action: "cancel",
      label: "Cancelar missao",
      title: "Cancelar missao operacional?",
      consequence: "Esta missao possui calculo ou historico financeiro vinculado. Para preservar a rastreabilidade, ela sera cancelada e o calculo vigente sera invalidado, sem apagar o historico.",
      help: "Preserva historico financeiro e invalida o calculo vigente vinculado.",
      loading: "Cancelando...",
      success: "Missao operacional cancelada.",
      reason: "Cancelamento solicitado pela tela de Missoes Operacionais",
    };
  }
  if (!capabilities.has("finance:missions:delete")) return null;
  return {
    action: "delete",
    label: "Excluir missao",
    title: "Excluir missao definitivamente?",
    consequence: "Esta missao sera removida dos lancamentos e nao aparecera nos relatorios. Esta acao so e permitida porque ainda nao ha calculo financeiro consolidado vinculado.",
    help: "Remove a missao dos fluxos operacionais comuns sem usar o cancelamento financeiro.",
    loading: "Excluindo...",
    success: "Missao operacional excluida definitivamente.",
    reason: "Exclusao definitiva solicitada pela tela de Missoes Operacionais",
  };
}

function renderMissionDestructiveAction(action) {
  if (!action) return "";
  return `
    <div class="financeiro-missoes-danger-zone">
      <button type="button" class="link-danger" id="financeMissionCancelButton" data-finance-cancel-action="${escapeAttr(action.action)}">${escapeHtml(action.label)}</button>
      <small>${escapeHtml(action.help)}</small>
    </div>
  `;
}

function renderMissionActionLinks({ mission, filters, capabilities }) {
  const missionStatus = String(mission?.status || "").trim().toLowerCase();
  const canRecalculateMission = capabilities.has("finance:missions:recalculate") && missionStatus !== "cancelada" && !missionIsDeleted(mission);
  const detailHref = buildHashHref(FINANCEIRO_MISSOES_ROUTE, {
    competencia: filters.competencia,
    status: filters.status,
    calculo_status: filters.calculoStatus,
    busca: filters.busca,
    page: filters.page,
    mission_id: mission.id,
  });
  const bonificacaoHref = buildHashHref(FINANCEIRO_BONIFICACOES_HORARIA_ROUTE, {
    competencia: mission.competencia || filters.competencia,
    mission_id: mission.id,
  });
  return [
    `<a href="${escapeAttr(detailHref)}">Abrir</a>`,
    canRecalculateMission ? `<a href="${escapeAttr(detailHref)}">Recalcular missão</a>` : "",
    `<a href="${escapeAttr(detailHref)}">Ver preflight</a>`,
    `<a href="${escapeAttr(bonificacaoHref)}">Ver calculo</a>`,
    `<a href="${escapeAttr(bonificacaoHref)}">Ver memoria</a>`,
    `<a href="${escapeAttr(bonificacaoHref)}">Ir para Bonificacoes</a>`,
  ].filter(Boolean).join("");
}

function renderMissionRows(items, filters, capabilities, optionState, runtimeMap) {
  return items
    .map((mission) => {
      const runtime = missionRuntimeEntry(runtimeMap, mission);
      return `
        <tr data-financeiro-missao-id="${escapeAttr(mission.id)}">
          <td data-label="Missão">
            <div class="primary-cell">${escapeHtml(mission.cavok_numero_voo || `Missao #${mission.id || "-"}`)}</div>
            <div class="secondary-cell">${formatDateBr(mission.data_missao)} - ${mission.chamado ? escapeHtml(mission.chamado) : "Chamado nao informado"}</div>
            <div class="secondary-cell">${mission.contratante ? escapeHtml(mission.contratante) : "Contratante nao informado"}</div>
          </td>
          <td data-label="Tripulação">
            <div class="primary-cell">CMT: ${renderParticipantLabel(mission, "comandante_tripulante_id", optionState.tripulantes)}</div>
            <div class="secondary-cell">COP: ${renderParticipantLabel(mission, "copiloto_tripulante_id", optionState.tripulantes)}</div>
          </td>
          <td data-label="Aeronave e operação">
            <div class="primary-cell">${renderEquipmentLabel(mission, optionState.equipamentos)}</div>
            ${renderOperationalCategoryLabel(mission.categoria_financeira_aeronave)}
          </td>
          <td data-label="Status">
            <span class="status-pill ${missionStatusClass(mission.status)}">${escapeHtml(mission.status || "-")}</span>
            <div class="secondary-cell">${escapeHtml(missionPendingDetail(mission, runtime))}</div>
          </td>
          <td data-label="Financeiro">
            <span class="status-pill ${missionCalculationStatusClass(runtime.calcStatus)}">${escapeHtml(runtime.calcLabel || "pendente")}</span>
            <div class="secondary-cell">${escapeHtml(`${runtime.calculationCount || 0} registro(s) de calculo`)}</div>
          </td>
          <td class="actions ui-table-actions" data-label="Ações">
            ${renderMissionActionLinks({ mission, filters, capabilities })}
          </td>
        </tr>
      `;
    })
    .join("");
}

function renderMissionEmptyState(filters, capabilities) {
  return responsiveStateMarkup({
    title: MISSION_EMPTY_TITLE,
    detail: MISSION_EMPTY_DETAIL,
    actionHref: capabilities.has("finance:missions:create")
      ? buildHashHref(FINANCEIRO_MISSOES_ROUTE, { competencia: filters.competencia })
      : "",
    actionLabel: capabilities.has("finance:missions:create") ? "Nova missão" : "",
    type: "structural-empty",
    className: "financeiro-missoes-empty-state",
    tag: "section",
  });
}

function renderMissionTable(items, filters, capabilities, optionState, runtimeMap) {
  if (!items.length) {
    return renderMissionEmptyState(filters, capabilities);
  }
  return `
    <div class="table-wrap ui-table-wrap ui-table-density-compact">
      <table class="data-table responsive-cards financeiro-missoes-table">
        <thead>
          <tr>
            <th>Missão</th>
            <th>Tripulação</th>
            <th>Aeronave e operação</th>
            <th>Status</th>
            <th>Financeiro</th>
            <th>Ações</th>
          </tr>
        </thead>
        <tbody>
          ${renderMissionRows(items, filters, capabilities, optionState, runtimeMap)}
        </tbody>
      </table>
    </div>
  `;
}

function renderMissionDetail(mission, capabilities, optionState, runtime = null, filters = {}) {
  if (!mission) {
    return `
      <div class="financeiro-missoes-side-empty financeiro-missoes-operational-state">
        ${responsiveStateMarkup({
          title: "Nenhuma missão selecionada",
          detail: "Use Nova missão para iniciar um rascunho ou abra um registro da lista para editar, validar pendências e recalcular.",
          type: "info",
          compact: true,
          actionHref: buildHashHref(FINANCEIRO_MISSOES_ROUTE, { competencia: filters.competencia || currentCompetencia() }),
          actionLabel: "Nova missão",
        })}
      </div>
    `;
  }
  const participants = Array.isArray(mission.participantes) ? mission.participantes : [];
  const calculationStatus = runtime?.calcStatus || "pendente";
  const destructiveAction = missionDestructiveAction(mission, runtime, capabilities);
  const workflowMessage = filters.previewStatus === "recalculada"
    ? "Cálculo vigente atualizado pelo backend nesta missão."
    : filters.previewStatus === "salva"
      ? "Missão salva. Revise a prévia antes de recalcular, se necessário."
      : "Registro persistido. Edite os dados abaixo ou acompanhe o cálculo vigente.";
  return `
    <div class="financeiro-missoes-detail financeiro-missoes-detail-card">
      <div class="financeiro-missoes-detail-head">
        <div>
          <h2>Missão salva #${escapeHtml(mission.id)}</h2>
          <p>${escapeHtml(mission.cavok_numero_voo || "Sem numero")} - ${escapeHtml(mission.trecho || "Trecho nao informado")}</p>
        </div>
        <span class="status-pill ${missionStatusClass(mission.status)}">${escapeHtml(mission.status || "-")}</span>
      </div>
      <div class="financeiro-missoes-workflow-state" data-workflow-state="missao_salva">
        <div>
          <strong>${filters.previewStatus === "recalculada" ? "Cálculo vigente atualizado" : "Missão persistida"}</strong>
          <span>${escapeHtml(workflowMessage)}</span>
        </div>
        <span class="status-pill ${missionCalculationStatusClass(calculationStatus)}">${escapeHtml(CALCULATION_STATUS_LABELS[calculationStatus] || calculationStatus)}</span>
      </div>
      <dl class="financeiro-missoes-detail-grid">
        <div><dt>Competência</dt><dd>${escapeHtml(mission.competencia || "-")}</dd></div>
        <div><dt>Data</dt><dd>${formatDateBr(mission.data_missao)}</dd></div>
        <div><dt>Aeronave</dt><dd>${renderEquipmentLabel(mission, optionState.equipamentos)}</dd></div>
        <div><dt>Apresentação</dt><dd>${formatDateTimeBr(mission.horario_apresentacao)}</dd></div>
        <div><dt>Abandono</dt><dd>${formatDateTimeBr(mission.horario_abandono)}</dd></div>
        <div><dt>Comandante</dt><dd>${renderParticipantLabel(mission, "comandante_tripulante_id", optionState.tripulantes)}</dd></div>
        <div><dt>Copiloto</dt><dd>${renderParticipantLabel(mission, "copiloto_tripulante_id", optionState.tripulantes)}</dd></div>
        <div><dt>Pernoite</dt><dd>${booleanLabel(mission.houve_pernoite)} (${escapeHtml(mission.quantidade_pernoites || 0)})</dd></div>
        <div><dt>Cobertura de base</dt><dd>${booleanLabel(mission.cobertura_base)}</dd></div>
      </dl>
      <div class="financeiro-missoes-participants">
        <strong>Participantes do registro</strong>
        ${participants.length
          ? `<ul>${participants.map((item) => `<li>${escapeHtml(item.funcao || "-")}: ${escapeHtml(optionLabel(optionState.tripulantes, item.tripulante_id, "Tripulante ID"))}</li>`).join("")}</ul>`
          : "<span>Participantes serao exibidos quando o detalhe retornar essa estrutura.</span>"}
      </div>
      <div class="financeiro-missoes-detail-actions ui-form-actions">
        <button type="button" class="secondary" data-finance-edit-focus>Editar</button>
        <a class="button-link secondary" href="${escapeAttr(buildHashHref(FINANCEIRO_MISSOES_ROUTE, { competencia: mission.competencia }))}">Fechar detalhe</a>
      </div>
      ${renderMissionDestructiveAction(destructiveAction)}
    </div>
  `;
}

function renderOperationalPanelHeader(mission) {
  const selected = Boolean(mission?.id);
  return `
    <div class="financeiro-missoes-operational-header">
      <div>
        <span>Painel operacional</span>
        <h2 id="financeMissionOperationalTitle">${selected ? "Fluxo da missão" : "Fluxo de lançamento"}</h2>
        <p>${selected
          ? "Registro salvo, rascunho de edição, prévia e recálculo ficam separados no mesmo painel."
          : "Comece uma nova missão e acompanhe a prévia financeira sem trocar de página."}</p>
      </div>
      <span class="status-pill ${selected ? "status-yellow" : "status-green"}">${selected ? `Missão salva #${escapeHtml(mission.id)}` : "Nova missão"}</span>
    </div>
  `;
}

function preflightOperationalMessage(preflightPayload) {
  const preflight = preflightDataFromPayload(preflightPayload);
  if (!preflight || typeof preflight !== "object") return "";
  if (preflight.calculavel === true) {
    return "Missao liberada para recalcular com seguranca no backend.";
  }
  if (preflight.calculavel === false) {
    const blocks = preflightBlockList(preflight);
    const firstBlock = blocks[0];
    if (firstBlock?.message) {
      return `Nao e possivel recalcular porque ${String(firstBlock.message).replace(/\.$/, "")}.`;
    }
    return "Nao e possivel recalcular enquanto houver bloqueios de elegibilidade.";
  }
  return "";
}

function renderPreflightHints(runtime) {
  const preflight = runtime?.preflightPayload || {};
  const blocks = preflightBlockList(preflight);
  if (!blocks.length) {
    if (runtime?.calcStatus === "calculado") {
      return `<small>Calculo pronto. Use "Ver memoria" para conferir a trilha no backend.</small>`;
    }
    return `<small>Execute o preflight para verificar se a missao pode ser recalculada com seguranca.</small>`;
  }
  return `
    <div class="financeiro-missoes-preflight-list" data-finance-preflight-blocks>
      <strong>Bloqueios atuais</strong>
      <ul>
        ${blocks
          .slice(0, 3)
          .map((block) => `<li>${escapeHtml(String(block?.message || "Bloqueio de elegibilidade identificado."))}</li>`)
          .join("")}
      </ul>
    </div>
  `;
}

function financialPreviewState(mission, runtime) {
  if (!mission) {
    return {
      key: "insufficient",
      label: "Sem dados suficientes",
      detail: "Salve ou selecione uma missão para validar pendências e preparar a prévia financeira.",
      tone: "neutral",
    };
  }
  if (runtime?.calcStatus === "bloqueada") {
    return {
      key: "blocked",
      label: "Bloqueada por inconsistência",
      detail: missionPendingDetail(mission, runtime),
      tone: "danger",
    };
  }
  if (runtime?.calcStatus === "calculado") {
    return {
      key: "available",
      label: "Prévia disponível",
      detail: `${runtime.calculationCount || 0} registro(s) financeiro(s) encontrados para esta missão.`,
      tone: "positive",
    };
  }
  if (runtime?.calcStatus === "obsoleto") {
    return {
      key: "outdated",
      label: "Cálculo obsoleto",
      detail: "Recalcule após revisar os dados operacionais e o preflight.",
      tone: "warning",
    };
  }
  if (preflightDataFromPayload(runtime?.preflightPayload)?.calculavel === true) {
    return {
      key: "ready",
      label: "Estado de cálculo disponível",
      detail: "Preflight aprovado. O recálculo pode ser executado pelo backend.",
      tone: "positive",
    };
  }
  return {
    key: "pending",
    label: "Pendente de dados",
    detail: "Execute o preflight para verificar elegibilidade antes do recálculo.",
    tone: "warning",
  };
}

function renderMissionRecalculationPanel(mission, runtime, capabilities) {
  const canRecalculate = capabilities.has("finance:missions:recalculate");
  const canReadPreflight = capabilities.has("finance:missions:read");
  const disabledReason = !mission
    ? "Selecione uma missao operacional para calcular a bonificacao horaria."
    : missionIsDeleted(mission)
      ? "Missoes excluidas nao podem ser recalculadas."
    : mission.status === "cancelada"
      ? "Missoes canceladas nao podem ser recalculadas."
      : !canRecalculate
        ? "Seu perfil nao possui permissao para recalcular missoes."
        : "";
  const preflightMessage = preflightOperationalMessage(runtime?.preflightPayload);
  return `
    <div class="financeiro-missoes-recalc-card">
      <div class="financeiro-missoes-preview-head">
        <div>
          <strong>Recálculo definitivo</strong>
          <span>Use somente depois de salvar a missão. Esta ação atualiza o cálculo vigente no backend.</span>
        </div>
      </div>
      <div id="financeMissionPreflightFeedback" aria-live="polite"></div>
      <div id="financeMissionRecalculateFeedback" aria-live="polite"></div>
      <div class="financeiro-missoes-recalc-actions">
        ${mission && canReadPreflight
          ? '<button type="button" id="financeMissionPreflightButton">Ver preflight</button>'
          : ""}
        ${mission && canRecalculate && mission.status !== "cancelada" && !missionIsDeleted(mission)
          ? '<button type="button" id="financeMissionRecalculateButton" data-finance-operation="recalculate">Recalcular missão</button>'
          : `<button type="button" disabled>${mission ? "Recalcular missão" : "Selecione uma missao"}</button>`}
        <a class="button-link secondary" href="${escapeAttr(buildHashHref(FINANCEIRO_BONIFICACOES_HORARIA_ROUTE, { competencia: mission?.competencia || currentCompetencia() }))}">Ver calculo</a>
        <a class="button-link secondary" href="${escapeAttr(buildHashHref(FINANCEIRO_BONIFICACOES_HORARIA_ROUTE, { competencia: mission?.competencia || currentCompetencia() }))}">Ver memoria</a>
        <a class="button-link secondary" href="${escapeAttr(buildHashHref(FINANCEIRO_BONIFICACOES_ROUTE, { competencia: mission?.competencia || currentCompetencia() }))}">Ir para Bonificacoes</a>
      </div>
      ${disabledReason ? `<small>${escapeHtml(disabledReason)}</small>` : ""}
      ${preflightMessage ? `<small>${escapeHtml(preflightMessage)}</small>` : ""}
      ${renderPreflightHints(runtime)}
    </div>
  `;
}

function renderMissionFinancialPreviewStrip(runtime = null) {
  const latestCalculation = runtime?.latestCalculation;
  return `
    <div class="financeiro-missoes-preview-card financeiro-missoes-preview-strip" data-preview-state="sem_dados_suficientes" data-finance-preview-card>
      <div class="financeiro-missoes-preview-head">
        <div>
          <strong>Prévia financeira automática</strong>
          <span>Atualiza enquanto você preenche os dados. Não salva missão, cálculo ou bonificação.</span>
        </div>
        <span class="status-pill ${previewStatusClass("sem_dados_suficientes")}" data-finance-preview-status>${escapeHtml(previewStatusLabel("sem_dados_suficientes"))}</span>
      </div>
      <div class="financeiro-missoes-preview-body" data-finance-preview-body>
        ${renderPreviewInitialContent("sem_dados_suficientes")}
      </div>
      <small data-finance-preview-updated>${latestCalculation?.id ? `Cálculo persistido mais recente: #${escapeHtml(latestCalculation.id)}.` : "A prévia será atualizada automaticamente conforme os campos obrigatórios forem preenchidos."}</small>
    </div>
  `;
}

function renderOptionsFeedback(optionState) {
  const messages = [];
  if (optionState.tripulantes.status !== "ready") {
    messages.push({
      title: "Opcoes de tripulantes indisponiveis",
      detail: `${optionState.tripulantes.detail} Fonte prevista: ${optionState.tripulantes.endpoint}.`,
      type: optionState.tripulantes.status === "forbidden" ? "warning" : "info",
    });
  }
  if (optionState.equipamentos.status !== "ready") {
    messages.push({
      title: "Opcoes de aeronave/equipamento indisponiveis",
      detail: `${optionState.equipamentos.detail} Fonte prevista: ${optionState.equipamentos.endpoint}.`,
      type: optionState.equipamentos.status === "forbidden" ? "warning" : "info",
    });
  }
  if (optionState.equipamentos.status === "ready" && !optionState.equipamentos.items.some((item) => item.category)) {
    messages.push({
      title: "Categoria operacional manual",
      detail: "Nenhum equipamento carregado trouxe categoria operacional; o backend normaliza a/b para categoria a/b antes de buscar parametro financeiro.",
      type: "info",
    });
  }
  if (!messages.length) return "";
  return `
    <div class="financeiro-missoes-options-feedback">
      ${messages.map((message) => responsiveStateMarkup({ ...message, compact: true })).join("")}
    </div>
  `;
}

function optionInputDisabledAttr(disabled) {
  return disabled ? "disabled" : "";
}

function renderOptionCombobox({
  name,
  label,
  mission,
  optionsState,
  disabled = false,
  required = false,
  fallbackLabel,
  placeholder,
}) {
  const value = mission?.[name] || "";
  if (optionsState.status !== "ready") {
    return `
      <label>${fallbackLabel || `${label} ID`}
        <input name="${name}" type="number" min="1" step="1" ${required ? "required" : ""} ${optionInputDisabledAttr(disabled)} value="${fieldValue(mission, name)}">
        <span class="financeiro-missoes-field-help">Fallback por ID: ${escapeHtml(optionsState.detail)}</span>
      </label>
    `;
  }
  const datalistId = `${name}_options`;
  return `
    <label class="financeiro-missoes-combobox">${label}
      <input
        type="search"
        list="${escapeAttr(datalistId)}"
        data-finance-option-search="${escapeAttr(name)}"
        placeholder="${escapeAttr(placeholder || "Digite para pesquisar")}"
        value="${escapeAttr(optionDisplayValue(optionsState, value))}"
        autocomplete="off"
        ${required ? "required" : ""}
        ${optionInputDisabledAttr(disabled)}
      >
      <input
        name="${escapeAttr(name)}"
        type="hidden"
        data-finance-option-value="${escapeAttr(name)}"
        value="${fieldValue(mission, name)}"
        ${optionInputDisabledAttr(disabled)}
      >
      <datalist id="${escapeAttr(datalistId)}">
        ${optionsState.items
          .map((item) => `<option value="${escapeAttr(item.display)}" data-option-id="${escapeAttr(item.id)}" data-category="${escapeAttr(item.category)}"></option>`)
          .join("")}
      </datalist>
      <span class="financeiro-missoes-field-help">Selecione do cadastro ou digite o ID no inicio.</span>
    </label>
  `;
}

function renderEquipmentSelect({ mission, optionsState, disabled = false }) {
  const name = "aeronave_id";
  if (optionsState.status !== "ready") {
    return `
      <label>Aeronave ID
        <input name="${name}" type="number" min="1" step="1" ${optionInputDisabledAttr(disabled)} value="${fieldValue(mission, name)}">
        <span class="financeiro-missoes-field-help">Fallback por ID: ${escapeHtml(optionsState.detail)}</span>
      </label>
    `;
  }
  const value = String(mission?.[name] || "");
  return `
    <label>Aeronave / equipamento
      <select name="${name}" data-finance-equipment-select ${optionInputDisabledAttr(disabled)}>
        <option value="">Selecione um equipamento cadastrado</option>
        ${optionsState.items
          .map((item) => `
            <option
              value="${escapeAttr(item.id)}"
              data-category="${escapeAttr(item.category)}"
              ${String(item.id) === value ? "selected" : ""}
            >${escapeHtml(item.display)}</option>
          `)
          .join("")}
      </select>
      <span class="financeiro-missoes-field-help">Lista carregada do cadastro de equipamentos.</span>
    </label>
  `;
}

function renderTripulanteSelect({
  name,
  label,
  fallbackLabel,
  mission,
  optionsState,
  disabled = false,
  required = false,
}) {
  if (optionsState.status !== "ready") {
    return `
      <label>${fallbackLabel || `${label} ID`}
        <input name="${name}" type="number" min="1" step="1" ${required ? "required" : ""} ${optionInputDisabledAttr(disabled)} value="${fieldValue(mission, name)}">
        <span class="financeiro-missoes-field-help">Fallback por ID: ${escapeHtml(optionsState.detail)}</span>
      </label>
    `;
  }
  const value = String(mission?.[name] || "");
  return `
    <label>${label}
      <select name="${escapeAttr(name)}" data-finance-crew-select ${required ? "required" : ""} ${optionInputDisabledAttr(disabled)}>
        <option value="">Selecione um tripulante cadastrado</option>
        ${optionsState.items
          .map((item) => `
            <option value="${escapeAttr(item.id)}" ${String(item.id) === value ? "selected" : ""}>
              ${escapeHtml(item.display)}
            </option>
          `)
          .join("")}
      </select>
      <span class="financeiro-missoes-field-help">Lista completa carregada do cadastro de tripulantes.</span>
    </label>
  `;
}

function renderMissionForm({ mission, capabilities, optionState, runtime = null }) {
  const editing = Boolean(mission?.id);
  const canCreate = capabilities.has("finance:missions:create");
  const canUpdate = capabilities.has("finance:missions:update");
  const canSubmit = editing ? canUpdate : canCreate;
  const workflowState = editing ? "editando_missao_existente" : "nova_missao";
  return `
    <form id="financeMissionForm" class="financeiro-missoes-form ui-stack-sm" data-editing="${editing ? "true" : "false"}" data-workflow-state="${workflowState}">
      <div class="financeiro-missoes-form-head">
        <div>
          <h2>${editing ? "Editando missão existente" : "Nova missão"}</h2>
          <p>${editing
            ? "A prévia usa o rascunho alterado; o cálculo vigente só muda depois de salvar e recalcular."
            : "Preencha os dados operacionais. A prévia aparece sem criar missão ou bonificação."}</p>
        </div>
        ${editing ? `<span class="status-pill ${missionStatusClass(mission.status)}">${escapeHtml(mission.status || "-")}</span>` : ""}
      </div>
      <div class="financeiro-missoes-workflow-state financeiro-missoes-draft-alert" data-finance-draft-state>
        <div>
          <strong>${editing ? "Alterações ainda não salvas" : "Rascunho de nova missão"}</strong>
          <span>${editing
            ? "Salvar alterações atualiza apenas a missão operacional. Recalcular missão fica disponível para atualizar o cálculo vigente."
            : "Salvar missão cria o registro operacional. Recalcular não aparece antes de a missão existir no backend."}</span>
        </div>
        <span class="status-pill ${editing ? "status-yellow" : "status-green"}">${editing ? "Edição" : "Criação"}</span>
      </div>
      <div id="financeMissionFormFeedback" aria-live="polite"></div>
      ${renderMissionFinancialPreviewStrip(runtime)}
      <div class="financeiro-missoes-form-grid">
        <fieldset class="financeiro-missoes-form-section" data-section="identification">
          <legend>Identificação</legend>
          <div class="financeiro-missoes-section-grid">
            <label>Competência
              <input name="competencia" type="month" required value="${fieldValue(mission, "competencia", currentCompetencia())}">
            </label>
            <label>Data da missão
              <input name="data_missao" type="date" required value="${fieldValue(mission, "data_missao")}">
            </label>
            <label>Cavok / número do voo
              <input name="cavok_numero_voo" type="text" value="${fieldValue(mission, "cavok_numero_voo")}">
            </label>
            <label>Status
              <select name="status">
                ${["rascunho", "ativa", "cancelada", "recalculo_pendente"]
                  .map((status) => `<option value="${status}" ${String(mission?.status || "ativa") === status ? "selected" : ""}>${status}</option>`)
                  .join("")}
              </select>
            </label>
            <label>Contratante
              <input name="contratante" type="text" value="${fieldValue(mission, "contratante")}">
            </label>
            <label>Chamado
              <input name="chamado" type="text" value="${fieldValue(mission, "chamado")}">
            </label>
          </div>
        </fieldset>

        <fieldset class="financeiro-missoes-form-section" data-section="operation">
          <legend>Aeronave e operação</legend>
          <div class="financeiro-missoes-section-grid">
            ${renderEquipmentSelect({ mission, optionsState: optionState.equipamentos })}
            <label>Categoria operacional
              <input name="categoria_financeira_aeronave" type="text" data-finance-category-field value="${fieldValue(mission, "categoria_financeira_aeronave")}">
              <span class="financeiro-missoes-field-help">Pode vir como a/b do cadastro operacional; o backend normaliza para categoria a/b na busca financeira.</span>
              <span class="financeiro-missoes-field-help" data-finance-category-feedback></span>
            </label>
            <label class="financeiro-missoes-wide">Condição operacional especial
              <input name="operacao_especial" type="text" list="financeMissionSpecialOperationOptions" value="${fieldValue(mission, "operacao_especial")}" placeholder="Ex.: Palmas turboélice">
              <datalist id="financeMissionSpecialOperationOptions">
                <option value="Palmas turboélice"></option>
              </datalist>
              <span class="financeiro-missoes-field-badge status-pill status-yellow">Impacta cálculo financeiro</span>
              <span class="financeiro-missoes-field-help">Opcional. Use quando a missão tiver uma condição reconhecida que altere a bonificação, como Palmas turboélice. Em branco, o cálculo segue a regra padrão.</span>
            </label>
            <label class="financeiro-missoes-wide">Trecho
              <input name="trecho" type="text" value="${fieldValue(mission, "trecho")}">
            </label>
          </div>
        </fieldset>

        <fieldset class="financeiro-missoes-form-section" data-section="crew">
          <legend>Tripulação</legend>
          <div class="financeiro-missoes-section-grid">
            ${renderTripulanteSelect({
              name: "comandante_tripulante_id",
              label: "Comandante",
              fallbackLabel: "Comandante tripulante ID",
              mission,
              optionsState: optionState.tripulantes,
              disabled: editing,
              required: true,
            })}
            ${renderTripulanteSelect({
              name: "copiloto_tripulante_id",
              label: "Copiloto",
              fallbackLabel: "Copiloto tripulante ID",
              mission,
              optionsState: optionState.tripulantes,
              disabled: editing,
              required: true,
            })}
          </div>
        </fieldset>

        <fieldset class="financeiro-missoes-form-section" data-section="times">
          <legend>Horários</legend>
          <div class="financeiro-missoes-section-grid">
            <label>Horário de apresentação
              <input name="horario_apresentacao" type="datetime-local" required value="${escapeAttr(datetimeLocalValue(mission?.horario_apresentacao))}">
            </label>
            <label>Horário de abandono
              <input name="horario_abandono" type="datetime-local" required value="${escapeAttr(datetimeLocalValue(mission?.horario_abandono))}">
            </label>
          </div>
        </fieldset>

        <fieldset class="financeiro-missoes-form-section" data-section="additional">
          <legend>Informações adicionais</legend>
          <div class="financeiro-missoes-section-grid">
            <label>Quantidade de pernoites
              <input name="quantidade_pernoites" type="number" min="0" step="1" value="${fieldValue(mission, "quantidade_pernoites", "0")}">
            </label>
            <label class="financeiro-missoes-check">
              <input name="houve_pernoite" type="checkbox" ${checkboxAttr(mission?.houve_pernoite)}>
              Houve pernoite
            </label>
            <label class="financeiro-missoes-check">
              <input name="cobertura_base" type="checkbox" ${checkboxAttr(mission?.cobertura_base)}>
              Cobertura de base
            </label>
            <label class="financeiro-missoes-wide">Observações
              <textarea name="observacoes" rows="3">${escapeHtml(mission?.observacoes || "")}</textarea>
            </label>
          </div>
        </fieldset>
      </div>
      ${editing ? '<div class="hint">Troca de comandante/copiloto sera feita em etapa posterior com controle de participantes.</div>' : ""}
      <div class="form-actions ui-form-actions financeiro-missoes-form-actions">
        ${canSubmit ? `<button type="submit" data-finance-operation="save" data-finance-form-submit>${editing ? "Salvar alterações" : "Salvar missão"}</button>` : '<div class="hint">Seu perfil nao possui permissao para salvar missoes operacionais.</div>'}
        <a class="button-link secondary" href="${escapeAttr(buildHashHref(FINANCEIRO_MISSOES_ROUTE, { competencia: mission.competencia || currentCompetencia() }))}">${editing ? "Cancelar edição" : "Cancelar"}</a>
      </div>
    </form>
  `;
}

function formPayload(form, { editing = false } = {}) {
  const data = Object.fromEntries(new FormData(form).entries());
  data.houve_pernoite = Boolean(form.elements.houve_pernoite?.checked);
  data.cobertura_base = Boolean(form.elements.cobertura_base?.checked);
  if (editing) {
    delete data.comandante_tripulante_id;
    delete data.copiloto_tripulante_id;
  }
  return data;
}

function previewPayload(form, selectedMission = null) {
  const data = {
    ...(selectedMission || {}),
    ...Object.fromEntries(new FormData(form).entries()),
  };
  data.houve_pernoite = Boolean(form.elements.houve_pernoite?.checked);
  data.cobertura_base = Boolean(form.elements.cobertura_base?.checked);
  data.comandante_tripulante_id = data.comandante_tripulante_id || selectedMission?.comandante_tripulante_id || "";
  data.copiloto_tripulante_id = data.copiloto_tripulante_id || selectedMission?.copiloto_tripulante_id || "";
  data.aeronave_id = data.aeronave_id || selectedMission?.aeronave_id || "";
  data.status = data.status || selectedMission?.status || "rascunho";
  return data;
}

function missingPreviewFields(payload) {
  return PREVIEW_REQUIRED_FIELDS.filter((field) => {
    const value = payload?.[field.key];
    return value === null || value === undefined || String(value).trim() === "";
  });
}

function previewSignature(payload) {
  const keys = [
    "id",
    "competencia",
    "data_missao",
    "cavok_numero_voo",
    "aeronave_id",
    "categoria_financeira_aeronave",
    "comandante_tripulante_id",
    "copiloto_tripulante_id",
    "horario_apresentacao",
    "horario_abandono",
    "status",
    "trecho",
    "houve_pernoite",
    "quantidade_pernoites",
    "cobertura_base",
    "operacao_especial",
  ];
  return JSON.stringify(keys.map((key) => [key, payload?.[key] ?? ""]));
}

function previewElements() {
  const card = document.querySelector("[data-finance-preview-card]");
  return {
    card,
    status: card?.querySelector("[data-finance-preview-status]") || null,
    body: card?.querySelector("[data-finance-preview-body]") || null,
    updated: card?.querySelector("[data-finance-preview-updated]") || null,
  };
}

function renderFinancePreviewState(state, { preview = null, missingFields = [], error = null, message = "" } = {}) {
  const elements = previewElements();
  if (!elements.card || !elements.status || !elements.body) return;
  elements.card.dataset.previewState = state;
  elements.status.className = `status-pill ${previewStatusClass(state)}`;
  elements.status.textContent = previewStatusLabel(state);

  if (state === "carregando") {
    elements.body.innerHTML = renderPreviewInitialContent("carregando");
  } else if (state === "pendente_dados") {
    elements.body.innerHTML = renderPreviewPending(missingFields);
  } else if (state === "disponivel" && preview) {
    elements.body.innerHTML = renderPreviewSummary(preview);
  } else if (state === "bloqueada" && preview) {
    elements.body.innerHTML = renderPreviewInitialContent("bloqueada", preview);
  } else if (state === "erro") {
    elements.body.innerHTML = `<p>${escapeHtml(error?.message || message || "Não foi possível calcular a prévia financeira agora.")}</p>`;
  } else if (state === "salva" || state === "recalculada") {
    elements.body.innerHTML = `<p>${escapeHtml(message || "Prévia atualizada com os dados mais recentes.")}</p>`;
  } else {
    elements.body.innerHTML = renderPreviewInitialContent("sem_dados_suficientes");
  }

  if (elements.updated) {
    const timestamp = preview?.generated_at ? formatPreviewTimestamp(preview.generated_at) : "";
    elements.updated.textContent = timestamp
      ? `Última atualização da prévia: ${timestamp}.`
      : "A prévia será atualizada automaticamente conforme os dados obrigatórios forem preenchidos.";
  }
}

function optionIdFromInput(input) {
  const rawValue = String(input?.value || "").trim();
  if (!rawValue) return "";
  const matchingOption = Array.from(input.list?.options || []).find((option) => option.value === rawValue);
  if (matchingOption?.dataset?.optionId) return matchingOption.dataset.optionId;
  const match = rawValue.match(/^(\d+)(?:\s*-\s*|\s|$)/);
  return match ? match[1] : "";
}

function markCrewFields(form, hasConflict) {
  ["comandante_tripulante_id", "copiloto_tripulante_id"].forEach((name) => {
    const search = form.querySelector(`[data-finance-option-search="${name}"]`);
    const select = form.querySelector(`[data-finance-crew-select][name="${name}"]`);
    const input = search || select || form.elements[name];
    input?.classList.toggle("is-invalid", hasConflict);
    input?.setAttribute("aria-invalid", hasConflict ? "true" : "false");
  });
}

function validateMissionCrew(form, { editing = false } = {}) {
  if (editing) return true;
  const comandanteId = String(form.elements.comandante_tripulante_id?.value || "").trim();
  const copilotoId = String(form.elements.copiloto_tripulante_id?.value || "").trim();
  const feedback = document.getElementById("financeMissionFormFeedback");
  markCrewFields(form, false);
  if (!comandanteId || !copilotoId) {
    renderInlineFeedback(feedback, "Informe comandante e copiloto a partir do cadastro de tripulantes ou pelo ID.", "warning");
    return false;
  }
  if (comandanteId === copilotoId) {
    markCrewFields(form, true);
    renderInlineFeedback(feedback, "Comandante e copiloto devem ser tripulantes distintos.", "warning");
    return false;
  }
  return true;
}

function updateCategoryFeedback(form, message) {
  const feedback = form.querySelector("[data-finance-category-feedback]");
  if (feedback) feedback.textContent = message || "";
}

function syncOptionInput(input, form) {
  const name = input.dataset.financeOptionSearch;
  const hidden = form.querySelector(`[data-finance-option-value="${name}"]`);
  const optionId = optionIdFromInput(input);
  if (hidden) hidden.value = optionId;
  input.classList.toggle("is-invalid", Boolean(input.value.trim()) && !optionId);
  input.setAttribute("aria-invalid", Boolean(input.value.trim()) && !optionId ? "true" : "false");
  if (name === "aeronave_id") {
    const matchingOption = Array.from(input.list?.options || []).find((option) => option.value === input.value);
    const category = matchingOption?.dataset?.category || "";
    const categoryInput = form.elements.categoria_financeira_aeronave;
    if (!categoryInput) return;
    if (category) {
      categoryInput.value = category;
      categoryInput.dataset.categorySource = "equipamento";
      updateCategoryFeedback(form, "Preenchida pelo cadastro do equipamento.");
      return;
    }
    if (optionId) {
      if (categoryInput.dataset.categorySource === "equipamento") {
        categoryInput.value = "";
      }
      delete categoryInput.dataset.categorySource;
      updateCategoryFeedback(form, "Categoria operacional nao cadastrada para este equipamento.");
      return;
    }
    updateCategoryFeedback(form, "Informe manualmente quando a categoria nao vier do cadastro.");
  }
}

function syncEquipmentSelect(select, form) {
  const categoryInput = form.elements.categoria_financeira_aeronave;
  if (!categoryInput) return;
  const selectedOption = select.selectedOptions?.[0];
  const category = selectedOption?.dataset?.category || "";
  if (category) {
    categoryInput.value = category;
    categoryInput.dataset.categorySource = "equipamento";
    updateCategoryFeedback(form, "Preenchida pelo cadastro do equipamento.");
    return;
  }
  if (select.value) {
    if (categoryInput.dataset.categorySource === "equipamento") {
      categoryInput.value = "";
    }
    delete categoryInput.dataset.categorySource;
    updateCategoryFeedback(form, "Categoria operacional nao cadastrada para este equipamento.");
    return;
  }
  updateCategoryFeedback(form, "Informe manualmente quando a categoria nao vier do cadastro.");
}

function wireOptionComboboxes(form) {
  form.querySelectorAll("[data-finance-option-search]").forEach((input) => {
    syncOptionInput(input, form);
    input.addEventListener("input", () => {
      syncOptionInput(input, form);
      markCrewFields(form, false);
    });
    input.addEventListener("change", () => {
      syncOptionInput(input, form);
      validateMissionCrew(form, { editing: form.dataset.editing === "true" });
    });
  });
  form.querySelectorAll("[data-finance-equipment-select]").forEach((select) => {
    syncEquipmentSelect(select, form);
    select.addEventListener("change", () => {
      syncEquipmentSelect(select, form);
    });
  });
  const categoryInput = form.elements.categoria_financeira_aeronave;
  categoryInput?.addEventListener("input", () => {
    categoryInput.dataset.categorySource = "manual";
    updateCategoryFeedback(
      form,
      categoryInput.value.trim()
        ? "Categoria operacional editada manualmente."
        : "Informe manualmente quando a categoria nao vier do cadastro.",
    );
  });
}

function setupFinanceMissionPreview({ form, selectedMission = null, previewStatus = "" }) {
  if (!form) return;
  let previewTimer = null;
  let previewRequestSeq = 0;
  let lastPreviewSignature = "";

  const runPreview = async () => {
    if (form.dataset.financeOperationState === "saving") return;
    const payload = previewPayload(form, selectedMission);
    const missingFields = missingPreviewFields(payload);
    if (missingFields.length >= PREVIEW_REQUIRED_FIELDS.length - 1) {
      lastPreviewSignature = "";
      renderFinancePreviewState("sem_dados_suficientes");
      return;
    }
    if (missingFields.length) {
      lastPreviewSignature = "";
      renderFinancePreviewState("pendente_dados", { missingFields });
      return;
    }

    const signature = previewSignature(payload);
    if (signature === lastPreviewSignature) return;
    lastPreviewSignature = signature;
    const requestSeq = previewRequestSeq + 1;
    previewRequestSeq = requestSeq;
    renderFinancePreviewState("carregando");
    try {
      const result = await previewFinanceiroMissao(payload);
      if (requestSeq !== previewRequestSeq) return;
      if (form.dataset.financeOperationState === "saving") return;
      const preview = result?.preview || {};
      const status = String(preview.status || "disponivel").trim();
      if (status === "pendente_dados") {
        renderFinancePreviewState("pendente_dados", { preview, missingFields: preview.campos_faltantes || [] });
      } else if (status === "bloqueada") {
        renderFinancePreviewState("bloqueada", { preview });
      } else {
        renderFinancePreviewState("disponivel", { preview });
      }
    } catch (error) {
      if (requestSeq !== previewRequestSeq) return;
      renderFinancePreviewState("erro", { error });
    }
  };

  const schedulePreview = () => {
    if (previewTimer) window.clearTimeout(previewTimer);
    previewTimer = window.setTimeout(runPreview, PREVIEW_DEBOUNCE_MS);
  };

  form.addEventListener("input", schedulePreview);
  form.addEventListener("change", schedulePreview);

  if (previewStatus === "salva") {
    renderFinancePreviewState("salva", { message: "Missão salva. A prévia foi refeita com os dados persistidos; nenhum recálculo definitivo foi disparado automaticamente." });
  } else if (previewStatus === "recalculada") {
    renderFinancePreviewState("recalculada", { message: "Recálculo concluído. O cálculo vigente da missão foi atualizado pelo backend." });
  }
  schedulePreview();
}

function renderFinanceiroMissoes({
  filters,
  listPayload,
  detailPayload,
  optionState,
  detailError = null,
  hourlyPayload = null,
  preflightByMission = new Map(),
}) {
  const capabilities = capabilitySet();
  const sourceItems = Array.isArray(listPayload?.items) ? listPayload.items : [];
  const hourlyItems = Array.isArray(hourlyPayload?.items) ? hourlyPayload.items : [];
  const runtimeMap = buildMissionRuntimeMap(sourceItems, { hourlyItems, preflightByMission });
  const items = visibleMissions(sourceItems, filters, runtimeMap);
  const pagination = listPayload?.pagination || { page: filters.page, total: sourceItems.length };
  const selectedMission = detailPayload?.mission || null;
  const selectedRuntime = selectedMission ? missionRuntimeEntry(runtimeMap, selectedMission) : null;
  const formMission = selectedMission || {
    competencia: filters.competencia,
    status: "ativa",
  };
  const filterLabels = {
    competencia: "Competencia",
    status: "Status",
    calculoStatus: "Estado de calculo",
    busca: "Busca",
  };

  renderShell(
    `
      <div class="financeiro-missoes-page priority-page-surface ui-page-shell ui-stack">
        <div class="page-header priority-page-header ui-page-header ui-surface">
          <div>
            <h1>Missões operacionais</h1>
            <p class="page-subtitle">Cadastre missões, acompanhe pendências e prepare o recálculo financeiro da competência.</p>
          </div>
          <div class="page-header-actions">
            ${capabilities.has("finance:missions:create") ? `<a class="button-link" href="${escapeAttr(buildHashHref(FINANCEIRO_MISSOES_ROUTE, { competencia: filters.competencia }))}">Nova missão</a>` : ""}
            <a class="button-link secondary" href="${escapeAttr(buildHashHref(FINANCEIRO_MISSOES_ROUTE, { competencia: currentCompetencia() }))}">Mês atual</a>
            ${selectedMission && selectedMission.status !== "cancelada" && !missionIsDeleted(selectedMission) && capabilities.has("finance:missions:recalculate") ? '<button type="button" id="financeMissionHeaderRecalculateButton" data-finance-header-recalculate data-finance-operation="recalculate">Recalcular missão</button>' : ""}
          </div>
        </div>

        <section class="panel ui-surface financeiro-missoes-notice">
          <strong>Estação financeira da competência</strong>
          <span>A prévia inline mostra status e pendências; o cálculo financeiro continua sendo executado pelo backend.</span>
        </section>

        ${renderMissionSummaryCards(sourceItems, runtimeMap)}

        <section class="panel ui-surface ui-stack-sm">
          <details class="financeiro-mobile-disclosure financeiro-missoes-filter-disclosure" open>
            <summary>Filtros da competencia</summary>
            <div class="financeiro-mobile-disclosure-body">
              <div class="financeiro-missoes-section-head">
                <div>
                  <h2>Filtros</h2>
                  <p>Filtre por competencia, status operacional, estado de calculo e busca por Cavok/chamado/contratante.</p>
                </div>
              </div>
              <form id="financeMissionFilters" class="filters-bar ui-form-toolbar ui-stack-sm">
                <div class="filters-bar-main ui-filter-row">
                  <input type="month" name="competencia" value="${escapeAttr(filters.competencia)}" aria-label="Competencia">
                  <select name="status" aria-label="Status">
                    <option value="">Ativas e pendentes</option>
                    ${["rascunho", "ativa", "cancelada", "recalculo_pendente"]
                      .map((status) => `<option value="${status}" ${filters.status === status ? "selected" : ""}>${status}</option>`)
                      .join("")}
                  </select>
                  <select name="calculo_status" aria-label="Estado de calculo">
                    <option value="">Todos os estados de calculo</option>
                    ${Object.keys(CALCULATION_STATUS_LABELS)
                      .map((status) => `<option value="${status}" ${filters.calculoStatus === status ? "selected" : ""}>${CALCULATION_STATUS_LABELS[status]}</option>`)
                      .join("")}
                  </select>
                  <input type="search" name="busca" value="${escapeAttr(filters.busca)}" placeholder="Buscar Cavok, chamado ou contratante" aria-label="Buscar Cavok, chamado ou contratante">
                  <button type="submit">Aplicar</button>
                  <a class="button-link secondary" href="${escapeAttr(buildHashHref(FINANCEIRO_MISSOES_ROUTE, { competencia: currentCompetencia() }))}">Limpar</a>
                </div>
                ${filterSummaryMarkup(
                  { competencia: filters.competencia, status: filters.status, calculoStatus: filters.calculoStatus, busca: filters.busca },
                  filterLabels,
                  { competencia: currentCompetencia() },
                )}
              </form>
            </div>
          </details>
        </section>

        <div id="financeMissionPageFeedback" aria-live="polite"></div>

        <div class="financeiro-missoes-layout">
          <section class="panel ui-surface ui-stack financeiro-missoes-list-panel" data-empty="${items.length ? "false" : "true"}">
            <div class="financeiro-missoes-section-head">
              <div>
                <h2>Lista da competência</h2>
                <p>${escapeHtml(String(items.length))} registro(s) exibido(s) de ${escapeHtml(String(pagination.total ?? sourceItems.length))} carregado(s).</p>
              </div>
            </div>
            ${renderMissionTable(items, filters, capabilities, optionState, runtimeMap)}
          </section>

          <section class="panel ui-surface ui-stack financeiro-missoes-side" aria-labelledby="financeMissionOperationalTitle">
            ${renderOperationalPanelHeader(selectedMission)}
            <div class="financeiro-missoes-side-shell">
              ${detailError ? responsiveStateMarkup({ ...requestErrorState(detailError), compact: true }) : renderMissionDetail(selectedMission, capabilities, optionState, selectedRuntime, filters)}
              ${renderMissionForm({ mission: formMission, capabilities, optionState, runtime: selectedRuntime })}
              ${renderMissionRecalculationPanel(selectedMission, selectedRuntime, capabilities)}
              ${renderOptionsFeedback(optionState)}
            </div>
          </section>
        </div>
      </div>
    `,
    "Missões Operacionais",
  );

  wireFinanceiroMissoesInteractions({ filters, selectedMission, selectedRuntime, capabilities });
}
function summarizeMissionPreflight(preflightPayload) {
  const preflight = preflightDataFromPayload(preflightPayload);
  const blocks = preflightBlockList(preflight);
  return {
    calculavel: preflight?.calculavel === true,
    blocks,
    nextAction: String(preflight?.next_action || "").trim(),
    raw: preflight,
  };
}

function firstBlockMessage(preflightSummary) {
  if (!preflightSummary.blocks.length) return "";
  const firstBlock = preflightSummary.blocks[0];
  const text = String(firstBlock?.message || "").trim();
  if (!text) return "Bloqueio de elegibilidade identificado no preflight.";
  return `Nao e possivel recalcular porque ${text.replace(/\.$/, "")}.`;
}

function renderMissionPreflightFeedback(target, preflightSummary) {
  if (!target) return;
  if (preflightSummary.calculavel) {
    renderInlineFeedback(target, "Preflight aprovado: a missao pode ser recalculada com seguranca.", "success");
    return;
  }
  const blockText = firstBlockMessage(preflightSummary);
  const nextAction = preflightSummary.nextAction
    ? ` Proxima acao: ${preflightSummary.nextAction}.`
    : " Revise pendencias de parametros, vigencia e elegibilidade antes de tentar novamente.";
  renderInlineFeedback(target, `${blockText || "Preflight bloqueou o recalculo."}${nextAction}`, "warning");
}

async function runMissionPreflight(missionId) {
  const payload = await preflightFinanceiroMissaoCalculo(missionId);
  return summarizeMissionPreflight(payload);
}

function wireFinanceiroMissoesInteractions({ filters, selectedMission, selectedRuntime, capabilities }) {
  syncFinanceiroMissoesMobileDisclosures();

  document.getElementById("financeMissionFilters")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
    window.location.hash = buildHashHref(FINANCEIRO_MISSOES_ROUTE, payload);
  });

  const missionForm = document.getElementById("financeMissionForm");
  if (missionForm) {
    wireOptionComboboxes(missionForm);
    setupFinanceMissionPreview({ form: missionForm, selectedMission, previewStatus: filters.previewStatus });
  }

  document.querySelector("[data-finance-edit-focus]")?.addEventListener("click", () => {
    missionForm?.scrollIntoView({ behavior: "smooth", block: "start" });
    missionForm?.querySelector("input, select, textarea")?.focus();
  });

  missionForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button[type='submit']");
    const editing = form.dataset.editing === "true" && selectedMission?.id;
    const feedback = document.getElementById("financeMissionFormFeedback");
    if (!validateMissionCrew(form, { editing })) return;
    const operationKey = `save:${selectedMission?.id || "new"}`;
    if (!beginFinanceMissionOperation(operationKey, feedback)) return;
    form.dataset.financeOperationState = "saving";
    try {
      await withActionBusy(button, "Salvando...", async () => {
        try {
          const payload = formPayload(form, { editing });
          const result = editing
            ? await updateFinanceiroMissao(selectedMission.id, payload)
            : await createFinanceiroMissao(payload);
          const mission = result.mission || {};
          showFlash(editing ? "Missao operacional atualizada." : "Missao operacional criada.", "success");
          window.location.hash = buildHashHref(FINANCEIRO_MISSOES_ROUTE, {
            competencia: mission.competencia || payload.competencia || filters.competencia,
            status: filters.status,
            calculo_status: filters.calculoStatus,
            busca: filters.busca,
            mission_id: mission.id,
            preview_status: "salva",
          });
        } catch (error) {
          renderInlineFeedback(feedback, buildErrorMessage(error), error.status === 403 ? "warning" : "error");
        }
      });
    } finally {
      delete form.dataset.financeOperationState;
      endFinanceMissionOperation(operationKey);
    }
  });

  document.getElementById("financeMissionCancelButton")?.addEventListener("click", async (event) => {
    if (!selectedMission?.id) return;
    const action = missionDestructiveAction(selectedMission, selectedRuntime, capabilities);
    if (!action) return;
    if (!confirmAction({
      title: action.title,
      subject: `Missao #${selectedMission.id}`,
      consequence: action.consequence,
    })) return;
    const button = event.currentTarget;
    const feedback = document.getElementById("financeMissionPageFeedback");
    const operationKey = `${action.action}:${selectedMission.id}`;
    if (!beginFinanceMissionOperation(operationKey, feedback)) return;
    try {
      await withActionBusy(button, action.loading, async () => {
        try {
          if (action.action === "delete") {
            await deleteFinanceiroMissao(selectedMission.id, { motivo: action.reason });
          } else {
            await cancelFinanceiroMissao(selectedMission.id, { motivo: action.reason });
          }
          showFlash(action.success, "success");
          const keepSelected = action.action === "cancel" && filters.status === "cancelada";
          const nextHash = {
            competencia: selectedMission.competencia || filters.competencia,
            status: filters.status,
            calculo_status: filters.calculoStatus,
            busca: filters.busca,
            preview_status: action.action === "delete" ? "excluida" : "cancelada",
            refresh: Date.now(),
          };
          if (keepSelected) nextHash.mission_id = selectedMission.id;
          if (!keepSelected && !filters.status) nextHash.status = "";
          window.location.hash = buildHashHref(FINANCEIRO_MISSOES_ROUTE, nextHash);
        } catch (error) {
          renderInlineFeedback(feedback, buildErrorMessage(error), error.status === 403 ? "warning" : "error");
        }
      });
    } finally {
      endFinanceMissionOperation(operationKey);
    }
  });

  if (selectedRuntime?.preflightPayload) {
    const preflightSummary = summarizeMissionPreflight(selectedRuntime.preflightPayload);
    if (preflightSummary.blocks.length || preflightSummary.calculavel) {
      renderMissionPreflightFeedback(document.getElementById("financeMissionPreflightFeedback"), preflightSummary);
    }
  }

  document.getElementById("financeMissionPreflightButton")?.addEventListener("click", async (event) => {
    if (!selectedMission?.id) return;
    const feedback = document.getElementById("financeMissionPreflightFeedback");
    const button = event.currentTarget;
    await withActionBusy(button, "Validando...", async () => {
      try {
        const preflightSummary = await runMissionPreflight(selectedMission.id);
        renderMissionPreflightFeedback(feedback, preflightSummary);
      } catch (error) {
        renderInlineFeedback(feedback, buildErrorMessage(error), error.status === 403 ? "warning" : "error");
      }
    });
  });

  document.getElementById("financeMissionHeaderRecalculateButton")?.addEventListener("click", () => {
    document.getElementById("financeMissionRecalculateButton")?.click();
  });

  document.getElementById("financeMissionRecalculateButton")?.addEventListener("click", async (event) => {
    if (!selectedMission?.id) return;
    const preflightFeedback = document.getElementById("financeMissionPreflightFeedback");
    const recalculateFeedback = document.getElementById("financeMissionRecalculateFeedback");
    const button = event.currentTarget;
    const operationKey = `recalculate:${selectedMission.id}`;

    if (!beginFinanceMissionOperation(operationKey, recalculateFeedback)) return;
    try {
      await withActionBusy(button, "Recalculando...", async () => {
        try {
          const preflightSummary = await runMissionPreflight(selectedMission.id);
          renderMissionPreflightFeedback(preflightFeedback, preflightSummary);
          if (!preflightSummary.calculavel) {
            renderInlineFeedback(recalculateFeedback, "Recalculo bloqueado pelo preflight. Corrija as pendencias antes de tentar novamente.", "warning");
            return;
          }

          if (!confirmAction({
            title: "Confirmar recálculo da missão?",
            subject: `Missao #${selectedMission.id}`,
            consequence: "A operação reprocessa o cálculo financeiro vigente da missão no backend.",
          })) return;

          const result = await recalculateFinanceiroMissao(selectedMission.id);
          const calculations = Array.isArray(result?.calculations) ? result.calculations.length : 0;
          renderInlineFeedback(
            recalculateFeedback,
            `Missão recalculada pelo backend. ${calculations} cálculo(s) horário(s) vigente(s) atualizado(s). Veja o resultado na aba Bonificacoes.`,
            "success",
          );
          showFlash("Missão recalculada com preflight aprovado.", "success");

          window.location.hash = buildHashHref(FINANCEIRO_MISSOES_ROUTE, {
            competencia: selectedMission.competencia || filters.competencia,
            status: filters.status,
            calculo_status: filters.calculoStatus,
            busca: filters.busca,
            mission_id: selectedMission.id,
            preview_status: "recalculada",
            refresh: Date.now(),
          });
        } catch (error) {
          renderInlineFeedback(recalculateFeedback, buildErrorMessage(error), error.status === 403 ? "warning" : "error");
        }
      });
    } finally {
      endFinanceMissionOperation(operationKey);
    }
  });
}
function syncFinanceiroMissoesMobileDisclosures() {
  const filterDisclosure = document.querySelector(".financeiro-missoes-filter-disclosure");
  if (!filterDisclosure) return;
  filterDisclosure.open = true;
}

async function loadHourlyMissionCalculations(filters, capabilities) {
  if (!capabilities.has("finance:bonuses:read")) {
    return { items: [], pagination: { total: 0, page: 1 } };
  }
  try {
    return await listFinanceiroBonificacoesHorarias({
      competencia: filters.competencia,
      pageSize: HOURLY_PAGE_SIZE,
    });
  } catch (_error) {
    return { items: [], pagination: { total: 0, page: 1 } };
  }
}

async function loadMissionPreflightBatch(missions, capabilities) {
  const byMission = new Map();
  if (!capabilities.has("finance:missions:read")) return byMission;
  const missionIds = missions
    .map((mission) => normalizeId(mission?.id))
    .filter(Boolean)
    .slice(0, PREFLIGHT_BATCH_LIMIT);
  if (!missionIds.length) return byMission;

  let cursor = 0;
  const workerCount = Math.min(6, missionIds.length);
  const workers = Array.from({ length: workerCount }, async () => {
    while (cursor < missionIds.length) {
      const targetId = missionIds[cursor];
      cursor += 1;
      try {
        byMission.set(targetId, await preflightFinanceiroMissaoCalculo(targetId));
      } catch (error) {
        byMission.set(targetId, {
          calculavel: false,
          bloqueios: [
            {
              code: error?.code || "preflight_unavailable",
              message: buildErrorMessage(error),
              severity: "alta",
              entity_type: "finance_mission",
              entity_id: targetId,
              field: "",
              next_action: "Valide conectividade e RBAC antes de recalcular.",
            },
          ],
          next_action: "Resolver o erro de preflight antes de nova tentativa.",
        });
      }
    }
  });

  await Promise.all(workers);
  return byMission;
}

export async function renderFinanceiroMissoesPage() {
  renderPageState({
    type: "loading",
    title: "Carregando Missoes Operacionais",
    detail: "Buscando registros operacionais, permissoes e opcoes de cadastro.",
  });
  try {
    const filters = readFilters();
    const capabilities = capabilitySet();
    const listPromise = listFinanceiroMissoes({
      competencia: filters.competencia,
      status: filters.status,
      page: filters.page,
      pageSize: PAGE_SIZE,
    });
    const detailPromise = filters.missionId
      ? getFinanceiroMissao(filters.missionId)
        .then((payload) => ({ payload, error: null }))
        .catch((error) => ({ payload: null, error }))
      : Promise.resolve({ payload: null, error: null });
    const [listPayload, optionState, detailResult, hourlyPayload] = await Promise.all([
      listPromise,
      loadFinanceiroMissionOptions(capabilities),
      detailPromise,
      loadHourlyMissionCalculations(filters, capabilities),
    ]);
    const sourceItems = Array.isArray(listPayload?.items) ? listPayload.items : [];
    const preflightByMission = await loadMissionPreflightBatch(sourceItems, capabilities);
    if (filters.missionId && !preflightByMission.has(filters.missionId)) {
      try {
        preflightByMission.set(filters.missionId, await preflightFinanceiroMissaoCalculo(filters.missionId));
      } catch (_error) {
        // Ignore isolated preflight failure; the action panel will show runtime error on demand.
      }
    }
    renderFinanceiroMissoes({
      filters,
      listPayload,
      optionState,
      hourlyPayload,
      preflightByMission,
      detailPayload: detailResult.payload,
      detailError: detailResult.error,
    });
  } catch (error) {
    renderPageState(requestErrorState(error));
  }
}
