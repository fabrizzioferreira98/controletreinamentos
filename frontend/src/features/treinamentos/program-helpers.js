import {
  api,
  buildHashHref,
  escapeAttr,
  escapeHtml,
  formatDateBr,
  hashQuery,
  trainingStatusClass,
} from "../../lib.js";
export const TREINAMENTO_STATUS_OPTIONS = [
  { key: "vencido", label: "vencido" },
  { key: "a vencer", label: "a vencer" },
  { key: "regular", label: "regular" },
  { key: "sem informação", label: "sem informação" },
];

export function formatInteger(value) {
  const amount = Number(value || 0);
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 }).format(Number.isFinite(amount) ? amount : 0);
}

export function formatHours(value) {
  const amount = Number(value || 0);
  return new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(Number.isFinite(amount) ? amount : 0);
}

export function formatPeriodicityLabel(value) {
  const months = Number(value || 0);
  if (!months) return "Sem validade";
  return `${months} meses`;
}

function addMonthsIso(dateValue, months) {
  const raw = String(dateValue || "").trim();
  const totalMonths = Number(months || 0);
  if (!raw || !totalMonths) return "";
  const match = raw.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return "";
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(Date.UTC(year, month - 1, day));
  date.setUTCMonth(date.getUTCMonth() + totalMonths);
  if (date.getUTCDate() !== day) {
    date.setUTCDate(0);
  }
  const yyyy = date.getUTCFullYear();
  const mm = String(date.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(date.getUTCDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

export function buildDuePreview(dateValue, periodicidadeMeses) {
  const months = Number(periodicidadeMeses || 0);
  if (!months) {
    return { iso: "", label: "Sem validade" };
  }
  const iso = addMonthsIso(dateValue, months);
  return { iso, label: iso ? formatDateBr(iso) : "-" };
}

export function todayIso() {
  const now = new Date();
  const yyyy = now.getFullYear();
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

export function selectedTypeFromOptions(types, typeId) {
  return types.find((item) => String(item.id) === String(typeId || "")) || null;
}

function normalizeTrainingToken(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

export function trainingModelTheme(value) {
  const normalized = normalizeTrainingToken(value);
  if (normalized === "gerais") return "general";
  if (normalized === "especificos") return "specific";
  if (normalized === "especiais") return "special";
  if (normalized === "solo e voo") return "flight";
  return "other";
}

export function renderTrainingModelBadge(value) {
  const label = value || "Outros";
  return `<span class="training-chip training-chip--${trainingModelTheme(label)}">${escapeHtml(label)}</span>`;
}

export function renderTrainingWorkspaceTabs(activeTab) {
  return `
    <nav class="training-workspace-tabs" aria-label="Abas de treinamento">
      <a href="#/treinamentos/raiz" class="training-tab-link ${activeTab === "root" ? "active" : ""}" ${activeTab === "root" ? 'aria-current="page"' : ""}>
        <span class="training-tab-eyebrow">ABA 1</span>
        <strong>Cadastro raiz de treinamentos</strong>
      </a>
      <a href="#/treinamentos" class="training-tab-link ${activeTab === "records" ? "active" : ""}" ${activeTab === "records" ? 'aria-current="page"' : ""}>
        <span class="training-tab-eyebrow">ABA 2</span>
        <strong>Treinamento por tripulante</strong>
      </a>
    </nav>
  `;
}

export function renderTrainingFieldLegend(items) {
  return `
    <div class="training-field-legend">
      ${items
        .map(
          (item) => `
            <span class="training-field-token">
              <strong>${escapeHtml(item.label)}</strong>
              <span>${escapeHtml(item.description)}</span>
            </span>
          `,
        )
        .join("")}
    </div>
  `;
}

export function renderTrainingSectionLead(step, title, subtitle) {
  return `
    <header class="training-section-head">
      <div class="training-section-step">${escapeHtml(step)}</div>
      <div class="training-section-copy">
        <h2>${escapeHtml(title)}</h2>
        <p>${escapeHtml(subtitle)}</p>
      </div>
    </header>
  `;
}

export function renderTrainingMetric(label, value, caption = "") {
  return `
    <div class="training-hero-metric">
      <span class="training-hero-label">${escapeHtml(label)}</span>
      <strong>${escapeHtml(String(value))}</strong>
      ${caption ? `<span class="training-hero-caption">${escapeHtml(caption)}</span>` : ""}
    </div>
  `;
}

export function wireExplicitSubmit(formId, buttonId, handler) {
  const form = document.getElementById(formId);
  if (!form) return;

  form.addEventListener("submit", handler);

  const submitButton = document.getElementById(buttonId);
  if (!submitButton) return;
  submitButton.addEventListener("click", (event) => {
    event.preventDefault();
    if (typeof form.requestSubmit === "function") {
      form.requestSubmit();
      return;
    }
    form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
  });
}

export function setSubmitButtonBusy(button, busy, idleLabel, busyLabel) {
  if (!button) return;
  button.disabled = busy;
  button.textContent = busy ? busyLabel : idleLabel;
}

function assertFlowObject(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`Resposta inesperada em ${label}.`);
  }
  return value;
}

function assertFlowArray(value, label) {
  if (!Array.isArray(value)) {
    throw new Error(`Resposta inesperada em ${label}.`);
  }
  return value;
}

export function readTrainingProgramFilters() {
  return Object.fromEntries(hashQuery().entries());
}

export function navigateTrainingProgramFilters(filters) {
  window.location.hash = buildHashHref("#/treinamentos", filters);
}

export function adaptTrainingProgramOptions(payload) {
  const options = assertFlowObject(payload?.options, "treinamentos.options");
  return {
    tripulantes: assertFlowArray(options.tripulantes, "options.tripulantes"),
    tipos_treinamento: assertFlowArray(options.tipos_treinamento, "options.tipos_treinamento"),
    modelos_aeronave: assertFlowArray(options.modelos_aeronave, "options.modelos_aeronave"),
  };
}

export function adaptTrainingProgramRecords(payload) {
  return assertFlowArray(payload?.items, "treinamentos.items");
}

function normalizedTrainingStatus(value) {
  const normalized = normalizeTrainingToken(value);
  return normalized || "sem informacao";
}

function isMissingTrainingInformation(item) {
  return normalizedTrainingStatus(item?.status_calculado) === "sem informacao";
}

function trainingProgramStatusKey(item) {
  const normalized = normalizedTrainingStatus(item?.status_calculado);
  if (normalized === "vencido") return "vencidos";
  if (normalized === "a vencer") return "a_vencer";
  if (normalized === "regular" || normalized === "em dia") return "regulares";
  return "sem_informacao";
}

function trainingProgramNeedsAttention(item) {
  const key = trainingProgramStatusKey(item);
  return key === "vencidos" || key === "a_vencer" || key === "sem_informacao" || Number(item?.total_anexos || 0) <= 0;
}

function trainingProgramGroupBy(items) {
  const tripulantes = new Set(items.map((item) => String(item.tripulante_id || item.tripulante_nome || "").trim()).filter(Boolean));
  return tripulantes.size > 1 ? "tripulante" : "tipo";
}

function trainingProgramGroupKey(item, groupBy) {
  if (groupBy === "tripulante") return String(item.tripulante_id || item.tripulante_nome || "sem-tripulante");
  return String(item.tipo_treinamento_id || item.tipo_treinamento_nome || "sem-tipo");
}

function trainingProgramGroupLabel(item, groupBy) {
  if (groupBy === "tripulante") return item.tripulante_nome || "Tripulante nao informado";
  return item.tipo_treinamento_nome || "Tipo nao informado";
}

function buildTrainingProgramRecordGroups(items) {
  if (!items.length) return [];
  const groupBy = trainingProgramGroupBy(items);
  const groups = new Map();
  items.forEach((item) => {
    const key = trainingProgramGroupKey(item, groupBy);
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        label: trainingProgramGroupLabel(item, groupBy),
        groupBy,
        items: [],
      });
    }
    groups.get(key).items.push(item);
  });
  return Array.from(groups.values());
}

export function buildTrainingProgramOperationalSummary(items) {
  return (items || []).reduce(
    (summary, item) => {
      summary.total += 1;
      summary[trainingProgramStatusKey(item)] += 1;
      if (Number(item?.total_anexos || 0) <= 0) summary.sem_anexo += 1;
      return summary;
    },
    {
      total: 0,
      vencidos: 0,
      a_vencer: 0,
      regulares: 0,
      sem_informacao: 0,
      sem_anexo: 0,
    },
  );
}

function renderTrainingSelectionSnapshot(options, filters, selectedType, template) {
  const tripulante = (options.tripulantes || []).find((item) => String(item.id) === String(filters.tripulante_id || ""));
  const aircraftLabel = filters.aeronave_modelo || (selectedType && !selectedType.exige_aeronave ? "Não obrigatório" : "Não selecionado");
  return `
    <section class="training-snapshot-card">
      <div class="training-snapshot-title">Resumo da selecao</div>
      <div class="training-snapshot-grid">
        <div class="training-snapshot-item">
          <span>Tripulante</span>
          <strong>${escapeHtml(tripulante?.label || "Não selecionado")}</strong>
        </div>
        <div class="training-snapshot-item">
          <span>Tipo</span>
          <strong>${escapeHtml(selectedType?.nome || "Não selecionado")}</strong>
        </div>
        <div class="training-snapshot-item">
          <span>Aeronave</span>
          <strong>${escapeHtml(aircraftLabel)}</strong>
        </div>
        <div class="training-snapshot-item">
          <span>Segmentos disponiveis</span>
          <strong>${template ? formatInteger((template.segmentos || []).length) : "0"}</strong>
        </div>
      </div>
    </section>
  `;
}

export function renderTrainingProgramSelectorGroups(template) {
  return Object.entries(template.segmentos_por_modelo || {})
    .map(
      ([modelo, items]) => `
        <section class="training-selector-group">
          <div class="training-selector-group-head">
            <div class="training-selector-group-title">
              ${renderTrainingModelBadge(modelo)}
              <strong>${escapeHtml(modelo)}</strong>
            </div>
            <span>${formatInteger(items.length)} segmentos</span>
          </div>
          <div class="training-selector-list">
            ${items
              .map(
                (segment) => `
                  <label class="training-catalog-row" id="training-segment-row-${segment.id}">
                    <input
                      type="checkbox"
                      name="segmento_${segment.id}"
                      class="training-segment-checkbox"
                      data-segment-id="${segment.id}"
                      data-periodicity="${segment.periodicidade_meses}"
                      data-segment-name="${escapeAttr(segment.nome_segmento)}"
                    >
                    <span class="training-catalog-copy">
                      <span class="training-segment-name">${escapeHtml(segment.nome_segmento)}</span>
                      <span class="training-catalog-meta">
                        ${renderTrainingModelBadge(segment.modelo_segmento)}
                        <span>${formatHours(segment.carga_horaria)} h</span>
                        <span>${escapeHtml(segment.periodicidade_label || formatPeriodicityLabel(segment.periodicidade_meses))}</span>
                      </span>
                    </span>
                    <span class="training-catalog-hours">${formatHours(segment.carga_horaria)} h</span>
                  </label>
                `,
              )
              .join("")}
          </div>
        </section>
      `,
    )
    .join("");
}

export function renderTrainingProgramSelectedCards(template) {
  return (template.segmentos || [])
    .map(
      (segment) => `
        <article class="training-detail-card frontend-hidden" id="training-segment-card-${segment.id}">
          <header class="training-detail-head">
            <div>
              <div class="training-detail-kicker">Segmento selecionado</div>
              <h3>${escapeHtml(segment.nome_segmento)}</h3>
              <div class="training-detail-meta">
                ${renderTrainingModelBadge(segment.modelo_segmento)}
                <span>${formatHours(segment.carga_horaria)} h</span>
                <span>Periodicidade: ${escapeHtml(segment.periodicidade_label || formatPeriodicityLabel(segment.periodicidade_meses))}</span>
              </div>
            </div>
          </header>
          <div class="training-segment-card-grid">
            <label>
              Data de realização
              <input type="date" name="data_realizacao_${segment.id}" class="training-realizacao-input" data-segment-id="${segment.id}">
            </label>
            <label>
              Data de vencimento
              <input type="text" name="data_vencimento_preview_${segment.id}" id="training-vencimento-${segment.id}" value="${segment.periodicidade_meses ? "-" : "Sem validade"}" readonly>
            </label>
            <label>
              Anexo PDF
              <input type="file" name="arquivo_${segment.id}" accept="application/pdf">
            </label>
            <label class="full-width">
              Observação
              <textarea name="observacao_${segment.id}" rows="2"></textarea>
            </label>
            ${
              template.ctac_required
                ? `
                  <label>
                    Solo horas (CTAC)
                    <input type="number" step="0.1" min="0" name="ctac_solo_horas_${segment.id}" placeholder="Informe o valor">
                  </label>
                  <label>
                    Voo PIC/SIC horas (CTAC)
                    <input type="number" step="0.1" min="0" name="ctac_voo_pic_sic_horas_${segment.id}" placeholder="Informe o valor">
                  </label>
                  <label>
                    Voo CREW horas (CTAC)
                    <input type="number" step="0.1" min="0" name="ctac_voo_crew_horas_${segment.id}" placeholder="Informe o valor">
                  </label>
                `
                : ""
            }
          </div>
        </article>
      `,
    )
    .join("");
}

export async function loadRequiredItem(path, itemKey = "item", label = "registro") {
  const { data } = await api(path);
  const item = data[itemKey];
  if (!item) {
    throw new Error(`${label} não encontrado para edição.`);
  }
  return item;
}

export function renderHoursReference(template) {
  const hours = template?.horas_voo;
  if (!hours) {
    return `
      <section class="panel">
        <div class="empty">Não há referência de horas de voo para o modelo selecionado.</div>
      </section>
    `;
  }
  const ctac = template.ctac_required;
  return `
    <section class="panel">
      <div class="page-header compact-page-header">
        <div>
          <h2>Referência de horas de voo</h2>
          <p class="page-subtitle">Dados carregados em tempo real da ABA 1 para o tipo e aeronave selecionados.</p>
        </div>
      </div>
      <section class="summary-grid compact-summary-grid">
        <div class="summary-card"><strong>Solo</strong><span>${ctac ? "Conforme CTAC" : `${formatHours(hours.solo_horas)} h`}</span></div>
        <div class="summary-card"><strong>Voo PIC/SIC</strong><span>${ctac ? "Conforme CTAC" : `${formatHours(hours.voo_pic_sic_horas)} h`}</span></div>
        <div class="summary-card"><strong>Voo CREW</strong><span>${ctac ? "Conforme CTAC" : `${formatHours(hours.voo_crew_horas)} h`}</span></div>
      </section>
      ${hours.observacao ? `<div class="hint ui-panel-offset-sm">${escapeHtml(hours.observacao)}</div>` : ""}
    </section>
  `;
}

export function renderTrainingProgramRecordsTable(items, capabilities) {
  const safeItems = items || [];
  const groups = buildTrainingProgramRecordGroups(safeItems);
  const canOpenDetail = capabilities.has("treinamentos:view") || capabilities.has("treinamentos:edit") || capabilities.has("treinamentos_anexos:view");
  const canDelete = capabilities.has("treinamentos:delete");
  const renderRecordRow = (item) => {
    const totalAnexos = Number(item.total_anexos || 0);
    const missingEvidence = totalAnexos <= 0;
    const needsAttention = trainingProgramNeedsAttention(item);
    const actionLabel = capabilities.has("treinamentos:edit")
      ? needsAttention
        ? "Regularizar"
        : "Editar"
      : "Abrir";
    const evidenceLabel = missingEvidence ? "Sem evidência" : "Com evidência";
    const evidenceClass = missingEvidence ? "training-evidence-chip--missing" : "training-evidence-chip--present";
    return `
      <tr
        class="training-program-record-row ${needsAttention ? "is-attention" : ""} ${missingEvidence ? "is-missing-evidence" : ""}"
        data-responsive-row="record"
      >
        <td data-label="Tripulante">
          <div class="primary-cell">${escapeHtml(item.tripulante_nome)}</div>
          <div class="secondary-cell">${escapeHtml(item.tripulante_matricula || "-")}</div>
        </td>
        <td data-label="Treinamento">
          <div class="primary-cell">${escapeHtml(item.tipo_treinamento_nome)}</div>
          <div class="secondary-cell">${escapeHtml(item.tipo_treinamento_codigo || "-")}</div>
        </td>
        <td data-label="Segmento">
          <div class="primary-cell">${escapeHtml(item.segmento_nome)}</div>
          <div class="secondary-cell">${escapeHtml(item.modelo_segmento || "-")}</div>
        </td>
        <td data-label="Aeronave">${escapeHtml(item.aeronave_modelo || "-")}</td>
        <td data-label="Realização">${escapeHtml(formatDateBr(item.data_realizacao))}</td>
        <td data-label="Vencimento">${escapeHtml(item.periodicidade_meses ? formatDateBr(item.data_vencimento) : "Sem validade")}</td>
        <td data-label="Status">
          <span class="status-pill ${trainingStatusClass(item.status_calculado)}">${escapeHtml(item.status_calculado || "sem informação")}</span>
        </td>
        <td data-label="Anexos">
          <span class="training-evidence-chip ${evidenceClass}">${evidenceLabel}</span>
          <span class="secondary-cell">${formatInteger(totalAnexos)} ${totalAnexos === 1 ? "anexo" : "anexos"}</span>
        </td>
        <td class="actions ui-table-actions" data-label="Ações">
          ${canOpenDetail ? `<a href="#/treinamentos/${item.id}">${escapeHtml(actionLabel)}</a>` : ""}
          ${
            canDelete
              ? `<button type="button" class="link-danger training-program-record-delete" data-record-id="${item.id}" data-record-label="${escapeAttr(`${item.tripulante_nome || "-"} - ${item.tipo_treinamento_nome || "-"} - ${item.segmento_nome || "-"}`)}">Excluir</button>`
              : ""
          }
        </td>
      </tr>
    `;
  };

  return `
    <div class="table-wrap ui-table-wrap ui-table-density-compact">
      <table class="data-table responsive-cards">
        <thead>
          <tr>
            <th>Tripulante</th>
            <th>Treinamento</th>
            <th>Segmento</th>
            <th>Aeronave</th>
            <th>Realização</th>
            <th>Vencimento</th>
            <th>Status</th>
            <th>Anexos</th>
            <th>Ações</th>
          </tr>
        </thead>
        <tbody>
          ${
            safeItems.length
              ? groups
                  .map(
                    (group) => `
                      <tr class="training-program-group-row" data-responsive-row="group">
                        <td colspan="9">
                          <div class="training-program-group-head">
                            <span>${group.groupBy === "tripulante" ? "Tripulante" : "Tipo"}</span>
                            <strong>${escapeHtml(group.label)}</strong>
                            <small>${formatInteger(group.items.length)} ${group.items.length === 1 ? "registro" : "registros"} · ${formatInteger(group.items.filter(trainingProgramNeedsAttention).length)} em atenção · ${formatInteger(group.items.filter(isMissingTrainingInformation).length)} sem informação</small>
                          </div>
                        </td>
                      </tr>
                      ${group.items.map(renderRecordRow).join("")}
                    `,
                  )
                  .join("")
              : `
                <tr data-responsive-row="empty">
                  <td colspan="9" class="empty operational-empty ui-table-state" data-empty-type="no-results">
                    <strong>Sem registros para os filtros atuais</strong>
                    <span>Ajuste base, tripulante, tipo ou aeronave para localizar treinamentos já registrados.</span>
                  </td>
                </tr>
              `
          }
        </tbody>
      </table>
    </div>
  `;
}

