import {
  api,
  booleanLabel,
  buildErrorMessage,
  buildHashHref,
  capabilitySet,
  escapeAttr,
  escapeHtml,
  fileToDataUrl,
  formatDateBr,
  showFlash,
  trainingStatusClass,
  hashQuery,
} from "./lib.20260430-142420.cf58b4b4395e.js";
import { renderShell } from "./shell.20260430-142420.eed3fe973fa2.js";

const trainingRootState = {
  typeEditId: null,
  segmentEditId: null,
  hourEditId: null,
};

function formatInteger(value) {
  const amount = Number(value || 0);
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 }).format(Number.isFinite(amount) ? amount : 0);
}

function formatHours(value) {
  const amount = Number(value || 0);
  return new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(Number.isFinite(amount) ? amount : 0);
}

function formatPeriodicityLabel(value) {
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
  if (date.getUTCDate() !== day) date.setUTCDate(0);
  const yyyy = date.getUTCFullYear();
  const mm = String(date.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(date.getUTCDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function buildDuePreview(dateValue, periodicidadeMeses) {
  const months = Number(periodicidadeMeses || 0);
  if (!months) {
    return { iso: "", label: "Sem validade" };
  }
  const iso = addMonthsIso(dateValue, months);
  return { iso, label: iso ? formatDateBr(iso) : "-" };
}

function todayIso() {
  const now = new Date();
  const yyyy = now.getFullYear();
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function selectedTypeFromOptions(types, typeId) {
  return types.find((item) => String(item.id) === String(typeId || "")) || null;
}

async function loadOptionalItem(path, itemKey = "item") {
  try {
    const { data } = await api(path);
    return data[itemKey] || null;
  } catch (_error) {
    return null;
  }
}

function normalizeTrainingToken(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

function trainingModelTheme(value) {
  const normalized = normalizeTrainingToken(value);
  if (normalized === "gerais") return "general";
  if (normalized === "especificos") return "specific";
  if (normalized === "especiais") return "special";
  if (normalized === "solo e voo") return "flight";
  return "other";
}

function renderTrainingModelBadge(value) {
  const label = value || "Outros";
  return `<span class="training-chip training-chip--${trainingModelTheme(label)}">${escapeHtml(label)}</span>`;
}

const TRAINING_ROOT_SEGMENT_GROUP_ORDER = ["Gerais", "Específicos", "Especiais", "Solo e Voo", "Outros"];

function normalizeTrainingRootSegmentGroup(value) {
  const normalized = normalizeTrainingToken(value);
  if (normalized === "gerais") return "Gerais";
  if (normalized === "especificos") return "Específicos";
  if (normalized === "especiais") return "Especiais";
  if (normalized === "solo e voo") return "Solo e Voo";
  return "Outros";
}

function renderTrainingRootInstructionRow(colspan, message) {
  return `<tr><td colspan="${colspan}" class="empty">${escapeHtml(message)}</td></tr>`;
}

function countTrainingRootAircraftModels(items) {
  return new Set(
    (items || [])
      .map((item) => String(item.aeronave_modelo || "").trim())
      .filter(Boolean),
  ).size;
}

function renderTrainingRootSegmentsRows(items, selectedType, capabilities) {
  if (!selectedType) {
    return renderTrainingRootInstructionRow(6, "Selecione um tipo de treinamento para visualizar os segmentos.");
  }

  if (!items.length) {
    return renderTrainingRootInstructionRow(6, "Nenhum segmento cadastrado para o tipo selecionado.");
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
        <tr>
          <td colspan="6"><strong>${escapeHtml(groupName)}</strong></td>
        </tr>
        ${groupItems
          .map(
            (item) => `
              <tr>
                <td data-label="Tipo">
                  <div class="primary-cell">${escapeHtml(item.tipo_treinamento_nome)}</div>
                  <div class="secondary-cell">${escapeHtml(item.tipo_treinamento_codigo || "-")}</div>
                </td>
                <td data-label="Modelo">${renderTrainingModelBadge(item.modelo_segmento)}</td>
                <td data-label="Segmento">
                  <div class="primary-cell">${escapeHtml(item.nome_segmento)}</div>
                  <div class="secondary-cell">${escapeHtml(item.observacao || "Sem observacao")}</div>
                </td>
                <td data-label="Carga">
                  <div class="primary-cell">${formatHours(item.carga_horaria)} h</div>
                  <div class="secondary-cell">Teorica ${formatHours(item.carga_teorica)} h · Pratica ${formatHours(item.carga_pratica)} h</div>
                </td>
                <td data-label="Periodicidade">${escapeHtml(item.periodicidade_label || formatPeriodicityLabel(item.periodicidade_meses))}</td>
                <td class="actions" data-label="Ações">
                  ${capabilities.has("tipos_treinamento:edit") ? `<button type="button" class="button-link secondary training-root-segment-edit" data-segment-id="${item.id}">Editar</button>` : ""}
                  ${capabilities.has("tipos_treinamento:delete") ? `<button type="button" class="link-danger training-root-segment-delete" data-segment-id="${item.id}">Excluir</button>` : ""}
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
    return renderTrainingRootInstructionRow(5, "Selecione um tipo de treinamento para visualizar as horas de voo.");
  }

  if (!items.length) {
    return renderTrainingRootInstructionRow(5, "Nenhuma referência de horas de voo cadastrada para o tipo selecionado.");
  }

  return items
    .map(
      (item) => `
        <tr>
          <td data-label="Tipo">
            <div class="primary-cell">${escapeHtml(item.tipo_treinamento_nome)}</div>
            <div class="secondary-cell">${escapeHtml(item.tipo_treinamento_codigo || "-")}</div>
          </td>
          <td data-label="Aeronave">
            <div class="primary-cell">${escapeHtml(item.aeronave_modelo)}</div>
            <div class="secondary-cell">${item.conforme_ctac ? '<span class="training-chip training-chip--warning">Conforme CTAC</span>' : "Referência fixa"}</div>
          </td>
          <td data-label="Horas">
            <div class="primary-cell">Solo ${formatHours(item.solo_horas)} h</div>
            <div class="secondary-cell">PIC/SIC ${formatHours(item.voo_pic_sic_horas)} h · CREW ${formatHours(item.voo_crew_horas)} h</div>
          </td>
          <td data-label="Observação">${escapeHtml(item.observacao || "-")}</td>
          <td class="actions" data-label="Ações">
            ${capabilities.has("tipos_treinamento:edit") ? `<button type="button" class="button-link secondary training-root-hour-edit" data-hour-id="${item.id}">Editar</button>` : ""}
            ${capabilities.has("tipos_treinamento:delete") ? `<button type="button" class="link-danger training-root-hour-delete" data-hour-id="${item.id}">Excluir</button>` : ""}
          </td>
        </tr>
      `,
    )
    .join("");
}

function buildTrainingRootFilterHref(tipoTreinamentoId) {
  const nextTypeId = String(tipoTreinamentoId || "").trim();
  return nextTypeId
    ? buildHashHref("#/treinamentos/raiz", { tipo_treinamento_id: nextTypeId })
    : "#/treinamentos/raiz";
}

function renderTrainingWorkspaceTabs(activeTab) {
  return `
    <nav class="training-workspace-tabs" aria-label="Abas de treinamento">
      <a href="#/treinamentos/raiz" class="training-tab-link ${activeTab === "root" ? "active" : ""}">
        <span class="training-tab-eyebrow">ABA 1</span>
        <strong>Cadastro raiz de treinamentos</strong>
      </a>
      <a href="#/treinamentos" class="training-tab-link ${activeTab === "records" ? "active" : ""}">
        <span class="training-tab-eyebrow">ABA 2</span>
        <strong>Treinamento por tripulante</strong>
      </a>
    </nav>
  `;
}

function renderTrainingFieldLegend(items) {
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

function renderTrainingSectionLead(step, title, subtitle) {
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

function renderTrainingMetric(label, value, caption = "") {
  return `
    <div class="training-hero-metric">
      <span class="training-hero-label">${escapeHtml(label)}</span>
      <strong>${escapeHtml(String(value))}</strong>
      ${caption ? `<span class="training-hero-caption">${escapeHtml(caption)}</span>` : ""}
    </div>
  `;
}

function renderTrainingSelectionSnapshot(options, filters, selectedType, template) {
  const tripulante = (options.tripulantes || []).find((item) => String(item.id) === String(filters.tripulante_id || ""));
  const aircraftLabel = filters.aeronave_modelo || (selectedType && !selectedType.exige_aeronave ? "N?o obrigat?rio" : "N?o selecionado");
  return `
    <section class="training-snapshot-card">
      <div class="training-snapshot-title">Resumo da sele??o</div>
      <div class="training-snapshot-grid">
        <div class="training-snapshot-item">
          <span>Tripulante</span>
          <strong>${escapeHtml(tripulante?.label || "N?o selecionado")}</strong>
        </div>
        <div class="training-snapshot-item">
          <span>Tipo</span>
          <strong>${escapeHtml(selectedType?.nome || "N?o selecionado")}</strong>
        </div>
        <div class="training-snapshot-item">
          <span>Aeronave</span>
          <strong>${escapeHtml(aircraftLabel)}</strong>
        </div>
        <div class="training-snapshot-item">
          <span>Segmentos dispon?veis</span>
          <strong>${template ? formatInteger((template.segmentos || []).length) : "0"}</strong>
        </div>
      </div>
    </section>
  `;
}

function renderHoursReference(template) {
  const hours = template?.horas_voo;
  if (!hours) {
    return `
      <section class="panel training-inline-empty">
        <div class="empty">N?o h? refer?ncia de horas de voo para o modelo selecionado.</div>
      </section>
    `;
  }
  const ctac = template.ctac_required;
  return `
    <section class="panel training-hours-reference">
      <div class="training-card-head">
        <div>
          <h3>Refer?ncia de horas de voo</h3>
          <p>Valores carregados em tempo real da ABA 1 para o tipo e a aeronave selecionados.</p>
        </div>
      </div>
      <section class="summary-grid compact-summary-grid">
        <div class="summary-card"><strong>Solo</strong><span>${ctac ? "Conforme CTAC" : `${formatHours(hours.solo_horas)} h`}</span></div>
        <div class="summary-card"><strong>Voo PIC/SIC</strong><span>${ctac ? "Conforme CTAC" : `${formatHours(hours.voo_pic_sic_horas)} h`}</span></div>
        <div class="summary-card"><strong>Voo CREW</strong><span>${ctac ? "Conforme CTAC" : `${formatHours(hours.voo_crew_horas)} h`}</span></div>
      </section>
      ${hours.observacao ? `<div class="hint training-hours-note">${escapeHtml(hours.observacao)}</div>` : ""}
    </section>
  `;
}

function renderTrainingProgramRecordsTable(items, capabilities) {
  return `
    <div class="table-wrap">
      <table class="data-table responsive-cards">
        <thead>
          <tr>
            <th>Tripulante</th>
            <th>Treinamento</th>
            <th>Segmento</th>
            <th>Aeronave</th>
            <th>Realizacao</th>
            <th>Vencimento</th>
            <th>Status</th>
            <th>A??es</th>
          </tr>
        </thead>
        <tbody>
          ${
            items.length
              ? items
                  .map(
                    (item) => `
                      <tr>
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
                        <td data-label="Realizacao">${escapeHtml(formatDateBr(item.data_realizacao))}</td>
                        <td data-label="Vencimento">${escapeHtml(item.periodicidade_meses ? formatDateBr(item.data_vencimento) : "Sem validade")}</td>
                        <td data-label="Status"><span class="status-pill ${trainingStatusClass(item.status_calculado)}">${escapeHtml(item.status_calculado || "-")}</span></td>
                        <td class="actions" data-label="A??es">
                          ${capabilities.has("treinamentos:edit") ? `<a href="#/treinamentos/${item.id}">Editar</a>` : ""}
                          ${capabilities.has("treinamentos:delete") ? `<button type="button" class="link-danger training-program-record-delete" data-record-id="${item.id}">Excluir</button>` : ""}
                        </td>
                      </tr>
                    `,
                  )
                  .join("")
              : '<tr><td colspan="8" class="empty">Nenhum treinamento registrado para os filtros atuais.</td></tr>'
          }
        </tbody>
      </table>
    </div>
  `;
}

function renderTrainingProgramSelectorGroups(template) {
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

function renderTrainingProgramSelectedCards(template) {
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
              Data de realizacao
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
              Observa??o
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

export async function renderTreinamentosListPageV2() {
  try {
    const filters = Object.fromEntries(hashQuery().entries());
    const capabilities = capabilitySet();
    const [optionsResponse, recordsResponse] = await Promise.all([
      api("/api/v1/treinamentos-tripulantes/options"),
      api(`/api/v1/treinamentos-tripulantes?${new URLSearchParams(filters).toString()}`),
    ]);
    const options = optionsResponse.data.options;
    const records = recordsResponse.data.items || [];
    const selectedType = selectedTypeFromOptions(options.tipos_treinamento || [], filters.tipo_treinamento_id);
    const recordsWithAttachments = records.filter((item) => Number(item.total_anexos || 0) > 0).length;

    let template = null;
    let templateError = "";
    if (selectedType && (!selectedType.exige_aeronave || filters.aeronave_modelo)) {
      try {
        const templateResponse = await api(
          `/api/v1/treinamentos-tripulantes/template?${new URLSearchParams({
            tipo_treinamento_id: String(filters.tipo_treinamento_id || ""),
            aeronave_modelo: String(filters.aeronave_modelo || ""),
          }).toString()}`,
        );
        template = templateResponse.data.template;
      } catch (error) {
        templateError = buildErrorMessage(error);
      }
    }

    renderShell(
      `
        ${renderTrainingWorkspaceTabs("records")}

        <section class="training-hero-panel">
          <div class="training-hero-copy">
            <span class="training-hero-kicker">ABA 2 - Execucao por tripulante</span>
            <h1>Cadastro de treinamento para tripulante</h1>
            <p>Escolha o tripulante, carregue o programa a partir da ABA 1 e registre somente os segmentos executados, cada um com seu proprio ciclo de validade.</p>
          </div>
          <div class="training-hero-metrics">
            ${renderTrainingMetric("Tripulantes", formatInteger((options.tripulantes || []).length), "Origem no cadastro existente")}
            ${renderTrainingMetric("Tipos ativos", formatInteger((options.tipos_treinamento || []).length), selectedType ? selectedType.nome : "Selecione um tipo")}
            ${renderTrainingMetric("Registros", formatInteger(records.length), "Historico filtrado")}
            ${renderTrainingMetric("PDFs vinculados", formatInteger(recordsWithAttachments), "Anexos por segmento")}
          </div>
        </section>

        <div class="training-legend">
          <span>Fluxo: tripulante -> tipo -> aeronave -> segmentos -> datas -> anexos -> salvar.</span>
          <span>A ABA 2 consulta a ABA 1 em tempo real e nao duplica definicoes.</span>
        </div>

        <section class="panel training-stage-panel">
          ${renderTrainingSectionLead("Etapa 1", "Identificacao do treinamento", "Defina o contexto antes de carregar o programa operacional do tripulante.")}
          <div class="training-stage-grid">
            <div class="training-stage-main">
              <form id="training-program-selection-form" class="filters filters-wide training-selection-form">
                <select name="tripulante_id" required>
                  <option value="">Tripulante</option>
                  ${(options.tripulantes || [])
                    .map(
                      (item) => `<option value="${item.id}" ${String(filters.tripulante_id || "") === String(item.id) ? "selected" : ""}>${escapeHtml(item.label || item.nome)}</option>`,
                    )
                    .join("")}
                </select>
                <select name="tipo_treinamento_id" id="trainingProgramType" required>
                  <option value="">Tipo de treinamento</option>
                  ${(options.tipos_treinamento || [])
                    .map(
                      (item) => `
                        <option
                          value="${item.id}"
                          data-exige-aeronave="${item.exige_aeronave ? 1 : 0}"
                          ${String(filters.tipo_treinamento_id || "") === String(item.id) ? "selected" : ""}
                        >${escapeHtml(item.nome)}</option>
                      `,
                    )
                    .join("")}
                </select>
                <select name="aeronave_modelo" id="trainingProgramAircraft">
                  <option value="">Modelo de aeronave</option>
                  ${(options.modelos_aeronave || [])
                    .map(
                      (item) => `<option value="${escapeAttr(item.aeronave_modelo)}" ${String(filters.aeronave_modelo || "") === String(item.aeronave_modelo) ? "selected" : ""}>${escapeHtml(item.aeronave_modelo)}</option>`,
                    )
                    .join("")}
                </select>
                <button type="submit">Carregar programa</button>
                <a class="button-link secondary" href="#/treinamentos">Limpar</a>
              </form>
              <div class="hint training-selection-hint" id="trainingProgramSelectionHint">
                ${
                  selectedType
                    ? selectedType.exige_aeronave
                      ? "Este tipo exige a sele??o do modelo de aeronave para carregar horas e segmentos."
                      : "Este tipo nao exige aeronave obrigatoria e pode ser montado sem modelo."
                    : "Selecione o tipo de treinamento para habilitar o carregamento do programa."
                }
              </div>
            </div>
            <aside class="training-stage-side">
              ${renderTrainingSelectionSnapshot(options, filters, selectedType, template)}
              ${templateError ? `<div class="flash error">${escapeHtml(templateError)}</div>` : ""}
              ${template ? renderHoursReference(template) : '<section class="panel training-inline-empty"><div class="empty">A refer?ncia de horas aparece assim que o programa for carregado.</div></section>'}
            </aside>
          </div>
        </section>

        ${
          template
            ? `
              <section class="panel training-stage-panel">
                ${renderTrainingSectionLead("Etapas 2, 3 e 4", "Segmentos e preenchimento", "Selecione os segmentos, avance para o preenchimento e registre um item por segmento.")}
                <form id="training-program-batch-form" class="training-program-batch-form training-program-workbench">
                  <input type="hidden" name="tripulante_id" value="${escapeAttr(filters.tripulante_id || "")}">
                  <input type="hidden" name="tipo_treinamento_id" value="${escapeAttr(filters.tipo_treinamento_id || "")}">
                  <input type="hidden" name="aeronave_modelo" value="${escapeAttr(filters.aeronave_modelo || "")}">

                  <section class="training-workbench-pane">
                    <div class="training-pane-head">
                      <div>
                        <h3>Etapa 2 - Selecione os segmentos</h3>
                        <p>Marque apenas os segmentos que o tripulante realizou ou precisa renovar agora.</p>
                      </div>
                      <span class="training-pane-counter">${formatInteger((template.segmentos || []).length)} disponiveis</span>
                    </div>
                    ${renderTrainingProgramSelectorGroups(template)}
                    <div class="training-selector-actions">
                      <button type="button" id="trainingProgramContinueButton">Continuar para preenchimento de datas</button>
                      <button type="button" class="button-link secondary" id="trainingProgramResetButton">Limpar sele??o</button>
                    </div>
                  </section>

                  <section class="training-workbench-pane training-workbench-pane--details">
                    <div class="training-selected-empty" id="trainingStep3Placeholder">
                      Selecione os segmentos e clique em "Continuar para preenchimento de datas" para liberar a Etapa 3.
                    </div>
                    <div class="frontend-hidden" id="trainingStep3Container">
                      <div class="training-pane-head">
                        <div>
                          <h3>Etapa 3 - Preenchimento de datas e documentos</h3>
                          <p>Apenas os segmentos marcados aparecem abaixo. Preencha realizacao, vencimento, observacao e PDF por segmento.</p>
                        </div>
                        <span class="training-pane-counter"><span id="trainingSelectedCount">0</span> selecionados</span>
                      </div>
                      ${template.ctac_required ? '<div class="training-inline-alert">Referencia "Conforme CTAC" detectada. Informe as horas reais para cada segmento marcado.</div>' : ""}
                      <div class="training-selected-empty" id="trainingSelectedEmpty">
                        Marque um ou mais segmentos no catalogo para liberar o preenchimento detalhado.
                      </div>
                      <div class="training-selected-stack">
                        ${renderTrainingProgramSelectedCards(template)}
                      </div>
                      <div class="form-actions training-submit-bar">
                        ${
                          capabilities.has("treinamentos:create")
                            ? '<button type="submit">Salvar segmentos marcados</button>'
                            : '<div class="hint">Seu perfil possui apenas visualizacao para este modulo.</div>'
                        }
                      </div>
                    </div>
                  </section>
                </form>
              </section>
            `
            : `
              <section class="panel training-inline-empty">
                <div class="empty">
                  ${
                    selectedType
                      ? selectedType.exige_aeronave && !filters.aeronave_modelo
                        ? "Selecione o modelo de aeronave para carregar o programa completo."
                        : "Selecione um tripulante e carregue o programa para abrir os segmentos."
                      : "Selecione um tipo de treinamento para iniciar a aba 2."
                  }
                </div>
              </section>
            `
        }

        <section class="panel training-stage-panel">
          ${renderTrainingSectionLead("Historico", "Registros salvos", "Cada linha representa um segmento salvo individualmente, com vencimento proprio.")}
          <section class="summary-grid compact-summary-grid">
            <div class="summary-card"><strong>Total</strong><span>${formatInteger(records.length)}</span></div>
            <div class="summary-card"><strong>Com vencimento</strong><span>${formatInteger(records.filter((item) => item.periodicidade_meses > 0).length)}</span></div>
            <div class="summary-card"><strong>Sem validade</strong><span>${formatInteger(records.filter((item) => !item.periodicidade_meses).length)}</span></div>
            <div class="summary-card"><strong>Com anexo</strong><span>${formatInteger(recordsWithAttachments)}</span></div>
          </section>
          ${renderTrainingProgramRecordsTable(records, capabilities)}
        </section>
      `,
      "Treinamentos por Tripulante",
    );

    document.getElementById("training-program-selection-form")?.addEventListener("submit", (event) => {
      event.preventDefault();
      const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
      window.location.hash = buildHashHref("#/treinamentos", payload);
    });

    document.querySelectorAll(".training-program-record-delete").forEach((button) => {
      button.addEventListener("click", async () => {
        if (!window.confirm("Excluir este registro de treinamento?")) return;
        try {
          await api(`/api/v1/treinamentos-tripulantes/${button.dataset.recordId}`, { method: "DELETE" });
          showFlash("Registro excluido com sucesso.", "success");
          await renderTreinamentosListPageV2();
        } catch (error) {
          showFlash(buildErrorMessage(error), "error");
        }
      });
    });

    if (!template) return;

    const batchForm = document.getElementById("training-program-batch-form");
    const segmentCheckboxes = Array.from(document.querySelectorAll(".training-segment-checkbox"));
    let detailsUnlocked = false;

    function resetSegmentCard(segmentId) {
      const checkbox = document.querySelector(`.training-segment-checkbox[data-segment-id="${segmentId}"]`);
      const dateInput = batchForm?.querySelector(`[name="data_realizacao_${segmentId}"]`);
      const duePreview = document.getElementById(`training-vencimento-${segmentId}`);
      const fileInput = batchForm?.querySelector(`[name="arquivo_${segmentId}"]`);
      const observacao = batchForm?.querySelector(`[name="observacao_${segmentId}"]`);
      const ctacInputs = [
        batchForm?.querySelector(`[name="ctac_solo_horas_${segmentId}"]`),
        batchForm?.querySelector(`[name="ctac_voo_pic_sic_horas_${segmentId}"]`),
        batchForm?.querySelector(`[name="ctac_voo_crew_horas_${segmentId}"]`),
      ];
      if (dateInput) dateInput.value = "";
      if (duePreview) duePreview.value = checkbox?.dataset?.periodicity === "0" ? "Sem validade" : "-";
      if (fileInput) fileInput.value = "";
      if (observacao) observacao.value = "";
      ctacInputs.forEach((input) => {
        if (input) input.value = "";
      });
    }

    function primeSegmentCard(segmentId) {
      const dateInput = batchForm?.querySelector(`[name="data_realizacao_${segmentId}"]`);
      if (dateInput && !dateInput.value) {
        dateInput.value = todayIso();
      }
    }

    function syncSegmentCard(segmentId) {
      const checkbox = document.querySelector(`.training-segment-checkbox[data-segment-id="${segmentId}"]`);
      const row = document.getElementById(`training-segment-row-${segmentId}`);
      const card = document.getElementById(`training-segment-card-${segmentId}`);
      const dateInput = batchForm?.querySelector(`[name="data_realizacao_${segmentId}"]`);
      const duePreview = document.getElementById(`training-vencimento-${segmentId}`);
      if (!checkbox || !row || !card || !dateInput || !duePreview) return;
      const selected = checkbox.checked;
      const enabled = detailsUnlocked && selected;
      row.classList.toggle("is-selected", selected);
      card.classList.toggle("frontend-hidden", !enabled);
      dateInput.required = enabled;
      if (!selected) {
        duePreview.value = checkbox.dataset.periodicity === "0" ? "Sem validade" : "-";
        return;
      }
      if (enabled) {
        primeSegmentCard(segmentId);
      }
      const preview = buildDuePreview(dateInput.value, checkbox.dataset.periodicity);
      duePreview.value = preview.label;
    }

    function syncSelectedState() {
      const selectedCount = segmentCheckboxes.filter((checkbox) => checkbox.checked).length;
      const counter = document.getElementById("trainingSelectedCount");
      if (counter) counter.textContent = String(selectedCount);
      document.getElementById("trainingSelectedEmpty")?.classList.toggle("frontend-hidden", selectedCount > 0);
      document.getElementById("trainingStep3Container")?.classList.toggle("frontend-hidden", !detailsUnlocked);
      document.getElementById("trainingStep3Placeholder")?.classList.toggle("frontend-hidden", detailsUnlocked);
    }

    function syncSelectionHint() {
      const hint = document.getElementById("trainingProgramSelectionHint");
      const typeSelect = document.getElementById("trainingProgramType");
      const aircraftSelect = document.getElementById("trainingProgramAircraft");
      if (!hint || !typeSelect || !aircraftSelect) return;
      const selected = typeSelect.options[typeSelect.selectedIndex];
      const requiresAircraft = selected?.dataset?.exigeAeronave === "1";
      aircraftSelect.required = requiresAircraft;
      if (!selected?.value) {
        hint.textContent = "Selecione o tipo de treinamento para habilitar o carregamento do programa.";
        return;
      }
      if (requiresAircraft && !aircraftSelect.value) {
        hint.textContent = "Este tipo exige a sele??o do modelo de aeronave para carregar horas e segmentos.";
        return;
      }
      hint.textContent = requiresAircraft
        ? "Programa carregado com refer?ncia de horas por aeronave."
        : "Programa carregado sem obrigatoriedade de aeronave.";
    }

    document.getElementById("trainingProgramType")?.addEventListener("change", syncSelectionHint);
    document.getElementById("trainingProgramAircraft")?.addEventListener("change", syncSelectionHint);
    syncSelectionHint();

    document.getElementById("trainingProgramContinueButton")?.addEventListener("click", () => {
      const selectedCount = segmentCheckboxes.filter((checkbox) => checkbox.checked).length;
      if (!selectedCount) {
        showFlash("Nenhum segmento selecionado. Marque pelo menos um segmento antes de continuar.", "error");
        return;
      }
      detailsUnlocked = true;
      segmentCheckboxes.forEach((checkbox) => syncSegmentCard(checkbox.dataset.segmentId));
      syncSelectedState();
      document.getElementById("trainingStep3Container")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });

    document.getElementById("trainingProgramResetButton")?.addEventListener("click", () => {
      detailsUnlocked = false;
      segmentCheckboxes.forEach((checkbox) => {
        checkbox.checked = false;
        resetSegmentCard(checkbox.dataset.segmentId);
        syncSegmentCard(checkbox.dataset.segmentId);
      });
      syncSelectedState();
      showFlash("Sele??o de segmentos limpa.", "success");
    });

    segmentCheckboxes.forEach((checkbox) => {
      const segmentId = checkbox.dataset.segmentId;
      checkbox.addEventListener("change", () => {
        if (detailsUnlocked && checkbox.checked) {
          primeSegmentCard(segmentId);
        }
        syncSegmentCard(segmentId);
        syncSelectedState();
      });
      batchForm?.querySelector(`[name="data_realizacao_${segmentId}"]`)?.addEventListener("change", () => syncSegmentCard(segmentId));
      syncSegmentCard(segmentId);
    });
    syncSelectedState();

    batchForm?.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        const selectedSegments = segmentCheckboxes.filter((checkbox) => checkbox.checked);
        if (!selectedSegments.length) {
          showFlash("Selecione ao menos um segmento para salvar.", "error");
          return;
        }
        const segmentPayload = [];
        for (const checkbox of selectedSegments) {
          const segmentId = checkbox.dataset.segmentId;
          const fileInput = batchForm.querySelector(`[name="arquivo_${segmentId}"]`);
          const file = fileInput?.files?.[0] || null;
          if (file && file.type && file.type !== "application/pdf") {
            showFlash(`O anexo do segmento ${segmentId} precisa ser PDF.`, "error");
            return;
          }
          const item = {
            segmento_id: Number(segmentId),
            data_realizacao: batchForm.querySelector(`[name="data_realizacao_${segmentId}"]`)?.value || "",
            observacao: batchForm.querySelector(`[name="observacao_${segmentId}"]`)?.value || "",
          };
          if (template.ctac_required) {
            item.ctac_solo_horas = batchForm.querySelector(`[name="ctac_solo_horas_${segmentId}"]`)?.value || "";
            item.ctac_voo_pic_sic_horas = batchForm.querySelector(`[name="ctac_voo_pic_sic_horas_${segmentId}"]`)?.value || "";
            item.ctac_voo_crew_horas = batchForm.querySelector(`[name="ctac_voo_crew_horas_${segmentId}"]`)?.value || "";
          }
          if (file) {
            item.filename = file.name;
            item.arquivo_base64 = await fileToDataUrl(file);
          }
          segmentPayload.push(item);
        }
        await api("/api/v1/treinamentos-tripulantes/batch", {
          method: "POST",
          json: {
            tripulante_id: Number(batchForm.querySelector('[name="tripulante_id"]')?.value || 0),
            tipo_treinamento_id: Number(batchForm.querySelector('[name="tipo_treinamento_id"]')?.value || 0),
            aeronave_modelo: batchForm.querySelector('[name="aeronave_modelo"]')?.value || "",
            segmentos: segmentPayload,
          },
        });
        showFlash("Segmentos registrados com sucesso.", "success");
        await renderTreinamentosListPageV2();
      } catch (error) {
        showFlash(buildErrorMessage(error), "error");
      }
    });
  } catch (error) {
    showFlash(buildErrorMessage(error), "error");
    renderShell("<section class='panel'><div class='empty'>Falha ao carregar a aba de treinamentos por tripulante.</div></section>", "Treinamentos por Tripulante");
  }
}

async function renderTrainingRootPageV2Legacy() {
  try {
    const filters = Object.fromEntries(hashQuery().entries());
    const tipoFilter = String(filters.tipo_treinamento_id || "");
    const capabilities = capabilitySet();
    const [optionsResponse, typesResponse, segmentsResponse, hoursResponse] = await Promise.all([
      api("/api/v1/treinamento-raiz/options"),
      api("/api/v1/treinamento-raiz/tipos"),
      tipoFilter
        ? api(`/api/v1/treinamento-raiz/segmentos?tipo_treinamento_id=${encodeURIComponent(tipoFilter)}`)
        : Promise.resolve({ data: { items: [] } }),
      tipoFilter
        ? api(`/api/v1/treinamento-raiz/horas-voo?tipo_treinamento_id=${encodeURIComponent(tipoFilter)}`)
        : Promise.resolve({ data: { items: [] } }),
    ]);

    const options = optionsResponse.data.options;
    const types = typesResponse.data.items || [];
    const segments = segmentsResponse.data.items || [];
    const hours = hoursResponse.data.items || [];
    const selectedType = selectedTypeFromOptions(options.tipos_treinamento || [], tipoFilter);
    const editingType = trainingRootState.typeEditId ? await loadOptionalItem(`/api/v1/treinamento-raiz/tipos/${trainingRootState.typeEditId}`) : null;
    const editingSegment = trainingRootState.segmentEditId ? await loadOptionalItem(`/api/v1/treinamento-raiz/segmentos/${trainingRootState.segmentEditId}`) : null;
    const editingHour = trainingRootState.hourEditId ? await loadOptionalItem(`/api/v1/treinamento-raiz/horas-voo/${trainingRootState.hourEditId}`) : null;

    const typeDefaults = editingType || { nome: "", codigo: "", descricao: "", status: "Ativo", exige_aeronave_label: "N?o" };
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

    renderShell(
      `
        ${renderTrainingWorkspaceTabs("root")}

        <section class="training-hero-panel">
          <div class="training-hero-copy">
            <span class="training-hero-kicker">ABA 1 - Banco mestre</span>
            <h1>Cadastro raiz de treinamentos</h1>
            <p>Esta ? a fonte ?nica da verdade para tipos, segmentos te?ricos e horas de voo por aeronave. Tudo o que a ABA 2 consome nasce aqui.</p>
          </div>
          <div class="training-hero-metrics">
            ${renderTrainingMetric("Tipos", formatInteger(types.length), `${formatInteger(types.filter((item) => item.ativo).length)} ativos`)}
            ${renderTrainingMetric("Segmentos", formatInteger(selectedType ? segments.length : 0), selectedType ? selectedType.nome : "Selecione um tipo")}
            ${renderTrainingMetric("Horas voo", formatInteger(selectedType ? hours.length : 0), selectedType ? `${formatInteger(countTrainingRootAircraftModels(hours))} aeronaves` : "Selecione um tipo")}
            ${renderTrainingMetric("Filtro ativo", selectedType ? selectedType.nome : "Não", selectedType ? "Escopo reduzido" : "Nenhum tipo selecionado")}
          </div>
        </section>

        <div class="training-legend">
          <span>ABA 1 = tipos + segmentos te?ricos + horas de voo por aeronave.</span>
          <span>A ABA 2 consulta estes dados em tempo real e nao duplica definicoes.</span>
        </div>

        ${renderTrainingFieldLegend([
          { label: "SELECT", description: "listas dinamicas, status e relacoes" },
          { label: "TEXTO", description: "nome, codigo, observacao e descricao" },
          { label: "NUMERO", description: "cargas e horas operacionais" },
          { label: "CALCULO", description: "periodicidade e regras derivadas" },
        ])}

        <section class="panel training-stage-panel">
          ${renderTrainingSectionLead("Filtro", "Escopo da fonte mestre", "Use o filtro por tipo para focar segmentos e horas sem perder a visao central do cadastro.")}
          <div class="training-toolbar-panel">
            <form id="training-root-filter-form" class="filters filters-wide training-root-filter-form">
              <select name="tipo_treinamento_id" id="trainingRootTypeFilter">
                <option value="">Filtrar segmentos e horas por tipo</option>
                ${(options.tipos_treinamento || [])
                  .map((item) => `<option value="${item.id}" ${String(tipoFilter) === String(item.id) ? "selected" : ""}>${escapeHtml(item.nome)}</option>`)
                  .join("")}
              </select>
              <button type="submit" disabled aria-disabled="true">Aplicar filtro</button>
              <a class="button-link secondary" href="#/treinamentos/raiz">Limpar</a>
            </form>
            <div class="training-toolbar-note">
              <strong>${escapeHtml(selectedType?.nome || "Nenhum tipo selecionado")}</strong>
              <span>${selectedType ? "As duas grades abaixo estão sincronizadas com o tipo selecionado." : "Selecione um tipo para carregar automaticamente segmentos e horas de voo."}</span>
            </div>
          </div>
        </section>

        <section class="panel training-stage-panel">
          ${renderTrainingSectionLead("1", "Tipos de treinamento", "Defina o catalogo principal que alimenta a aba operacional.")}
          <div class="training-master-layout">
            <div class="training-master-editor">
              <div class="training-editor-card">
                <div class="training-card-head">
                  <div>
                    <h3>${editingType ? "Editar tipo" : "Novo tipo"}</h3>
                    <p>Nome, codigo, status e exigencia de aeronave no mesmo bloco.</p>
                  </div>
                </div>
                ${
                  capabilities.has("tipos_treinamento:create") || capabilities.has("tipos_treinamento:edit")
                    ? `
                      <form id="training-root-type-form" class="form-grid training-master-form">
                        <label>Nome<input type="text" name="nome" value="${escapeAttr(typeDefaults.nome || "")}" required></label>
                        <label>C?digo<input type="text" name="codigo" value="${escapeAttr(typeDefaults.codigo || "")}" required></label>
                        <label>
                          Status
                          <select name="status">
                            ${(options.status || []).map((item) => `<option value="${escapeAttr(item)}" ${typeDefaults.status === item ? "selected" : ""}>${escapeHtml(item)}</option>`).join("")}
                          </select>
                        </label>
                        <label>
                          Exige aeronave
                          <select name="exige_aeronave">
                            ${(options.exige_aeronave || []).map((item) => `<option value="${escapeAttr(item)}" ${String(typeDefaults.exige_aeronave_label || "N?o") === String(item) ? "selected" : ""}>${escapeHtml(item)}</option>`).join("")}
                          </select>
                        </label>
                        <label class="full-width">Descricao<textarea name="descricao" rows="3">${escapeHtml(typeDefaults.descricao || "")}</textarea></label>
                        <div class="form-actions full-width">
                          <button type="submit">${editingType ? "Salvar tipo" : "Criar tipo"}</button>
                          ${editingType ? '<button type="button" class="button-link secondary" id="training-root-type-cancel">Cancelar</button>' : ""}
                        </div>
                      </form>
                    `
                    : '<div class="hint">Seu perfil n?o possui permiss?o para alterar o cadastro raiz.</div>'
                }
              </div>
            </div>
            <div class="training-master-register">
              <div class="training-data-card">
                <div class="training-card-head">
                  <div>
                    <h3>Tipos cadastrados</h3>
                    <p>Visao operacional do banco mestre com contagem de segmentos e horas.</p>
                  </div>
                </div>
                <div class="table-wrap">
                  <table class="data-table responsive-cards">
                    <thead><tr><th>Tipo</th><th>C?digo</th><th>Status</th><th>Exige</th><th>Uso</th><th>A??es</th></tr></thead>
                    <tbody>
                      ${
                        types.length
                          ? types
                              .map(
                                (item) => `
                                  <tr>
                                    <td data-label="Tipo">
                                      <div class="primary-cell">${escapeHtml(item.nome)}</div>
                                      <div class="secondary-cell">${escapeHtml(item.descricao || "Sem descricao")}</div>
                                    </td>
                                    <td data-label="C?digo"><span class="training-mono-tag">${escapeHtml(item.codigo || "-")}</span></td>
                                    <td data-label="Status"><span class="status-pill ${item.ativo ? "status-green" : "status-red"}">${escapeHtml(item.status)}</span></td>
                                    <td data-label="Exige"><span class="training-inline-value">${escapeHtml(booleanLabel(item.exige_aeronave))}</span></td>
                                    <td data-label="Uso">
                                      <div class="primary-cell">${formatInteger(item.total_segmentos)} segmentos</div>
                                      <div class="secondary-cell">${formatInteger(item.total_horas_voo)} refer?ncias</div>
                                    </td>
                                    <td class="actions" data-label="A??es">
                                      ${capabilities.has("tipos_treinamento:edit") ? `<button type="button" class="button-link secondary training-root-type-edit" data-type-id="${item.id}">Editar</button>` : ""}
                                      ${capabilities.has("tipos_treinamento:delete") ? `<button type="button" class="link-danger training-root-type-delete" data-type-id="${item.id}">Excluir</button>` : ""}
                                    </td>
                                  </tr>
                                `,
                              )
                              .join("")
                          : '<tr><td colspan="6" class="empty">Nenhum tipo cadastrado.</td></tr>'
                      }
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section class="panel training-stage-panel">
          ${renderTrainingSectionLead("2", "Segmentos te?ricos", "Monte o programa com modelo, carga e periodicidade por segmento.")}
          <div class="training-master-layout">
            <div class="training-master-editor">
              <div class="training-editor-card">
                <div class="training-card-head">
                  <div>
                    <h3>${editingSegment ? "Editar segmento" : "Novo segmento"}</h3>
                    <p>Todo segmento nasce vinculado a um tipo de treinamento do banco mestre.</p>
                  </div>
                </div>
                ${
                  capabilities.has("tipos_treinamento:create") || capabilities.has("tipos_treinamento:edit")
                    ? `
                      <form id="training-root-segment-form" class="form-grid training-master-form">
                        <label>
                          Tipo
                          <select name="tipo_treinamento_id" required>
                            <option value="">Selecione</option>
                            ${(options.tipos_treinamento || []).map((item) => `<option value="${item.id}" ${String(segmentDefaults.tipo_treinamento_id || "") === String(item.id) ? "selected" : ""}>${escapeHtml(item.nome)}</option>`).join("")}
                          </select>
                        </label>
                        <label>
                          Modelo do segmento
                          <select name="modelo_segmento" required>
                            ${(options.modelos_segmento || []).map((item) => `<option value="${escapeAttr(item)}" ${String(segmentDefaults.modelo_segmento || "") === String(item) ? "selected" : ""}>${escapeHtml(item)}</option>`).join("")}
                          </select>
                        </label>
                        <label class="full-width">Nome do segmento<input type="text" name="nome_segmento" value="${escapeAttr(segmentDefaults.nome_segmento || "")}" required></label>
                        <label>Carga hor?ria<input type="number" step="0.1" min="0" name="carga_horaria" value="${escapeAttr(segmentDefaults.carga_horaria || "")}"></label>
                        <label>Carga teorica<input type="number" step="0.1" min="0" name="carga_teorica" value="${escapeAttr(segmentDefaults.carga_teorica || "")}"></label>
                        <label>Carga pratica<input type="number" step="0.1" min="0" name="carga_pratica" value="${escapeAttr(segmentDefaults.carga_pratica || "")}"></label>
                        <label>
                          Periodicidade
                          <select name="periodicidade_meses">
                            ${(options.periodicidades || []).map((item) => `<option value="${item.value}" ${String(segmentDefaults.periodicidade_meses || 0) === String(item.value) ? "selected" : ""}>${escapeHtml(item.label)}</option>`).join("")}
                          </select>
                        </label>
                        <label class="full-width">Observa??o<textarea name="observacao" rows="2">${escapeHtml(segmentDefaults.observacao || "")}</textarea></label>
                        <div class="form-actions full-width">
                          <button type="submit">${editingSegment ? "Salvar segmento" : "Criar segmento"}</button>
                          ${editingSegment ? '<button type="button" class="button-link secondary" id="training-root-segment-cancel">Cancelar</button>' : ""}
                        </div>
                      </form>
                    `
                    : '<div class="hint">Seu perfil n?o possui permiss?o para alterar segmentos.</div>'
                }
              </div>
            </div>
            <div class="training-master-register">
              <div class="training-data-card">
                <div class="training-card-head">
                  <div>
                    <h3>Segmentos cadastrados</h3>
                    <p>Visualize por tipo, modelo e regra de validade.</p>
                  </div>
                </div>
                <div class="table-wrap">
                  <table class="data-table responsive-cards">
                    <thead><tr><th>Tipo</th><th>Modelo</th><th>Segmento</th><th>Carga</th><th>Periodicidade</th><th>A??es</th></tr></thead>
                    <tbody>
                      ${
                        segments.length
                          ? segments
                              .map(
                                (item) => `
                                  <tr>
                                    <td data-label="Tipo">
                                      <div class="primary-cell">${escapeHtml(item.tipo_treinamento_nome)}</div>
                                      <div class="secondary-cell">${escapeHtml(item.tipo_treinamento_codigo || "-")}</div>
                                    </td>
                                    <td data-label="Modelo">${renderTrainingModelBadge(item.modelo_segmento)}</td>
                                    <td data-label="Segmento">
                                      <div class="primary-cell">${escapeHtml(item.nome_segmento)}</div>
                                      <div class="secondary-cell">${escapeHtml(item.observacao || "Sem observacao")}</div>
                                    </td>
                                    <td data-label="Carga">
                                      <div class="primary-cell">${formatHours(item.carga_horaria)} h</div>
                                      <div class="secondary-cell">Teorica ${formatHours(item.carga_teorica)} h · Pratica ${formatHours(item.carga_pratica)} h</div>
                                    </td>
                                    <td data-label="Periodicidade">${escapeHtml(item.periodicidade_label || formatPeriodicityLabel(item.periodicidade_meses))}</td>
                                    <td class="actions" data-label="A??es">
                                      ${capabilities.has("tipos_treinamento:edit") ? `<button type="button" class="button-link secondary training-root-segment-edit" data-segment-id="${item.id}">Editar</button>` : ""}
                                      ${capabilities.has("tipos_treinamento:delete") ? `<button type="button" class="link-danger training-root-segment-delete" data-segment-id="${item.id}">Excluir</button>` : ""}
                                    </td>
                                  </tr>
                                `,
                              )
                              .join("")
                          : '<tr><td colspan="6" class="empty">Nenhum segmento encontrado.</td></tr>'
                      }
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section class="panel training-stage-panel">
          ${renderTrainingSectionLead("3", "Horas de voo por aeronave", "Cadastre a refer?ncia operacional por tipo e por modelo de aeronave.")}
          <div class="training-master-layout">
            <div class="training-master-editor">
              <div class="training-editor-card">
                <div class="training-card-head">
                  <div>
                    <h3>${editingHour ? "Editar refer?ncia" : "Nova refer?ncia"}</h3>
                    <p>As horas variam por tipo de treinamento e por modelo de aeronave.</p>
                  </div>
                </div>
                ${
                  capabilities.has("tipos_treinamento:create") || capabilities.has("tipos_treinamento:edit")
                    ? `
                      <form id="training-root-hour-form" class="form-grid training-master-form">
                        <label>
                          Tipo
                          <select name="tipo_treinamento_id" required>
                            <option value="">Selecione</option>
                            ${(options.tipos_treinamento || []).map((item) => `<option value="${item.id}" ${String(hourDefaults.tipo_treinamento_id || "") === String(item.id) ? "selected" : ""}>${escapeHtml(item.nome)}</option>`).join("")}
                          </select>
                        </label>
                        <label>Modelo de aeronave<input type="text" name="aeronave_modelo" value="${escapeAttr(hourDefaults.aeronave_modelo || "")}" required></label>
                        <label>Solo horas<input type="number" step="0.1" min="0" name="solo_horas" value="${escapeAttr(hourDefaults.solo_horas || "")}"></label>
                        <label>Voo PIC/SIC horas<input type="number" step="0.1" min="0" name="voo_pic_sic_horas" value="${escapeAttr(hourDefaults.voo_pic_sic_horas || "")}"></label>
                        <label>Voo CREW horas<input type="number" step="0.1" min="0" name="voo_crew_horas" value="${escapeAttr(hourDefaults.voo_crew_horas || "")}"></label>
                        <label class="full-width">Observa??o<textarea name="observacao" rows="2">${escapeHtml(hourDefaults.observacao || "")}</textarea></label>
                        <div class="form-actions full-width">
                          <button type="submit">${editingHour ? "Salvar refer?ncia" : "Criar refer?ncia"}</button>
                          ${editingHour ? '<button type="button" class="button-link secondary" id="training-root-hour-cancel">Cancelar</button>' : ""}
                        </div>
                      </form>
                    `
                    : '<div class="hint">Seu perfil n?o possui permiss?o para alterar horas de voo.</div>'
                }
              </div>
            </div>
            <div class="training-master-register">
              <div class="training-data-card">
                <div class="training-card-head">
                  <div>
                    <h3>Refer?ncias por aeronave</h3>
                    <p>Use esta grade para revisar horas, exce??es e casos "Conforme CTAC".</p>
                  </div>
                </div>
                <div class="table-wrap">
                  <table class="data-table responsive-cards">
                    <thead><tr><th>Tipo</th><th>Aeronave</th><th>Horas</th><th>Observa??o</th><th>A??es</th></tr></thead>
                    <tbody>
                      ${
                        hours.length
                          ? hours
                              .map(
                                (item) => `
                                  <tr>
                                    <td data-label="Tipo">
                                      <div class="primary-cell">${escapeHtml(item.tipo_treinamento_nome)}</div>
                                      <div class="secondary-cell">${escapeHtml(item.tipo_treinamento_codigo || "-")}</div>
                                    </td>
                                    <td data-label="Aeronave">
                                      <div class="primary-cell">${escapeHtml(item.aeronave_modelo)}</div>
                                      <div class="secondary-cell">${item.conforme_ctac ? '<span class="training-chip training-chip--warning">Conforme CTAC</span>' : "Refer?ncia fixa"}</div>
                                    </td>
                                    <td data-label="Horas">
                                      <div class="primary-cell">Solo ${formatHours(item.solo_horas)} h</div>
                                      <div class="secondary-cell">PIC/SIC ${formatHours(item.voo_pic_sic_horas)} h · CREW ${formatHours(item.voo_crew_horas)} h</div>
                                    </td>
                                    <td data-label="Observa??o">${escapeHtml(item.observacao || "-")}</td>
                                    <td class="actions" data-label="A??es">
                                      ${capabilities.has("tipos_treinamento:edit") ? `<button type="button" class="button-link secondary training-root-hour-edit" data-hour-id="${item.id}">Editar</button>` : ""}
                                      ${capabilities.has("tipos_treinamento:delete") ? `<button type="button" class="link-danger training-root-hour-delete" data-hour-id="${item.id}">Excluir</button>` : ""}
                                    </td>
                                  </tr>
                                `,
                              )
                              .join("")
                          : '<tr><td colspan="5" class="empty">Nenhuma refer?ncia de horas encontrada.</td></tr>'
                      }
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </section>
      `,
      "Cadastro Raiz Treinamentos",
    );

    document.getElementById("training-root-filter-form")?.addEventListener("submit", (event) => {
      event.preventDefault();
      window.location.hash = buildHashHref("#/treinamentos/raiz", Object.fromEntries(new FormData(event.currentTarget).entries()));
    });

    document.getElementById("training-root-type-cancel")?.addEventListener("click", async () => {
      trainingRootState.typeEditId = null;
      await renderTrainingRootPageV2();
    });
    document.getElementById("training-root-segment-cancel")?.addEventListener("click", async () => {
      trainingRootState.segmentEditId = null;
      await renderTrainingRootPageV2();
    });
    document.getElementById("training-root-hour-cancel")?.addEventListener("click", async () => {
      trainingRootState.hourEditId = null;
      await renderTrainingRootPageV2();
    });

    document.getElementById("training-root-type-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await api(trainingRootState.typeEditId ? `/api/v1/treinamento-raiz/tipos/${trainingRootState.typeEditId}` : "/api/v1/treinamento-raiz/tipos", {
          method: trainingRootState.typeEditId ? "PUT" : "POST",
          json: Object.fromEntries(new FormData(event.currentTarget).entries()),
        });
        trainingRootState.typeEditId = null;
        showFlash("Tipo de treinamento salvo com sucesso.", "success");
        await renderTrainingRootPageV2();
      } catch (error) {
        showFlash(buildErrorMessage(error), "error");
      }
    });
    document.getElementById("training-root-segment-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await api(trainingRootState.segmentEditId ? `/api/v1/treinamento-raiz/segmentos/${trainingRootState.segmentEditId}` : "/api/v1/treinamento-raiz/segmentos", {
          method: trainingRootState.segmentEditId ? "PUT" : "POST",
          json: Object.fromEntries(new FormData(event.currentTarget).entries()),
        });
        trainingRootState.segmentEditId = null;
        showFlash("Segmento salvo com sucesso.", "success");
        await renderTrainingRootPageV2();
      } catch (error) {
        showFlash(buildErrorMessage(error), "error");
      }
    });
    document.getElementById("training-root-hour-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await api(trainingRootState.hourEditId ? `/api/v1/treinamento-raiz/horas-voo/${trainingRootState.hourEditId}` : "/api/v1/treinamento-raiz/horas-voo", {
          method: trainingRootState.hourEditId ? "PUT" : "POST",
          json: Object.fromEntries(new FormData(event.currentTarget).entries()),
        });
        trainingRootState.hourEditId = null;
        showFlash("Referencia de horas salva com sucesso.", "success");
        await renderTrainingRootPageV2();
      } catch (error) {
        showFlash(buildErrorMessage(error), "error");
      }
    });

    document.querySelectorAll(".training-root-type-edit").forEach((button) => {
      button.addEventListener("click", async () => {
        trainingRootState.typeEditId = Number(button.dataset.typeId);
        await renderTrainingRootPageV2();
      });
    });
    document.querySelectorAll(".training-root-segment-edit").forEach((button) => {
      button.addEventListener("click", async () => {
        trainingRootState.segmentEditId = Number(button.dataset.segmentId);
        await renderTrainingRootPageV2();
      });
    });
    document.querySelectorAll(".training-root-hour-edit").forEach((button) => {
      button.addEventListener("click", async () => {
        trainingRootState.hourEditId = Number(button.dataset.hourId);
        await renderTrainingRootPageV2();
      });
    });

    document.querySelectorAll(".training-root-type-delete").forEach((button) => {
      button.addEventListener("click", async () => {
        if (!window.confirm("Excluir este tipo de treinamento?")) return;
        try {
          await api(`/api/v1/treinamento-raiz/tipos/${button.dataset.typeId}`, { method: "DELETE" });
          showFlash("Tipo removido com sucesso.", "success");
          await renderTrainingRootPageV2();
        } catch (error) {
          showFlash(buildErrorMessage(error), "error");
        }
      });
    });
    document.querySelectorAll(".training-root-segment-delete").forEach((button) => {
      button.addEventListener("click", async () => {
        if (!window.confirm("Excluir este segmento te?rico?")) return;
        try {
          await api(`/api/v1/treinamento-raiz/segmentos/${button.dataset.segmentId}`, { method: "DELETE" });
          showFlash("Segmento removido com sucesso.", "success");
          await renderTrainingRootPageV2();
        } catch (error) {
          showFlash(buildErrorMessage(error), "error");
        }
      });
    });
    document.querySelectorAll(".training-root-hour-delete").forEach((button) => {
      button.addEventListener("click", async () => {
        if (!window.confirm("Excluir esta refer?ncia de horas de voo?")) return;
        try {
          await api(`/api/v1/treinamento-raiz/horas-voo/${button.dataset.hourId}`, { method: "DELETE" });
          showFlash("Refer?ncia removida com sucesso.", "success");
          await renderTrainingRootPageV2();
        } catch (error) {
          showFlash(buildErrorMessage(error), "error");
        }
      });
    });
  } catch (error) {
    showFlash(buildErrorMessage(error), "error");
    renderShell("<section class='panel'><div class='empty'>Falha ao carregar o cadastro raiz de treinamentos.</div></section>", "Cadastro Raiz Treinamentos");
  }
}

function setTrainingRootTableInstruction(table, colspan, message) {
  const tbody = table?.querySelector("tbody");
  if (!tbody) return 0;
  tbody.innerHTML = renderTrainingRootInstructionRow(colspan, message);
  return 0;
}

function countTrainingRootTableRows(table) {
  return Array.from(table?.querySelectorAll('tbody tr td[data-label="Tipo"]') || [])
    .map((cell) => cell.parentElement)
    .filter(Boolean);
}

function syncTrainingRootSummaryCards(selectedTypeName, segmentCount, hourCount, aircraftCount) {
  const metrics = Array.from(document.querySelectorAll(".training-hero-metric"));
  if (metrics.length < 4) return;

  const segmentsMetric = metrics[1];
  const hoursMetric = metrics[2];
  const filterMetric = metrics[3];

  segmentsMetric.querySelector("strong").textContent = formatInteger(segmentCount);
  const segmentsCaption = segmentsMetric.querySelector(".training-hero-caption");
  if (segmentsCaption) {
    segmentsCaption.textContent = selectedTypeName || "Selecione um tipo";
  }

  hoursMetric.querySelector("strong").textContent = formatInteger(hourCount);
  const hoursCaption = hoursMetric.querySelector(".training-hero-caption");
  if (hoursCaption) {
    hoursCaption.textContent = selectedTypeName ? `${formatInteger(aircraftCount)} aeronaves` : "Selecione um tipo";
  }

  filterMetric.querySelector("strong").textContent = selectedTypeName || "Não";
  const filterCaption = filterMetric.querySelector(".training-hero-caption");
  if (filterCaption) {
    filterCaption.textContent = selectedTypeName ? "Escopo reduzido" : "Nenhum tipo selecionado";
  }
}

function groupTrainingRootSegmentRows(table) {
  const tbody = table?.querySelector("tbody");
  if (!tbody) return 0;

  const dataRows = Array.from(tbody.querySelectorAll("tr")).filter((row) => row.querySelector('td[data-label="Tipo"]'));
  if (!dataRows.length) return 0;

  const groupedRows = new Map(TRAINING_ROOT_SEGMENT_GROUP_ORDER.map((label) => [label, []]));
  dataRows.forEach((row) => {
    const modelLabel = row.querySelector('td[data-label="Modelo"]')?.textContent || "";
    const groupName = normalizeTrainingRootSegmentGroup(modelLabel);
    groupedRows.get(groupName).push(row);
  });

  const fragment = document.createDocumentFragment();
  TRAINING_ROOT_SEGMENT_GROUP_ORDER.forEach((groupName) => {
    const rows = groupedRows.get(groupName) || [];
    if (!rows.length) return;

    const headerRow = document.createElement("tr");
    const headerCell = document.createElement("td");
    const strong = document.createElement("strong");
    strong.textContent = groupName;
    headerCell.colSpan = 6;
    headerCell.appendChild(strong);
    headerRow.appendChild(headerCell);
    fragment.appendChild(headerRow);
    rows.forEach((row) => fragment.appendChild(row));
  });

  tbody.replaceChildren(fragment);
  return dataRows.length;
}

function syncTrainingRootFilterBehavior() {
  const filterForm = document.getElementById("training-root-filter-form");
  const filterSelect = document.getElementById("trainingRootTypeFilter");
  const filterButton = filterForm?.querySelector('button[type="submit"]');

  if (filterButton) {
    filterButton.disabled = true;
    filterButton.setAttribute("aria-disabled", "true");
  }

  filterForm?.addEventListener("submit", (event) => {
    event.preventDefault();
  });

  filterSelect?.addEventListener("change", () => {
    window.location.hash = buildTrainingRootFilterHref(filterSelect.value);
  });
}

function syncTrainingRootFormDefaults(selectedTypeId) {
  if (!trainingRootState.segmentEditId) {
    const segmentTypeSelect = document.querySelector('#training-root-segment-form select[name="tipo_treinamento_id"]');
    if (segmentTypeSelect) {
      segmentTypeSelect.value = selectedTypeId || "";
    }
  }

  if (!trainingRootState.hourEditId) {
    const hourTypeSelect = document.querySelector('#training-root-hour-form select[name="tipo_treinamento_id"]');
    if (hourTypeSelect) {
      hourTypeSelect.value = selectedTypeId || "";
    }
  }
}

function applyTrainingRootReactiveTables() {
  const tables = Array.from(document.querySelectorAll(".training-master-register .training-data-card table"));
  const segmentsTable = tables[1] || null;
  const hoursTable = tables[2] || null;
  const filterSelect = document.getElementById("trainingRootTypeFilter");
  const selectedTypeId = String(filterSelect?.value || "").trim();
  const selectedTypeName = selectedTypeId ? filterSelect?.selectedOptions?.[0]?.textContent?.trim() || "" : "";

  syncTrainingRootFormDefaults(selectedTypeId);

  let segmentCount = 0;
  let hourCount = 0;
  let aircraftCount = 0;

  if (!selectedTypeId) {
    setTrainingRootTableInstruction(segmentsTable, 6, "Selecione um tipo de treinamento para visualizar os segmentos.");
    setTrainingRootTableInstruction(hoursTable, 5, "Selecione um tipo de treinamento para visualizar as horas de voo.");
    syncTrainingRootSummaryCards("", 0, 0, 0);
    return;
  }

  const segmentRows = countTrainingRootTableRows(segmentsTable);
  if (!segmentRows.length) {
    setTrainingRootTableInstruction(segmentsTable, 6, "Nenhum segmento cadastrado para o tipo selecionado.");
  } else {
    segmentCount = groupTrainingRootSegmentRows(segmentsTable);
  }

  const hourRows = countTrainingRootTableRows(hoursTable);
  if (!hourRows.length) {
    setTrainingRootTableInstruction(hoursTable, 5, "Nenhuma referência de horas de voo cadastrada para o tipo selecionado.");
  } else {
    hourCount = hourRows.length;
    aircraftCount = new Set(
      hourRows
        .map((row) => row.querySelector('td[data-label="Aeronave"] .primary-cell')?.textContent?.trim() || "")
        .filter(Boolean),
    ).size;
  }

  syncTrainingRootSummaryCards(selectedTypeName, segmentCount, hourCount, aircraftCount);
}

export async function renderTrainingRootPageV2() {
  await renderTrainingRootPageV2Legacy();
  syncTrainingRootFilterBehavior();
  applyTrainingRootReactiveTables();
}
