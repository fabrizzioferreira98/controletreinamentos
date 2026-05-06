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
};

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

export async function api(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});
  if (!headers.has("Accept")) headers.set("Accept", "application/json");
  if (options.json) headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD"].includes(method) && state.csrfToken && !headers.has("X-CSRFToken")) {
    headers.set("X-CSRFToken", state.csrfToken);
  }

  const response = await fetch(`${config.apiBaseUrl}${path}`, {
    method,
    headers,
    body: options.json ? JSON.stringify(options.json) : options.body,
    credentials: "include",
  });

  const requestId = response.headers.get("X-Request-ID") || "";
  const contentType = response.headers.get("Content-Type") || "";

  if (!response.ok && contentType.includes("application/json")) {
    const payload = await response.json();
    const error = new Error(payload.message || `Falha HTTP ${response.status}`);
    error.status = response.status;
    error.code = payload.code;
    error.requestId = payload.request_id || requestId;
    throw error;
  }

  if (!response.ok) {
    const error = new Error(`Falha HTTP ${response.status}`);
    error.status = response.status;
    error.requestId = requestId;
    throw error;
  }

  if (contentType.includes("application/json")) {
    return { response, data: await response.json(), requestId };
  }

  return { response, data: await response.blob(), requestId };
}

export async function refreshSession() {
  const { data } = await api("/api/v1/session");
  state.session = data;
  state.csrfToken = data.csrf_token || "";
  return data;
}

export function showFlash(message, kind = "error") {
  state.flash = { message, kind };
}

export function consumeFlash() {
  const flash = state.flash;
  state.flash = null;
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
