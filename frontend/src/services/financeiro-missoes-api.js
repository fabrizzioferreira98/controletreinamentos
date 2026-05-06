import { api } from "./api-client.js";

const FINANCEIRO_MISSOES_API = "/api/v1/financeiro/missoes";
const TRIPULANTES_API = "/api/v1/tripulantes";
const EQUIPAMENTOS_OPTIONS_API = "/api/v1/equipamentos/options";

function compactParams(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== "" && value !== null && value !== undefined) {
      query.set(key, String(value));
    }
  });
  return query.toString();
}

export async function listFinanceiroMissoes({ competencia, page = 1, pageSize = 100, status = "" } = {}) {
  const queryString = compactParams({
    competencia,
    page,
    page_size: pageSize,
    status,
  });
  const { data } = await api(`${FINANCEIRO_MISSOES_API}?${queryString}`);
  return data;
}

export async function createFinanceiroMissao(payload) {
  const { data } = await api(FINANCEIRO_MISSOES_API, {
    method: "POST",
    json: payload,
  });
  return data;
}

export async function previewFinanceiroMissao(payload) {
  const { data } = await api(`${FINANCEIRO_MISSOES_API}/preview`, {
    method: "POST",
    json: payload,
    timeoutMs: 15000,
  });
  return data;
}

export async function getFinanceiroMissao(missionId) {
  const { data } = await api(`${FINANCEIRO_MISSOES_API}/${Number(missionId)}`);
  return data;
}

export async function updateFinanceiroMissao(missionId, payload) {
  const { data } = await api(`${FINANCEIRO_MISSOES_API}/${Number(missionId)}`, {
    method: "PATCH",
    json: payload,
  });
  return data;
}

export async function cancelFinanceiroMissao(missionId, payload = {}) {
  const { data } = await api(`${FINANCEIRO_MISSOES_API}/${Number(missionId)}/cancelar`, {
    method: "POST",
    json: payload,
  });
  return data;
}

export async function deleteFinanceiroMissao(missionId, payload = {}) {
  const { data } = await api(`${FINANCEIRO_MISSOES_API}/${Number(missionId)}`, {
    method: "DELETE",
    json: payload,
  });
  return data;
}

export async function recalculateFinanceiroMissao(missionId) {
  const { data } = await api(`${FINANCEIRO_MISSOES_API}/${Number(missionId)}/recalcular`, {
    method: "POST",
  });
  return data;
}

export async function preflightFinanceiroMissaoCalculo(missionId) {
  const { data } = await api(`${FINANCEIRO_MISSOES_API}/${Number(missionId)}/preflight-calculo`);
  return data;
}

async function fetchFinanceiroTripulantePage({ nome = "", ativo = "1", page = 1 } = {}) {
  const queryString = compactParams({
    nome,
    ativo,
    page,
  });
  const { data } = await api(`${TRIPULANTES_API}?${queryString}`);
  return data;
}

export async function listFinanceiroTripulanteOptions({ nome = "", ativo = "1" } = {}) {
  const firstPage = await fetchFinanceiroTripulantePage({ nome, ativo, page: 1 });
  const items = Array.isArray(firstPage?.items) ? [...firstPage.items] : [];
  const pagination = firstPage?.pagination || {};
  const totalPages = Math.max(1, Number(pagination.pages || 1) || 1);
  for (let page = 2; page <= totalPages; page += 1) {
    const payload = await fetchFinanceiroTripulantePage({ nome, ativo, page });
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

export async function listFinanceiroEquipamentoOptions({ equipamentoId = "" } = {}) {
  const queryString = compactParams({
    equipamento_id: equipamentoId,
  });
  const suffix = queryString ? `?${queryString}` : "";
  const { data } = await api(`${EQUIPAMENTOS_OPTIONS_API}${suffix}`);
  return data;
}
