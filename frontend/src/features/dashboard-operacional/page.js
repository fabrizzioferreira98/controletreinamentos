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
import { STATIC_ASSETS } from "../../compat/static-assets.js";
import { DASHBOARD_LOWER_SECTION_EMPTY, DASHBOARD_OPERATIONAL_QUICK_ACTIONS } from "./lower-section-data.js";
import { DASHBOARD_EMPTY_BASE_OPERATIONS, DASHBOARD_UPPER_SECTION_EMPTY } from "./upper-section-data.js";

const DASHBOARD_WEATHER_ROTATION_BASES = ["SBGO", "SBSP", "SBPJ", "SBSV", "SBEG", "SBBE", "SBSN"];
const DASHBOARD_WEATHER_ROTATION_INTERVAL_MS = 12000;
const DASHBOARD_WEATHER_ANIMATION_MS = 220;
const DASHBOARD_REALTIME_CLOCK_INTERVAL_MS = 1000;
const DASHBOARD_BASES_MAP_ENDPOINT = "/api/v1/dashboard/base-operations";
const DASHBOARD_WEATHER_BY_BASE_ENDPOINT = "/api/v1/dashboard/weather-by-base";
const DASHBOARD_RELEVANT_NOTAMS_ENDPOINT = "/api/v1/dashboard/notams";
const DASHBOARD_OPERATIONAL_ALERTS_ENDPOINT = "/api/v1/dashboard/operational-alerts";
const DASHBOARD_LEAFLET_CSS_HREF = STATIC_ASSETS.leafletCss;
const DASHBOARD_LEAFLET_SCRIPT_SRC = STATIC_ASSETS.leafletScript;
const DASHBOARD_BASES_MAP_CENTER = Object.freeze([-14.235, -51.925]);
const DASHBOARD_BASES_MAP_INITIAL_ZOOM = 4;
const DASHBOARD_BASES_MAP_FOCUS_ZOOM = 5;
const DASHBOARD_BASES_MAP_ROTATION_INTERVAL_MS = 5200;
const DASHBOARD_BASE_ICAO_BY_LOCATION = Object.freeze({
  goiania: "SBGO",
  "sao paulo": "SBSP",
  palmas: "SBPJ",
  salvador: "SBSV",
  manaus: "SBEG",
  belem: "SBBE",
  santarem: "SBSN",
});
const DASHBOARD_WEATHER_LOCATION_LABELS = {
  SBGO: "Goi\u00e2nia",
  SBSP: "S\u00e3o Paulo",
  SBPJ: "Palmas",
  SBSV: "Salvador",
  SBEG: "Manaus",
  SBBE: "Bel\u00e9m",
  SBSN: "Santar\u00e9m",
};
const DASHBOARD_UPPER_SECTION_CARD_STATES = Object.freeze(["success", "loading", "empty", "error"]);
const DASHBOARD_UPPER_SEVERITY_LABELS = Object.freeze({
  critical: "Cr\u00edtico",
  warning: "Aten\u00e7\u00e3o",
  planning: "Planejamento",
  normal: "Normal",
});
const DASHBOARD_UPPER_SEVERITY_ORDER = Object.freeze({
  critical: 0,
  warning: 1,
  planning: 2,
  normal: 3,
});
const DASHBOARD_RELEVANT_NOTAMS_EMPTY = Object.freeze({
  status: "empty",
  source: "",
  message: "",
  items: Object.freeze([]),
});
const DASHBOARD_WEATHER_BY_BASE_EMPTY = Object.freeze({
  status: "empty",
  source: "AISWEB",
  message: "",
  items: Object.freeze([]),
});
const DASHBOARD_OPERATIONAL_ALERTS_EMPTY = Object.freeze({
  status: "empty",
  source: "",
  message: "Sem alertas operacionais no momento.",
  items: Object.freeze([]),
});

let dashboardSummarySnapshot = {};
let dashboardWeatherSnapshot = dashboardWeatherFallback("unavailable");
let dashboardWeatherBaseIndex = 0;
let dashboardWeatherRotationTimer = null;
let dashboardWeatherRequestSequence = 0;
let dashboardRealtimeClockTimer = null;
let dashboardFullscreenChangeListenerBound = false;
let dashboardBaseMapState = null;
let dashboardBaseMapRotationTimer = null;
let dashboardBaseMapRequestSequence = 0;
let dashboardLeafletLoadPromise = null;

function normalizeDashboardWeatherIcaoCode(value) {
  const normalized = String(value || "").trim().toUpperCase();
  return DASHBOARD_WEATHER_ROTATION_BASES.includes(normalized) ? normalized : DASHBOARD_WEATHER_ROTATION_BASES[0];
}

function dashboardWeatherLocationLabel(icaoCode) {
  const normalized = normalizeDashboardWeatherIcaoCode(icaoCode);
  return DASHBOARD_WEATHER_LOCATION_LABELS[normalized] || normalized;
}

function dashboardWeatherEndpoint(icaoCode) {
  return `/api/aisweb/met?icaoCode=${encodeURIComponent(normalizeDashboardWeatherIcaoCode(icaoCode))}`;
}

function dashboardWeatherFallback(status = "unavailable", icaoCode = DASHBOARD_WEATHER_ROTATION_BASES[0]) {
  const isLoading = status === "loading";
  const normalizedIcaoCode = normalizeDashboardWeatherIcaoCode(icaoCode);
  return {
    icaoCode: normalizedIcaoCode,
    locationLabel: dashboardWeatherLocationLabel(normalizedIcaoCode),
    temperatureC: null,
    windDirection: null,
    windSpeedKt: null,
    condition: "UNKNOWN",
    rawMetar: null,
    rawTaf: null,
    observedAt: null,
    updatedAtLabel: isLoading ? "Carregando meteorologia..." : "Dados n\u00e3o atualizados",
    source: "AISWEB",
    status,
  };
}

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

function resolveDashboardUserMeta() {
  const user = state.session?.user || {};
  const name = String(user.nome || user.login || "Usu\u00e1rio").trim();
  const role = String(user.perfil || "").trim();
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase() || "U";
  return { initials, name, role };
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

function formatDashboardDateTime(now = new Date()) {
  try {
    return new Intl.DateTimeFormat("pt-BR", {
      dateStyle: "short",
      timeStyle: "short",
    }).format(now);
  } catch (_error) {
    return now.toLocaleString();
  }
}

function formatDashboardDateLabel(now = new Date()) {
  try {
    return new Intl.DateTimeFormat("pt-BR").format(now);
  } catch (_error) {
    return now.toLocaleDateString();
  }
}

function formatDashboardTimeLabel(now = new Date()) {
  try {
    return new Intl.DateTimeFormat("pt-BR", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).format(now);
  } catch (_error) {
    return now.toLocaleTimeString();
  }
}

function dashboardTopIconMarkup(icon) {
  const icons = {
    calendar: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M7 3v3M17 3v3M4.8 9.2h14.4M6.2 5.2h11.6a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H6.2a2 2 0 0 1-2-2v-11a2 2 0 0 1 2-2Z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    clock: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-13v5l3 2" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    refresh: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M20 6v5h-5M4 18v-5h5M18.2 10.2A6.8 6.8 0 0 0 6.7 7.7L4 10.3m16 3.4-2.7 2.6a6.8 6.8 0 0 1-11.5-2.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    pulse: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M3 12h4l2-6 4 12 2-6h6" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    fullscreen: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M9 4H4v5M15 4h5v5M4 15v5h5M20 15v5h-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    fullscreenExit: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    map: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 21s6-5.1 6-11A6 6 0 0 0 6 10c0 5.9 6 11 6 11Zm0-8.3a2.7 2.7 0 1 0 0-5.4 2.7 2.7 0 0 0 0 5.4Z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    weather: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M8.6 18.3h8.2a4.2 4.2 0 0 0 .5-8.4 6.2 6.2 0 0 0-11.8 2.2 3.2 3.2 0 0 0 3.1 6.2Z" fill="currentColor"/><path d="M16.8 3.8v1.7M20.4 7.4h-1.7M18.9 5.3l-1.2 1.2" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
    alert: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 4.2 21 20H3L12 4.2Z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M12 9.5v4.6m0 3h.01" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
    timer: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M9 2h6M12 6a8 8 0 1 0 0 16 8 8 0 0 0 0-16Zm0 4v4l2.5 2.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    month: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M7 3v3M17 3v3M5 8h14M6.5 5h11A2.5 2.5 0 0 1 20 7.5v10A2.5 2.5 0 0 1 17.5 20h-11A2.5 2.5 0 0 1 4 17.5v-10A2.5 2.5 0 0 1 6.5 5Zm3 7h1m3 0h1m-5 4h1m3 0h1" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    info: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-8v5m0-9h.01" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    users: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M16 20v-1.5a3.5 3.5 0 0 0-3.5-3.5h-5A3.5 3.5 0 0 0 4 18.5V20M10 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm10 9v-1.3a3.1 3.1 0 0 0-2.3-3M15.5 3.4a3.7 3.7 0 0 1 0 7.2" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    bell: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9Zm-4.3 12a2 2 0 0 1-3.4 0" fill="currentColor"/></svg>',
    chevronRight: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="m9 18 6-6-6-6" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    plane: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="m3.7 18.8 16.5-7.1a1.4 1.4 0 0 0-.1-2.6L3.7 3.9l3.1 6.9 7.1.1-7.1 1.9-3.1 6Z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    download: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 4v10m0 0 4-4m-4 4-4-4M5 17.5V20h14v-2.5" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "calendar-days": '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M7 3v3M17 3v3M5 8.2h14M6.5 5h11A2.5 2.5 0 0 1 20 7.5v10A2.5 2.5 0 0 1 17.5 20h-11A2.5 2.5 0 0 1 4 17.5v-10A2.5 2.5 0 0 1 6.5 5Zm2.2 7.2h.1m3.2 0h.1m3.2 0h.1m-6.5 3.6h.1m3.2 0h.1m3.2 0h.1" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "alert-triangle": '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 4.2 21 20H3L12 4.2Z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M12 9.5v4.6m0 3h.01" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
  };
  return icons[icon] || "";
}

function dashboardWeatherStatusLabel(status) {
  const labels = {
    available: "Dispon\u00edvel",
    stale: "Dados n\u00e3o atualizados",
    unavailable: "Indispon\u00edvel",
    error: "Indispon\u00edvel",
    loading: "Atualizando",
  };
  return labels[status] || labels.unavailable;
}

function dashboardWeatherValueMarkup(weather) {
  if (weather.status === "loading") return "Carregando meteorologia...";
  if (!["available", "stale"].includes(weather.status)) return "Meteorologia indispon&iacute;vel";

  const parts = [];
  if (Number.isFinite(Number(weather.temperatureC))) {
    parts.push(`${Number(weather.temperatureC)}&deg;C`);
  }
  if (Number.isFinite(Number(weather.windSpeedKt))) {
    parts.push(`Vento ${Number(weather.windSpeedKt)} kt`);
  }
  return parts.length ? parts.join(" &middot; ") : "Meteorologia indispon&iacute;vel";
}

function renderDashboardHeader(options = {}) {
  const weather = options.dashboardWeather || dashboardWeatherFallback("unavailable");
  const userMeta = resolveDashboardUserMeta();
  const now = new Date();
  // Shared header contract: priority-page-header ui-page-header ui-surface.
  return `
    <div class="page-header priority-page-header dashboard-page-header ui-page-header ui-surface">
      <div class="dashboard-header-main">
        <h1>Dashboard Operacional</h1>
        <p class="page-subtitle">Vis&atilde;o geral das opera&ccedil;&otilde;es, vencimentos e condi&ccedil;&otilde;es atuais.</p>
      </div>
      <aside class="dashboard-header-actions dashboard-top-statusbar" data-dashboard-compatible="dashboard-action-rail" aria-label="Estado atual da dashboard">
        <div class="dashboard-header-meta-item">
          <span class="dashboard-meta-icon">${dashboardTopIconMarkup("calendar")}</span>
          <span><strong data-dashboard-date-label>${escapeHtml(formatDashboardDateLabel(now))}</strong><small>Data</small></span>
        </div>
        <div class="dashboard-header-meta-item">
          <span class="dashboard-meta-icon">${dashboardTopIconMarkup("clock")}</span>
          <span><strong data-dashboard-time-label>${escapeHtml(formatDashboardTimeLabel(now))}</strong><small>Hora</small></span>
        </div>
        <div class="dashboard-header-update">
          <span class="dashboard-meta-icon">${dashboardTopIconMarkup("refresh")}</span>
          <span class="dashboard-update-dot"></span>
          <span data-dashboard-weather-updated-label>${escapeHtml(weather.updatedAtLabel || "Dados n\u00e3o atualizados")}</span>
        </div>
        <button type="button" class="dashboard-fullscreen-button" data-dashboard-fullscreen-action aria-pressed="false" title="Ativar tela cheia">
          <span class="dashboard-meta-icon" data-dashboard-fullscreen-icon>${dashboardTopIconMarkup("fullscreen")}</span>
          <span><strong data-dashboard-fullscreen-label>Tela cheia</strong><small>TV</small></span>
        </button>
        <div class="dashboard-system-badge dashboard-system-badge--available">
          <span>${dashboardTopIconMarkup("pulse")}</span>
          <strong>Sistema<br>Operacional</strong>
        </div>
        <div class="dashboard-user-summary">
          <span class="dashboard-user-avatar">${escapeHtml(userMeta.initials)}</span>
          <span><strong>${escapeHtml(userMeta.name)}</strong>${userMeta.role ? `<small>${escapeHtml(userMeta.role)}</small>` : ""}</span>
        </div>
      </aside>
    </div>
  `;
}

function updateDashboardRealtimeClock(now = new Date()) {
  const dateLabel = document.querySelector("[data-dashboard-date-label]");
  const timeLabel = document.querySelector("[data-dashboard-time-label]");
  if (dateLabel) dateLabel.textContent = formatDashboardDateLabel(now);
  if (timeLabel) timeLabel.textContent = formatDashboardTimeLabel(now);
}

function stopDashboardRealtimeClock() {
  if (dashboardRealtimeClockTimer) {
    window.clearInterval(dashboardRealtimeClockTimer);
  }
  dashboardRealtimeClockTimer = null;
}

function startDashboardRealtimeClock() {
  stopDashboardRealtimeClock();
  updateDashboardRealtimeClock();
  dashboardRealtimeClockTimer = window.setInterval(() => {
    if (!document.querySelector(".dashboard-operational-page-shell")) {
      stopDashboardRealtimeClock();
      return;
    }
    updateDashboardRealtimeClock();
  }, DASHBOARD_REALTIME_CLOCK_INTERVAL_MS);
}

function dashboardFullscreenElement() {
  return document.fullscreenElement || document.webkitFullscreenElement || null;
}

function dashboardFullscreenTarget() {
  return document.querySelector(".dashboard-operational-page-shell") || document.documentElement;
}

function dashboardFullscreenSupported(target = dashboardFullscreenTarget()) {
  return Boolean(
    document.fullscreenEnabled ||
      document.webkitFullscreenEnabled ||
      target.requestFullscreen ||
      target.webkitRequestFullscreen,
  );
}

function updateDashboardFullscreenButton() {
  const button = document.querySelector("[data-dashboard-fullscreen-action]");
  if (!button) return;
  const isFullscreen = Boolean(dashboardFullscreenElement());
  const supported = dashboardFullscreenSupported();
  const label = button.querySelector("[data-dashboard-fullscreen-label]");
  const icon = button.querySelector("[data-dashboard-fullscreen-icon]");
  button.disabled = !supported;
  button.setAttribute("aria-pressed", isFullscreen ? "true" : "false");
  button.title = isFullscreen ? "Sair da tela cheia" : "Ativar tela cheia";
  button.setAttribute("aria-label", button.title);
  if (label) label.textContent = isFullscreen ? "Sair" : "Tela cheia";
  if (icon) icon.innerHTML = dashboardTopIconMarkup(isFullscreen ? "fullscreenExit" : "fullscreen");
}

async function toggleDashboardFullscreen() {
  const target = dashboardFullscreenTarget();
  if (!dashboardFullscreenSupported(target)) {
    showFlash("Tela cheia n\u00e3o est\u00e1 dispon\u00edvel neste navegador.", "warning");
    return;
  }

  try {
    if (dashboardFullscreenElement()) {
      const exitFullscreen = document.exitFullscreen || document.webkitExitFullscreen;
      await exitFullscreen.call(document);
    } else {
      const requestFullscreen = target.requestFullscreen || target.webkitRequestFullscreen;
      await requestFullscreen.call(target);
    }
    updateDashboardFullscreenButton();
  } catch (error) {
    showFlash(buildErrorMessage(error), "error");
  }
}

function wireDashboardFullscreenControl() {
  const button = document.querySelector("[data-dashboard-fullscreen-action]");
  if (!button) return;
  button.addEventListener("click", () => void toggleDashboardFullscreen());
  if (!dashboardFullscreenChangeListenerBound) {
    document.addEventListener("fullscreenchange", updateDashboardFullscreenButton);
    document.addEventListener("webkitfullscreenchange", updateDashboardFullscreenButton);
    dashboardFullscreenChangeListenerBound = true;
  }
  updateDashboardFullscreenButton();
}

function renderDashboardWeatherStripContent(weatherInput) {
  const weather = weatherInput || dashboardWeatherFallback("unavailable");
  const weatherStatus = weather.status || "unavailable";
  const normalizedIcaoCode = normalizeDashboardWeatherIcaoCode(weather.icaoCode);
  const locationLabel = String(weather.locationLabel || dashboardWeatherLocationLabel(normalizedIcaoCode)).trim() || dashboardWeatherLocationLabel(normalizedIcaoCode);
  const baseLabel = `${normalizedIcaoCode} - ${locationLabel}`;
  const metarTitle = weather.rawMetar ? `METAR: ${weather.rawMetar}` : "";
  return `
    <div class="dashboard-weather-item dashboard-weather-item--base">
      <span class="dashboard-weather-icon dashboard-weather-icon--map">${dashboardTopIconMarkup("map")}</span>
      <span class="dashboard-weather-copy">
        <span class="dashboard-weather-label">Base Principal</span>
        <strong>${escapeHtml(baseLabel)}</strong>
      </span>
    </div>
    <div class="dashboard-weather-item dashboard-weather-item--conditions" title="${escapeAttr(metarTitle)}" aria-live="polite">
      <span class="dashboard-weather-icon dashboard-weather-icon--weather">${dashboardTopIconMarkup("weather")}</span>
      <span class="dashboard-weather-copy">
        <span class="dashboard-weather-label">Condi&ccedil;&otilde;es</span>
        <strong>${dashboardWeatherValueMarkup(weather)}</strong>
        <small>${escapeHtml(weather.source || "AISWEB")} &middot; ${escapeHtml(dashboardWeatherStatusLabel(weatherStatus))}</small>
      </span>
    </div>
  `;
}

function renderDashboardPriorityStrip() {
  const weather = dashboardWeatherSnapshot || dashboardWeatherFallback("unavailable");
  return `
    <section class="dashboard-priority-strip ui-surface dashboard-above-fold" data-dashboard-priority="p0" data-dashboard-weather-surface="dashboard-operational-weather-strip" data-dashboard-compatible="dashboard-priority-step" data-weather-icao="${escapeAttr(normalizeDashboardWeatherIcaoCode(weather.icaoCode))}" data-weather-status="${escapeAttr(weather.status || "unavailable")}" aria-label="Base principal e condi&ccedil;&otilde;es atuais">
      ${renderDashboardWeatherStripContent(weather)}
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

function adaptDashboardBaseOperations(payload) {
  return normalizeDashboardBaseOperationsPayload(payload);
}

function buildDashboardLicenseSummary(summaryData = {}) {
  const summary = summaryData.summary && typeof summaryData.summary === "object" ? summaryData.summary : {};
  const alerts = summaryData.alerts && typeof summaryData.alerts === "object" ? summaryData.alerts : {};
  return {
    total: asDashboardNumber(summary.total),
    expired: asDashboardNumber(summary.vencido),
    dueToday: asDashboardNumber(alerts.vencem_hoje),
    dueIn7Days: asDashboardNumber(alerts.em_7_dias),
    dueIn30Days: asDashboardNumber(alerts.em_30_dias),
    valid: asDashboardNumber(summary.regular),
  };
}

function dashboardCriticalTrainingSeverity(status) {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "vencido") return "critical";
  if (normalized === "a vencer") return "warning";
  if (normalized === "sem informa\u00e7\u00e3o" || normalized === "sem informacao") return "planning";
  return "normal";
}

function buildDashboardCriticalQualifications(itemsInput = []) {
  const grouped = new Map();
  const severityRank = { critical: 0, warning: 1, planning: 2, normal: 3 };
  (Array.isArray(itemsInput) ? itemsInput : []).forEach((item) => {
    const severity = dashboardCriticalTrainingSeverity(item.status);
    if (severity === "normal") return;
    const label = String(item.tipo_treinamento_nome || "Habilita\u00e7\u00e3o sem tipo").trim();
    const current = grouped.get(label) || {
      label,
      affected: 0,
      expired: 0,
      dueSoon: 0,
      missingInfo: 0,
      severity,
    };
    current.affected += 1;
    if (severity === "critical") current.expired += 1;
    if (severity === "warning") current.dueSoon += 1;
    if (severity === "planning") current.missingInfo += 1;
    if (severityRank[severity] < severityRank[current.severity]) {
      current.severity = severity;
    }
    grouped.set(label, current);
  });
  return [...grouped.values()].map((item) => {
    const parts = [
      item.expired ? `${item.expired} vencido(s)` : "",
      item.dueSoon ? `${item.dueSoon} a vencer` : "",
      item.missingInfo ? `${item.missingInfo} sem informa\u00e7\u00e3o` : "",
    ].filter(Boolean);
    return {
      label: item.label,
      affected: item.affected,
      severity: item.severity,
      helper: parts.join(" \u00b7 ") || "Sem detalhe adicional",
    };
  });
}

function buildDashboardUpperRuntimeData({ summaryData = {}, baseOperations = DASHBOARD_EMPTY_BASE_OPERATIONS, criticalTrainings = [] } = {}) {
  return {
    licenseSummary: buildDashboardLicenseSummary(summaryData),
    baseOperations,
    criticalQualifications: buildDashboardCriticalQualifications(criticalTrainings),
  };
}

function dashboardWeatherVisibilityKm(weather) {
  const meters = Number(weather?.visibilityMeters);
  if (Number.isFinite(meters)) return Math.round((meters / 1000) * 10) / 10;
  const km = Number(weather?.visibilityKm);
  return Number.isFinite(km) ? km : null;
}

function dashboardWeatherRowSeverity(status) {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "available") return "normal";
  if (normalized === "stale") return "attention";
  if (normalized === "error") return "critical";
  return "unknown";
}

function dashboardWeatherToBaseWeatherRow(weather) {
  if (!weather || typeof weather !== "object") return null;
  const status = String(weather.status || "error").trim().toLowerCase();
  const isAvailable = ["available", "stale"].includes(status);
  const icao = normalizeDashboardWeatherIcaoCode(weather.icaoCode);
  return {
    icao,
    city: String(weather.locationLabel || dashboardWeatherLocationLabel(icao)).trim(),
    condition: isAvailable ? String(weather.condition || "UNKNOWN").trim().toUpperCase() || "UNKNOWN" : "INDISP.",
    temperatureC: isAvailable && Number.isFinite(Number(weather.temperatureC)) ? Number(weather.temperatureC) : null,
    windKt: isAvailable && Number.isFinite(Number(weather.windSpeedKt)) ? Number(weather.windSpeedKt) : null,
    coverage: null,
    visibilityKm: isAvailable ? dashboardWeatherVisibilityKm(weather) : null,
    severity: dashboardWeatherRowSeverity(status),
    status,
  };
}

function adaptDashboardWeatherByBase(payload) {
  const collection = assertObject(payload?.weather_by_base, "dashboard.weather_by_base");
  const items = assertArray(collection.items, "weather_by_base.items")
    .map((item) => dashboardWeatherToBaseWeatherRow(item))
    .filter(Boolean);
  return {
    status: String(collection.status || "error").trim().toLowerCase(),
    source: String(collection.source || "AISWEB").trim(),
    message: String(collection.message || "").trim(),
    updatedAtLabel: String(collection.updatedAtLabel || "").trim(),
    items,
  };
}

function adaptDashboardRelevantNotams(payload) {
  const collection = assertObject(payload?.notams, "dashboard.notams");
  const items = assertArray(collection.items, "notams.items").map((item) => {
    const source = assertObject(item, "notams.item");
    const severity = dashboardNotamSeverity(source.severity);
    return {
      id: String(source.id || source.notamId || `${source.icao || "notam"}-${source.updatedAt || ""}`).trim(),
      code: String(source.code || severity.slice(0, 1)).trim().toUpperCase(),
      icao: String(source.icao || source.icaoCode || "----").trim().toUpperCase(),
      description: String(source.description || source.message || "").trim(),
      updatedAt: String(source.updatedAtLabel || source.updatedAt || "--").trim(),
      validUntil: String(source.validUntilLabel || source.validUntil || "Validade indispon\u00edvel").trim(),
      severity,
    };
  });
  return {
    status: String(collection.status || (items.length ? "available" : "empty")).trim().toLowerCase(),
    source: String(collection.source || "").trim(),
    message: String(collection.message || "").trim(),
    updatedAtLabel: String(collection.updatedAtLabel || "").trim(),
    items,
  };
}

function adaptDashboardOperationalAlerts(payload) {
  const collection = assertObject(payload?.operational_alerts, "dashboard.operational_alerts");
  const items = assertArray(collection.items, "operational_alerts.items").map((item) => {
    const source = assertObject(item, "operational_alerts.item");
    return {
      id: String(source.id || source.label || source.message || "operational-alert").trim(),
      severity: dashboardNotamSeverity(source.severity),
      label: String(source.label || "Operacional").trim(),
      message: String(source.message || "").trim(),
      source: String(source.source || "").trim(),
    };
  }).filter((item) => item.message);
  return {
    status: String(collection.status || (items.length ? "available" : "empty")).trim().toLowerCase(),
    source: String(collection.source || "").trim(),
    message: String(collection.message || "").trim(),
    updatedAtLabel: String(collection.updatedAtLabel || "").trim(),
    items,
  };
}

function buildDashboardLowerRuntimeData({ weatherByBase = DASHBOARD_WEATHER_BY_BASE_EMPTY, relevantNotams = DASHBOARD_RELEVANT_NOTAMS_EMPTY } = {}) {
  const weatherByBaseCollection = weatherByBase && typeof weatherByBase === "object" ? weatherByBase : DASHBOARD_WEATHER_BY_BASE_EMPTY;
  const relevantNotamsCollection = relevantNotams && typeof relevantNotams === "object" ? relevantNotams : DASHBOARD_RELEVANT_NOTAMS_EMPTY;
  return {
    ...DASHBOARD_LOWER_SECTION_EMPTY,
    weatherByBase: Array.isArray(weatherByBaseCollection.items) ? weatherByBaseCollection.items : [],
    weatherByBaseMeta: {
      status: String(weatherByBaseCollection.status || "error").trim().toLowerCase(),
      source: String(weatherByBaseCollection.source || "AISWEB").trim(),
      message: String(weatherByBaseCollection.message || "").trim(),
      updatedAtLabel: String(weatherByBaseCollection.updatedAtLabel || "").trim(),
    },
    relevantNotams: Array.isArray(relevantNotamsCollection.items) ? relevantNotamsCollection.items : [],
    relevantNotamsMeta: {
      status: String(relevantNotamsCollection.status || "error").trim().toLowerCase(),
      source: String(relevantNotamsCollection.source || "").trim(),
      message: String(relevantNotamsCollection.message || "").trim(),
      updatedAtLabel: String(relevantNotamsCollection.updatedAtLabel || "").trim(),
    },
    quickActions: DASHBOARD_OPERATIONAL_QUICK_ACTIONS,
  };
}

function dashboardCardStateFromBlock(block, isEmpty = false) {
  if (block?.error) return "error";
  return isEmpty ? "empty" : "success";
}

function dashboardOperationalCollectionCardState(block, collection, isEmpty = false) {
  if (block?.error) return "error";
  const status = String(collection?.status || "").trim().toLowerCase();
  if (["error", "unavailable"].includes(status)) return "error";
  return isEmpty || status === "empty" ? "empty" : "success";
}

function adaptDashboardWeather(payload, fallbackIcaoCode = DASHBOARD_WEATHER_ROTATION_BASES[0]) {
  const weather = assertObject(payload?.weather, "dashboard.weather");
  const statusValues = new Set(["available", "stale", "unavailable", "error"]);
  const status = statusValues.has(weather.status) ? weather.status : "error";
  const icaoCode = normalizeDashboardWeatherIcaoCode(weather.icaoCode || fallbackIcaoCode);
  const locationLabel = String(weather.locationLabel || dashboardWeatherLocationLabel(icaoCode)).trim() || dashboardWeatherLocationLabel(icaoCode);
  return {
    ...dashboardWeatherFallback(status, icaoCode),
    ...weather,
    icaoCode,
    locationLabel,
    source: "AISWEB",
    status,
  };
}

function updateDashboardWeatherDom(weather, { animate = false } = {}) {
  const strip = document.querySelector('[data-dashboard-weather-surface="dashboard-operational-weather-strip"]');
  const updatedLabel = document.querySelector("[data-dashboard-weather-updated-label]");
  if (updatedLabel) {
    updatedLabel.textContent = weather.updatedAtLabel || "Dados n\u00e3o atualizados";
  }
  if (!strip) return false;

  const applyContent = () => {
    strip.innerHTML = renderDashboardWeatherStripContent(weather);
    strip.dataset.weatherIcao = normalizeDashboardWeatherIcaoCode(weather.icaoCode);
    strip.dataset.weatherStatus = weather.status || "unavailable";
  };

  const prefersReducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
  if (!animate || prefersReducedMotion) {
    applyContent();
    return true;
  }

  strip.classList.add("is-weather-transitioning");
  window.setTimeout(() => {
    applyContent();
    strip.classList.remove("is-weather-transitioning");
    strip.classList.add("is-weather-transitioned");
    window.setTimeout(() => strip.classList.remove("is-weather-transitioned"), DASHBOARD_WEATHER_ANIMATION_MS);
  }, DASHBOARD_WEATHER_ANIMATION_MS);
  return true;
}

async function fetchDashboardWeatherForBase(icaoCode, { animate = true } = {}) {
  const normalizedIcaoCode = normalizeDashboardWeatherIcaoCode(icaoCode);
  const requestSequence = ++dashboardWeatherRequestSequence;
  const loadingWeather = dashboardWeatherFallback("loading", normalizedIcaoCode);
  dashboardWeatherSnapshot = loadingWeather;
  updateDashboardWeatherDom(loadingWeather, { animate });
  try {
    const result = await api(dashboardWeatherEndpoint(normalizedIcaoCode));
    if (requestSequence !== dashboardWeatherRequestSequence) return;
    const weather = adaptDashboardWeather(result.data, normalizedIcaoCode);
    dashboardWeatherSnapshot = weather;
    updateDashboardWeatherDom(weather, { animate });
  } catch (_error) {
    if (requestSequence !== dashboardWeatherRequestSequence) return;
    const fallbackWeather = dashboardWeatherFallback("error", normalizedIcaoCode);
    dashboardWeatherSnapshot = fallbackWeather;
    updateDashboardWeatherDom(fallbackWeather, { animate });
  }
}

function stopDashboardWeatherRotation() {
  if (dashboardWeatherRotationTimer) {
    window.clearInterval(dashboardWeatherRotationTimer);
  }
  dashboardWeatherRotationTimer = null;
  dashboardWeatherRequestSequence += 1;
}

function startDashboardWeatherRotation() {
  stopDashboardWeatherRotation();
  if (DASHBOARD_WEATHER_ROTATION_BASES.length < 2) return;
  dashboardWeatherBaseIndex = Math.max(
    0,
    DASHBOARD_WEATHER_ROTATION_BASES.indexOf(normalizeDashboardWeatherIcaoCode(dashboardWeatherSnapshot.icaoCode)),
  );
  dashboardWeatherRotationTimer = window.setInterval(() => {
    const strip = document.querySelector('[data-dashboard-weather-surface="dashboard-operational-weather-strip"]');
    if (!strip) {
      stopDashboardWeatherRotation();
      return;
    }
    dashboardWeatherBaseIndex = (dashboardWeatherBaseIndex + 1) % DASHBOARD_WEATHER_ROTATION_BASES.length;
    fetchDashboardWeatherForBase(DASHBOARD_WEATHER_ROTATION_BASES[dashboardWeatherBaseIndex], { animate: true });
  }, DASHBOARD_WEATHER_ROTATION_INTERVAL_MS);
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

function normalizeDashboardUpperCardState(value) {
  const normalized = String(value || "success").trim().toLowerCase();
  return DASHBOARD_UPPER_SECTION_CARD_STATES.includes(normalized) ? normalized : "success";
}

function dashboardUpperSeverity(value) {
  const normalized = String(value || "normal").trim().toLowerCase();
  return Object.prototype.hasOwnProperty.call(DASHBOARD_UPPER_SEVERITY_LABELS, normalized) ? normalized : "normal";
}

function dashboardUpperSeverityLabel(severity) {
  return DASHBOARD_UPPER_SEVERITY_LABELS[dashboardUpperSeverity(severity)] || DASHBOARD_UPPER_SEVERITY_LABELS.normal;
}

function dashboardUpperCardState(cardState, isEmpty = false) {
  const normalized = normalizeDashboardUpperCardState(cardState);
  return normalized === "success" && isEmpty ? "empty" : normalized;
}

function normalizeDashboardUpperSectionData(data = DASHBOARD_UPPER_SECTION_EMPTY) {
  const source = data && typeof data === "object" ? data : DASHBOARD_UPPER_SECTION_EMPTY;
  return {
    licenseSummary: source.licenseSummary && typeof source.licenseSummary === "object" ? source.licenseSummary : {},
    baseOperations: source.baseOperations && typeof source.baseOperations === "object" ? source.baseOperations : { bases: [], summary: {} },
    criticalQualifications: Array.isArray(source.criticalQualifications) ? source.criticalQualifications : [],
  };
}

function renderDashboardUpperInfoIcon(title) {
  return `<span class="dashboard-upper-info-icon" title="${escapeAttr(title)}" aria-label="${escapeAttr(title)}">${dashboardTopIconMarkup("info")}</span>`;
}

function renderDashboardUpperCardHeader(title, subtitle, options = {}) {
  const actionHref = String(options.actionHref || "").trim();
  const actionLabel = String(options.actionLabel || "").trim();
  const asideMarkup = options.metaMarkup || (
    actionHref && actionLabel
      ? `<a class="dashboard-upper-card-action" href="${escapeAttr(actionHref)}">${escapeHtml(actionLabel)} ${dashboardTopIconMarkup("chevronRight")}</a>`
      : ""
  );
  return `
    <header class="dashboard-upper-card-header">
      <div>
        <h3>${escapeHtml(title)} ${options.info === false ? "" : renderDashboardUpperInfoIcon(options.infoLabel || title)}</h3>
        <p>${escapeHtml(subtitle)}</p>
      </div>
      ${asideMarkup}
    </header>
  `;
}

function renderDashboardUpperCardState(title, detail = "", type = "empty") {
  const normalizedType = ["empty", "error"].includes(type) ? type : "empty";
  return `
    <div class="dashboard-upper-card-state dashboard-upper-card-state--${normalizedType}" role="${normalizedType === "error" ? "alert" : "status"}">
      <strong>${escapeHtml(title)}</strong>
      ${detail ? `<span>${escapeHtml(detail)}</span>` : ""}
    </div>
  `;
}

function renderDashboardUpperLoadingSkeleton(rows = 4) {
  return `
    <div class="dashboard-upper-skeleton" aria-hidden="true">
      ${Array.from({ length: rows })
        .map((_, index) => `<span class="dashboard-upper-skeleton-line dashboard-upper-skeleton-line--${index + 1}"></span>`)
        .join("")}
    </div>
  `;
}

function renderDashboardSeverityBadge(severity, label = "") {
  const tone = dashboardUpperSeverity(severity);
  return `<span class="dashboard-severity-badge dashboard-severity-badge--${tone}">${escapeHtml(label || dashboardUpperSeverityLabel(tone))}</span>`;
}

function renderDashboardMiniProgress(value, severity = "normal") {
  const percent = Math.max(0, Math.min(100, Math.round(asDashboardNumber(value))));
  const tone = dashboardUpperSeverity(severity);
  return `
    <span class="dashboard-mini-progress dashboard-mini-progress--${tone}" style="--progress-value: ${percent}%">
      <span class="dashboard-mini-progress-fill"></span>
    </span>
  `;
}

function renderDashboardSegmentedStatusBar(items) {
  const safeItems = Array.isArray(items) ? items : [];
  const total = safeItems.reduce((acc, item) => acc + asDashboardNumber(item.value), 0);
  if (total <= 0) {
    return `<div class="dashboard-segmented-status-bar dashboard-segmented-status-bar--empty" aria-hidden="true"></div>`;
  }
  return `
    <div class="dashboard-segmented-status-bar" aria-label="Distribui\u00e7\u00e3o por status operacional">
      ${safeItems
        .map((item) => {
          const share = dashboardPercent(item.value, total);
          const tone = dashboardUpperSeverity(item.severity);
          return `<span class="dashboard-segmented-status-segment dashboard-segmented-status-segment--${tone}" style="--segment-width: ${share}%" title="${escapeAttr(`${item.label}: ${asDashboardNumber(item.value)}`)}"></span>`;
        })
        .join("")}
    </div>
  `;
}

function dashboardDonutColor(item) {
  if (item.color) return item.color;
  const colors = {
    critical: "#ef233c",
    warning: "#ff7a18",
    planning: "#f6c915",
    normal: "#43b756",
  };
  return colors[dashboardUpperSeverity(item.severity)] || colors.normal;
}

function renderDashboardLicenseDonut(items, total) {
  const safeItems = Array.isArray(items) ? items : [];
  const numericTotal = Math.max(0, asDashboardNumber(total));
  const distributionTotal = safeItems.reduce((acc, item) => acc + asDashboardNumber(item.value), 0);
  if (numericTotal <= 0 || distributionTotal <= 0) {
    return `
      <div class="dashboard-license-donut dashboard-license-donut--empty">
        <span class="dashboard-license-donut-center"><strong>0</strong><small>Total</small></span>
      </div>
    `;
  }

  let cursor = 0;
  const gradient = safeItems
    .map((item) => {
      const share = (asDashboardNumber(item.value) / distributionTotal) * 100;
      const start = cursor;
      const end = Math.min(100, cursor + share);
      cursor = end;
      return `${dashboardDonutColor(item)} ${start.toFixed(2)}% ${end.toFixed(2)}%`;
    })
    .join(", ");
  const percentByKey = Object.fromEntries(safeItems.map((item) => [item.key || item.label, dashboardPercent(item.value, distributionTotal)]));

  return `
    <div class="dashboard-license-donut" style="--donut-gradient: ${escapeAttr(gradient)}" aria-label="Distribui\u00e7\u00e3o de vencimentos">
      <span class="dashboard-license-donut-center"><strong>${numericTotal}</strong><small>Total</small></span>
      <span class="dashboard-license-donut-label dashboard-license-donut-label--critical">${percentByKey.expired || 0}%</span>
      <span class="dashboard-license-donut-label dashboard-license-donut-label--warning">${percentByKey.dueIn7Days || 0}%</span>
      <span class="dashboard-license-donut-label dashboard-license-donut-label--planning">${percentByKey.dueIn30Days || 0}%</span>
      <span class="dashboard-license-donut-label dashboard-license-donut-label--normal">${percentByKey.valid || 0}%</span>
    </div>
  `;
}

function renderLicenseExpirationCard(summaryInput, cardState = "success") {
  const summary = summaryInput && typeof summaryInput === "object" ? summaryInput : {};
  const total = asDashboardNumber(summary.total);
  const metricItems = [
    { key: "expired", label: "Vencidos", value: summary.expired, severity: "critical", color: "#ef233c" },
    { key: "dueToday", label: "Vencem hoje", value: summary.dueToday, severity: "warning", color: "#ff7a18" },
    { key: "dueIn7Days", label: "Vencem em at\u00e9 7 dias", value: summary.dueIn7Days, severity: "warning", color: "#fb8500" },
    { key: "dueIn30Days", label: "Vencem em at\u00e9 30 dias", value: summary.dueIn30Days, severity: "planning", color: "#f6c915" },
    { key: "valid", label: "Dentro do prazo", value: summary.valid, severity: "normal", color: "#43b756" },
  ];
  const distributionTotal = metricItems.reduce((acc, item) => acc + asDashboardNumber(item.value), 0);
  const stateName = dashboardUpperCardState(cardState, total <= 0 && distributionTotal <= 0);
  const bodyMarkup = () => `
    <div class="dashboard-license-card-body">
      <div class="dashboard-license-donut-layout">
        ${renderDashboardLicenseDonut(metricItems, total)}
        <div class="dashboard-license-legend">
        ${metricItems
          .map((item) => {
            const tone = dashboardUpperSeverity(item.severity);
            const value = asDashboardNumber(item.value);
            return `
              <div class="dashboard-license-legend-row dashboard-license-metric--${tone}">
                <span class="dashboard-license-metric-label"><span style="background: ${escapeAttr(item.color)}" aria-hidden="true"></span>${escapeHtml(item.label)}</span>
                <strong>${value}</strong>
              </div>
            `;
          })
          .join("")}
        </div>
      </div>
      <footer class="dashboard-license-card-footer">
        <span class="dashboard-license-footer-icon">${dashboardTopIconMarkup("clock")}</span>
        <span>\u00daltima atualiza\u00e7\u00e3o: h\u00e1 1 min</span>
      </footer>
    </div>
  `;

  return `
    <article class="dashboard-upper-card dashboard-upper-card--licenses ui-surface ui-card" data-dashboard-upper-card="license-expiration" data-dashboard-upper-card-state="${stateName}">
      ${renderDashboardUpperCardHeader("Vencimentos de Licen\u00e7as", "Distribui\u00e7\u00e3o por status operacional", {
        infoLabel: "Distribui\u00e7\u00e3o dos documentos por janela de vencimento",
        metaMarkup: `<span class="dashboard-license-total-inline"><small>Total monitorado</small><strong>${total}</strong></span>`,
      })}
      ${
        stateName === "loading"
          ? renderDashboardUpperLoadingSkeleton(5)
          : stateName === "error"
            ? renderDashboardUpperCardState("N\u00e3o foi poss\u00edvel carregar os indicadores.", "A leitura de vencimentos ser\u00e1 retomada na pr\u00f3xima atualiza\u00e7\u00e3o.", "error")
            : stateName === "empty"
              ? renderDashboardUpperCardState("Nenhum vencimento cr\u00edtico encontrado.", "A base monitorada n\u00e3o possui itens priorit\u00e1rios neste recorte.", "empty")
              : bodyMarkup()
      }
    </article>
  `;
}

function dashboardBaseStatusOptions(payload = {}) {
  const options = Array.isArray(payload.statusOptions)
    ? payload.statusOptions
    : Array.isArray(payload.status_options)
      ? payload.status_options
      : [];
  return options
    .filter((item) => item && typeof item === "object")
    .map((item) => ({
      key: String(item.key || "").trim(),
      label: String(item.label || item.key || "").trim(),
      class: String(item.class || item.status_class || item.marker_class || "status-gray").trim(),
      marker_class: String(item.marker_class || item.class || item.status_class || "status-gray").trim(),
    }))
    .filter((item) => item.key);
}

function dashboardBaseSafeNumber(value, fallback = 0) {
  if (value === null || value === undefined || value === "") return fallback;
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function dashboardBaseNormalizeLocationKey(value) {
  return String(value || "")
    .trim()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function dashboardBaseIcaoCode(base = {}) {
  const explicit = String(base.icao || base.icao_code || base.codigo_icao || base.airport_icao || "").trim().toUpperCase();
  if (/^[A-Z]{4}$/.test(explicit)) return explicit;
  const locationKey = dashboardBaseNormalizeLocationKey(base.nome || base.location || base.cidade || base.city);
  return DASHBOARD_BASE_ICAO_BY_LOCATION[locationKey] || "";
}

function dashboardBaseCounts(base = {}, statusOptions = []) {
  const sourceCounts = base.counts && typeof base.counts === "object" ? base.counts : {};
  const counts = {};
  statusOptions.forEach((item) => {
    counts[item.key] = asDashboardNumber(sourceCounts[item.key]);
  });
  Object.entries(sourceCounts).forEach(([key, value]) => {
    const normalizedKey = String(key || "").trim();
    if (normalizedKey && !Object.prototype.hasOwnProperty.call(counts, normalizedKey)) {
      counts[normalizedKey] = asDashboardNumber(value);
    }
  });
  return counts;
}

function dashboardBasePilotInitials(name = "") {
  const initials = String(name || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
  return initials || "?";
}

function normalizeDashboardBasePilot(pilot = {}, base = {}) {
  const name = String(pilot.nome || pilot.name || "").trim() || "Tripulante";
  return {
    ...pilot,
    id: dashboardBaseSafeNumber(pilot.id, 0),
    nome: name,
    matricula: String(pilot.matricula || "").trim(),
    tripulante_id: dashboardBaseSafeNumber(pilot.tripulante_id, 0),
    base_id: dashboardBaseSafeNumber(pilot.base_id, dashboardBaseSafeNumber(base.id, 0)),
    base_nome: String(pilot.base_nome || base.nome || "").trim(),
    base_uf: String(pilot.base_uf || base.uf || "").trim(),
    status: String(pilot.status || "ativo").trim(),
    status_label: String(pilot.status_label || pilot.status || "Ativo").trim(),
    status_class: String(pilot.status_class || "status-gray").trim(),
    possui_foto: Boolean(pilot.possui_foto),
    foto_url: String(pilot.foto_url || "").trim(),
    iniciais: String(pilot.iniciais || dashboardBasePilotInitials(name)).trim(),
    expiry_indicator: pilot.expiry_indicator && typeof pilot.expiry_indicator === "object" ? pilot.expiry_indicator : {},
  };
}

function normalizeDashboardBaseOperationsPayload(payloadInput, fallbackInput = DASHBOARD_EMPTY_BASE_OPERATIONS) {
  const fallback = fallbackInput && typeof fallbackInput === "object" ? fallbackInput : {};
  const payload = payloadInput && typeof payloadInput === "object" ? payloadInput : fallback;
  const statusOptions = dashboardBaseStatusOptions(payload).length ? dashboardBaseStatusOptions(payload) : dashboardBaseStatusOptions(fallback);
  const sourceBases = Array.isArray(payload.bases) ? payload.bases : Array.isArray(fallback.bases) ? fallback.bases : [];
  const bases = sourceBases
    .map((base, index) => {
      const id = dashboardBaseSafeNumber(base.id, index + 1);
      const nome = String(base.nome || base.location || base.code || `Base ${index + 1}`).trim();
      const uf = String(base.uf || base.code || "BR").trim();
      const latitude = dashboardBaseSafeNumber(base.latitude, Number.NaN);
      const longitude = dashboardBaseSafeNumber(base.longitude, Number.NaN);
      const counts = dashboardBaseCounts(base, statusOptions);
      const pilots = Array.isArray(base.pilotos) ? base.pilotos.map((pilot) => normalizeDashboardBasePilot(pilot, { id, nome, uf })) : [];
      const totalPilots = asDashboardNumber(base.total_pilotos ?? base.crew ?? pilots.length);
      if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return null;
      return {
        ...base,
        id,
        icao: dashboardBaseIcaoCode(base),
        nome,
        uf,
        latitude,
        longitude,
        ativa: base.ativa !== false,
        total_pilotos: totalPilots,
        counts,
        pilotos: pilots,
      };
    })
    .filter(Boolean);
  const topLevelPilots = Array.isArray(payload.pilotos)
    ? payload.pilotos.map((pilot) => normalizeDashboardBasePilot(pilot, bases.find((base) => Number(base.id) === Number(pilot.base_id)) || {}))
    : bases.flatMap((base) => base.pilotos);
  const basesWithPilots = bases.map((base) => {
    const pilots = base.pilotos.length ? base.pilotos : topLevelPilots.filter((pilot) => Number(pilot.base_id) === Number(base.id));
    return { ...base, pilotos: pilots, total_pilotos: Math.max(asDashboardNumber(base.total_pilotos), pilots.length) };
  });
  const derivedCrew = basesWithPilots.reduce((acc, base) => acc + asDashboardNumber(base.total_pilotos), 0);
  const derivedAlerts = basesWithPilots.reduce((acc, base) => acc + asDashboardNumber(base.counts.atestado) + asDashboardNumber(base.counts.afastado) + asDashboardNumber(base.counts.treinamento), 0);
  const hasExplicitSummary = payload.summary && typeof payload.summary === "object";
  const summarySource = hasExplicitSummary ? payload.summary : {};
  const fallbackSummary = fallback.summary && typeof fallback.summary === "object" ? fallback.summary : {};
  return {
    ...payload,
    bases: basesWithPilots,
    pilotos: topLevelPilots.length ? topLevelPilots : basesWithPilots.flatMap((base) => base.pilotos),
    statusOptions,
    summary: {
      basesActive: asDashboardNumber(summarySource.basesActive ?? (basesWithPilots.length ? basesWithPilots.filter((base) => base.ativa !== false).length : fallbackSummary.basesActive)),
      crew: asDashboardNumber(summarySource.crew ?? (basesWithPilots.length ? derivedCrew : fallbackSummary.crew)),
      alerts: asDashboardNumber(summarySource.alerts ?? (basesWithPilots.length ? derivedAlerts : fallbackSummary.alerts)),
      restrictions: asDashboardNumber(summarySource.restrictions ?? (basesWithPilots.length ? basesWithPilots.reduce((acc, base) => acc + asDashboardNumber(base.counts.afastado), 0) : fallbackSummary.restrictions)),
    },
  };
}

function stopDashboardBaseMapRotation() {
  if (dashboardBaseMapRotationTimer) {
    window.clearInterval(dashboardBaseMapRotationTimer);
  }
  dashboardBaseMapRotationTimer = null;
}

function destroyDashboardBaseMirrorMap() {
  dashboardBaseMapRequestSequence += 1;
  stopDashboardBaseMapRotation();
  if (dashboardBaseMapState?.resizeRaf) {
    window.cancelAnimationFrame(dashboardBaseMapState.resizeRaf);
  }
  if (dashboardBaseMapState?.resizeObserver) {
    dashboardBaseMapState.resizeObserver.disconnect();
  }
  if (dashboardBaseMapState?.resizeHandler) {
    window.removeEventListener("resize", dashboardBaseMapState.resizeHandler);
    document.removeEventListener("fullscreenchange", dashboardBaseMapState.resizeHandler);
    document.removeEventListener("webkitfullscreenchange", dashboardBaseMapState.resizeHandler);
  }
  if (dashboardBaseMapState?.map) {
    dashboardBaseMapState.map.remove();
  }
  dashboardBaseMapState = null;
}

function dashboardBaseMapStatus(message, stateName = "loading") {
  const statusNode = document.querySelector("[data-dashboard-base-map-status]");
  if (!statusNode) return;
  statusNode.textContent = message;
  statusNode.dataset.state = stateName;
}

function dashboardScriptAlreadyLoaded(src) {
  return [...document.querySelectorAll("script[src]")].some((script) => script.getAttribute("src") === src);
}

function dashboardStylesheetAlreadyLoaded(href) {
  return [...document.querySelectorAll('link[rel="stylesheet"][href]')].some((link) => link.getAttribute("href") === href);
}

function loadDashboardLeaflet() {
  if (window.L) return Promise.resolve(window.L);
  if (dashboardLeafletLoadPromise) return dashboardLeafletLoadPromise;

  if (!dashboardStylesheetAlreadyLoaded(DASHBOARD_LEAFLET_CSS_HREF)) {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = DASHBOARD_LEAFLET_CSS_HREF;
    document.head.appendChild(link);
  }

  dashboardLeafletLoadPromise = new Promise((resolve, reject) => {
    const finish = () => {
      if (window.L) {
        resolve(window.L);
      } else {
        reject(new Error("Leaflet indisponivel."));
      }
    };
    const fail = () => reject(new Error("Leaflet indisponivel."));
    const existingScript = [...document.querySelectorAll("script[src]")].find((script) => script.getAttribute("src") === DASHBOARD_LEAFLET_SCRIPT_SRC);
    if (existingScript) {
      existingScript.addEventListener("load", finish, { once: true });
      existingScript.addEventListener("error", fail, { once: true });
      window.setTimeout(finish, 0);
      return;
    }

    const script = document.createElement("script");
    script.src = DASHBOARD_LEAFLET_SCRIPT_SRC;
    script.async = true;
    script.addEventListener("load", finish, { once: true });
    script.addEventListener("error", fail, { once: true });
    document.head.appendChild(script);
  });

  if (dashboardScriptAlreadyLoaded(DASHBOARD_LEAFLET_SCRIPT_SRC) && window.L) {
    return Promise.resolve(window.L);
  }
  return dashboardLeafletLoadPromise;
}

function dashboardBaseSanitizeCssToken(value, fallback = "status-gray") {
  const raw = String(value || "").trim();
  if (!raw) return fallback;
  return /^[a-z0-9_-]+$/i.test(raw) ? raw : fallback;
}

function dashboardBaseSafeInt(value, fallback = 0) {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function dashboardBaseSanitizeInternalPhotoUrl(value) {
  const raw = String(value || "").trim();
  if (!raw || !raw.startsWith("/")) return "";
  return /^\/(bases\/pilotos|tripulantes)\/\d+\/foto(?:\?.*)?$/i.test(raw) ? raw : "";
}

function dashboardBaseBuildBadge(label, count, className) {
  const safeClass = dashboardBaseSanitizeCssToken(className, "status-gray");
  const safeCount = dashboardBaseSafeInt(count, 0);
  return `<span class="status-pill ${safeClass}">${escapeHtml(label)}: ${safeCount}</span>`;
}

function dashboardBasePilotAvatar(pilot, extraClass = "") {
  const indicator = pilot.expiry_indicator || {};
  const safeIndicatorClass = dashboardBaseSanitizeCssToken(indicator.css_class, "");
  const indicatorClass = safeIndicatorClass ? ` ${safeIndicatorClass}` : "";
  const pulseClass = indicator.pulse ? " avatar-expiry-pulse" : "";
  const daysRemaining = Number.isInteger(indicator.days_remaining) ? indicator.days_remaining : null;
  const tooltip = daysRemaining === null
    ? "Sem data de vencimento cadastrada"
    : daysRemaining < 0
      ? `Habilitacao vencida ha ${Math.abs(daysRemaining)} dia(s)`
      : daysRemaining === 0
        ? "Habilitacao vence hoje"
        : `Habilitacao vence em ${daysRemaining} dia(s)`;
  const safePhotoUrl = dashboardBaseSanitizeInternalPhotoUrl(pilot.foto_url);
  const initials = escapeHtml(pilot.iniciais || "?");
  const onErrScript = "const p=this.parentElement;if(!p)return;this.onerror=null;p.dataset.photoState='unavailable';p.textContent='';const s=document.createElement('span');s.textContent=this.dataset.initials||'?';p.appendChild(s);";
  const photoMarkup = safePhotoUrl
    ? `<img src="${escapeAttr(safePhotoUrl)}" alt="${escapeAttr(pilot.nome)}" loading="lazy" decoding="async" referrerpolicy="same-origin" data-initials="${initials}" onerror="${escapeAttr(onErrScript)}">`
    : `<span>${initials}</span>`;
  return `<div class="avatar avatar-expiry ${escapeAttr(`${extraClass}${indicatorClass}${pulseClass}`.trim())}" data-photo-state="${safePhotoUrl ? "loaded" : "empty"}" title="${escapeAttr(tooltip)}">${photoMarkup}</div>`;
}

function dashboardBaseMarkerMode(mapState) {
  if (mapState?.root?.closest?.(".dashboard-operational-page-shell")) {
    return "pin";
  }
  const zoom = mapState?.map ? mapState.map.getZoom() : DASHBOARD_BASES_MAP_INITIAL_ZOOM;
  if (zoom <= 4) return "zoomout";
  const expandedZoom = mapState?.compactMarkers ? 6 : 5;
  return zoom >= expandedZoom ? "expanded" : "peek";
}

function dashboardBasePilotSortWeight(pilot) {
  const indicator = pilot.expiry_indicator || {};
  const daysRemaining = Number.isInteger(indicator.days_remaining) ? indicator.days_remaining : 99999;
  return [daysRemaining, String(pilot.nome || "")];
}

function dashboardBasePilotComparator(left, right) {
  const [leftDays, leftName] = dashboardBasePilotSortWeight(left);
  const [rightDays, rightName] = dashboardBasePilotSortWeight(right);
  if (leftDays !== rightDays) return leftDays - rightDays;
  return leftName.localeCompare(rightName, "pt-BR");
}

function dashboardBaseAggregateCounts(list, statusOptions) {
  const counts = {};
  statusOptions.forEach((item) => {
    counts[item.key] = 0;
  });
  list.forEach((base) => {
    statusOptions.forEach((item) => {
      counts[item.key] += asDashboardNumber(base.counts?.[item.key]);
    });
  });
  return counts;
}

function buildDashboardBaseMarkerEntities(mapState, mode) {
  const bases = Array.isArray(mapState?.payload?.bases) ? [...mapState.payload.bases] : [];
  const baseToMarker = (base) => ({
    ...base,
    marker_key: `base-${base.id}`,
    marker_kind: "base",
    marker_label: `${base.icao ? `${base.icao} - ` : ""}${base.nome} / ${base.uf}`,
    marker_bases: [base],
  });
  if (mode !== "zoomout") {
    return bases.map(baseToMarker);
  }

  const maxMarkers = 4;
  if (bases.length <= maxMarkers) {
    return bases.map(baseToMarker);
  }

  const sorted = [...bases].sort((left, right) => asDashboardNumber(right.total_pilotos) - asDashboardNumber(left.total_pilotos));
  const topBases = sorted.slice(0, maxMarkers - 1);
  const remaining = sorted.slice(maxMarkers - 1);
  const totalWeight = remaining.reduce((acc, item) => acc + Math.max(1, asDashboardNumber(item.total_pilotos)), 0);
  const weightedLatitude = remaining.reduce((acc, item) => acc + dashboardBaseSafeNumber(item.latitude, 0) * Math.max(1, asDashboardNumber(item.total_pilotos)), 0);
  const weightedLongitude = remaining.reduce((acc, item) => acc + dashboardBaseSafeNumber(item.longitude, 0) * Math.max(1, asDashboardNumber(item.total_pilotos)), 0);
  const aggregatedPilots = remaining.flatMap((item) => item.pilotos || []).sort(dashboardBasePilotComparator);
  const entities = topBases.map(baseToMarker);
  entities.push({
    id: "cluster-rest",
    nome: "Outras bases",
    uf: "BR",
    latitude: Number.isFinite(weightedLatitude) && totalWeight > 0 ? weightedLatitude / totalWeight : DASHBOARD_BASES_MAP_CENTER[0],
    longitude: Number.isFinite(weightedLongitude) && totalWeight > 0 ? weightedLongitude / totalWeight : DASHBOARD_BASES_MAP_CENTER[1],
    total_pilotos: remaining.reduce((acc, item) => acc + asDashboardNumber(item.total_pilotos), 0),
    counts: dashboardBaseAggregateCounts(remaining, mapState.payload.statusOptions || []),
    pilotos: aggregatedPilots,
    marker_key: "cluster-rest",
    marker_kind: "cluster",
    marker_label: `${remaining.length} bases agrupadas`,
    marker_bases: remaining,
  });
  return entities;
}

function dashboardBaseAlertCount(marker = {}) {
  return asDashboardNumber(marker.counts?.atestado) + asDashboardNumber(marker.counts?.afastado) + asDashboardNumber(marker.counts?.treinamento);
}

function dashboardBasePilotsForMarker(mapState, marker, mode) {
  const source = Array.isArray(marker.pilotos) ? [...marker.pilotos] : [];
  source.sort(dashboardBasePilotComparator);
  const limit = mode === "pin" ? 0 : mode === "expanded" ? (mapState.compactMarkers ? 3 : 4) : 3;
  const visible = source.slice(0, limit);
  const hiddenCount = Math.max(0, source.length - visible.length);
  return { visible, hiddenCount };
}

function renderDashboardBaseMarkerHtml(mapState, marker, mode) {
  const compact = mapState.compactMarkers;
  const activeClass = marker.marker_key === mapState.activeMarkerKey ? "dashboard-base-marker-active" : "";
  const markerCardClass = mode === "zoomout" ? "base-marker-card--zoomout" : "";
  const badges = (mapState.payload.statusOptions || [])
    .filter((item) => asDashboardNumber(marker.counts?.[item.key]) > 0)
    .map((item) => {
      const count = asDashboardNumber(marker.counts?.[item.key]);
      const label = compact ? item.label.slice(0, 3) : item.label;
      return dashboardBaseBuildBadge(label, count, item.class);
    })
    .join("");
  const { visible: visiblePilots, hiddenCount } = dashboardBasePilotsForMarker(mapState, marker, mode);
  const avatars = visiblePilots
    .map((pilot) => dashboardBasePilotAvatar(pilot, mode !== "expanded" ? "avatar-xs" : (compact ? "avatar-xs" : "avatar-sm")))
    .join("");
  const overflowBadge = hiddenCount > 0 ? `<span class="base-marker-avatar-more">+${hiddenCount}</span>` : "";

  if (mode === "pin") {
    const alerts = dashboardBaseAlertCount(marker);
    const icaoCode = marker.icao || "BASE";
    const title = `${icaoCode} - ${marker.nome} / ${marker.uf} · ${asDashboardNumber(marker.total_pilotos)} tripulantes${alerts ? ` · ${alerts} alertas` : ""}`;
    return `
      <button
        type="button"
        class="dashboard-base-pin-marker ${alerts ? "dashboard-base-pin-marker--attention" : "dashboard-base-pin-marker--normal"} ${activeClass} base-marker-trigger"
        data-marker-key="${escapeAttr(marker.marker_key)}"
        title="${escapeAttr(title)}"
        aria-label="${escapeAttr(title)}"
      >
        <span class="dashboard-base-pin-marker-code">${escapeHtml(icaoCode)}</span>
        <span class="dashboard-base-pin-marker-count">${asDashboardNumber(marker.total_pilotos)}</span>
        ${alerts ? `<span class="dashboard-base-pin-marker-alert">${alerts}</span>` : ""}
      </button>
    `;
  }

  if (mode === "peek") {
    return `
      <button type="button" class="base-marker-card base-marker-card-peek ${compact ? "compact" : ""} ${markerCardClass} ${activeClass} base-marker-trigger" data-marker-key="${escapeAttr(marker.marker_key)}">
        <div class="base-marker-peek-top">
          <strong>${escapeHtml(marker.nome)}</strong>
          <span>${escapeHtml(marker.total_pilotos)} piloto(s)</span>
        </div>
        <div class="base-marker-peek-avatars">${avatars || '<span class="secondary-cell">Sem tripulantes</span>'}${overflowBadge}</div>
        <div class="base-marker-peek-footer">
          <span class="base-marker-peek-status">${asDashboardNumber(marker.total_pilotos)} monitorados</span>
          <span class="base-marker-peek-link">Abrir</span>
        </div>
      </button>
    `;
  }

  if (mode === "zoomout") {
    return `
      <button type="button" class="base-marker-card base-marker-card-peek ${compact ? "compact" : ""} base-marker-card--zoomout ${activeClass} base-marker-trigger" data-marker-key="${escapeAttr(marker.marker_key)}">
        <div class="base-marker-peek-top">
          <strong>${escapeHtml(marker.nome)}</strong>
          <span>${escapeHtml(marker.total_pilotos)} piloto(s)</span>
        </div>
        <div class="base-marker-peek-avatars">${avatars || '<span class="secondary-cell">Sem tripulantes</span>'}${overflowBadge}</div>
        <div class="base-marker-peek-footer">
          <span class="base-marker-peek-status">${escapeHtml(marker.marker_label || "Base")}</span>
          <span class="base-marker-peek-link">Abrir</span>
        </div>
      </button>
    `;
  }

  return `
    <div class="base-marker-card ${compact ? "compact" : ""} ${markerCardClass} ${activeClass}">
      <div class="base-marker-head">
        <strong>${escapeHtml(marker.nome)}</strong>
        <span>${escapeHtml(marker.uf)}</span>
      </div>
      <div class="base-marker-total">${escapeHtml(marker.total_pilotos)} piloto(s)</div>
      <div class="base-marker-avatars" aria-label="Pr\u00e9via de pilotos">${avatars || '<span class="secondary-cell base-marker-empty">Sem tripulantes vinculados</span>'}${overflowBadge}</div>
      <div class="base-marker-badges">${badges}</div>
      <button type="button" class="base-marker-button" data-marker-key="${escapeAttr(marker.marker_key)}">Ver pilotos</button>
    </div>
  `;
}

function dashboardBaseMarkerIconMetrics(mapState, marker, mode) {
  const renderedAvatarsCount = dashboardBasePilotsForMarker(mapState, marker, mode).visible.length;
  if (mode === "pin") {
    const compact = mapState.compactMarkers;
    const width = compact ? 62 : 72;
    const height = compact ? 36 : 42;
    return {
      iconSize: [width, height],
      iconAnchor: [Math.round(width / 2), Math.round(height / 2)],
    };
  }
  const compact = mapState.compactMarkers;
  if (mode !== "peek") {
    const perRow = compact ? 3 : 4;
    const rows = Math.max(1, Math.ceil(renderedAvatarsCount / perRow));
    const width = compact ? 182 : 248;
    const headerHeight = compact ? 68 : 76;
    const badgesHeight = compact ? 26 : 28;
    const buttonHeight = compact ? 34 : 38;
    const verticalPadding = compact ? 22 : 26;
    const avatarRowHeight = compact ? 30 : 38;
    const avatarGap = compact ? 4 : 6;
    const avatarsHeight = rows * avatarRowHeight + Math.max(0, rows - 1) * avatarGap;
    const height = headerHeight + badgesHeight + buttonHeight + verticalPadding + avatarsHeight;
    return {
      iconSize: [width, height],
      iconAnchor: [Math.round(width / 2), Math.round(height / 2)],
    };
  }
  const width = compact ? 156 : 184;
  const rows = Math.max(1, Math.ceil(renderedAvatarsCount / 3));
  const baseHeight = compact ? 84 : 88;
  const extraHeightPerRow = compact ? 22 : 24;
  const height = baseHeight + Math.max(0, rows - 1) * extraHeightPerRow;
  return {
    iconSize: [width, height],
    iconAnchor: [Math.round(width / 2), Math.round(height / 2)],
  };
}

function dashboardCssEscape(value) {
  const raw = String(value ?? "");
  if (window.CSS?.escape) return window.CSS.escape(raw);
  return raw.replace(/["\\]/g, "\\$&");
}

function applyDashboardBaseActiveMarker() {
  const mapRoot = document.querySelector("[data-dashboard-base-map]");
  if (!mapRoot || !dashboardBaseMapState?.activeMarkerKey) return;
  mapRoot.querySelectorAll(".dashboard-base-marker-active").forEach((node) => node.classList.remove("dashboard-base-marker-active"));
  mapRoot
    .querySelectorAll(`[data-marker-key="${dashboardCssEscape(dashboardBaseMapState.activeMarkerKey)}"]`)
    .forEach((node) => node.classList.add("dashboard-base-marker-active"));
}

function renderDashboardBaseMapMarkers(force = false) {
  const mapState = dashboardBaseMapState;
  if (!mapState?.map || !window.L) return;
  updateDashboardBaseMapViewport(mapState);
  const mode = dashboardBaseMarkerMode(mapState);
  if (!force && mode === mapState.lastMarkerMode) {
    applyDashboardBaseActiveMarker();
    return;
  }
  mapState.lastMarkerMode = mode;
  mapState.markers.forEach((marker) => mapState.map.removeLayer(marker));
  mapState.markers = [];
  mapState.markerEntityByKey = new Map();
  const entities = buildDashboardBaseMarkerEntities(mapState, mode);
  entities.forEach((entity) => {
    const metrics = dashboardBaseMarkerIconMetrics(mapState, entity, mode);
    const icon = window.L.divIcon({
      className: "base-marker-wrapper",
      html: renderDashboardBaseMarkerHtml(mapState, entity, mode),
      iconSize: metrics.iconSize,
      iconAnchor: metrics.iconAnchor,
    });
    const marker = window.L.marker([entity.latitude, entity.longitude], { icon }).addTo(mapState.map);
    mapState.markers.push(marker);
    mapState.markerEntityByKey.set(entity.marker_key, entity);
  });
  applyDashboardBaseActiveMarker();
}

function dashboardBaseRotationTargets(mapState) {
  return buildDashboardBaseMarkerEntities(mapState, "expanded").filter((entity) => entity.marker_kind === "base");
}

function dashboardBaseMapViewportProfile(root) {
  const stage = root?.closest?.("[data-dashboard-base-map-stage]");
  const shell = root?.closest?.(".dashboard-operational-page-shell");
  const rect = stage?.getBoundingClientRect?.() || { width: window.innerWidth || 0, height: window.innerHeight || 0 };
  const isFullscreen = Boolean(document.fullscreenElement || document.webkitFullscreenElement);
  const isTvShell = shell?.classList.contains("dashboard-operational-tv-shell") || isFullscreen;
  const isShort = rect.height <= 240 || window.innerHeight <= 900;
  const isNarrow = rect.width <= 560 || window.innerWidth <= 900;
  return {
    isTvShell,
    isShort,
    isNarrow,
    compactMarkers: isTvShell || isShort || isNarrow,
    fitPadding: isNarrow ? [16, 16] : isTvShell ? [32, 32] : [24, 24],
  };
}

function updateDashboardBaseMapViewport(mapState) {
  const profile = dashboardBaseMapViewportProfile(mapState?.root);
  const changed = mapState.compactMarkers !== profile.compactMarkers;
  mapState.compactMarkers = profile.compactMarkers;
  mapState.viewportProfile = profile;
  return changed;
}

function dashboardBaseMapBounds(mapState) {
  const bases = Array.isArray(mapState?.payload?.bases) ? mapState.payload.bases : [];
  const coordinates = bases
    .map((base) => [dashboardBaseSafeNumber(base.latitude, Number.NaN), dashboardBaseSafeNumber(base.longitude, Number.NaN)])
    .filter(([latitude, longitude]) => Number.isFinite(latitude) && Number.isFinite(longitude));
  if (!coordinates.length || !window.L) return null;
  return window.L.latLngBounds(coordinates);
}

function fitDashboardBaseMapToBounds(mapState, options = {}) {
  if (!mapState?.map || !window.L) return;
  const bounds = dashboardBaseMapBounds(mapState);
  if (!bounds || !bounds.isValid()) {
    mapState.map.setView(DASHBOARD_BASES_MAP_CENTER, DASHBOARD_BASES_MAP_INITIAL_ZOOM, { animate: false });
    return;
  }
  updateDashboardBaseMapViewport(mapState);
  mapState.map.fitBounds(bounds, {
    animate: Boolean(options.animate),
    maxZoom: DASHBOARD_BASES_MAP_INITIAL_ZOOM,
    padding: mapState.viewportProfile?.fitPadding || [24, 24],
  });
}

function focusDashboardBaseMarker(mapState, targetIndex = 0, options = {}) {
  if (!mapState?.map) return;
  const targets = dashboardBaseRotationTargets(mapState);
  if (!targets.length) return;
  const target = targets[((targetIndex % targets.length) + targets.length) % targets.length];
  const prefersReducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
  mapState.activeMarkerKey = target.marker_key;
  mapState.rotationIndex = targetIndex;
  const keepAllBasesVisible = dashboardBaseMarkerMode(mapState) === "pin";
  if (keepAllBasesVisible) {
    fitDashboardBaseMapToBounds(mapState, { animate: false });
  } else if (prefersReducedMotion || options.immediate || typeof mapState.map.flyTo !== "function") {
    mapState.map.setView([target.latitude, target.longitude], DASHBOARD_BASES_MAP_FOCUS_ZOOM, { animate: false });
  } else {
    const latLng = [target.latitude, target.longitude];
    mapState.map.flyTo(latLng, DASHBOARD_BASES_MAP_FOCUS_ZOOM, {
      animate: true,
      duration: 1.25,
      easeLinearity: 0.25,
    });
  }
  dashboardBaseMapStatus(`Foco: ${target.marker_label}`, "ready");
  window.setTimeout(() => {
    renderDashboardBaseMapMarkers(false);
    applyDashboardBaseActiveMarker();
  }, options.immediate ? 0 : 800);
}

function startDashboardBaseMapRotation(mapState) {
  stopDashboardBaseMapRotation();
  const targets = dashboardBaseRotationTargets(mapState);
  if (!targets.length) return;
  focusDashboardBaseMarker(mapState, 0, { immediate: true });
  if (targets.length < 2) return;
  dashboardBaseMapRotationTimer = window.setInterval(() => {
    const mapRoot = document.querySelector("[data-dashboard-base-map]");
    if (!mapRoot || dashboardBaseMapState !== mapState) {
      stopDashboardBaseMapRotation();
      return;
    }
    focusDashboardBaseMarker(mapState, (mapState.rotationIndex + 1) % targets.length);
  }, DASHBOARD_BASES_MAP_ROTATION_INTERVAL_MS);
}

function scheduleDashboardBaseMapResize(mapState, options = {}) {
  if (!mapState?.map) return;
  if (mapState.resizeRaf) {
    window.cancelAnimationFrame(mapState.resizeRaf);
  }
  mapState.resizeRaf = window.requestAnimationFrame(() => {
    mapState.resizeRaf = null;
    if (!dashboardBaseMapState || dashboardBaseMapState !== mapState || !document.contains(mapState.root)) return;
    const markerModeChanged = updateDashboardBaseMapViewport(mapState);
    mapState.map.invalidateSize({ animate: false });
    fitDashboardBaseMapToBounds(mapState, { animate: false });
    renderDashboardBaseMapMarkers(Boolean(options.force || markerModeChanged));
    applyDashboardBaseActiveMarker();
  });
}

function wireDashboardBaseMapResize(mapState) {
  if (!mapState?.root) return;
  if (window.ResizeObserver) {
    mapState.resizeObserver = new ResizeObserver(() => scheduleDashboardBaseMapResize(mapState, { force: true }));
    mapState.resizeObserver.observe(mapState.root);
    const stage = mapState.root.closest("[data-dashboard-base-map-stage]");
    if (stage) mapState.resizeObserver.observe(stage);
  }
  mapState.resizeHandler = () => scheduleDashboardBaseMapResize(mapState, { force: true });
  window.addEventListener("resize", mapState.resizeHandler, { passive: true });
  document.addEventListener("fullscreenchange", mapState.resizeHandler);
  document.addEventListener("webkitfullscreenchange", mapState.resizeHandler);
}

function updateDashboardBaseSummaryDom(summary = {}) {
  Object.entries(summary).forEach(([key, value]) => {
    const node = document.querySelector(`[data-dashboard-base-summary-value="${dashboardCssEscape(key)}"]`);
    if (node) node.textContent = String(asDashboardNumber(value));
  });
}

function wireDashboardBaseMapActions(root) {
  root.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-marker-key]");
    if (!trigger) return;
    event.preventDefault();
    window.location.href = BACKEND_LINKS.bases;
  });
}

function initializeDashboardBaseMap(root, payload) {
  const profile = dashboardBaseMapViewportProfile(root);
  const mapState = {
    root,
    payload,
    map: window.L.map(root, {
      zoomControl: false,
      scrollWheelZoom: false,
      attributionControl: true,
    }).setView(DASHBOARD_BASES_MAP_CENTER, DASHBOARD_BASES_MAP_INITIAL_ZOOM),
    markers: [],
    markerEntityByKey: new Map(),
    compactMarkers: profile.compactMarkers,
    viewportProfile: profile,
    lastMarkerMode: null,
    activeMarkerKey: null,
    rotationIndex: 0,
    resizeObserver: null,
    resizeHandler: null,
    resizeRaf: null,
  };
  dashboardBaseMapState = mapState;
  window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(mapState.map);
  wireDashboardBaseMapActions(root);
  wireDashboardBaseMapResize(mapState);
  fitDashboardBaseMapToBounds(mapState, { animate: false });
  renderDashboardBaseMapMarkers(true);
  mapState.map.on("zoomend", () => renderDashboardBaseMapMarkers(false));
  window.setTimeout(() => {
    mapState.map.invalidateSize({ animate: false });
    fitDashboardBaseMapToBounds(mapState, { animate: false });
    renderDashboardBaseMapMarkers(true);
    startDashboardBaseMapRotation(mapState);
  }, 150);
  return mapState;
}

async function wireDashboardBaseMirrorMap(snapshot = DASHBOARD_EMPTY_BASE_OPERATIONS) {
  const root = document.querySelector("[data-dashboard-base-map]");
  if (!root) return;
  const requestSequence = ++dashboardBaseMapRequestSequence;
  const payload = normalizeDashboardBaseOperationsPayload(snapshot);
  updateDashboardBaseSummaryDom(payload.summary);
  if (!payload.bases.length) {
    root.setAttribute("aria-busy", "false");
    dashboardBaseMapStatus("Nenhuma base real dispon\u00edvel para o mapa", "empty");
    return;
  }
  dashboardBaseMapStatus("Carregando mapa de Gest\u00e3o de Bases...", "loading");
  try {
    await loadDashboardLeaflet();
    if (requestSequence !== dashboardBaseMapRequestSequence || !document.contains(root)) return;
    const mapState = initializeDashboardBaseMap(root, payload);
    root.setAttribute("aria-busy", "false");
    startDashboardBaseMapRotation(mapState);
    dashboardBaseMapStatus("Mapa atualizado via Gest\u00e3o de Bases", "ready");
  } catch (_error) {
    root.setAttribute("aria-busy", "false");
    dashboardBaseMapStatus("Mapa indispon\u00edvel", "error");
  }
}

function renderBaseManagementCard(snapshotInput, cardState = "success") {
  const snapshot = normalizeDashboardBaseOperationsPayload(snapshotInput);
  const bases = Array.isArray(snapshot.bases) ? snapshot.bases : [];
  const summary = snapshot.summary && typeof snapshot.summary === "object" ? snapshot.summary : {};
  const stateName = dashboardUpperCardState(cardState, bases.length === 0);
  const bodyMarkup = () => `
    <div class="dashboard-base-card-body">
      <div class="dashboard-base-map-stage" data-dashboard-base-map-stage>
        <div
          id="dashboardBaseMirrorMap"
          class="dashboard-base-map bases-map"
          data-dashboard-base-map
          role="region"
          tabindex="0"
          aria-busy="true"
          aria-label="Mapa operacional espelhado da Gest\u00e3o de Bases"
        ></div>
        <div class="dashboard-base-map-status" data-dashboard-base-map-status data-state="loading">
          Carregando mapa de Gest\u00e3o de Bases...
        </div>
      </div>
      <div class="dashboard-base-summary">
        <span class="dashboard-base-summary-item">
          <span>${dashboardTopIconMarkup("users")}</span>
          <strong data-dashboard-base-summary-value="basesActive">${asDashboardNumber(summary.basesActive)}</strong>
          <small>Bases ativas</small>
        </span>
        <span class="dashboard-base-summary-item">
          <span>${dashboardTopIconMarkup("users")}</span>
          <strong data-dashboard-base-summary-value="crew">${asDashboardNumber(summary.crew)}</strong>
          <small>Tripulantes</small>
        </span>
        <span class="dashboard-base-summary-item">
          <span>${dashboardTopIconMarkup("bell")}</span>
          <strong data-dashboard-base-summary-value="alerts">${asDashboardNumber(summary.alerts)}</strong>
          <small>Alertas</small>
        </span>
        <span class="dashboard-base-summary-item dashboard-base-summary-item--critical">
          <span>${dashboardTopIconMarkup("alert")}</span>
          <strong data-dashboard-base-summary-value="restrictions">${asDashboardNumber(summary.restrictions)}</strong>
          <small>Restri\u00e7\u00e3o</small>
        </span>
      </div>
    </div>
  `;

  return `
    <article class="dashboard-upper-card dashboard-upper-card--base-management ui-surface ui-card" data-dashboard-upper-card="base-management" data-dashboard-upper-card-state="${stateName}">
      ${renderDashboardUpperCardHeader("Gest\u00e3o de Base", "Mapa operacional das bases e tripulantes", {
        infoLabel: "Distribui\u00e7\u00e3o operacional das bases monitoradas",
        actionHref: BACKEND_LINKS.bases,
        actionLabel: "Abrir gest\u00e3o",
      })}
      ${
        stateName === "loading"
          ? renderDashboardUpperLoadingSkeleton(5)
          : stateName === "error"
            ? renderDashboardUpperCardState("N\u00e3o foi poss\u00edvel carregar os indicadores.", "A leitura das bases permanece dispon\u00edvel para nova tentativa.", "error")
            : stateName === "empty"
              ? renderDashboardUpperCardState("Nenhuma base real dispon\u00edvel.", "O mapa ser\u00e1 exibido assim que a Gest\u00e3o de Bases retornar registros com coordenadas.", "empty")
              : bodyMarkup()
      }
    </article>
  `;
}

function renderCriticalQualificationsCard(itemsInput, cardState = "success") {
  const items = Array.isArray(itemsInput) ? [...itemsInput] : [];
  const sortedItems = items.sort((left, right) => {
    const severityDelta = DASHBOARD_UPPER_SEVERITY_ORDER[dashboardUpperSeverity(left.severity)] - DASHBOARD_UPPER_SEVERITY_ORDER[dashboardUpperSeverity(right.severity)];
    return severityDelta || asDashboardNumber(right.affected) - asDashboardNumber(left.affected);
  });
  const maxAffected = Math.max(1, ...sortedItems.map((item) => asDashboardNumber(item.affected)));
  const stateName = dashboardUpperCardState(cardState, sortedItems.length === 0);
  const bodyMarkup = () => `
    <div class="dashboard-qualification-list">
      ${sortedItems
        .map((item) => {
          const tone = dashboardUpperSeverity(item.severity);
          const affected = asDashboardNumber(item.affected);
          const riskValue = Math.max(12, dashboardPercent(affected, maxAffected));
          return `
            <article class="dashboard-qualification-item dashboard-qualification-item--${tone}">
              <span class="dashboard-qualification-icon">${dashboardTopIconMarkup(tone === "normal" ? "info" : "alert")}</span>
              <div class="dashboard-qualification-main">
                <strong title="${escapeAttr(item.label || "Habilita\u00e7\u00e3o")}">${escapeHtml(item.label || "Habilita\u00e7\u00e3o")}</strong>
                <small>${escapeHtml(item.helper || "Sem detalhe adicional")}</small>
              </div>
              <div class="dashboard-qualification-risk">
                <strong>${affected}</strong>
                ${renderDashboardSeverityBadge(tone)}
                ${renderDashboardMiniProgress(riskValue, tone)}
              </div>
            </article>
          `;
        })
        .join("")}
    </div>
  `;

  return `
    <article class="dashboard-upper-card dashboard-upper-card--qualifications ui-surface ui-card" data-dashboard-upper-card="critical-qualifications" data-dashboard-upper-card-state="${stateName}">
      ${renderDashboardUpperCardHeader("Habilita\u00e7\u00f5es Cr\u00edticas", "Documentos e habilita\u00e7\u00f5es com maior risco", {
        infoLabel: "Habilita\u00e7\u00f5es e documentos ordenados por risco operacional",
        actionHref: buildHashHref("#/treinamentos", { risco: "habilitacoes" }),
        actionLabel: "Ver todas",
      })}
      ${
        stateName === "loading"
          ? renderDashboardUpperLoadingSkeleton(4)
          : stateName === "error"
            ? renderDashboardUpperCardState("N\u00e3o foi poss\u00edvel carregar os indicadores.", "A lista de habilita\u00e7\u00f5es continuar\u00e1 isolada dos demais cards.", "error")
            : stateName === "empty"
              ? renderDashboardUpperCardState("Nenhum vencimento cr\u00edtico encontrado.", "Nenhuma habilita\u00e7\u00e3o exige a\u00e7\u00e3o imediata.", "empty")
              : bodyMarkup()
      }
    </article>
  `;
}

function renderDashboardUpperSection(options = {}) {
  const sectionState = normalizeDashboardUpperCardState(options.state);
  const data = normalizeDashboardUpperSectionData(options.data || DASHBOARD_UPPER_SECTION_EMPTY);
  const cardStatesInput = options.cardStates && typeof options.cardStates === "object" ? options.cardStates : {};
  const inheritedState = sectionState === "success" ? "success" : sectionState;
  const cardStates = {
    licenseSummary: normalizeDashboardUpperCardState(cardStatesInput.licenseSummary || inheritedState),
    baseOperations: normalizeDashboardUpperCardState(cardStatesInput.baseOperations || inheritedState),
    criticalQualifications: normalizeDashboardUpperCardState(cardStatesInput.criticalQualifications || inheritedState),
  };

  return `
    <section class="dashboard-upper-section dashboard-upper-section--${sectionState}" data-dashboard-zone="upper-operational-diagnostics" aria-label="Diagn\u00f3stico operacional de vencimentos">
      <div class="dashboard-upper-grid">
        ${renderLicenseExpirationCard(data.licenseSummary, cardStates.licenseSummary)}
        ${renderBaseManagementCard(data.baseOperations, cardStates.baseOperations)}
        ${renderCriticalQualificationsCard(data.criticalQualifications, cardStates.criticalQualifications)}
      </div>
    </section>
  `;
}

function normalizeDashboardLowerSectionData(data = DASHBOARD_LOWER_SECTION_EMPTY) {
  const source = data && typeof data === "object" ? data : DASHBOARD_LOWER_SECTION_EMPTY;
  return {
    weatherByBase: Array.isArray(source.weatherByBase) ? source.weatherByBase : [],
    weatherByBaseMeta: source.weatherByBaseMeta && typeof source.weatherByBaseMeta === "object" ? source.weatherByBaseMeta : {},
    relevantNotams: Array.isArray(source.relevantNotams) ? source.relevantNotams : [],
    relevantNotamsMeta: source.relevantNotamsMeta && typeof source.relevantNotamsMeta === "object" ? source.relevantNotamsMeta : {},
    quickActions: Array.isArray(source.quickActions) ? source.quickActions : [],
  };
}

function dashboardWeatherSeverity(value) {
  const normalized = String(value || "unknown").trim().toLowerCase();
  return ["normal", "attention", "critical", "unknown"].includes(normalized) ? normalized : "unknown";
}

function dashboardNotamSeverity(value) {
  const normalized = String(value || "info").trim().toLowerCase();
  return ["critical", "warning", "attention", "info"].includes(normalized) ? normalized : "info";
}

function renderDashboardLowerCardHeader(title, subtitle, options = {}) {
  const actionHref = String(options.actionHref || "").trim();
  const actionLabel = String(options.actionLabel || "").trim();
  return `
    <header class="dashboard-lower-card-header">
      <div>
        <h3>${escapeHtml(title)} ${options.info === false ? "" : renderDashboardUpperInfoIcon(options.infoLabel || title)}</h3>
        <p>${escapeHtml(subtitle)}</p>
      </div>
      ${
        actionHref && actionLabel
          ? `<a class="dashboard-lower-card-action" href="${escapeAttr(actionHref)}">${escapeHtml(actionLabel)} ${dashboardTopIconMarkup("chevronRight")}</a>`
          : ""
      }
    </header>
  `;
}

function dashboardLowerFallbackValue(value, suffix = "", fallback = "--") {
  if (value === null || value === undefined || value === "") return fallback;
  const normalized = Number(value);
  if (Number.isFinite(normalized)) return `${normalized}${suffix}`;
  return `${value}${suffix}`;
}

function renderWeatherConditionBadge(condition, severity) {
  const tone = dashboardWeatherSeverity(severity);
  const label = String(condition || "UNKNOWN").trim().toUpperCase() || "UNKNOWN";
  return `
    <span class="dashboard-weather-condition dashboard-weather-condition--${tone}">
      <span aria-hidden="true"></span>
      ${escapeHtml(label)}
    </span>
  `;
}

function renderDashboardLowerCollectionStateBanner(title, detail = "", type = "empty") {
  const normalizedType = ["empty", "error"].includes(type) ? type : "empty";
  return `
    <div class="dashboard-lower-collection-state dashboard-lower-collection-state--${normalizedType}" role="${normalizedType === "error" ? "alert" : "status"}">
      <strong>${escapeHtml(title)}</strong>
      ${detail ? `<span>${escapeHtml(detail)}</span>` : ""}
    </div>
  `;
}

function renderBaseWeatherCard(itemsInput, cardState = "success", collectionMeta = {}) {
  const items = Array.isArray(itemsInput) ? itemsInput : [];
  const stateName = dashboardUpperCardState(cardState, items.length === 0);
  const hasRows = items.length > 0;
  const safeMessage = String(collectionMeta?.message || "Falha ao carregar meteorologia por base.").trim();
  const statusBanner = stateName === "error"
    ? renderDashboardLowerCollectionStateBanner("Falha ao carregar meteorologia", safeMessage, "error")
    : "";
  const bodyMarkup = () => `
    <div class="dashboard-base-weather-table" role="table" aria-label="Meteorologia por base">
      <div class="dashboard-base-weather-row dashboard-base-weather-row--head" role="row">
        <span role="columnheader">Base</span>
        <span role="columnheader">Condi\u00e7\u00e3o</span>
        <span role="columnheader">Temp.</span>
        <span role="columnheader">Vento</span>
        <span role="columnheader">Cobertura</span>
        <span role="columnheader">Visibilidade</span>
      </div>
      ${items
        .map((item) => {
          const tone = dashboardWeatherSeverity(item.severity);
          const baseLabel = `${String(item.icao || "----").toUpperCase()} - ${item.city || "Base"}`;
          return `
            <article class="dashboard-base-weather-row dashboard-base-weather-row--${tone}" role="row">
              <span class="dashboard-base-weather-cell dashboard-base-weather-cell--base" role="cell" data-label="Base">
                <span class="dashboard-lower-status-dot" aria-hidden="true"></span>
                <strong title="${escapeAttr(baseLabel)}">${escapeHtml(baseLabel)}</strong>
              </span>
              <span class="dashboard-base-weather-cell" role="cell" data-label="Condi\u00e7\u00e3o">${renderWeatherConditionBadge(item.condition, tone)}</span>
              <span class="dashboard-base-weather-cell" role="cell" data-label="Temp.">${escapeHtml(dashboardLowerFallbackValue(item.temperatureC, "\u00b0C"))}</span>
              <span class="dashboard-base-weather-cell" role="cell" data-label="Vento">${escapeHtml(dashboardLowerFallbackValue(item.windKt, " kt"))}</span>
              <span class="dashboard-base-weather-cell" role="cell" data-label="Cobertura">${escapeHtml(item.coverage || "Indisp.")}</span>
              <span class="dashboard-base-weather-cell" role="cell" data-label="Visibilidade">${escapeHtml(dashboardLowerFallbackValue(item.visibilityKm, " km"))}</span>
            </article>
          `;
        })
        .join("")}
    </div>
  `;

  return `
    <article class="dashboard-lower-card dashboard-lower-card--weather ui-surface ui-card" data-dashboard-lower-card="weather-by-base" data-dashboard-lower-card-state="${stateName}">
      ${renderDashboardLowerCardHeader("Meteorologia por Base", "Condi\u00e7\u00f5es atuais", {
        actionHref: buildHashHref("#/dashboard-operacional", { painel: "meteorologia" }),
        actionLabel: "Ver todas",
        infoLabel: "Resumo sint\u00e9tico das bases principais",
      })}
      ${
        stateName === "loading"
          ? renderDashboardUpperLoadingSkeleton(4)
          : stateName === "error"
            ? hasRows
              ? `${statusBanner}${bodyMarkup()}`
              : renderDashboardUpperCardState("N\u00e3o foi poss\u00edvel carregar meteorologia.", safeMessage || "Os demais indicadores permanecem dispon\u00edveis.", "error")
            : stateName === "empty"
              ? renderDashboardUpperCardState("Nenhuma base monitorada.", "A lista ser\u00e1 preenchida quando houver bases habilitadas.", "empty")
              : bodyMarkup()
      }
    </article>
  `;
}

function renderNotamSeverityBadge(code, severity) {
  const tone = dashboardNotamSeverity(severity);
  return `<span class="dashboard-notam-code dashboard-notam-code--${tone}" aria-label="Severidade ${escapeAttr(code || "")}">${escapeHtml(code || "-")}</span>`;
}

function renderRelevantNotamsCard(itemsInput, cardState = "success", collectionMeta = {}) {
  const items = Array.isArray(itemsInput) ? itemsInput : [];
  const stateName = dashboardUpperCardState(cardState, items.length === 0);
  const notamsStatus = String(collectionMeta?.status || "").trim().toLowerCase();
  const notamsUnavailable = ["error", "unavailable"].includes(notamsStatus) || stateName === "error";
  const notamsMessage = String(collectionMeta?.message || "Integra\u00e7\u00e3o real de NOTAM indispon\u00edvel no momento.").trim();
  const bodyMarkup = () => `
    <div class="dashboard-notam-list" aria-label="NOTAMs relevantes">
      ${items
        .map((item) => {
          const tone = dashboardNotamSeverity(item.severity);
          return `
            <article class="dashboard-notam-item dashboard-notam-item--${tone}">
              ${renderNotamSeverityBadge(item.code, tone)}
              <span class="dashboard-notam-main">
                <strong>${escapeHtml(item.icao || "----")}</strong>
                <small title="${escapeAttr(item.description || "")}">${escapeHtml(item.description || "Sem descri\u00e7\u00e3o operacional")}</small>
              </span>
              <span class="dashboard-notam-meta">
                <strong>${escapeHtml(item.updatedAt || "--")}</strong>
                <small>${escapeHtml(item.validUntil || "Validade indispon\u00edvel")}</small>
              </span>
            </article>
          `;
        })
        .join("")}
    </div>
  `;

  return `
    <article class="dashboard-lower-card dashboard-lower-card--notams ui-surface ui-card" data-dashboard-lower-card="relevant-notams" data-dashboard-lower-card-state="${stateName}">
      ${renderDashboardLowerCardHeader("NOTAMs Relevantes", "\u00daltimas atualiza\u00e7\u00f5es", {
        actionHref: buildHashHref("#/dashboard-operacional", { painel: "notams" }),
        actionLabel: "Ver todos",
        info: false,
      })}
      ${
        stateName === "loading"
          ? renderDashboardUpperLoadingSkeleton(4)
          : stateName === "error"
            ? renderDashboardUpperCardState(
              notamsUnavailable ? "NOTAMs indispon\u00edveis no momento." : "N\u00e3o foi poss\u00edvel carregar NOTAMs.",
              notamsMessage,
              "error",
            )
            : stateName === "empty"
              ? renderDashboardUpperCardState("Nenhum NOTAM relevante no momento.", "Sem restri\u00e7\u00f5es priorit\u00e1rias neste recorte.", "empty")
              : bodyMarkup()
      }
    </article>
  `;
}

function renderQuickActionsCard(itemsInput, cardState = "success") {
  const items = Array.isArray(itemsInput) ? itemsInput : [];
  const stateName = dashboardUpperCardState(cardState, items.length === 0);
  const bodyMarkup = () => `
    <div class="dashboard-quick-action-grid" aria-label="A\u00e7\u00f5es r\u00e1pidas operacionais">
      ${items
        .map((action) => {
          const enabled = action.enabled !== false;
          const iconMarkup = dashboardTopIconMarkup(action.icon) || dashboardTopIconMarkup("info");
          const content = `
            <span class="dashboard-quick-action-icon" aria-hidden="true">${iconMarkup}</span>
            <span>${escapeHtml(action.label || "A\u00e7\u00e3o")}</span>
          `;
          if (!enabled) {
      return `
        <span class="dashboard-quick-action dashboard-quick-action--disabled" role="button" aria-disabled="true" data-future-intent="${escapeAttr(action.futureIntent || action.id || "")}" title="Atalho reservado para uma inten&ccedil;&atilde;o futura sem rota registrada">
                ${content}
              </span>
            `;
          }
          return `
            <a class="dashboard-quick-action" href="${escapeAttr(action.href || "#/dashboard-operacional")}">
              ${content}
            </a>
          `;
        })
        .join("")}
    </div>
  `;

  return `
    <article class="dashboard-lower-card dashboard-lower-card--quick-actions ui-surface ui-card" data-dashboard-lower-card="quick-actions" data-dashboard-lower-card-state="${stateName}">
      ${renderDashboardLowerCardHeader("A\u00e7\u00f5es R\u00e1pidas", "Atalhos operacionais", {
        infoLabel: "Acessos frequentes para a rotina operacional",
      })}
      ${
        stateName === "loading"
          ? renderDashboardUpperLoadingSkeleton(4)
          : stateName === "error"
            ? renderDashboardUpperCardState("N\u00e3o foi poss\u00edvel carregar atalhos.", "Tente novamente na pr\u00f3xima atualiza\u00e7\u00e3o.", "error")
            : stateName === "empty"
              ? renderDashboardUpperCardState("Nenhuma a\u00e7\u00e3o dispon\u00edvel para seu perfil.", "Os atalhos respeitar\u00e3o as permiss\u00f5es configuradas.", "empty")
              : bodyMarkup()
      }
    </article>
  `;
}

function renderDashboardLowerSection(options = {}) {
  const sectionState = normalizeDashboardUpperCardState(options.state);
  const data = normalizeDashboardLowerSectionData(options.data || DASHBOARD_LOWER_SECTION_EMPTY);
  const cardStatesInput = options.cardStates && typeof options.cardStates === "object" ? options.cardStates : {};
  const inheritedState = sectionState === "success" ? "success" : sectionState;
  const cardStates = {
    weatherByBase: normalizeDashboardUpperCardState(cardStatesInput.weatherByBase || inheritedState),
    relevantNotams: normalizeDashboardUpperCardState(cardStatesInput.relevantNotams || inheritedState),
    quickActions: normalizeDashboardUpperCardState(cardStatesInput.quickActions || inheritedState),
  };

  return `
    <section class="dashboard-lower-section dashboard-lower-section--${sectionState}" data-dashboard-zone="lower-operational-context" aria-label="Contexto operacional e a\u00e7\u00f5es r\u00e1pidas">
      <div class="dashboard-lower-grid">
        ${renderBaseWeatherCard(data.weatherByBase, cardStates.weatherByBase, data.weatherByBaseMeta)}
        ${renderRelevantNotamsCard(data.relevantNotams, cardStates.relevantNotams, data.relevantNotamsMeta)}
        ${renderQuickActionsCard(data.quickActions, cardStates.quickActions)}
      </div>
    </section>
  `;
}

function renderDashboardOperationalTicker(tickerInput = DASHBOARD_OPERATIONAL_ALERTS_EMPTY, cardState = "success") {
  const ticker = tickerInput && typeof tickerInput === "object" ? tickerInput : DASHBOARD_OPERATIONAL_ALERTS_EMPTY;
  const items = Array.isArray(ticker.items) ? ticker.items : [];
  const stateName = dashboardUpperCardState(cardState, items.length === 0);
  const message = String(ticker.message || "Sem alertas operacionais no momento.").trim();
  const fallbackLabel = stateName === "loading" ? "Carregando" : stateName === "error" ? "Dados indispon\u00edveis" : "Operacional";
  const fallbackMessage = stateName === "loading"
    ? "Carregando alertas operacionais."
    : stateName === "error"
      ? "Alertas operacionais indispon\u00edveis."
      : message;
  const renderedItems = stateName === "success"
    ? [...items, ...items].map((item) => {
      const tone = dashboardNotamSeverity(item.severity);
      return `
        <span class="dashboard-operational-ticker-item dashboard-operational-ticker-item--${tone}">
          <strong>${escapeHtml(item.label || "Operacional")}</strong>
          <span>${escapeHtml(item.message || "Alerta operacional sem detalhe.")}</span>
        </span>
      `;
    }).join("")
    : `
      <span class="dashboard-operational-ticker-item dashboard-operational-ticker-item--${stateName === "error" ? "warning" : "info"}">
        <strong>${fallbackLabel}</strong>
        <span>${escapeHtml(fallbackMessage)}</span>
      </span>
    `;

  return `
    <footer class="dashboard-operational-ticker dashboard-operational-ticker--${stateName}" data-dashboard-zone="operational-cnn-ticker" data-dashboard-cnn-ticker data-dashboard-ticker-state="${stateName}" aria-label="Alertas operacionais rotativos">
      <span class="dashboard-operational-ticker-label">Operacional</span>
      <div class="dashboard-operational-ticker-viewport">
        <div class="dashboard-operational-ticker-track">
          ${renderedItems}
        </div>
      </div>
    </footer>
  `;
}

function renderDashboardStatCards(alerts) {
  const summary = dashboardSummarySnapshot || {};
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
  const alertCards = [
    {
      ...cards[0],
      label: "Vencem hoje",
      value: alerts.vencem_hoje ?? alerts.vencidos,
      support: "A\u00e7\u00e3o imediata",
      icon: "alert",
      tone: "critical",
    },
    {
      ...cards[1],
      label: "Vencem em at\u00e9 7 dias",
      support: "Aten\u00e7\u00e3o necess\u00e1ria",
      icon: "timer",
      tone: "warning",
    },
    {
      ...cards[2],
      label: "Vencem em at\u00e9 30 dias",
      support: "Planejamento",
      icon: "month",
      tone: "stable",
    },
    {
      ...cards[3],
      label: "Alertas operacionais",
      value: alerts.operacionais ?? summary.sem_informacao ?? 0,
      support: "Ver detalhes",
      icon: "info",
      tone: "neutral",
    },
  ];
  return `
    <section class="dashboard-stat-grid ui-card-grid ui-card-equal-height dashboard-kpi-priority-row" data-dashboard-zone="kpi-priority" data-dashboard-alert-surface="dashboard-operational-alert-grid" aria-label="Alertas operacionais">
      ${alertCards
        .map(
          (card) => `
            <a class="dashboard-kpi-card dashboard-alert-card dashboard-kpi-card--${card.tone} ui-surface ui-card" data-dashboard-priority="${card.tone === "critical" ? "p0" : card.tone === "warning" ? "p1" : "p2"}" href="${escapeAttr(card.href)}">
              <span class="dashboard-alert-icon" aria-hidden="true">${dashboardTopIconMarkup(card.icon)}</span>
              <span class="dashboard-alert-copy">
                <span class="dashboard-alert-label">${escapeHtml(card.label)}</span>
                <strong class="dashboard-kpi-value">${asDashboardNumber(card.value)}</strong>
                <span class="dashboard-kpi-action">${escapeHtml(card.support)}</span>
              </span>
            </a>
          `,
        )
        .join("")}
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

function dashboardOperationalShellClass(options = {}) {
  return [
    "dashboard-page-shell",
    "dashboard-operational-page-shell",
    options.tv ? "dashboard-operational-tv-shell" : "",
    "priority-page-surface",
    "ui-page-shell",
    "ui-stack",
    "dashboard-reference-target",
    "dashboard-responsive-surface",
  ]
    .filter(Boolean)
    .join(" ");
}

function renderDashboardLoadingMarkup(capabilities, options = {}) {
  return `
    <div class="${escapeAttr(dashboardOperationalShellClass(options))}" data-dashboard-layout="responsive-operational">
    <div class="dashboard-top-cluster dashboard-fold-priority" data-dashboard-zone="above-fold">
      ${renderDashboardHeader(capabilities)}

      ${renderDashboardPriorityStrip()}

      <section class="dashboard-stat-grid ui-card-grid ui-card-equal-height dashboard-kpi-priority-row" data-dashboard-zone="kpi-priority" data-dashboard-alert-surface="dashboard-operational-alert-grid" aria-label="Alertas operacionais">
        <div class="dashboard-kpi-card dashboard-kpi-card--critical dashboard-kpi-card--loading ui-surface ui-card" data-dashboard-priority="p0">
          <span class="dashboard-alert-icon" aria-hidden="true">${dashboardTopIconMarkup("alert")}</span>
          <span class="dashboard-alert-copy">
            <span class="dashboard-alert-label">Vencem hoje</span>
            <strong class="dashboard-kpi-value">...</strong>
            <span class="dashboard-kpi-action">Carregando</span>
          </span>
        </div>
        <div class="dashboard-kpi-card dashboard-kpi-card--warning dashboard-kpi-card--loading ui-surface ui-card" data-dashboard-priority="p1">
          <span class="dashboard-alert-icon" aria-hidden="true">${dashboardTopIconMarkup("timer")}</span>
          <span class="dashboard-alert-copy">
            <span class="dashboard-alert-label">Vencem em at&eacute; 7 dias</span>
            <strong class="dashboard-kpi-value">...</strong>
            <span class="dashboard-kpi-action">Carregando</span>
          </span>
        </div>
        <div class="dashboard-kpi-card dashboard-kpi-card--stable dashboard-kpi-card--loading ui-surface ui-card" data-dashboard-priority="p2">
          <span class="dashboard-alert-icon" aria-hidden="true">${dashboardTopIconMarkup("month")}</span>
          <span class="dashboard-alert-copy">
            <span class="dashboard-alert-label">Vencem em at&eacute; 30 dias</span>
            <strong class="dashboard-kpi-value">...</strong>
            <span class="dashboard-kpi-action">Carregando</span>
          </span>
        </div>
        <div class="dashboard-kpi-card dashboard-kpi-card--neutral dashboard-kpi-card--loading ui-surface ui-card" data-dashboard-priority="p2">
          <span class="dashboard-alert-icon" aria-hidden="true">${dashboardTopIconMarkup("info")}</span>
          <span class="dashboard-alert-copy">
            <span class="dashboard-alert-label">Alertas operacionais</span>
            <strong class="dashboard-kpi-value">...</strong>
            <span class="dashboard-kpi-action">Carregando</span>
          </span>
        </div>
      </section>
    </div>
    ${renderDashboardUpperSection({ state: "loading" })}
    ${renderDashboardLowerSection({ state: "loading" })}
    ${renderDashboardOperationalTicker(DASHBOARD_OPERATIONAL_ALERTS_EMPTY, "loading")}
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

export async function renderDashboardPage(options = {}) {
  try {
    stopDashboardWeatherRotation();
    stopDashboardRealtimeClock();
    destroyDashboardBaseMirrorMap();
    const capabilities = capabilitySet();
    capabilities.dashboardWeather = dashboardWeatherFallback("loading");
    dashboardWeatherSnapshot = capabilities.dashboardWeather;
    renderShell(renderDashboardLoadingMarkup(capabilities, options), "Dashboard Operacional");
    startDashboardRealtimeClock();
    wireDashboardFullscreenControl();
    const [
      summaryResultTv,
      weatherResultTv,
      criticalResultTv,
      basesResultTv,
      weatherByBaseResultTv,
      notamsResultTv,
      operationalAlertsResultTv,
    ] = await Promise.allSettled([
      api("/api/v1/dashboard/summary"),
      api(dashboardWeatherEndpoint(DASHBOARD_WEATHER_ROTATION_BASES[0])),
      api("/api/v1/dashboard/critical-trainings?limit=20"),
      api(DASHBOARD_BASES_MAP_ENDPOINT, { timeoutMs: 15000 }),
      api(DASHBOARD_WEATHER_BY_BASE_ENDPOINT, { timeoutMs: 20000 }),
      api(DASHBOARD_RELEVANT_NOTAMS_ENDPOINT, { timeoutMs: 15000 }),
      api(DASHBOARD_OPERATIONAL_ALERTS_ENDPOINT, { timeoutMs: 15000 }),
    ]);
    const summaryBlockTv = dashboardBlockFromResult(summaryResultTv, "Resumo", adaptDashboardSummary, { totals: {}, alerts: {}, summary: {} });
    const weatherBlockTv = dashboardBlockFromResult(weatherResultTv, "Meteorologia", adaptDashboardWeather, dashboardWeatherFallback("error"));
    const criticalBlockTv = dashboardBlockFromResult(criticalResultTv, "Habilita\u00e7\u00f5es cr\u00edticas", adaptDashboardCriticalTrainings, []);
    const basesBlockTv = dashboardBlockFromResult(basesResultTv, "Gest\u00e3o de Bases", adaptDashboardBaseOperations, DASHBOARD_EMPTY_BASE_OPERATIONS);
    const weatherByBaseBlockTv = dashboardBlockFromResult(weatherByBaseResultTv, "Meteorologia por Base", adaptDashboardWeatherByBase, DASHBOARD_WEATHER_BY_BASE_EMPTY);
    const notamsBlockTv = dashboardBlockFromResult(notamsResultTv, "NOTAMs", adaptDashboardRelevantNotams, DASHBOARD_RELEVANT_NOTAMS_EMPTY);
    const operationalAlertsBlockTv = dashboardBlockFromResult(
      operationalAlertsResultTv,
      "Alertas operacionais",
      adaptDashboardOperationalAlerts,
      DASHBOARD_OPERATIONAL_ALERTS_EMPTY,
    );
    const dashboardAlertsTv = summaryBlockTv.data.alerts;
    dashboardSummarySnapshot = summaryBlockTv.data.summary;
    capabilities.dashboardWeather = weatherBlockTv.data;
    dashboardWeatherSnapshot = weatherBlockTv.data;
    const upperRuntimeData = buildDashboardUpperRuntimeData({
      summaryData: summaryBlockTv.data,
      baseOperations: basesBlockTv.data,
      criticalTrainings: criticalBlockTv.data,
    });
    const lowerRuntimeData = buildDashboardLowerRuntimeData({
      weatherByBase: weatherByBaseBlockTv.data,
      relevantNotams: notamsBlockTv.data,
    });
    const upperCardStates = {
      licenseSummary: dashboardCardStateFromBlock(summaryBlockTv, asDashboardNumber(upperRuntimeData.licenseSummary.total) <= 0),
      baseOperations: dashboardCardStateFromBlock(basesBlockTv, !upperRuntimeData.baseOperations.bases?.length),
      criticalQualifications: dashboardCardStateFromBlock(criticalBlockTv, !upperRuntimeData.criticalQualifications.length),
    };
    const lowerCardStates = {
      weatherByBase: dashboardOperationalCollectionCardState(weatherByBaseBlockTv, weatherByBaseBlockTv.data, !lowerRuntimeData.weatherByBase.length),
      relevantNotams: dashboardOperationalCollectionCardState(notamsBlockTv, notamsBlockTv.data, !lowerRuntimeData.relevantNotams.length),
      quickActions: lowerRuntimeData.quickActions.length ? "success" : "empty",
    };
    const tickerState = dashboardOperationalCollectionCardState(
      operationalAlertsBlockTv,
      operationalAlertsBlockTv.data,
      !operationalAlertsBlockTv.data.items.length,
    );
    renderShell(
      `
        <div class="${escapeAttr(dashboardOperationalShellClass(options))}" data-dashboard-layout="responsive-operational">
          <div class="dashboard-top-cluster dashboard-fold-priority" data-dashboard-zone="above-fold">
            ${renderDashboardHeader(capabilities)}
            ${renderDashboardPriorityStrip()}
            ${renderDashboardPartialFeedback([
              summaryBlockTv.error,
              weatherBlockTv.error,
              criticalBlockTv.error,
              basesBlockTv.error,
              weatherByBaseBlockTv.error,
              notamsBlockTv.error,
              operationalAlertsBlockTv.error,
            ])}
            ${renderDashboardStatCards(dashboardAlertsTv)}
          </div>
          ${renderDashboardUpperSection({ data: upperRuntimeData, cardStates: upperCardStates })}
          ${renderDashboardLowerSection({ data: lowerRuntimeData, cardStates: lowerCardStates })}
          ${renderDashboardOperationalTicker(operationalAlertsBlockTv.data, tickerState)}
        </div>
      `,
      "Dashboard Operacional",
    );
    startDashboardRealtimeClock();
    wireDashboardFullscreenControl();
    startDashboardWeatherRotation();
    if (!basesBlockTv.error && upperRuntimeData.baseOperations.bases?.length) {
      void wireDashboardBaseMirrorMap(upperRuntimeData.baseOperations);
    }
    return;
  } catch (error) {
    stopDashboardWeatherRotation();
    stopDashboardRealtimeClock();
    destroyDashboardBaseMirrorMap();
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
    `, "Dashboard Operacional");
  }
}


