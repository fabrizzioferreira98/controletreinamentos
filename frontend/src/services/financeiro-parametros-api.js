import { api } from "./api-client.js";

const FINANCEIRO_PARAMETROS_API = "/api/v1/financeiro/parametros";
const FINANCEIRO_FERIADOS_API = "/api/v1/financeiro/feriados";
const FINANCEIRO_COMPETENCIAS_API = "/api/v1/financeiro/competencias";
const FINANCEIRO_AUDITORIA_API = "/api/v1/financeiro/auditoria";
const FINANCEIRO_DIVERGENCIAS_API = "/api/v1/financeiro/divergencias";

function compactParams(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== "" && value !== null && value !== undefined) {
      query.set(key, String(value));
    }
  });
  return query.toString();
}

export async function listFinanceiroParametros({
  tipo = "",
  status = "",
  funcao = "",
  categoria = "",
  unidade = "",
  vigenciaEm = "",
  page = 1,
  pageSize = 100,
} = {}) {
  const queryString = compactParams({
    tipo,
    status,
    funcao,
    categoria,
    unidade,
    vigencia_em: vigenciaEm,
    page,
    page_size: pageSize,
  });
  const { data } = await api(`${FINANCEIRO_PARAMETROS_API}?${queryString}`);
  return data;
}

export async function createFinanceiroParametro(payload) {
  const { data } = await api(FINANCEIRO_PARAMETROS_API, {
    method: "POST",
    json: payload,
  });
  return data;
}

export async function updateFinanceiroParametro(parameterId, payload) {
  const { data } = await api(`${FINANCEIRO_PARAMETROS_API}/${Number(parameterId)}`, {
    method: "PATCH",
    json: payload,
  });
  return data;
}

export async function listFinanceiroFeriados({
  ano = "",
  status = "",
  dataInicio = "",
  dataFim = "",
  page = 1,
  pageSize = 100,
} = {}) {
  const queryString = compactParams({
    ano,
    status,
    data_inicio: dataInicio,
    data_fim: dataFim,
    page,
    page_size: pageSize,
  });
  const { data } = await api(`${FINANCEIRO_FERIADOS_API}?${queryString}`);
  return data;
}

export async function createFinanceiroFeriado(payload) {
  const { data } = await api(FINANCEIRO_FERIADOS_API, {
    method: "POST",
    json: payload,
  });
  return data;
}

export async function updateFinanceiroFeriado(holidayId, payload) {
  const { data } = await api(`${FINANCEIRO_FERIADOS_API}/${Number(holidayId)}`, {
    method: "PATCH",
    json: payload,
  });
  return data;
}

export async function getFinanceiroCompetencia(competencia) {
  const { data } = await api(`${FINANCEIRO_COMPETENCIAS_API}/${encodeURIComponent(competencia)}`);
  return data;
}

export async function getFinanceiroCompetenciaPreflight(competencia) {
  const { data } = await api(`${FINANCEIRO_COMPETENCIAS_API}/${encodeURIComponent(competencia)}/preflight-calculo`);
  return data;
}

export async function listFinanceiroAuditoria({
  competencia = "",
  entityType = "",
  entityId = "",
  eventName = "",
  limit = 20,
  offset = 0,
} = {}) {
  const queryString = compactParams({
    competencia,
    entity_type: entityType,
    entity_id: entityId,
    event_name: eventName,
    limit,
    offset,
  });
  const suffix = queryString ? `?${queryString}` : "";
  const { data } = await api(`${FINANCEIRO_AUDITORIA_API}${suffix}`);
  return data;
}

export async function listFinanceiroDivergencias({
  competencia = "",
  status = "",
  severidade = "",
  codigo = "",
  limit = 20,
  offset = 0,
} = {}) {
  const queryString = compactParams({
    competencia,
    status,
    severidade,
    codigo,
    limit,
    offset,
  });
  const suffix = queryString ? `?${queryString}` : "";
  const { data } = await api(`${FINANCEIRO_DIVERGENCIAS_API}${suffix}`);
  return data;
}

function filenameFromContentDisposition(value, fallback) {
  const header = String(value || "");
  const utf8Match = header.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) return decodeURIComponent(utf8Match[1]);
  const plainMatch = header.match(/filename="?([^";]+)"?/i);
  return plainMatch?.[1] || fallback;
}

export async function downloadFinanceiroCompetenciaPdf(competencia) {
  const filename = `relatorio-financeiro-${competencia}.pdf`;
  const { response, data } = await api(`${FINANCEIRO_COMPETENCIAS_API}/${encodeURIComponent(competencia)}/relatorio.pdf`, {
    headers: {
      Accept: "application/pdf",
      "X-Requested-With": "XMLHttpRequest",
    },
  });
  return {
    blob: data,
    filename: filenameFromContentDisposition(response.headers.get("Content-Disposition"), filename),
  };
}

export async function recalculateFinanceiroCompetencia(competencia) {
  const { data } = await api(`${FINANCEIRO_COMPETENCIAS_API}/${encodeURIComponent(competencia)}/recalcular`, {
    method: "POST",
    json: {},
  });
  return data;
}

export async function closeFinanceiroCompetencia(competencia, payload = {}) {
  const { data } = await api(`${FINANCEIRO_COMPETENCIAS_API}/${encodeURIComponent(competencia)}/fechar`, {
    method: "POST",
    json: { ...payload, confirm: true },
  });
  return data;
}

export async function reopenFinanceiroCompetencia(competencia, payload = {}) {
  const { data } = await api(`${FINANCEIRO_COMPETENCIAS_API}/${encodeURIComponent(competencia)}/reabrir`, {
    method: "POST",
    json: payload,
  });
  return data;
}
