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
  tipos: "/tipos",
  treinamentosConsolidadoExportCsv: "/treinamentos/consolidado/export.csv",
  treinamentosConsolidadoExportPdf: "/treinamentos/consolidado/export.pdf",
  treinamentosConsolidadoRelatorio: "/treinamentos/consolidado/relatorio",
  usuarios: "/usuarios",
  usuariosNew: "/usuarios/novo",
});

export const BACKEND_LINK_BOUNDARIES = Object.freeze({
  [BACKEND_LINKS.auditoria]: "backend_ssr_compat",
  [BACKEND_LINKS.backups]: "backend_ssr_compat",
  [BACKEND_LINKS.bases]: "backend_ssr_compat",
  [BACKEND_LINKS.equipamentos]: "backend_ssr_compat",
  [BACKEND_LINKS.manualUsuarioPdf]: "externo_operacional",
  [BACKEND_LINKS.monitoramento]: "backend_ssr_compat",
  [BACKEND_LINKS.notificacoesEmail]: "backend_ssr_compat",
  [BACKEND_LINKS.pernoites]: "legacy_vivo_controlado",
  [BACKEND_LINKS.pernoitesNew]: "legacy_vivo_controlado",
  [BACKEND_LINKS.tipos]: "backend_ssr_compat",
  [BACKEND_LINKS.treinamentosConsolidadoExportCsv]: "backend_ssr_compat",
  [BACKEND_LINKS.treinamentosConsolidadoExportPdf]: "backend_ssr_compat",
  [BACKEND_LINKS.treinamentosConsolidadoRelatorio]: "backend_ssr_compat",
  [BACKEND_LINKS.usuarios]: "backend_ssr_compat",
  [BACKEND_LINKS.usuariosNew]: "backend_ssr_compat",
});

export const FRONTEND_HASH_BY_BACKEND_PATH = Object.freeze({
  "/dashboard": "#/dashboard",
  "/tripulantes": "#/tripulantes",
  "/treinamentos": "#/treinamentos",
  "/tipos-treinamento": "#/treinamentos/raiz",
  "/treinamentos/consolidado": "#/relatorios/habilitacoes",
});

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
    const hash = FRONTEND_HASH_BY_BACKEND_PATH[path];
    if (hash) return { kind: "hash", value: query ? `${hash}?${query}` : hash };
    return { kind: "path", value: raw };
  }
  if (!fallbackHash) return { kind: "none", value: "" };
  return { kind: "hash", value: fallbackHash };
}
