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
