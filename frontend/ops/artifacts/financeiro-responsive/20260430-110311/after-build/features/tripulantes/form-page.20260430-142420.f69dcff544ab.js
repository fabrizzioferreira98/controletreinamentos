import {
  api,
  buildErrorMessage,
  capabilitySet,
  confirmAction,
  escapeAttr,
  escapeHtml,
  fileToDataUrl,
  formatDateTimeBr,
  formatFileSize,
  initialsForName,
  refreshSession,
  renderInlineFeedback,
  showFlash,
  tripulanteStatusClass,
  withActionBusy,
  wireResponsiveMasterDetail,
} from "../../lib.20260430-142420.cf58b4b4395e.js";
import { renderShell } from "../../shell.20260430-142420.eed3fe973fa2.js";
import {
  resolveTripulantePhotoUrl,
  wireTripulantePhotoFallbacks,
} from "./avatar.20260430-142420.0a864c9dac51.js";
import {
  adaptTripulantesOptionsPayload,
  assertArray,
  optionsContainBase,
} from "./data-adapters.20260430-142420.08f18946c4a4.js";
import { wireCriticalFormDraftProtection } from "../../shared/forms/draft-protection.20260430-142420.b75e9befef5d.js";

const PHOTO_ALLOWED_MIME_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
const PHOTO_MAX_BYTES = 1 * 1024 * 1024;

function renderTripulanteFilesSection(tripulanteId, files, capabilities = capabilitySet()) {
  if (!tripulanteId) {
    return `
      <section class="panel tripulante-document-panel ui-surface ui-stack">
        <div class="hint ui-field-help">Salve o tripulante primeiro para habilitar anexos PDF.</div>
      </section>
    `;
  }
  const activeFiles = files.filter((item) => item.status !== "removido");
  const primaryFile = activeFiles.find((item) => item.status === "ativo") || activeFiles[0] || null;
  const canReplace = capabilities.has("tripulantes_file:replace") && activeFiles.some((item) => item.status === "ativo");
  const canDelete = capabilities.has("tripulantes_file:delete");
  const statusClass = (status) => {
    if (status === "ativo") return "status-green";
    if (status === "substituido") return "status-yellow";
    if (status === "removido") return "status-dark";
    return "status-gray";
  };
  const fileTypeLabel = (item) => item.tipo_documento || item.mime_type || "application/pdf";
  const fileStatusLabel = (item) => item.status_label || item.status || "-";
  const fileBlobAvailable = (item) => Boolean(item?.blob_available);
  const canOpenFileBlob = (item) => item?.status !== "removido" && fileBlobAvailable(item);
  const fileAvailabilityLabel = (item) => {
    if (item?.status === "removido") return "Registro removido";
    if (fileBlobAvailable(item)) return "Arquivo disponível";
    if (item?.blob_status === "missing_blob") return "Arquivo indisponível";
    return "Disponibilidade não confirmada";
  };
  const fileAvailabilityTone = (item) => {
    if (item?.status === "removido") return "removed";
    if (fileBlobAvailable(item)) return "ready";
    if (item?.blob_status === "missing_blob") return "unavailable";
    return "unknown";
  };
  const fileAvailabilityMessage = (item) => {
    if (fileBlobAvailable(item)) return "Arquivo salvo e disponível para visualização.";
    if (item?.blob_status === "missing_blob") {
      return "O registro existe, mas o arquivo não está acessível no armazenamento atual. Visualização e download foram bloqueados.";
    }
    return "Não foi possível confirmar a disponibilidade do arquivo. Visualização e download foram bloqueados.";
  };
  const fileNoteLabel = (item) => {
    const notes = [];
    if (item.substitui_arquivo_id) notes.push(`Substitui #${item.substitui_arquivo_id}`);
    if (item.motivo_status) notes.push(item.motivo_status);
    return notes.join(" - ") || "Sem observações adicionais.";
  };
  const primaryCanOpen = canOpenFileBlob(primaryFile);
  const previewMarkup = primaryFile
    ? `
      <div class="document-detail-shell document-preview-card ui-surface" id="tripulanteDocumentPreview" data-preview-state="${primaryCanOpen ? "ready" : "unavailable"}">
        <div class="document-detail-header">
          <span class="eyebrow">Documento selecionado</span>
          <h3 id="tripulanteDocumentPreviewName">${escapeHtml(primaryFile.nome_original)}</h3>
          <p id="tripulanteDocumentPreviewDescription">
            ${escapeHtml(fileTypeLabel(primaryFile))} - ${escapeHtml(formatFileSize(primaryFile.tamanho_bytes))} - ${escapeHtml(fileStatusLabel(primaryFile))}
          </p>
        </div>
        <dl class="document-detail-facts">
          <div>
            <dt>Tipo</dt>
            <dd id="tripulanteDocumentDetailType">${escapeHtml(fileTypeLabel(primaryFile))}</dd>
          </div>
          <div>
            <dt>Tamanho</dt>
            <dd id="tripulanteDocumentDetailSize">${escapeHtml(formatFileSize(primaryFile.tamanho_bytes))}</dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd id="tripulanteDocumentDetailStatus">${escapeHtml(fileStatusLabel(primaryFile))}</dd>
          </div>
          <div>
            <dt>Enviado em</dt>
            <dd id="tripulanteDocumentDetailSentAt">${escapeHtml(formatDateTimeBr(primaryFile.enviado_em))}</dd>
          </div>
          <div class="document-detail-fact-full">
            <dt>Histórico</dt>
            <dd id="tripulanteDocumentDetailNote">${escapeHtml(fileNoteLabel(primaryFile))}</dd>
          </div>
        </dl>
        <div class="document-detail-actions ui-detail-actions">
          <a id="tripulanteDocumentPreviewOpen" href="${escapeAttr(primaryCanOpen ? primaryFile.links?.self || "#" : "#")}" target="_blank" rel="noopener noreferrer" ${primaryCanOpen ? "" : 'aria-disabled="true" tabindex="-1"'}>Abrir em nova aba</a>
          <a id="tripulanteDocumentPreviewDownload" href="${escapeAttr(primaryCanOpen ? primaryFile.links?.download || "#" : "#")}" target="_blank" rel="noopener noreferrer" ${primaryCanOpen ? "" : 'aria-disabled="true" tabindex="-1"'}>Baixar PDF</a>
          ${
            canDelete
              ? `<button type="button" class="link-danger" id="tripulanteDocumentDelete" data-file-id="${escapeAttr(primaryFile.id)}" data-file-name="${escapeAttr(primaryFile.nome_original)}">Excluir documento</button>`
              : ""
          }
        </div>
        <div class="upload-state compact ui-form-upload-state" id="tripulanteDocumentPreviewState" aria-live="polite" data-kind="${primaryCanOpen ? "ready" : "warning"}">
          ${escapeHtml(fileAvailabilityMessage(primaryFile))}
        </div>
        <div class="document-preview-frame" id="tripulanteDocumentPreviewFrameWrap" ${primaryCanOpen ? "" : "hidden"}>
          <iframe
            id="tripulanteDocumentPreviewFrame"
            src=""
            data-preview-url="${escapeAttr(primaryCanOpen ? primaryFile.links?.self || "" : "")}"
            title="Visualização do documento ${escapeAttr(primaryFile.nome_original)}"
            loading="lazy"
          ></iframe>
        </div>
        <div class="document-preview-fallback" id="tripulanteDocumentPreviewFallback" ${primaryCanOpen ? "hidden" : ""}>
          <strong>${escapeHtml(fileAvailabilityLabel(primaryFile))}</strong>
          <span>${escapeHtml(fileAvailabilityMessage(primaryFile))}</span>
        </div>
      </div>
    `
    : `
      <div class="document-detail-shell document-preview-card document-preview-empty ui-surface" id="tripulanteDocumentPreview" data-preview-state="empty">
        <div class="document-detail-header">
          <span class="eyebrow">Documento selecionado</span>
          <h3 id="tripulanteDocumentPreviewName">Nenhum PDF selecionado</h3>
          <p id="tripulanteDocumentPreviewDescription">Escolha um item da biblioteca para ver detalhes, disponibilidade e visualização.</p>
        </div>
        <dl class="document-detail-facts">
          <div>
            <dt>Tipo</dt>
            <dd id="tripulanteDocumentDetailType">-</dd>
          </div>
          <div>
            <dt>Tamanho</dt>
            <dd id="tripulanteDocumentDetailSize">-</dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd id="tripulanteDocumentDetailStatus">-</dd>
          </div>
          <div>
            <dt>Enviado em</dt>
            <dd id="tripulanteDocumentDetailSentAt">-</dd>
          </div>
          <div class="document-detail-fact-full">
            <dt>Histórico</dt>
            <dd id="tripulanteDocumentDetailNote">Nenhum documento selecionado.</dd>
          </div>
        </dl>
        <div class="document-detail-actions ui-detail-actions">
          <a id="tripulanteDocumentPreviewOpen" href="#" target="_blank" rel="noopener noreferrer" aria-disabled="true">Abrir em nova aba</a>
          <a id="tripulanteDocumentPreviewDownload" href="#" target="_blank" rel="noopener noreferrer" aria-disabled="true">Baixar PDF</a>
          ${canDelete ? '<button type="button" class="link-danger" id="tripulanteDocumentDelete" disabled>Excluir documento</button>' : ""}
        </div>
        <div class="upload-state compact ui-form-upload-state" id="tripulanteDocumentPreviewState" aria-live="polite">
          Selecione um documento na biblioteca para abrir o painel de detalhe.
        </div>
        <div class="document-preview-fallback" id="tripulanteDocumentPreviewFallback">
          <strong>Nenhum PDF selecionado para visualização.</strong>
          <span>Quando um documento for anexado, a visualização e os metadados aparecerão no painel de detalhe.</span>
        </div>
      </div>
    `;

  return `
    <section class="panel entity-document-panel tripulante-document-panel ui-surface ui-stack" data-tripulante-section="documents">
      <div class="page-header ui-block-end-sm">
        <div>
          <h2 class="ui-heading-reset">Documentos do tripulante</h2>
          <p class="page-subtitle ui-subtitle-compact">Arquivos PDF vinculados ao cadastro.</p>
        </div>
      </div>

      <form id="tripulante-file-form" class="filters filters-wide document-upload-form ui-form-toolbar tripulante-document-upload ui-block-end-sm">
        <div class="tripulante-document-upload-header">
          <h3 class="ui-heading-reset">Adicionar documento PDF</h3>
          <p class="field-help ui-field-help">Envie um novo PDF ou substitua intencionalmente um documento ativo.</p>
        </div>
        <div class="tripulante-document-upload-meta ui-form-grid ui-form-density-compact">
          <label>
            Tipo de documento
            <input type="text" name="tipo_documento" placeholder="Ex.: CMA, contrato, comprovante">
          </label>
          ${
            canReplace
              ? `
                <label>
                  Modo de envio
                  <select name="substitui_arquivo_id" id="tripulanteFileReplaceSelect" aria-describedby="tripulanteFileUploadState">
                    <option value="">Novo documento</option>
                    ${activeFiles
                      .filter((item) => item.status === "ativo")
                      .map((item) => `<option value="${escapeAttr(item.id)}">Substituir: ${escapeHtml(item.nome_original)}</option>`)
                      .join("")}
                  </select>
                  <span class="field-help ui-field-help">Escolha se este PDF cria um novo registro ou substitui um documento ativo.</span>
                </label>
              `
              : ""
          }
        </div>
        <div class="tripulante-document-upload-intake ui-form-upload-grid" data-upload-layout="single">
          <label class="document-upload-input ui-form-upload-field">
            PDF do tripulante
            <input type="file" name="arquivo_pdf" id="tripulanteFileInput" accept="application/pdf" required aria-describedby="tripulanteFileUploadState">
            <span class="field-help ui-field-help">Limite por arquivo: 20 MB. Apenas PDF.</span>
          </label>
          <button type="submit" id="tripulanteFileSubmit">Anexar PDF</button>
        </div>
        <div class="upload-state ui-form-upload-state tripulante-document-upload-state" id="tripulanteFileUploadState" aria-live="polite">
          Nenhum PDF selecionado. O envio criará um novo registro de documento.
        </div>
      </form>

      <div class="document-master-detail ui-master-detail ui-panel-offset-sm" id="tripulanteDocumentMasterDetail" data-master-detail-pattern="documents">
        <div class="document-master-pane ui-master-pane" id="tripulanteDocumentMaster">
      <div class="table-wrap ui-table-wrap ui-table-density-compact">
        <table class="data-table responsive-cards document-library-table">
          <thead>
            <tr>
              <th>Arquivo</th>
              <th>Status</th>
              <th>Enviado em</th>
              <th>Selecionar</th>
            </tr>
          </thead>
          <tbody>
            ${
              files
                .map(
                  (item) => `
                    <tr class="document-library-row ${primaryFile?.id === item.id ? "is-selected" : ""}" data-file-status="${escapeAttr(item.status || "")}">
                      <td data-label="Arquivo">
                          <div class="primary-cell">
                            <div class="document-library-name" title="${escapeAttr(item.nome_original)}">${escapeHtml(item.nome_original)}</div>
                            <div class="document-library-meta">${escapeHtml(fileTypeLabel(item))} - ${escapeHtml(formatFileSize(item.tamanho_bytes))}</div>
                            <div class="document-library-availability" data-availability="${escapeAttr(fileAvailabilityTone(item))}">${escapeHtml(fileAvailabilityLabel(item))}</div>
                            <div class="document-library-note">${escapeHtml(fileNoteLabel(item))}</div>
                          </div>
                        </td>
                      <td data-label="Status"><span class="status-pill ${statusClass(item.status)}">${escapeHtml(item.status_label || item.status || "-")}</span></td>
                      <td data-label="Enviado em">${escapeHtml(formatDateTimeBr(item.enviado_em))}</td>
                      <td class="actions ui-table-actions" data-label="Selecionar">
                        ${
                          item.status !== "removido"
                            ? `
                              <button
                                type="button"
                                class="button-link secondary tripulante-file-preview document-library-select ${primaryFile?.id === item.id ? "is-selected" : ""}"
                                data-preview-url="${escapeAttr(item.links?.self || "")}"
                                data-download-url="${escapeAttr(item.links?.download || "")}"
                                data-file-blob-available="${escapeAttr(String(fileBlobAvailable(item)))}"
                                data-file-availability-label="${escapeAttr(fileAvailabilityLabel(item))}"
                                data-file-availability-message="${escapeAttr(fileAvailabilityMessage(item))}"
                                data-file-name="${escapeAttr(item.nome_original)}"
                                data-file-id="${escapeAttr(item.id)}"
                                data-file-type="${escapeAttr(fileTypeLabel(item))}"
                                data-file-size="${escapeAttr(formatFileSize(item.tamanho_bytes))}"
                                data-file-status="${escapeAttr(fileStatusLabel(item))}"
                                data-file-sent-at="${escapeAttr(formatDateTimeBr(item.enviado_em))}"
                                data-file-note="${escapeAttr(fileNoteLabel(item))}"
                                data-file-meta="${escapeAttr(`${fileTypeLabel(item)} - ${formatFileSize(item.tamanho_bytes)} - ${fileStatusLabel(item)}`)}"
                                data-master-detail-key="${escapeAttr(String(item.id))}"
                                data-detail-target="tripulanteDocumentPreview"
                              >${primaryFile?.id === item.id ? "Selecionado" : "Selecionar"}</button>
                            `
                                : '<span class="secondary-cell">Sem visualização</span>'
                        }
                      </td>
                    </tr>
                  `,
                )
                .join("") || '<tr><td colspan="4" class="empty ui-table-state">Nenhum PDF anexado a este tripulante. Use o upload acima quando houver documento comprobatório.</td></tr>'
            }
          </tbody>
        </table>
      </div>
        </div>
        <div class="document-detail-pane ui-detail-pane" id="tripulanteDocumentDetailPane" data-detail-sticky="true" tabindex="-1">
          <button type="button" class="button-link secondary ui-detail-back document-preview-back" id="tripulanteDocumentPreviewBack">Voltar para documentos</button>
          ${previewMarkup}
        </div>
      </div>
    </section>
  `;
}

export async function renderTripulanteFormPage(tripulanteId = null) {
  try {
    const detailPromise = tripulanteId ? api(`/api/v1/tripulantes/${tripulanteId}`) : Promise.resolve({ data: { tripulante: null } });
    const filesPromise = tripulanteId ? api(`/api/v1/tripulantes/${tripulanteId}/files`) : Promise.resolve({ data: { items: [] } });
    const defaultOptionsPromise = api("/api/v1/tripulantes/options");
    const [detailPayload, filesPayload, defaultOptionsResponse] = await Promise.all([
      detailPromise,
      filesPromise,
      defaultOptionsPromise,
    ]);
    const tripulante = detailPayload.data.tripulante;
    const files = assertArray(filesPayload.data?.items, "tripulantes.files");
    let options = adaptTripulantesOptionsPayload(defaultOptionsResponse.data);
    if (tripulante?.base && !optionsContainBase(options, tripulante.base)) {
      const selectedBaseOptionsResponse = await api(`/api/v1/tripulantes/options?base=${encodeURIComponent(tripulante.base)}`);
      options = adaptTripulantesOptionsPayload(selectedBaseOptionsResponse.data);
    }
    const photoUrl = resolveTripulantePhotoUrl(tripulante);
    const photoStateMessage = photoUrl
      ? "Foto vinculada ao tripulante."
      : "Sem foto vinculada.";
    const capabilities = capabilitySet();

    renderShell(
      `
        <div class="tripulante-detail-page-shell priority-page-surface ui-page-shell ui-stack">
        <div class="page-header entity-detail-header priority-page-header ui-page-header ui-surface">
          <div>
            <h1>${tripulanteId ? "Atualizar dados do tripulante" : "Cadastrar novo tripulante"}</h1>
            <p class="page-subtitle">${tripulanteId ? "Detalhe e edição compartilham o mesmo contexto operacional." : "Crie o cadastro e depois anexe documentos PDF."}</p>
            <div class="entity-status-row ui-cluster">
              <span class="status-pill ${tripulanteStatusClass(tripulante?.status || "ativo")}">${escapeHtml(tripulante?.status || "novo cadastro")}</span>
              <span class="status-pill ${tripulante?.ativo === false ? "status-gray" : "status-green"}">${tripulante?.ativo === false ? "Indisponível na operação" : "Disponível para operação"}</span>
              ${tripulanteId ? `<span class="status-pill status-gray">${files.length} PDF${files.length === 1 ? "" : "s"} anexado${files.length === 1 ? "" : "s"}</span>` : ""}
            </div>
          </div>
          <div class="page-header-actions">
            <a class="button-link secondary" href="#/tripulantes">Voltar para a lista</a>
          </div>
        </div>

        <div id="tripulante-form-feedback" aria-live="polite"></div>

        <form id="tripulante-form" class="form-grid entity-form-grid tripulante-entity-form ui-form-grid" novalidate>
          <section class="form-section entity-form-section ui-surface ui-stack ui-form-section" data-tripulante-section="identity">
            <div class="form-section-header">
              <h2>Identificação</h2>
              <p>Dados usados para localizar, validar e acionar o tripulante.</p>
              <div class="section-feedback ui-field-help" id="tripulanteIdentitySectionFeedback" aria-live="polite"></div>
            </div>
            <div class="form-grid form-grid-compact ui-form-grid ui-form-density-compact">
              <label>Nome<input type="text" name="nome" id="tripulanteNome" value="${escapeAttr(tripulante?.nome || "")}" required aria-describedby="tripulanteNomeFeedback"><span class="field-feedback ui-field-help" id="tripulanteNomeFeedback" aria-live="polite"></span></label>
              <label>CPF<input type="text" name="cpf" id="tripulanteCpf" value="${escapeAttr(tripulante?.cpf || "")}" inputmode="numeric" maxlength="14" placeholder="000.000.000-00" required aria-describedby="tripulanteCpfFeedback"><span class="field-feedback ui-field-help" id="tripulanteCpfFeedback" aria-live="polite"></span></label>
              <label>Código ANAC<input type="text" name="licenca_anac" id="tripulanteAnac" value="${escapeAttr(tripulante?.licenca_anac || "")}" inputmode="numeric" maxlength="6" placeholder="000000" required aria-describedby="tripulanteAnacFeedback"><span class="field-feedback ui-field-help" id="tripulanteAnacFeedback" aria-live="polite"></span></label>
              <label>E-mail<input type="email" name="email" id="tripulanteEmail" value="${escapeAttr(tripulante?.email || "")}" maxlength="254" placeholder="tripulante@empresa.com" aria-describedby="tripulanteEmailFeedback"><span class="field-feedback ui-field-help" id="tripulanteEmailFeedback" aria-live="polite"></span></label>
              <label>Telefone / WhatsApp<input type="text" name="telefone" id="tripulanteTelefone" value="${escapeAttr(tripulante?.telefone || "")}" inputmode="tel" maxlength="16" placeholder="(91) 99999-9999" aria-describedby="tripulanteTelefoneFeedback"><span class="field-feedback ui-field-help" id="tripulanteTelefoneFeedback" aria-live="polite"></span></label>
            </div>
          </section>
          <section class="form-section entity-form-section ui-surface ui-stack ui-form-section" data-tripulante-section="operation">
            <div class="form-section-header">
              <h2>Operação</h2>
              <p>Status, base e fun&ccedil;&atilde;o que impactam escala e relat&oacute;rios.</p>
              <div class="section-feedback ui-field-help" id="tripulanteOperationSectionFeedback" aria-live="polite"></div>
            </div>
            <div class="form-grid form-grid-compact ui-form-grid ui-form-density-compact">
          <label>
            Base
            <select name="base" id="tripulanteBase" required aria-describedby="tripulanteBaseFeedback">
              <option value="">Selecione</option>
              ${options.bases
                .map((item) => `<option value="${escapeAttr(item.nome)}" ${tripulante?.base === item.nome ? "selected" : ""}>${escapeHtml(item.uf ? `${item.nome} / ${item.uf}` : item.nome)}</option>`)
                .join("")}
            </select>
            <span class="field-feedback ui-field-help" id="tripulanteBaseFeedback" aria-live="polite"></span>
          </label>
          <label>
            Status
            <select name="status" id="tripulanteStatus" required aria-describedby="tripulanteStatusFeedback">
              <option value="">Selecione</option>
              ${options.status
                .map((item) => `<option value="${escapeAttr(item)}" ${tripulante?.status === item ? "selected" : ""}>${escapeHtml(item)}</option>`)
                .join("")}
            </select>
            <span class="field-feedback ui-field-help" id="tripulanteStatusFeedback" aria-live="polite"></span>
          </label>
          <label>
            Função operacional
            <select name="funcao_operacional" id="tripulanteFuncao" required aria-describedby="tripulanteFuncaoFeedback">
              ${options.funcoes
                .map((item) => `<option value="${escapeAttr(item)}" ${tripulante?.funcao_operacional === item || (!tripulante && item === "outro") ? "selected" : ""}>${escapeHtml(item)}</option>`)
                .join("")}
            </select>
            <span class="field-feedback ui-field-help" id="tripulanteFuncaoFeedback" aria-live="polite"></span>
          </label>
          <label>
            Categoria operacional
            <select name="categoria_operacional" id="tripulanteCategoria" required aria-describedby="tripulanteCategoriaFeedback">
              ${options.categorias
                .map((item) => `<option value="${escapeAttr(item)}" ${tripulante?.categoria_operacional === item || (!tripulante && item === "N/A") ? "selected" : ""}>${escapeHtml(item)}</option>`)
                .join("")}
            </select>
            <span class="field-feedback ui-field-help" id="tripulanteCategoriaFeedback" aria-live="polite"></span>
            <span class="field-help ui-field-help">
              <strong>Legenda de porte:</strong><br>
              A - C525 ou aeronave do mesmo porte.<br>
              B - LRJ serie 30, C560, LRJ45, WW, G100 ou aeronave do mesmo porte.
            </span>
          </label>
            </div>
          </section>
          <section class="full-width flags-section entity-form-section ui-surface ui-stack ui-form-section" data-tripulante-section="eligibility">
            <div class="flags-section-header">
              <h2>Elegibilidade operacional</h2>
              <p>Defina rapidamente os indicadores que impactam c&aacute;lculo e escala.</p>
            </div>
            <div class="flags-grid">
              <label class="checkbox-field"><span class="checkbox-label-group"><span class="checkbox-title">Tripulante ativo</span><span class="checkbox-description">Controla disponibilidade geral no sistema.</span></span><span class="toggle-switch"><input type="checkbox" name="ativo" ${!tripulante || tripulante.ativo ? "checked" : ""}><span class="toggle-slider" aria-hidden="true"></span><span class="toggle-text">${!tripulante || tripulante.ativo ? "Ativo" : "Inativo"}</span></span></label>
              <label class="checkbox-field"><span class="checkbox-label-group"><span class="checkbox-title">SDEA ativo</span><span class="checkbox-description">Aplica adicional mensal de idioma quando habilitado.</span></span><span class="toggle-switch"><input type="checkbox" name="sdea_ativo" ${tripulante?.sdea_ativo ? "checked" : ""}><span class="toggle-slider" aria-hidden="true"></span><span class="toggle-text">${tripulante?.sdea_ativo ? "Ativo" : "Inativo"}</span></span></label>
              <label class="checkbox-field"><span class="checkbox-label-group"><span class="checkbox-title">Instrutor designado</span><span class="checkbox-description">Considera adicional fixo de instrutoria na competencia.</span></span><span class="toggle-switch"><input type="checkbox" name="instrutor_ativo" ${tripulante?.instrutor_ativo ? "checked" : ""}><span class="toggle-slider" aria-hidden="true"></span><span class="toggle-text">${tripulante?.instrutor_ativo ? "Ativo" : "Inativo"}</span></span></label>
              <label class="checkbox-field"><span class="checkbox-label-group"><span class="checkbox-title">Checador designado</span><span class="checkbox-description">Considera adicional fixo de checagem na competencia.</span></span><span class="toggle-switch"><input type="checkbox" name="checador_ativo" ${tripulante?.checador_ativo ? "checked" : ""}><span class="toggle-slider" aria-hidden="true"></span><span class="toggle-text">${tripulante?.checador_ativo ? "Ativo" : "Inativo"}</span></span></label>
              <label class="checkbox-field"><span class="checkbox-label-group"><span class="checkbox-title">Elegivel para adicional excepcional</span><span class="checkbox-description">Permite aplicar valor excepcional parametrizado ou manual.</span></span><span class="toggle-switch"><input type="checkbox" name="elegivel_adicional_excepcional" ${tripulante?.elegivel_adicional_excepcional ? "checked" : ""}><span class="toggle-slider" aria-hidden="true"></span><span class="toggle-text">${tripulante?.elegivel_adicional_excepcional ? "Ativo" : "Inativo"}</span></span></label>
            </div>
          </section>
          <section class="form-section entity-form-section ui-surface ui-stack ui-form-section" data-tripulante-section="media">
            <div class="form-section-header">
              <h2>Arquivos visuais e observações</h2>
              <p>Informações de apoio que completam o cadastro sem competir com a operação principal.</p>
            </div>
            <div class="tripulante-photo-field">
              <div class="tripulante-photo-preview-card ui-surface">
                <div class="tripulante-photo-preview" id="tripulantePhotoPreview">
                  ${
                    photoUrl
                      ? `<img class="tripulante-photo-img" src="${escapeAttr(photoUrl)}" alt="${escapeAttr(tripulante?.nome || "Tripulante")}" data-photo-fallback="initials" data-initials="${escapeAttr(initialsForName(tripulante?.nome || ""))}" data-photo-state-target="tripulantePhotoState">`
                      : `<span>${escapeHtml(initialsForName(tripulante?.nome || ""))}</span>`
                  }
                </div>
                <div class="tripulante-photo-meta">
                  <div class="checkbox-title">Foto do tripulante</div>
                  <div class="checkbox-description">Envie JPG, PNG ou WEBP. A imagem será exibida no cadastro, relatório e gestão de bases.</div>
                  <div class="upload-state compact ui-form-upload-state" id="tripulantePhotoState" aria-live="polite" data-kind="${photoUrl ? "ready" : ""}">${photoStateMessage}</div>
                </div>
              </div>
              <div class="tripulante-photo-actions">
                <input type="file" id="tripulantePhotoInput" accept="image/png,image/jpeg,image/webp" aria-label="Foto do tripulante" aria-describedby="tripulantePhotoState">
                <button type="button" class="button-link secondary" id="tripulantePhotoUpload" ${tripulanteId ? "" : "disabled"}>Enviar foto</button>
                <button type="button" class="button-link secondary" id="tripulantePhotoRemove" ${tripulanteId ? "" : "disabled"}>Remover foto</button>
              </div>
            </div>
            <label class="full-width ui-form-field-long">Observações<textarea name="observacoes" rows="4">${escapeHtml(tripulante?.observacoes || "")}</textarea></label>
          </section>
          <div class="form-actions full-width entity-sticky-actions ui-form-actions ui-form-sticky-actions">
            <button type="submit" id="tripulanteFormSubmit">Salvar alterações</button>
            ${tripulanteId && capabilities.has("tripulantes:delete") ? '<button type="button" class="button-link secondary" id="tripulanteDeleteButton">Excluir tripulante</button>' : ""}
            <a class="button-link secondary" href="#/tripulantes">Voltar sem salvar</a>
          </div>
        </form>

        ${renderTripulanteFilesSection(tripulanteId, files, capabilities)}
        </div>
      `,
      tripulanteId ? "Editar Tripulante" : "Novo Tripulante",
    );
    wireTripulantePhotoFallbacks();

    const photoInput = document.getElementById("tripulantePhotoInput");
    const photoPreview = document.getElementById("tripulantePhotoPreview");
    const nameInput = document.querySelector("input[name='nome']");
    const cpfInput = document.getElementById("tripulanteCpf");
    const anacInput = document.getElementById("tripulanteAnac");
    const phoneInput = document.getElementById("tripulanteTelefone");
    const formFeedback = document.getElementById("tripulante-form-feedback");
    const photoState = document.getElementById("tripulantePhotoState");
    const documentInput = document.getElementById("tripulanteFileInput");
    const documentState = document.getElementById("tripulanteFileUploadState");
    const documentReplaceSelect = document.getElementById("tripulanteFileReplaceSelect");
    const documentSubmit = document.getElementById("tripulanteFileSubmit");

    function setFieldFeedback(input, message = "", kind = "error") {
      if (!input) return true;
      const feedbackId = input.getAttribute("aria-describedby");
      const feedback = feedbackId ? document.getElementById(feedbackId) : null;
      input.setAttribute("aria-invalid", message && kind === "error" ? "true" : "false");
      if (feedback) {
        feedback.textContent = message;
        feedback.dataset.kind = message ? kind : "";
      }
      return !message || kind !== "error";
    }

    function validateRequiredInput(input, message) {
      return setFieldFeedback(input, String(input?.value || "").trim() ? "" : message);
    }

    function setUploadState(target, message, kind = "") {
      if (!target) return;
      target.textContent = message;
      target.dataset.kind = kind;
    }

    function setPhotoUploadState(message, kind = "", userUploadState = "") {
      if (userUploadState) {
        photoState.dataset.userUploadState = userUploadState;
      } else {
        delete photoState.dataset.userUploadState;
      }
      setUploadState(photoState, message, kind);
    }

    function appendPhotoRequestCode(message, error) {
      const requestId = String(error?.requestId || "").trim();
      return requestId ? `${message} Codigo: ${requestId}` : message;
    }

    function classifyPhotoSelection(file) {
      if (!file) {
        return {
          ok: false,
          cause: "empty",
          stateMessage: "Nenhuma nova foto selecionada.",
          formMessage: "Selecione uma foto antes de enviar.",
          kind: "error",
        };
      }
      if (!PHOTO_ALLOWED_MIME_TYPES.has(file.type)) {
        return {
          ok: false,
          cause: "format",
          stateMessage: "Formato não aceito. Use JPG, PNG ou WEBP.",
          formMessage: "Envie uma imagem JPG, PNG ou WEBP.",
          kind: "error",
        };
      }
      if (!file.size) {
        return {
          ok: false,
          cause: "validation",
          stateMessage: "Arquivo vazio. Selecione uma foto valida.",
          formMessage: "O arquivo selecionado esta vazio. Escolha uma foto valida.",
          kind: "error",
        };
      }
      if (file.size > PHOTO_MAX_BYTES) {
        return {
          ok: false,
          cause: "size",
          stateMessage: `Arquivo muito grande: ${formatFileSize(file.size)}. Limite: ${formatFileSize(PHOTO_MAX_BYTES)}.`,
          formMessage: `A foto excede o limite de ${formatFileSize(PHOTO_MAX_BYTES)}. Reduza o arquivo e tente novamente.`,
          kind: "error",
        };
      }
      return {
        ok: true,
        cause: "ready",
        stateMessage: `${file.name} - ${formatFileSize(file.size)} - pré-visualização local; ainda não salva.`,
        formMessage: "",
        kind: "ready",
      };
    }

    function classifyPhotoUploadFailure(error, file) {
      const code = String(error?.code || "").trim();
      const status = Number(error?.status || 0);
      const rawMessage = String(error?.message || "");
      const name = file?.name || "Foto selecionada";
      const localSelection = classifyPhotoSelection(file);

      if (!code && rawMessage.includes("Falha ao ler arquivo")) {
        return {
          cause: "local_read",
          stateMessage: `${name} - arquivo local não pode ser lido.`,
          formMessage: "Nao foi possivel ler o arquivo local selecionado. Escolha a foto novamente.",
          kind: "error",
        };
      }
      if (code === "network_error" || code === "timeout") {
        return {
          cause: "network",
          stateMessage: `${name} - falha de rede; envio não confirmado.`,
          formMessage: appendPhotoRequestCode("Não foi possível conectar ao servidor. A foto não foi salva.", error),
          kind: "error",
        };
      }
      if (code === "csrf_error") {
        return {
          cause: "csrf",
          stateMessage: `${name} - sessão/CSRF inconsistente; envio não confirmado.`,
          formMessage: appendPhotoRequestCode("Sua sessão ficou inconsistente. Atualize a página e tente enviar novamente.", error),
          kind: "error",
        };
      }
      if (status === 401 || ["auth_required", "auth_session_expired", "auth_session_invalid"].includes(code)) {
        return {
          cause: "auth",
          stateMessage: `${name} - sessão expirada; envio não confirmado.`,
          formMessage: appendPhotoRequestCode("Sua sessão expirou. Entre novamente antes de enviar a foto.", error),
          kind: "error",
        };
      }
      if (status === 403 || code === "forbidden") {
        return {
          cause: "permission",
          stateMessage: `${name} - sem permissão para alterar foto.`,
          formMessage: appendPhotoRequestCode("Seu usuário não tem permissão para alterar a foto deste tripulante.", error),
          kind: "error",
        };
      }
      if (code === "tripulante_photo_blob_unavailable" || code === "unavailable" || status === 503) {
        return {
          cause: "storage",
          stateMessage: `${name} - armazenamento não confirmou a foto; envio revertido.`,
          formMessage: appendPhotoRequestCode("O servidor não confirmou a leitura da foto gravada. Nenhuma troca foi marcada como salva.", error),
          kind: "error",
        };
      }
      if (code === "tripulante_invalid_photo" || status === 400) {
        if (!localSelection.ok && ["format", "size", "validation"].includes(localSelection.cause)) {
          return {
            ...localSelection,
            stateMessage: `${name} - ${localSelection.stateMessage}`,
            formMessage: appendPhotoRequestCode(localSelection.formMessage, error),
          };
        }
        return {
          cause: "validation",
          stateMessage: `${name} - rejeitada pela validação do servidor.`,
          formMessage: appendPhotoRequestCode("O backend rejeitou o conteudo da imagem. Envie uma foto real em JPG, PNG ou WEBP.", error),
          kind: "error",
        };
      }
      if (code === "tripulante_photo_unconfirmed") {
        return {
          cause: "unconfirmed_success",
          stateMessage: `${name} - resposta sem confirmação de foto disponível.`,
          formMessage: "O servidor respondeu sem confirmar que a foto ficou disponível. O painel não aplicou sucesso.",
          kind: "warning",
        };
      }
      if (code === "invalid_json") {
        return {
          cause: "unexpected_response",
          stateMessage: `${name} - resposta inesperada; envio não confirmado.`,
          formMessage: appendPhotoRequestCode("O servidor retornou uma resposta inesperada. A foto não foi marcada como salva.", error),
          kind: "error",
        };
      }
      if (status >= 500) {
        return {
          cause: "unexpected",
          stateMessage: `${name} - erro inesperado no servidor; envio não confirmado.`,
          formMessage: appendPhotoRequestCode("Erro inesperado ao salvar a foto. Tente novamente e acione o suporte se persistir.", error),
          kind: "error",
        };
      }
      return {
        cause: "unexpected",
        stateMessage: `${name} - falha não classificada; envio não confirmado.`,
        formMessage: appendPhotoRequestCode("Nao foi possivel concluir o envio da foto. Tente novamente e acione o suporte se persistir.", error),
        kind: "error",
      };
    }

    function revertPhotoPreviewToPersisted() {
      renderPhotoPreview(photoUrl || "");
    }

    function assertPhotoUploadConfirmed(result) {
      const photo = result?.data?.photo || {};
      if (result?.data?.success && photo.has_photo && photo.photo_url) return photo;
      const error = new Error("Upload de foto sem confirmacao de disponibilidade.");
      error.code = "tripulante_photo_unconfirmed";
      error.status = result?.response?.status || result?.data?.status || 200;
      throw error;
    }

    function setSectionFeedback(id, message = "", kind = "error") {
      const target = document.getElementById(id);
      if (!target) return;
      target.textContent = message;
      target.dataset.kind = message ? kind : "";
    }

    function validatePdfFile(file, target) {
      if (!file) {
        setUploadState(target, "Selecione um PDF antes de anexar.", "error");
        return false;
      }
      if (file.type !== "application/pdf" && !String(file.name || "").toLowerCase().endsWith(".pdf")) {
        setUploadState(target, "Arquivo inválido. Envie apenas PDF.", "error");
        return false;
      }
      if (file.size > 20 * 1024 * 1024) {
        setUploadState(target, "Arquivo maior que 20 MB. Escolha um PDF menor.", "error");
        return false;
      }
      return true;
    }

    function describeDocumentReplaceMode() {
      const replacing = Boolean(documentReplaceSelect?.value);
      const selectedOption = documentReplaceSelect?.selectedOptions?.[0];
      const selectedLabel = String(selectedOption?.textContent || "Documento selecionado")
        .replace(/^Substituir:\s*/i, "")
        .trim();
      return replacing
        ? {
            replacing: true,
            idleMessage: `Nenhum PDF selecionado. Ao anexar, ${selectedLabel} será marcado como substituído.`,
            readyHint: `substituição selecionada de ${selectedLabel}`,
          }
        : {
            replacing: false,
            idleMessage: "Nenhum PDF selecionado. O envio criará um novo registro de documento.",
            readyHint: "novo registro de documento",
          };
    }

    function renderDocumentUploadIdleState() {
      const mode = describeDocumentReplaceMode();
      setUploadState(documentState, mode.idleMessage, mode.replacing ? "warning" : "");
    }

    function renderDocumentUploadReadyState(file) {
      if (!file) return;
      const mode = describeDocumentReplaceMode();
      setUploadState(
        documentState,
        `${file.name} - ${formatFileSize(file.size)} - ${file.type || "application/pdf"} - ${mode.replacing ? "pronto para substituir" : "pronto para anexar"} (${mode.readyHint})`,
        "ready",
      );
    }

    function syncDocumentUploadMode() {
      const mode = describeDocumentReplaceMode();
      if (documentSubmit) documentSubmit.textContent = mode.replacing ? "Substituir PDF" : "Anexar PDF";
      const file = documentInput?.files?.[0];
      if (!file) {
        renderDocumentUploadIdleState();
        return;
      }
      if (validatePdfFile(file, documentState)) renderDocumentUploadReadyState(file);
    }

    async function runWithCsrfRetry(requestAction) {
      try {
        return await requestAction();
      } catch (error) {
        if (error?.code !== "csrf_error") throw error;
        await refreshSession();
        return requestAction();
      }
    }

    function setDocumentDetailLink(link, href) {
      if (!link) return;
      const resolved = String(href || "").trim();
      if (!resolved) {
        link.href = "#";
        link.setAttribute("aria-disabled", "true");
        link.setAttribute("tabindex", "-1");
        return;
      }
      link.href = resolved;
      link.removeAttribute("aria-disabled");
      link.removeAttribute("tabindex");
    }

    let currentDocumentPreviewObjectUrl = "";

    function clearDocumentPreviewObjectUrl() {
      if (!currentDocumentPreviewObjectUrl) return;
      URL.revokeObjectURL(currentDocumentPreviewObjectUrl);
      currentDocumentPreviewObjectUrl = "";
    }

    function renderDocumentPreviewFallback(fallback, label, message) {
      if (!fallback) return;
      fallback.hidden = false;
      fallback.innerHTML = `
        <strong>${escapeHtml(label || "Arquivo indisponível")}</strong>
        <span>${escapeHtml(message || "O registro existe, mas o arquivo não está acessível no armazenamento atual. Visualização e download foram bloqueados.")}</span>
      `;
    }

    async function loadDocumentPreviewBlob({ url, titleText, frame, frameWrap, fallback, state }) {
      clearDocumentPreviewObjectUrl();
      if (frame) frame.src = "";
      if (frameWrap) frameWrap.hidden = true;
      if (fallback) fallback.hidden = true;
      setUploadState(state, "Carregando visualização segura do PDF...", "busy");
      try {
        const response = await fetch(url, {
          method: "GET",
          credentials: "same-origin",
          headers: { Accept: "application/pdf" },
        });
        const contentType = response.headers.get("Content-Type") || "";
        if (!response.ok || !contentType.toLowerCase().includes("application/pdf")) {
          throw new Error(`preview_unavailable_${response.status || "unknown"}`);
        }
        const blob = await response.blob();
        if (!blob.size) throw new Error("preview_empty_pdf");
        currentDocumentPreviewObjectUrl = URL.createObjectURL(blob);
        if (frame) {
          frame.src = currentDocumentPreviewObjectUrl;
          frame.title = `Visualização do documento ${titleText}`;
        }
        if (frameWrap) frameWrap.hidden = false;
        setUploadState(state, "Visualização carregada com segurança a partir do PDF autenticado.", "ready");
      } catch (_error) {
        if (frame) frame.src = "";
        if (frameWrap) frameWrap.hidden = true;
        renderDocumentPreviewFallback(
          fallback,
          "Visualização indisponível",
          "Não foi possível carregar um PDF válido para visualização. A resposta técnica foi bloqueada para não exibir erro bruto no painel.",
        );
        setUploadState(
          state,
          "Visualização indisponível. A resposta técnica não foi exibida para evitar conteúdo enganoso.",
          "warning",
        );
      }
    }

    async function renderDocumentPreview({
      url,
      downloadUrl,
      fileId,
      name,
      meta,
      type,
      size,
      status,
      sentAt,
      note,
      blobAvailable = false,
      availabilityLabel = "",
      availabilityMessage = "",
    }) {
      const previewCard = document.getElementById("tripulanteDocumentPreview");
      const frame = document.getElementById("tripulanteDocumentPreviewFrame");
      const frameWrap = document.getElementById("tripulanteDocumentPreviewFrameWrap");
      const fallback = document.getElementById("tripulanteDocumentPreviewFallback");
      const title = document.getElementById("tripulanteDocumentPreviewName");
      const description = document.getElementById("tripulanteDocumentPreviewDescription");
      const openLink = document.getElementById("tripulanteDocumentPreviewOpen");
      const downloadLink = document.getElementById("tripulanteDocumentPreviewDownload");
      const deleteButton = document.getElementById("tripulanteDocumentDelete");
      const detailType = document.getElementById("tripulanteDocumentDetailType");
      const detailSize = document.getElementById("tripulanteDocumentDetailSize");
      const detailStatus = document.getElementById("tripulanteDocumentDetailStatus");
      const detailSentAt = document.getElementById("tripulanteDocumentDetailSentAt");
      const detailNote = document.getElementById("tripulanteDocumentDetailNote");
      const state = document.getElementById("tripulanteDocumentPreviewState");
      if (!title || !description || !openLink || !downloadLink || !state) return;

      const titleText = name || "Documento PDF";
      const typeText = type || "application/pdf";
      const sizeText = size || "-";
      const statusText = status || "-";
      const sentAtText = sentAt || "-";
      const noteText = note || "Sem observações adicionais.";

      title.textContent = titleText;
      description.textContent = meta || [typeText, sizeText, statusText].filter(Boolean).join(" - ");
      if (detailType) detailType.textContent = typeText;
      if (detailSize) detailSize.textContent = sizeText;
      if (detailStatus) detailStatus.textContent = statusText;
      if (detailSentAt) detailSentAt.textContent = sentAtText;
      if (detailNote) detailNote.textContent = noteText;

      if (deleteButton) {
        const deletable = Boolean(fileId);
        deleteButton.disabled = !deletable;
        deleteButton.dataset.fileId = deletable ? String(fileId) : "";
        deleteButton.dataset.fileName = titleText;
      }

      if (!blobAvailable || !url) {
        clearDocumentPreviewObjectUrl();
        setDocumentDetailLink(openLink, "");
        setDocumentDetailLink(downloadLink, "");
        if (frame) frame.src = "";
        if (frameWrap) frameWrap.hidden = true;
        renderDocumentPreviewFallback(fallback, availabilityLabel || "Arquivo indisponível", availabilityMessage);
        if (previewCard) previewCard.dataset.previewState = "unavailable";
        setUploadState(
          state,
          availabilityMessage || "O registro existe, mas o arquivo não está acessível no armazenamento atual. Visualização e download foram bloqueados.",
          "warning",
        );
        return;
      }

      setDocumentDetailLink(openLink, url);
      setDocumentDetailLink(downloadLink, downloadUrl || url);
      if (fallback) fallback.hidden = true;
      if (previewCard) previewCard.dataset.previewState = "ready";
      await loadDocumentPreviewBlob({ url, titleText, frame, frameWrap, fallback, state });
    }

    function validateTripulanteForm() {
      const identityValidations = [
        validateRequiredInput(nameInput, "Informe o nome do tripulante."),
        validateRequiredInput(cpfInput, "Informe o CPF."),
        setFieldFeedback(cpfInput, String(cpfInput?.value || "").replace(/\D/g, "").length === 11 ? "" : "CPF deve ter 11 dígitos."),
        validateRequiredInput(anacInput, "Informe o código ANAC."),
        setFieldFeedback(anacInput, String(anacInput?.value || "").replace(/\D/g, "").length >= 4 ? "" : "Código ANAC deve ter ao menos 4 dígitos."),
      ];
      const operationValidations = [
        validateRequiredInput(document.getElementById("tripulanteBase"), "Selecione a base."),
        validateRequiredInput(document.getElementById("tripulanteStatus"), "Selecione o status."),
        validateRequiredInput(document.getElementById("tripulanteFuncao"), "Selecione a função."),
        validateRequiredInput(document.getElementById("tripulanteCategoria"), "Selecione a categoria."),
      ];
      const validations = [...identityValidations, ...operationValidations];
      const emailInput = document.getElementById("tripulanteEmail");
      if (emailInput?.value && !emailInput.validity.valid) {
        const emailValid = setFieldFeedback(emailInput, "Informe um e-mail válido.");
        identityValidations.push(emailValid);
        validations.push(emailValid);
      } else {
        setFieldFeedback(emailInput, "");
      }
      setSectionFeedback(
        "tripulanteIdentitySectionFeedback",
        identityValidations.every(Boolean) ? "" : "Revise identificação antes de salvar.",
      );
      setSectionFeedback(
        "tripulanteOperationSectionFeedback",
        operationValidations.every(Boolean) ? "" : "Complete os campos operacionais obrigatórios.",
      );
      return validations.every(Boolean);
    }

    function renderPhotoPreview(src = "") {
      photoPreview.innerHTML = src
        ? `<img class="tripulante-photo-img" src="${escapeAttr(src)}" alt="${escapeAttr(nameInput?.value || "Tripulante")}" data-photo-fallback="initials" data-initials="${escapeAttr(initialsForName(nameInput?.value || ""))}" data-photo-state-target="tripulantePhotoState">`
        : `<span>${escapeHtml(initialsForName(nameInput?.value || ""))}</span>`;
      wireTripulantePhotoFallbacks(photoPreview);
    }

    function formatCpf(value) {
      const digits = String(value || "").replace(/\D/g, "").slice(0, 11);
      if (digits.length <= 3) return digits;
      if (digits.length <= 6) return `${digits.slice(0, 3)}.${digits.slice(3)}`;
      if (digits.length <= 9) return `${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6)}`;
      return `${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6, 9)}-${digits.slice(9)}`;
    }

    function formatPhone(value) {
      const digits = String(value || "").replace(/\D/g, "").slice(0, 11);
      if (digits.length <= 2) return digits ? `(${digits}` : "";
      if (digits.length <= 6) return `(${digits.slice(0, 2)}) ${digits.slice(2)}`;
      if (digits.length <= 10) return `(${digits.slice(0, 2)}) ${digits.slice(2, 6)}-${digits.slice(6)}`;
      return `(${digits.slice(0, 2)}) ${digits.slice(2, 7)}-${digits.slice(7)}`;
    }

    cpfInput?.addEventListener("input", () => {
      cpfInput.value = formatCpf(cpfInput.value);
      setFieldFeedback(cpfInput, String(cpfInput.value || "").replace(/\D/g, "").length === 11 || !cpfInput.value ? "" : "CPF deve ter 11 dígitos.");
    });
    anacInput?.addEventListener("input", () => {
      anacInput.value = String(anacInput.value || "").replace(/\D/g, "").slice(0, 6);
      setFieldFeedback(anacInput, String(anacInput.value || "").length >= 4 || !anacInput.value ? "" : "Código ANAC deve ter ao menos 4 dígitos.");
    });
    phoneInput?.addEventListener("input", () => {
      phoneInput.value = formatPhone(phoneInput.value);
    });
    nameInput?.addEventListener("input", () => {
      setFieldFeedback(nameInput, "");
      if (!photoPreview.querySelector("img")) renderPhotoPreview("");
    });
    document.querySelectorAll("#tripulante-form [required]").forEach((input) => {
      input.addEventListener("blur", () => validateRequiredInput(input, "Campo obrigatório."));
      input.addEventListener("change", () => setFieldFeedback(input, ""));
    });
    document.querySelectorAll(".toggle-switch input[type='checkbox']").forEach((input) => {
      input.addEventListener("change", () => {
        const textNode = input.closest(".toggle-switch")?.querySelector(".toggle-text");
        if (textNode) textNode.textContent = input.checked ? "Ativo" : "Inativo";
      });
    });

    const tripulanteDraft = wireCriticalFormDraftProtection({
      form: "tripulante-form",
      formKey: `tripulante:${tripulanteId || "new"}`,
      baselineFields: {
        nome: tripulante?.nome || "",
        cpf: tripulante?.cpf || "",
        licenca_anac: tripulante?.licenca_anac || "",
        email: tripulante?.email || "",
        telefone: tripulante?.telefone || "",
        base: tripulante?.base || "",
        status: tripulante?.status || "",
        funcao_operacional: tripulante?.funcao_operacional || (!tripulante ? "outro" : ""),
        categoria_operacional: tripulante?.categoria_operacional || (!tripulante ? "N/A" : ""),
        ativo: !tripulante || Boolean(tripulante.ativo),
        sdea_ativo: Boolean(tripulante?.sdea_ativo),
        instrutor_ativo: Boolean(tripulante?.instrutor_ativo),
        checador_ativo: Boolean(tripulante?.checador_ativo),
        elegivel_adicional_excepcional: Boolean(tripulante?.elegivel_adicional_excepcional),
        observacoes: tripulante?.observacoes || "",
      },
      includeFields: [
        "nome",
        "cpf",
        "licenca_anac",
        "email",
        "telefone",
        "base",
        "status",
        "funcao_operacional",
        "categoria_operacional",
        "ativo",
        "sdea_ativo",
        "instrutor_ativo",
        "checador_ativo",
        "elegivel_adicional_excepcional",
        "observacoes",
      ],
      feedbackTarget: formFeedback,
      restoreMessage: "Rascunho local recuperado. Revise e salve para persistir o cadastro.",
    });

    document.getElementById("tripulante-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!validateTripulanteForm()) {
        renderInlineFeedback(formFeedback, "Revise os campos destacados antes de salvar.", "error");
        document.querySelector("#tripulante-form [aria-invalid='true']")?.focus();
        return;
      }
      const form = new FormData(event.currentTarget);
      const payload = Object.fromEntries(form.entries());
      ["ativo", "sdea_ativo", "instrutor_ativo", "checador_ativo", "elegivel_adicional_excepcional"].forEach((key) => {
        payload[key] = form.has(key);
      });
      const submitButton = document.getElementById("tripulanteFormSubmit");
      await withActionBusy(submitButton, "Salvando...", async () => {
        try {
          renderInlineFeedback(formFeedback, "");
          const result = await api(tripulanteId ? `/api/v1/tripulantes/${tripulanteId}` : "/api/v1/tripulantes", {
            method: tripulanteId ? "PUT" : "POST",
            json: payload,
          });
          tripulanteDraft?.clear({ reason: "save_success" });
          showFlash("Tripulante salvo com sucesso.", "success");
          const nextId = Number(result.data.tripulante.id);
          if (Number(tripulanteId || 0) === nextId) {
            await renderTripulanteFormPage(nextId);
          } else {
            window.location.hash = `#/tripulantes/${nextId}`;
          }
        } catch (error) {
          renderInlineFeedback(formFeedback, buildErrorMessage(error), "error");
        }
      });
    });

    document.getElementById("tripulanteDeleteButton")?.addEventListener("click", async () => {
      const deleteButton = document.getElementById("tripulanteDeleteButton");
      if (!confirmAction({
        title: "Remover este tripulante?",
        subject: tripulante?.nome || nameInput?.value || "Tripulante selecionado",
        consequence: "Se houver vínculos históricos, o registro pode ser inativado em vez de excluído.",
      })) return;
      await withActionBusy(deleteButton, "Removendo...", async () => {
        try {
          const { data } = await api(`/api/v1/tripulantes/${tripulanteId}`, { method: "DELETE" });
          showFlash(
            data?.operation === "inactivated"
              ? "Tripulante inativado porque existem vínculos históricos."
              : "Tripulante excluído com sucesso.",
            "success",
          );
          tripulanteDraft?.clear({ reason: "delete_success" });
          window.location.hash = "#/tripulantes";
        } catch (error) {
          renderInlineFeedback(formFeedback, buildErrorMessage(error), "error");
        }
      });
    });

    photoInput?.addEventListener("change", async () => {
      const file = photoInput.files?.[0];
      const selection = classifyPhotoSelection(file);
      if (!file) {
        setPhotoUploadState(selection.stateMessage);
        return;
      }
      if (!selection.ok) {
        setPhotoUploadState(selection.stateMessage, selection.kind, "error");
        renderInlineFeedback(formFeedback, selection.formMessage, selection.kind);
        photoInput.value = "";
        revertPhotoPreviewToPersisted();
        return;
      }
      setPhotoUploadState(selection.stateMessage, selection.kind, "ready");
      renderInlineFeedback(formFeedback, "");
      try {
        renderPhotoPreview(await fileToDataUrl(file));
      } catch (error) {
        const failure = classifyPhotoUploadFailure(error, file);
        setPhotoUploadState(failure.stateMessage, failure.kind, "error");
        renderInlineFeedback(formFeedback, failure.formMessage, failure.kind);
        photoInput.value = "";
        revertPhotoPreviewToPersisted();
      }
    });

    document.getElementById("tripulantePhotoUpload")?.addEventListener("click", async () => {
      const uploadButton = document.getElementById("tripulantePhotoUpload");
      const file = photoInput?.files?.[0];
      const selection = classifyPhotoSelection(file);
      if (!tripulanteId || !selection.ok) {
        setPhotoUploadState(
          !tripulanteId ? "Salve o tripulante antes de enviar foto." : selection.stateMessage,
          "error",
          "error",
        );
        renderInlineFeedback(
          formFeedback,
          !tripulanteId ? "Salve o cadastro do tripulante antes de enviar foto." : selection.formMessage,
          "error",
        );
        return;
      }
      setPhotoUploadState(`${file.name} - enviando e confirmando persistencia...`, "busy", "busy");
      await withActionBusy(uploadButton, "Enviando...", async () => {
        try {
          const photoDataUrl = await fileToDataUrl(file);
          const result = await runWithCsrfRetry(() => api(`/api/v1/tripulantes/${tripulanteId}/photo`, {
            method: "POST",
            json: { foto_base64: photoDataUrl },
          }));
          const confirmedPhoto = assertPhotoUploadConfirmed(result);
          const confirmedUrl = `${confirmedPhoto.photo_url}${confirmedPhoto.photo_url.includes("?") ? "&" : "?"}v=${Date.now()}`;
          setPhotoUploadState(`${file.name} - envio confirmado. Foto salva e disponível para exibição.`, "success", "success");
          renderPhotoPreview(confirmedUrl);
          photoInput.value = "";
          showFlash("Foto atualizada com sucesso. Arquivo confirmado para exibição.", "success");
          await renderTripulanteFormPage(tripulanteId);
        } catch (error) {
          const failure = classifyPhotoUploadFailure(error, file);
          setPhotoUploadState(failure.stateMessage, failure.kind, failure.kind === "warning" ? "warning" : "error");
          renderInlineFeedback(formFeedback, failure.formMessage, failure.kind);
          revertPhotoPreviewToPersisted();
        }
      });
    });

    document.getElementById("tripulantePhotoRemove")?.addEventListener("click", async () => {
      if (!tripulanteId) return;
      const removeButton = document.getElementById("tripulantePhotoRemove");
      if (!confirmAction({
        title: "Remover foto do tripulante?",
        subject: tripulante?.nome || nameInput?.value || "Tripulante selecionado",
        consequence: "A foto deixará de aparecer no cadastro e nos relatórios vinculados.",
      })) return;
      await withActionBusy(removeButton, "Removendo...", async () => {
        try {
          await api(`/api/v1/tripulantes/${tripulanteId}/photo`, { method: "DELETE" });
          showFlash("Foto removida com sucesso.", "success");
          await renderTripulanteFormPage(tripulanteId);
        } catch (error) {
          renderInlineFeedback(formFeedback, buildErrorMessage(error), "error");
        }
      });
    });

    document.getElementById("tripulante-file-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const submitButton = event.currentTarget.querySelector('button[type="submit"]');
      const file = documentInput?.files?.[0];
      if (!validatePdfFile(file, documentState)) {
        documentInput?.focus();
        return;
      }
      const replacing = Boolean(documentReplaceSelect?.value);
        setUploadState(documentState, `${file.name} - ${formatFileSize(file.size)} - ${replacing ? "substituindo documento existente..." : "anexando novo documento..."}`, "busy");
      await withActionBusy(submitButton, replacing ? "Substituindo..." : "Anexando...", async () => {
        try {
          await api(`/api/v1/tripulantes/${tripulanteId}/files`, {
            method: "POST",
            body: new FormData(event.currentTarget),
          });
          showFlash(replacing ? "PDF substituido com sucesso." : "PDF anexado com sucesso.", "success");
          await renderTripulanteFormPage(tripulanteId);
        } catch (error) {
          setUploadState(documentState, `${file.name} - ${replacing ? "falha ao substituir" : "falha ao anexar"}`, "error");
          renderInlineFeedback(formFeedback, buildErrorMessage(error), "error");
        }
      });
    });
    documentInput?.addEventListener("change", () => {
      const file = documentInput.files?.[0];
      if (!file) {
        renderDocumentUploadIdleState();
        return;
      }
      if (validatePdfFile(file, documentState)) renderDocumentUploadReadyState(file);
    });
    documentReplaceSelect?.addEventListener("change", () => {
      syncDocumentUploadMode();
    });
    syncDocumentUploadMode();

    const documentMasterDetail = wireResponsiveMasterDetail({
      root: "#tripulanteDocumentMasterDetail",
      master: "#tripulanteDocumentMaster",
      detail: "#tripulanteDocumentDetailPane",
      triggers: ".tripulante-file-preview",
      backTrigger: "#tripulanteDocumentPreviewBack",
      detailFocus: "#tripulanteDocumentPreviewName",
      autoWire: false,
    });

    function documentPreviewPayloadFromButton(button) {
      return {
        url: button.dataset.previewUrl || "",
        downloadUrl: button.dataset.downloadUrl || "",
        fileId: button.dataset.fileId || "",
        name: button.dataset.fileName || "Documento PDF",
        meta: button.dataset.fileMeta || "application/pdf",
        type: button.dataset.fileType || "",
        size: button.dataset.fileSize || "",
        status: button.dataset.fileStatus || "",
        sentAt: button.dataset.fileSentAt || "",
        note: button.dataset.fileNote || "",
        blobAvailable: button.dataset.fileBlobAvailable === "true",
        availabilityLabel: button.dataset.fileAvailabilityLabel || "",
        availabilityMessage: button.dataset.fileAvailabilityMessage || "",
      };
    }

    document.querySelectorAll(".tripulante-file-preview").forEach((button) => {
      button.addEventListener("click", () => {
        document.querySelectorAll(".document-library-select").forEach((candidate) => {
          const selected = candidate === button;
          candidate.classList.toggle("is-selected", selected);
          candidate.textContent = selected ? "Selecionado" : "Selecionar";
          candidate.closest(".document-library-row")?.classList.toggle("is-selected", selected);
        });
        void renderDocumentPreview(documentPreviewPayloadFromButton(button));
        documentMasterDetail?.activate(button);
      });
    });

    const initialDocumentButton = document.querySelector(".tripulante-file-preview.is-selected");
    if (initialDocumentButton) {
      void renderDocumentPreview(documentPreviewPayloadFromButton(initialDocumentButton));
    }

    const detailDeleteButton = document.getElementById("tripulanteDocumentDelete");
    detailDeleteButton?.addEventListener("click", async () => {
      const fileId = detailDeleteButton.dataset.fileId || "";
      const fileName = detailDeleteButton.dataset.fileName || "Documento selecionado";
      if (!fileId) {
        setUploadState(
          document.getElementById("tripulanteDocumentPreviewState"),
          "Selecione um documento disponível para exclusão.",
          "error",
        );
        return;
      }
      if (!confirmAction({
        title: "Excluir este documento PDF?",
        subject: fileName,
        consequence: "O arquivo deixará de ficar disponível no cadastro do tripulante.",
      })) return;
      await withActionBusy(detailDeleteButton, "Excluindo...", async () => {
        try {
          await api(`/api/v1/tripulantes/${tripulanteId}/files/${fileId}`, { method: "DELETE" });
          showFlash("Documento removido com sucesso.", "success");
          await renderTripulanteFormPage(tripulanteId);
        } catch (error) {
          renderInlineFeedback(formFeedback, buildErrorMessage(error), "error");
        }
      });
    });
  } catch (error) {
    showFlash(buildErrorMessage(error), "error");
    renderShell("<section class='panel'><div class='empty'>Falha ao carregar formulario de tripulante.</div></section>", "Tripulantes");
  }
}



