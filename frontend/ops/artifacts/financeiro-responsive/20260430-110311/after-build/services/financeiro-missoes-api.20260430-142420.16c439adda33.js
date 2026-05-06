import { api } from "./api-client.20260430-142420.5a9c7b9d22cd.js";

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

export async function listFinanceiroTripulanteOptions({ nome = "", ativo = "1", page = 1 } = {}) {
  const queryString = compactParams({
    nome,
    ativo,
    page,
  });
  const { data } = await api(`${TRIPULANTES_API}?${queryString}`);
  return data;
}

export async function listFinanceiroEquipamentoOptions({ equipamentoId = "" } = {}) {
  const queryString = compactParams({
    equipamento_id: equipamentoId,
  });
  const suffix = queryString ? `?${queryString}` : "";
  const { data } = await api(`${EQUIPAMENTOS_OPTIONS_API}${suffix}`);
  return data;
}
