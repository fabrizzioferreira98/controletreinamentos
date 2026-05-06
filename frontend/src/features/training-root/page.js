import {
  api,
  buildErrorMessage,
  buildHashHref,
  capabilitySet,
  confirmAction,
  escapeAttr,
  escapeHtml,
  hashQuery,
  showFlash,
  withActionBusy,
} from "../../lib.js";
import { renderShell } from "../../shell.js";
import { wireCriticalFormDraftProtection } from "../../shared/forms/draft-protection.js";
import {
  formatHours,
  formatInteger,
  formatPeriodicityLabel,
  loadRequiredItem,
  selectedTypeFromOptions,
  setSubmitButtonBusy,
  trainingModelTheme,
  wireExplicitSubmit,
} from "../treinamentos/program-helpers.js";
const TRAINING_ROOT_TABS = ["types", "segments", "hours"];

const trainingRootState = {
  typeEditId: null,
  segmentEditId: null,
  hourEditId: null,
  activeTab: "types",
  typeFormExpanded: false,
};

const TRAINING_ROOT_SEGMENT_GROUP_ORDER = ["Gerais", "Específicos", "Especiais", "Solo e Voo", "Outros"];
const TRAINING_ROOT_AIRCRAFT_OPTIONS = [
  "King Air B200/200/C90A/C90GT",
  "Citation 525/560",
  "LR 31A/35A/LR45",
  "ASTRA G100",
  "WESTWIND 1124",
];

function normalizeTrainingRootSegmentGroup(value) {
  const normalized = normalizeTrainingToken(value);
  if (normalized === "gerais") return "Gerais";
  if (normalized === "especificos") return "Específicos";
  if (normalized === "especiais") return "Especiais";
  if (normalized === "solo e voo") return "Solo e Voo";
  return "Outros";
}

function renderTrainingRootInstructionRow(colspan, message, icon = "") {
  return `
    <tr>
      <td colspan="${colspan}" class="empty ui-table-state">
        <div class="training-root-empty-state">
          ${icon ? `<div class="training-root-empty-icon" aria-hidden="true">${escapeHtml(icon)}</div>` : ""}
          <p>${escapeHtml(message)}</p>
        </div>
      </td>
    </tr>
  `;
}

function renderTrainingRootModelBadge(value) {
  const label = normalizeTrainingRootSegmentGroup(value);
  const theme = trainingModelTheme(label);
  return `<span class="training-root-model-badge badge-modelo badge-modelo--${theme} training-root-model-badge--${theme}">${escapeHtml(label)}</span>`;
}

function countTrainingRootAircraftModels(items) {
  return new Set(
    (items || [])
      .map((item) => String(item.aeronave_modelo || "").trim())
      .filter(Boolean),
  ).size;
}

function buildTrainingRootFilterHref(tipoTreinamentoId) {
  const nextTypeId = String(tipoTreinamentoId || "").trim();
  return nextTypeId
    ? buildHashHref("#/treinamentos/raiz", { tipo_treinamento_id: nextTypeId })
    : "#/treinamentos/raiz";
}

function normalizeTrainingRootTab(value) {
  return TRAINING_ROOT_TABS.includes(value) ? value : "types";
}

function resolveTrainingRootActiveTab() {
  if (trainingRootState.typeEditId) return "types";
  if (trainingRootState.segmentEditId) return "segments";
  if (trainingRootState.hourEditId) return "hours";
  return normalizeTrainingRootTab(trainingRootState.activeTab);
}

function resolveTrainingRootTypeToggleLabel(expanded, editing) {
  if (expanded) {
    return editing ? "Recolher edição" : "Recolher formulário";
  }
  return "+ Novo tipo de treinamento";
}

function renderTrainingRootFilterBadge(selectedType) {
  return selectedType
    ? `<span class="training-root-filter-badge is-active">Filtro: ${escapeHtml(selectedType.nome)}</span>`
    : '<span class="training-root-filter-badge">Nenhum filtro ativo</span>';
}

function renderTrainingRootTypeStatusBadge(item) {
  const active = Boolean(item?.ativo);
  return `<span class="training-root-status-badge ${active ? "is-active" : "is-inactive"}">${active ? "Ativo" : "Inativo"}</span>`;
}

function renderTrainingRootMetricBadge(value, label) {
  return `<span class="training-root-metric-badge">${formatInteger(value)} ${escapeHtml(label)}</span>`;
}

function renderTrainingRootTypeCards(items, capabilities, selectedTypeId) {
  if (!items.length) {
    return `
      <div class="training-root-empty-block">
        <div class="training-root-empty-icon" aria-hidden="true">🗂️</div>
        <p>Nenhum tipo de treinamento cadastrado.</p>
      </div>
    `;
  }

  return items
    .map((item) => {
      const isFiltered = String(selectedTypeId || "") === String(item.id);
      const isEditing = Number(trainingRootState.typeEditId || 0) === Number(item.id);
      return `
        <article class="type-card ui-surface ui-card${isFiltered ? " is-filtered" : ""}${isEditing ? " is-editing" : ""}">
          <div class="type-card-header">
            <div>
              <h3>${escapeHtml(item.nome)}</h3>
              <p>${escapeHtml(item.codigo || "Sem código")}</p>
            </div>
          </div>
          <div class="type-card-badges">
            ${renderTrainingRootMetricBadge(item.total_segmentos, "segmentos")}
            ${renderTrainingRootMetricBadge(item.total_horas_voo, "horas")}
            ${renderTrainingRootTypeStatusBadge(item)}
          </div>
          <div class="type-card-meta">${escapeHtml(item.exige_aeronave ? "Exige aeronave" : "Aeronave opcional")}</div>
          ${
            item.descricao
              ? `<p class="type-card-description">${escapeHtml(item.descricao)}</p>`
              : '<p class="type-card-description is-muted">Sem descrição complementar.</p>'
          }
          <div class="type-card-actions ui-card-actions">
            ${capabilities.has("tipos_treinamento:edit") ? `<button type="button" class="button-link secondary training-root-type-edit" data-type-id="${item.id}">Editar</button>` : ""}
            ${capabilities.has("tipos_treinamento:delete") ? `<button type="button" class="link-danger training-root-type-delete" data-type-id="${item.id}" data-type-name="${escapeAttr(item.nome)}">Excluir</button>` : ""}
          </div>
        </article>
      `;
    })
    .join("");
}

function renderTrainingRootFilterPanel(options, types, selectedType, tipoFilter, segmentCount, hourCount) {
  return `
    <section class="panel training-root-filter-panel ui-surface ui-stack">
      <form id="training-root-filter-form" class="filters filters-wide training-root-filter-bar ui-form-toolbar ui-stack-sm ui-filter-bar" data-responsive-filter="bar">
        <label class="training-root-filter-field" for="trainingRootTypeFilter">
          <span>Filtrar por tipo de treinamento</span>
          <select name="tipo_treinamento_id" id="trainingRootTypeFilter">
            <option value="">Filtrar segmentos e horas por tipo</option>
            ${(options.tipos_treinamento || [])
              .map((item) => `<option value="${item.id}" ${String(tipoFilter) === String(item.id) ? "selected" : ""}>${escapeHtml(item.nome)}</option>`)
              .join("")}
          </select>
        </label>
        <a class="button-link secondary training-root-filter-clear" href="#/treinamentos/raiz">✕ Limpar</a>
      </form>
      <div class="training-root-filter-meta">
        ${renderTrainingRootFilterBadge(selectedType)}
      </div>
      <section class="summary-grid compact-summary-grid training-root-summary-grid ui-card-grid ui-card-grid-compact ui-card-equal-height">
        <div class="summary-card training-root-summary-card ui-surface ui-card ui-card-compact">
          <strong>Tipos</strong>
          <span>${formatInteger(types.length)}</span>
        </div>
        <div class="summary-card training-root-summary-card ui-surface ui-card ui-card-compact">
          <strong>Segmentos</strong>
          <span>${formatInteger(segmentCount)}</span>
        </div>
        <div class="summary-card training-root-summary-card ui-surface ui-card ui-card-compact">
          <strong>Horas voo</strong>
          <span>${formatInteger(hourCount)}</span>
        </div>
        <div class="summary-card training-root-summary-card ui-surface ui-card ui-card-compact${selectedType ? " is-highlighted" : ""}">
          <strong>Filtro ativo</strong>
          <span>${escapeHtml(selectedType ? "Sim" : "Não")}</span>
          <small>${escapeHtml(selectedType ? selectedType.nome : "Nenhum filtro")}</small>
        </div>
      </section>
    </section>
  `;
}

function renderTrainingRootTypesTab({
  capabilities,
  canManageTypes,
  activeTab,
  typeFormExpanded,
  typeToggleLabel,
  typeDefaults,
  options,
  types,
  editingType,
  selectedType,
}) {
  return `
    <section
      class="training-root-tab-content${activeTab === "types" ? " is-active" : ""}"
      id="training-root-tab-types"
      data-training-root-panel="types"
      role="tabpanel"
      aria-labelledby="training-root-tab-button-types"
      ${activeTab === "types" ? "" : "hidden"}
    >
      <div class="training-root-section-head">
        <div>
          <h2>Tipos de treinamento</h2>
          <p class="page-subtitle">Catálogo mestre com status, código e vínculos de referência do sistema.</p>
        </div>
        ${
          canManageTypes
            ? `
              <button
                type="button"
                class="button-link secondary training-root-type-toggle"
                data-training-root-type-toggle
                aria-expanded="${typeFormExpanded ? "true" : "false"}"
                aria-controls="training-root-type-form-shell"
              >
                ${escapeHtml(typeToggleLabel)}
              </button>
            `
            : ""
        }
      </div>
      ${
        canManageTypes
          ? `
            <div
              class="form-collapsible training-root-type-form-shell ${typeFormExpanded ? "is-expanded" : "is-collapsed"}"
              id="training-root-type-form-shell"
              ${typeFormExpanded ? "" : "hidden"}
            >
              <form id="training-root-type-form" class="form-grid training-root-form-grid ui-form-grid ui-stack-sm ui-form-density-compact">
                <label>Nome<input type="text" name="nome" value="${escapeAttr(typeDefaults.nome || "")}" required></label>
                <label>Código<input type="text" name="codigo" value="${escapeAttr(typeDefaults.codigo || "")}" required></label>
                <label>
                  Status
                  <select name="status">
                    ${(options.status || []).map((item) => `<option value="${escapeAttr(item)}" ${typeDefaults.status === item ? "selected" : ""}>${escapeHtml(item)}</option>`).join("")}
                  </select>
                </label>
                <label>
                  Exige aeronave
                  <select name="exige_aeronave">
                    ${(options.exige_aeronave || []).map((item) => `<option value="${escapeAttr(item)}" ${String(typeDefaults.exige_aeronave_label || "Não") === String(item) ? "selected" : ""}>${escapeHtml(item)}</option>`).join("")}
                  </select>
                </label>
                <label class="full-width ui-form-field-long">Descrição<textarea name="descricao" rows="3">${escapeHtml(typeDefaults.descricao || "")}</textarea></label>
                <div class="form-actions full-width ui-form-actions">
                  <button type="submit" id="training-root-type-submit">${editingType ? "Salvar tipo" : "Criar tipo"}</button>
                  ${editingType ? '<button type="button" class="button-link secondary" id="training-root-type-cancel">Cancelar</button>' : ""}
                </div>
              </form>
            </div>
          `
          : '<div class="hint training-root-inline-hint">Seu perfil não possui permissão para alterar o cadastro raiz.</div>'
      }
      <div class="type-card-grid ui-card-grid ui-card-equal-height">
        ${renderTrainingRootTypeCards(types, capabilities, selectedType?.id)}
      </div>
    </section>
  `;
}

function renderTrainingRootSegmentsTab({
  capabilities,
  canManageTypes,
  activeTab,
  hasActiveTypeFilter,
  options,
  segmentDefaults,
  editingSegment,
  selectedType,
  segments,
}) {
  return `
    <section
      class="training-root-tab-content${activeTab === "segments" ? " is-active" : ""}"
      id="training-root-tab-segments"
      data-training-root-panel="segments"
      role="tabpanel"
      aria-labelledby="training-root-tab-button-segments"
      ${activeTab === "segments" ? "" : "hidden"}
    >
      <div class="training-root-section-head">
        <div>
          <h2>Segmentos teóricos</h2>
          <p class="page-subtitle">${escapeHtml(selectedType ? `Tipo selecionado: ${selectedType.nome}` : "Selecione um tipo de treinamento para visualizar os segmentos.")}</p>
        </div>
      </div>
      ${
        canManageTypes
          ? `
            <form id="training-root-segment-form" class="form-grid training-root-form-grid ui-form-grid ui-stack-sm ui-form-density-compact">
              <label>
                Tipo
                <select name="tipo_treinamento_id" ${hasActiveTypeFilter ? "disabled" : ""} required>
                  <option value="">Selecione</option>
                  ${(options.tipos_treinamento || []).map((item) => `<option value="${item.id}" ${String(segmentDefaults.tipo_treinamento_id || "") === String(item.id) ? "selected" : ""}>${escapeHtml(item.nome)}</option>`).join("")}
                </select>
              </label>
              <label>
                Modelo
                <select name="modelo_segmento" required>
                  ${(options.modelos_segmento || []).map((item) => `<option value="${escapeAttr(item)}" ${String(segmentDefaults.modelo_segmento || "") === String(item) ? "selected" : ""}>${escapeHtml(item)}</option>`).join("")}
                </select>
              </label>
              <label>Nome do segmento<input type="text" name="nome_segmento" value="${escapeAttr(segmentDefaults.nome_segmento || "")}" required></label>
              <label>Carga horária<input type="number" step="0.1" min="0" name="carga_horaria" value="${escapeAttr(segmentDefaults.carga_horaria || "")}"></label>
              <label>Carga teórica<input type="number" step="0.1" min="0" name="carga_teorica" value="${escapeAttr(segmentDefaults.carga_teorica || "")}"></label>
              <label>Carga prática<input type="number" step="0.1" min="0" name="carga_pratica" value="${escapeAttr(segmentDefaults.carga_pratica || "")}"></label>
              <label>
                Periodicidade
                <select name="periodicidade_meses">
                  ${(options.periodicidades || []).map((item) => `<option value="${item.value}" ${String(segmentDefaults.periodicidade_meses || 0) === String(item.value) ? "selected" : ""}>${escapeHtml(item.label)}</option>`).join("")}
                </select>
              </label>
              <label class="full-width ui-form-field-long">Observação<textarea name="observacao" rows="2">${escapeHtml(segmentDefaults.observacao || "")}</textarea></label>
              <div class="form-actions full-width ui-form-actions">
                <button type="submit" id="training-root-segment-submit">${editingSegment ? "Salvar segmento" : "Criar segmento"}</button>
                ${editingSegment ? '<button type="button" class="button-link secondary" id="training-root-segment-cancel">Cancelar</button>' : ""}
              </div>
            </form>
          `
          : ""
      }
      <div class="table-wrap training-root-table-wrap training-reports-table-wrap ui-table-wrap ui-table-density-compact">
        <table class="data-table responsive-cards">
          <thead><tr><th>Modelo</th><th>Segmento</th><th>Carga (h)</th><th>Teórica</th><th>Prática</th><th>Period.</th><th>Observação</th><th>Ações</th></tr></thead>
          <tbody>
            ${renderTrainingRootSegmentsRows(segments, selectedType, capabilities)}
          </tbody>
        </table>
      </div>
    </section>
  `;
}

function renderTrainingRootHoursTab({
  capabilities,
  canManageTypes,
  activeTab,
  hasActiveTypeFilter,
  options,
  hourDefaults,
  editingHour,
  selectedType,
  hours,
}) {
  return `
    <section
      class="training-root-tab-content${activeTab === "hours" ? " is-active" : ""}"
      id="training-root-tab-hours"
      data-training-root-panel="hours"
      role="tabpanel"
      aria-labelledby="training-root-tab-button-hours"
      ${activeTab === "hours" ? "" : "hidden"}
    >
      <div class="training-root-section-head">
        <div>
          <h2>Horas de voo por aeronave</h2>
          <p class="page-subtitle">${escapeHtml(selectedType ? `Tipo selecionado: ${selectedType.nome}` : "Selecione um tipo de treinamento para visualizar as horas de voo.")}</p>
        </div>
      </div>
      ${
        canManageTypes
          ? `
            <form id="training-root-hour-form" class="form-grid training-root-form-grid ui-form-grid ui-stack-sm ui-form-density-compact">
              <label>
                Tipo
                <select name="tipo_treinamento_id" ${hasActiveTypeFilter ? "disabled" : ""} required>
                  <option value="">Selecione</option>
                  ${(options.tipos_treinamento || []).map((item) => `<option value="${item.id}" ${String(hourDefaults.tipo_treinamento_id || "") === String(item.id) ? "selected" : ""}>${escapeHtml(item.nome)}</option>`).join("")}
                </select>
              </label>
              <label>
                Modelo de aeronave
                <select name="aeronave_modelo" required>
                  <option value="">Selecione a aeronave</option>
                  ${TRAINING_ROOT_AIRCRAFT_OPTIONS.map((item) => `<option value="${escapeAttr(item)}" ${String(hourDefaults.aeronave_modelo || "") === String(item) ? "selected" : ""}>${escapeHtml(item)}</option>`).join("")}
                </select>
              </label>
              <label>Solo<input type="number" step="0.1" min="0" name="solo_horas" value="${escapeAttr(hourDefaults.solo_horas || "")}"></label>
              <label>PIC/SIC<input type="number" step="0.1" min="0" name="voo_pic_sic_horas" value="${escapeAttr(hourDefaults.voo_pic_sic_horas || "")}"></label>
              <label>CREW<input type="number" step="0.1" min="0" name="voo_crew_horas" value="${escapeAttr(hourDefaults.voo_crew_horas || "")}"></label>
              <label class="full-width ui-form-field-long">Observação<textarea name="observacao" rows="2">${escapeHtml(hourDefaults.observacao || "")}</textarea></label>
              <div class="form-actions full-width ui-form-actions">
                <button type="submit" id="training-root-hour-submit">${editingHour ? "Salvar horas" : "Criar horas"}</button>
                ${editingHour ? '<button type="button" class="button-link secondary" id="training-root-hour-cancel">Cancelar</button>' : ""}
              </div>
            </form>
          `
          : ""
      }
      <div class="table-wrap training-root-table-wrap training-reports-table-wrap ui-table-wrap ui-table-density-compact">
        <table class="data-table responsive-cards">
          <thead><tr><th>Tipo</th><th>Aeronave</th><th>Solo</th><th>PIC/SIC</th><th>CREW</th><th>Observação</th><th>Ações</th></tr></thead>
          <tbody>
            ${renderTrainingRootHoursRows(hours, selectedType, capabilities)}
          </tbody>
        </table>
      </div>
    </section>
  `;
}

function renderTrainingRootSegmentsRows(items, selectedType, capabilities) {
  if (!selectedType) {
    return renderTrainingRootInstructionRow(8, "Selecione um tipo de treinamento para visualizar os segmentos.", "📋");
  }

  if (!items.length) {
    return renderTrainingRootInstructionRow(8, "Nenhum segmento cadastrado para o tipo selecionado.", "📋");
  }

  const grouped = new Map(TRAINING_ROOT_SEGMENT_GROUP_ORDER.map((label) => [label, []]));
  items.forEach((item) => {
    const groupName = normalizeTrainingRootSegmentGroup(item.modelo_segmento);
    grouped.get(groupName).push(item);
  });

  return TRAINING_ROOT_SEGMENT_GROUP_ORDER
    .filter((groupName) => (grouped.get(groupName) || []).length > 0)
    .map((groupName) => {
      const groupItems = grouped.get(groupName) || [];
      return `
        <tr class="training-root-group-row">
          <td colspan="8"><strong>${escapeHtml(groupName)}</strong></td>
        </tr>
        ${groupItems
          .map(
            (item) => `
              <tr>
                <td data-label="Modelo">${renderTrainingRootModelBadge(item.modelo_segmento)}</td>
                <td data-label="Segmento">${escapeHtml(item.nome_segmento)}</td>
                <td data-label="Carga (h)">${formatHours(item.carga_horaria)}</td>
                <td data-label="Teórica">${formatHours(item.carga_teorica)}</td>
                <td data-label="Prática">${formatHours(item.carga_pratica)}</td>
                <td data-label="Period.">${escapeHtml(item.periodicidade_label || formatPeriodicityLabel(item.periodicidade_meses))}</td>
                <td data-label="Observação">${escapeHtml(item.observacao || "-")}</td>
                <td class="actions ui-table-actions" data-label="Ações">
                  ${capabilities.has("tipos_treinamento:edit") ? `<button type="button" class="button-link secondary training-root-segment-edit" data-segment-id="${item.id}">Editar</button>` : ""}
                  ${capabilities.has("tipos_treinamento:delete") ? `<button type="button" class="link-danger training-root-segment-delete" data-segment-id="${item.id}" data-segment-name="${escapeAttr(item.nome_segmento)}">Excluir</button>` : ""}
                </td>
              </tr>
            `,
          )
          .join("")}
      `;
    })
    .join("");
}

function renderTrainingRootHoursRows(items, selectedType, capabilities) {
  if (!selectedType) {
    return renderTrainingRootInstructionRow(7, "Selecione um tipo de treinamento para visualizar as horas de voo.", "✈️");
  }

  if (!items.length) {
    return renderTrainingRootInstructionRow(7, "Nenhuma referência de horas de voo cadastrada para o tipo selecionado.", "✈️");
  }

  return items
    .map(
      (item) => `
        <tr>
          <td data-label="Tipo">${escapeHtml(item.tipo_treinamento_nome)}</td>
          <td data-label="Aeronave">${escapeHtml(item.aeronave_modelo)}</td>
          <td data-label="Solo">${formatHours(item.solo_horas)}</td>
          <td data-label="PIC/SIC">${formatHours(item.voo_pic_sic_horas)}</td>
          <td data-label="CREW">${formatHours(item.voo_crew_horas)}</td>
          <td data-label="Observação">${escapeHtml(item.observacao || "-")}</td>
          <td class="actions ui-table-actions" data-label="Ações">
            ${capabilities.has("tipos_treinamento:edit") ? `<button type="button" class="button-link secondary training-root-hour-edit" data-hour-id="${item.id}">Editar</button>` : ""}
            ${capabilities.has("tipos_treinamento:delete") ? `<button type="button" class="link-danger training-root-hour-delete" data-hour-id="${item.id}" data-hour-name="${escapeAttr(item.aeronave_modelo)}">Excluir</button>` : ""}
          </td>
        </tr>
      `,
    )
    .join("");
}

export async function renderTrainingRootPage() {
  try {
    const filters = Object.fromEntries(hashQuery().entries());
    const tipoFilter = String(filters.tipo_treinamento_id || "");
    const hasActiveTypeFilter = Boolean(tipoFilter.trim());
    const capabilities = capabilitySet();
    const editingTypePromise = trainingRootState.typeEditId
      ? loadRequiredItem(`/api/v1/treinamento-raiz/tipos/${trainingRootState.typeEditId}`, "item", "Tipo de treinamento")
      : Promise.resolve(null);
    const editingSegmentPromise = trainingRootState.segmentEditId
      ? loadRequiredItem(`/api/v1/treinamento-raiz/segmentos/${trainingRootState.segmentEditId}`, "item", "Segmento teórico")
      : Promise.resolve(null);
    const editingHourPromise = trainingRootState.hourEditId
      ? loadRequiredItem(`/api/v1/treinamento-raiz/horas-voo/${trainingRootState.hourEditId}`, "item", "Referência de horas")
      : Promise.resolve(null);
    const [optionsResponse, typesResponse, segmentsResponse, hoursResponse, editingType, editingSegment, editingHour] = await Promise.all([
      api("/api/v1/treinamento-raiz/options"),
      api("/api/v1/treinamento-raiz/tipos"),
      tipoFilter
        ? api(`/api/v1/treinamento-raiz/segmentos?tipo_treinamento_id=${encodeURIComponent(tipoFilter)}`)
        : Promise.resolve({ data: { items: [] } }),
      tipoFilter
        ? api(`/api/v1/treinamento-raiz/horas-voo?tipo_treinamento_id=${encodeURIComponent(tipoFilter)}`)
        : Promise.resolve({ data: { items: [] } }),
      editingTypePromise,
      editingSegmentPromise,
      editingHourPromise,
    ]);
    const optionsPayload = optionsResponse.data?.options || {};
    const options = {
      tipos_treinamento: Array.isArray(optionsPayload.tipos_treinamento) ? optionsPayload.tipos_treinamento : [],
      status: Array.isArray(optionsPayload.status) ? optionsPayload.status : [],
      modelos_segmento: Array.isArray(optionsPayload.modelos_segmento) ? optionsPayload.modelos_segmento : [],
      periodicidades: Array.isArray(optionsPayload.periodicidades) ? optionsPayload.periodicidades : [],
      exige_aeronave: Array.isArray(optionsPayload.exige_aeronave) ? optionsPayload.exige_aeronave : [],
    };
    const types = Array.isArray(typesResponse.data?.items) ? typesResponse.data.items : [];
    const segments = Array.isArray(segmentsResponse.data?.items) ? segmentsResponse.data.items : [];
    const hours = Array.isArray(hoursResponse.data?.items) ? hoursResponse.data.items : [];
    const selectedType = selectedTypeFromOptions(options.tipos_treinamento || [], tipoFilter);

    const typeDefaults = editingType || { nome: "", codigo: "", descricao: "", status: "Ativo", exige_aeronave_label: "Não" };
    const segmentDefaults = editingSegment || {
      tipo_treinamento_id: tipoFilter || "",
      modelo_segmento: "Gerais",
      nome_segmento: "",
      carga_horaria: "",
      carga_teorica: "",
      carga_pratica: "",
      periodicidade_meses: 12,
      observacao: "",
    };
    const hourDefaults = editingHour || {
      tipo_treinamento_id: tipoFilter || "",
      aeronave_modelo: "",
      solo_horas: "",
      voo_pic_sic_horas: "",
      voo_crew_horas: "",
      observacao: "",
    };
    const canManageTypes = capabilities.has("tipos_treinamento:create") || capabilities.has("tipos_treinamento:edit");
    const activeTab = resolveTrainingRootActiveTab();
    const typeFormExpanded = Boolean(trainingRootState.typeEditId) || Boolean(trainingRootState.typeFormExpanded);
    const typeToggleLabel = resolveTrainingRootTypeToggleLabel(typeFormExpanded, Boolean(editingType));
    const segmentCount = selectedType ? segments.length : 0;
    const hourCount = selectedType ? hours.length : 0;

    renderShell(
      `
        <div class="training-reports-page-shell training-root-page-shell priority-page-surface ui-page-shell ui-stack">
        <div class="page-header priority-page-header ui-page-header ui-surface">
          <div>
            <h1>Cadastro raiz de treinamentos</h1>
          </div>
          <div class="page-header-actions">
            <a class="button-link secondary" href="#/treinamentos">Abrir cadastro por tripulante</a>
          </div>
        </div>

        ${renderTrainingRootFilterPanel(options, types, selectedType, tipoFilter, segmentCount, hourCount)}

        <section class="panel training-root-panel ui-surface ui-stack">
          <div class="training-root-tab-shell">
            <nav class="training-root-tab-nav" aria-label="Seções do cadastro raiz" role="tablist">
              <button type="button" class="training-root-tab${activeTab === "types" ? " is-active" : ""}" data-training-root-tab="types" id="training-root-tab-button-types" role="tab" aria-selected="${activeTab === "types" ? "true" : "false"}" aria-controls="training-root-tab-types" tabindex="${activeTab === "types" ? "0" : "-1"}">
                <span>Tipos de treinamento</span>
                <span class="training-root-tab-count">${formatInteger(types.length)}</span>
              </button>
              <button type="button" class="training-root-tab${activeTab === "segments" ? " is-active" : ""}" data-training-root-tab="segments" id="training-root-tab-button-segments" role="tab" aria-selected="${activeTab === "segments" ? "true" : "false"}" aria-controls="training-root-tab-segments" tabindex="${activeTab === "segments" ? "0" : "-1"}">
                <span>Segmentos teóricos</span>
                <span class="training-root-tab-count">${formatInteger(segmentCount)}</span>
              </button>
              <button type="button" class="training-root-tab${activeTab === "hours" ? " is-active" : ""}" data-training-root-tab="hours" id="training-root-tab-button-hours" role="tab" aria-selected="${activeTab === "hours" ? "true" : "false"}" aria-controls="training-root-tab-hours" tabindex="${activeTab === "hours" ? "0" : "-1"}">
                <span>Horas de voo</span>
                <span class="training-root-tab-count">${formatInteger(hourCount)}</span>
              </button>
            </nav>
            ${renderTrainingRootTypesTab({ capabilities, canManageTypes, activeTab, typeFormExpanded, typeToggleLabel, typeDefaults, options, types, editingType, selectedType })}
            ${renderTrainingRootSegmentsTab({ capabilities, canManageTypes, activeTab, hasActiveTypeFilter, options, segmentDefaults, editingSegment, selectedType, segments })}
            ${renderTrainingRootHoursTab({ capabilities, canManageTypes, activeTab, hasActiveTypeFilter, options, hourDefaults, editingHour, selectedType, hours })}
          </div>
        </section>
        </div>
      `,
      "Cadastro Raiz Treinamentos",
    );

    const trainingRootFilterForm = document.getElementById("training-root-filter-form");
    const trainingRootFilterSelect = document.getElementById("trainingRootTypeFilter");
    const trainingRootSegmentTypeSelect = document.querySelector('#training-root-segment-form select[name="tipo_treinamento_id"]');
    const trainingRootHourTypeSelect = document.querySelector('#training-root-hour-form select[name="tipo_treinamento_id"]');
    const trainingRootTypeToggle = document.querySelector("[data-training-root-type-toggle]");
    const trainingRootTypeFormShell = document.getElementById("training-root-type-form-shell");
    const trainingRootTabButtons = Array.from(document.querySelectorAll("[data-training-root-tab]"));
    const trainingRootTabPanels = Array.from(document.querySelectorAll("[data-training-root-panel]"));

    trainingRootFilterForm?.addEventListener("submit", (event) => {
      event.preventDefault();
    });

    const applyTrainingRootTabState = (nextTab) => {
      const normalizedTab = normalizeTrainingRootTab(nextTab);
      trainingRootState.activeTab = normalizedTab;
      trainingRootTabButtons.forEach((button) => {
        const isActive = button.dataset.trainingRootTab === normalizedTab;
        button.classList.toggle("is-active", isActive);
        button.setAttribute("aria-selected", String(isActive));
        button.tabIndex = isActive ? 0 : -1;
      });
      trainingRootTabPanels.forEach((panel) => {
        const isActive = panel.dataset.trainingRootPanel === normalizedTab;
        panel.classList.toggle("is-active", isActive);
        panel.hidden = !isActive;
        panel.setAttribute("aria-hidden", String(!isActive));
      });
    };

    const syncTrainingRootTypeFormState = () => {
      if (!trainingRootTypeFormShell) return;
      const expanded = Boolean(trainingRootState.typeEditId) || Boolean(trainingRootState.typeFormExpanded);
      trainingRootTypeFormShell.hidden = !expanded;
      trainingRootTypeFormShell.classList.toggle("is-expanded", expanded);
      trainingRootTypeFormShell.classList.toggle("is-collapsed", !expanded);
      if (trainingRootTypeToggle) {
        trainingRootTypeToggle.setAttribute("aria-expanded", String(expanded));
        trainingRootTypeToggle.textContent = resolveTrainingRootTypeToggleLabel(expanded, Boolean(trainingRootState.typeEditId));
      }
    };

    const syncTrainingRootTypeSelectors = () => {
      const activeTypeId = String(trainingRootFilterSelect?.value || "").trim();
      [trainingRootSegmentTypeSelect, trainingRootHourTypeSelect].forEach((select) => {
        if (!select) return;
        if (activeTypeId) {
          select.value = activeTypeId;
          select.disabled = true;
          return;
        }
        select.disabled = false;
      });
    };

    applyTrainingRootTabState(activeTab);
    syncTrainingRootTypeFormState();
    syncTrainingRootTypeSelectors();

    const typeDraft = wireCriticalFormDraftProtection({
      form: "training-root-type-form",
      formKey: `treinamento-raiz:tipo:${trainingRootState.typeEditId || "new"}`,
      baselineFields: {
        nome: typeDefaults.nome || "",
        codigo: typeDefaults.codigo || "",
        status: typeDefaults.status || "Ativo",
        exige_aeronave: typeDefaults.exige_aeronave_label || "",
        descricao: typeDefaults.descricao || "",
      },
      includeFields: ["nome", "codigo", "status", "exige_aeronave", "descricao"],
      feedbackTarget: "training-root-type-form",
      restoreMessage: "Rascunho local recuperado para tipo de treinamento.",
    });
    const segmentDraft = wireCriticalFormDraftProtection({
      form: "training-root-segment-form",
      formKey: `treinamento-raiz:segmento:${trainingRootState.segmentEditId || "new"}:${tipoFilter || "none"}`,
      baselineFields: {
        tipo_treinamento_id: segmentDefaults.tipo_treinamento_id || "",
        modelo_segmento: segmentDefaults.modelo_segmento || "",
        nome_segmento: segmentDefaults.nome_segmento || "",
        carga_horaria: segmentDefaults.carga_horaria || "",
        carga_teorica: segmentDefaults.carga_teorica || "",
        carga_pratica: segmentDefaults.carga_pratica || "",
        periodicidade_meses: segmentDefaults.periodicidade_meses || "",
        observacao: segmentDefaults.observacao || "",
      },
      includeFields: [
        "tipo_treinamento_id",
        "modelo_segmento",
        "nome_segmento",
        "carga_horaria",
        "carga_teorica",
        "carga_pratica",
        "periodicidade_meses",
        "observacao",
      ],
      feedbackTarget: "training-root-segment-form",
      restoreMessage: "Rascunho local recuperado para segmento teorico.",
    });
    const hourDraft = wireCriticalFormDraftProtection({
      form: "training-root-hour-form",
      formKey: `treinamento-raiz:horas:${trainingRootState.hourEditId || "new"}:${tipoFilter || "none"}`,
      baselineFields: {
        tipo_treinamento_id: hourDefaults.tipo_treinamento_id || "",
        aeronave_modelo: hourDefaults.aeronave_modelo || "",
        solo_horas: hourDefaults.solo_horas || "",
        voo_pic_sic_horas: hourDefaults.voo_pic_sic_horas || "",
        voo_crew_horas: hourDefaults.voo_crew_horas || "",
        observacao: hourDefaults.observacao || "",
      },
      includeFields: [
        "tipo_treinamento_id",
        "aeronave_modelo",
        "solo_horas",
        "voo_pic_sic_horas",
        "voo_crew_horas",
        "observacao",
      ],
      feedbackTarget: "training-root-hour-form",
      restoreMessage: "Rascunho local recuperado para referencia de horas.",
    });

    trainingRootFilterSelect?.addEventListener("change", () => {
      syncTrainingRootTypeSelectors();
      window.location.hash = buildTrainingRootFilterHref(trainingRootFilterSelect.value);
    });

    trainingRootTabButtons.forEach((button, index) => {
      button.addEventListener("click", () => {
        applyTrainingRootTabState(button.dataset.trainingRootTab);
      });
      button.addEventListener("keydown", (event) => {
        const keyActions = {
          ArrowRight: () => trainingRootTabButtons[(index + 1) % trainingRootTabButtons.length],
          ArrowDown: () => trainingRootTabButtons[(index + 1) % trainingRootTabButtons.length],
          ArrowLeft: () => trainingRootTabButtons[(index - 1 + trainingRootTabButtons.length) % trainingRootTabButtons.length],
          ArrowUp: () => trainingRootTabButtons[(index - 1 + trainingRootTabButtons.length) % trainingRootTabButtons.length],
          Home: () => trainingRootTabButtons[0],
          End: () => trainingRootTabButtons[trainingRootTabButtons.length - 1],
        };
        const resolveNext = keyActions[event.key];
        if (!resolveNext) return;
        event.preventDefault();
        const nextButton = resolveNext();
        nextButton?.focus();
        applyTrainingRootTabState(nextButton?.dataset.trainingRootTab);
      });
    });

    trainingRootTypeToggle?.addEventListener("click", async () => {
      if (trainingRootState.typeEditId) {
        typeDraft?.clear({ reason: "cancel_edit" });
        trainingRootState.typeEditId = null;
        trainingRootState.typeFormExpanded = false;
        await renderTrainingRootPage();
        return;
      }
      trainingRootState.typeFormExpanded = !trainingRootState.typeFormExpanded;
      syncTrainingRootTypeFormState();
    });

    document.getElementById("training-root-type-cancel")?.addEventListener("click", async () => {
      typeDraft?.clear({ reason: "cancel_edit" });
      trainingRootState.typeEditId = null;
      trainingRootState.typeFormExpanded = false;
      trainingRootState.activeTab = "types";
      await renderTrainingRootPage();
    });
    document.getElementById("training-root-segment-cancel")?.addEventListener("click", async () => {
      segmentDraft?.clear({ reason: "cancel_edit" });
      trainingRootState.segmentEditId = null;
      trainingRootState.activeTab = "segments";
      await renderTrainingRootPage();
    });
    document.getElementById("training-root-hour-cancel")?.addEventListener("click", async () => {
      hourDraft?.clear({ reason: "cancel_edit" });
      trainingRootState.hourEditId = null;
      trainingRootState.activeTab = "hours";
      await renderTrainingRootPage();
    });

    wireExplicitSubmit("training-root-type-form", "training-root-type-submit", async (event) => {
      event.preventDefault();
      const submitButton = document.getElementById("training-root-type-submit");
      const idleLabel = trainingRootState.typeEditId ? "Salvar tipo" : "Criar tipo";
      try {
        setSubmitButtonBusy(submitButton, true, idleLabel, "Salvando tipo...");
        await api(trainingRootState.typeEditId ? `/api/v1/treinamento-raiz/tipos/${trainingRootState.typeEditId}` : "/api/v1/treinamento-raiz/tipos", {
          method: trainingRootState.typeEditId ? "PUT" : "POST",
          json: Object.fromEntries(new FormData(event.currentTarget).entries()),
        });
        typeDraft?.clear({ reason: "save_success" });
        trainingRootState.typeEditId = null;
        trainingRootState.typeFormExpanded = false;
        trainingRootState.activeTab = "types";
        showFlash("Tipo de treinamento salvo com sucesso.", "success");
        await renderTrainingRootPage();
      } catch (error) {
        showFlash(buildErrorMessage(error), "error");
      } finally {
        setSubmitButtonBusy(submitButton, false, idleLabel, "Salvando tipo...");
      }
    });
    wireExplicitSubmit("training-root-segment-form", "training-root-segment-submit", async (event) => {
      event.preventDefault();
      const submitButton = document.getElementById("training-root-segment-submit");
      const idleLabel = trainingRootState.segmentEditId ? "Salvar segmento" : "Criar segmento";
      try {
        setSubmitButtonBusy(submitButton, true, idleLabel, "Salvando segmento...");
        const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
        if (hasActiveTypeFilter) {
          payload.tipo_treinamento_id = tipoFilter;
        }
        await api(trainingRootState.segmentEditId ? `/api/v1/treinamento-raiz/segmentos/${trainingRootState.segmentEditId}` : "/api/v1/treinamento-raiz/segmentos", {
          method: trainingRootState.segmentEditId ? "PUT" : "POST",
          json: payload,
        });
        segmentDraft?.clear({ reason: "save_success" });
        trainingRootState.segmentEditId = null;
        trainingRootState.activeTab = "segments";
        showFlash("Segmento salvo com sucesso.", "success");
        await renderTrainingRootPage();
      } catch (error) {
        showFlash(buildErrorMessage(error), "error");
      } finally {
        setSubmitButtonBusy(submitButton, false, idleLabel, "Salvando segmento...");
      }
    });
    wireExplicitSubmit("training-root-hour-form", "training-root-hour-submit", async (event) => {
      event.preventDefault();
      const submitButton = document.getElementById("training-root-hour-submit");
      const idleLabel = trainingRootState.hourEditId ? "Salvar horas" : "Criar horas";
      try {
        setSubmitButtonBusy(submitButton, true, idleLabel, "Salvando horas...");
        const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
        if (hasActiveTypeFilter) {
          payload.tipo_treinamento_id = tipoFilter;
        }
        await api(trainingRootState.hourEditId ? `/api/v1/treinamento-raiz/horas-voo/${trainingRootState.hourEditId}` : "/api/v1/treinamento-raiz/horas-voo", {
          method: trainingRootState.hourEditId ? "PUT" : "POST",
          json: payload,
        });
        hourDraft?.clear({ reason: "save_success" });
        trainingRootState.hourEditId = null;
        trainingRootState.activeTab = "hours";
        showFlash("Referencia de horas salva com sucesso.", "success");
        await renderTrainingRootPage();
      } catch (error) {
        showFlash(buildErrorMessage(error), "error");
      } finally {
        setSubmitButtonBusy(submitButton, false, idleLabel, "Salvando horas...");
      }
    });

    document.querySelectorAll(".training-root-type-edit").forEach((button) => {
      button.addEventListener("click", async () => {
        trainingRootState.typeEditId = Number(button.dataset.typeId);
        trainingRootState.typeFormExpanded = true;
        trainingRootState.activeTab = "types";
        await renderTrainingRootPage();
      });
    });
    document.querySelectorAll(".training-root-segment-edit").forEach((button) => {
      button.addEventListener("click", async () => {
        trainingRootState.segmentEditId = Number(button.dataset.segmentId);
        trainingRootState.activeTab = "segments";
        await renderTrainingRootPage();
      });
    });
    document.querySelectorAll(".training-root-hour-edit").forEach((button) => {
      button.addEventListener("click", async () => {
        trainingRootState.hourEditId = Number(button.dataset.hourId);
        trainingRootState.activeTab = "hours";
        await renderTrainingRootPage();
      });
    });

    document.querySelectorAll(".training-root-type-delete").forEach((button) => {
      button.addEventListener("click", async () => {
        if (!confirmAction({
          title: "Excluir este tipo de treinamento?",
          subject: button.dataset.typeName || "Tipo selecionado",
          consequence: "Segmentos e referências vinculadas podem impedir a exclusão ou exigir ajuste no cadastro raiz.",
        })) return;
        await withActionBusy(button, "Excluindo...", async () => {
          try {
            await api(`/api/v1/treinamento-raiz/tipos/${button.dataset.typeId}`, { method: "DELETE" });
            trainingRootState.activeTab = "types";
            showFlash("Tipo removido com sucesso.", "success");
            await renderTrainingRootPage();
          } catch (error) {
            showFlash(buildErrorMessage(error), "error");
            if (error?.status !== 401) await renderTrainingRootPage();
          }
        });
      });
    });
    document.querySelectorAll(".training-root-segment-delete").forEach((button) => {
      button.addEventListener("click", async () => {
        if (!confirmAction({
          title: "Excluir este segmento teórico?",
          subject: button.dataset.segmentName || "Segmento selecionado",
          consequence: "Registros de treinamento podem depender deste segmento.",
        })) return;
        await withActionBusy(button, "Excluindo...", async () => {
          try {
            await api(`/api/v1/treinamento-raiz/segmentos/${button.dataset.segmentId}`, { method: "DELETE" });
            trainingRootState.activeTab = "segments";
            showFlash("Segmento removido com sucesso.", "success");
            await renderTrainingRootPage();
          } catch (error) {
            showFlash(buildErrorMessage(error), "error");
            if (error?.status !== 401) await renderTrainingRootPage();
          }
        });
      });
    });
    document.querySelectorAll(".training-root-hour-delete").forEach((button) => {
      button.addEventListener("click", async () => {
        if (!confirmAction({
          title: "Excluir esta referência de horas de voo?",
          subject: button.dataset.hourName || "Referência selecionada",
          consequence: "Novos registros desse tipo/aeronave podem ficar sem referência de horas.",
        })) return;
        await withActionBusy(button, "Excluindo...", async () => {
          try {
            await api(`/api/v1/treinamento-raiz/horas-voo/${button.dataset.hourId}`, { method: "DELETE" });
            trainingRootState.activeTab = "hours";
            showFlash("Referência removida com sucesso.", "success");
            await renderTrainingRootPage();
          } catch (error) {
            showFlash(buildErrorMessage(error), "error");
            if (error?.status !== 401) await renderTrainingRootPage();
          }
        });
      });
    });
  } catch (error) {
    showFlash(buildErrorMessage(error), "error");
    renderShell("<section class='panel'><div class='empty'>Falha ao carregar o cadastro raiz de treinamentos.</div></section>", "Cadastro Raiz Treinamentos");
  }
}

