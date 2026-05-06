import {
  downloadFinanceiroRelatorioIndividual,
} from "./financeiro-bonificacoes-api.js";
import { config } from "../state/app-state.js";
import { api } from "./api-client.js";
import {
  listFinanceiroEquipamentoOptions,
  listFinanceiroTripulanteOptions,
} from "./financeiro-missoes-api.js";

export const JORNADA_API_CAPABILITIES = Object.freeze({
  nativeGradeEndpoint: true,
  nativeLineCreateEndpoint: true,
  nativeLineCancelEndpoint: false,
  previewEndpoint: "/api/v1/financeiro/lancamentos-jornada/preview",
  sourceOfTruth: "backend",
});

const FINANCEIRO_JORNADA_API = "/api/v1/financeiro/lancamentos-jornada";
const FINANCEIRO_RELATORIO_INDIVIDUAL_API = "/api/v1/financeiro/relatorios/individual.pdf";
const FINANCEIRO_PRODUTIVIDADE_CONSOLIDADO_API = "/api/v1/financeiro/produtividade/consolidado";
const FINANCEIRO_PRODUTIVIDADE_RELATORIO_GERAL_API = "/api/v1/financeiro/produtividade/relatorio-geral";
const FINANCEIRO_EXTRATO_PERIODO_API = "/api/v1/financeiro/extrato-periodo";
const FINANCEIRO_HORAS_TOTAIS_VOADAS_API = "/api/v1/financeiro/horas-totais-voadas";

function normalizeText(value) {
  return String(value ?? "").trim();
}

function normalizeLower(value) {
  return normalizeText(value).toLowerCase();
}

function numericValue(value) {
  const amount = Number(value ?? 0);
  return Number.isFinite(amount) ? amount : 0;
}

function nonNegativeNumber(value) {
  const amount = numericValue(value);
  return amount < 0 ? 0 : amount;
}

function remunerableOvernightCount(value) {
  const amount = nonNegativeNumber(value) - 1;
  return amount < 0 ? 0 : amount;
}

function compactParams(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== "" && value !== null && value !== undefined) {
      query.set(key, String(value));
    }
  });
  return query.toString();
}

function apiHref(path) {
  const base = String(config.apiBaseUrl || "").replace(/\/$/, "");
  return `${base}${path}`;
}

function createPdfValidationError(message, { status = 0, code = "invalid_pdf_response" } = {}) {
  const error = new Error(message);
  error.status = status;
  error.code = code;
  return error;
}

function ensurePdfContentType(response, data, contextLabel = "PDF") {
  if (!response?.ok) {
    throw createPdfValidationError(`${contextLabel} indisponivel: falha HTTP ${response?.status || 0}.`, {
      status: response?.status || 0,
      code: "pdf_http_error",
    });
  }
  const contentType = String(response.headers.get("Content-Type") || "").toLowerCase();
  if (contentType.includes("application/pdf")) return;
  if (contentType.includes("application/json") && data && typeof data === "object") {
    throw createPdfValidationError(data.message || `${contextLabel} indisponivel para o recorte informado.`, {
      status: response.status,
      code: data.code || data.error?.code || "pdf_json_response",
    });
  }
  throw createPdfValidationError(`${contextLabel} invalido: o servidor retornou ${contentType || "tipo desconhecido"} em vez de application/pdf.`, {
    status: response.status,
    code: "invalid_pdf_content_type",
  });
}

async function ensurePdfBlob(blob, contextLabel = "PDF") {
  if (!(blob instanceof Blob) || !blob.size) {
    throw new Error(`${contextLabel} vazio ou indisponivel.`);
  }
  const header = await blob.slice(0, 5).text();
  const trailerStart = blob.size > 32 ? blob.size - 32 : 0;
  const trailer = await blob.slice(trailerStart).text();
  if (!header.startsWith("%PDF") || !trailer.includes("%%EOF")) {
    throw new Error(`${contextLabel} invalido: o servidor nao retornou um PDF completo.`);
  }
  return blob;
}

function filenameFromContentDisposition(value, fallback) {
  const header = String(value || "");
  const utf8Match = header.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) return decodeURIComponent(utf8Match[1]);
  const plainMatch = header.match(/filename="?([^";]+)"?/i);
  return plainMatch?.[1] || fallback;
}

function indicatorsFromNative(indicators = {}) {
  return {
    totalGeral: numericValue(indicators.total_geral),
    linhas: Number(indicators.quantidade_linhas || 0) || 0,
    horaReduzida: numericValue(indicators.hora_reduzida_total),
    excecoes: Number(indicators.excecoes || 0) || 0,
    alertasDescanso: Number(indicators.alertas_descanso || 0) || 0,
    domingos: Number(indicators.domingos || 0) || 0,
    feriados: Number(indicators.feriados || 0) || 0,
    valorNormal: numericValue(indicators.valor_normal),
  };
}

export function normalizeFinanceiroHorasTotaisVoadasFuncao(value) {
  const normalized = normalizeLower(value).replace(/s$/, "");
  if (normalized === "comandante") return "comandante";
  if (normalized === "copiloto") return "copiloto";
  return "";
}

function normalizeHorasTotaisVoadasFilters(filters = {}) {
  const competencia = normalizeText(filters.competencia);
  const funcao = normalizeFinanceiroHorasTotaisVoadasFuncao(filters.funcao);
  if (!/^\d{4}-\d{2}$/.test(competencia)) {
    throw createPdfValidationError("Informe uma competencia valida no formato YYYY-MM.", {
      code: "invalid_competencia",
    });
  }
  if (!funcao) {
    throw createPdfValidationError("Selecione a funcao operacional do relatorio.", {
      code: "invalid_funcao",
    });
  }
  return { competencia, funcao };
}

export function financeiroHorasTotaisVoadasFilename(filters = {}) {
  const normalized = normalizeHorasTotaisVoadasFilters(filters);
  const functionSlug = normalized.funcao === "copiloto" ? "copilotos" : "comandantes";
  return `relatorio-horas-totais-voadas-${functionSlug}-${normalized.competencia}.pdf`;
}

export function financeiroProdutividadeRelatorioGeralFilename(filters = {}) {
  const normalized = normalizeHorasTotaisVoadasFilters(filters);
  const functionSlug = normalized.funcao === "copiloto" ? "copilotos" : "comandantes";
  return `relatorio-geral-produtividade-${functionSlug}-${normalized.competencia}.pdf`;
}

function rowFromNativeLine(item = {}, index = 0) {
  const lineId = Number(item.id || item.linha_id || 0) || 0;
  const missionId = Number(item.missao_operacional_id || 0) || 0;
  const tripulanteId = Number(item.tripulante_id || item.tripulante?.id || 0) || 0;
  const funcao = normalizeText(item.funcao || "operacional");
  const comandanteTripulanteId = Number(item.comandante_tripulante_id || 0) || 0;
  const copilotoTripulanteId = Number(item.copiloto_tripulante_id || 0) || 0;
  return {
    key: lineId ? `line-${lineId}` : lineKey({ missionId, tripulanteId, funcao, index }),
    id: lineId,
    lineId,
    missionId,
    calculationId: Number(item.calculo_horario_id || item.calculation_id || 0) || 0,
    source: "lancamento-jornada",
    competencia: normalizeText(item.competencia),
    data: normalizeText(item.data || item.data_missao),
    dataFinal: normalizeText(item.data_final || item.data || item.data_missao),
    tripulanteId,
    tripulanteNome: normalizeText(item.tripulante?.nome || item.tripulante_nome),
    funcao,
    comandanteTripulanteId,
    comandanteTripulanteNome: normalizeText(item.comandante_nome || item.comandante_tripulante_nome || item.comandante_tripulante),
    copilotoTripulanteId,
    copilotoTripulanteNome: normalizeText(item.copiloto_nome || item.copiloto_tripulante_nome || item.copiloto_tripulante),
    aeronaveId: Number(item.aeronave_id || item.aeronave?.id || 0) || 0,
    aeronave: normalizeText(item.aeronave?.nome || item.aeronave_nome),
    relVoo: normalizeText(item.relatorio_voo || item.cavok_numero_voo),
    numeroDb: normalizeText(item.numero_db || item.chamado),
    contratante: normalizeText(item.contratante),
    trecho: normalizeText(item.trecho),
    apresentacao: normalizeText(item.hora_apresentacao || item.horario_apresentacao),
    abandono: normalizeText(item.hora_abandono || item.horario_abandono),
    posExecMin: numericValue(item.pos_exec_min),
    quantidadePernoites: numericValue(item.quantidade_pernoites),
    coberturaBase: Boolean(item.cobertura_base),
    tipoPernoite: normalizeText(item.tipo_pernoite),
    pernoitesRemuneraveis: numericValue(item.pernoites_remuneraveis),
    valorPernoiteComumUnitario: numericValue(item.valor_pernoite_comum_unitario),
    valorPernoiteComumTotal: numericValue(item.valor_pernoite_comum_total),
    operacaoEspecial: normalizeText(item.operacao_especial),
    justificativa: normalizeText(item.justificativa),
    observacao: normalizeText(item.observacao || item.observacoes),
    tipo: normalizeText(item.tipo || item.categoria_financeira_aeronave),
    diurna: numericValue(item.minutos_diurnos),
    noturna: numericValue(item.minutos_noturnos),
    preCalcMin: numericValue(item.pre_calculo_min),
    posCalc: numericValue(item.pos_calculo_min),
    total: numericValue(item.total),
    missionStatus: normalizeText(item.status || "ativa"),
    calculationStatus: normalizeText(item.calculation_status || item.status || "pendente"),
    status: normalizeText(item.calculation_status || item.status || "pendente"),
    isDomingo: false,
    isFeriado: false,
    hasException: Boolean((item.erros || []).length || (item.avisos || []).length),
    sourceMission: {
      id: missionId,
      competencia: item.competencia,
      data_missao: item.data || item.data_missao,
      data_final: item.data_final || item.data || item.data_missao,
      cavok_numero_voo: item.relatorio_voo,
      contratante: item.contratante,
      aeronave_id: item.aeronave_id,
      categoria_financeira_aeronave: item.tipo,
      comandante_tripulante_id: comandanteTripulanteId,
      comandante_nome: item.comandante_nome || item.comandante_tripulante_nome || item.comandante_tripulante,
      copiloto_tripulante_id: copilotoTripulanteId,
      copiloto_nome: item.copiloto_nome || item.copiloto_tripulante_nome || item.copiloto_tripulante,
      horario_apresentacao: item.hora_apresentacao,
      horario_abandono: item.hora_abandono,
      pos_exec_min: item.pos_exec_min,
      trecho: item.trecho,
      houve_pernoite: item.houve_pernoite,
      quantidade_pernoites: item.quantidade_pernoites,
      cobertura_base: item.cobertura_base,
      chamado: item.numero_db,
      operacao_especial: item.operacao_especial,
      justificativa: item.justificativa,
      observacoes: item.observacao,
    },
    sourceCalculation: item,
  };
}

function missionIdFromCalculation(item) {
  return Number(item?.missao_operacional_id || item?.mission_id || item?.missao_id || 0) || 0;
}

function tripulanteIdFromCalculation(item) {
  return Number(item?.tripulante_id || item?.tripulante?.id || 0) || 0;
}

function nameFromOption(item) {
  return normalizeText(item?.nome || item?.name || item?.label || item?.display_name);
}

function equipmentLabel(item) {
  return normalizeText(
    item?.prefixo ||
      item?.matricula ||
      item?.nome ||
      item?.modelo ||
      item?.equipamento ||
      item?.label ||
      item?.aeronave,
  );
}

function missionEquipmentLabel(mission, equipamentosById) {
  const explicit = equipmentLabel(mission);
  if (explicit) return explicit;
  const option = equipamentosById.get(Number(mission?.aeronave_id || 0));
  return equipmentLabel(option) || (mission?.aeronave_id ? `ID ${mission.aeronave_id}` : "");
}

function calculationTripulanteName(item, tripulantesById) {
  const explicit = normalizeText(
    item?.tripulante_nome ||
      item?.nome_tripulante ||
      item?.tripulante?.nome ||
      item?.tripulante,
  );
  if (explicit) return explicit;
  const option = tripulantesById.get(tripulanteIdFromCalculation(item));
  return nameFromOption(option) || (tripulanteIdFromCalculation(item) ? `ID ${tripulanteIdFromCalculation(item)}` : "");
}

function missionParticipantName(mission, funcao, tripulantesById) {
  const normalized = normalizeLower(funcao);
  const key = normalized === "copiloto" ? "copiloto" : "comandante";
  const explicit = normalizeText(
    mission?.[`${key}_nome`] ||
      mission?.[`${key}_tripulante_nome`] ||
      mission?.[`${key}_tripulante`],
  );
  if (explicit) return explicit;
  const id = Number(mission?.[`${key}_tripulante_id`] || 0) || 0;
  const option = tripulantesById.get(id);
  return nameFromOption(option) || (id ? `ID ${id}` : "");
}

function missionParticipantExplicitName(mission, funcao) {
  const normalized = normalizeLower(funcao);
  const key = normalized === "copiloto" ? "copiloto" : "comandante";
  return normalizeText(
    mission?.[`${key}_nome`] ||
      mission?.[`${key}_tripulante_nome`] ||
      mission?.[`${key}_tripulante`],
  );
}

function lineKey({ missionId, tripulanteId, funcao, index }) {
  const missionPart = missionId || "sem-missao";
  const crewPart = tripulanteId || "sem-tripulante";
  const functionPart = normalizeLower(funcao || "funcao");
  return `${missionPart}:${crewPart}:${functionPart}:${index}`;
}

function rowFromMissionAndCalculation({
  mission,
  calculation,
  funcao,
  tripulanteId,
  tripulanteNome,
  index,
  equipamentosById,
}) {
  const missionId = Number(mission?.id || missionIdFromCalculation(calculation) || 0) || 0;
  const resolvedFuncao = normalizeText(funcao || calculation?.funcao || "operacional");
  const resolvedTripulanteId = Number(tripulanteId || tripulanteIdFromCalculation(calculation) || 0) || 0;
  const comandanteTripulanteId = Number(mission?.comandante_tripulante_id || calculation?.comandante_tripulante_id || 0) || 0;
  const copilotoTripulanteId = Number(mission?.copiloto_tripulante_id || calculation?.copiloto_tripulante_id || 0) || 0;
  return {
    key: lineKey({ missionId, tripulanteId: resolvedTripulanteId, funcao: resolvedFuncao, index }),
    id: missionId ? `mission-${missionId}-${resolvedTripulanteId || index}-${normalizeLower(resolvedFuncao)}` : `calc-${index}`,
    missionId,
    calculationId: Number(calculation?.id || 0) || 0,
    source: missionId ? "missao" : "calculo",
    competencia: normalizeText(mission?.competencia || calculation?.competencia),
    data: normalizeText(mission?.data_missao || calculation?.data_missao),
    dataFinal: normalizeText(mission?.data_final || calculation?.data_final || mission?.data_missao || calculation?.data_missao),
    tripulanteId: resolvedTripulanteId,
    tripulanteNome: normalizeText(tripulanteNome || calculation?.tripulante_nome),
    funcao: resolvedFuncao,
    comandanteTripulanteId,
    comandanteTripulanteNome: missionParticipantExplicitName(mission || calculation || {}, "comandante"),
    copilotoTripulanteId,
    copilotoTripulanteNome: missionParticipantExplicitName(mission || calculation || {}, "copiloto"),
    aeronaveId: Number(mission?.aeronave_id || calculation?.aeronave_id || 0) || 0,
    aeronave: missionEquipmentLabel(mission || calculation || {}, equipamentosById),
    relVoo: normalizeText(mission?.cavok_numero_voo || calculation?.cavok_numero_voo || calculation?.relatorio_voo),
    numeroDb: normalizeText(mission?.chamado || calculation?.numero_db || calculation?.db_numero || ""),
    contratante: normalizeText(mission?.contratante || calculation?.contratante),
    trecho: normalizeText(mission?.trecho || calculation?.trecho),
    apresentacao: normalizeText(mission?.horario_apresentacao || calculation?.horario_apresentacao),
    abandono: normalizeText(mission?.horario_abandono || calculation?.horario_abandono),
    posExecMin: normalizeText(mission?.pos_exec_min || calculation?.pos_exec_min || calculation?.minutos_pos || "0"),
    quantidadePernoites: numericValue(mission?.quantidade_pernoites || calculation?.quantidade_pernoites),
    coberturaBase: Boolean(mission?.cobertura_base || calculation?.cobertura_base),
    tipoPernoite: numericValue(mission?.quantidade_pernoites || calculation?.quantidade_pernoites) <= 0
      ? "sem_pernoite"
      : Boolean(mission?.cobertura_base || calculation?.cobertura_base)
        ? "cobertura_base"
        : "pernoite_comum",
    pernoitesRemuneraveis: Boolean(mission?.cobertura_base || calculation?.cobertura_base)
      ? 0
      : remunerableOvernightCount(mission?.quantidade_pernoites || calculation?.quantidade_pernoites),
    valorPernoiteComumTotal: numericValue(calculation?.valor_pernoite_comum),
    operacaoEspecial: normalizeText(mission?.operacao_especial || calculation?.operacao_especial),
    justificativa: normalizeText(mission?.justificativa || calculation?.justificativa || calculation?.motivo || ""),
    observacao: normalizeText(mission?.observacoes || calculation?.observacoes || calculation?.observacao),
    tipo: normalizeText(calculation?.tipo || calculation?.categoria_aplicavel || mission?.categoria_financeira_aeronave || "VD"),
    diurna: numericValue(calculation?.minutos_diurnos),
    noturna: numericValue(calculation?.minutos_noturnos_reais || calculation?.minutos_noturnos),
    preCalcMin: numericValue(calculation?.minutos_pre || calculation?.jornada_total_minutos),
    posCalc: numericValue(calculation?.minutos_pos || calculation?.jornada_total_minutos),
    total: numericValue(calculation?.total || calculation?.valor_total || calculation?.total_devido),
    missionStatus: normalizeText(mission?.status || "ativa"),
    calculationStatus: normalizeText(calculation?.status || mission?.status || "pendente"),
    status: normalizeText(calculation?.status || mission?.status || "pendente"),
    isDomingo: Boolean(calculation?.domingo || calculation?.domingo_feriado),
    isFeriado: Boolean(calculation?.feriado || calculation?.domingo_feriado),
    hasException: Boolean(calculation?.pendencias?.length || calculation?.warnings?.length || calculation?.bloqueios?.length),
    sourceMission: mission || {},
    sourceCalculation: calculation || {},
  };
}

function rowsFromMissions({ missions, hourlyItems, tripulantesById, equipamentosById }) {
  const calculationsByMission = new Map();
  hourlyItems.forEach((item) => {
    const missionId = missionIdFromCalculation(item);
    if (!missionId) return;
    if (!calculationsByMission.has(missionId)) calculationsByMission.set(missionId, []);
    calculationsByMission.get(missionId).push(item);
  });

  const rows = [];
  missions.forEach((mission, missionIndex) => {
    const missionId = Number(mission?.id || 0) || 0;
    const calculations = calculationsByMission.get(missionId) || [];
    if (calculations.length) {
      calculations.forEach((calculation, calculationIndex) => {
        rows.push(rowFromMissionAndCalculation({
          mission,
          calculation,
          funcao: calculation?.funcao,
          tripulanteId: tripulanteIdFromCalculation(calculation),
          tripulanteNome: calculationTripulanteName(calculation, tripulantesById),
          index: rows.length + calculationIndex,
          equipamentosById,
        }));
      });
      return;
    }

    [
      ["comandante", mission?.comandante_tripulante_id],
      ["copiloto", mission?.copiloto_tripulante_id],
    ].forEach(([funcao, tripulanteId], crewIndex) => {
      if (!tripulanteId) return;
      rows.push(rowFromMissionAndCalculation({
        mission,
        calculation: null,
        funcao,
        tripulanteId,
        tripulanteNome: missionParticipantName(mission, funcao, tripulantesById),
        index: rows.length + crewIndex + missionIndex,
        equipamentosById,
      }));
    });
  });
  return rows;
}

function rowsFromOrphanCalculations({ hourlyItems, tripulantesById, equipamentosById, knownMissionIds, startIndex }) {
  return hourlyItems
    .filter((item) => !knownMissionIds.has(missionIdFromCalculation(item)))
    .map((item, index) => rowFromMissionAndCalculation({
      mission: null,
      calculation: item,
      funcao: item?.funcao,
      tripulanteId: tripulanteIdFromCalculation(item),
      tripulanteNome: calculationTripulanteName(item, tripulantesById),
      index: startIndex + index,
      equipamentosById,
    }));
}

function rowMatchesFilters(row, { funcao = "", tripulanteId = "" } = {}) {
  const requestedFuncao = normalizeLower(funcao);
  const requestedTripulante = Number(tripulanteId || 0) || 0;
  if (requestedFuncao && normalizeLower(row.funcao) !== requestedFuncao) return false;
  if (requestedTripulante && Number(row.tripulanteId || 0) !== requestedTripulante) return false;
  return true;
}

function indicatorsFromRows(rows, productivityItems) {
  const productivityTotal = productivityItems.reduce((sum, item) => sum + numericValue(item?.total_devido), 0);
  const hourlyTotal = rows.reduce((sum, row) => sum + numericValue(row.total), 0);
  const reducedHours = rows.reduce((sum, row) => sum + numericValue(row.posCalc), 0) / 60;
  return {
    totalGeral: hourlyTotal + productivityTotal,
    linhas: rows.length,
    horaReduzida: reducedHours,
    excecoes: rows.filter((row) => row.hasException).length,
    alertasDescanso: rows.filter((row) => numericValue(row.posExecMin) > 0).length,
    domingos: rows.filter((row) => row.isDomingo).length,
    feriados: rows.filter((row) => row.isFeriado).length,
    valorNormal: hourlyTotal,
  };
}

function normalizePeriodStatus(periodPayload) {
  const status = normalizeLower(periodPayload?.competencia?.status || periodPayload?.status);
  return status || "aberta";
}

export async function listFinanceiroJornadaOptions() {
  const [tripulantesPayload, equipamentosPayload] = await Promise.all([
    listFinanceiroTripulanteOptions(),
    listFinanceiroEquipamentoOptions(),
  ]);
  const equipamentos = Array.isArray(equipamentosPayload?.options)
    ? equipamentosPayload.options
    : (Array.isArray(equipamentosPayload?.items) ? equipamentosPayload.items : []);
  return {
    tripulantes: Array.isArray(tripulantesPayload?.items) ? tripulantesPayload.items : [],
    equipamentos,
  };
}

export async function getFinanceiroJornadaGrade({ competencia, funcao = "", tripulanteId = "" } = {}) {
  const queryString = compactParams({
    competencia,
    funcao,
    tripulante_id: tripulanteId,
    page_size: 500,
  });
  const [options, payload] = await Promise.all([
    listFinanceiroJornadaOptions(),
    api(`${FINANCEIRO_JORNADA_API}?${queryString}`).then(({ data }) => data),
  ]);
  const rows = (payload.linhas || []).map(rowFromNativeLine);
  return {
    rows,
    indicators: indicatorsFromNative(payload.indicadores || {}),
    context: {
      competencia: payload.contexto?.competencia || competencia,
      funcao: payload.contexto?.funcao_operacional || funcao || "Todos",
      tripulanteId: Number(payload.contexto?.tripulante_id || tripulanteId || 0) || 0,
      tripulantes: Number(payload.contexto?.tripulantes || 0) || 0,
      resultadoAtual: numericValue(payload.contexto?.resultado_atual),
      statusCompetencia: payload.contexto?.status_competencia || payload.status_competencia || "aberta",
      preflight: payload.contexto?.preflight || null,
    },
    options,
    missionsPayload: { items: rows.map((row) => row.sourceMission).filter(Boolean) },
    hourlyPayload: { items: rows.map((row) => row.sourceCalculation).filter(Boolean) },
    productivityPayload: { items: Array.isArray(payload.produtividade) ? payload.produtividade : [] },
    periodPayload: { status: payload.status_competencia, competencia: { status: payload.status_competencia } },
    capabilities: JORNADA_API_CAPABILITIES,
  };
}

export async function previewFinanceiroJornadaLinha(rowPayload) {
  const { data } = await api(`${FINANCEIRO_JORNADA_API}/preview`, {
    method: "POST",
    json: rowPayload,
    timeoutMs: 15000,
  });
  return data;
}

export async function updateFinanceiroJornadaLinha(row) {
  const lineId = Number(row?.lineId || row?.linhaId || row?.id || 0) || 0;
  if (!lineId) return createFinanceiroJornadaLinha(row?.payload || row);
  const { data } = await api(`${FINANCEIRO_JORNADA_API}/${lineId}`, {
    method: "PATCH",
    json: row.payload || row,
  });
  return data;
}

export async function createFinanceiroJornadaLinha(payload) {
  const { data } = await api(FINANCEIRO_JORNADA_API, {
    method: "POST",
    json: payload,
  });
  return data;
}

export async function recalculateFinanceiroJornadaLinha(lineId) {
  const { data } = await api(`${FINANCEIRO_JORNADA_API}/${Number(lineId)}/recalcular`, {
    method: "POST",
    json: {},
  });
  return data;
}

export async function recalculateFinanceiroJornadaGrade(competencia, filters = {}) {
  const { data } = await api(`${FINANCEIRO_JORNADA_API}/recalcular-grade`, {
    method: "POST",
    json: {
      competencia,
      funcao: filters.funcao || "",
      tripulante_id: filters.tripulanteId || filters.tripulante_id || "",
    },
  });
  return data;
}

export async function downloadFinanceiroJornadaPdf(filtersOrCompetencia) {
  const filters = typeof filtersOrCompetencia === "string"
    ? { competencia: filtersOrCompetencia }
    : (filtersOrCompetencia || {});
  const filename = `lancamentos-jornada-${filters.competencia || "competencia"}.pdf`;
  const queryString = compactParams({
    competencia: filters.competencia,
    funcao: filters.funcao || "",
    tripulante_id: filters.tripulanteId || filters.tripulante_id || "",
    status: filters.status || "",
  });
  const { response, data } = await api(`${FINANCEIRO_JORNADA_API}.pdf?${queryString}`, {
    headers: {
      Accept: "application/pdf",
      "X-Requested-With": "XMLHttpRequest",
    },
    timeoutMs: 120000,
  });
  ensurePdfContentType(response, data, "PDF da grade de jornada");
  return {
    blob: await ensurePdfBlob(data, "PDF da grade de jornada"),
    filename: filenameFromContentDisposition(response.headers.get("Content-Disposition"), filename),
  };
}

export function financeiroJornadaPdfHref(filtersOrCompetencia) {
  const filters = typeof filtersOrCompetencia === "string"
    ? { competencia: filtersOrCompetencia }
    : (filtersOrCompetencia || {});
  const queryString = compactParams({
    competencia: filters.competencia,
    funcao: filters.funcao || "",
    tripulante_id: filters.tripulanteId || filters.tripulante_id || "",
    status: filters.status || "",
  });
  return apiHref(`${FINANCEIRO_JORNADA_API}.pdf?${queryString}`);
}

export function financeiroRelatorioIndividualPdfHref({
  tipo,
  competencia,
  tripulanteId,
  funcao = "",
  status = "",
  incluirObsoletos = false,
} = {}) {
  const queryString = compactParams({
    tipo: String(tipo || "").trim(),
    competencia,
    tripulante_id: tripulanteId,
    funcao,
    status,
    incluir_obsoletos: incluirObsoletos ? "1" : "",
    formato: "pdf",
  });
  return apiHref(`${FINANCEIRO_RELATORIO_INDIVIDUAL_API}?${queryString}`);
}

export async function getFinanceiroProdutividadeConsolidado(filters = {}) {
  const queryString = compactParams({
    competencia: filters.competencia,
    funcao: filters.funcao || "",
    tripulante_id: filters.tripulanteId || filters.tripulante_id || "",
  });
  const { data } = await api(`${FINANCEIRO_PRODUTIVIDADE_CONSOLIDADO_API}?${queryString}`);
  return data;
}

export async function getFinanceiroProdutividadeRelatorioGeral(filters = {}) {
  const normalized = normalizeHorasTotaisVoadasFilters(filters);
  const queryString = compactParams({
    competencia: normalized.competencia,
    funcao: normalized.funcao,
    org_id: filters.orgId || filters.org_id || "",
    incluir_zerados: filters.incluirZerados ?? filters.incluir_zerados ?? "",
    categoria: filters.categoria || "",
  });
  const { data } = await api(`${FINANCEIRO_PRODUTIVIDADE_RELATORIO_GERAL_API}?${queryString}`);
  return data;
}

export async function getFinanceiroExtratoPeriodo(filters = {}) {
  const queryString = compactParams({
    data_inicio: filters.dataInicio || filters.data_inicio || "",
    data_fim: filters.dataFim || filters.data_fim || "",
    tripulante_id: filters.tripulanteId || filters.tripulante_id || "",
    funcao: filters.funcao || "",
    tipo: filters.tipo || "ambos",
  });
  const { data } = await api(`${FINANCEIRO_EXTRATO_PERIODO_API}?${queryString}`);
  return data;
}

export async function getFinanceiroHorasTotaisVoadas(filters = {}) {
  const normalized = normalizeHorasTotaisVoadasFilters(filters);
  const queryString = compactParams({
    competencia: normalized.competencia,
    funcao: normalized.funcao,
    org_id: filters.orgId || filters.org_id || "",
    incluir_zerados: filters.incluirZerados ?? filters.incluir_zerados ?? "",
  });
  const { data } = await api(`${FINANCEIRO_HORAS_TOTAIS_VOADAS_API}?${queryString}`);
  return data;
}

export async function downloadFinanceiroExtratoPeriodoPdf(filters = {}) {
  const filename = `extrato-periodo-${filters.dataInicio || filters.data_inicio || "inicio"}-${filters.dataFim || filters.data_fim || "fim"}.pdf`;
  const queryString = compactParams({
    data_inicio: filters.dataInicio || filters.data_inicio || "",
    data_fim: filters.dataFim || filters.data_fim || "",
    tripulante_id: filters.tripulanteId || filters.tripulante_id || "",
    funcao: filters.funcao || "",
    tipo: filters.tipo || "ambos",
  });
  const { response, data } = await api(`${FINANCEIRO_EXTRATO_PERIODO_API}.pdf?${queryString}`, {
    headers: {
      Accept: "application/pdf",
      "X-Requested-With": "XMLHttpRequest",
    },
    timeoutMs: 120000,
  });
  ensurePdfContentType(response, data, "PDF do extrato por periodo");
  return {
    blob: await ensurePdfBlob(data, "PDF do extrato por periodo"),
    filename: filenameFromContentDisposition(response.headers.get("Content-Disposition"), filename),
  };
}

export function financeiroExtratoPeriodoPdfHref(filters = {}) {
  const queryString = compactParams({
    data_inicio: filters.dataInicio || filters.data_inicio || "",
    data_fim: filters.dataFim || filters.data_fim || "",
    tripulante_id: filters.tripulanteId || filters.tripulante_id || "",
    funcao: filters.funcao || "",
    tipo: filters.tipo || "ambos",
  });
  return apiHref(`${FINANCEIRO_EXTRATO_PERIODO_API}.pdf?${queryString}`);
}

export async function downloadFinanceiroHorasTotaisVoadasPdf(filters = {}) {
  const normalized = normalizeHorasTotaisVoadasFilters(filters);
  const filename = financeiroHorasTotaisVoadasFilename(normalized);
  const queryString = compactParams({
    competencia: normalized.competencia,
    funcao: normalized.funcao,
    org_id: filters.orgId || filters.org_id || "",
  });
  const { response, data } = await api(`${FINANCEIRO_HORAS_TOTAIS_VOADAS_API}.pdf?${queryString}`, {
    headers: {
      Accept: "application/pdf",
      "X-Requested-With": "XMLHttpRequest",
    },
    timeoutMs: 120000,
  });
  ensurePdfContentType(response, data, "PDF do relatorio geral de horas totais voadas");
  return {
    blob: await ensurePdfBlob(data, "PDF do relatorio geral de horas totais voadas"),
    filename,
  };
}

export async function downloadFinanceiroProdutividadeRelatorioGeralPdf(filters = {}) {
  const normalized = normalizeHorasTotaisVoadasFilters(filters);
  const filename = financeiroProdutividadeRelatorioGeralFilename(normalized);
  const queryString = compactParams({
    competencia: normalized.competencia,
    funcao: normalized.funcao,
    org_id: filters.orgId || filters.org_id || "",
    categoria: filters.categoria || "",
  });
  const { response, data } = await api(`${FINANCEIRO_PRODUTIVIDADE_RELATORIO_GERAL_API}.pdf?${queryString}`, {
    headers: {
      Accept: "application/pdf",
      "X-Requested-With": "XMLHttpRequest",
    },
    timeoutMs: 120000,
  });
  ensurePdfContentType(response, data, "PDF do relatorio geral de produtividade");
  return {
    blob: await ensurePdfBlob(data, "PDF do relatorio geral de produtividade"),
    filename,
  };
}

export async function downloadFinanceiroJornadaRelatorioIndividual(payload) {
  return downloadFinanceiroRelatorioIndividual(payload);
}
