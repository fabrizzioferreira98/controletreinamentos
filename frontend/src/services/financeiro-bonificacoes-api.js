import { api } from "./api-client.js";

const FINANCEIRO_BONIFICACOES_HORARIA_API = "/api/v1/financeiro/bonificacoes/horaria";
const FINANCEIRO_BONIFICACOES_PRODUTIVIDADE_API = "/api/v1/financeiro/bonificacoes/produtividade";
const FINANCEIRO_RELATORIO_INDIVIDUAL_API = "/api/v1/financeiro/relatorios/individual.pdf";

function compactParams(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== "" && value !== null && value !== undefined) {
      query.set(key, String(value));
    }
  });
  return query.toString();
}

function filenameFromContentDisposition(value, fallback) {
  const header = String(value || "");
  const utf8Match = header.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) return decodeURIComponent(utf8Match[1]);
  const plainMatch = header.match(/filename="?([^";]+)"?/i);
  return plainMatch?.[1] || fallback;
}

async function ensurePdfBlob(blob, contextLabel = "PDF") {
  if (!(blob instanceof Blob) || !blob.size) {
    throw new Error(`${contextLabel} vazio ou indisponivel.`);
  }
  const header = await blob.slice(0, 5).text();
  const trailerStart = blob.size > 32 ? blob.size - 32 : 0;
  const trailer = await blob.slice(trailerStart).text();
  if (header !== "%PDF-" || !trailer.includes("%%EOF")) {
    throw new Error(`${contextLabel} invalido: o servidor nao retornou um PDF completo.`);
  }
  return blob;
}

async function fetchFinanceiroBonificacoesHorariasPage({
  competencia = "",
  funcao = "",
  status = "",
  page = 1,
  pageSize = 100,
} = {}) {
  const queryString = compactParams({
    competencia,
    funcao,
    status,
    page,
    page_size: pageSize,
  });
  const suffix = queryString ? `?${queryString}` : "";
  const { data } = await api(`${FINANCEIRO_BONIFICACOES_HORARIA_API}${suffix}`);
  return data;
}

export async function listFinanceiroBonificacoesHorarias({ competencia = "", funcao = "", status = "", pageSize = 100 } = {}) {
  const firstPage = await fetchFinanceiroBonificacoesHorariasPage({ competencia, funcao, status, page: 1, pageSize });
  const items = Array.isArray(firstPage?.items) ? [...firstPage.items] : [];
  const pagination = firstPage?.pagination || {};
  let totalPages = Number(pagination.pages || 1) || 1;
  if (totalPages < 1) totalPages = 1;
  for (let page = 2; page <= totalPages; page += 1) {
    const payload = await fetchFinanceiroBonificacoesHorariasPage({ competencia, funcao, status, page, pageSize });
    if (Array.isArray(payload?.items)) {
      items.push(...payload.items);
    }
  }
  return {
    ...firstPage,
    items,
    pagination: {
      ...pagination,
      page: 1,
      pages: totalPages,
      total: Number(pagination.total || items.length) || items.length,
      loaded: items.length,
    },
  };
}

export async function getFinanceiroBonificacaoHoraria(calculationId) {
  const { data } = await api(`${FINANCEIRO_BONIFICACOES_HORARIA_API}/${Number(calculationId)}`);
  return data;
}

async function fetchFinanceiroBonificacoesProdutividadePage({
  competencia = "",
  funcao = "",
  status = "",
  page = 1,
  pageSize = 100,
} = {}) {
  const queryString = compactParams({
    competencia,
    funcao,
    status,
    page,
    page_size: pageSize,
  });
  const suffix = queryString ? `?${queryString}` : "";
  const { data } = await api(`${FINANCEIRO_BONIFICACOES_PRODUTIVIDADE_API}${suffix}`);
  return data;
}

export async function listFinanceiroBonificacoesProdutividade({ competencia = "", funcao = "", status = "", pageSize = 100 } = {}) {
  const firstPage = await fetchFinanceiroBonificacoesProdutividadePage({ competencia, funcao, status, page: 1, pageSize });
  const items = Array.isArray(firstPage?.items) ? [...firstPage.items] : [];
  const pagination = firstPage?.pagination || {};
  let totalPages = Number(pagination.pages || 1) || 1;
  if (totalPages < 1) totalPages = 1;
  for (let page = 2; page <= totalPages; page += 1) {
    const payload = await fetchFinanceiroBonificacoesProdutividadePage({ competencia, funcao, status, page, pageSize });
    if (Array.isArray(payload?.items)) {
      items.push(...payload.items);
    }
  }
  return {
    ...firstPage,
    items,
    pagination: {
      ...pagination,
      page: 1,
      pages: totalPages,
      total: Number(pagination.total || items.length) || items.length,
      loaded: items.length,
    },
  };
}

export async function getFinanceiroBonificacaoProdutividade(tripulanteId, { competencia = "", funcao = "" } = {}) {
  const queryString = compactParams({ competencia, funcao });
  const suffix = queryString ? `?${queryString}` : "";
  const { data } = await api(`${FINANCEIRO_BONIFICACOES_PRODUTIVIDADE_API}/${Number(tripulanteId)}${suffix}`);
  return data;
}

export async function downloadFinanceiroRelatorioIndividual({
  tipo,
  competencia,
  tripulanteId,
  funcao = "",
  status = "",
  incluirObsoletos = false,
} = {}) {
  const reportType = String(tipo || "").trim();
  const queryString = compactParams({
    tipo: reportType,
    competencia,
    tripulante_id: Number(tripulanteId),
    funcao,
    status,
    incluir_obsoletos: incluirObsoletos ? "true" : "",
    formato: "pdf",
  });
  const fallback = `relatorio-${reportType || "individual"}-${competencia || "competencia"}.pdf`;
  const { response, data } = await api(`${FINANCEIRO_RELATORIO_INDIVIDUAL_API}?${queryString}`, {
    headers: {
      Accept: "application/pdf",
      "X-Requested-With": "XMLHttpRequest",
    },
    timeoutMs: 120000,
  });
  return {
    blob: await ensurePdfBlob(data, "Relatorio individual financeiro"),
    filename: filenameFromContentDisposition(response.headers.get("Content-Disposition"), fallback),
  };
}
