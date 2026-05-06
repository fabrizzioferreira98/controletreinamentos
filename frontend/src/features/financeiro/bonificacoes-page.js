import {
  buildErrorMessage,
  capabilitySet,
  emptyTableRowMarkup,
  escapeAttr,
  escapeHtml,
  formatCompetenciaLabel,
  formatCurrencyBr,
  formatDateBr,
  renderInlineFeedback,
  responsiveStateMarkup,
  routePath,
  showFlash,
  withActionBusy,
} from "../../lib.js";
import { renderShell } from "../../shell.js";
import {
  downloadFinanceiroExtratoPeriodoPdf,
  downloadFinanceiroHorasTotaisVoadasPdf,
  downloadFinanceiroJornadaPdf,
  downloadFinanceiroJornadaRelatorioIndividual,
  downloadFinanceiroProdutividadeRelatorioGeralPdf,
  financeiroHorasTotaisVoadasFilename,
  financeiroProdutividadeRelatorioGeralFilename,
  getFinanceiroHorasTotaisVoadas,
  getFinanceiroProdutividadeConsolidado,
  getFinanceiroProdutividadeRelatorioGeral,
  getFinanceiroJornadaGrade,
  JORNADA_API_CAPABILITIES,
  listFinanceiroJornadaOptions,
  previewFinanceiroJornadaLinha,
  recalculateFinanceiroJornadaGrade,
  createFinanceiroJornadaLinha,
  getFinanceiroExtratoPeriodo,
  updateFinanceiroJornadaLinha,
} from "../../services/financeiro-lancamentos-jornada-api.js";

const FINANCEIRO_JORNADA_ROUTE = "#/financeiro/lancamentos-jornada";
const FINANCEIRO_BONUS_LEGACY_ROUTE = "#/financeiro/bonificacoes";
const FINANCEIRO_PRODUTIVIDADE_LEGACY_ROUTE = "#/financeiro/bonificacoes/produtividade";
const BONUS_READ_PERMISSION = "finance:bonuses:read";
const EXPORT_CREATE_PERMISSION = "finance:exports:create";
const PERIOD_RECALCULATE_PERMISSION = "finance:periods:recalculate";
const MISSION_UPDATE_PERMISSION = "finance:missions:update";
const MISSION_CREATE_PERMISSION = "finance:missions:create";
const PREVIEW_DEBOUNCE_MS = 520;
const JORNADA_TABLE_COLSPAN = 28;
const PDF_OBJECT_URL_REVOKE_MS = 120000;
const GENERAL_HOURS_PENDING_MESSAGE = "Existem lançamentos sem cálculo persistido. Recalcule a grade antes de exportar o relatório financeiro.";
const GENERAL_PRODUCTIVITY_PENDING_MESSAGE = "Existem inconsistências na memória de produtividade persistida. Recalcule a grade antes de exportar o relatório financeiro.";

const DEFAULT_INDICATORS = Object.freeze({
  totalGeral: 0,
  linhas: 0,
  horaReduzida: 0,
  excecoes: 0,
  alertasDescanso: 0,
  domingos: 0,
  feriados: 0,
  valorNormal: 0,
});

let jornadaState = createInitialState();
let previewTimers = new Map();
let previewRequestSeq = 0;
let gridPreviewRequestSeq = 0;
let gradeRequestSeq = 0;

function currentCompetencia() {
  return new Date().toISOString().slice(0, 7);
}

function isLegacyBonusRoute() {
  return routePath().startsWith(FINANCEIRO_BONUS_LEGACY_ROUTE);
}

function isProductivityCompatibilityRoute() {
  return routePath() === FINANCEIRO_PRODUTIVIDADE_LEGACY_ROUTE;
}

function createInitialState() {
  return {
    filters: {
      competencia: currentCompetencia(),
      funcao: "",
      tripulanteId: "",
    },
    status: "initial",
    rows: [],
    context: null,
    indicators: { ...DEFAULT_INDICATORS },
    options: {
      tripulantes: [],
      equipamentos: [],
    },
    optionsStatus: "idle",
    hourlyPayload: null,
    productivityPayload: null,
    periodPayload: null,
    message: "",
    editingRowKey: "",
    draftRows: {},
    rowErrors: {},
    rowPreview: {},
    activeInsight: "",
    productivityConsolidado: null,
    productivityConsolidadoStatus: "idle",
    productivityConsolidadoError: "",
    extractFilters: null,
    extractPayload: null,
    extractStatus: "idle",
    extractError: "",
    extractExportStatus: "idle",
    generalHoursReportFilters: null,
    generalHoursReportStatus: "idle",
    generalHoursReportMessage: "",
    generalHoursReportKey: "",
    generalProductivityReportFilters: null,
    generalProductivityReportStatus: "idle",
    generalProductivityReportMessage: "",
    generalProductivityReportKey: "",
    recalculateStatus: "idle",
    exportStatus: "idle",
    reportStatus: "idle",
    reportKey: "",
  };
}

function normalizeText(value) {
  return String(value ?? "").trim();
}

function normalizeLower(value) {
  return normalizeText(value).toLowerCase();
}

function formatAny(value, fallback = "-") {
  const text = normalizeText(value);
  return text || fallback;
}

function numberValue(value) {
  const amount = Number(value ?? 0);
  return Number.isFinite(amount) ? amount : 0;
}

function nonNegativeNumber(value) {
  const amount = Number(value ?? 0);
  if (!Number.isFinite(amount)) return 0;
  return amount < 0 ? 0 : amount;
}

function formatMinutes(value) {
  const amount = numberValue(value);
  return `${amount.toLocaleString("pt-BR", { maximumFractionDigits: 0 })} min`;
}

function formatHours(value) {
  const amount = numberValue(value);
  return `${amount.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} h`;
}

function statusClass(value) {
  const normalized = normalizeLower(value);
  if (["calculado", "recalculada", "salvo", "ativa", "aberta"].includes(normalized)) return "status-green";
  if (["pendente", "rascunho", "em_edicao"].includes(normalized)) return "status-yellow";
  if (["cancelada", "bloqueada", "erro", "fechada"].includes(normalized)) return "status-red";
  return "status-gray";
}

function hasPermission(permission) {
  return capabilitySet().has(permission);
}

function canReadJornada() {
  return hasPermission(BONUS_READ_PERMISSION);
}

function canEditJornada() {
  return hasPermission(MISSION_UPDATE_PERMISSION) || hasPermission(MISSION_CREATE_PERMISSION);
}

function canRecalculateJornada() {
  return hasPermission(PERIOD_RECALCULATE_PERMISSION);
}

function optionsReady() {
  return jornadaState.optionsStatus === "ready" ||
    jornadaState.options.tripulantes.length ||
    jornadaState.options.equipamentos.length;
}

function isCompetenciaClosed() {
  return normalizeLower(jornadaState.context?.statusCompetencia) === "fechada";
}

function isBusy() {
  return ["loading"].includes(jornadaState.status) ||
    jornadaState.recalculateStatus === "loading" ||
    jornadaState.exportStatus === "loading" ||
    jornadaState.reportStatus === "loading" ||
    jornadaState.generalHoursReportStatus === "exporting" ||
    jornadaState.generalProductivityReportStatus === "exporting" ||
    jornadaState.extractStatus === "loading" ||
    jornadaState.extractExportStatus === "loading";
}

function saveValidatedPdfDownload({ blob, filename }, fallbackFilename) {
  if (!(blob instanceof Blob) || !blob.size) {
    throw new Error("PDF vazio ou indisponivel.");
  }
  const safeFilename = normalizeText(filename) || fallbackFilename || "relatorio-financeiro.pdf";
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = safeFilename;
  link.rel = "noopener";
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  window.setTimeout(() => {
    link.remove();
  }, 1000);
  window.setTimeout(() => {
    URL.revokeObjectURL(url);
  }, PDF_OBJECT_URL_REVOKE_MS);
}

function downloadValidatedPdf(result, fallbackFilename) {
  if (!(result?.blob instanceof Blob) || !result.blob.size) {
    throw new Error("PDF vazio ou indisponivel.");
  }
  const filename = normalizeText(result.filename) || fallbackFilename || "relatorio-financeiro.pdf";
  saveValidatedPdfDownload(result, filename);
}

function firstDayFromCompetencia(competencia) {
  const value = normalizeText(competencia) || currentCompetencia();
  return `${value}-01`;
}

function lastDayFromCompetencia(competencia) {
  const value = normalizeText(competencia) || currentCompetencia();
  const [year, month] = value.split("-").map((part) => Number(part));
  if (!year || !month) return `${value}-31`;
  const last = new Date(year, month, 0).getDate();
  return `${value}-${String(last).padStart(2, "0")}`;
}

function defaultExtractFilters() {
  return {
    dataInicio: firstDayFromCompetencia(jornadaState.filters.competencia),
    dataFim: lastDayFromCompetencia(jornadaState.filters.competencia),
    tripulanteId: jornadaState.filters.tripulanteId || "",
    funcao: jornadaState.filters.funcao || "",
    tipo: "ambos",
  };
}

function rowValue(row, key, fallback = "") {
  const value = row?.[key];
  return value === null || value === undefined ? fallback : value;
}

function buildRowDraft(row) {
  const sourceMission = row.sourceMission || {};
  const funcao = normalizeLower(row.funcao || jornadaState.filters.funcao);
  const filterTripulanteId = normalizeText(jornadaState.filters.tripulanteId);
  const rowTripulanteId = normalizeText(row.tripulanteId);
  const comandanteTripulanteId = normalizeText(
    row.comandanteTripulanteId ||
      row.comandante_tripulante_id ||
      sourceMission.comandante_tripulante_id ||
      (funcao === "comandante" ? rowTripulanteId || filterTripulanteId : ""),
  );
  const copilotoTripulanteId = normalizeText(
    row.copilotoTripulanteId ||
      row.copiloto_tripulante_id ||
      sourceMission.copiloto_tripulante_id ||
      (funcao === "copiloto" ? rowTripulanteId || filterTripulanteId : ""),
  );
  return syncCrewSelectionOnLine({
    key: row.key || "new",
    isNew: Boolean(row.isNew),
    lineId: row.lineId || row.id || 0,
    missionId: row.missionId || 0,
    competencia: row.competencia || jornadaState.filters.competencia || currentCompetencia(),
    data: row.data || firstDayFromCompetencia(jornadaState.filters.competencia),
    dataFinal: row.dataFinal || row.sourceMission?.data_final || row.data || firstDayFromCompetencia(jornadaState.filters.competencia),
    tripulanteId: row.tripulanteId || filterTripulanteId || "",
    tripulanteNome: row.tripulanteNome || "",
    funcao: row.funcao || "",
    comandanteTripulanteId,
    comandanteTripulanteNome: row.comandanteTripulanteNome || tripulanteNameById(comandanteTripulanteId),
    copilotoTripulanteId,
    copilotoTripulanteNome: row.copilotoTripulanteNome || tripulanteNameById(copilotoTripulanteId),
    aeronaveId: row.aeronaveId || "",
    aeronave: row.aeronave || "",
    categoriaFinanceiraAeronave: row.categoriaFinanceiraAeronave || row.sourceMission?.categoria_financeira_aeronave || row.tipo || "",
    equipmentType: row.equipmentType || "",
    aircraftRaw: row.aircraftRaw || null,
    aircraftCleared: Boolean(row.aircraftCleared),
    relVoo: row.relVoo || "",
    numeroDb: row.numeroDb || "",
    contratante: row.contratante || row.sourceMission?.contratante || "",
    trecho: row.trecho || "",
    apresentacao: row.apresentacao || "",
    abandono: row.abandono || "",
    posExecMin: row.posExecMin || "0",
    quantidadePernoites: row.quantidadePernoites ?? row.sourceMission?.quantidade_pernoites ?? "0",
    coberturaBase: Boolean(row.coberturaBase ?? row.sourceMission?.cobertura_base),
    pernoitesRemuneraveis: row.pernoitesRemuneraveis || 0,
    valorPernoiteComumTotal: row.valorPernoiteComumTotal || 0,
    operacaoEspecial: row.operacaoEspecial || row.sourceMission?.operacao_especial || "",
    justificativa: row.justificativa || "",
    observacao: row.observacao || "",
    tipo: row.tipo || "",
    diurna: row.diurna || 0,
    noturna: row.noturna || 0,
    preCalcMin: row.preCalcMin || 0,
    posCalc: row.posCalc || 0,
    sourceMission,
  });
}

function pernoiteTypeFromValues(quantidadePernoites, coberturaBase) {
  const quantidade = nonNegativeNumber(quantidadePernoites);
  if (quantidade <= 0) return "sem_pernoite";
  return coberturaBase ? "cobertura_base" : "pernoite_comum";
}

function pernoiteSummaryMarkup(row) {
  const quantidade = nonNegativeNumber(row.quantidadePernoites);
  const tipo = row.tipoPernoite || pernoiteTypeFromValues(quantidade, row.coberturaBase);
  if (tipo === "sem_pernoite") {
    return `<strong>Sem pernoite</strong><small>0 informado</small>`;
  }
  if (tipo === "cobertura_base") {
    return `<strong>Cobertura de base</strong><small>${escapeHtml(String(quantidade))} por pernoite</small>`;
  }
  const remuneraveis = nonNegativeNumber(row.pernoitesRemuneraveis ?? quantidade - 1);
  const total = Number(row.valorPernoiteComumTotal || 0) || 0;
  const detail = total > 0
    ? `${remuneraveis} remuneravel(is) · ${formatCurrencyBr(total)}`
    : `${remuneraveis} remuneravel(is) · parametro pendente`;
  return `<strong>Pernoite comum</strong><small>${escapeHtml(detail)}</small>`;
}

function findRow(key) {
  if (key === "new") return buildRowDraft(jornadaState.draftRows.new || { key: "new", isNew: true });
  return jornadaState.rows.find((row) => row.key === key) || null;
}

function optionName(option) {
  return normalizeText(option?.nome || option?.name || option?.label || option?.display || option?.display_name || option?.prefixo || option?.matricula);
}

function tripulanteOptionsMarkup(selectedId) {
  const selected = Number(selectedId || 0) || 0;
  const known = new Set();
  const options = jornadaState.options.tripulantes
    .map((item) => {
      const id = Number(item?.id || 0) || 0;
      if (!id) return "";
      known.add(id);
      return `<option value="${escapeAttr(id)}" ${id === selected ? "selected" : ""}>${escapeHtml(optionName(item) || `ID ${id}`)}</option>`;
    })
    .join("");
  const selectedFallback = selected && !known.has(selected)
    ? `<option value="${escapeAttr(selected)}" selected>ID ${escapeHtml(selected)}</option>`
    : "";
  return `<option value="">Selecione</option>${selectedFallback}${options}`;
}

function tripulanteNameById(tripulanteId) {
  const selected = Number(tripulanteId || 0) || 0;
  if (!selected) return "";
  const item = jornadaState.options.tripulantes.find((option) => Number(option?.id || 0) === selected);
  return optionName(item) || `ID ${selected}`;
}

function equipamentoOptionsMarkup(selectedId) {
  const selected = Number(selectedId || 0) || 0;
  const known = new Set();
  const options = jornadaState.options.equipamentos
    .map((item) => {
      const raw = item?.raw || {};
      const id = Number(item?.id || item?.value || item?.equipamento_id || raw?.id || 0) || 0;
      if (!id) return "";
      known.add(id);
      const name = optionName(item) || optionName(raw);
      const equipmentType = normalizeText(item?.tipo || raw?.tipo || item?.modelo || raw?.modelo || item?.equipamento);
      const label = normalizeText(item?.label || item?.display || [name, equipmentType].filter(Boolean).join(" / ")) || `ID ${id}`;
      const category = normalizeText(
        item?.categoria_financeira ||
        item?.categoria_financeira_aeronave ||
        item?.categoria ||
        item?.category ||
        raw?.categoria_financeira ||
        raw?.categoria,
      );
      return `<option value="${escapeAttr(id)}" data-category="${escapeAttr(category)}" data-equipment-label="${escapeAttr(label)}" data-equipment-name="${escapeAttr(name)}" data-equipment-type="${escapeAttr(equipmentType)}" ${id === selected ? "selected" : ""}>${escapeHtml(label)}</option>`;
    })
    .join("");
  const selectedFallback = selected && !known.has(selected)
    ? `<option value="${escapeAttr(selected)}" selected>ID ${escapeHtml(selected)}</option>`
    : "";
  return `<option value="">Selecione</option>${selectedFallback}${options}`;
}

function uniqueFunctionOptions() {
  const values = new Set(["comandante", "copiloto"]);
  jornadaState.rows.forEach((row) => {
    const value = normalizeLower(row.funcao);
    if (value) values.add(value);
  });
  return Array.from(values);
}

function functionOptionsMarkup(selectedValue, includeEmpty = false) {
  const selected = normalizeLower(selectedValue);
  const options = uniqueFunctionOptions()
    .map((value) => `<option value="${escapeAttr(value)}" ${selected === value ? "selected" : ""}>${escapeHtml(functionLabel(value))}</option>`)
    .join("");
  return `${includeEmpty ? '<option value="">Todos</option>' : '<option value="">Selecione</option>'}${options}`;
}

function functionLabel(value) {
  const normalized = normalizeLower(value);
  const labels = {
    comandante: "Comandante",
    copiloto: "Copiloto",
    instrutor: "Instrutor",
    checador: "Checador",
    pt: "PT",
    cpp: "CPP",
  };
  return labels[normalized] || formatAny(value, "Operacional");
}

function generalHoursFunctionLabel(value) {
  return normalizeLower(value) === "copiloto" ? "Copilotos" : "Comandantes";
}

function normalizeGeneralHoursFunction(value) {
  const normalized = normalizeLower(value).replace(/s$/, "");
  if (normalized === "copiloto") return "copiloto";
  return "comandante";
}

function defaultGeneralHoursReportFilters() {
  return {
    competencia: jornadaState.generalHoursReportFilters?.competencia || jornadaState.filters.competencia || currentCompetencia(),
    funcao: normalizeGeneralHoursFunction(jornadaState.generalHoursReportFilters?.funcao || jornadaState.filters.funcao || "comandante"),
  };
}

function defaultGeneralProductivityReportFilters() {
  return {
    competencia: jornadaState.generalProductivityReportFilters?.competencia || jornadaState.filters.competencia || currentCompetencia(),
    funcao: normalizeGeneralHoursFunction(jornadaState.generalProductivityReportFilters?.funcao || jornadaState.filters.funcao || "comandante"),
  };
}

function generalHoursFunctionOptionsMarkup(selectedValue) {
  const selected = normalizeGeneralHoursFunction(selectedValue);
  return ["comandante", "copiloto"]
    .map((value) => `<option value="${escapeAttr(value)}" ${selected === value ? "selected" : ""}>${escapeHtml(generalHoursFunctionLabel(value))}</option>`)
    .join("");
}

function generalHoursRowsFromPayload(payload) {
  if (Array.isArray(payload?.linhas)) return payload.linhas;
  if (Array.isArray(payload?.items)) return payload.items;
  if (Array.isArray(payload?.data?.linhas)) return payload.data.linhas;
  return [];
}

function generalHoursPayloadHasPendingCalculations(payload) {
  const rows = generalHoursRowsFromPayload(payload);
  if (rows.some((row) => Boolean(row?.possui_pendencias) || (Array.isArray(row?.pendencias) && row.pendencias.length))) {
    return true;
  }
  const pendingCollections = [
    payload?.pendencias,
    payload?.data?.pendencias,
    payload?.contexto?.pendencias,
    payload?.totais?.pendencias,
  ];
  return pendingCollections.some((items) => Array.isArray(items) ? items.length > 0 : Boolean(items));
}

function productivityGeneralRowsFromPayload(payload) {
  if (Array.isArray(payload?.items)) return payload.items;
  if (Array.isArray(payload?.data?.items)) return payload.data.items;
  if (Array.isArray(payload?.linhas)) return payload.linhas;
  return [];
}

function productivityGeneralPayloadHasPendingCalculations(payload) {
  const rows = productivityGeneralRowsFromPayload(payload);
  if (rows.some((row) => Boolean(row?.possui_pendencias) || (Array.isArray(row?.pendencias) && row.pendencias.length))) {
    return true;
  }
  const pendingCollections = [
    payload?.pendencias,
    payload?.data?.pendencias,
    payload?.contexto?.pendencias,
    payload?.totais?.pendencias,
  ];
  if (pendingCollections.some((items) => Array.isArray(items) ? items.length > 0 : Boolean(items))) return true;
  return Boolean(payload?.totais?.possui_pendencias);
}

function normalizeErrorLookup(value) {
  return normalizeLower(value)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

function isGeneralHoursPendingError(error) {
  const code = normalizeErrorLookup(error?.code);
  const message = normalizeErrorLookup(error?.message);
  return code.includes("pendencia") ||
    code.includes("calculo_persistido") ||
    code.includes("calculo_horario_pendente") ||
    message.includes("calculo persistido") ||
    message.includes("lancamentos sem calculo");
}

function classifyGeneralHoursReportError(error) {
  const code = normalizeErrorLookup(error?.code);
  const message = normalizeErrorLookup(error?.message);
  if (isGeneralHoursPendingError(error)) {
    return { status: "pending", message: GENERAL_HOURS_PENDING_MESSAGE };
  }
  if (error?.status === 403) {
    return { status: "permission", message: buildErrorMessage(error) };
  }
  if (error?.status === 404 || error?.status === 204 || code.includes("no_data") || code.includes("sem_dados") || message.includes("sem dados")) {
    return {
      status: "empty",
      message: "Não há dados consolidados para a competência e função selecionadas.",
    };
  }
  return {
    status: "error",
    message: buildErrorMessage(error),
  };
}

function isGeneralProductivityPendingError(error) {
  const code = normalizeErrorLookup(error?.code);
  const message = normalizeErrorLookup(error?.message);
  return code.includes("finance_productivity_general_report_pending_calculations") ||
    code.includes("pendencia") ||
    code.includes("produtividade") && code.includes("pending") ||
    message.includes("memoria de produtividade") ||
    message.includes("calculo persistido") ||
    message.includes("recalcule a grade");
}

function classifyGeneralProductivityReportError(error) {
  const code = normalizeErrorLookup(error?.code);
  const message = normalizeErrorLookup(error?.message);
  if (isGeneralProductivityPendingError(error)) {
    return { status: "pending", message: GENERAL_PRODUCTIVITY_PENDING_MESSAGE };
  }
  if (error?.status === 403) {
    return { status: "permission", message: buildErrorMessage(error) };
  }
  if (error?.status === 404 || error?.status === 204 || code.includes("no_data") || code.includes("sem_dados") || message.includes("sem dados")) {
    return {
      status: "empty",
      message: "Não há produtividade consolidada para a competência e função selecionadas.",
    };
  }
  return {
    status: "error",
    message: buildErrorMessage(error),
  };
}

function addReportTripulanteEntry(entries, id, label) {
  const normalizedId = normalizeText(id);
  if (!normalizedId) return;
  const normalizedLabel = formatAny(label || tripulanteNameById(normalizedId), `ID ${normalizedId}`);
  if (!entries.has(normalizedId)) entries.set(normalizedId, normalizedLabel);
}

function reportTripulanteOptionsMarkup(selectedValue = "") {
  const selected = normalizeText(selectedValue || jornadaState.filters.tripulanteId);
  const entries = new Map();
  jornadaState.rows.forEach((row) => {
    const sourceMission = row.sourceMission || {};
    addReportTripulanteEntry(entries, row.tripulanteId, row.tripulanteNome);
    addReportTripulanteEntry(
      entries,
      row.comandanteTripulanteId || row.comandante_tripulante_id || sourceMission.comandante_tripulante_id,
      row.comandanteTripulanteNome || sourceMission.comandante_nome
    );
    addReportTripulanteEntry(
      entries,
      row.copilotoTripulanteId || row.copiloto_tripulante_id || sourceMission.copiloto_tripulante_id,
      row.copilotoTripulanteNome || sourceMission.copiloto_nome
    );
  });
  if (!entries.size) {
    jornadaState.options.tripulantes.forEach((item) => {
      addReportTripulanteEntry(entries, item?.id, item?.nome || item?.label || item?.name);
    });
  }
  const options = Array.from(entries.entries())
    .sort((a, b) => a[1].localeCompare(b[1], "pt-BR"))
    .map(([id, label]) => `<option value="${escapeAttr(id)}" ${selected === id ? "selected" : ""}>${escapeHtml(label)}</option>`)
    .join("");
  return `<option value="">Selecione</option>${options}`;
}

function reportFuncaoForTripulante(tripulanteId, fallback = "") {
  const selected = normalizeText(tripulanteId);
  const fallbackFuncao = normalizeLower(fallback);
  if (!selected) return fallbackFuncao;
  for (const row of jornadaState.rows) {
    const sourceMission = row.sourceMission || {};
    if (selected === normalizeText(row.tripulanteId)) return normalizeLower(row.funcao || fallbackFuncao);
    if (selected === normalizeText(row.comandanteTripulanteId || row.comandante_tripulante_id || sourceMission.comandante_tripulante_id)) {
      return "comandante";
    }
    if (selected === normalizeText(row.copilotoTripulanteId || row.copiloto_tripulante_id || sourceMission.copiloto_tripulante_id)) {
      return "copiloto";
    }
  }
  return fallbackFuncao;
}

function renderHeader() {
  const exportDisabled = !jornadaState.rows.length || jornadaState.exportStatus === "loading" || !hasPermission(EXPORT_CREATE_PERMISSION);
  const reportDisabled = !jornadaState.rows.length || jornadaState.reportStatus === "loading" || !hasPermission(EXPORT_CREATE_PERMISSION);
  const generalHoursReportDisabled = jornadaState.generalHoursReportStatus === "exporting" || !hasPermission(EXPORT_CREATE_PERMISSION);
  const generalProductivityReportDisabled = jornadaState.generalProductivityReportStatus === "exporting" || !hasPermission(EXPORT_CREATE_PERMISSION);
  const productivityDisabled = jornadaState.productivityConsolidadoStatus === "loading" || !hasPermission(BONUS_READ_PERMISSION);
  const extractDisabled = jornadaState.extractStatus === "loading" || !hasPermission(BONUS_READ_PERMISSION);
  return `
    <section class="jornada-hero ui-surface">
      <div class="jornada-hero-copy">
        <h1>Lançamentos de Jornada</h1>
        <p>Lance uma vez e alimente os relatórios de Bonificação Horária e Produtividade com a mesma fonte operacional.</p>
        <div class="jornada-source-note" role="status">
          <strong>Lançamento único</strong>
          <span>Cada linha salva aqui grava a missão operacional vinculada no backend; Horária, Produtividade, extratos e PDFs leem esse mesmo lançamento com preview calculado no backend.</span>
        </div>
      </div>
      <div class="jornada-hero-actions">
        <button type="button" class="button-link secondary" data-jornada-insight="productivity" ${productivityDisabled ? "disabled" : ""}>
          ${jornadaState.productivityConsolidadoStatus === "loading" ? "Carregando..." : "Consolidado de produtividade"}
        </button>
        <button type="button" class="button-link secondary" data-jornada-insight="extract" ${extractDisabled ? "disabled" : ""}>
          Extrato por período
        </button>
        <button type="button" class="button-link secondary" data-jornada-insight="general-hours" ${generalHoursReportDisabled ? "disabled" : ""}>
          ${jornadaState.generalHoursReportStatus === "exporting" ? "Exportando..." : "Relatório geral de horas"}
        </button>
        <button type="button" class="button-link secondary" data-jornada-insight="general-productivity" ${generalProductivityReportDisabled ? "disabled" : ""}>
          ${jornadaState.generalProductivityReportStatus === "exporting" ? "Exportando..." : "Relatório geral de produtividade"}
        </button>
        <button type="button" class="button-link secondary" data-jornada-insight="individual-report" ${reportDisabled ? "disabled" : ""}>
          Relatório individual
        </button>
        <button type="button" class="button-link" id="jornadaExportPdf" ${exportDisabled ? "disabled" : ""}>
          ${jornadaState.exportStatus === "loading" ? "Exportando..." : "Exportar PDF"}
        </button>
      </div>
    </section>
  `;
}

function renderFilters() {
  const filters = jornadaState.filters;
  return `
    <form class="jornada-filter-panel ui-surface" id="jornadaFilters">
      <label>
        <span>Competência</span>
        <input type="month" name="competencia" value="${escapeAttr(filters.competencia)}">
      </label>
      <label>
        <span>Filtrar por função</span>
        <select name="funcao">${functionOptionsMarkup(filters.funcao, true)}</select>
      </label>
      <label>
        <span>Filtrar por tripulante</span>
        <select name="tripulanteId" ${jornadaState.optionsStatus === "loading" ? "disabled" : ""}>${tripulanteOptionsMarkup(filters.tripulanteId)}</select>
      </label>
      <div class="jornada-filter-actions">
        <button type="submit" ${jornadaState.status === "loading" ? "disabled" : ""}>
          ${jornadaState.status === "loading" ? "Gerando..." : "Gerar grade"}
        </button>
        <button type="button" class="button-link secondary" id="jornadaClearFilters" ${jornadaState.status === "loading" ? "disabled" : ""}>Limpar</button>
      </div>
    </form>
  `;
}

function renderContextCard({ icon, label, value, detail, tone = "info" }) {
  return `
    <article class="jornada-context-card" data-tone="${escapeAttr(tone)}">
      <span class="jornada-icon-bubble" aria-hidden="true">${escapeHtml(icon)}</span>
      <div>
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(value)}</strong>
        ${detail ? `<small>${escapeHtml(detail)}</small>` : ""}
      </div>
    </article>
  `;
}

function renderContext() {
  const context = jornadaState.context || {};
  const result = formatCurrencyBr(context.resultadoAtual || 0);
  const status = context.statusCompetencia || "aberta";
  return `
    <section class="jornada-context ui-surface">
      <div class="jornada-section-head">
        <div>
          <h2>Contexto da grade mensal</h2>
          <p>A função operacional, a precificação e os cálculos vêm do backend; o operador não precisa lançar a mesma informação em outra aba.</p>
        </div>
        <span class="status-pill ${statusClass(status)}">${escapeHtml(status)}</span>
      </div>
      <div class="jornada-context-grid">
        ${renderContextCard({ icon: "C", label: "Competência", value: formatCompetenciaLabel(context.competencia || jornadaState.filters.competencia), detail: "Recorte mensal" })}
        ${renderContextCard({ icon: "F", label: "Função operacional", value: functionLabel(context.funcao || jornadaState.filters.funcao || "Todos"), detail: "Filtro atual", tone: "success" })}
        ${renderContextCard({ icon: "T", label: "Tripulantes", value: context.tripulantes ? String(context.tripulantes) : "Todos", detail: "Com linhas na grade", tone: "purple" })}
        ${renderContextCard({ icon: "$", label: "Resultado atual", value: result, detail: `${jornadaState.rows.length} linha(s) carregada(s)`, tone: "money" })}
      </div>
      ${isCompetenciaClosed() ? `
        <div class="jornada-locked-note" role="status">
          <strong>Competência fechada</strong>
          <span>Edição, recálculo e descarte de linha ficam bloqueados para preservar o fechamento.</span>
        </div>
      ` : ""}
    </section>
  `;
}

function indicatorCard({ label, value, detail, icon, tone }) {
  return `
    <article class="jornada-indicator-card ui-surface" data-tone="${escapeAttr(tone)}">
      <div class="jornada-indicator-top">
        <span class="jornada-icon-bubble" aria-hidden="true">${escapeHtml(icon)}</span>
        <span>${escapeHtml(label)}</span>
      </div>
      <strong>${escapeHtml(value)}</strong>
      <small>${escapeHtml(detail)}</small>
    </article>
  `;
}

function renderIndicators() {
  const values = jornadaState.indicators || DEFAULT_INDICATORS;
  const totalGeralValue = jornadaState.status === "loading"
    ? "Carregando..."
    : (jornadaState.status === "initial" ? "Gerar grade" : formatCurrencyBr(values.totalGeral));
  const totalGeralDetail = jornadaState.status === "initial"
    ? "aguardando consulta ao backend"
    : "backend consolidado";
  return `
    <section class="jornada-indicators" aria-label="Indicadores financeiros">
      ${indicatorCard({ label: "Total geral", value: totalGeralValue, detail: totalGeralDetail, icon: "$", tone: "money" })}
      ${indicatorCard({ label: "Linhas", value: String(values.linhas || 0), detail: "grade atual", icon: "L", tone: "info" })}
      ${indicatorCard({ label: "Hora reduzida", value: formatHours(values.horaReduzida), detail: "pós cálculo exibido", icon: "H", tone: "warning" })}
      ${indicatorCard({ label: "Exceções", value: String(values.excecoes || 0), detail: "linhas com alerta", icon: "!", tone: "danger" })}
      ${indicatorCard({ label: "Alertas descanso", value: String(values.alertasDescanso || 0), detail: "pós execução", icon: "D", tone: "purple" })}
      ${indicatorCard({ label: "Domingos", value: String(values.domingos || 0), detail: "calendário backend", icon: "S", tone: "success" })}
      ${indicatorCard({ label: "Feriados", value: String(values.feriados || 0), detail: "feriados cadastrados", icon: "*", tone: "cyan" })}
      ${indicatorCard({ label: "Valor normal", value: formatCurrencyBr(values.valorNormal), detail: "bonificação horária", icon: "N", tone: "blue" })}
    </section>
  `;
}

function renderFlowStep(number, title, text) {
  return `
    <article class="jornada-flow-step">
      <span class="jornada-flow-icon">${escapeHtml(number)}</span>
      <div>
        <strong>${escapeHtml(title)}</strong>
        <p>${escapeHtml(text)}</p>
      </div>
    </article>
  `;
}

function renderFlow() {
  return `
    <section class="jornada-flow ui-surface" aria-label="Fluxo operacional">
      ${renderFlowStep("1", "Filtre", "Escolha competência, função ou tripulante e gere a grade.")}
      ${renderFlowStep("2", "Lance", "Adicione uma linha e salve o lançamento único da jornada.")}
      ${renderFlowStep("3", "Confira", "Apresentação e abandono liberam o preview backend para Horária e Produtividade.")}
      ${renderFlowStep("4", "Feche", "Recalcule, confira os relatórios e exporte PDFs do mesmo recorte.")}
    </section>
  `;
}

function renderExtractPanel() {
  const filters = jornadaState.extractFilters || defaultExtractFilters();
  const payload = jornadaState.extractPayload || null;
  const subtotais = payload?.subtotais || {};
  const linhas = payload?.linhas || [];
  const alertas = payload?.alertas || [];
  const isLoading = jornadaState.extractStatus === "loading";
  const isExporting = jornadaState.extractExportStatus === "loading";
  return `
    <section class="jornada-insight-panel ui-surface" data-insight="extract">
      <div class="jornada-section-head">
        <div>
          <h2>Extrato por período</h2>
          <p>Consulte lançamentos e valores por intervalo de datas, sem depender do consolidado mensal completo.</p>
        </div>
        <button type="button" class="button-link secondary" data-jornada-insight-close>Fechar</button>
      </div>
      <div class="jornada-report-form" aria-label="Filtros do extrato por período">
        <label>
          <span>Data inicial</span>
          <input type="date" id="jornadaExtractStart" value="${escapeAttr(filters.dataInicio)}">
        </label>
        <label>
          <span>Data final</span>
          <input type="date" id="jornadaExtractEnd" value="${escapeAttr(filters.dataFim)}">
        </label>
        <label>
          <span>Tripulante</span>
          <select id="jornadaExtractTripulante">${reportTripulanteOptionsMarkup(filters.tripulanteId)}</select>
        </label>
        <label>
          <span>Função</span>
          <select id="jornadaExtractFuncao">${functionOptionsMarkup(filters.funcao, true)}</select>
        </label>
        <label>
          <span>Tipo</span>
          <select id="jornadaExtractType">
            <option value="ambos" ${filters.tipo === "ambos" ? "selected" : ""}>Ambos</option>
            <option value="horaria" ${filters.tipo === "horaria" ? "selected" : ""}>Bonificação Horária</option>
            <option value="produtividade" ${filters.tipo === "produtividade" ? "selected" : ""}>Produtividade</option>
          </select>
        </label>
        <button type="button" id="jornadaGenerateExtract" ${isLoading ? "disabled" : ""}>
          ${isLoading ? "Gerando..." : "Gerar extrato"}
        </button>
        <button type="button" class="button-link secondary" id="jornadaExportExtractPdf" ${!payload || isExporting ? "disabled" : ""}>
          ${isExporting ? "Exportando..." : "Exportar PDF"}
        </button>
      </div>
      ${jornadaState.extractStatus === "loading" ? responsiveStateMarkup({
        title: "Carregando extrato",
        detail: "Buscando lançamentos, cálculos vigentes e alertas no backend.",
        type: "loading",
        compact: true,
      }) : ""}
      ${jornadaState.extractStatus === "error" ? responsiveStateMarkup({
        title: "Não foi possível gerar o extrato",
        detail: jornadaState.extractError || "Revise o período informado e tente novamente.",
        type: "error",
        compact: true,
      }) : ""}
      ${payload && jornadaState.extractStatus !== "loading" ? `
        <div class="jornada-mini-grid">
          ${renderContextCard({ icon: "$", label: "Total geral", value: formatCurrencyBr(payload.total_geral || 0), detail: "somente vigentes" })}
          ${renderContextCard({ icon: "H", label: "Bonificação Horária", value: formatCurrencyBr(subtotais.horaria || 0), detail: "linhas ativas" })}
          ${renderContextCard({ icon: "P", label: "Produtividade", value: formatCurrencyBr(subtotais.produtividade || 0), detail: "competências completas" })}
          ${renderContextCard({ icon: "L", label: "Linhas", value: String(linhas.length), detail: "no período" })}
        </div>
        <div class="jornada-mini-grid">
          ${linhas.length ? linhas.slice(0, 12).map((line) => `
            <article class="jornada-mini-card">
              <strong>${escapeHtml(formatAny(line.tripulante_nome || `Tripulante ${line.tripulante_id || ""}`))}</strong>
              <span>${escapeHtml(`${formatDateBr(line.data)} · ${functionLabel(line.funcao)} · ${formatAny(line.tipo)}`)}</span>
              <small>${escapeHtml(formatAny(line.descricao || line.trecho || line.status))}</small>
              <b>${escapeHtml(formatCurrencyBr(line.valor_total || 0))}</b>
            </article>
          `).join("") : responsiveStateMarkup({
            title: "Sem lançamentos no período",
            detail: "Ajuste as datas ou os filtros para consultar outro recorte.",
            type: "empty",
            compact: true,
          })}
        </div>
        ${alertas.length ? `
          <div class="jornada-report-note">
            <strong>Alertas:</strong> ${escapeHtml(alertas.map((item) => item.message || item.code || "").filter(Boolean).join("; "))}
          </div>
        ` : ""}
      ` : ""}
      ${!payload && jornadaState.extractStatus === "idle" ? `
        <p class="jornada-report-note">O extrato usa dados persistidos e cálculos vigentes do backend. Cancelados e obsoletos não entram no total ativo por padrão.</p>
      ` : ""}
    </section>
  `;
}

function renderGeneralHoursReportStatus(filters) {
  const status = jornadaState.generalHoursReportStatus || "idle";
  const message = jornadaState.generalHoursReportMessage || "";
  if (status === "exporting") {
    return responsiveStateMarkup({
      title: "Exportando",
      detail: "Validando dados consolidados no backend e preparando o PDF.",
      type: "loading",
      compact: true,
    });
  }
  if (status === "success") {
    return responsiveStateMarkup({
      title: "PDF gerado",
      detail: message || "Arquivo validado e download iniciado.",
      type: "success",
      compact: true,
    });
  }
  if (status === "empty") {
    return responsiveStateMarkup({
      title: "Sem dados",
      detail: message || "Não há dados consolidados para a competência e função selecionadas.",
      type: "empty",
      compact: true,
    });
  }
  if (status === "pending") {
    return responsiveStateMarkup({
      title: "Pendência de recálculo",
      detail: GENERAL_HOURS_PENDING_MESSAGE,
      type: "warning",
      compact: true,
    });
  }
  if (status === "permission") {
    return responsiveStateMarkup({
      title: "Erro de permissão",
      detail: message || "Você não tem permissão para exportar este relatório.",
      type: "no-permission",
      compact: true,
    });
  }
  if (status === "error") {
    return responsiveStateMarkup({
      title: "Erro inesperado",
      detail: message || "Não foi possível exportar o relatório. Tente novamente.",
      type: "error",
      compact: true,
    });
  }
  return responsiveStateMarkup({
    title: "Pronto para exportar",
    detail: `${generalHoursFunctionLabel(filters.funcao)} - ${formatCompetenciaLabel(filters.competencia)}.`,
    type: "info",
    compact: true,
  });
}

function renderGeneralHoursReportPanel() {
  const filters = defaultGeneralHoursReportFilters();
  const isExporting = jornadaState.generalHoursReportStatus === "exporting";
  return `
    <section class="jornada-insight-panel ui-surface" data-insight="general-hours">
      <div class="jornada-section-head">
        <div>
          <h2>Relatório geral de horas</h2>
          <p>Consolide a Bonificação Horária mensal por competência e função operacional.</p>
        </div>
        <button type="button" class="button-link secondary" data-jornada-insight-close>Fechar</button>
      </div>
      <div class="jornada-report-form jornada-general-hours-form" aria-label="Filtros do relatório geral de horas">
        <label>
          <span>Competência</span>
          <input type="month" id="jornadaGeneralHoursCompetencia" value="${escapeAttr(filters.competencia)}">
        </label>
        <label>
          <span>Função operacional</span>
          <select id="jornadaGeneralHoursFuncao">${generalHoursFunctionOptionsMarkup(filters.funcao)}</select>
        </label>
        <button type="button" id="jornadaExportGeneralHoursPdf" ${isExporting ? "disabled" : ""}>
          ${isExporting ? "Exportando..." : "Exportar PDF"}
        </button>
      </div>
      ${renderGeneralHoursReportStatus(filters)}
      <p class="jornada-report-note">O relatório usa somente cálculos horários persistidos vigentes do backend. Obsoletos, cancelados e excluídos não entram no PDF.</p>
    </section>
  `;
}

function renderGeneralProductivityReportStatus(filters) {
  const status = jornadaState.generalProductivityReportStatus || "idle";
  const message = jornadaState.generalProductivityReportMessage || "";
  if (status === "exporting") {
    return responsiveStateMarkup({
      title: "Exportando",
      detail: "Validando a produtividade consolidada no backend e preparando o PDF.",
      type: "loading",
      compact: true,
    });
  }
  if (status === "success") {
    return responsiveStateMarkup({
      title: "PDF gerado",
      detail: message || "Arquivo validado e download iniciado.",
      type: "success",
      compact: true,
    });
  }
  if (status === "empty") {
    return responsiveStateMarkup({
      title: "Sem dados",
      detail: message || "Não há produtividade consolidada para a competência e função selecionadas.",
      type: "empty",
      compact: true,
    });
  }
  if (status === "pending") {
    return responsiveStateMarkup({
      title: "Pendência de recálculo",
      detail: GENERAL_PRODUCTIVITY_PENDING_MESSAGE,
      type: "warning",
      compact: true,
    });
  }
  if (status === "permission") {
    return responsiveStateMarkup({
      title: "Erro de permissão",
      detail: message || "Você não tem permissão para exportar este relatório.",
      type: "no-permission",
      compact: true,
    });
  }
  if (status === "error") {
    return responsiveStateMarkup({
      title: "Erro inesperado",
      detail: message || "Não foi possível exportar o relatório. Tente novamente.",
      type: "error",
      compact: true,
    });
  }
  return responsiveStateMarkup({
    title: "Pronto para exportar",
    detail: `${generalHoursFunctionLabel(filters.funcao)} - ${formatCompetenciaLabel(filters.competencia)}.`,
    type: "info",
    compact: true,
  });
}

function renderGeneralProductivityReportPanel() {
  const filters = defaultGeneralProductivityReportFilters();
  const isExporting = jornadaState.generalProductivityReportStatus === "exporting";
  return `
    <section class="jornada-insight-panel ui-surface" data-insight="general-productivity">
      <div class="jornada-section-head">
        <div>
          <h2>Relatório geral de produtividade</h2>
          <p>Consolide a produtividade mensal por competência e função operacional.</p>
        </div>
        <button type="button" class="button-link secondary" data-jornada-insight-close>Fechar</button>
      </div>
      <div class="jornada-report-form jornada-general-productivity-form" aria-label="Filtros do relatório geral de produtividade">
        <label>
          <span>Competência</span>
          <input type="month" id="jornadaGeneralProductivityCompetencia" value="${escapeAttr(filters.competencia)}">
        </label>
        <label>
          <span>Função operacional</span>
          <select id="jornadaGeneralProductivityFuncao">${generalHoursFunctionOptionsMarkup(filters.funcao)}</select>
        </label>
        <button type="button" id="jornadaExportGeneralProductivityPdf" ${isExporting ? "disabled" : ""}>
          ${isExporting ? "Exportando..." : "Exportar PDF"}
        </button>
      </div>
      ${renderGeneralProductivityReportStatus(filters)}
      <p class="jornada-report-note">O relatório usa somente cálculos de produtividade persistidos vigentes do backend. Preview, obsoletos, cancelados e excluídos não entram no PDF.</p>
    </section>
  `;
}

function renderInsightPanel() {
  if (!jornadaState.activeInsight) return "";
  if (jornadaState.activeInsight === "productivity") {
    const payload = jornadaState.productivityConsolidado || {};
    const indicadores = payload.indicadores || {};
    const tripulantes = payload.linhas_por_tripulante || [];
    const funcoes = payload.totais_por_funcao || [];
    const alertas = payload.alertas || [];
    const bloqueios = payload.bloqueios || [];
    const condicoes = payload.condicoes_especiais || [];
    return `
      <section class="jornada-insight-panel ui-surface" data-insight="productivity">
        <div class="jornada-section-head">
          <div>
            <h2>Consolidado de produtividade</h2>
            <p>Total devido, garantia mínima e produtividade calculada conforme retorno do backend.</p>
          </div>
          <button type="button" class="button-link secondary" data-jornada-insight-close>Fechar</button>
        </div>
        ${jornadaState.productivityConsolidadoStatus === "loading" ? responsiveStateMarkup({
          title: "Carregando consolidado",
          detail: "Buscando produtividade vigente no backend.",
          type: "loading",
          compact: true,
        }) : ""}
        ${jornadaState.productivityConsolidadoStatus === "error" ? responsiveStateMarkup({
          title: "Nao foi possivel carregar o consolidado",
          detail: jornadaState.productivityConsolidadoError || "Tente novamente ou revise as permissoes financeiras.",
          type: "error",
          compact: true,
        }) : ""}
        ${jornadaState.productivityConsolidadoStatus !== "loading" && jornadaState.productivityConsolidadoStatus !== "error" ? `
          <div class="jornada-mini-grid">
            ${renderContextCard({ icon: "$", label: "Total a pagar", value: formatCurrencyBr(indicadores.total_a_pagar || indicadores.total_geral || 0), detail: "calculos vigentes" })}
            ${renderContextCard({ icon: "T", label: "Tripulantes", value: String(indicadores.tripulantes || 0), detail: "no recorte" })}
            ${renderContextCard({ icon: "M", label: "Missoes consideradas", value: String(indicadores.missoes_consideradas || indicadores["missões_consideradas"] || 0), detail: "ativas" })}
            ${renderContextCard({ icon: "B", label: "Missoes bloqueadas", value: String(indicadores.missoes_bloqueadas || indicadores["missões_bloqueadas"] || 0), detail: "nao somadas" })}
            ${renderContextCard({ icon: "E", label: "Excecoes", value: String(indicadores.excecoes || 0), detail: "regras especiais" })}
            ${renderContextCard({ icon: "A", label: "Alertas", value: String(indicadores.alertas || 0), detail: "avisos do backend" })}
          </div>
          <div class="jornada-mini-grid">
            ${tripulantes.length ? tripulantes.slice(0, 12).map((item) => `
              <article class="jornada-mini-card">
                <strong>${escapeHtml(formatAny(item.tripulante_nome || `Tripulante ${item.tripulante_id || ""}`))}</strong>
                <span>${escapeHtml((item.funcoes || []).map(functionLabel).join(", ") || "Funcao operacional")}</span>
                <small>${escapeHtml(String(item.missoes_consideradas || item["missões_consideradas"] || 0))} missao(oes) considerada(s)</small>
                <b>${escapeHtml(formatCurrencyBr(item.total_a_pagar || item.total_devido || 0))}</b>
              </article>
            `).join("") : responsiveStateMarkup({
              title: "Sem produtividade consolidada",
              detail: "Nao ha calculo de produtividade vigente para o recorte selecionado.",
              type: "empty",
              compact: true,
            })}
          </div>
          ${funcoes.length ? `
            <div class="jornada-mini-grid">
              ${funcoes.map((item) => `
                <article class="jornada-mini-card">
                  <strong>${escapeHtml(functionLabel(item.funcao))}</strong>
                  <span>${escapeHtml(String(item.tripulantes || 0))} tripulante(s)</span>
                  <small>${escapeHtml(String(item.missoes_consideradas || item["missões_consideradas"] || 0))} missao(oes)</small>
                  <b>${escapeHtml(formatCurrencyBr(item.total_a_pagar || item.total_devido || 0))}</b>
                </article>
              `).join("")}
            </div>
          ` : ""}
          ${condicoes.length || alertas.length || bloqueios.length ? `
            <div class="jornada-report-note">
              ${condicoes.length ? `<strong>Condicao operacional especial:</strong> ${escapeHtml(condicoes.map((item) => item.condicao_operacional_especial).join(", "))}<br>` : ""}
              ${alertas.length ? `<strong>Alertas:</strong> ${escapeHtml(alertas.map((item) => item.message).join("; "))}<br>` : ""}
              ${bloqueios.length ? `<strong>Bloqueios:</strong> ${escapeHtml(bloqueios.map((item) => item.message).join("; "))}` : ""}
            </div>
          ` : ""}
        ` : ""}
      </section>
    `;
  }
  if (jornadaState.activeInsight === "individual-report") {
    const defaultTripulanteId = jornadaState.filters.tripulanteId || jornadaState.rows.find((row) => row.tripulanteId)?.tripulanteId || "";
    const defaultFuncao = reportFuncaoForTripulante(defaultTripulanteId, jornadaState.filters.funcao);
    return `
      <section class="jornada-insight-panel ui-surface" data-insight="individual-report">
        <div class="jornada-section-head">
          <div>
            <h2>Relatório individual</h2>
            <p>Gere o PDF individualizado de Bonificação Horária ou Produtividade usando o recorte atual da grade.</p>
          </div>
          <button type="button" class="button-link secondary" data-jornada-insight-close>Fechar</button>
        </div>
        <div class="jornada-report-form" aria-label="Filtros do relatório individual">
          <label>
            <span>Tipo</span>
            <select id="jornadaIndividualType">
              <option value="horaria">Bonificação Horária</option>
              <option value="produtividade">Produtividade</option>
            </select>
          </label>
          <label>
            <span>Tripulante</span>
            <select id="jornadaIndividualTripulante">${reportTripulanteOptionsMarkup(defaultTripulanteId)}</select>
          </label>
          <label>
            <span>Função</span>
            <select id="jornadaIndividualFuncao">${functionOptionsMarkup(defaultFuncao, true)}</select>
          </label>
          <button type="button" id="jornadaGenerateIndividualReport" ${jornadaState.reportStatus === "loading" ? "disabled" : ""}>
            ${jornadaState.reportStatus === "loading" ? "Gerando..." : "Gerar relatório individual"}
          </button>
        </div>
        <p class="jornada-report-note">Salve ou recalcule a grade antes de gerar o relatÃ³rio. Salve ou descarte a linha antes de gerar o relatório.</p>
        <p class="jornada-report-note">O PDF usa cálculos persistidos no backend, respeita permissão financeira e não inclui obsoletos ou missões canceladas no total por padrão.</p>
      </section>
    `;
  }
  if (jornadaState.activeInsight === "extract") {
    return renderExtractPanel();
  }
  if (jornadaState.activeInsight === "general-hours") {
    return renderGeneralHoursReportPanel();
  }
  if (jornadaState.activeInsight === "general-productivity") {
    return renderGeneralProductivityReportPanel();
  }
  return "";
}

function gridStateMarkup() {
  if (jornadaState.status === "initial") {
    return responsiveStateMarkup({
      title: "Nenhuma grade gerada ainda",
      detail: "Escolha competência, função e tripulante, depois clique em Gerar grade para carregar os lançamentos do backend.",
      type: "info",
      compact: false,
    });
  }
  if (jornadaState.status === "loading") {
    return responsiveStateMarkup({
      title: "Carregando grade",
      detail: "Buscando lançamentos, cálculos horários, produtividade e opções operacionais.",
      type: "loading",
      compact: false,
    });
  }
  if (jornadaState.status === "error") {
    return responsiveStateMarkup({
      title: "Não foi possível gerar a grade",
      detail: jornadaState.message || "Tente novamente ou revise as permissões financeiras.",
      type: "error",
      compact: false,
      actionId: "jornadaRetry",
      actionLabel: "Tentar novamente",
    });
  }
  if (jornadaState.status === "empty") {
    return responsiveStateMarkup({
      title: "Grade vazia",
      detail: "A competência não possui lançamentos para o recorte selecionado. Adicione uma linha para iniciar a grade mensal.",
      type: "empty",
      compact: false,
    });
  }
  return "";
}

function rowErrorMarkup(key) {
  const message = jornadaState.rowErrors[key];
  if (!message) return "";
  return `<div class="jornada-row-feedback status-red" role="alert">${escapeHtml(message)}</div>`;
}

function previewStatusLabel(previewState) {
  if (!previewState) return "Sem preview";
  const status = previewState.status || "idle";
  const labels = {
    loading: "Calculando...",
    insufficient: "Dados insuficientes",
    available: "Preview disponível",
    pending: "Pendente",
    blocked: "Bloqueada",
    error: "Erro",
  };
  return labels[status] || "Sem preview";
}

function renderPreviewCell(row) {
  const preview = jornadaState.rowPreview[row.key];
  if (!preview) {
    return `
      <div class="jornada-preview-line" data-row-preview="${escapeAttr(row.key)}">
        <span class="status-pill status-gray">Sem preview</span>
        <small>Preencha data, aeronave e tripulação.</small>
      </div>
    `;
  }
  if (preview.status === "loading") {
    return `
      <div class="jornada-preview-line" data-row-preview="${escapeAttr(row.key)}">
        <span class="status-pill status-yellow">Calculando...</span>
        <small>Preview financeiro pelo backend.</small>
      </div>
    `;
  }
  if (preview.status === "available") {
    return `
      <div class="jornada-preview-line" data-row-preview="${escapeAttr(row.key)}">
        <span class="status-pill status-green">${escapeHtml(previewStatusLabel(preview))}</span>
        <small>${escapeHtml(formatCurrencyBr(preview.valorEstimado || 0))} · ${escapeHtml(formatMinutes(preview.horasConsideradas || preview.minutos || 0))}</small>
      </div>
    `;
  }
  const pillClass = preview.status === "error" || preview.status === "blocked" ? "status-red" : "status-yellow";
  return `
    <div class="jornada-preview-line" data-row-preview="${escapeAttr(row.key)}">
      <span class="status-pill ${pillClass}">${escapeHtml(previewStatusLabel(preview))}</span>
      <small>${escapeHtml(preview.message || "Revise os campos obrigatórios.")}</small>
    </div>
  `;
}

function seedPreviewFromPersistedRow(row) {
  const calculationStatus = normalizeLower(row.calculationStatus || row.status);
  if (calculationStatus === "calculado" || Number(row.total || 0) > 0) {
    return {
      status: "available",
      message: "Cálculo vigente persistido.",
      valorEstimado: row.total || 0,
      horasConsideradas: row.preCalcMin || row.diurna + row.noturna || 0,
    };
  }
  if (calculationStatus === "erro" || calculationStatus === "bloqueado") {
    return {
      status: "blocked",
      message: "Linha pendente de revisão antes do cálculo.",
    };
  }
  return {
    status: "pending",
    message: "Aguardando prévia do backend.",
  };
}

function seedGridRowPreviews(rows = []) {
  return rows.reduce((acc, row) => {
    if (row?.key) acc[row.key] = seedPreviewFromPersistedRow(row);
    return acc;
  }, {});
}

function setGridRowPreview(row, preview) {
  if (!row?.key || jornadaState.editingRowKey === row.key) return;
  jornadaState.rowPreview = {
    ...jornadaState.rowPreview,
    [row.key]: preview,
  };
  updatePreviewCell(document.querySelector(`[data-jornada-row="${CSS.escape(row.key)}"]`), row.key);
}

async function runGridRowPreview(row, requestSeq) {
  if (!row?.key || jornadaState.editingRowKey === row.key) return;
  const payload = previewPayloadFromDraft(buildRowDraft(row));
  const validationMessages = payloadValidationMessages(payload, { forPreview: true });
  if (validationMessages.length) {
    setGridRowPreview(row, {
      status: "insufficient",
      message: validationMessages.join(" "),
    });
    return;
  }
  setGridRowPreview(row, { status: "loading" });
  try {
    const result = await previewFinanceiroJornadaLinha(payload);
    if (requestSeq !== gridPreviewRequestSeq || jornadaState.editingRowKey === row.key) return;
    const preview = result?.preview || {};
    const status = normalizeLower(preview.status);
    const pendingMessages = (preview.pendencias || preview.inconsistencias || [])
      .map((item) => typeof item === "string" ? item : item?.message || item?.field || "")
      .filter(Boolean);
    setGridRowPreview(row, {
      status: status === "pendente_dados" ? "pending" : status === "bloqueada" ? "blocked" : "available",
      message: pendingMessages.join(", ") || "Prévia atualizada pelo backend.",
      valorEstimado: preview.valor_estimado || preview.valor_total || 0,
      horasConsideradas: preview.horas_consideradas || preview.minutos_considerados || preview.jornada_total_minutos || 0,
    });
  } catch (error) {
    if (requestSeq !== gridPreviewRequestSeq || jornadaState.editingRowKey === row.key) return;
    setGridRowPreview(row, {
      status: "error",
      message: buildErrorMessage(error),
    });
  }
}

function refreshPreviewForGradeRows(rows = jornadaState.rows) {
  const requestSeq = ++gridPreviewRequestSeq;
  (rows || [])
    .filter((row) => row?.key && row.key !== jornadaState.editingRowKey)
    .forEach((row) => {
      runGridRowPreview(row, requestSeq);
    });
}

function renderReadOnlyRow(row, index) {
  return `
    <tr data-jornada-row="${escapeAttr(row.key)}">
      <td data-label="#">${index + 1}</td>
      <td data-label="Data inicial">${escapeHtml(formatDateBr(row.data))}</td>
      <td data-label="Data final">${escapeHtml(formatDateBr(row.dataFinal || row.data))}</td>
      <td data-label="Comandante">${escapeHtml(formatAny(row.comandanteTripulanteNome || tripulanteNameById(row.comandanteTripulanteId || row.sourceMission?.comandante_tripulante_id)))}</td>
      <td data-label="Copiloto">${escapeHtml(formatAny(row.copilotoTripulanteNome || tripulanteNameById(row.copilotoTripulanteId || row.sourceMission?.copiloto_tripulante_id)))}</td>
      <td data-label="Tripulante"><strong>${escapeHtml(formatAny(row.tripulanteNome))}</strong></td>
      <td data-label="Função">${escapeHtml(functionLabel(row.funcao))}</td>
      <td data-label="Aeronave">${escapeHtml(formatAny(row.aeronave))}</td>
      <td data-label="Rel. voo">${escapeHtml(formatAny(row.relVoo))}</td>
      <td data-label="N. DB">${escapeHtml(formatAny(row.numeroDb))}</td>
      <td data-label="Contratante">${escapeHtml(formatAny(row.contratante))}</td>
      <td data-label="Trecho">${escapeHtml(formatAny(row.trecho))}</td>
      <td data-label="Pernoites" class="jornada-pernoite-cell">${pernoiteSummaryMarkup(row)}</td>
      <td data-label="Cob. base">${row.coberturaBase ? "Sim" : "Nao"}</td>
      <td data-label="Cond. especial">${escapeHtml(formatAny(row.operacaoEspecial))}</td>
      <td data-label="Apresentação">${escapeHtml(formatAny(row.apresentacao))}</td>
      <td data-label="Abandono">${escapeHtml(formatAny(row.abandono))}</td>
      <td data-label="Pós exec. min">${escapeHtml(formatMinutes(row.posExecMin))}</td>
      <td data-label="Justif.">${escapeHtml(formatAny(row.justificativa))}</td>
      <td data-label="Obs">${escapeHtml(formatAny(row.observacao))}</td>
      <td data-label="Tipo">${escapeHtml(formatAny(row.tipo))}</td>
      <td data-label="Diurna">${escapeHtml(formatMinutes(row.diurna))}</td>
      <td data-label="Noturna">${escapeHtml(formatMinutes(row.noturna))}</td>
      <td data-label="Pré calc min">${escapeHtml(formatMinutes(row.preCalcMin))}</td>
      <td data-label="Pós calc">${escapeHtml(formatMinutes(row.posCalc))}</td>
      <td data-label="Total">${renderPreviewCell(row)}</td>
      <td data-label="Status"><span class="status-pill ${statusClass(row.status)}">${escapeHtml(formatAny(row.status, "Pendente"))}</span></td>
      <td data-label="Ações" class="actions">
        <div class="jornada-row-actions">
          <button type="button" class="button-link secondary" data-jornada-edit="${escapeAttr(row.key)}" ${!canEditJornada() || isCompetenciaClosed() ? "disabled" : ""}>Editar</button>
          <button type="button" class="button-link secondary" data-jornada-report-type="horaria" data-tripulante-id="${escapeAttr(row.tripulanteId)}" data-funcao="${escapeAttr(row.funcao)}" ${row.tripulanteId ? "" : "disabled"}>PDF Horária</button>
          <button type="button" class="button-link secondary" data-jornada-report-type="produtividade" data-tripulante-id="${escapeAttr(row.tripulanteId)}" data-funcao="${escapeAttr(row.funcao)}" ${row.tripulanteId ? "" : "disabled"}>PDF Produt.</button>
        </div>
      </td>
    </tr>
  `;
}

function renderEditableRow(row, index) {
  const draft = jornadaState.draftRows[row.key] || buildRowDraft(row);
  const derivedDraft = syncCrewSelectionOnLine({ ...draft });
  const hasError = Boolean(jornadaState.rowErrors[row.key]);
  return `
    <tr class="jornada-edit-row ${hasError ? "is-invalid" : ""}" data-jornada-row="${escapeAttr(row.key)}" data-editing="true">
      <td data-label="#">${row.key === "new" ? "+" : index + 1}</td>
      <td data-label="Data inicial"><input type="date" data-jornada-field="data" value="${escapeAttr(draft.data)}"></td>
      <td data-label="Data final"><input type="date" data-jornada-field="dataFinal" value="${escapeAttr(draft.dataFinal || draft.data)}"></td>
      <td data-label="Comandante"><select data-jornada-field="comandanteTripulanteId" data-jornada-crew="comandante" aria-label="Comandante">${tripulanteOptionsMarkup(draft.comandanteTripulanteId)}</select></td>
      <td data-label="Copiloto"><select data-jornada-field="copilotoTripulanteId" data-jornada-crew="copiloto" aria-label="Copiloto">${tripulanteOptionsMarkup(draft.copilotoTripulanteId)}</select></td>
      <td data-label="Tripulante da linha">
        <span data-jornada-derived="tripulante">${escapeHtml(formatAny(derivedDraft.tripulanteNome || tripulanteNameById(derivedDraft.tripulanteId)))}</span>
      </td>
      <td data-label="Função da linha">
        <span data-jornada-derived="funcao">${escapeHtml(functionLabel(derivedDraft.funcao))}</span>
      </td>
      <td data-label="Aeronave"><select data-jornada-field="aeronaveId" data-jornada-equipment>${equipamentoOptionsMarkup(draft.aeronaveId)}</select></td>
      <td data-label="Rel. voo"><input type="text" data-jornada-field="relVoo" value="${escapeAttr(draft.relVoo)}"></td>
      <td data-label="N. DB"><input type="text" data-jornada-field="numeroDb" value="${escapeAttr(draft.numeroDb)}"></td>
      <td data-label="Contratante"><input type="text" data-jornada-field="contratante" value="${escapeAttr(draft.contratante)}"></td>
      <td data-label="Trecho"><input type="text" data-jornada-field="trecho" value="${escapeAttr(draft.trecho)}"></td>
      <td data-label="Pernoites"><input type="number" min="0" data-jornada-field="quantidadePernoites" value="${escapeAttr(draft.quantidadePernoites)}"></td>
      <td data-label="Cob. base"><input type="checkbox" data-jornada-field="coberturaBase" ${draft.coberturaBase ? "checked" : ""} aria-label="Cobertura de base"></td>
      <td data-label="Cond. especial"><input type="text" data-jornada-field="operacaoEspecial" value="${escapeAttr(draft.operacaoEspecial)}" placeholder="Ex.: Palmas turbo-helice"></td>
      <td data-label="Apresentação"><input type="time" data-jornada-field="apresentacao" value="${escapeAttr(draft.apresentacao)}"></td>
      <td data-label="Abandono"><input type="time" data-jornada-field="abandono" value="${escapeAttr(draft.abandono)}"></td>
      <td data-label="Pós exec. min"><input type="number" min="0" data-jornada-field="posExecMin" value="${escapeAttr(draft.posExecMin)}"></td>
      <td data-label="Justif."><input type="text" data-jornada-field="justificativa" value="${escapeAttr(draft.justificativa)}"></td>
      <td data-label="Obs"><input type="text" data-jornada-field="observacao" value="${escapeAttr(draft.observacao)}"></td>
      <td data-label="Tipo"><input type="text" data-jornada-field="tipo" value="${escapeAttr(draft.tipo)}"></td>
      <td data-label="Diurna">${escapeHtml(formatMinutes(draft.diurna))}</td>
      <td data-label="Noturna">${escapeHtml(formatMinutes(draft.noturna))}</td>
      <td data-label="Pré calc min">${escapeHtml(formatMinutes(draft.preCalcMin))}</td>
      <td data-label="Pós calc">${escapeHtml(formatMinutes(draft.posCalc))}</td>
      <td data-label="Total">${renderPreviewCell(row)}</td>
      <td data-label="Status"><span class="status-pill status-yellow">Em edição</span></td>
      <td data-label="Ações" class="actions">
        <div class="jornada-row-actions">
          <button type="button" data-jornada-save="${escapeAttr(row.key)}" ${isBusy() || isCompetenciaClosed() ? "disabled" : ""}>Salvar</button>
          <button type="button" class="button-link secondary" data-jornada-discard="${escapeAttr(row.key)}" ${isBusy() ? "disabled" : ""}>Descartar</button>
        </div>
        ${rowErrorMarkup(row.key)}
      </td>
    </tr>
  `;
}

function renderGridRows() {
  const rows = [...jornadaState.rows];
  if (jornadaState.editingRowKey === "new") {
    rows.unshift(buildRowDraft({ ...(jornadaState.draftRows.new || {}), key: "new", isNew: true }));
  }
  if (jornadaState.status !== "ready" && jornadaState.status !== "empty" && !rows.length) {
    return emptyTableRowMarkup(JORNADA_TABLE_COLSPAN, {
      title: "Grade não carregada",
      detail: "Use os filtros acima para gerar a grade mensal.",
      type: "info",
    });
  }
  if (!rows.length) {
    return emptyTableRowMarkup(JORNADA_TABLE_COLSPAN, {
      title: "Nenhum lançamento encontrado",
      detail: "A competência não possui linhas para o recorte atual.",
      type: "empty",
    });
  }
  return rows
    .map((row, index) => row.key === jornadaState.editingRowKey ? renderEditableRow(row, index) : renderReadOnlyRow(row, index))
    .join("");
}

function renderGrid() {
  const disabledAdd = !canEditJornada() || isCompetenciaClosed() || jornadaState.status === "loading" || jornadaState.editingRowKey === "new";
  const disabledRecalculate = !jornadaState.rows.length || !canRecalculateJornada() || isCompetenciaClosed() || jornadaState.recalculateStatus === "loading";
  return `
    <section class="jornada-grid-panel ui-surface">
      <div class="jornada-section-head">
        <div>
          <h2>Grade de lançamentos</h2>
          <p>Edite uma única linha operacional; ao salvar, ela alimenta Bonificação Horária e Produtividade sem novo lançamento.</p>
        </div>
        <div class="jornada-grid-actions">
          <button type="button" class="button-link secondary" id="jornadaAddLine" ${disabledAdd ? "disabled" : ""}>Adicionar linha</button>
          <button type="button" class="button-link secondary" id="jornadaRecalculate" ${disabledRecalculate ? "disabled" : ""}>
            ${jornadaState.recalculateStatus === "loading" ? "Recalculando..." : "Recalcular grade"}
          </button>
        </div>
      </div>
      ${gridStateMarkup()}
      <div class="jornada-table-scroll-hint" aria-hidden="true">Deslize a grade horizontalmente para ver todas as colunas.</div>
      <div class="jornada-table-wrap ui-table-wrap" data-jornada-table-wrap tabindex="0" aria-label="Grade de lançamentos de jornada com rolagem horizontal controlada">
        <table class="data-table jornada-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Data inicial</th>
              <th>Data final</th>
              <th>Comandante</th>
              <th>Copiloto</th>
              <th>Tripulante da linha</th>
              <th>Função da linha</th>
              <th>Aeronave</th>
              <th>Rel. voo</th>
              <th>N. DB</th>
              <th>Contratante</th>
              <th>Trecho</th>
              <th>Pernoites</th>
              <th>Cob. base</th>
              <th>Cond. especial</th>
              <th>Apresentação</th>
              <th>Abandono</th>
              <th>Pós exec. min</th>
              <th>Justif.</th>
              <th>Obs</th>
              <th>Tipo</th>
              <th>Diurna</th>
              <th>Noturna</th>
              <th>Pré calc min</th>
              <th>Pós calc</th>
              <th>Total</th>
              <th>Status</th>
              <th>Ações</th>
            </tr>
          </thead>
          <tbody>${renderGridRows()}</tbody>
        </table>
      </div>
      <div id="jornadaGridFeedback" class="jornada-feedback" aria-live="polite"></div>
      ${!JORNADA_API_CAPABILITIES.nativeLineCreateEndpoint ? `
        <div class="jornada-contract-note">
          <strong>Contrato pendente:</strong>
          <span>Adicionar e editar linhas usa o endpoint nativo de Lançamentos de Jornada; cancelamento de linha segue a regra segura da missão operacional vinculada.</span>
        </div>
      ` : ""}
    </section>
  `;
}

function renderPermissionDenied() {
  return `
    <section class="ui-surface panel">
      ${responsiveStateMarkup({
        title: "Sem permissão financeira",
        detail: "Seu perfil não possui finance:bonuses:read para acessar Lançamentos de Jornada.",
        type: "no-permission",
      })}
    </section>
  `;
}

function renderJornadaPage() {
  const body = canReadJornada()
    ? `
      ${renderFilters()}
      ${renderContext()}
      ${renderIndicators()}
      ${renderFlow()}
      ${renderInsightPanel()}
      ${renderGrid()}
    `
    : renderPermissionDenied();

  renderShell(
    `
      <div class="financeiro-jornada-page ui-page-shell ui-stack" data-finance-page="lancamentos-jornada" data-owner-route="${escapeAttr(FINANCEIRO_JORNADA_ROUTE)}" data-current-route="${escapeAttr(routePath())}">
        ${renderHeader()}
        ${body}
      </div>
    `,
    "Lançamentos de Jornada",
  );
  wireJornadaPage();
}

async function loadJornadaGrade(filters = jornadaState.filters) {
  const requestSeq = gradeRequestSeq + 1;
  gradeRequestSeq = requestSeq;
  gridPreviewRequestSeq += 1;
  jornadaState = {
    ...jornadaState,
    filters: {
      competencia: normalizeText(filters.competencia) || currentCompetencia(),
      funcao: normalizeText(filters.funcao),
      tripulanteId: normalizeText(filters.tripulanteId),
    },
    status: "loading",
    message: "",
    editingRowKey: "",
    rowErrors: {},
    rowPreview: {},
    productivityConsolidado: null,
    productivityConsolidadoStatus: "idle",
    productivityConsolidadoError: "",
    extractFilters: null,
    extractPayload: null,
    extractStatus: "idle",
    extractError: "",
  };
  renderJornadaPage();
  try {
    const result = await getFinanceiroJornadaGrade(jornadaState.filters);
    if (requestSeq !== gradeRequestSeq) return;
    const rows = result.rows || [];
    jornadaState = {
      ...jornadaState,
      status: rows.length ? "ready" : "empty",
      rows,
      rowPreview: seedGridRowPreviews(rows),
      indicators: result.indicators || { ...DEFAULT_INDICATORS },
      context: result.context,
      options: result.options || jornadaState.options,
      optionsStatus: "ready",
      hourlyPayload: result.hourlyPayload,
      productivityPayload: result.productivityPayload,
      periodPayload: result.periodPayload,
    };
  } catch (error) {
    if (requestSeq !== gradeRequestSeq) return;
    jornadaState = {
      ...jornadaState,
      status: "error",
      message: buildErrorMessage(error),
    };
  }
  renderJornadaPage();
  if (jornadaState.status === "ready" && jornadaState.rows.length) {
    refreshPreviewForGradeRows(jornadaState.rows);
  }
}

async function loadJornadaOptions() {
  if (optionsReady() || jornadaState.optionsStatus === "loading") return;
  jornadaState = {
    ...jornadaState,
    optionsStatus: "loading",
  };
  renderJornadaPage();
  try {
    const options = await listFinanceiroJornadaOptions();
    jornadaState = {
      ...jornadaState,
      options,
      optionsStatus: "ready",
    };
  } catch (_error) {
    jornadaState = {
      ...jornadaState,
      optionsStatus: "error",
    };
  }
  renderJornadaPage();
}

function collectFilters(form) {
  const data = Object.fromEntries(new FormData(form).entries());
  return {
    competencia: normalizeText(data.competencia) || currentCompetencia(),
    funcao: normalizeText(data.funcao),
    tripulanteId: normalizeText(data.tripulanteId),
  };
}

function collectExtractFilters() {
  return {
    dataInicio: normalizeText(document.getElementById("jornadaExtractStart")?.value) || firstDayFromCompetencia(jornadaState.filters.competencia),
    dataFim: normalizeText(document.getElementById("jornadaExtractEnd")?.value) || lastDayFromCompetencia(jornadaState.filters.competencia),
    tripulanteId: normalizeText(document.getElementById("jornadaExtractTripulante")?.value),
    funcao: normalizeText(document.getElementById("jornadaExtractFuncao")?.value),
    tipo: normalizeText(document.getElementById("jornadaExtractType")?.value) || "ambos",
  };
}

function collectGeneralHoursReportFilters() {
  return {
    competencia: normalizeText(document.getElementById("jornadaGeneralHoursCompetencia")?.value) || jornadaState.filters.competencia || currentCompetencia(),
    funcao: normalizeGeneralHoursFunction(document.getElementById("jornadaGeneralHoursFuncao")?.value || jornadaState.filters.funcao || "comandante"),
  };
}

function collectGeneralProductivityReportFilters() {
  return {
    competencia: normalizeText(document.getElementById("jornadaGeneralProductivityCompetencia")?.value) || jornadaState.filters.competencia || currentCompetencia(),
    funcao: normalizeGeneralHoursFunction(document.getElementById("jornadaGeneralProductivityFuncao")?.value || jornadaState.filters.funcao || "comandante"),
  };
}

function collectDraftFromElement(rowElement) {
  const key = rowElement?.dataset?.jornadaRow || "";
  const current = jornadaState.draftRows[key] || buildRowDraft(findRow(key) || { key });
  const next = { ...current };
  rowElement?.querySelectorAll("[data-jornada-field]").forEach((field) => {
    next[field.dataset.jornadaField] = field.type === "checkbox" ? field.checked : field.value;
  });
  syncCrewSelectionOnLine(next);
  syncCrewFieldsOnRow(rowElement, next);
  const equipment = rowElement?.querySelector("[data-jornada-equipment]");
  const option = equipment?.selectedOptions?.[0];
  if (normalizeText(equipment?.value) && option) {
    applySelectedAircraftToLine(next, option);
  } else {
    clearAircraftFromLine(next);
  }
  jornadaState.draftRows[key] = next;
  return next;
}

function syncCrewSelectionOnLine(line) {
  line.comandanteTripulanteId = normalizeText(line.comandanteTripulanteId);
  line.copilotoTripulanteId = normalizeText(line.copilotoTripulanteId);
  const filterFuncao = normalizeLower(jornadaState.filters.funcao);
  const requestedTripulanteId = normalizeText(line.tripulanteId || jornadaState.filters.tripulanteId);
  let funcao = normalizeLower(line.funcao || filterFuncao);
  if (!funcao && requestedTripulanteId) {
    if (requestedTripulanteId === line.copilotoTripulanteId) funcao = "copiloto";
    if (requestedTripulanteId === line.comandanteTripulanteId) funcao = "comandante";
  }
  if (!funcao) {
    funcao = line.comandanteTripulanteId ? "comandante" : line.copilotoTripulanteId ? "copiloto" : "";
  }
  line.funcao = funcao;
  if (funcao === "comandante") {
    if (!line.comandanteTripulanteId && line.tripulanteId) line.comandanteTripulanteId = normalizeText(line.tripulanteId);
    line.tripulanteId = line.comandanteTripulanteId || normalizeText(line.tripulanteId);
  } else if (funcao === "copiloto") {
    if (!line.copilotoTripulanteId && line.tripulanteId) line.copilotoTripulanteId = normalizeText(line.tripulanteId);
    line.tripulanteId = line.copilotoTripulanteId || normalizeText(line.tripulanteId);
  } else {
    line.tripulanteId = normalizeText(line.tripulanteId);
  }
  line.comandanteTripulanteNome = tripulanteNameById(line.comandanteTripulanteId);
  line.copilotoTripulanteNome = tripulanteNameById(line.copilotoTripulanteId);
  return line;
}

function syncCrewFieldsOnRow(rowElement, line) {
  if (!rowElement) return;
  const tripulanteTarget = rowElement.querySelector('[data-jornada-derived="tripulante"]');
  const funcaoTarget = rowElement.querySelector('[data-jornada-derived="funcao"]');
  if (tripulanteTarget) {
    tripulanteTarget.textContent = formatAny(line.tripulanteNome || tripulanteNameById(line.tripulanteId));
  }
  if (funcaoTarget) {
    funcaoTarget.textContent = functionLabel(line.funcao);
  }
}

function applySelectedAircraftToLine(line, aircraftOption) {
  const dataset = aircraftOption?.dataset || {};
  const category = normalizeText(dataset.category);
  const equipmentType = normalizeText(dataset.equipmentType);
  const label = normalizeText(dataset.equipmentLabel || dataset.equipmentName || aircraftOption?.textContent);
  line.aircraftCleared = false;
  line.aeronaveId = normalizeText(aircraftOption?.value);
  line.aeronave = label;
  line.categoriaFinanceiraAeronave = category;
  line.tipo = category;
  line.equipmentType = equipmentType;
  line.aircraftRaw = {
    label,
    nome: normalizeText(dataset.equipmentName),
    tipo: equipmentType,
    categoria_financeira: category,
  };
  return line;
}

function clearAircraftFromLine(line) {
  line.aircraftCleared = true;
  line.aeronaveId = "";
  line.aeronave = "";
  line.categoriaFinanceiraAeronave = "";
  line.tipo = "";
  line.equipmentType = "";
  line.aircraftRaw = null;
  return line;
}

function syncEquipmentSelectionOnRow(rowElement) {
  const key = rowElement?.dataset?.jornadaRow || "";
  const equipment = rowElement?.querySelector("[data-jornada-equipment]");
  const option = equipment?.selectedOptions?.[0];
  const current = jornadaState.draftRows[key] || buildRowDraft(findRow(key) || { key });
  const next = { ...current };
  const typeField = rowElement?.querySelector('[data-jornada-field="tipo"]');
  if (normalizeText(equipment?.value) && option) {
    applySelectedAircraftToLine(next, option);
  } else {
    clearAircraftFromLine(next);
  }
  if (typeField) {
    typeField.value = next.tipo || "";
  }
  if (key) {
    delete jornadaState.rowPreview[key];
    jornadaState.draftRows[key] = next;
  }
}

function previewPayloadFromDraft(draft) {
  const sourceMission = draft.sourceMission || {};
  const normalizedDraft = syncCrewSelectionOnLine({ ...draft });
  const quantidadePernoites = nonNegativeNumber(draft.quantidadePernoites);
  const coberturaBase = quantidadePernoites > 0 && Boolean(draft.coberturaBase);
  const aircraftCleared = Boolean(draft.aircraftCleared);
  const aeronaveId = aircraftCleared ? "" : (draft.aeronaveId || sourceMission.aeronave_id || "");
  const aircraftCategory = aircraftCleared
    ? ""
    : (draft.categoriaFinanceiraAeronave || draft.tipo || sourceMission.categoria_financeira_aeronave || "");
  const comandanteTripulanteId = normalizeText(normalizedDraft.comandanteTripulanteId);
  const copilotoTripulanteId = normalizeText(normalizedDraft.copilotoTripulanteId);
  return {
    ...sourceMission,
    competencia: draft.competencia || jornadaState.filters.competencia,
    tripulante_id: normalizedDraft.tripulanteId,
    funcao: normalizedDraft.funcao,
    data_missao: draft.data,
    data_final: draft.dataFinal || draft.data,
    data: draft.data,
    cavok_numero_voo: draft.relVoo,
    relatorio_voo: draft.relVoo,
    contratante: draft.contratante || sourceMission.contratante || "",
    aeronave_id: aeronaveId,
    categoria_financeira_aeronave: aircraftCategory,
    tipo: aircraftCategory,
    comandante_tripulante_id: comandanteTripulanteId,
    copiloto_tripulante_id: copilotoTripulanteId,
    counterpart_tripulante_id: normalizeLower(normalizedDraft.funcao) === "comandante" ? copilotoTripulanteId : comandanteTripulanteId,
    horario_apresentacao: draft.apresentacao,
    hora_apresentacao: draft.apresentacao,
    horario_abandono: draft.abandono,
    hora_abandono: draft.abandono,
    pos_exec_min: nonNegativeNumber(draft.posExecMin),
    trecho: draft.trecho,
    houve_pernoite: quantidadePernoites > 0,
    quantidade_pernoites: quantidadePernoites,
    cobertura_base: coberturaBase,
    tipo_pernoite: pernoiteTypeFromValues(quantidadePernoites, coberturaBase),
    operacao_especial: draft.operacaoEspecial || sourceMission.operacao_especial || "",
    justificativa: draft.justificativa || "",
    observacoes: draft.observacao,
    observacao: draft.observacao,
    status: sourceMission.status || "rascunho",
  };
}

function missingSaveFields(payload) {
  return [
    ["data_missao", "data"],
    ["aeronave_id", "aeronave"],
    ["categoria_financeira_aeronave", "tipo/categoria"],
    ["tripulante_id", "tripulante"],
    ["funcao", "função"],
  ].filter(([key]) => !normalizeText(payload[key])).map(([, label]) => label);
}

function missingPreviewFields(payload) {
  const previewOnlyFields = [
    ["horario_apresentacao", "apresentação"],
    ["horario_abandono", "abandono"],
  ].filter(([key]) => !normalizeText(payload[key])).map(([, label]) => label);
  return [...missingSaveFields(payload), ...previewOnlyFields];
}

function crewValidationMessages(payload) {
  const messages = [];
  const comandanteId = normalizeText(payload.comandante_tripulante_id);
  const copilotoId = normalizeText(payload.copiloto_tripulante_id);
  if (!comandanteId) messages.push("Informe o comandante da missão.");
  if (!copilotoId) messages.push("Informe o copiloto da missão.");
  if (comandanteId && copilotoId && comandanteId === copilotoId) {
    messages.push("Comandante e copiloto não podem ser o mesmo tripulante.");
  }
  return messages;
}

function payloadValidationMessages(payload, { forPreview = false } = {}) {
  const missingFields = forPreview ? missingPreviewFields(payload) : missingSaveFields(payload);
  const baseMessages = missingFields.map((label) => `Faltam: ${label}.`);
  return [...crewValidationMessages(payload), ...baseMessages];
}

function schedulePreview(rowElement) {
  const key = rowElement?.dataset?.jornadaRow || "";
  if (!key) return;
  const draft = collectDraftFromElement(rowElement);
  const payload = previewPayloadFromDraft(draft);
  const validationMessages = payloadValidationMessages(payload, { forPreview: true });
  window.clearTimeout(previewTimers.get(key));
  if (validationMessages.length) {
    jornadaState.rowPreview[key] = {
      status: "insufficient",
      message: validationMessages.join(" "),
    };
    updatePreviewCell(rowElement, key);
    return;
  }
  jornadaState.rowPreview[key] = { status: "loading" };
  updatePreviewCell(rowElement, key);
  const timer = window.setTimeout(() => runPreview(key, draft), PREVIEW_DEBOUNCE_MS);
  previewTimers.set(key, timer);
}

function updatePreviewCell(rowElement, key) {
  const previewCell = rowElement?.querySelector(`[data-row-preview="${CSS.escape(key)}"]`);
  if (!previewCell) return;
  const row = findRow(key) || buildRowDraft(jornadaState.draftRows[key] || { key });
  const template = document.createElement("template");
  template.innerHTML = renderPreviewCell(row).trim();
  previewCell.replaceWith(template.content.firstElementChild);
}

async function runPreview(key, draft) {
  const payload = previewPayloadFromDraft(draft);
  const validationMessages = payloadValidationMessages(payload, { forPreview: true });
  if (validationMessages.length) {
    jornadaState.rowPreview[key] = {
      status: "insufficient",
      message: validationMessages.join(" "),
    };
    const rowElement = document.querySelector(`[data-jornada-row="${CSS.escape(key)}"]`);
    updatePreviewCell(rowElement, key);
    return;
  }
  const requestSeq = ++previewRequestSeq;
  try {
    const result = await previewFinanceiroJornadaLinha(payload);
    if (requestSeq !== previewRequestSeq && jornadaState.editingRowKey === key) return;
    const preview = result?.preview || {};
    const status = normalizeLower(preview.status);
    const pendingMessages = (preview.pendencias || preview.inconsistencias || [])
      .map((item) => typeof item === "string" ? item : item?.message || item?.field || "")
      .filter(Boolean);
    jornadaState.rowPreview[key] = {
      status: status === "pendente_dados" ? "pending" : status === "bloqueada" ? "blocked" : "available",
      message: pendingMessages.join(", "),
      valorEstimado: preview.valor_estimado || preview.valor_total || 0,
      horasConsideradas: preview.horas_consideradas || preview.minutos_considerados || preview.jornada_total_minutos || 0,
    };
  } catch (error) {
    jornadaState.rowPreview[key] = {
      status: "error",
      message: buildErrorMessage(error),
    };
  }
  const rowElement = document.querySelector(`[data-jornada-row="${CSS.escape(key)}"]`);
  updatePreviewCell(rowElement, key);
}

function updatePayloadFromDraft(draft) {
  const normalizedDraft = syncCrewSelectionOnLine({ ...draft });
  const quantidadePernoites = nonNegativeNumber(draft.quantidadePernoites);
  const coberturaBase = quantidadePernoites > 0 && Boolean(draft.coberturaBase);
  const aircraftCleared = Boolean(draft.aircraftCleared);
  const aircraftCategory = aircraftCleared ? "" : (draft.categoriaFinanceiraAeronave || draft.tipo || "");
  const comandanteTripulanteId = normalizeText(normalizedDraft.comandanteTripulanteId);
  const copilotoTripulanteId = normalizeText(normalizedDraft.copilotoTripulanteId);
  return {
    competencia: draft.competencia || jornadaState.filters.competencia,
    data: draft.data,
    data_missao: draft.data,
    data_final: draft.dataFinal || draft.data,
    tripulante_id: normalizedDraft.tripulanteId,
    funcao: normalizedDraft.funcao,
    relatorio_voo: draft.relVoo,
    cavok_numero_voo: draft.relVoo,
    numero_db: draft.numeroDb,
    chamado: draft.numeroDb,
    contratante: draft.contratante,
    aeronave_id: aircraftCleared ? "" : draft.aeronaveId,
    categoria_financeira_aeronave: aircraftCategory,
    tipo: aircraftCategory,
    comandante_tripulante_id: comandanteTripulanteId,
    copiloto_tripulante_id: copilotoTripulanteId,
    counterpart_tripulante_id: normalizeLower(normalizedDraft.funcao) === "comandante" ? copilotoTripulanteId : comandanteTripulanteId,
    hora_apresentacao: draft.apresentacao,
    horario_apresentacao: draft.apresentacao,
    hora_abandono: draft.abandono,
    horario_abandono: draft.abandono,
    pos_exec_min: draft.posExecMin,
    trecho: draft.trecho,
    houve_pernoite: quantidadePernoites > 0,
    quantidade_pernoites: quantidadePernoites,
    cobertura_base: coberturaBase,
    tipo_pernoite: pernoiteTypeFromValues(quantidadePernoites, coberturaBase),
    observacao: draft.observacao,
    observacoes: draft.observacao,
    justificativa: draft.justificativa,
    operacao_especial: draft.operacaoEspecial,
  };
}

async function saveRow(button, key) {
  const rowElement = document.querySelector(`[data-jornada-row="${CSS.escape(key)}"]`);
  const draft = collectDraftFromElement(rowElement);
  jornadaState.rowErrors = { ...jornadaState.rowErrors, [key]: "" };
  const payload = updatePayloadFromDraft(draft);
  const validationMessages = payloadValidationMessages(payload);
  if (validationMessages.length) {
    jornadaState.rowErrors = {
      ...jornadaState.rowErrors,
      [key]: validationMessages.join(" "),
    };
    renderJornadaPage();
    return;
  }
  await withActionBusy(button, "Salvando...", async () => {
    try {
      let result = null;
      const isNewLine = draft.isNew || key === "new" || !draft.lineId;
      const saveSuccessPrefix = isNewLine ? "Linha de jornada criada no backend." : "Linha de jornada salva no backend.";
      if (isNewLine) {
        result = await createFinanceiroJornadaLinha(payload);
      } else {
        result = await updateFinanceiroJornadaLinha({
          lineId: draft.lineId,
          missionId: draft.missionId,
          payload,
        });
      }
      const recalculation = result?.recalculation || {};
      const recalculationStatus = normalizeLower(recalculation.status || recalculation.calculation_status);
      const productivityStatus = normalizeLower(recalculation.productivity_status);
      if (recalculationStatus === "calculado") {
        const productivityMessage = productivityStatus === "calculado"
          ? " Produtividade da competência recalculada."
          : (recalculation.productivity_error ? ` Produtividade pendente: ${recalculation.productivity_error.message || recalculation.productivity_error.code}.` : "");
        showFlash(`${saveSuccessPrefix} Cálculo vigente atualizado pelo backend.${productivityMessage}`, productivityStatus === "pendente" ? "warning" : "success");
      } else if (recalculation?.error) {
        showFlash(`${saveSuccessPrefix} Recálculo pendente: ${recalculation.error.message || recalculation.error.code || "revise os parâmetros financeiros."}`, "warning");
      } else {
        showFlash(`${saveSuccessPrefix} Recarregando grade para exibir o cálculo vigente.`, "success");
      }
      jornadaState.editingRowKey = "";
      jornadaState.draftRows = {};
      await loadJornadaGrade(jornadaState.filters);
    } catch (error) {
      jornadaState.rowErrors = {
        ...jornadaState.rowErrors,
        [key]: buildErrorMessage(error),
      };
      renderJornadaPage();
    }
  });
}

async function recalculateGrade(button) {
  if (!jornadaState.rows.length || isCompetenciaClosed()) return;
  await withActionBusy(button, "Recalculando...", async () => {
    jornadaState.recalculateStatus = "loading";
    renderJornadaPage();
    try {
      await recalculateFinanceiroJornadaGrade(jornadaState.filters.competencia, jornadaState.filters);
      showFlash("Grade enviada para recálculo da competência pelo backend.", "success");
      jornadaState.recalculateStatus = "success";
      await loadJornadaGrade(jornadaState.filters);
    } catch (error) {
      jornadaState.recalculateStatus = "error";
      renderInlineFeedback(document.getElementById("jornadaGridFeedback"), buildErrorMessage(error), error?.status === 403 ? "warning" : "error");
    } finally {
      if (jornadaState.recalculateStatus === "loading") jornadaState.recalculateStatus = "idle";
      renderJornadaPage();
    }
  });
}

async function exportPdf(button) {
  if (!jornadaState.rows.length) return;
  if (jornadaState.editingRowKey) {
    showFlash("Salve ou descarte a linha em edição antes de exportar o PDF da grade.", "warning");
    return;
  }
  await withActionBusy(button, "Exportando...", async () => {
    jornadaState.exportStatus = "loading";
    try {
      const result = await downloadFinanceiroJornadaPdf(jornadaState.filters);
      downloadValidatedPdf(
        result,
        `lancamentos-jornada-${jornadaState.filters.competencia || "competencia"}.pdf`,
      );
      showFlash("PDF do fechamento validado e download iniciado.", "success");
      jornadaState.exportStatus = "success";
    } catch (error) {
      showFlash(buildErrorMessage(error), error?.status === 403 ? "warning" : "error");
      jornadaState.exportStatus = "error";
    } finally {
      renderJornadaPage();
    }
  });
}

async function openProductivityConsolidado(button) {
  if (jornadaState.productivityConsolidadoStatus === "loading") return;
  const loadConsolidado = async () => {
    jornadaState.activeInsight = "productivity";
    jornadaState.productivityConsolidadoStatus = "loading";
    jornadaState.productivityConsolidadoError = "";
    renderJornadaPage();
    try {
      const result = await getFinanceiroProdutividadeConsolidado(jornadaState.filters);
      jornadaState.productivityConsolidado = result;
      jornadaState.productivityConsolidadoStatus = "ready";
    } catch (error) {
      jornadaState.productivityConsolidado = null;
      jornadaState.productivityConsolidadoStatus = "error";
      jornadaState.productivityConsolidadoError = buildErrorMessage(error);
    } finally {
      renderJornadaPage();
    }
  };
  if (button) {
    await withActionBusy(button, "Carregando...", loadConsolidado);
  } else {
    await loadConsolidado();
  }
}

async function generateExtract(button) {
  if (jornadaState.extractStatus === "loading") return;
  if (jornadaState.editingRowKey) {
    showFlash("Salve ou descarte a linha em edição antes de gerar o extrato.", "warning");
    return;
  }
  const filters = collectExtractFilters();
  if (filters.dataInicio > filters.dataFim) {
    showFlash("Data inicial não pode ser maior que data final.", "warning");
    return;
  }
  await withActionBusy(button, "Gerando...", async () => {
    jornadaState.extractFilters = filters;
    jornadaState.extractStatus = "loading";
    jornadaState.extractError = "";
    renderJornadaPage();
    try {
      const result = await getFinanceiroExtratoPeriodo(filters);
      jornadaState.extractPayload = result;
      jornadaState.extractStatus = "ready";
      showFlash("Extrato por período carregado.", "success");
    } catch (error) {
      jornadaState.extractPayload = null;
      jornadaState.extractStatus = "error";
      jornadaState.extractError = buildErrorMessage(error);
    } finally {
      renderJornadaPage();
    }
  });
}

async function exportExtractPdf(button) {
  if (!jornadaState.extractPayload) return;
  if (jornadaState.editingRowKey) {
    showFlash("Salve ou descarte a linha em edição antes de exportar o extrato.", "warning");
    return;
  }
  const filters = jornadaState.extractFilters || collectExtractFilters();
  await withActionBusy(button, "Exportando...", async () => {
    jornadaState.extractExportStatus = "loading";
    renderJornadaPage();
    try {
      const result = await downloadFinanceiroExtratoPeriodoPdf(filters);
      downloadValidatedPdf(
        result,
        `extrato-periodo-${filters.dataInicio || "inicio"}-${filters.dataFim || "fim"}.pdf`,
      );
      showFlash("PDF do extrato validado e download iniciado.", "success");
      jornadaState.extractExportStatus = "success";
    } catch (error) {
      showFlash(buildErrorMessage(error), error?.status === 403 ? "warning" : "error");
      jornadaState.extractExportStatus = "error";
    } finally {
      renderJornadaPage();
    }
  });
}

async function exportGeneralHoursReportPdf(button) {
  if (jornadaState.generalHoursReportStatus === "exporting") return;
  if (jornadaState.editingRowKey) {
    showFlash("Salve ou descarte a linha em edição antes de exportar o relatório financeiro.", "warning");
    return;
  }
  const filters = collectGeneralHoursReportFilters();
  const key = `${filters.competencia}:${filters.funcao}`;
  if (jornadaState.generalHoursReportStatus === "exporting" && jornadaState.generalHoursReportKey === key) return;
  await withActionBusy(button, "Exportando...", async () => {
    jornadaState.generalHoursReportFilters = filters;
    jornadaState.generalHoursReportStatus = "exporting";
    jornadaState.generalHoursReportMessage = "";
    jornadaState.generalHoursReportKey = key;
    renderJornadaPage();
    try {
      const payload = await getFinanceiroHorasTotaisVoadas({
        ...filters,
        incluirZerados: true,
      });
      if (!generalHoursRowsFromPayload(payload).length) {
        jornadaState.generalHoursReportStatus = "empty";
        jornadaState.generalHoursReportMessage = "Não há dados consolidados para a competência e função selecionadas.";
        showFlash(jornadaState.generalHoursReportMessage, "warning");
        return;
      }
      if (generalHoursPayloadHasPendingCalculations(payload)) {
        jornadaState.generalHoursReportStatus = "pending";
        jornadaState.generalHoursReportMessage = GENERAL_HOURS_PENDING_MESSAGE;
        showFlash(GENERAL_HOURS_PENDING_MESSAGE, "warning");
        return;
      }
      const result = await downloadFinanceiroHorasTotaisVoadasPdf(filters);
      const filename = financeiroHorasTotaisVoadasFilename(filters);
      downloadValidatedPdf({ ...result, filename }, filename);
      jornadaState.generalHoursReportStatus = "success";
      jornadaState.generalHoursReportMessage = "PDF gerado, validado e download iniciado.";
      showFlash("PDF do relatório geral de horas validado e download iniciado.", "success");
    } catch (error) {
      const nextState = classifyGeneralHoursReportError(error);
      jornadaState.generalHoursReportStatus = nextState.status;
      jornadaState.generalHoursReportMessage = nextState.message;
      showFlash(nextState.message, nextState.status === "error" ? "error" : "warning");
    } finally {
      jornadaState.generalHoursReportKey = "";
      renderJornadaPage();
    }
  });
}

async function exportGeneralProductivityReportPdf(button) {
  if (jornadaState.generalProductivityReportStatus === "exporting") return;
  if (jornadaState.editingRowKey) {
    showFlash("Salve ou descarte a linha em edição antes de exportar o relatório financeiro.", "warning");
    return;
  }
  const filters = collectGeneralProductivityReportFilters();
  const key = `${filters.competencia}:${filters.funcao}`;
  if (jornadaState.generalProductivityReportStatus === "exporting" && jornadaState.generalProductivityReportKey === key) return;
  await withActionBusy(button, "Exportando...", async () => {
    jornadaState.generalProductivityReportFilters = filters;
    jornadaState.generalProductivityReportStatus = "exporting";
    jornadaState.generalProductivityReportMessage = "";
    jornadaState.generalProductivityReportKey = key;
    renderJornadaPage();
    try {
      const payload = await getFinanceiroProdutividadeRelatorioGeral({
        ...filters,
        incluirZerados: true,
      });
      if (!productivityGeneralRowsFromPayload(payload).length) {
        jornadaState.generalProductivityReportStatus = "empty";
        jornadaState.generalProductivityReportMessage = "Não há produtividade consolidada para a competência e função selecionadas.";
        showFlash(jornadaState.generalProductivityReportMessage, "warning");
        return;
      }
      if (productivityGeneralPayloadHasPendingCalculations(payload)) {
        jornadaState.generalProductivityReportStatus = "pending";
        jornadaState.generalProductivityReportMessage = GENERAL_PRODUCTIVITY_PENDING_MESSAGE;
        showFlash(GENERAL_PRODUCTIVITY_PENDING_MESSAGE, "warning");
        return;
      }
      const result = await downloadFinanceiroProdutividadeRelatorioGeralPdf(filters);
      const filename = financeiroProdutividadeRelatorioGeralFilename(filters);
      downloadValidatedPdf({ ...result, filename }, filename);
      jornadaState.generalProductivityReportStatus = "success";
      jornadaState.generalProductivityReportMessage = "PDF gerado, validado e download iniciado.";
      showFlash("PDF do relatório geral de produtividade validado e download iniciado.", "success");
    } catch (error) {
      const nextState = classifyGeneralProductivityReportError(error);
      jornadaState.generalProductivityReportStatus = nextState.status;
      jornadaState.generalProductivityReportMessage = nextState.message;
      showFlash(nextState.message, nextState.status === "error" ? "error" : "warning");
    } finally {
      jornadaState.generalProductivityReportKey = "";
      renderJornadaPage();
    }
  });
}

async function downloadIndividualReport(button) {
  if (jornadaState.editingRowKey) {
    showFlash("Salve ou recalcule a grade antes de gerar o relatório.", "warning");
    return;
  }
  const tipo = button.dataset.jornadaReportType || document.getElementById("jornadaIndividualType")?.value || "";
  const tripulanteId = button.dataset.tripulanteId || document.getElementById("jornadaIndividualTripulante")?.value || "";
  const explicitFuncao = button.dataset.funcao || document.getElementById("jornadaIndividualFuncao")?.value || "";
  const funcao = button.dataset.funcao ? explicitFuncao : (reportFuncaoForTripulante(tripulanteId, explicitFuncao) || explicitFuncao);
  if (!tipo || !tripulanteId) {
    showFlash("Selecione tipo e tripulante para gerar o relatório individual.", "warning");
    return;
  }
  const key = `${tipo}:${tripulanteId}:${funcao || ""}`;
  if (jornadaState.reportStatus === "loading" && jornadaState.reportKey === key) return;
  await withActionBusy(button, "Gerando...", async () => {
    jornadaState.reportStatus = "loading";
    jornadaState.reportKey = key;
    try {
      const result = await downloadFinanceiroJornadaRelatorioIndividual({
        tipo,
        competencia: jornadaState.filters.competencia,
        tripulanteId,
        funcao,
      });
      downloadValidatedPdf(
        result,
        `relatorio-${tipo || "individual"}-${jornadaState.filters.competencia || "competencia"}.pdf`,
      );
      showFlash("PDF do relatório individual validado e download iniciado.", "success");
      jornadaState.reportStatus = "success";
    } catch (error) {
      showFlash(buildErrorMessage(error), error?.status === 403 ? "warning" : "error");
      jornadaState.reportStatus = "error";
    } finally {
      jornadaState.reportKey = "";
    }
  });
}

function wireJornadaPage() {
  const filterForm = document.getElementById("jornadaFilters");
  filterForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    loadJornadaGrade(collectFilters(event.currentTarget));
  });

  document.getElementById("jornadaClearFilters")?.addEventListener("click", () => {
    jornadaState = {
      ...createInitialState(),
      options: jornadaState.options,
      optionsStatus: jornadaState.optionsStatus,
    };
    renderJornadaPage();
  });

  document.getElementById("jornadaRetry")?.addEventListener("click", () => {
    loadJornadaGrade(jornadaState.filters);
  });

  document.getElementById("jornadaAddLine")?.addEventListener("click", () => {
    gridPreviewRequestSeq += 1;
    const draft = buildRowDraft({ key: "new", isNew: true, competencia: jornadaState.filters.competencia });
    jornadaState.editingRowKey = "new";
    jornadaState.draftRows = { new: draft };
    jornadaState.rowPreview = { ...jornadaState.rowPreview, new: { status: "insufficient", message: "Preencha os dados para solicitar preview." } };
    renderJornadaPage();
    const rowElement = document.querySelector('[data-jornada-row="new"]');
    rowElement?.querySelector("input, select")?.focus();
  });

  document.querySelectorAll("[data-jornada-edit]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.jornadaEdit;
      const row = findRow(key);
      if (!row) return;
      gridPreviewRequestSeq += 1;
      jornadaState.editingRowKey = key;
      jornadaState.draftRows = { [key]: buildRowDraft(row) };
      jornadaState.rowErrors = {};
      renderJornadaPage();
      const rowElement = document.querySelector(`[data-jornada-row="${CSS.escape(key)}"]`);
      rowElement?.querySelector("input, select")?.focus();
      if (rowElement) schedulePreview(rowElement);
    });
  });

  document.querySelectorAll("[data-jornada-discard]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.jornadaDiscard;
      window.clearTimeout(previewTimers.get(key));
      jornadaState.editingRowKey = "";
      jornadaState.draftRows = {};
      jornadaState.rowErrors = {};
      renderJornadaPage();
    });
  });

  document.querySelectorAll("[data-jornada-save]").forEach((button) => {
    button.addEventListener("click", () => saveRow(button, button.dataset.jornadaSave));
  });

  document.querySelectorAll("[data-jornada-row][data-editing='true']").forEach((rowElement) => {
    rowElement.addEventListener("input", () => schedulePreview(rowElement));
    rowElement.addEventListener("change", (event) => {
      if (event.target?.matches("[data-jornada-equipment]")) {
        syncEquipmentSelectionOnRow(rowElement);
      }
      schedulePreview(rowElement);
    });
  });

  document.getElementById("jornadaRecalculate")?.addEventListener("click", (event) => {
    recalculateGrade(event.currentTarget);
  });

  document.getElementById("jornadaExportPdf")?.addEventListener("click", (event) => {
    exportPdf(event.currentTarget);
  });

  document.querySelectorAll("[data-jornada-report-type]").forEach((button) => {
    button.addEventListener("click", () => downloadIndividualReport(button));
  });

  document.getElementById("jornadaGenerateIndividualReport")?.addEventListener("click", (event) => {
    downloadIndividualReport(event.currentTarget);
  });

  document.getElementById("jornadaIndividualTripulante")?.addEventListener("change", (event) => {
    const funcaoSelect = document.getElementById("jornadaIndividualFuncao");
    if (!funcaoSelect) return;
    const inferredFuncao = reportFuncaoForTripulante(event.currentTarget.value, funcaoSelect.value || jornadaState.filters.funcao);
    if (inferredFuncao) funcaoSelect.value = inferredFuncao;
  });

  document.getElementById("jornadaGenerateExtract")?.addEventListener("click", (event) => {
    generateExtract(event.currentTarget);
  });

  document.getElementById("jornadaExportExtractPdf")?.addEventListener("click", (event) => {
    exportExtractPdf(event.currentTarget);
  });

  document.getElementById("jornadaExportGeneralHoursPdf")?.addEventListener("click", (event) => {
    exportGeneralHoursReportPdf(event.currentTarget);
  });

  document.getElementById("jornadaExportGeneralProductivityPdf")?.addEventListener("click", (event) => {
    exportGeneralProductivityReportPdf(event.currentTarget);
  });

  document.querySelectorAll("#jornadaGeneralHoursCompetencia, #jornadaGeneralHoursFuncao").forEach((field) => {
    field.addEventListener("change", () => {
      jornadaState.generalHoursReportFilters = collectGeneralHoursReportFilters();
      jornadaState.generalHoursReportStatus = "idle";
      jornadaState.generalHoursReportMessage = "";
      renderJornadaPage();
    });
  });

  document.querySelectorAll("#jornadaGeneralProductivityCompetencia, #jornadaGeneralProductivityFuncao").forEach((field) => {
    field.addEventListener("change", () => {
      jornadaState.generalProductivityReportFilters = collectGeneralProductivityReportFilters();
      jornadaState.generalProductivityReportStatus = "idle";
      jornadaState.generalProductivityReportMessage = "";
      renderJornadaPage();
    });
  });

  document.querySelectorAll("[data-jornada-insight]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.jornadaInsight === "productivity") {
        openProductivityConsolidado(button);
        return;
      }
      if (button.dataset.jornadaInsight === "extract") {
        jornadaState.activeInsight = "extract";
        jornadaState.extractFilters = jornadaState.extractFilters || defaultExtractFilters();
        renderJornadaPage();
        return;
      }
      jornadaState.activeInsight = button.dataset.jornadaInsight;
      renderJornadaPage();
    });
  });

  document.querySelector("[data-jornada-insight-close]")?.addEventListener("click", () => {
    jornadaState.activeInsight = "";
    renderJornadaPage();
  });
}

async function bootstrapJornadaPage({ autoLoad = false } = {}) {
  if (!canReadJornada()) {
    renderJornadaPage();
    return;
  }
  renderJornadaPage();
  await loadJornadaOptions();
  const shouldAutoLoad = autoLoad || isLegacyBonusRoute();
  if (shouldAutoLoad && jornadaState.status === "initial") {
    await loadJornadaGrade(jornadaState.filters);
  }
  if (isProductivityCompatibilityRoute()) {
    await openProductivityConsolidado();
  }
}

export async function renderFinanceiroLancamentosJornadaPage() {
  await bootstrapJornadaPage({ autoLoad: false });
}
