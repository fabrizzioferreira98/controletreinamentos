export const config = window.__FRONTEND_CONFIG__ || {
  appName: "Controle Treinamentos",
  apiBaseUrl: "",
  publicOrigin: window.location.origin,
  debug: false,
};

export const state = {
  session: null,
  csrfToken: "",
  flash: null,
  frontendPerf: {
    bootId: 0,
    phases: [],
  },
};

const FLASH_STORAGE_KEY = "controle_treinamentos.flash.v1";
const CORRELATION_STORAGE_KEY = "controle_treinamentos.correlation.v1";
const DEFAULT_API_TIMEOUT_MS = 45000;

const MONTH_LABELS = [
  "Janeiro",
  "Fevereiro",
  "Março",
  "Abril",
  "Maio",
  "Junho",
  "Julho",
  "Agosto",
  "Setembro",
  "Outubro",
  "Novembro",
  "Dezembro",
];

function normalizeFlashKind(kind) {
  if (kind === "success" || kind === "warning" || kind === "info" || kind === "loading") return kind;
  return "error";
}

function frontendNow() {
  return window.performance?.now?.() ?? Date.now();
}

export function resetFrontendPerf() {
  state.frontendPerf = {
    bootId: Number(state.frontendPerf?.bootId || 0) + 1,
    phases: [],
  };
  window.__FRONTEND_PERF__ = state.frontendPerf;
  return state.frontendPerf;
}

export function startFrontendPhase(name, detail = {}) {
  return {
    name,
    detail,
    startedAt: frontendNow(),
  };
}

export function finishFrontendPhase(mark, detail = {}) {
  const entry = {
    name: mark.name,
    duration_ms: Math.round((frontendNow() - mark.startedAt) * 10) / 10,
    detail: Object.assign({}, mark.detail || {}, detail || {}),
  };
  state.frontendPerf.phases.push(entry);
  window.__FRONTEND_PERF__ = state.frontendPerf;
  if (config.debug) {
    console.info("[frontend-perf]", entry);
  }
  return entry;
}

function writeStoredFlash(flash) {
  try {
    window.sessionStorage?.setItem(FLASH_STORAGE_KEY, JSON.stringify(flash));
  } catch (_error) {
    // sessionStorage can be unavailable in restricted browser contexts.
  }
}

function readStoredFlash() {
  try {
    const raw = window.sessionStorage?.getItem(FLASH_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.message) return null;
    return {
      message: String(parsed.message),
      kind: normalizeFlashKind(parsed.kind),
    };
  } catch (_error) {
    return null;
  }
}

function clearStoredFlash() {
  try {
    window.sessionStorage?.removeItem(FLASH_STORAGE_KEY);
  } catch (_error) {
    // best effort only
  }
}

function createTraceId(prefix = "web") {
  if (window.crypto?.randomUUID) return `${prefix}-${window.crypto.randomUUID()}`;
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

function clientCorrelationId() {
  try {
    const existing = window.sessionStorage?.getItem(CORRELATION_STORAGE_KEY);
    if (existing) return existing;
    const created = createTraceId("webcorr");
    window.sessionStorage?.setItem(CORRELATION_STORAGE_KEY, created);
    return created;
  } catch (_error) {
    return createTraceId("webcorr");
  }
}

function createApiError(message, { status = 0, code = "frontend_api_error", requestId = "", correlationId = "" } = {}) {
  const error = new Error(message);
  error.status = status;
  error.code = code;
  error.requestId = requestId;
  error.correlationId = correlationId;
  return error;
}

function apiTimeoutError(timeoutMs) {
  return createApiError(`Tempo limite excedido após ${Math.round(timeoutMs / 1000)}s.`, {
    code: "timeout",
  });
}

function handleApiErrorSideEffects(error, options = {}) {
  if (error?.code === "auth_user_inactive") {
    state.session = null;
    state.csrfToken = "";
    showFlash("Seu usuário está inativo. Contate o administrador.", "error");
    if (routePath() !== "#/login") {
      window.location.hash = "#/login";
    }
    return;
  }
  if (error?.status !== 401 || options.handleAuth === false) return;
  state.session = null;
  state.csrfToken = "";
  showFlash("Sua sessão expirou. Entre novamente para continuar.", "warning");
  if (routePath() !== "#/login") {
    window.location.hash = "#/login";
  }
}

async function readJsonResponse(response, requestId, correlationId = "") {
  try {
    return await response.json();
  } catch (_error) {
    throw createApiError("Resposta inesperada do servidor: JSON inválido.", {
      status: response.status,
      code: "invalid_json",
      requestId,
      correlationId,
    });
  }
}

export async function api(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});
  if (!headers.has("Accept")) headers.set("Accept", "application/json");
  if (options.json) headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD"].includes(method) && state.csrfToken && !headers.has("X-CSRFToken")) {
    headers.set("X-CSRFToken", state.csrfToken);
  }
  if (!headers.has("X-Correlation-ID")) headers.set("X-Correlation-ID", clientCorrelationId());
  if (!headers.has("X-Request-ID")) headers.set("X-Request-ID", createTraceId("webreq"));
  const outboundRequestId = headers.get("X-Request-ID") || "";
  const outboundCorrelationId = headers.get("X-Correlation-ID") || "";

  const timeoutMs = Number(options.timeoutMs ?? config.apiTimeoutMs ?? DEFAULT_API_TIMEOUT_MS);
  const controller = timeoutMs > 0 && typeof AbortController !== "undefined" ? new AbortController() : null;
  const timeoutId = controller ? window.setTimeout(() => controller.abort(), timeoutMs) : null;

  let response;
  try {
    response = await fetch(`${config.apiBaseUrl}${path}`, {
      method,
      headers,
      body: options.json ? JSON.stringify(options.json) : options.body,
      credentials: "include",
      signal: controller?.signal,
    });
  } catch (error) {
    const normalizedError = error?.name === "AbortError"
      ? apiTimeoutError(timeoutMs)
      : createApiError("Não foi possível conectar ao servidor.", {
          code: "network_error",
          requestId: outboundRequestId,
          correlationId: outboundCorrelationId,
        });
    normalizedError.requestId = normalizedError.requestId || outboundRequestId;
    normalizedError.correlationId = normalizedError.correlationId || outboundCorrelationId;
    normalizedError.cause = error;
    throw normalizedError;
  } finally {
    if (timeoutId) window.clearTimeout(timeoutId);
  }

  const requestId = response.headers.get("X-Request-ID") || outboundRequestId;
  const correlationId = response.headers.get("X-Correlation-ID") || outboundCorrelationId;
  const contentType = response.headers.get("Content-Type") || "";

  if (!response.ok && contentType.includes("application/json")) {
    const payload = await readJsonResponse(response, requestId, correlationId);
    const error = new Error(payload.message || `Falha HTTP ${response.status}`);
    error.status = response.status;
    error.code = payload.code;
    error.requestId = payload.request_id || requestId;
    error.correlationId = payload.correlation_id || correlationId;
    handleApiErrorSideEffects(error, options);
    throw error;
  }

  if (!response.ok) {
    const error = new Error(`Falha HTTP ${response.status}`);
    error.status = response.status;
    error.requestId = requestId;
    error.correlationId = correlationId;
    handleApiErrorSideEffects(error, options);
    throw error;
  }

  if (contentType.includes("application/json")) {
    return { response, data: await readJsonResponse(response, requestId, correlationId), requestId, correlationId };
  }

  return { response, data: await response.blob(), requestId, correlationId };
}

export async function refreshSession() {
  const { data } = await api("/api/v1/session", { handleAuth: false });
  state.session = data;
  state.csrfToken = data.csrf_token || "";
  return data;
}

export function showFlash(message, kind = "error") {
  const flash = { message: String(message || ""), kind: normalizeFlashKind(kind) };
  state.flash = flash;
  if (flash.message) writeStoredFlash(flash);
}

export function consumeFlash() {
  const flash = state.flash || readStoredFlash();
  state.flash = null;
  clearStoredFlash();
  return flash;
}

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export function escapeAttr(value) {
  return escapeHtml(value);
}

export function buildErrorMessage(error) {
  if (error?.code === "timeout") {
    return "Tempo limite excedido. Verifique a conexão e tente novamente.";
  }
  if (error?.code === "network_error") {
    return "Não foi possível conectar ao servidor. Verifique a rede e tente novamente.";
  }
  if (error?.status === 401 || error?.code === "auth_required") {
    return "Sua sessão expirou. Entre novamente para continuar.";
  }
  if (error?.code === "auth_user_inactive") {
    return "Seu usuário está inativo. Contate o administrador.";
  }
  if (error?.code === "auth_session_expired") {
    return "Sua sessão expirou. Entre novamente para continuar.";
  }
  if (error?.code === "auth_session_invalid") {
    return "Sua sessão não é mais válida. Entre novamente para continuar.";
  }
  if (error?.code === "auth_backend_unavailable") {
    return "Não foi possível validar sua sessão agora. Tente novamente em instantes.";
  }
  if (error?.code === "csrf_error") {
    return "Sua sessão expirou ou ficou inconsistente. Atualize e tente novamente.";
  }
  if (error?.status === 403 || error?.code === "forbidden") {
    return "Você não tem permissão para executar esta ação.";
  }
  if (error?.code === "invalid_json") {
    return "Resposta inesperada do servidor. Tente novamente e acione o suporte se persistir.";
  }
  const requestId = error?.requestId ? ` Código: ${error.requestId}` : "";
  return `${error?.message || "Falha inesperada."}${requestId}`;
}

export function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("Falha ao ler arquivo."));
    reader.readAsDataURL(file);
  });
}

export function feedbackMarkup(message, kind = "error") {
  if (!message) return "";
  const normalizedKind = normalizeFlashKind(kind);
  const role = normalizedKind === "error" || normalizedKind === "warning" ? "alert" : "status";
  const live = role === "alert" ? "assertive" : "polite";
  return `<div class="flash ${normalizedKind}" role="${role}" aria-live="${live}">${escapeHtml(message)}</div>`;
}

export function renderInlineFeedback(target, message, kind = "error") {
  if (!target) return;
  target.innerHTML = feedbackMarkup(message, kind);
}

export function countActiveFilters(filters = {}, defaults = {}) {
  return Object.entries(filters || {}).filter(([key, value]) => {
    if (key === "page") return false;
    const normalizedValue = String(value ?? "").trim();
    const normalizedDefault = String(defaults[key] ?? "").trim();
    return normalizedValue !== "" && normalizedValue !== normalizedDefault;
  }).length;
}

export function filterSummaryMarkup(filters = {}, labels = {}, defaults = {}) {
  const activeEntries = Object.entries(filters || {}).filter(([key, value]) => {
    if (key === "page") return false;
    const normalizedValue = String(value ?? "").trim();
    const normalizedDefault = String(defaults[key] ?? "").trim();
    return normalizedValue !== "" && normalizedValue !== normalizedDefault;
  });
  if (!activeEntries.length) {
    return '<div class="filters-state" data-filter-state="empty">Sem filtros ativos</div>';
  }
  return `
    <div class="filters-state" data-filter-state="active">
      <span>${activeEntries.length} filtro${activeEntries.length > 1 ? "s" : ""} ativo${activeEntries.length > 1 ? "s" : ""}</span>
      ${activeEntries
        .map(([key, value]) => `<span class="filters-state-chip">${escapeHtml(labels[key] || key)}: ${escapeHtml(value)}</span>`)
        .join("")}
    </div>
  `;
}

export function emptyTableRowMarkup(colspan, { title, detail = "", actionHref = "", actionLabel = "", type = "no-results" } = {}) {
  const action = actionHref && actionLabel
    ? `<a class="button-link secondary" href="${escapeAttr(actionHref)}">${escapeHtml(actionLabel)}</a>`
    : "";
  return `
    <tr class="operational-empty-row">
      <td colspan="${Number(colspan) || 1}" class="empty operational-empty" data-empty-type="${escapeAttr(type)}">
        <strong>${escapeHtml(title || "Nenhum registro encontrado.")}</strong>
        ${detail ? `<span>${escapeHtml(detail)}</span>` : ""}
        ${action}
      </td>
    </tr>
  `;
}

const CONTROL_LABELS = {
  nome: "Nome",
  busca: "Busca",
  status: "Status",
  base: "Base",
  funcao: "Funcao operacional",
  categoria: "Categoria",
  ativo: "Ativo/Inativo",
  tripulante: "Tripulante",
  tripulante_id: "Tripulante",
  equipamento: "Equipamento",
  equipamento_id: "Equipamento",
  tipo: "Tipo de treinamento",
  tipo_treinamento_id: "Tipo de treinamento",
  aeronave_modelo: "Modelo de aeronave",
  ordenacao: "Ordenacao",
  periodo: "Periodo",
  competencia: "Competencia",
  contratante: "Contratante",
  arquivo_pdf: "Arquivo PDF",
};

function readableControlKey(control) {
  return String(control.name || control.id || control.getAttribute("data-filter-key") || "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function derivedControlLabel(control) {
  const directKey = String(control.name || control.id || "").trim();
  if (CONTROL_LABELS[directKey]) return CONTROL_LABELS[directKey];
  if (control.id === "tripulantePhotoInput") return "Foto do tripulante";
  const placeholder = String(control.getAttribute("placeholder") || "").trim();
  if (placeholder) return placeholder;
  if (control.tagName === "SELECT") {
    const firstOption = Array.from(control.options || []).find((option) => String(option.textContent || "").trim());
    const firstLabel = String(firstOption?.textContent || "").trim();
    if (firstLabel && !/^selecione$/i.test(firstLabel)) return firstLabel;
  }
  const key = readableControlKey(control);
  return key ? key.charAt(0).toUpperCase() + key.slice(1) : "Campo";
}

function controlHasAccessibleName(control) {
  if (control.getAttribute("aria-label") || control.getAttribute("aria-labelledby")) return true;
  if (control.labels && control.labels.length > 0) return true;
  return false;
}

function enhanceFormControlLabels(scope) {
  scope.querySelectorAll("input:not([type='hidden']), select, textarea").forEach((control) => {
    if (controlHasAccessibleName(control)) return;
    control.setAttribute("aria-label", derivedControlLabel(control));
    control.dataset.a11yLabelGenerated = "true";
  });
}

function enhanceResponsiveTables(scope) {
  scope.querySelectorAll("table.data-table.responsive-cards").forEach((table, tableIndex) => {
    const tableKey = table.id || table.dataset.a11yTableId || `responsive-table-${tableIndex + 1}`;
    table.dataset.a11yTableId = tableKey;
    const headerCells = Array.from(table.querySelectorAll("thead th"));
    const headers = headerCells.map((header, headerIndex) => {
      if (!header.id) {
        header.id = `${tableKey}-header-${headerIndex + 1}`;
      }
      return {
        id: header.id,
        label: header.textContent.trim(),
      };
    });
    table.dataset.operationalSurface = "table-responsive";
    table.querySelectorAll("tbody tr").forEach((row) => {
      const cells = Array.from(row.children).filter((cell) => cell.tagName === "TD" || cell.tagName === "TH");
      const hasColspan = cells.some((cell) => Number(cell.getAttribute("colspan") || 1) > 1);
      if (hasColspan || row.classList.contains("operational-empty-row")) {
        row.dataset.responsiveRow = row.classList.contains("operational-empty-row") ? "empty" : "group";
        return;
      }
      row.dataset.responsiveRow = "record";
      cells.forEach((cell, index) => {
        const header = headers[index];
        if (!cell.hasAttribute("data-label") && header?.label) {
          cell.setAttribute("data-label", header.label);
          cell.dataset.labelGenerated = "true";
        }
        if (header?.id && !cell.hasAttribute("headers")) {
          cell.setAttribute("headers", header.id);
        }
        if (!cell.getAttribute("data-label")) {
          cell.dataset.labelMissing = "true";
        }
      });
    });
  });
}

export function enhanceOperationalSurfaces(root = document) {
  const scope = root?.querySelectorAll ? root : document;
  enhanceFormControlLabels(scope);
  enhanceResponsiveTables(scope);
}

export async function withActionBusy(button, busyLabel, action) {
  if (!button || button.dataset.busy === "1") return null;
  const idleLabel = button.textContent;
  button.dataset.busy = "1";
  button.setAttribute("aria-busy", "true");
  button.disabled = true;
  if (busyLabel) button.textContent = busyLabel;
  try {
    return await action();
  } finally {
    button.disabled = false;
    button.dataset.busy = "0";
    button.removeAttribute("aria-busy");
    if (busyLabel) button.textContent = idleLabel;
  }
}

export function confirmAction({ title, subject = "", consequence = "" }) {
  const message = [title, subject, consequence].filter(Boolean).join("\n\n");
  return window.confirm(message);
}

export function hashQuery() {
  return new URLSearchParams(window.location.hash.split("?")[1] || "");
}

export function routePath() {
  const hash = String(window.location.hash || "").trim();
  if (!hash) return "";
  return hash.split("?")[0] || "";
}

export function buildHashHref(path, params = null) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params || {})) {
    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (item !== "" && item !== null && item !== undefined) query.append(key, item);
      });
      continue;
    }
    if (value === "" || value === null || value === undefined) continue;
    query.set(key, String(value));
  }
  const queryString = query.toString();
  return queryString ? `${path}?${queryString}` : path;
}

export function capabilitySet() {
  return new Set(state.session?.capabilities?.granted_permissions || []);
}

export function hasCapability(permission) {
  return capabilitySet().has(permission);
}

export function digitsOnly(value) {
  return String(value || "").replace(/\D/g, "");
}

export function initialsForName(value) {
  const parts = String(value || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

export function formatDateBr(value) {
  const raw = String(value || "").trim();
  if (!raw) return "-";
  const match = raw.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (match) return `${match[3]}/${match[2]}/${match[1]}`;
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return raw;
  return parsed.toLocaleDateString("pt-BR");
}

export function formatDateTimeBr(value) {
  const raw = String(value || "").trim();
  if (!raw) return "-";
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return raw;
  return parsed.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatCurrencyBr(value) {
  const amount = Number(value || 0);
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(Number.isFinite(amount) ? amount : 0);
}

export function formatFileSize(value) {
  const bytes = Number(value || 0);
  if (!Number.isFinite(bytes) || bytes <= 0) return "Tamanho não informado";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let amount = bytes / 1024;
  let unitIndex = 0;
  while (amount >= 1024 && unitIndex < units.length - 1) {
    amount /= 1024;
    unitIndex += 1;
  }
  return `${amount.toLocaleString("pt-BR", { maximumFractionDigits: amount >= 10 ? 1 : 2 })} ${units[unitIndex]}`;
}

export function formatCompetenciaLabel(value) {
  const raw = String(value || "").trim();
  const match = raw.match(/^(\d{4})-(\d{2})$/);
  if (!match) return raw || "-";
  const monthIndex = Number(match[2]) - 1;
  return `${MONTH_LABELS[monthIndex] || match[2]}/${match[1]}`;
}

export function normalizeTextKey(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

export function trainingStatusClass(value) {
  const normalized = normalizeTextKey(value);
  if (normalized === "vencido") return "status-red";
  if (normalized === "a vencer") return "status-yellow";
  if (normalized === "regular" || normalized === "em dia") return "status-green";
  if (normalized === "critico 15") return "status-red";
  if (normalized === "vencer 30" || normalized === "vencer 60" || normalized === "vencer 90") return "status-yellow";
  return "status-gray";
}

export function tripulanteStatusClass(value) {
  const normalized = normalizeTextKey(value);
  if (normalized === "ativo") return "status-green";
  if (normalized === "folga") return "status-yellow";
  if (normalized === "ferias") return "status-blue";
  if (normalized === "atestado") return "status-red";
  if (normalized === "afastado") return "status-dark";
  if (normalized === "treinamento") return "status-purple";
  return "status-gray";
}

export function booleanLabel(value) {
  return value ? "Sim" : "Não";
}

export function whatsappUrl(value) {
  const digits = digitsOnly(value);
  if (!digits) return "";
  const normalized = digits.startsWith("55") ? digits : `55${digits}`;
  return `https://wa.me/${normalized}`;
}
