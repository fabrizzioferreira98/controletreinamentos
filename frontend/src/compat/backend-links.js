export const BACKEND_LINKS = Object.freeze({
  auditoria: "/auditoria",
  backups: "/backups",
  bases: "/bases",
  equipamentos: "/equipamentos",
  manualUsuarioPdf: "/manual/usuario.pdf",
  monitoramento: "/monitoramento",
  notificacoesEmail: "/notificacoes-email",
  pernoites: "/pernoites",
  pernoitesNew: "/pernoites/novo",
  tipos: "/tipos-treinamento",
  treinamentosConsolidadoExportCsv: "/treinamentos/consolidado/export.csv",
  treinamentosConsolidadoExportPdf: "/treinamentos/consolidado/export.pdf",
  treinamentosConsolidadoRelatorio: "/treinamentos/consolidado/relatorio",
  usuarios: "/usuarios",
  usuariosNew: "/usuarios/novo",
});

export const CANONICAL_FRONTEND_HASHES = Object.freeze({
  dashboard: "#/dashboard",
  tripulantes: "#/tripulantes",
  treinamentos: "#/treinamentos",
  trainingRoot: "#/treinamentos/raiz",
  relatorioHabilitacoes: "#/relatorios/habilitacoes",
});

export const BACKEND_LINK_BOUNDARIES = Object.freeze({
  [BACKEND_LINKS.auditoria]: "backend_ssr_compat",
  [BACKEND_LINKS.backups]: "backend_ssr_compat",
  [BACKEND_LINKS.bases]: "backend_ssr_compat",
  [BACKEND_LINKS.equipamentos]: "backend_ssr_compat",
  [BACKEND_LINKS.manualUsuarioPdf]: "externo_operacional",
  [BACKEND_LINKS.monitoramento]: "backend_ssr_compat",
  [BACKEND_LINKS.notificacoesEmail]: "backend_ssr_compat",
  [BACKEND_LINKS.pernoites]: "ssr_ui_current_with_api_read_model",
  [BACKEND_LINKS.pernoitesNew]: "ssr_write_canonical_current_direct",
  [BACKEND_LINKS.tipos]: "backend_ssr_compat_redirect_only",
  [BACKEND_LINKS.treinamentosConsolidadoExportCsv]: "backend_ssr_compat",
  [BACKEND_LINKS.treinamentosConsolidadoExportPdf]: "backend_ssr_compat",
  [BACKEND_LINKS.treinamentosConsolidadoRelatorio]: "backend_ssr_compat",
  [BACKEND_LINKS.usuarios]: "backend_ssr_compat",
  [BACKEND_LINKS.usuariosNew]: "backend_ssr_compat",
});

export const LEGACY_BACKEND_PATH_ALIASES = Object.freeze({
  "/tipos": CANONICAL_FRONTEND_HASHES.trainingRoot,
});

export const FRONTEND_HASH_BY_BACKEND_PATH = Object.freeze({
  "/dashboard": CANONICAL_FRONTEND_HASHES.dashboard,
  "/tripulantes": CANONICAL_FRONTEND_HASHES.tripulantes,
  "/treinamentos": CANONICAL_FRONTEND_HASHES.treinamentos,
  [BACKEND_LINKS.tipos]: CANONICAL_FRONTEND_HASHES.trainingRoot,
  "/treinamentos/consolidado": CANONICAL_FRONTEND_HASHES.relatorioHabilitacoes,
  ...LEGACY_BACKEND_PATH_ALIASES,
});

export function normalizeBackendPath(value) {
  const raw = String(value || "").trim();
  const [path = "/"] = raw.split(/[?#]/);
  if (!path.startsWith("/") || path.startsWith("//")) return "";
  return path.replace(/\/+$/, "") || "/";
}

export function resolveFrontendHashForBackendPath(value) {
  return FRONTEND_HASH_BY_BACKEND_PATH[normalizeBackendPath(value)] || "";
}

export function buildBackendHref(path, params = {}) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === "" || value === null || value === undefined) continue;
    query.set(key, String(value));
  }
  const queryString = query.toString();
  return queryString ? `${path}?${queryString}` : path;
}

export function resolveLoginDestination(value, { fallbackHash = "#/dashboard" } = {}) {
  const raw = String(value || "").trim();
  if (raw.startsWith("#/")) return { kind: "hash", value: raw };
  if (raw.startsWith("/") && !raw.startsWith("//")) {
    const [path = "/", query = ""] = raw.split("?");
    const hash = resolveFrontendHashForBackendPath(path);
    if (hash) return { kind: "hash", value: query ? `${hash}?${query}` : hash };
    return { kind: "path", value: raw };
  }
  if (!fallbackHash) return { kind: "none", value: "" };
  return { kind: "hash", value: fallbackHash };
}
