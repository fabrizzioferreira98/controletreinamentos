import { api } from "./api-client.20260430-142420.5a9c7b9d22cd.js";

const FINANCEIRO_BONIFICACOES_HORARIA_API = "/api/v1/financeiro/bonificacoes/horaria";
const FINANCEIRO_BONIFICACOES_PRODUTIVIDADE_API = "/api/v1/financeiro/bonificacoes/produtividade";

function compactParams(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== "" && value !== null && value !== undefined) {
      query.set(key, String(value));
    }
  });
  return query.toString();
}

export async function listFinanceiroBonificacoesHorarias({
  competencia = "",
  tripulanteId = "",
  funcao = "",
  status = "",
  page = 1,
  pageSize = 100,
} = {}) {
  const queryString = compactParams({
    competencia,
    tripulante_id: tripulanteId,
    funcao,
    status,
    page,
    page_size: pageSize,
  });
  const suffix = queryString ? `?${queryString}` : "";
  const { data } = await api(`${FINANCEIRO_BONIFICACOES_HORARIA_API}${suffix}`);
  return data;
}

export async function getFinanceiroBonificacaoHoraria(calculationId) {
  const { data } = await api(`${FINANCEIRO_BONIFICACOES_HORARIA_API}/${Number(calculationId)}`);
  return data;
}

export async function listFinanceiroBonificacoesProdutividade({
  competencia = "",
  tripulanteId = "",
  funcao = "",
  status = "",
  page = 1,
  pageSize = 100,
} = {}) {
  const queryString = compactParams({
    competencia,
    tripulante_id: tripulanteId,
    funcao,
    status,
    page,
    page_size: pageSize,
  });
  const suffix = queryString ? `?${queryString}` : "";
  const { data } = await api(`${FINANCEIRO_BONIFICACOES_PRODUTIVIDADE_API}${suffix}`);
  return data;
}

export async function getFinanceiroBonificacaoProdutividade(tripulanteId, { competencia = "", funcao = "" } = {}) {
  const queryString = compactParams({ competencia, funcao });
  const suffix = queryString ? `?${queryString}` : "";
  const { data } = await api(`${FINANCEIRO_BONIFICACOES_PRODUTIVIDADE_API}/${Number(tripulanteId)}${suffix}`);
  return data;
}
