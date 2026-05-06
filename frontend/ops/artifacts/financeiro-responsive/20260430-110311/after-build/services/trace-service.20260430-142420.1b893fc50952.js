const CORRELATION_STORAGE_KEY = "controle_treinamentos.correlation.v1";
const FORENSICS_GLOBAL_KEY = "__FRONTEND_FORENSICS__";
let forensicSequence = 0;
let forensicHooksInstalled = false;

export function createTraceId(prefix = "web") {
  if (window.crypto?.randomUUID) return `${prefix}-${window.crypto.randomUUID()}`;
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

export function clientCorrelationId() {
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

function forensicNow() {
  return Math.round((window.performance?.now?.() ?? Date.now()) * 10) / 10;
}

function normalizeForensicValue(value, depth = 0) {
  if (depth > 4) return "[max-depth]";
  if (value === null || value === undefined) return value;
  const valueType = typeof value;
  if (valueType === "string" || valueType === "number" || valueType === "boolean") return value;
  if (valueType === "function") return "[function]";
  if (value instanceof Error) {
    return {
      name: value.name,
      message: value.message,
      code: value.code || "",
      status: value.status || "",
      requestId: value.requestId || "",
      correlationId: value.correlationId || "",
    };
  }
  if (value instanceof Headers) {
    return Object.fromEntries(Array.from(value.entries()).map(([key, item]) => [key, String(item)]));
  }
  if (value instanceof Element) {
    return {
      tagName: value.tagName,
      id: value.id || "",
      className: String(value.className || ""),
    };
  }
  if (Array.isArray(value)) return value.slice(0, 30).map((item) => normalizeForensicValue(item, depth + 1));
  if (valueType === "object") {
    return Object.fromEntries(
      Object.entries(value)
        .slice(0, 60)
        .map(([key, item]) => [key, normalizeForensicValue(item, depth + 1)]),
    );
  }
  return String(value);
}

function shortUrl(value) {
  const raw = String(value || "");
  if (!raw) return "";
  try {
    const parsed = new URL(raw, window.location.href);
    return parsed.pathname + parsed.search + parsed.hash;
  } catch (_error) {
    return raw;
  }
}

function resourceEntries() {
  try {
    return performance.getEntriesByType("resource")
      .filter((entry) => /\.(?:css|js)(?:$|\?)/i.test(entry.name))
      .slice(-40)
      .map((entry) => ({
        name: shortUrl(entry.name),
        initiatorType: entry.initiatorType || "",
        duration_ms: Math.round(entry.duration * 10) / 10,
        transferSize: entry.transferSize || 0,
        encodedBodySize: entry.encodedBodySize || 0,
        decodedBodySize: entry.decodedBodySize || 0,
      }));
  } catch (_error) {
    return [];
  }
}

function stylesheetLinks() {
  return Array.from(document.querySelectorAll('link[rel~="stylesheet"]')).map((link) => ({
    href: shortUrl(link.href),
    loadedInCssom: Boolean(link.sheet),
    disabled: Boolean(link.disabled),
    media: link.media || "",
  }));
}

function scriptTags() {
  return Array.from(document.querySelectorAll("script[src]")).map((script) => ({
    src: shortUrl(script.src),
    type: script.type || "",
    async: Boolean(script.async),
    defer: Boolean(script.defer),
  }));
}

function computedProbe(selector, properties) {
  const element = document.querySelector(selector);
  if (!element) return null;
  const style = window.getComputedStyle(element);
  return Object.fromEntries(properties.map((property) => [property, style.getPropertyValue(property)]));
}

export function forensicAssetSnapshot() {
  return {
    readyState: document.readyState,
    href: window.location.href,
    hash: window.location.hash,
    stylesheetLinks: stylesheetLinks(),
    scriptTags: scriptTags(),
    resources: resourceEntries(),
    dom: {
      appChildren: document.getElementById("app")?.children.length ?? 0,
      shell: Boolean(document.querySelector(".app-shell")),
      login: Boolean(document.querySelector(".login-shell")),
      dashboard: Boolean(document.querySelector(".dashboard-reference-target")),
      routeFailure: Boolean(document.querySelector(".route-state")),
    },
    cssProbes: {
      appShell: computedProbe(".app-shell", ["display", "grid-template-columns"]),
      dashboardShell: computedProbe(".dashboard-reference-target", ["display", "gap"]),
      dashboardStatGrid: computedProbe(".dashboard-stat-grid", ["display", "grid-template-columns", "gap"]),
      dashboardKpiCard: computedProbe(".dashboard-kpi-card", ["display", "padding", "border-radius", "background-color"]),
      dashboardSparkline: computedProbe(".dashboard-kpi-sparkline", ["display", "width", "height", "max-width"]),
    },
  };
}

export function forensicTrace(event, detail = {}, options = {}) {
  try {
    const entry = {
      seq: ++forensicSequence,
      at_ms: forensicNow(),
      event,
      route: window.location.hash || "",
      path: `${window.location.pathname || ""}${window.location.search || ""}`,
      detail: normalizeForensicValue(detail),
    };
    if (options.assets) {
      entry.assets = forensicAssetSnapshot();
    }
    const store = window[FORENSICS_GLOBAL_KEY] || [];
    store.push(entry);
    window[FORENSICS_GLOBAL_KEY] = store.slice(-500);
    if (window.__FRONTEND_CONFIG__?.debug || window.__FRONTEND_FORENSICS_VERBOSE__) {
      console.info("[frontend-forensics]", entry);
    }
    return entry;
  } catch (error) {
    console.info("[frontend-forensics:error]", event, error?.message || error);
    return null;
  }
}

export function installForensicRuntimeHooks() {
  if (forensicHooksInstalled) return;
  forensicHooksInstalled = true;
  forensicTrace("runtime.hooks.install", { userAgent: navigator.userAgent }, { assets: true });

  window.addEventListener("hashchange", (event) => {
    forensicTrace("navigation.hashchange", {
      oldURL: shortUrl(event.oldURL),
      newURL: shortUrl(event.newURL),
    }, { assets: true });
  });
  window.addEventListener("popstate", () => {
    forensicTrace("navigation.popstate", {}, { assets: true });
  });
  window.addEventListener("pageshow", (event) => {
    forensicTrace("page.pageshow", { persisted: event.persisted }, { assets: true });
  });
  window.addEventListener("pagehide", (event) => {
    forensicTrace("page.pagehide", { persisted: event.persisted });
  });
  window.addEventListener("error", (event) => {
    const target = event.target;
    if (target instanceof HTMLLinkElement || target instanceof HTMLScriptElement || target instanceof HTMLImageElement) {
      forensicTrace("resource.error", {
        tagName: target.tagName,
        href: shortUrl(target.href || target.src),
      }, { assets: true });
    }
  }, true);

  const originalPushState = history.pushState;
  const originalReplaceState = history.replaceState;
  history.pushState = function pushStateForensics(...args) {
    forensicTrace("history.pushState", { url: args[2] || "" });
    return originalPushState.apply(this, args);
  };
  history.replaceState = function replaceStateForensics(...args) {
    forensicTrace("history.replaceState", { url: args[2] || "" });
    return originalReplaceState.apply(this, args);
  };
}
