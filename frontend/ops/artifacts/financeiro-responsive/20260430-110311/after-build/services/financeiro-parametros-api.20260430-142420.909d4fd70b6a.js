import { api } from "./api-client.20260430-142420.5a9c7b9d22cd.js";

const FINANCEIRO_PARAMETROS_API = "/api/v1/financeiro/parametros";
const FINANCEIRO_FERIADOS_API = "/api/v1/financeiro/feriados";
const FINANCEIRO_COMPETENCIAS_API = "/api/v1/financeiro/competencias";

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
