import {
  api,
  buildErrorMessage,
  capabilitySet,
  confirmAction,
  escapeAttr,
  escapeHtml,
  fileToDataUrl,
  renderInlineFeedback,
  showFlash,
  withActionBusy,
} from "../../lib.20260430-142420.cf58b4b4395e.js";
import { renderShell } from "../../shell.20260430-142420.eed3fe973fa2.js";
import { wireCriticalFormDraftProtection } from "../../shared/forms/draft-protection.20260430-142420.b75e9befef5d.js";
import {
  adaptTrainingProgramOptions,
  adaptTrainingProgramRecords,
  buildDuePreview,
  buildTrainingProgramOperationalSummary,
  formatInteger,
  navigateTrainingProgramFilters,
  readTrainingProgramFilters,
  renderHoursReference,
  renderTrainingProgramRecordsTable,
  renderTrainingProgramSelectedCards,
  renderTrainingProgramSelectorGroups,
  selectedTypeFromOptions,
  todayIso,
} from "./program-helpers.20260430-142420.c573a857a926.js";

function adaptTrainingBaseOptions(payload) {
  const bases = payload?.options?.bases;
  return Array.isArray(bases) ? bases : [];
}

export async function renderTreinamentosListPage() {
  renderShell(
    "<section class='panel training-program-panel ui-surface'><div class='empty operational-empty ui-table-state'><strong>Carregando treinamentos por tripulante</strong><span>Buscando filtros, permissões e registros salvos.</span></div></section>",
    "Treinamentos por Tripulante",
  );

  try {
    const filters = readTrainingProgramFilters();
    const baseFilter = String(filters.base || "").trim();
    const optionsQuery = new URLSearchParams();
    if (baseFilter) optionsQuery.set("base", baseFilter);
    const capabilities = capabilitySet();
    const optionsRequest = baseFilter
      ? api(`/api/v1/treinamentos-tripulantes/options?${optionsQuery.toString()}`)
      : api("/api/v1/treinamentos-tripulantes/options");
    const [baseOptionsResponse, optionsResponse, recordsResponse] = await Promise.all([
      api("/api/v1/tripulantes/options"),
      optionsRequest,
      api(`/api/v1/treinamentos-tripulantes?${new URLSearchParams(filters).toString()}`),
    ]);
    const baseOptions = adaptTrainingBaseOptions(baseOptionsResponse.data);
    const options = adaptTrainingProgramOptions(optionsResponse.data);
    const records = adaptTrainingProgramRecords(recordsResponse.data);
    const operationalSummary = buildTrainingProgramOperationalSummary(records);
    const selectedType = selectedTypeFromOptions(options.tipos_treinamento || [], filters.tipo_treinamento_id);
    const hasSelectedTripulante = String(filters.tripulante_id || "").trim() !== "";

    let template = null;
    let templateError = "";
    if (selectedType && hasSelectedTripulante && (!selectedType.exige_aeronave || filters.aeronave_modelo)) {
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
        <div class="training-reports-page-shell training-program-page-shell priority-page-surface ui-page-shell ui-stack">
        <div class="page-header priority-page-header ui-page-header ui-surface">
          <div>
            <h1>Cadastro de treinamento para tripulante</h1>
            <p class="page-subtitle">ABA 2. Selecione tripulante, tipo e aeronave para carregar os segmentos da fonte mestre em tempo real.</p>
          </div>
          <div class="page-header-actions">
            ${capabilities.has("tipos_treinamento:view") ? '<a class="button-link secondary" href="#/treinamentos/raiz">Abrir cadastro raiz</a>' : ""}
          </div>
        </div>

        <section class="panel training-program-panel ui-surface ui-stack">
          <div class="page-header compact-page-header">
            <div>
              <h2>Etapa 1 - Seleção inicial</h2>
              <p class="page-subtitle">Base + tripulante + tipo de treinamento + modelo de aeronave.</p>
            </div>
          </div>
          <form id="training-program-selection-form" class="filters filters-wide ui-form-toolbar ui-stack-sm">
            <select name="base" id="trainingProgramBase">
              <option value="">Todas as bases</option>
              ${baseOptions
                .map(
                  (item) => `<option value="${escapeAttr(item.nome)}" ${String(filters.base || "") === String(item.nome || "") ? "selected" : ""}>${escapeHtml(item.nome || "-")}${item.uf ? ` - ${escapeHtml(item.uf)}` : ""}</option>`,
                )
                .join("")}
            </select>
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

        ${templateError ? `<section class="panel training-program-panel ui-surface"><div class="flash error" role="alert" aria-live="assertive">${escapeHtml(templateError)}</div></section>` : ""}
        ${template ? renderHoursReference(template) : ""}

        ${
          template
            ? `
              <section class="panel training-program-panel ui-surface ui-stack">
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
                  <section class="training-workbench-pane ui-surface">
                    <div class="training-pane-head">
                      <div>
                        <h3>Etapa 2 - Selecione os segmentos</h3>
                        <p>Marque apenas os segmentos que o tripulante realizou ou precisa renovar agora.</p>
                      </div>
                      <span class="training-pane-counter">${formatInteger((template.segmentos || []).length)} disponíveis</span>
                    </div>
                    ${renderTrainingProgramSelectorGroups(template)}
                    <div class="training-selector-actions ui-form-actions">
                      <button type="button" id="trainingProgramContinueButton" disabled>Selecione ao menos 1 segmento</button>
                      <button type="button" class="button-link secondary" id="trainingProgramResetButton">Limpar seleção</button>
                    </div>
                    <div class="training-selector-feedback" id="trainingProgramSelectionFeedback">Marque um ou mais segmentos para liberar a etapa de preenchimento.</div>
                  </section>

                  <section class="training-workbench-pane training-workbench-pane--details ui-surface">
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
                      <div class="form-actions training-submit-bar ui-form-actions">
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
              <section class="panel training-program-panel ui-surface">
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

        <section class="panel training-program-panel ui-surface ui-stack">
          <div class="page-header compact-page-header">
            <div>
              <h2>Registros salvos</h2>
              <p class="page-subtitle">Consulta em tempo real dos registros criados para os segmentos selecionados.</p>
            </div>
          </div>
          <div id="training-program-feedback" aria-live="polite"></div>
          <section class="summary-grid compact-summary-grid training-program-operational-summary ui-card-grid ui-card-grid-compact ui-card-equal-height">
            <div class="summary-card ui-surface training-program-summary-card"><strong>Total</strong><span>${formatInteger(operationalSummary.total)}</span><small>registros carregados</small></div>
            <div class="summary-card ui-surface training-program-summary-card training-program-summary-card--critical"><strong>Vencidos</strong><span>${formatInteger(operationalSummary.vencidos)}</span><small>prioridade imediata</small></div>
            <div class="summary-card ui-surface training-program-summary-card training-program-summary-card--warning"><strong>A vencer</strong><span>${formatInteger(operationalSummary.a_vencer)}</span><small>monitorar renovação</small></div>
            <div class="summary-card ui-surface training-program-summary-card training-program-summary-card--stable"><strong>Regulares</strong><span>${formatInteger(operationalSummary.regulares)}</span><small>em dia</small></div>
            <div class="summary-card ui-surface training-program-summary-card training-program-summary-card--neutral"><strong>Sem informação</strong><span>${formatInteger(operationalSummary.sem_informacao)}</span><small>regularização pendente</small></div>
            <div class="summary-card ui-surface training-program-summary-card training-program-summary-card--warning"><strong>Sem anexo</strong><span>${formatInteger(operationalSummary.sem_anexo)}</span><small>sem evidência PDF</small></div>
          </section>
          ${renderTrainingProgramRecordsTable(records, capabilities)}
        </section>
        </div>
      `,
      "Treinamentos por Tripulante",
    );

    document.getElementById("training-program-selection-form")?.addEventListener("submit", (event) => {
      event.preventDefault();
      const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
      navigateTrainingProgramFilters(payload);
    });
    document.getElementById("trainingProgramBase")?.addEventListener("change", (event) => {
      navigateTrainingProgramFilters({
        base: event.currentTarget.value,
        tipo_treinamento_id: filters.tipo_treinamento_id || "",
        aeronave_modelo: filters.aeronave_modelo || "",
      });
    });

    document.querySelectorAll(".training-program-record-delete").forEach((button) => {
      button.addEventListener("click", async () => {
        const feedbackEl = document.getElementById("training-program-feedback");
        if (!confirmAction({
          title: "Excluir este registro de treinamento?",
          subject: button.dataset.recordLabel || "Registro selecionado",
          consequence: "O registro e seus vínculos deixam de aparecer na lista do tripulante.",
        })) return;
        await withActionBusy(button, "Excluindo...", async () => {
          try {
            await api(`/api/v1/treinamentos-tripulantes/${button.dataset.recordId}`, { method: "DELETE" });
            showFlash("Registro excluído com sucesso.", "success");
            await renderTreinamentosListPage();
          } catch (error) {
            renderInlineFeedback(feedbackEl, buildErrorMessage(error), "error");
          }
        });
      });
    });

    if (!template) return;

    const batchForm = document.getElementById("training-program-batch-form");
    const segmentCheckboxes = Array.from(document.querySelectorAll(".training-segment-checkbox"));
    const continueButton = document.getElementById("trainingProgramContinueButton");
    const selectionFeedback = document.getElementById("trainingProgramSelectionFeedback");
    let detailsUnlocked = false;
    let batchDraft = null;

    function batchDraftBaselineFields() {
      return (template.segmentos || []).reduce((acc, segment) => {
        const segmentId = String(segment.id);
        acc[`segmento_${segmentId}`] = false;
        acc[`data_realizacao_${segmentId}`] = "";
        acc[`observacao_${segmentId}`] = "";
        if (template.ctac_required) {
          acc[`ctac_solo_horas_${segmentId}`] = "";
          acc[`ctac_voo_pic_sic_horas_${segmentId}`] = "";
          acc[`ctac_voo_crew_horas_${segmentId}`] = "";
        }
        return acc;
      }, {});
    }

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
      batchDraft?.clear({ reason: "manual_reset" });
      setSelectionFeedback("Seleção de segmentos limpa.", "success");
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
    const batchDraftFields = batchDraftBaselineFields();
    batchDraft = wireCriticalFormDraftProtection({
      form: batchForm,
      formKey: `treinamentos:batch:${filters.tripulante_id || "none"}:${filters.tipo_treinamento_id || "none"}:${filters.aeronave_modelo || "none"}`,
      baselineFields: batchDraftFields,
      includeFields: Object.keys(batchDraftFields),
      feedbackTarget: selectionFeedback,
      restoreMessage: "Rascunho local recuperado. PDFs devem ser selecionados novamente antes de salvar.",
    });
    if (segmentCheckboxes.some((checkbox) => checkbox.checked)) {
      detailsUnlocked = true;
      segmentCheckboxes.forEach((checkbox) => syncSegmentCard(checkbox.dataset.segmentId));
    }
    syncSelectedState();

    batchForm?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const submitButton = batchForm.querySelector('.training-submit-bar button[type="submit"]');
      await withActionBusy(submitButton, "Salvando segmentos...", async () => {
        try {
        const selectedSegments = segmentCheckboxes.filter((checkbox) => checkbox.checked);
        if (!selectedSegments.length) {
          setSelectionFeedback("Selecione ao menos um segmento para salvar.", "error");
          return;
        }
        const segmentPayload = [];
        for (const checkbox of selectedSegments) {
          const segmentId = checkbox.dataset.segmentId;
          const fileInput = batchForm.querySelector(`[name="arquivo_${segmentId}"]`);
          const file = fileInput?.files?.[0] || null;
          if (file && file.type && file.type !== "application/pdf") {
            setSelectionFeedback(`O anexo do segmento ${segmentId} precisa ser PDF.`, "error");
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
        batchDraft?.clear({ reason: "save_success" });
        showFlash("Segmentos registrados com sucesso.", "success");
        await renderTreinamentosListPage();
      } catch (error) {
        setSelectionFeedback(buildErrorMessage(error), "error");
      }
      });
    });
  } catch (error) {
    const errorMessage = buildErrorMessage(error);
    showFlash(errorMessage, "error");
    renderShell(
      `<section class="panel training-program-panel ui-surface">
        <div class="empty operational-empty ui-table-state">
          <strong>Falha ao carregar a aba de treinamentos por tripulante</strong>
          <span>${escapeHtml(errorMessage)}</span>
        </div>
      </section>`,
      "Treinamentos por Tripulante",
    );
  }
}

