import {
  api,
  booleanLabel,
  buildErrorMessage,
  buildHashHref,
  capabilitySet,
  escapeAttr,
  escapeHtml,
  fileToDataUrl,
  formatCompetenciaLabel,
  formatCurrencyBr,
  formatDateBr,
  formatDateTimeBr,
  hashQuery,
  showFlash,
  trainingStatusClass,
} from "./lib.js?v=20260408-161133";
import { renderShell } from "./shell.js?v=20260408-161133";

const TREINAMENTO_STATUS_OPTIONS = [
  { key: "vencido", label: "vencido" },
  { key: "a vencer", label: "a vencer" },
  { key: "regular", label: "regular" },
  { key: "sem informação", label: "sem informação" },
];

function buildServerHref(path, params = {}) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === "" || value === null || value === undefined) continue;
    query.set(key, String(value));
  }
  const queryString = query.toString();
  return queryString ? `${path}?${queryString}` : path;
}

function formatInteger(value) {
  const amount = Number(value || 0);
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 }).format(Number.isFinite(amount) ? amount : 0);
}

function wireResponsiveFilters(toggleId, panelId, expandedText, collapsedText) {
  const toggle = document.getElementById(toggleId);
  const panel = document.getElementById(panelId);
  if (!toggle || !panel) return;
  const mobileQuery = window.matchMedia("(max-width: 900px)");

  function syncCollapsedState() {
    if (!mobileQuery.matches) {
      panel.classList.remove("collapsed");
      toggle.setAttribute("aria-expanded", "true");
      toggle.textContent = expandedText;
      return;
    }

    const expanded = !panel.classList.contains("collapsed");
    toggle.setAttribute("aria-expanded", String(expanded));
    toggle.textContent = expanded ? expandedText : collapsedText;
  }

  toggle.addEventListener("click", () => {
    panel.classList.toggle("collapsed");
    syncCollapsedState();
  });

  syncCollapsedState();
  if (typeof mobileQuery.addEventListener === "function") {
    mobileQuery.addEventListener("change", syncCollapsedState);
  } else {
    window.addEventListener("resize", syncCollapsedState, { passive: true });
  }
}

function renderTrainingAttachmentSection(treinamentoId, attachments, capabilities) {
  if (!treinamentoId) {
    return `
      <section class="panel" style="margin-top: 1rem;">
        <div class="hint">Salve o treinamento primeiro para habilitar anexos PDF.</div>
      </section>
    `;
  }

  const canUpload = capabilities.has("treinamentos_anexos:create");
  const canDelete = capabilities.has("treinamentos_anexos:delete");

  return `
    <section class="panel" style="margin-top: 1rem;">
      <div class="page-header" style="margin-bottom: 12px;">
        <div>
          <h2 style="margin: 0;">Anexos em PDF do treinamento</h2>
          <p class="page-subtitle" style="margin-top: 4px;">Documentos comprobatórios vinculados ao treinamento.</p>
        </div>
      </div>

      ${
        canUpload
          ? `
            <form id="treinamento-attachment-form" class="filters filters-wide" style="margin-bottom: 12px;">
              <input type="file" name="arquivo_pdf" id="arquivo_pdf" accept="application/pdf" required>
              <button type="submit">Anexar PDF</button>
            </form>
            <div class="hint">Limite por arquivo: 20 MB. Apenas arquivos PDF válidos são aceitos.</div>
          `
          : ""
      }

      <div class="table-wrap" style="margin-top: 12px;">
        <table class="data-table responsive-cards">
          <thead>
            <tr>
              <th>Arquivo</th>
              <th>Tamanho</th>
              <th>Enviado em</th>
              <th>Enviado por</th>
              <th>Ações</th>
            </tr>
          </thead>
          <tbody>
            ${
              attachments.length
                ? attachments
                    .map(
                      (item) => `
                        <tr>
                          <td data-label="Arquivo">
                            <div class="primary-cell">${escapeHtml(item.nome_original)}</div>
                            <div class="secondary-cell">${escapeHtml(item.mime_type || "application/pdf")}</div>
                          </td>
                          <td data-label="Tamanho">${(Number(item.tamanho_bytes || 0) / (1024 * 1024)).toFixed(2)} MB</td>
                          <td data-label="Enviado em">${escapeHtml(formatDateTimeBr(item.enviado_em))}</td>
                          <td data-label="Enviado por">${escapeHtml(item.enviado_por_nome || "-")}</td>
                          <td class="actions" data-label="Ações">
                            <a href="${item.links.self}" target="_blank" rel="noopener noreferrer">Visualizar</a>
                            <a href="${item.links.download}" target="_blank" rel="noopener noreferrer">Baixar</a>
                            ${
                              canDelete
                                ? `<button type="button" class="link-danger treinamento-attachment-delete" data-attachment-id="${item.id}">Excluir</button>`
                                : ""
                            }
                          </td>
                        </tr>
                      `,
                    )
                    .join("")
                : '<tr><td colspan="5" class="empty">Nenhum PDF anexado a este treinamento.</td></tr>'
            }
          </tbody>
        </table>
      </div>
    </section>
  `;
}

const trainingRootState = {
  typeEditId: null,
  segmentEditId: null,
  hourEditId: null,
};

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
  if (date.getUTCDate() !== day) {
    date.setUTCDate(0);
  }
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

function renderTrainingRootInstructionRow(colspan, message) {
  return `<tr><td colspan="${colspan}" class="empty">${escapeHtml(message)}</td></tr>`;
}

function renderTrainingRootModelBadge(value) {
  const label = normalizeTrainingRootSegmentGroup(value);
  return `<span class="training-root-model-badge training-root-model-badge--${trainingModelTheme(label)}">${escapeHtml(label)}</span>`;
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

function renderTrainingRootSegmentsRows(items, selectedType, capabilities) {
  if (!selectedType) {
    return renderTrainingRootInstructionRow(8, "Selecione um tipo de treinamento para visualizar os segmentos.");
  }

  if (!items.length) {
    return renderTrainingRootInstructionRow(8, "Nenhum segmento cadastrado para o tipo selecionado.");
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
    return renderTrainingRootInstructionRow(7, "Selecione um tipo de treinamento para visualizar as horas de voo.");
  }

  if (!items.length) {
    return renderTrainingRootInstructionRow(7, "Nenhuma referência de horas de voo cadastrada para o tipo selecionado.");
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
          <td class="actions" data-label="Ações">
            ${capabilities.has("tipos_treinamento:edit") ? `<button type="button" class="button-link secondary training-root-hour-edit" data-hour-id="${item.id}">Editar</button>` : ""}
            ${capabilities.has("tipos_treinamento:delete") ? `<button type="button" class="link-danger training-root-hour-delete" data-hour-id="${item.id}">Excluir</button>` : ""}
          </td>
        </tr>
      `,
    )
    .join("");
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

function wireExplicitSubmit(formId, buttonId, handler) {
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

function setSubmitButtonBusy(button, busy, idleLabel, busyLabel) {
  if (!button) return;
  button.disabled = busy;
  button.textContent = busy ? busyLabel : idleLabel;
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

async function loadOptionalItem(path, itemKey = "item") {
  try {
    const { data } = await api(path);
    return data[itemKey] || null;
  } catch (_error) {
    return null;
  }
}

function renderHoursReference(template) {
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
      ${hours.observacao ? `<div class="hint" style="margin-top: 12px;">${escapeHtml(hours.observacao)}</div>` : ""}
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
            <th>Realização</th>
            <th>Vencimento</th>
            <th>Status</th>
            <th>Ações</th>
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
                        <td data-label="Realização">${escapeHtml(formatDateBr(item.data_realizacao))}</td>
                        <td data-label="Vencimento">${escapeHtml(item.periodicidade_meses ? formatDateBr(item.data_vencimento) : "Sem validade")}</td>
                        <td data-label="Status"><span class="status-pill ${trainingStatusClass(item.status_calculado)}">${escapeHtml(item.status_calculado || "-")}</span></td>
                        <td class="actions" data-label="Ações">
                          ${capabilities.has("treinamentos:edit") ? `<a href="#/treinamentos/${item.id}">Editar</a>` : ""}
                          ${
                            capabilities.has("treinamentos:delete")
                              ? `<button type="button" class="link-danger training-program-record-delete" data-record-id="${item.id}">Excluir</button>`
                              : ""
                          }
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

export async function renderTreinamentosListPage() {
  try {
    const filters = Object.fromEntries(hashQuery().entries());
    const capabilities = capabilitySet();
    const [optionsResponse, recordsResponse] = await Promise.all([
      api("/api/v1/treinamentos-tripulantes/options"),
      api(`/api/v1/treinamentos-tripulantes?${new URLSearchParams(filters).toString()}`),
    ]);
    const optionsPayload = optionsResponse.data?.options || {};
    const options = {
      tripulantes: Array.isArray(optionsPayload.tripulantes) ? optionsPayload.tripulantes : [],
      tipos_treinamento: Array.isArray(optionsPayload.tipos_treinamento) ? optionsPayload.tipos_treinamento : [],
      modelos_aeronave: Array.isArray(optionsPayload.modelos_aeronave) ? optionsPayload.modelos_aeronave : [],
    };
    const records = Array.isArray(recordsResponse.data?.items) ? recordsResponse.data.items : [];
    const selectedType = selectedTypeFromOptions(options.tipos_treinamento || [], filters.tipo_treinamento_id);

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
        <div class="page-header">
          <div>
            <h1>Cadastro de treinamento para tripulante</h1>
            <p class="page-subtitle">ABA 2. Selecione tripulante, tipo e aeronave para carregar os segmentos da fonte mestre em tempo real.</p>
          </div>
          <div class="page-header-actions">
            ${capabilities.has("tipos_treinamento:view") ? '<a class="button-link secondary" href="#/treinamentos/raiz">Abrir cadastro raiz</a>' : ""}
          </div>
        </div>

        <section class="panel">
          <div class="page-header compact-page-header">
            <div>
              <h2>Etapa 1 - Seleção inicial</h2>
              <p class="page-subtitle">Tripulante + tipo de treinamento + modelo de aeronave.</p>
            </div>
          </div>
          <form id="training-program-selection-form" class="filters filters-wide">
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
            <button type="submit">Carregar segmentos</button>
            <a class="button-link secondary" href="#/treinamentos">Limpar</a>
          </form>
          <div class="hint" id="trainingProgramSelectionHint">
            ${
              selectedType
                ? selectedType.exige_aeronave
                  ? "Este tipo exige seleção do modelo de aeronave para carregar as horas de voo."
                  : "Este tipo não exige aeronave obrigatória. Os segmentos podem ser carregados sem selecionar modelo."
                : "Selecione o tipo de treinamento para habilitar as etapas seguintes."
            }
          </div>
        </section>

        ${templateError ? `<section class="panel"><div class="flash error">${escapeHtml(templateError)}</div></section>` : ""}
        ${template ? renderHoursReference(template) : ""}

        ${
          template
            ? `
              <section class="panel">
                <div class="page-header compact-page-header">
                  <div>
                    <h2>Etapas 2, 3 e 4</h2>
                    <p class="page-subtitle">Selecione os segmentos, avance para o preenchimento e salve um registro por segmento.</p>
                  </div>
                </div>
                <form id="training-program-batch-form" class="training-program-batch-form">
                  <input type="hidden" name="tripulante_id" value="${escapeAttr(filters.tripulante_id || "")}">
                  <input type="hidden" name="tipo_treinamento_id" value="${escapeAttr(filters.tipo_treinamento_id || "")}">
                  <input type="hidden" name="aeronave_modelo" value="${escapeAttr(filters.aeronave_modelo || "")}">
                  <section class="training-workbench-pane">
                    <div class="training-pane-head">
                      <div>
                        <h3>Etapa 2 - Selecione os segmentos</h3>
                        <p>Marque apenas os segmentos que o tripulante realizou ou precisa renovar agora.</p>
                      </div>
                      <span class="training-pane-counter">${formatInteger((template.segmentos || []).length)} disponíveis</span>
                    </div>
                    ${renderTrainingProgramSelectorGroups(template)}
                    <div class="training-selector-actions">
                      <button type="button" id="trainingProgramContinueButton" disabled>Selecione ao menos 1 segmento</button>
                      <button type="button" class="button-link secondary" id="trainingProgramResetButton">Limpar seleção</button>
                    </div>
                    <div class="training-selector-feedback" id="trainingProgramSelectionFeedback">Marque um ou mais segmentos para liberar a etapa de preenchimento.</div>
                  </section>

                  <section class="training-workbench-pane training-workbench-pane--details">
                    <div class="training-selected-empty" id="trainingStep3Placeholder">
                      Selecione os segmentos e clique em "Continuar para preenchimento de datas" para liberar a Etapa 3.
                    </div>
                    <div class="frontend-hidden" id="trainingStep3Container">
                      <div class="training-pane-head">
                        <div>
                          <h3>Etapa 3 - Preenchimento de datas e documentos</h3>
                          <p>Apenas os segmentos marcados aparecem abaixo. Preencha realização, vencimento, observação e PDF por segmento.</p>
                        </div>
                        <span class="training-pane-counter"><span id="trainingSelectedCount">0</span> selecionados</span>
                      </div>
                      ${template.ctac_required ? '<div class="training-inline-alert">Referência "Conforme CTAC" detectada. Informe as horas reais para cada segmento marcado.</div>' : ""}
                      <div class="training-selected-empty" id="trainingSelectedEmpty">
                        Marque um ou mais segmentos no catálogo para liberar o preenchimento detalhado.
                      </div>
                      <div class="training-selected-stack">
                        ${renderTrainingProgramSelectedCards(template)}
                      </div>
                      <div class="form-actions training-submit-bar">
                        ${
                          capabilities.has("treinamentos:create")
                            ? '<button type="submit">Salvar segmentos marcados</button>'
                            : '<div class="hint">Seu perfil possui apenas visualização para este módulo.</div>'
                        }
                      </div>
                    </div>
                  </section>
                </form>
              </section>
            `
            : `
              <section class="panel">
                <div class="empty">
                  ${
                    selectedType
                      ? selectedType.exige_aeronave && !filters.aeronave_modelo
                        ? "Selecione o modelo de aeronave para carregar os segmentos e a referência de horas."
                        : "Selecione um tripulante e um tipo de treinamento para iniciar o cadastro."
                      : "Selecione um tipo de treinamento para carregar o programa."
                  }
                </div>
              </section>
            `
        }

        <section class="panel">
          <div class="page-header compact-page-header">
            <div>
              <h2>Registros salvos</h2>
              <p class="page-subtitle">Consulta em tempo real dos registros criados para os segmentos selecionados.</p>
            </div>
          </div>
          <section class="summary-grid compact-summary-grid">
            <div class="summary-card"><strong>Total</strong><span>${formatInteger(records.length)}</span></div>
            <div class="summary-card"><strong>Com vencimento</strong><span>${formatInteger(records.filter((item) => item.periodicidade_meses > 0).length)}</span></div>
            <div class="summary-card"><strong>Sem validade</strong><span>${formatInteger(records.filter((item) => !item.periodicidade_meses).length)}</span></div>
            <div class="summary-card"><strong>Com anexo</strong><span>${formatInteger(records.filter((item) => Number(item.total_anexos || 0) > 0).length)}</span></div>
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
          showFlash("Registro exclu?do com sucesso.", "success");
          await renderTreinamentosListPage();
        } catch (error) {
          showFlash(buildErrorMessage(error), "error");
        }
      });
    });

    if (!template) return;

    const batchForm = document.getElementById("training-program-batch-form");
    const segmentCheckboxes = Array.from(document.querySelectorAll(".training-segment-checkbox"));
    const continueButton = document.getElementById("trainingProgramContinueButton");
    const selectionFeedback = document.getElementById("trainingProgramSelectionFeedback");
    let detailsUnlocked = false;

    function updateContinueButton(selectedCount) {
      if (!continueButton) return;
      continueButton.disabled = selectedCount <= 0;
      if (selectedCount <= 0) {
        continueButton.textContent = "Selecione ao menos 1 segmento";
        return;
      }
      continueButton.textContent = selectedCount === 1 ? "Continuar com 1 segmento" : `Continuar com ${selectedCount} segmentos`;
    }

    function setSelectionFeedback(message, kind = "neutral") {
      if (!selectionFeedback) return;
      selectionFeedback.textContent = message;
      selectionFeedback.dataset.kind = kind;
    }

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
      updateContinueButton(selectedCount);
      if (!selectedCount) {
        setSelectionFeedback("Marque um ou mais segmentos para liberar a etapa de preenchimento.");
        return;
      }
      if (!detailsUnlocked) {
        setSelectionFeedback(
          selectedCount === 1
            ? "1 segmento selecionado. Clique em continuar para preencher datas e documentos."
            : `${selectedCount} segmentos selecionados. Clique em continuar para preencher datas e documentos.`,
          "info",
        );
        return;
      }
      setSelectionFeedback(
        selectedCount === 1
          ? "Etapa 3 liberada para 1 segmento."
          : `Etapa 3 liberada para ${selectedCount} segmentos.`,
        "success",
      );
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
        hint.textContent = "Selecione o tipo de treinamento para habilitar as etapas seguintes.";
        return;
      }
      if (requiresAircraft && !aircraftSelect.value) {
        hint.textContent = "Este tipo exige seleção do modelo de aeronave para carregar as horas de voo.";
        return;
      }
      hint.textContent = requiresAircraft
        ? "Programa carregado com referência de horas por aeronave."
        : "Programa carregado sem obrigatoriedade de aeronave.";
    }

    document.getElementById("trainingProgramType")?.addEventListener("change", syncSelectionHint);
    document.getElementById("trainingProgramAircraft")?.addEventListener("change", syncSelectionHint);
    syncSelectionHint();

    document.getElementById("trainingProgramContinueButton")?.addEventListener("click", () => {
      const selectedCount = segmentCheckboxes.filter((checkbox) => checkbox.checked).length;
      if (!selectedCount) {
        setSelectionFeedback("Nenhum segmento selecionado. Marque pelo menos um segmento antes de continuar.", "error");
        segmentCheckboxes[0]?.focus();
        return;
      }
      detailsUnlocked = true;
      segmentCheckboxes.forEach((checkbox) => syncSegmentCard(checkbox.dataset.segmentId));
      syncSelectedState();
      setSelectionFeedback(
        selectedCount === 1
          ? "Etapa 3 liberada para 1 segmento. Preencha a data, o PDF e a observação."
          : `Etapa 3 liberada para ${selectedCount} segmentos. Preencha datas, PDFs e observações.`,
        "success",
      );
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
      showFlash("Seleção de segmentos limpa.", "success");
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
        await renderTreinamentosListPage();
      } catch (error) {
        showFlash(buildErrorMessage(error), "error");
      }
    });
  } catch (error) {
    showFlash(buildErrorMessage(error), "error");
    renderShell("<section class='panel'><div class='empty'>Falha ao carregar a aba de treinamentos por tripulante.</div></section>", "Treinamentos por Tripulante");
  }
}

export async function renderTrainingRootPage() {
  try {
    const filters = Object.fromEntries(hashQuery().entries());
    const tipoFilter = String(filters.tipo_treinamento_id || "");
    const hasActiveTypeFilter = Boolean(tipoFilter.trim());
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
    const editingType = trainingRootState.typeEditId ? await loadOptionalItem(`/api/v1/treinamento-raiz/tipos/${trainingRootState.typeEditId}`) : null;
    const editingSegment = trainingRootState.segmentEditId ? await loadOptionalItem(`/api/v1/treinamento-raiz/segmentos/${trainingRootState.segmentEditId}`) : null;
    const editingHour = trainingRootState.hourEditId ? await loadOptionalItem(`/api/v1/treinamento-raiz/horas-voo/${trainingRootState.hourEditId}`) : null;

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

      renderShell(
        `
          <div class="page-header">
            <div>
              <h1>Cadastro raiz de treinamentos</h1>
            </div>
            <div class="page-header-actions">
              <a class="button-link secondary" href="#/treinamentos">Abrir cadastro por tripulante</a>
            </div>
          </div>

        <section class="panel">
          <form id="training-root-filter-form" class="filters filters-wide">
            <select name="tipo_treinamento_id" id="trainingRootTypeFilter">
              <option value="">Filtrar segmentos e horas por tipo</option>
              ${(options.tipos_treinamento || [])
                .map((item) => `<option value="${item.id}" ${String(tipoFilter) === String(item.id) ? "selected" : ""}>${escapeHtml(item.nome)}</option>`)
                .join("")}
            </select>
            <a class="button-link secondary" href="#/treinamentos/raiz">Limpar</a>
          </form>
          <section class="summary-grid compact-summary-grid">
            <div class="summary-card"><strong>Tipos</strong><span>${formatInteger(types.length)}</span></div>
            <div class="summary-card"><strong>Segmentos</strong><span>${formatInteger(selectedType ? segments.length : 0)}</span></div>
            <div class="summary-card"><strong>Horas voo</strong><span>${formatInteger(selectedType ? hours.length : 0)}</span></div>
            <div class="summary-card"><strong>Filtro ativo</strong><span>${escapeHtml(selectedType ? `Sim — ${selectedType.nome}` : "Não")}</span></div>
          </section>
        </section>

        <section class="panel">
          <div class="page-header compact-page-header"><div><h2>Tipos de treinamento</h2></div></div>
          ${
            capabilities.has("tipos_treinamento:create") || capabilities.has("tipos_treinamento:edit")
              ? `
                <form id="training-root-type-form" class="form-grid">
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
                  <label class="full-width">Descrição<textarea name="descricao" rows="3">${escapeHtml(typeDefaults.descricao || "")}</textarea></label>
                  <div class="form-actions full-width">
                    <button type="submit" id="training-root-type-submit">${editingType ? "Salvar tipo" : "Criar tipo"}</button>
                    ${editingType ? '<button type="button" class="button-link secondary" id="training-root-type-cancel">Cancelar</button>' : ""}
                  </div>
                </form>
              `
              : '<div class="hint">Seu perfil não possui permissão para alterar o cadastro raiz.</div>'
          }
          <div class="table-wrap">
            <table class="data-table responsive-cards">
              <thead><tr><th>Nome</th><th>Código</th><th>Status</th><th>Exige</th><th>Segmentos</th><th>Horas</th><th>Ações</th></tr></thead>
              <tbody>
                ${
                  types.length
                    ? types
                        .map(
                          (item) => `
                            <tr>
                              <td data-label="Nome">${escapeHtml(item.nome)}</td>
                              <td data-label="Código">${escapeHtml(item.codigo || "-")}</td>
                              <td data-label="Status">${escapeHtml(item.status)}</td>
                              <td data-label="Exige">${escapeHtml(booleanLabel(item.exige_aeronave))}</td>
                              <td data-label="Segmentos">${formatInteger(item.total_segmentos)}</td>
                              <td data-label="Horas">${formatInteger(item.total_horas_voo)}</td>
                              <td class="actions" data-label="Ações">
                                ${capabilities.has("tipos_treinamento:edit") ? `<button type="button" class="button-link secondary training-root-type-edit" data-type-id="${item.id}">Editar</button>` : ""}
                                ${capabilities.has("tipos_treinamento:delete") ? `<button type="button" class="link-danger training-root-type-delete" data-type-id="${item.id}">Excluir</button>` : ""}
                              </td>
                            </tr>
                          `,
                        )
                        .join("")
                    : '<tr><td colspan="7" class="empty">Nenhum tipo cadastrado.</td></tr>'
                }
              </tbody>
            </table>
          </div>
        </section>

        <section class="panel">
          <div class="page-header compact-page-header"><div><h2>Segmentos teoricos</h2></div></div>
          ${
            capabilities.has("tipos_treinamento:create") || capabilities.has("tipos_treinamento:edit")
              ? `
                <form id="training-root-segment-form" class="form-grid">
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
                  <label>Carga horaria<input type="number" step="0.1" min="0" name="carga_horaria" value="${escapeAttr(segmentDefaults.carga_horaria || "")}"></label>
                  <label>Carga teorica<input type="number" step="0.1" min="0" name="carga_teorica" value="${escapeAttr(segmentDefaults.carga_teorica || "")}"></label>
                  <label>Carga pratica<input type="number" step="0.1" min="0" name="carga_pratica" value="${escapeAttr(segmentDefaults.carga_pratica || "")}"></label>
                  <label>
                    Periodicidade
                    <select name="periodicidade_meses">
                      ${(options.periodicidades || []).map((item) => `<option value="${item.value}" ${String(segmentDefaults.periodicidade_meses || 0) === String(item.value) ? "selected" : ""}>${escapeHtml(item.label)}</option>`).join("")}
                    </select>
                  </label>
                  <label class="full-width">Observação<textarea name="observacao" rows="2">${escapeHtml(segmentDefaults.observacao || "")}</textarea></label>
                  <div class="form-actions full-width">
                    <button type="submit" id="training-root-segment-submit">${editingSegment ? "Salvar segmento" : "Criar segmento"}</button>
                    ${editingSegment ? '<button type="button" class="button-link secondary" id="training-root-segment-cancel">Cancelar</button>' : ""}
                  </div>
                </form>
              `
              : ""
          }
          <div class="table-wrap">
            <table class="data-table responsive-cards">
              <thead><tr><th>Modelo</th><th>Segmento</th><th>Carga (h)</th><th>Teórica</th><th>Prática</th><th>Period.</th><th>Observação</th><th>Ações</th></tr></thead>
              <tbody>
                ${renderTrainingRootSegmentsRows(segments, selectedType, capabilities)}
              </tbody>
            </table>
          </div>
        </section>

        <section class="panel">
          <div class="page-header compact-page-header"><div><h2>Horas de voo por aeronave</h2></div></div>
          ${
            capabilities.has("tipos_treinamento:create") || capabilities.has("tipos_treinamento:edit")
              ? `
                <form id="training-root-hour-form" class="form-grid">
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
                  <label>Solo horas<input type="number" step="0.1" min="0" name="solo_horas" value="${escapeAttr(hourDefaults.solo_horas || "")}"></label>
                  <label>Voo PIC/SIC horas<input type="number" step="0.1" min="0" name="voo_pic_sic_horas" value="${escapeAttr(hourDefaults.voo_pic_sic_horas || "")}"></label>
                  <label>Voo CREW horas<input type="number" step="0.1" min="0" name="voo_crew_horas" value="${escapeAttr(hourDefaults.voo_crew_horas || "")}"></label>
                  <label class="full-width">Observação<textarea name="observacao" rows="2">${escapeHtml(hourDefaults.observacao || "")}</textarea></label>
                  <div class="form-actions full-width">
                    <button type="submit" id="training-root-hour-submit">${editingHour ? "Salvar horas" : "Criar horas"}</button>
                    ${editingHour ? '<button type="button" class="button-link secondary" id="training-root-hour-cancel">Cancelar</button>' : ""}
                  </div>
                </form>
              `
              : ""
          }
          <div class="table-wrap">
            <table class="data-table responsive-cards">
              <thead><tr><th>Tipo</th><th>Aeronave</th><th>Solo</th><th>PIC/SIC</th><th>CREW</th><th>Observação</th><th>Ações</th></tr></thead>
              <tbody>
                ${renderTrainingRootHoursRows(hours, selectedType, capabilities)}
              </tbody>
            </table>
          </div>
        </section>
      `,
      "Cadastro Raiz Treinamentos",
    );

    const trainingRootFilterForm = document.getElementById("training-root-filter-form");
    const trainingRootFilterSelect = document.getElementById("trainingRootTypeFilter");
    const trainingRootSegmentTypeSelect = document.querySelector('#training-root-segment-form select[name="tipo_treinamento_id"]');
    const trainingRootHourTypeSelect = document.querySelector('#training-root-hour-form select[name="tipo_treinamento_id"]');

    trainingRootFilterForm?.addEventListener("submit", (event) => {
      event.preventDefault();
    });

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

    syncTrainingRootTypeSelectors();

    trainingRootFilterSelect?.addEventListener("change", () => {
      syncTrainingRootTypeSelectors();
      window.location.hash = buildTrainingRootFilterHref(trainingRootFilterSelect.value);
    });

    document.getElementById("training-root-type-cancel")?.addEventListener("click", async () => {
      trainingRootState.typeEditId = null;
      await renderTrainingRootPage();
    });
    document.getElementById("training-root-segment-cancel")?.addEventListener("click", async () => {
      trainingRootState.segmentEditId = null;
      await renderTrainingRootPage();
    });
    document.getElementById("training-root-hour-cancel")?.addEventListener("click", async () => {
      trainingRootState.hourEditId = null;
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
        trainingRootState.typeEditId = null;
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
        trainingRootState.segmentEditId = null;
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
        trainingRootState.hourEditId = null;
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
        await renderTrainingRootPage();
      });
    });
    document.querySelectorAll(".training-root-segment-edit").forEach((button) => {
      button.addEventListener("click", async () => {
        trainingRootState.segmentEditId = Number(button.dataset.segmentId);
        await renderTrainingRootPage();
      });
    });
    document.querySelectorAll(".training-root-hour-edit").forEach((button) => {
      button.addEventListener("click", async () => {
        trainingRootState.hourEditId = Number(button.dataset.hourId);
        await renderTrainingRootPage();
      });
    });

    document.querySelectorAll(".training-root-type-delete").forEach((button) => {
      button.addEventListener("click", async () => {
        if (!window.confirm("Excluir este tipo de treinamento?")) return;
        try {
          await api(`/api/v1/treinamento-raiz/tipos/${button.dataset.typeId}`, { method: "DELETE" });
          showFlash("Tipo removido com sucesso.", "success");
          await renderTrainingRootPage();
        } catch (error) {
          showFlash(buildErrorMessage(error), "error");
        }
      });
    });
    document.querySelectorAll(".training-root-segment-delete").forEach((button) => {
      button.addEventListener("click", async () => {
        if (!window.confirm("Excluir este segmento teorico?")) return;
        try {
          await api(`/api/v1/treinamento-raiz/segmentos/${button.dataset.segmentId}`, { method: "DELETE" });
          showFlash("Segmento removido com sucesso.", "success");
          await renderTrainingRootPage();
        } catch (error) {
          showFlash(buildErrorMessage(error), "error");
        }
      });
    });
    document.querySelectorAll(".training-root-hour-delete").forEach((button) => {
      button.addEventListener("click", async () => {
        if (!window.confirm("Excluir esta referencia de horas de voo?")) return;
        try {
          await api(`/api/v1/treinamento-raiz/horas-voo/${button.dataset.hourId}`, { method: "DELETE" });
          showFlash("Referencia removida com sucesso.", "success");
          await renderTrainingRootPage();
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

async function renderTrainingProgramRecordPage(treinamentoId = null) {
  if (!treinamentoId) {
    window.location.hash = "#/treinamentos";
    return;
  }
  try {
    const capabilities = capabilitySet();
    const [detailResponse, optionsResponse] = await Promise.all([
      api(`/api/v1/treinamentos-tripulantes/${treinamentoId}`),
      api("/api/v1/treinamentos-tripulantes/options"),
    ]);
    const record = detailResponse.data?.item;
    const optionsPayload = optionsResponse.data?.options || {};
    const options = {
      tripulantes: Array.isArray(optionsPayload.tripulantes) ? optionsPayload.tripulantes : [],
      tipos_treinamento: Array.isArray(optionsPayload.tipos_treinamento) ? optionsPayload.tipos_treinamento : [],
      modelos_aeronave: Array.isArray(optionsPayload.modelos_aeronave) ? optionsPayload.modelos_aeronave : [],
    };
    if (!record) {
      throw new Error("Registro de treinamento não encontrado.");
    }
    const templateResponse = await api(
      `/api/v1/treinamentos-tripulantes/template?${new URLSearchParams({
        tipo_treinamento_id: String(record.tipo_treinamento_id),
        aeronave_modelo: String(record.aeronave_modelo || ""),
      }).toString()}`,
    );
    const template = templateResponse.data.template;
    const duePreview = buildDuePreview(record.data_realizacao, record.periodicidade_meses);

    renderShell(
      `
        <div class="page-header">
          <div>
            <h1>Editar treinamento por segmento</h1>
            <p class="page-subtitle">ABA 2. Registro individual criado a partir da selecao de segmentos.</p>
          </div>
          <div class="page-header-actions">
            <a class="button-link secondary" href="#/treinamentos">Voltar para a lista</a>
          </div>
        </div>

        <section class="panel">
          <form id="training-program-record-form" class="form-grid">
            <label>
              Tripulante
              <select name="tripulante_id" required>
                <option value="">Selecione</option>
                ${(options.tripulantes || []).map((item) => `<option value="${item.id}" ${String(record.tripulante_id) === String(item.id) ? "selected" : ""}>${escapeHtml(item.label || item.nome)}</option>`).join("")}
              </select>
            </label>
            <label>
              Tipo de treinamento
              <select name="tipo_treinamento_id" id="trainingRecordType" required>
                ${(options.tipos_treinamento || [])
                  .map(
                    (item) => `
                      <option value="${item.id}" data-exige-aeronave="${item.exige_aeronave ? 1 : 0}" ${String(record.tipo_treinamento_id) === String(item.id) ? "selected" : ""}>${escapeHtml(item.nome)}</option>
                    `,
                  )
                  .join("")}
              </select>
            </label>
            <label>
              Modelo de aeronave
              <select name="aeronave_modelo" id="trainingRecordAircraft">
                <option value="">Modelo de aeronave</option>
                ${(options.modelos_aeronave || []).map((item) => `<option value="${escapeAttr(item.aeronave_modelo)}" ${String(record.aeronave_modelo || "") === String(item.aeronave_modelo) ? "selected" : ""}>${escapeHtml(item.aeronave_modelo)}</option>`).join("")}
              </select>
            </label>
            <label>
              Segmento
              <select name="segmento_id" id="trainingRecordSegment" required>
                ${(template.segmentos || []).map((item) => `<option value="${item.id}" data-periodicity="${item.periodicidade_meses}" ${String(record.segmento_teorico_id) === String(item.id) ? "selected" : ""}>${escapeHtml(item.nome_segmento)} · ${escapeHtml(item.modelo_segmento)}</option>`).join("")}
              </select>
            </label>
            <label>Data de realização<input type="date" name="data_realizacao" id="trainingRecordDate" value="${escapeAttr(record.data_realizacao || "")}" required></label>
            <label>Data de vencimento<input type="text" id="trainingRecordDuePreview" value="${escapeAttr(duePreview.label)}" readonly></label>
            <label class="full-width">Observação<textarea name="observacao" rows="3">${escapeHtml(record.observacao || "")}</textarea></label>
            ${
              record.ctac_required
                ? `
                  <label>Solo horas (CTAC)<input type="number" step="0.1" min="0" name="ctac_solo_horas" value="${escapeAttr(record.ctac_solo_horas ?? "")}"></label>
                  <label>Voo PIC/SIC horas (CTAC)<input type="number" step="0.1" min="0" name="ctac_voo_pic_sic_horas" value="${escapeAttr(record.ctac_voo_pic_sic_horas ?? "")}"></label>
                  <label>Voo CREW horas (CTAC)<input type="number" step="0.1" min="0" name="ctac_voo_crew_horas" value="${escapeAttr(record.ctac_voo_crew_horas ?? "")}"></label>
                `
                : ""
            }
            <div class="form-actions full-width">
              ${capabilities.has("treinamentos:edit") ? '<button type="submit">Salvar alterações</button>' : ""}
              ${capabilities.has("treinamentos:delete") ? '<button type="button" class="button-link secondary" id="training-program-record-delete">Excluir registro</button>' : ""}
            </div>
          </form>
        </section>

        ${renderHoursReference(template)}
        ${renderTrainingAttachmentSection(treinamentoId, record.attachments || [], capabilities)}
      `,
      "Editar Treinamento por Segmento",
    );

    function syncRecordHints() {
      const typeSelect = document.getElementById("trainingRecordType");
      const aircraftSelect = document.getElementById("trainingRecordAircraft");
      const segmentSelect = document.getElementById("trainingRecordSegment");
      const dateInput = document.getElementById("trainingRecordDate");
      const dueInput = document.getElementById("trainingRecordDuePreview");
      if (!typeSelect || !aircraftSelect || !segmentSelect || !dateInput || !dueInput) return;
      const typeOption = typeSelect.options[typeSelect.selectedIndex];
      aircraftSelect.required = typeOption?.dataset?.exigeAeronave === "1";
      const segmentOption = segmentSelect.options[segmentSelect.selectedIndex];
      dueInput.value = buildDuePreview(dateInput.value, segmentOption?.dataset?.periodicity || 0).label;
    }

    document.getElementById("trainingRecordType")?.addEventListener("change", syncRecordHints);
    document.getElementById("trainingRecordAircraft")?.addEventListener("change", syncRecordHints);
    document.getElementById("trainingRecordSegment")?.addEventListener("change", syncRecordHints);
    document.getElementById("trainingRecordDate")?.addEventListener("change", syncRecordHints);
    syncRecordHints();

    document.getElementById("training-program-record-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await api(`/api/v1/treinamentos-tripulantes/${treinamentoId}`, {
          method: "PUT",
          json: Object.fromEntries(new FormData(event.currentTarget).entries()),
        });
        showFlash("Registro atualizado com sucesso.", "success");
        await renderTrainingProgramRecordPage(treinamentoId);
      } catch (error) {
        showFlash(buildErrorMessage(error), "error");
      }
    });

    document.getElementById("training-program-record-delete")?.addEventListener("click", async () => {
      if (!window.confirm("Excluir este registro de treinamento?")) return;
      try {
        await api(`/api/v1/treinamentos-tripulantes/${treinamentoId}`, { method: "DELETE" });
        showFlash("Registro removido com sucesso.", "success");
        window.location.hash = "#/treinamentos";
      } catch (error) {
        showFlash(buildErrorMessage(error), "error");
      }
    });

    document.getElementById("treinamento-attachment-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await api(`/api/v1/treinamentos/${treinamentoId}/attachments`, {
          method: "POST",
          body: new FormData(event.currentTarget),
        });
        showFlash("Anexo enviado com sucesso.", "success");
      } catch (error) {
        showFlash(buildErrorMessage(error), "error");
      }
      await renderTrainingProgramRecordPage(treinamentoId);
    });

    document.querySelectorAll(".treinamento-attachment-delete").forEach((button) => {
      button.addEventListener("click", async () => {
        if (!window.confirm("Excluir este anexo PDF?")) return;
        try {
          await api(`/api/v1/treinamentos/${treinamentoId}/attachments/${button.dataset.attachmentId}`, { method: "DELETE" });
          showFlash("Anexo removido com sucesso.", "success");
        } catch (error) {
          showFlash(buildErrorMessage(error), "error");
        }
        await renderTrainingProgramRecordPage(treinamentoId);
      });
    });
  } catch (error) {
    showFlash(buildErrorMessage(error), "error");
    renderShell("<section class='panel'><div class='empty'>Falha ao carregar o registro de treinamento.</div></section>", "Editar Treinamento por Segmento");
  }
}

export async function renderTreinamentoFormPage(treinamentoId = null) {
  return renderTrainingProgramRecordPage(treinamentoId);
}

async function legacyRenderTreinamentoFormPage(treinamentoId = null) {
  try {
    const detailPromise = treinamentoId ? api(`/api/v1/treinamentos/${treinamentoId}`) : Promise.resolve({ data: { treinamento: null } });
    const detailPayload = await detailPromise;
    const treinamento = detailPayload.data.treinamento;
    const optionsResponse = await api(
      `/api/v1/treinamentos/options${treinamentoId ? `?treinamento_id=${treinamentoId}${treinamento?.equipamento_id ? `&equipamento_id=${treinamento.equipamento_id}` : ""}${treinamento?.tipo_treinamento_id ? `&tipo_treinamento_id=${treinamento.tipo_treinamento_id}` : ""}` : ""}`,
    );
    const optionsPayload = optionsResponse.data?.options || {};
    const options = {
      tripulantes: Array.isArray(optionsPayload.tripulantes) ? optionsPayload.tripulantes : [],
      equipamentos: Array.isArray(optionsPayload.equipamentos) ? optionsPayload.equipamentos : [],
      tipos: Array.isArray(optionsPayload.tipos) ? optionsPayload.tipos : [],
      attachments: Array.isArray(optionsPayload.attachments) ? optionsPayload.attachments : [],
    };
    const attachments = Array.isArray(treinamento?.attachments) ? treinamento.attachments : options.attachments;
    const capabilities = capabilitySet();

    renderShell(
      `
        <div class="page-header"><h1>${treinamentoId ? "Atualizar treinamento" : "Cadastrar novo treinamento"}</h1></div>
        <form id="treinamento-form" class="form-grid">
          <label>
            Tripulante
            <select name="tripulante_id" required>
              <option value="">Selecione</option>
              ${options.tripulantes
                .map(
                  (item) => `<option value="${item.id}" ${String(treinamento?.tripulante_id || "") === String(item.id) ? "selected" : ""}>${escapeHtml(item.nome)}</option>`,
                )
                .join("")}
            </select>
          </label>
          <label>
            Equipamento
            <select name="equipamento_id" id="treinamentoEquipamento">
              <option value="">Sem equipamento</option>
              ${options.equipamentos
                .map(
                  (item) => `<option value="${item.id}" ${String(treinamento?.equipamento_id || "") === String(item.id) ? "selected" : ""}>${escapeHtml(item.nome)}</option>`,
                )
                .join("")}
            </select>
          </label>
          <label>
            Tipo de treinamento
            <select name="tipo_treinamento_id" id="tipo_treinamento_id" required>
              <option value="">Selecione</option>
              ${options.tipos
                .map(
                  (item) => `
                    <option
                      value="${item.id}"
                      data-periodicidade="${item.periodicidade_meses || 0}"
                      data-exige-equipamento="${item.exige_equipamento ? 1 : 0}"
                      ${String(treinamento?.tipo_treinamento_id || "") === String(item.id) ? "selected" : ""}
                    >${escapeHtml(item.nome)}</option>
                  `,
                )
                .join("")}
            </select>
          </label>
          <div class="full-width hint" id="trainingTypeHint">Selecione o tipo para ver se ele exige vínculo com equipamento específico.</div>
          <label>Data de realização<input type="date" name="data_realizacao" id="data_realizacao" value="${escapeAttr(treinamento?.data_realizacao || "")}"></label>
          <label>
            Opção da data de vencimento
            <select id="due_date_mode" name="due_date_mode">
              <option value="auto" ${!treinamento || treinamento.due_date_mode === "auto" ? "selected" : ""}>Calcular automaticamente</option>
              <option value="manual" ${treinamento?.due_date_mode === "manual" ? "selected" : ""}>Informar manualmente</option>
            </select>
          </label>
          <label id="due_date_field_wrap">
            Data de vencimento
            <input type="date" name="data_vencimento" id="data_vencimento" value="${escapeAttr(treinamento?.data_vencimento || "")}">
            <span class="field-help">Escolha "Informar manualmente" para definir a data por conta própria, ou deixe no automático para calcular a partir da realização e da periodicidade.</span>
          </label>
          <label class="full-width">Observação<textarea name="observacao">${escapeHtml(treinamento?.observacao || "")}</textarea></label>
          <div class="form-actions full-width">
            <button type="submit">Salvar alterações</button>
            ${treinamentoId && capabilities.has("treinamentos:delete") ? '<button type="button" class="button-link secondary" id="treinamento-delete">Excluir treinamento</button>' : ""}
            <a class="button-link secondary" href="#/treinamentos">Voltar sem salvar</a>
          </div>
        </form>

        ${renderTrainingAttachmentSection(treinamentoId, attachments, capabilities)}
      `,
      treinamentoId ? "Editar Treinamento" : "Novo Treinamento",
    );

    const typeSelect = document.getElementById("tipo_treinamento_id");
    const realizedInput = document.getElementById("data_realizacao");
    const dueModeSelect = document.getElementById("due_date_mode");
    const dueInput = document.getElementById("data_vencimento");
    const dueFieldWrap = document.getElementById("due_date_field_wrap");
    const equipmentSelect = document.getElementById("treinamentoEquipamento");
    const trainingTypeHint = document.getElementById("trainingTypeHint");
    let lastAutoValue = dueInput?.value || "";

    function syncEquipmentRequirement() {
      const selected = typeSelect?.options[typeSelect.selectedIndex];
      const requiresEquipment = selected?.dataset?.exigeEquipamento === "1";
      if (equipmentSelect) equipmentSelect.required = requiresEquipment;
      if (!trainingTypeHint) return;
      if (requiresEquipment) {
        trainingTypeHint.textContent = "Este tipo exige vínculo com equipamento ou aeronave específica.";
        trainingTypeHint.className = "hint";
      } else if (selected?.value) {
        trainingTypeHint.textContent = "Este tipo pertence à categoria Especiais e pode ser registrado sem equipamento específico. Exemplo: IFR.";
        trainingTypeHint.className = "hint";
      } else {
        trainingTypeHint.textContent = "Selecione o tipo para ver se ele exige vínculo com equipamento específico.";
        trainingTypeHint.className = "hint";
      }
    }

    function calculateDueDate() {
      if (!typeSelect || !realizedInput || !dueModeSelect || !dueInput) return;
      if (dueModeSelect.value === "manual") return;
      const selected = typeSelect.options[typeSelect.selectedIndex];
      const months = Number(selected?.dataset?.periodicidade || 0);
      const canReplace = !dueInput.value || dueInput.value === lastAutoValue;
      if (!months || !realizedInput.value || !canReplace) return;
      const [year, month, day] = realizedInput.value.split("-").map(Number);
      const dueDate = new Date(year, month - 1, day);
      dueDate.setMonth(dueDate.getMonth() + months);
      const yyyy = dueDate.getFullYear();
      const mm = String(dueDate.getMonth() + 1).padStart(2, "0");
      const dd = String(dueDate.getDate()).padStart(2, "0");
      lastAutoValue = `${yyyy}-${mm}-${dd}`;
      dueInput.value = lastAutoValue;
    }

    function syncDueMode() {
      if (!dueModeSelect || !dueInput || !dueFieldWrap) return;
      const isManual = dueModeSelect.value === "manual";
      dueInput.disabled = !isManual;
      dueFieldWrap.style.opacity = isManual ? "1" : "0.72";
      if (!isManual) {
        if (!dueInput.value || dueInput.value === lastAutoValue) dueInput.value = "";
        calculateDueDate();
      }
    }

    realizedInput?.addEventListener("change", calculateDueDate);
    typeSelect?.addEventListener("change", () => {
      syncEquipmentRequirement();
      calculateDueDate();
    });
    dueModeSelect?.addEventListener("change", syncDueMode);
    dueInput?.addEventListener("input", () => {
      if (dueInput.value !== lastAutoValue) lastAutoValue = "";
    });
    syncEquipmentRequirement();
    syncDueMode();
    calculateDueDate();

    document.getElementById("treinamento-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        const result = await api(treinamentoId ? `/api/v1/treinamentos/${treinamentoId}` : "/api/v1/treinamentos", {
          method: treinamentoId ? "PUT" : "POST",
          json: Object.fromEntries(new FormData(event.currentTarget).entries()),
        });
        showFlash("Treinamento salvo com sucesso.", "success");
        const nextId = Number(result.data.treinamento.id);
        if (Number(treinamentoId || 0) === nextId) {
          await renderTreinamentoFormPage(nextId);
        } else {
          window.location.hash = `#/treinamentos/${nextId}`;
        }
      } catch (error) {
        showFlash(buildErrorMessage(error), "error");
        await renderTreinamentoFormPage(treinamentoId);
      }
    });

    document.getElementById("treinamento-delete")?.addEventListener("click", async () => {
      if (!window.confirm("Excluir este treinamento?")) return;
      try {
        await api(`/api/v1/treinamentos/${treinamentoId}`, { method: "DELETE" });
        showFlash("Treinamento removido com sucesso.", "success");
        window.location.hash = "#/treinamentos";
      } catch (error) {
        showFlash(buildErrorMessage(error), "error");
        await renderTreinamentoFormPage(treinamentoId);
      }
    });

    document.getElementById("treinamento-attachment-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await api(`/api/v1/treinamentos/${treinamentoId}/attachments`, {
          method: "POST",
          body: new FormData(event.currentTarget),
        });
        showFlash("Anexo enviado com sucesso.", "success");
      } catch (error) {
        showFlash(buildErrorMessage(error), "error");
      }
      await renderTreinamentoFormPage(treinamentoId);
    });

    document.querySelectorAll(".treinamento-attachment-delete").forEach((button) => {
      button.addEventListener("click", async () => {
        if (!window.confirm("Excluir este anexo PDF?")) return;
        try {
          await api(`/api/v1/treinamentos/${treinamentoId}/attachments/${button.dataset.attachmentId}`, { method: "DELETE" });
          showFlash("Anexo removido com sucesso.", "success");
        } catch (error) {
          showFlash(buildErrorMessage(error), "error");
        }
        await renderTreinamentoFormPage(treinamentoId);
      });
    });
  } catch (error) {
    showFlash(buildErrorMessage(error), "error");
    renderShell("<section class='panel'><div class='empty'>Falha ao carregar formulário de treinamento.</div></section>", "Treinamentos");
  }
}

export async function renderRelatorioHabilitacoesPage() {
  const filters = Object.fromEntries(hashQuery().entries());
  try {
    const { data } = await api(`/api/v1/relatorios/habilitacoes?${new URLSearchParams(filters).toString()}`);
    const report = data.report || {};
    const reportFilters = report.filters || {};
    const reportOptionsPayload = report.options || {};
    const reportOptions = {
      bases: Array.isArray(reportOptionsPayload.bases) ? reportOptionsPayload.bases : [],
      tipos: Array.isArray(reportOptionsPayload.tipos) ? reportOptionsPayload.tipos : [],
      status: Array.isArray(reportOptionsPayload.status) ? reportOptionsPayload.status : [],
    };
    const reportSummary = report.summary || {};
    const reportItems = Array.isArray(report.items) ? report.items : [];

    renderShell(
      `
        <div class="page-header">
          <div>
            <h1>Consolidado de habilitações</h1>
            <p class="page-subtitle">Visão operacional consolidada de vencimentos de habilitações por tripulante.</p>
          </div>
          <div class="page-header-actions print-hide">
            <a class="button-link secondary" href="#/treinamentos">Voltar para treinamentos</a>
            <a class="button-link secondary" href="${buildServerHref("/treinamentos/consolidado/export.csv", reportFilters)}">Exportar CSV</a>
            <a class="button-link" target="_blank" rel="noopener noreferrer" href="${buildServerHref("/treinamentos/consolidado/relatorio", { ...reportFilters, auto_print: 1 })}">Imprimir visualização</a>
            <a class="button-link secondary" target="_blank" rel="noopener noreferrer" href="${buildServerHref("/treinamentos/consolidado/relatorio", reportFilters)}">Visualizar impressão</a>
          </div>
        </div>

        <section class="panel">
          <section class="consolidated-brand-banner print-hide">
            <div class="consolidated-brand-left">
              <img class="consolidated-brand-logo" src="/static/logo-brasilvida.svg" alt="Brasilvida">
              <div>
                <div class="consolidated-brand-kicker">Treinamentos Brasil Vida</div>
                <div class="consolidated-brand-title">Relatório consolidado de habilitações</div>
                <div class="consolidated-brand-subtitle">Padrão operacional corporativo para vencimentos e criticidade.</div>
              </div>
            </div>
            <div class="consolidated-brand-meta">
              <div class="consolidated-brand-meta-label">Emissão</div>
              <div class="consolidated-brand-meta-value">${escapeHtml(report.emitted_at || new Date().toLocaleString("pt-BR"))}</div>
            </div>
          </section>

          <header class="report-print-header report-only">
            <div class="report-brand-row">
              <img class="report-logo" src="/static/logo-brasilvida.svg" alt="Brasilvida">
              <div class="report-brand-meta">
                <div class="report-doc-title">Consolidado de Habilitações</div>
                <div class="report-doc-subtitle">Relatório operacional de vencimentos por tripulante</div>
              </div>
            </div>
            <div class="report-issued-at">Emissão: ${escapeHtml(report.emitted_at || new Date().toLocaleString("pt-BR"))}</div>
          </header>

          <div class="state-note print-hide" style="margin-bottom: 12px;">
            Emissão operacional: use <strong>Imprimir visualização</strong> para gerar o documento e <strong>Exportar CSV</strong> para análise externa com os filtros atuais.
          </div>

          <div class="filters-toggle-row print-hide">
            <button type="button" class="button-link secondary filters-toggle-btn" id="consolidatedFiltersToggle" aria-expanded="false" aria-controls="consolidatedFiltersPanel">Mostrar filtros</button>
          </div>

          <div class="filters-panel ${reportFilters.nome || reportFilters.base || reportFilters.status || reportFilters.tipo || reportFilters.ordenacao !== "criticidade" ? "" : "collapsed"}" id="consolidatedFiltersPanel">
            <form class="filters filters-wide" id="habilitacoes-filter-form">
              <input type="text" name="nome" placeholder="Buscar tripulante" value="${escapeAttr(reportFilters.nome)}">
              <select name="base">
                <option value="">Base</option>
                ${reportOptions.bases
                  .map((item) => `<option value="${escapeAttr(item.nome)}" ${reportFilters.base === item.nome ? "selected" : ""}>${escapeHtml(item.nome)}</option>`)
                  .join("")}
              </select>
              <select name="tipo">
                <option value="">Tipo de habilitação</option>
                ${reportOptions.tipos
                  .map((item) => `<option value="${item.id}" ${String(reportFilters.tipo || "") === String(item.id) ? "selected" : ""}>${escapeHtml(item.nome)}</option>`)
                  .join("")}
              </select>
              <select name="status">
                <option value="">Status</option>
                ${reportOptions.status
                  .map((item) => {
                    const key = typeof item === "string" ? item : item.key;
                    const label = typeof item === "string" ? item : item.label;
                    return `<option value="${escapeAttr(key)}" ${reportFilters.status === key ? "selected" : ""}>${escapeHtml(label)}</option>`;
                  })
                  .join("")}
              </select>
              <select name="ordenacao">
                <option value="criticidade" ${reportFilters.ordenacao === "criticidade" ? "selected" : ""}>Ordenar por criticidade</option>
                <option value="vencimento" ${reportFilters.ordenacao === "vencimento" ? "selected" : ""}>Ordenar por vencimento</option>
              </select>
              <button type="submit">Aplicar filtros</button>
              <a class="button-link secondary" href="#/relatorios/habilitacoes">Limpar filtros</a>
            </form>
          </div>

          <section class="summary-grid consolidated-summary-grid">
            <div class="summary-card"><strong>Total de tripulantes</strong><span>${formatInteger(reportSummary.total_tripulantes)}</span></div>
            <div class="summary-card"><strong>Total de habilitações</strong><span>${formatInteger(reportSummary.total_habilitacoes)}</span></div>
            <div class="summary-card"><strong>Em dia</strong><span>${formatInteger(reportSummary.total_em_dia)}</span></div>
            <div class="summary-card"><strong>A vencer até 90 dias</strong><span>${formatInteger(reportSummary.total_vencer_90)}</span></div>
            <div class="summary-card"><strong>A vencer até 60 dias</strong><span>${formatInteger(reportSummary.total_vencer_60)}</span></div>
            <div class="summary-card"><strong>A vencer até 30 dias</strong><span>${formatInteger(reportSummary.total_vencer_30)}</span></div>
            <div class="summary-card"><strong>Crítico até 15 dias</strong><span>${formatInteger(reportSummary.total_critico_15)}</span></div>
            <div class="summary-card"><strong>Vencido</strong><span>${formatInteger(reportSummary.total_vencido)}</span></div>
          </section>

          <div class="consolidated-table-wrap">
            <div class="table-wrap">
              <table class="data-table consolidated-table responsive-cards">
                <thead>
                  <tr>
                    <th>Habilitação</th>
                    <th>Data de vencimento</th>
                    <th>Dias restantes</th>
                    <th>Status</th>
                    <th>Ações</th>
                  </tr>
                </thead>
                <tbody>
                  ${
                    reportItems.length
                      ? reportItems
                          .map(
                            (group) => `
                              <tr class="consolidated-group-row">
                                <td colspan="5">
                                  <div class="consolidated-group-header">
                                    <div>
                                      <strong>${escapeHtml(group.tripulante_nome)}</strong>
                                      <span>Base: ${escapeHtml(group.base || "-")}</span>
                                    </div>
                                    <div class="consolidated-group-meta">Função/Cargo: ${escapeHtml(group.funcao_cargo || "-")}</div>
                                  </div>
                                </td>
                              </tr>
                              ${(Array.isArray(group.habilitacoes) ? group.habilitacoes : [])
                                .map(
                                  (item) => `
                                    <tr class="${["vencido", "critico_15"].includes(item.status_key) ? "consolidated-row-critical" : ""}">
                                      <td data-label="Habilitação">${escapeHtml(item.habilitacao_nome)}</td>
                                      <td data-label="Data de vencimento"><span class="date-strong">${escapeHtml(item.data_vencimento || "-")}</span></td>
                                      <td data-label="Dias restantes">${escapeHtml(item.days_remaining_label || "-")}</td>
                                      <td data-label="Status"><span class="status-pill ${trainingStatusClass(item.status_label)}${item.pulse ? " status-pill-pulse" : ""}">${escapeHtml(item.status_label || "-")}</span></td>
                                      <td class="actions" data-label="Ações">
                                        ${item.treinamento_id ? `<a href="#/treinamentos/${item.treinamento_id}">Abrir</a>` : '<span class="secondary-cell">-</span>'}
                                      </td>
                                    </tr>
                                  `,
                                )
                                .join("")}
                            `,
                          )
                          .join("")
                      : '<tr><td colspan="5" class="empty">Nenhum registro encontrado para os filtros atuais.</td></tr>'
                  }
                </tbody>
              </table>
            </div>
          </div>

          <footer class="report-print-footer report-only">
            Treinamentos Brasil Vida · Consolidado de habilitações · Emissão ${escapeHtml(report.emitted_at || new Date().toLocaleString("pt-BR"))}
          </footer>
        </section>
      `,
      "Relatório de Habilitações",
    );

    wireResponsiveFilters("consolidatedFiltersToggle", "consolidatedFiltersPanel", "Ocultar filtros", "Mostrar filtros");

    document.getElementById("habilitacoes-filter-form")?.addEventListener("submit", (event) => {
      event.preventDefault();
      window.location.hash = buildHashHref("#/relatorios/habilitacoes", Object.fromEntries(new FormData(event.currentTarget).entries()));
    });
  } catch (error) {
    showFlash(buildErrorMessage(error), "error");
    renderShell("<section class='panel'><div class='empty'>Falha ao carregar relatório.</div></section>", "Relatório de Habilitações");
  }
}

export async function renderRelatorioProdutividadePage() {
  const filters = Object.fromEntries(hashQuery().entries());
  try {
    const { data } = await api(`/api/v1/relatorios/produtividade?${new URLSearchParams(filters).toString()}`);
    const report = data.report || {};
    const reportFilters = report.filters || {};
    const reportOptionsPayload = report.options || {};
    const reportOptions = {
      competencias: Array.isArray(reportOptionsPayload.competencias) ? reportOptionsPayload.competencias : [],
      bases: Array.isArray(reportOptionsPayload.bases) ? reportOptionsPayload.bases : [],
      funcoes: Array.isArray(reportOptionsPayload.funcoes) ? reportOptionsPayload.funcoes : [],
      categorias: Array.isArray(reportOptionsPayload.categorias) ? reportOptionsPayload.categorias : [],
    };
    const reportSummary = report.summary || {};
    const reportItems = Array.isArray(report.items) ? report.items : [];
    const reportCompetencia = report.competencia || filters.competencia || "";
    const reportCompetenciaLabel = report.competencia_label || formatCompetenciaLabel(reportCompetencia);

    renderShell(
      `
        <div class="page-header">
          <div>
            <h1>Consolidado de produtividade</h1>
            <p class="page-subtitle">Competência ${escapeHtml(reportCompetenciaLabel)} · visão executiva de piso mínimo x produtividade apurada.</p>
          </div>
          <div class="page-header-actions print-hide">
            <a class="button-link secondary" href="${buildServerHref("/produtividade/adicionais", { competencia: reportCompetencia })}">Adicionais excepcionais</a>
            <a class="button-link secondary" href="${buildServerHref("/produtividade/painel-tv", { competencia: reportCompetencia })}">Painel TV</a>
            <button type="button" class="button-link" id="produtividadePrintButton">Imprimir visualização</button>
          </div>
        </div>

        <section class="panel">
          <section class="consolidated-brand-banner print-hide">
            <div class="consolidated-brand-left">
              <img class="consolidated-brand-logo" src="/static/logo-brasilvida.svg" alt="Brasilvida">
              <div>
                <div class="consolidated-brand-kicker">Treinamentos Brasil Vida</div>
                <div class="consolidated-brand-title">Relatório consolidado de produtividade</div>
                <div class="consolidated-brand-subtitle">Padrão operacional corporativo para fechamento mensal e conferência.</div>
              </div>
            </div>
            <div class="consolidated-brand-meta">
              <div class="consolidated-brand-meta-label">Emissão</div>
              <div class="consolidated-brand-meta-value">${escapeHtml(report.emitted_at || new Date().toLocaleString("pt-BR"))}</div>
            </div>
          </section>

          <header class="report-print-header report-only">
            <div class="report-brand-row">
              <img class="report-logo" src="/static/logo-brasilvida.svg" alt="Brasilvida">
              <div class="report-brand-meta">
                <div class="report-doc-title">Consolidado de Produtividade</div>
                <div class="report-doc-subtitle">Relatório operacional de bonificação por tripulante</div>
              </div>
            </div>
            <div class="report-issued-at">Emissão: ${escapeHtml(report.emitted_at || new Date().toLocaleString("pt-BR"))}</div>
          </header>

          <section class="competencia-history print-hide">
            <div class="competencia-history-title">Histórico de bonificação disponível</div>
            <div class="competencia-history-list">
              ${reportOptions.competencias
                .map(
                  (item) => `
                    <a class="competencia-chip ${item === reportCompetencia ? "active" : ""}" href="${buildHashHref("#/relatorios/produtividade", {
                      competencia: item,
                      nome: reportFilters.nome,
                      base: reportFilters.base,
                      funcao: reportFilters.funcao,
                      categoria: reportFilters.categoria,
                      ordenacao: reportFilters.ordenacao,
                    })}">
                      ${escapeHtml(formatCompetenciaLabel(item))}
                    </a>
                  `,
                )
                .join("")}
            </div>
          </section>

          <div class="state-note print-hide" style="margin-bottom: 12px;">
            Emissão operacional: registre <strong>Missões</strong> e <strong>Pernoites</strong>, valide <strong>Adicionais</strong> e feche a competência com conferência.
          </div>

          <div class="filters-toggle-row print-hide">
            <button type="button" class="button-link secondary filters-toggle-btn" id="productivityFiltersToggle" aria-expanded="false" aria-controls="productivityFiltersPanel">Mostrar filtros</button>
          </div>

          <div class="filters-panel ${reportFilters.nome || reportFilters.base || reportFilters.funcao || reportFilters.categoria || reportFilters.ordenacao !== "valor_final" ? "" : "collapsed"}" id="productivityFiltersPanel">
            <form class="filters filters-wide" id="produtividade-filter-form">
              <label>Competência<input type="month" name="competencia" value="${escapeAttr(reportCompetencia)}"></label>
              <input type="text" name="nome" placeholder="Buscar tripulante" value="${escapeAttr(reportFilters.nome)}">
              <select name="base">
                <option value="">Base</option>
                ${reportOptions.bases
                  .map((item) => `<option value="${escapeAttr(item)}" ${reportFilters.base === item ? "selected" : ""}>${escapeHtml(item)}</option>`)
                  .join("")}
              </select>
              <select name="funcao">
                <option value="">Função</option>
                ${reportOptions.funcoes
                  .map((item) => `<option value="${escapeAttr(item)}" ${reportFilters.funcao === item ? "selected" : ""}>${escapeHtml(item)}</option>`)
                  .join("")}
              </select>
              <select name="categoria">
                <option value="">Categoria</option>
                ${reportOptions.categorias
                  .map((item) => `<option value="${escapeAttr(item)}" ${reportFilters.categoria === item ? "selected" : ""}>${escapeHtml(item)}</option>`)
                  .join("")}
              </select>
              <select name="ordenacao">
                <option value="valor_final" ${reportFilters.ordenacao === "valor_final" ? "selected" : ""}>Ordenar por maior valor final</option>
                <option value="produtividade" ${reportFilters.ordenacao === "produtividade" ? "selected" : ""}>Ordenar por maior produtividade</option>
                <option value="base" ${reportFilters.ordenacao === "base" ? "selected" : ""}>Ordenar por base</option>
                <option value="nome" ${reportFilters.ordenacao === "nome" ? "selected" : ""}>Ordenar por nome</option>
              </select>
              <button type="submit">Aplicar filtros</button>
              <a class="button-link secondary" href="#/relatorios/produtividade">Limpar filtros</a>
            </form>
          </div>

          <section class="summary-grid consolidated-summary-grid">
            <div class="summary-card"><strong>Tripulantes processados</strong><span>${formatInteger(reportSummary.total_tripulantes)}</span></div>
            <div class="summary-card"><strong>Total de missões</strong><span>${formatInteger(reportSummary.total_missoes)}</span></div>
            <div class="summary-card"><strong>Total de pernoites</strong><span>${formatInteger(reportSummary.total_pernoites)}</span></div>
            <div class="summary-card"><strong>Total piso mínimo</strong><span>${formatCurrencyBr(reportSummary.total_pago_piso)}</span></div>
            <div class="summary-card"><strong>Total por produtividade</strong><span>${formatCurrencyBr(reportSummary.total_pago_produtividade)}</span></div>
            <div class="summary-card"><strong>Valor consolidado</strong><span>${formatCurrencyBr(reportSummary.valor_total_consolidado)}</span></div>
            <div class="summary-card"><strong>Categorias A/B</strong><span>${formatInteger(reportSummary.categoria_a)} / ${formatInteger(reportSummary.categoria_b)}</span></div>
            <div class="summary-card"><strong>Com adicionais ativos</strong><span>${formatInteger(reportSummary.tripulantes_com_adicionais)}</span></div>
          </section>

          <div class="table-wrap">
            <table class="data-table consolidated-table responsive-cards">
              <thead>
                <tr>
                  <th>Tripulante</th>
                  <th>Base / Perfil</th>
                  <th>Missões</th>
                  <th>Pernoites</th>
                  <th>Piso mínimo</th>
                  <th>Produtividade</th>
                  <th>Valor final</th>
                  <th>Critério</th>
                  <th>Conferência</th>
                  <th>Ações</th>
                </tr>
              </thead>
              <tbody>
                ${
                  reportItems.length
                    ? reportItems
                        .map(
                          (item) => `
                            <tr class="${String(item.criterio_fechamento || "").toLowerCase().includes("piso") ? "consolidated-row-critical" : ""}">
                              <td data-label="Tripulante"><strong>${escapeHtml(item.tripulante_nome)}</strong></td>
                              <td data-label="Base / Perfil">${escapeHtml(item.base || "-")}<div class="secondary-cell">${escapeHtml(item.funcao || "-")} · ${escapeHtml(item.categoria || "-")}</div></td>
                              <td data-label="Missões">${formatInteger(item.total_missoes_validas)}</td>
                              <td data-label="Pernoites">${formatInteger(item.total_pernoites)}</td>
                              <td data-label="Piso mínimo">${formatCurrencyBr(item.piso_minimo_mensal ?? 0)}</td>
                              <td data-label="Produtividade">${formatCurrencyBr(item.total_produtividade)}</td>
                              <td data-label="Valor final"><span class="date-strong">${formatCurrencyBr(item.valor_final_mes)}</span></td>
                              <td data-label="Critério"><span class="status-pill ${String(item.criterio_fechamento || "").toLowerCase().includes("piso") ? "status-yellow" : "status-green"}">${escapeHtml(item.criterio_fechamento || "-")}</span></td>
                              <td data-label="Conferência">
                                ${
                                  item.conferencia
                                    ? `
                                      <div class="secondary-cell"><span class="status-pill status-green">Conferido</span></div>
                                      <div class="secondary-cell">${escapeHtml(item.conferencia.conferido_por_nome || "-")}</div>
                                      <div class="secondary-cell">${escapeHtml(formatDateTimeBr(item.conferencia.conferido_em))}</div>
                                    `
                                    : '<span class="status-pill status-gray">Pendente</span>'
                                }
                              </td>
                              <td class="actions" data-label="Ações">
                                <button type="button" class="${item.conferencia ? "link-danger " : ""}conferencia-btn" data-tripulante-id="${item.tripulante_id}" data-action="${item.conferencia ? "unmark" : "mark"}">${item.conferencia ? "Desmarcar" : "Marcar conferido"}</button>
                                <a href="${buildServerHref(`/produtividade/tripulantes/${item.tripulante_id}`, { competencia: reportCompetencia })}">Relatório</a>
                              </td>
                            </tr>
                          `,
                        )
                        .join("")
                    : '<tr><td colspan="10" class="empty">Nenhum tripulante encontrado para os filtros informados.</td></tr>'
                }
              </tbody>
            </table>
          </div>

          ${
            Number(reportSummary.total_missoes || 0) === 0 && Number(reportSummary.total_pernoites || 0) === 0
              ? `
                <div class="empty" style="margin-top: 1rem;">
                  Nenhum lançamento operacional encontrado nesta competência.
                  Cadastre primeiro em
                  <a href="/missoes/novo">Missões</a>,
                  <a href="/pernoites/novo">Pernoites</a>
                  e, se necessário,
                  <a href="${buildServerHref("/produtividade/adicionais/novo", { competencia: reportCompetencia })}">Adicional excepcional</a>.
                </div>
              `
              : ""
          }

          <footer class="report-print-footer report-only">
            Treinamentos Brasil Vida · Consolidado de produtividade · Emissão ${escapeHtml(report.emitted_at || new Date().toLocaleString("pt-BR"))}
          </footer>
        </section>
      `,
      "Relatório de Produtividade",
    );

    wireResponsiveFilters("productivityFiltersToggle", "productivityFiltersPanel", "Ocultar filtros", "Mostrar filtros");

    document.getElementById("produtividadePrintButton")?.addEventListener("click", () => {
      window.print();
    });

    document.getElementById("produtividade-filter-form")?.addEventListener("submit", (event) => {
      event.preventDefault();
      window.location.hash = buildHashHref("#/relatorios/produtividade", Object.fromEntries(new FormData(event.currentTarget).entries()));
    });
    document.querySelectorAll(".conferencia-btn").forEach((button) => {
      button.addEventListener("click", async () => {
        try {
          await api("/api/v1/relatorios/produtividade/conferencias", {
            method: "POST",
            json: {
              tripulante_id: Number(button.dataset.tripulanteId),
              competencia: reportCompetencia,
              action: button.dataset.action,
            },
          });
          showFlash("Conferência atualizada com sucesso.", "success");
        } catch (error) {
          showFlash(buildErrorMessage(error), "error");
        }
        await renderRelatorioProdutividadePage();
      });
    });
  } catch (error) {
    showFlash(buildErrorMessage(error), "error");
    renderShell("<section class='panel'><div class='empty'>Falha ao carregar produtividade.</div></section>", "Relatório de Produtividade");
  }
}


