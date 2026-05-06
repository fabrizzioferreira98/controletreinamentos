import {
  escapeAttr,
  escapeHtml,
  formatDateTimeBr,
  formatFileSize,
} from "../../lib.js";
export function renderTrainingAttachmentSection(treinamentoId, attachments, capabilities) {
  if (!treinamentoId) {
    return `
      <section class="panel training-record-attachment-panel ui-surface ui-stack ui-panel-offset">
        <div class="hint ui-field-help">Salve o treinamento primeiro para habilitar anexos PDF.</div>
      </section>
    `;
  }

  const canUpload = capabilities.has("treinamentos_anexos:create");
  const canDelete = capabilities.has("treinamentos_anexos:delete");

  return `
    <section class="panel entity-document-panel training-record-attachment-panel ui-surface ui-stack ui-panel-offset">
      <div class="page-header ui-block-end-sm">
        <div>
          <h2 class="ui-heading-reset">Anexos em PDF do treinamento</h2>
          <p class="page-subtitle ui-subtitle-compact">Documentos comprobatórios vinculados ao treinamento.</p>
        </div>
      </div>

      ${
        canUpload
          ? `
            <form id="treinamento-attachment-form" class="filters filters-wide document-upload-form ui-form-toolbar ui-form-upload-grid ui-block-end-sm" data-upload-layout="single">
              <label class="document-upload-input ui-form-upload-field">
                PDF do treinamento
                <input type="file" name="arquivo_pdf" id="treinamentoAttachmentInput" accept="application/pdf" required aria-describedby="treinamentoAttachmentUploadState">
                <span class="field-help ui-field-help">Limite por arquivo: 20 MB. Apenas PDF.</span>
              </label>
              <button type="submit">Anexar PDF</button>
            </form>
            <div class="upload-state ui-form-upload-state" id="treinamentoAttachmentUploadState" aria-live="polite">Nenhum PDF selecionado.</div>
          `
          : ""
      }

      <div class="table-wrap ui-table-wrap ui-table-density-compact ui-panel-offset-sm">
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
                          <td data-label="Tamanho">${escapeHtml(formatFileSize(item.tamanho_bytes))}</td>
                          <td data-label="Enviado em">${escapeHtml(formatDateTimeBr(item.enviado_em))}</td>
                          <td data-label="Enviado por">${escapeHtml(item.enviado_por_nome || "-")}</td>
                          <td class="actions ui-table-actions" data-label="Ações">
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
                : '<tr><td colspan="5" class="empty ui-table-state">Nenhum PDF anexado a este treinamento. Anexe o comprovante quando o registro exigir evidência.</td></tr>'
            }
          </tbody>
        </table>
      </div>
    </section>
  `;
}

