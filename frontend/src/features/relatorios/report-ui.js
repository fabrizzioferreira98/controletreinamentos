import {
  escapeAttr,
  escapeHtml,
  responsiveStateMarkup,
  wireResponsiveFilterPanel,
} from "../../lib.js";

export function formatInteger(value) {
  const amount = Number(value || 0);
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 }).format(Number.isFinite(amount) ? amount : 0);
}

export function reportValue(value, fallback = "Todos") {
  const normalized = String(value || "").trim();
  return normalized || fallback;
}

export function renderReportLoadingState(title, detail) {
  return `
    <section class="panel report-shell report-state-panel ui-surface">
      ${responsiveStateMarkup({
        title,
        detail,
        type: "loading",
        className: "feedback info ui-feedback report-loading-state",
      })}
    </section>
  `;
}

export function renderReportErrorState(title, detail, actionHref, actionLabel) {
  return `
    <section class="panel report-shell report-state-panel ui-surface">
      ${responsiveStateMarkup({
        title,
        detail,
        actionHref,
        actionLabel: actionHref ? (actionLabel || "Tentar novamente") : "",
        type: "error",
        className: "empty-state empty-state-error",
      })}
    </section>
  `;
}

export function renderReportContextStrip({ title, detail = "", items = [] }) {
  return `
    <section class="report-context-strip ui-surface">
      <div class="report-context-intro">
        <strong>${escapeHtml(title)}</strong>
        ${detail ? `<span>${escapeHtml(detail)}</span>` : ""}
      </div>
      <div class="report-context-items ui-card-grid ui-card-grid-compact ui-card-equal-height">
        ${items
          .map(
            (item) => `
              <div class="report-context-item ui-surface ui-card ui-card-compact">
                <span>${escapeHtml(item.label)}</span>
                <strong>${escapeHtml(item.value)}</strong>
              </div>
            `,
          )
          .join("")}
      </div>
    </section>
  `;
}

export function renderReportEvidencePanel({ title, detail = "", items = [] }) {
  return `
    <section class="report-evidence-panel print-hide ui-surface">
      <div>
        <h2>${escapeHtml(title)}</h2>
        ${detail ? `<p>${escapeHtml(detail)}</p>` : ""}
      </div>
      <div class="report-evidence-list ui-card-grid ui-card-equal-height">
        ${items
          .map(
            (item) => `
              <a class="report-evidence-item ui-surface ui-card" href="${escapeAttr(item.href)}" ${item.target ? `target="${escapeAttr(item.target)}" rel="noopener noreferrer"` : ""}>
                <span>${escapeHtml(item.label)}</span>
                <strong>${escapeHtml(item.value)}</strong>
              </a>
            `,
          )
          .join("")}
      </div>
    </section>
  `;
}

export function wireResponsiveFilters(toggleId, panelId, expandedText, collapsedText) {
  wireResponsiveFilterPanel(toggleId, panelId, expandedText, collapsedText);
}

