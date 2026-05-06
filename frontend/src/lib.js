import { state } from "./state/app-state.js";
import { normalizeFlashKind } from "./state/flash-state.js";

export {
  config,
  finishFrontendPhase,
  resetFrontendPerf,
  startFrontendPhase,
  state,
} from "./state/app-state.js";
export {
  consumeFlash,
  normalizeFlashKind,
  showFlash,
} from "./state/flash-state.js";
export {
  DEFAULT_AUTHENTICATED_ROUTE,
  LOGIN_ROUTE,
  consumeReturnRoute,
  currentHashRoute,
  isLoginRoute,
  isRestorableRoute,
  normalizeHashRoute,
  peekLastSuccessfulRoute,
  rememberCurrentRouteForLogin,
  rememberLastSuccessfulRoute,
  rememberReturnRoute,
  routeFromCurrentPathname,
  routeKeyFromHash,
} from "./state/navigation-state.js";
export { api } from "./services/api-client.js";
export {
  clearCsrfToken,
  getCsrfToken,
  setCsrfToken,
} from "./services/csrf-service.js";
export { refreshSession } from "./services/session-service.js";
export {
  clientCorrelationId,
  createTraceId,
  forensicAssetSnapshot,
  forensicTrace,
  installForensicRuntimeHooks,
} from "./services/trace-service.js";

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
  return `<div class="flash ${normalizedKind} ui-alert" data-kind="${escapeAttr(normalizedKind)}" role="${role}" aria-live="${live}">${escapeHtml(message)}</div>`;
}

export function renderInlineFeedback(target, message, kind = "error") {
  if (!target) return;
  target.innerHTML = feedbackMarkup(message, kind);
}

const UI_STATE_VALUES = new Set(["loading", "empty", "error", "no-permission", "no-results", "info", "warning", "success"]);
const UI_STATE_ALIASES = {
  denied: "no-permission",
  forbidden: "no-permission",
  partial: "error",
  "partial-unavailable": "error",
  "structural-empty": "empty",
};

function normalizeUiStateType(type = "empty") {
  const normalized = String(type || "empty")
    .trim()
    .toLowerCase()
    .replace(/_/g, "-");
  const aliased = UI_STATE_ALIASES[normalized] || normalized;
  return UI_STATE_VALUES.has(aliased) ? aliased : "empty";
}

function responsiveStateAccessibility(type) {
  const normalized = normalizeUiStateType(type);
  if (normalized === "error" || normalized === "warning" || normalized === "no-permission") {
    return { role: "alert", live: "assertive" };
  }
  return { role: "status", live: "polite" };
}

export function responsiveStateContentMarkup({
  title = "",
  detail = "",
  actionHref = "",
  actionLabel = "",
  actionId = "",
  actionClassName = "button-link secondary",
} = {}) {
  const actionAttrs = [
    actionId ? `id="${escapeAttr(actionId)}"` : "",
    `class="${escapeAttr(actionClassName)}"`,
    actionHref ? `href="${escapeAttr(actionHref)}"` : "",
    actionHref ? "" : 'type="button"',
  ].filter(Boolean).join(" ");
  const action = actionLabel
    ? actionHref
      ? `<a ${actionAttrs}>${escapeHtml(actionLabel)}</a>`
      : `<button ${actionAttrs}>${escapeHtml(actionLabel)}</button>`
    : "";
  return `
    ${title ? `<strong class="ui-state-title">${escapeHtml(title)}</strong>` : ""}
    ${detail ? `<span class="ui-state-detail">${escapeHtml(detail)}</span>` : ""}
    ${action ? `<div class="ui-state-actions">${action}</div>` : ""}
  `;
}

export function responsiveStateMarkup({
  title = "",
  detail = "",
  actionHref = "",
  actionLabel = "",
  actionId = "",
  type = "empty",
  className = "",
  compact = false,
  tag = "div",
} = {}) {
  const normalizedType = normalizeUiStateType(type);
  const { role, live } = responsiveStateAccessibility(normalizedType);
  const density = compact ? ' data-density="compact"' : "";
  const safeTag = ["div", "section", "article"].includes(tag) ? tag : "div";
  const classes = [className, "ui-state"].filter(Boolean).join(" ");
  return `
    <${safeTag} class="${escapeAttr(classes)}" data-state="${escapeAttr(normalizedType)}"${density} role="${role}" aria-live="${live}">
      ${responsiveStateContentMarkup({ title, detail, actionHref, actionLabel, actionId })}
    </${safeTag}>
  `;
}

export function responsiveAlertMarkup(message, kind = "info", className = "") {
  if (!message) return "";
  const normalizedKind = normalizeFlashKind(kind);
  const role = normalizedKind === "error" || normalizedKind === "warning" ? "alert" : "status";
  const live = role === "alert" ? "assertive" : "polite";
  const classes = ["flash", normalizedKind, className, "ui-alert"].filter(Boolean).join(" ");
  return `<div class="${escapeAttr(classes)}" data-kind="${escapeAttr(normalizedKind)}" role="${role}" aria-live="${live}">${escapeHtml(message)}</div>`;
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
    return '<div class="filters-state ui-filter-summary" data-filter-state="empty" data-filter-persistence="visual">Sem filtros ativos</div>';
  }
  return `
    <div class="filters-state ui-filter-summary" data-filter-state="active" data-filter-persistence="visual">
      <span>${activeEntries.length} filtro${activeEntries.length > 1 ? "s" : ""} ativo${activeEntries.length > 1 ? "s" : ""}</span>
      ${activeEntries
        .map(([key, value]) => `<span class="filters-state-chip ui-filter-chip">${escapeHtml(labels[key] || key)}: ${escapeHtml(value)}</span>`)
        .join("")}
    </div>
  `;
}

export function emptyTableRowMarkup(colspan, { title, detail = "", actionHref = "", actionLabel = "", type = "no-results" } = {}) {
  const normalizedType = normalizeUiStateType(type);
  const { role, live } = responsiveStateAccessibility(normalizedType);
  return `
    <tr class="operational-empty-row">
      <td colspan="${Number(colspan) || 1}" class="empty operational-empty ui-table-state ui-state" data-empty-type="${escapeAttr(type)}" data-state="${escapeAttr(normalizedType)}" role="${role}" aria-live="${live}">
        ${responsiveStateContentMarkup({
          title: title || "Nenhum registro encontrado.",
          detail,
          actionHref,
          actionLabel,
        })}
      </td>
    </tr>
  `;
}

const OVERLAY_FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled]):not([type='hidden'])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(", ");
const activeScrollLocks = new Set();

function syncDocumentScrollLockState() {
  const body = globalThis.document?.body;
  if (!body) return;
  const hasLocks = activeScrollLocks.size > 0;
  body.classList.toggle("ui-overlay-open", hasLocks);
  if (hasLocks) {
    body.dataset.scrollLockCount = String(activeScrollLocks.size);
  } else {
    delete body.dataset.scrollLockCount;
  }
}

export function setDocumentScrollLock(lockKey = "overlay", locked = true) {
  const key = String(lockKey || "overlay");
  if (locked) {
    activeScrollLocks.add(key);
  } else {
    activeScrollLocks.delete(key);
  }
  syncDocumentScrollLockState();
}

export function getFocusableElements(scope = document) {
  if (!scope?.querySelectorAll) return [];
  return Array.from(scope.querySelectorAll(OVERLAY_FOCUSABLE_SELECTOR)).filter((element) => {
    if (element.disabled || element.getAttribute("aria-hidden") === "true") return false;
    if (element.closest("[hidden], [aria-hidden='true']")) return false;
    return Boolean(element.offsetParent || element.getClientRects().length);
  });
}

export function trapFocusWithin(scope, event) {
  if (!scope || !event || event.key !== "Tab") return false;
  const focusable = getFocusableElements(scope);
  if (!focusable.length) return false;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
    return true;
  }
  if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
    return true;
  }
  return false;
}

function resolveOverlayElement(ref) {
  if (!ref) return null;
  if (typeof ref !== "string") return ref;
  return document.getElementById(ref) || document.querySelector(ref);
}

export function wireResponsiveOverlay({
  trigger = null,
  panel,
  backdrop = null,
  closeTriggers = [],
  initialFocus = null,
  returnFocus = true,
  modal = true,
  lockKey = "responsive-overlay",
  openClass = "open",
  hiddenWhenClosed = true,
  onOpen = null,
  onClose = null,
} = {}) {
  const triggerEl = resolveOverlayElement(trigger);
  const panelEl = resolveOverlayElement(panel);
  const backdropEl = resolveOverlayElement(backdrop);
  if (!panelEl) return null;
  let lastFocusedElement = null;
  let hasOpened = false;

  const closeEls = closeTriggers.flatMap((ref) => {
    if (typeof ref === "string") return Array.from(document.querySelectorAll(ref));
    const resolved = resolveOverlayElement(ref);
    return resolved ? [resolved] : [];
  });

  function isOpen() {
    return panelEl.dataset.overlayState === "open" || panelEl.classList.contains(openClass);
  }

  function syncOverlayState(open) {
    panelEl.classList.toggle(openClass, open);
    panelEl.dataset.overlayState = open ? "open" : "closed";
    panelEl.dataset.overlaySurface = panelEl.dataset.overlaySurface || (modal ? "modal" : "overlay");
    panelEl.setAttribute("aria-hidden", open ? "false" : "true");
    if (hiddenWhenClosed) {
      panelEl.hidden = !open;
    }
    if (modal) {
      panelEl.setAttribute("role", panelEl.getAttribute("role") || "dialog");
      if (open) {
        panelEl.setAttribute("aria-modal", "true");
      } else {
        panelEl.removeAttribute("aria-modal");
      }
    }
    if (backdropEl) {
      backdropEl.hidden = !open;
      backdropEl.classList.toggle("show", open);
      backdropEl.dataset.overlayState = open ? "open" : "closed";
      backdropEl.setAttribute("aria-hidden", "true");
    }
    setDocumentScrollLock(lockKey, open && modal);
    if (open) {
      hasOpened = true;
      lastFocusedElement = document.activeElement;
      const focusTarget = resolveOverlayElement(initialFocus) || getFocusableElements(panelEl)[0] || panelEl;
      requestAnimationFrame(() => focusTarget?.focus?.());
      onOpen?.();
    } else {
      onClose?.();
      if (returnFocus && hasOpened && lastFocusedElement && document.contains(lastFocusedElement)) {
        requestAnimationFrame(() => lastFocusedElement.focus?.());
      }
    }
  }

  triggerEl?.addEventListener("click", () => syncOverlayState(true));
  backdropEl?.addEventListener("click", () => syncOverlayState(false));
  closeEls.forEach((element) => element.addEventListener("click", () => syncOverlayState(false)));
  document.addEventListener("keydown", (event) => {
    if (!isOpen()) return;
    if (event.key === "Escape") {
      event.preventDefault();
      syncOverlayState(false);
      return;
    }
    if (modal) trapFocusWithin(panelEl, event);
  });

  syncOverlayState(isOpen());
  return {
    open: () => syncOverlayState(true),
    close: () => syncOverlayState(false),
    toggle: () => syncOverlayState(!isOpen()),
  };
}

function resolveResponsiveElement(ref, root = document) {
  if (!ref) return null;
  if (typeof ref !== "string") return ref;
  return root?.querySelector?.(ref) || document.getElementById(ref) || document.querySelector(ref);
}

function resolveResponsiveElements(ref, root = document) {
  if (!ref) return [];
  if (typeof ref === "string") {
    const scope = root?.querySelectorAll ? root : document;
    return Array.from(scope.querySelectorAll(ref));
  }
  return Array.isArray(ref) ? ref.filter(Boolean) : [ref];
}

function inferMasterDetailContext(trigger) {
  return String(
    trigger?.dataset?.masterDetailKey
      || trigger?.dataset?.calendarDay
      || trigger?.dataset?.fileName
      || trigger?.id
      || trigger?.textContent
      || "",
  )
    .trim()
    .slice(0, 120);
}

export function wireResponsiveMasterDetail({
  root,
  master = null,
  detail,
  triggers = [],
  backTrigger = null,
  selectedClass = "is-selected",
  detailFocus = null,
  scroll = true,
  autoWire = true,
} = {}) {
  const rootEl = resolveResponsiveElement(root);
  const detailEl = resolveResponsiveElement(detail, rootEl || document);
  const masterEl = resolveResponsiveElement(master, rootEl || document);
  if (!rootEl || !detailEl) return null;

  const triggerEls = resolveResponsiveElements(triggers, rootEl);
  const backEl = resolveResponsiveElement(backTrigger, rootEl);
  const scheduleFrame = globalThis.requestAnimationFrame || ((callback) => callback());
  let selectedTrigger = triggerEls.find((trigger) => trigger.classList.contains(selectedClass)) || null;

  function isCompactViewport() {
    return Boolean(window.matchMedia?.("(max-width: 900px)").matches);
  }

  function focusDetail() {
    const focusTarget = resolveResponsiveElement(detailFocus, detailEl) || detailEl;
    if (!focusTarget?.focus) return;
    scheduleFrame(() => focusTarget.focus({ preventScroll: true }));
  }

  function scrollToDetail() {
    if (!scroll || !isCompactViewport()) return;
    scheduleFrame(() => detailEl.scrollIntoView({ block: "start", behavior: "smooth" }));
  }

  function syncSelection(nextTrigger = selectedTrigger) {
    selectedTrigger = nextTrigger || selectedTrigger;
    triggerEls.forEach((trigger) => {
      const selected = Boolean(selectedTrigger && trigger === selectedTrigger);
      trigger.classList.toggle(selectedClass, selected);
      trigger.setAttribute("aria-selected", String(selected));
      if (!selected) delete trigger.dataset.masterDetailSelected;
    });
    if (!selectedTrigger) return;
    const context = inferMasterDetailContext(selectedTrigger);
    if (context) {
      rootEl.dataset.masterDetailContext = context;
      detailEl.dataset.detailContext = context;
      selectedTrigger.dataset.masterDetailSelected = "true";
    }
  }

  function activate(trigger, { focus = true, revealDetail = true, shouldScroll = scroll } = {}) {
    if (trigger) selectedTrigger = trigger;
    rootEl.dataset.masterDetailState = revealDetail ? "detail" : rootEl.dataset.masterDetailState || "master";
    detailEl.dataset.detailState = "active";
    masterEl?.setAttribute("data-master-state", "context-preserved");
    syncSelection(selectedTrigger);
    if (revealDetail && shouldScroll) scrollToDetail();
    if (revealDetail && focus) focusDetail();
  }

  function backToMaster() {
    rootEl.dataset.masterDetailState = "master";
    detailEl.dataset.detailState = selectedTrigger ? "docked" : "empty";
    masterEl?.setAttribute("data-master-state", "active");
    scheduleFrame(() => {
      selectedTrigger?.focus?.({ preventScroll: true });
      if (scroll && isCompactViewport()) {
        (masterEl || rootEl).scrollIntoView({ block: "start", behavior: "smooth" });
      }
    });
  }

  rootEl.dataset.masterDetail = "ready";
  rootEl.dataset.masterDetailState = rootEl.dataset.masterDetailState || "master";
  detailEl.dataset.detailState = selectedTrigger ? "docked" : detailEl.dataset.detailState || "empty";
  detailEl.setAttribute("tabindex", detailEl.getAttribute("tabindex") || "-1");
  masterEl?.setAttribute("data-master-state", "active");
  syncSelection(selectedTrigger);

  triggerEls.forEach((trigger) => {
    trigger.dataset.masterDetailTrigger = trigger.dataset.masterDetailTrigger || "true";
    if (autoWire) trigger.addEventListener("click", () => activate(trigger));
  });
  backEl?.addEventListener("click", backToMaster);

  return {
    activate,
    backToMaster,
    syncSelection,
    get selectedTrigger() {
      return selectedTrigger;
    },
  };
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

const FORM_CONTROL_SELECTOR = "input:not([type='hidden']), select, textarea";

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
  scope.querySelectorAll(FORM_CONTROL_SELECTOR).forEach((control) => {
    if (controlHasAccessibleName(control)) return;
    control.setAttribute("aria-label", derivedControlLabel(control));
    control.dataset.a11yLabelGenerated = "true";
  });
}

function inferResponsiveFieldKind(control) {
  const tagName = control.tagName;
  const type = String(control.getAttribute("type") || "").toLowerCase();
  if (tagName === "TEXTAREA") return "long";
  if (type === "file") return "upload";
  if (type === "checkbox" || type === "radio") return "choice";
  if (control.closest(".full-width, .ui-form-field-long, [data-field-width='full']")) return "long";
  return "control";
}

function inferResponsiveFormDensity(form) {
  if (form.dataset.formDensity) return form.dataset.formDensity;
  if (form.classList.contains("ui-form-density-compact") || form.matches(".filters, .filters-bar")) return "compact";
  return "standard";
}

function enhanceResponsiveForms(scope) {
  scope.querySelectorAll("form").forEach((form) => {
    if (!form.matches(".ui-form-grid, .ui-form-toolbar, .form-grid, .filters, .filters-bar, [data-responsive-form]")) {
      return;
    }
    form.dataset.responsiveForm = form.dataset.responsiveForm || "true";
    form.dataset.formDensity = inferResponsiveFormDensity(form);
    form.querySelectorAll(FORM_CONTROL_SELECTOR).forEach((control) => {
      if (!control.dataset.responsiveField) {
        control.dataset.responsiveField = inferResponsiveFieldKind(control);
      }
      if (control.getAttribute("aria-describedby") && !control.dataset.validationHint) {
        control.dataset.validationHint = "described";
      }
    });
  });
}

function inferResponsiveFilterDensity(form) {
  if (form.dataset.filterDensity) return form.dataset.filterDensity;
  if (form.matches(".filters-bar, .filters, .ui-filter-bar")) return "compact";
  return "standard";
}

function syncResponsiveFilterPanel(panel) {
  if (!panel) return;
  const expanded = !panel.hidden && !panel.classList.contains("collapsed");
  panel.dataset.filterState = expanded ? "expanded" : "collapsed";
  panel.dataset.overlayState = expanded ? "open" : "closed";
  panel.dataset.overlaySurface = panel.classList.contains("ui-filter-drawer")
    ? "inline-drawer"
    : panel.dataset.overlaySurface || "inline-panel";
  panel.setAttribute("aria-hidden", expanded ? "false" : "true");
  if (!panel.getAttribute("role")) {
    panel.setAttribute("role", "region");
  }
}

function enhanceResponsiveFilters(scope) {
  scope.querySelectorAll("form.filters-bar, form.filters, form.ui-filter-bar, [data-responsive-filter]").forEach((form) => {
    form.dataset.responsiveFilter = form.dataset.responsiveFilter || "bar";
    form.dataset.filterDensity = inferResponsiveFilterDensity(form);
    form.querySelectorAll(".filters-bar-actions, .filter-actions, .ui-filter-actions").forEach((actions) => {
      actions.dataset.filterActions = "true";
    });
    form.querySelectorAll(".filters-panel, .ui-filter-panel").forEach((panel) => {
      panel.dataset.filterPanel = panel.dataset.filterPanel || "advanced";
      if (panel.classList.contains("ui-filter-drawer")) {
        panel.classList.add("ui-overlay-inline-drawer");
      }
      syncResponsiveFilterPanel(panel);
    });
    form.querySelectorAll("[aria-controls]").forEach((toggle) => {
      const panelId = toggle.getAttribute("aria-controls");
      const controlledPanel = panelId ? document.getElementById(panelId) : null;
      if (!controlledPanel || !form.contains(controlledPanel)) return;
      toggle.dataset.filterToggle = toggle.dataset.filterToggle || "advanced";
      toggle.dataset.filterPersistence = toggle.dataset.filterPersistence || "local";
      toggle.dataset.overlayTrigger = toggle.dataset.overlayTrigger || "inline-drawer";
    });
  });
}

function filterPanelStorageKey(panelId) {
  const routeKey = String(window.location?.hash || window.location?.pathname || "root").split("?")[0] || "root";
  return `controle-treinamentos:filter-panel:${routeKey}:${panelId}`;
}

function readFilterPanelState(panelId) {
  try {
    return window.sessionStorage?.getItem(filterPanelStorageKey(panelId)) || "";
  } catch {
    return "";
  }
}

function writeFilterPanelState(panelId, expanded) {
  try {
    window.sessionStorage?.setItem(filterPanelStorageKey(panelId), expanded ? "expanded" : "collapsed");
  } catch {
    // Session storage is an enhancement only; filters must keep working without it.
  }
}

export function wireResponsiveFilterPanel(toggleId, panelId, expandedText, collapsedText, { persist = true } = {}) {
  const toggle = document.getElementById(toggleId);
  const panel = document.getElementById(panelId);
  if (!toggle || !panel) return;
  const mobileQuery = window.matchMedia("(max-width: 900px)");
  const initiallyExpanded = !panel.classList.contains("collapsed") && !panel.hidden;
  const storedState = persist ? readFilterPanelState(panelId) : "";

  if (storedState === "expanded") {
    panel.classList.remove("collapsed");
    panel.hidden = false;
  } else if (storedState === "collapsed" && !initiallyExpanded) {
    panel.classList.add("collapsed");
    panel.hidden = true;
  }

  panel.dataset.filterPanel = panel.dataset.filterPanel || "advanced";
  panel.dataset.overlaySurface = panel.classList.contains("ui-filter-drawer") ? "inline-drawer" : panel.dataset.overlaySurface || "inline-panel";
  toggle.dataset.filterToggle = toggle.dataset.filterToggle || "advanced";
  toggle.dataset.filterPersistence = persist ? "local" : "none";
  toggle.dataset.overlayTrigger = toggle.dataset.overlayTrigger || "inline-drawer";

  function syncCollapsedState({ shouldPersist = false } = {}) {
    const expanded = !panel.classList.contains("collapsed");
    panel.hidden = !expanded;
    panel.dataset.filterState = expanded ? "expanded" : "collapsed";
    panel.dataset.overlayState = expanded ? "open" : "closed";
    panel.setAttribute("aria-hidden", expanded ? "false" : "true");
    if (!panel.getAttribute("role")) {
      panel.setAttribute("role", "region");
    }
    toggle.setAttribute("aria-expanded", String(expanded));
    toggle.textContent = expanded ? expandedText : collapsedText;
    if (shouldPersist && persist) {
      writeFilterPanelState(panelId, expanded);
    }
  }

  toggle.addEventListener("click", () => {
    panel.classList.toggle("collapsed");
    syncCollapsedState({ shouldPersist: true });
  });

  syncCollapsedState();
  if (typeof mobileQuery.addEventListener === "function") {
    mobileQuery.addEventListener("change", () => syncCollapsedState());
  } else {
    window.addEventListener("resize", () => syncCollapsedState(), { passive: true });
  }
}

const TABLE_PRIORITY_VALUES = new Set(["primary", "secondary", "tertiary", "actions", "detail"]);
const TABLE_ACTION_LABEL_PATTERN = /^(acao|acoes|actions?)$/i;
const TABLE_SECONDARY_LABEL_PATTERN = /\b(status|situacao|data|validade|vencimento|base|funcao|tipo|total|valor|hora|horas|competencia|categoria|operacao|jornada|avisos|flags)\b/i;
const TABLE_DETAIL_LABEL_PATTERN = /\b(observacao|observacoes|detalhe|detalhes|arquivo|anexo|notas|comentario|comentarios)\b/i;

function normalizeTableLabel(label) {
  return String(label || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

function tableColumnKey(label, index) {
  const normalized = normalizeTableLabel(label)
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return normalized || `coluna-${index + 1}`;
}

function normalizeTablePriority(value) {
  const normalized = normalizeTableLabel(value).replace(/[^a-z]/g, "");
  return TABLE_PRIORITY_VALUES.has(normalized) ? normalized : "";
}

function inferTableCellPriority(cell, index, header, totalCells) {
  const explicit = normalizeTablePriority(cell.getAttribute("data-responsive-priority") || cell.getAttribute("data-priority"));
  if (explicit) return explicit;

  const label = normalizeTableLabel(cell.getAttribute("data-label") || header?.label);
  const hasRowAction = Boolean(cell.querySelector("a, button"));
  const isActionCell = cell.classList.contains("actions")
    || cell.classList.contains("ui-table-actions")
    || TABLE_ACTION_LABEL_PATTERN.test(label)
    || (index === totalCells - 1 && hasRowAction);
  if (isActionCell) return "actions";

  if (cell.hasAttribute("data-table-detail") || cell.classList.contains("ui-table-row-detail") || TABLE_DETAIL_LABEL_PATTERN.test(label)) {
    return "detail";
  }

  if (index === 0) return "primary";
  if (index <= 2 || TABLE_SECONDARY_LABEL_PATTERN.test(label)) return "secondary";
  return "tertiary";
}

function inferTableDensity(table) {
  if (table.dataset.responsiveDensity) return table.dataset.responsiveDensity;
  const wrapper = table.closest(".ui-table-wrap, .table-wrap");
  if (wrapper?.classList.contains("ui-table-density-compact")) return "compact";
  if (wrapper?.classList.contains("ui-table-density-comfortable")) return "comfortable";
  return "standard";
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
    table.dataset.responsiveDensity = inferTableDensity(table);
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
        if (!cell.hasAttribute("data-responsive-column")) {
          cell.dataset.responsiveColumn = tableColumnKey(cell.getAttribute("data-label") || header?.label, index);
        }
        if (!cell.hasAttribute("data-responsive-priority")) {
          cell.dataset.responsivePriority = inferTableCellPriority(cell, index, header, cells.length);
        }
      });
      if (cells.some((cell) => cell.hasAttribute("data-table-detail") || cell.classList.contains("ui-table-row-detail"))) {
        row.dataset.responsiveExpandable = "true";
      }
    });
  });
}

export function enhanceOperationalSurfaces(root = document) {
  const scope = root?.querySelectorAll ? root : document;
  enhanceFormControlLabels(scope);
  enhanceResponsiveForms(scope);
  enhanceResponsiveFilters(scope);
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

