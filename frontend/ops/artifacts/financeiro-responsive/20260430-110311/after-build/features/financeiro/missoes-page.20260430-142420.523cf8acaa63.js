import {
  booleanLabel,
  buildErrorMessage,
  buildHashHref,
  capabilitySet,
  confirmAction,
  emptyTableRowMarkup,
  escapeAttr,
  escapeHtml,
  filterSummaryMarkup,
  formatDateBr,
  formatDateTimeBr,
  hashQuery,
  renderInlineFeedback,
  responsiveStateMarkup,
  showFlash,
  withActionBusy,
} from "../../lib.20260430-142420.cf58b4b4395e.js";
import { renderShell } from "../../shell.20260430-142420.eed3fe973fa2.js";
import {
  cancelFinanceiroMissao,
  createFinanceiroMissao,
  getFinanceiroMissao,
  listFinanceiroEquipamentoOptions,
  listFinanceiroMissoes,
  listFinanceiroTripulanteOptions,
  updateFinanceiroMissao,
} from "../../services/financeiro-missoes-api.20260430-142420.16c439adda33.js";

const FINANCEIRO_MISSOES_ROUTE = "#/financeiro/missoes";
const PAGE_SIZE = 50;
const TRIPULANTE_OPTION_PERMISSIONS = ["tripulantes:view", "relatorio_individual:view"];
const EQUIPAMENTO_OPTION_PERMISSIONS = ["equipamentos:view"];

function currentCompetencia() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  return `${now.getFullYear()}-${month}`;
}

function normalizeId(value) {
  const numeric = Number(value || 0);
  return Number.isFinite(numeric) && numeric > 0 ? numeric : null;
}

function readFilters() {
  const query = hashQuery();
  return {
    competencia: String(query.get("competencia") || currentCompetencia()).trim(),
    status: String(query.get("status") || "").trim(),
    busca: String(query.get("busca") || "").trim(),
    page: Math.max(1, Number(query.get("page") || 1) || 1),
    missionId: normalizeId(query.get("mission_id")),
  };
}

function missionStatusClass(status) {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "ativa") return "status-green";
  if (normalized === "cancelada") return "status-red";
  if (normalized === "recalculo_pendente") return "status-yellow";
  return "status-dark";
}

function normalizeSearchText(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

function missionMatchesSearch(mission, search) {
  const term = normalizeSearchText(search);
  if (!term) return true;
  const haystack = [
    mission?.cavok_numero_voo,
    mission?.chamado,
    mission?.contratante,
    mission?.trecho,
    mission?.categoria_financeira_aeronave,
  ].map(normalizeSearchText).join(" ");
  return haystack.includes(term);
}

function visibleMissions(items, filters) {
  return items.filter((mission) => missionMatchesSearch(mission, filters.busca));
}

function missionSummary(items) {
  const total = items.length;
  const active = items.filter((mission) => String(mission.status || "").toLowerCase() === "ativa").length;
  const cancelled = items.filter((mission) => String(mission.status || "").toLowerCase() === "cancelada").length;
  const pending = items.filter((mission) => String(mission.status || "").toLowerCase() === "recalculo_pendente").length;
  return { total, active, cancelled, pending };
}

function ratioLabel(part, total) {
  if (!total) return "0%";
  return `${((Number(part) / Number(total)) * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
}

function formatTimeBr(value) {
  const raw = String(value || "").trim();
  if (!raw) return "-";
  const match = raw.match(/[T\s](\d{2}):(\d{2})/);
  return match ? `${match[1]}:${match[2]}` : formatDateTimeBr(raw);
}

function fieldValue(mission, key, fallback = "") {
  return escapeAttr(mission?.[key] ?? fallback);
}

function datetimeLocalValue(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  return raw.replace(" ", "T").slice(0, 16);
}

function checkboxAttr(value) {
  return value ? "checked" : "";
}

function hasAnyCapability(capabilities, permissions) {
  return permissions.some((permission) => capabilities.has(permission));
}

function normalizeOptionItem(item, { fallbackName = "Registro", categoryKeys = [] } = {}) {
  const id = normalizeId(item?.id);
  if (!id) return null;
  const name = String(item?.nome || item?.label || item?.name || `${fallbackName} ${id}`).trim();
  const details = [
    item?.base,
    item?.funcao_operacional,
    item?.categoria_operacional,
  ]
    .map((value) => String(value || "").trim())
    .filter(Boolean);
  const category = categoryKeys
    .map((key) => String(item?.[key] || "").trim())
    .find(Boolean) || "";
  const suffix = details.length ? ` (${details.join(" / ")})` : "";
  return {
    id: String(id),
    label: name,
    display: `${id} - ${name}${suffix}`,
    category,
  };
}

function normalizeTripulanteOptions(payload) {
  const source = Array.isArray(payload?.items) ? payload.items : [];
  return source
    .map((item) => normalizeOptionItem(item, { fallbackName: "Tripulante" }))
    .filter(Boolean);
}

function normalizeEquipamentoOptions(payload) {
  const source = Array.isArray(payload?.options)
    ? payload.options
    : (Array.isArray(payload?.options?.equipamentos) ? payload.options.equipamentos : []);
  return source
    .map((item) => normalizeOptionItem(item, {
      fallbackName: "Equipamento",
      categoryKeys: ["categoria_financeira", "categoria_financeira_aeronave"],
    }))
    .filter(Boolean);
}

function optionStateReady(items, endpoint) {
  return {
    status: items.length ? "ready" : "empty",
    endpoint,
    items,
    detail: items.length ? "" : "Nenhuma opcao disponivel; informe o ID manualmente.",
  };
}

function optionStateUnavailable({ status = "unavailable", endpoint, detail }) {
  return {
    status,
    endpoint,
    items: [],
    detail,
  };
}

function optionStateFromError(error, endpoint) {
  if (error?.status === 401) {
    return optionStateUnavailable({
      status: "forbidden",
      endpoint,
      detail: "Sessao expirada ao carregar opcoes; informe o ID manualmente.",
    });
  }
  if (error?.status === 403) {
    return optionStateUnavailable({
      status: "forbidden",
      endpoint,
      detail: "Seu perfil nao possui permissao para carregar estas opcoes; informe o ID manualmente.",
    });
  }
  if (error?.status === 501) {
    return optionStateUnavailable({
      status: "not-implemented",
      endpoint,
      detail: "Endpoint de opcoes ainda nao implementado; informe o ID manualmente.",
    });
  }
  return optionStateUnavailable({
    status: "error",
    endpoint,
    detail: buildErrorMessage(error),
  });
}

async function loadTripulanteOptions(capabilities) {
  const endpoint = "/api/v1/tripulantes";
  if (!hasAnyCapability(capabilities, TRIPULANTE_OPTION_PERMISSIONS)) {
    return optionStateUnavailable({
      status: "forbidden",
      endpoint,
      detail: "Sem permissao de leitura de tripulantes; informe o ID manualmente.",
    });
  }
  try {
    const payload = await listFinanceiroTripulanteOptions({ ativo: "1" });
    return optionStateReady(normalizeTripulanteOptions(payload), endpoint);
  } catch (error) {
    return optionStateFromError(error, endpoint);
  }
}

async function loadEquipamentoOptions(capabilities) {
  const endpoint = "/api/v1/equipamentos/options";
  if (!hasAnyCapability(capabilities, EQUIPAMENTO_OPTION_PERMISSIONS)) {
    return optionStateUnavailable({
      status: "forbidden",
      endpoint,
      detail: "Sem permissao de leitura de equipamentos. Informe o ID manualmente.",
    });
  }
  try {
    const payload = await listFinanceiroEquipamentoOptions();
    return optionStateReady(normalizeEquipamentoOptions(payload), endpoint);
  } catch (error) {
    return optionStateFromError(error, endpoint);
  }
}

async function loadFinanceiroMissionOptions(capabilities) {
  const [tripulantes, equipamentos] = await Promise.all([
    loadTripulanteOptions(capabilities),
    loadEquipamentoOptions(capabilities),
  ]);
  return { tripulantes, equipamentos };
}

function optionById(optionsState, id) {
  const target = String(id || "").trim();
  if (!target) return null;
  return (optionsState?.items || []).find((item) => String(item.id) === target) || null;
}

function optionLabel(optionsState, id, fallbackPrefix) {
  const option = optionById(optionsState, id);
  if (option) return option.label;
  return id ? `${fallbackPrefix} ${escapeHtml(id)}` : "-";
}

function optionDisplayValue(optionsState, id) {
  const option = optionById(optionsState, id);
  if (option) return option.display;
  return id ? String(id) : "";
}

function requestErrorState(error) {
  if (error?.status === 401 || error?.code === "unauthorized") {
    return {
      type: "no-permission",
      title: "Sessao expirada",
      detail: "Entre novamente para acessar as Missoes Operacionais.",
    };
  }
  if (error?.status === 403 || error?.code === "forbidden") {
    return {
      type: "no-permission",
      title: "Acesso negado",
      detail: "Seu perfil nao possui permissao para acessar esta area do Financeiro.",
    };
  }
  if (error?.status === 501) {
    return {
      type: "warning",
      title: "Recurso ainda nao implementado",
      detail: "Esta parte do Financeiro ainda esta planejada para uma proxima etapa.",
    };
  }
  return {
    type: "error",
    title: "Nao foi possivel carregar Missoes Operacionais",
    detail: buildErrorMessage(error),
  };
}

function renderPageState(state) {
  renderShell(
    `
      <div class="financeiro-missoes-page ui-page-shell ui-stack">
        <section class="panel ui-surface">
          ${responsiveStateMarkup({
            title: state.title,
            detail: state.detail,
            type: state.type,
            className: "financeiro-missoes-state",
          })}
        </section>
      </div>
    `,
    "Missoes Operacionais",
  );
}

function missionParticipantName(mission, key) {
  if (key === "comandante_tripulante_id") {
    return mission?.comandante_nome || mission?.comandante_tripulante_nome || "";
  }
  if (key === "copiloto_tripulante_id") {
    return mission?.copiloto_nome || mission?.copiloto_tripulante_nome || "";
  }
  return "";
}

function renderParticipantLabel(mission, key, optionsState) {
  const value = mission?.[key];
  const explicitName = missionParticipantName(mission, key);
  if (explicitName) return escapeHtml(explicitName);
  return escapeHtml(optionLabel(optionsState, value, "Tripulante ID"));
}

function renderEquipmentLabel(mission, optionsState) {
  const explicitName = mission?.aeronave_nome || mission?.equipamento_nome || "";
  if (explicitName) return escapeHtml(explicitName);
  return escapeHtml(optionLabel(optionsState, mission?.aeronave_id, "Equipamento ID"));
}

function renderMissionSummaryCards(items) {
  const summary = missionSummary(items);
  const cards = [
    { label: "Missoes da competencia", value: summary.total, detail: "Registros carregados", tone: "neutral" },
    { label: "Ativas", value: summary.active, detail: ratioLabel(summary.active, summary.total), tone: "positive" },
    { label: "Canceladas", value: summary.cancelled, detail: ratioLabel(summary.cancelled, summary.total), tone: "danger" },
    { label: "Pendencias", value: summary.pending, detail: ratioLabel(summary.pending, summary.total), tone: "warning" },
  ];
  return `
    <section class="financeiro-missoes-summary-grid" aria-label="Resumo da competencia">
      ${cards
        .map((card) => `
          <article class="financeiro-missoes-summary-card ui-surface" data-tone="${escapeAttr(card.tone)}">
            <span>${escapeHtml(card.label)}</span>
            <strong>${escapeHtml(card.value)}</strong>
            <small>${escapeHtml(card.detail)}</small>
          </article>
        `)
        .join("")}
    </section>
  `;
}

function renderMissionRows(items, filters, capabilities, optionState) {
  if (!items.length) {
    return emptyTableRowMarkup(11, {
      title: "Nenhuma missao operacional encontrada.",
      detail: "Ajuste a competencia ou cadastre uma missao operacional para iniciar o acompanhamento.",
      type: "structural-empty",
    });
  }
  return items
    .map((mission) => {
      const detailHref = buildHashHref(FINANCEIRO_MISSOES_ROUTE, {
        competencia: filters.competencia,
        status: filters.status,
        page: filters.page,
        mission_id: mission.id,
      });
      return `
        <tr data-financeiro-missao-id="${escapeAttr(mission.id)}">
          <td data-label="Data">${formatDateBr(mission.data_missao)}</td>
          <td data-label="Cavok / Voo">
            <div class="primary-cell">${escapeHtml(mission.cavok_numero_voo || "-")}</div>
            <div class="secondary-cell">${mission.chamado ? `Chamado ${escapeHtml(mission.chamado)}` : "Sem chamado"}</div>
          </td>
          <td data-label="Contratante">${escapeHtml(mission.contratante || "-")}</td>
          <td data-label="Aeronave">${renderEquipmentLabel(mission, optionState.equipamentos)}</td>
          <td data-label="Categoria">${escapeHtml(mission.categoria_financeira_aeronave || "-")}</td>
          <td data-label="Comandante">${renderParticipantLabel(mission, "comandante_tripulante_id", optionState.tripulantes)}</td>
          <td data-label="Copiloto">${renderParticipantLabel(mission, "copiloto_tripulante_id", optionState.tripulantes)}</td>
          <td data-label="Apresentacao">${formatTimeBr(mission.horario_apresentacao)}</td>
          <td data-label="Abandono">${formatTimeBr(mission.horario_abandono)}</td>
          <td data-label="Status"><span class="status-pill ${missionStatusClass(mission.status)}">${escapeHtml(mission.status || "-")}</span></td>
          <td class="actions ui-table-actions" data-label="Acoes">
            <a href="${escapeAttr(detailHref)}">Abrir</a>
            ${capabilities.has("finance:missions:update") ? `<a href="${escapeAttr(detailHref)}">Editar</a>` : ""}
          </td>
        </tr>
      `;
    })
    .join("");
}

function renderMissionDetail(mission, canCancel, optionState) {
  if (!mission) {
    return `
      <div class="financeiro-missoes-side-empty">
        ${responsiveStateMarkup({
          title: "Selecione uma missao operacional",
          detail: "Abra um registro da lista para ver detalhe, editar campos basicos ou cancelar.",
          type: "info",
          compact: true,
        })}
      </div>
    `;
  }
  const participants = Array.isArray(mission.participantes) ? mission.participantes : [];
  return `
    <div class="financeiro-missoes-detail">
      <div class="financeiro-missoes-detail-head">
        <div>
          <h2>Missao operacional #${escapeHtml(mission.id)}</h2>
          <p>${escapeHtml(mission.cavok_numero_voo || "Sem numero")} - ${escapeHtml(mission.trecho || "Trecho nao informado")}</p>
        </div>
        <span class="status-pill ${missionStatusClass(mission.status)}">${escapeHtml(mission.status || "-")}</span>
      </div>
      <dl class="financeiro-missoes-detail-grid">
        <div><dt>Competencia</dt><dd>${escapeHtml(mission.competencia || "-")}</dd></div>
        <div><dt>Data</dt><dd>${formatDateBr(mission.data_missao)}</dd></div>
        <div><dt>Aeronave</dt><dd>${renderEquipmentLabel(mission, optionState.equipamentos)}</dd></div>
        <div><dt>Apresentacao unica</dt><dd>${formatDateTimeBr(mission.horario_apresentacao)}</dd></div>
        <div><dt>Abandono unico</dt><dd>${formatDateTimeBr(mission.horario_abandono)}</dd></div>
        <div><dt>Comandante</dt><dd>${renderParticipantLabel(mission, "comandante_tripulante_id", optionState.tripulantes)}</dd></div>
        <div><dt>Copiloto</dt><dd>${renderParticipantLabel(mission, "copiloto_tripulante_id", optionState.tripulantes)}</dd></div>
        <div><dt>Pernoite</dt><dd>${booleanLabel(mission.houve_pernoite)} (${escapeHtml(mission.quantidade_pernoites || 0)})</dd></div>
        <div><dt>Cobertura de base</dt><dd>${booleanLabel(mission.cobertura_base)}</dd></div>
      </dl>
      <div class="financeiro-missoes-participants">
        <strong>Participantes do registro</strong>
        ${participants.length
          ? `<ul>${participants.map((item) => `<li>${escapeHtml(item.funcao || "-")}: ${escapeHtml(optionLabel(optionState.tripulantes, item.tripulante_id, "Tripulante ID"))}</li>`).join("")}</ul>`
          : "<span>Participantes serao exibidos quando o detalhe retornar essa estrutura.</span>"}
      </div>
      <div class="financeiro-missoes-detail-actions ui-form-actions">
        <a class="button-link secondary" href="${escapeAttr(buildHashHref(FINANCEIRO_MISSOES_ROUTE, { competencia: mission.competencia }))}">Fechar detalhe</a>
        ${canCancel && mission.status !== "cancelada" ? '<button type="button" class="link-danger" id="financeMissionCancelButton">Cancelar missao</button>' : ""}
      </div>
    </div>
  `;
}

function renderOptionsFeedback(optionState) {
  const messages = [];
  if (optionState.tripulantes.status !== "ready") {
    messages.push({
      title: "Opcoes de tripulantes indisponiveis",
      detail: `${optionState.tripulantes.detail} Fonte prevista: ${optionState.tripulantes.endpoint}.`,
      type: optionState.tripulantes.status === "forbidden" ? "warning" : "info",
    });
  }
  if (optionState.equipamentos.status !== "ready") {
    messages.push({
      title: "Opcoes de aeronave/equipamento indisponiveis",
      detail: `${optionState.equipamentos.detail} Fonte prevista: ${optionState.equipamentos.endpoint}.`,
      type: optionState.equipamentos.status === "forbidden" ? "warning" : "info",
    });
  }
  if (optionState.equipamentos.status === "ready" && !optionState.equipamentos.items.some((item) => item.category)) {
    messages.push({
      title: "Categoria financeira manual",
      detail: "Nenhum equipamento carregado trouxe categoria financeira; o campo da missao permanece manual.",
      type: "info",
    });
  }
  if (!messages.length) return "";
  return `
    <div class="financeiro-missoes-options-feedback">
      ${messages.map((message) => responsiveStateMarkup({ ...message, compact: true })).join("")}
    </div>
  `;
}

function optionInputDisabledAttr(disabled) {
  return disabled ? "disabled" : "";
}

function renderOptionCombobox({
  name,
  label,
  mission,
  optionsState,
  disabled = false,
  required = false,
  fallbackLabel,
  placeholder,
}) {
  const value = mission?.[name] || "";
  if (optionsState.status !== "ready") {
    return `
      <label>${fallbackLabel || `${label} ID`}
        <input name="${name}" type="number" min="1" step="1" ${required ? "required" : ""} ${optionInputDisabledAttr(disabled)} value="${fieldValue(mission, name)}">
        <span class="financeiro-missoes-field-help">Fallback por ID: ${escapeHtml(optionsState.detail)}</span>
      </label>
    `;
  }
  const datalistId = `${name}_options`;
  return `
    <label class="financeiro-missoes-combobox">${label}
      <input
        type="search"
        list="${escapeAttr(datalistId)}"
        data-finance-option-search="${escapeAttr(name)}"
        placeholder="${escapeAttr(placeholder || "Digite para pesquisar")}"
        value="${escapeAttr(optionDisplayValue(optionsState, value))}"
        autocomplete="off"
        ${required ? "required" : ""}
        ${optionInputDisabledAttr(disabled)}
      >
      <input
        name="${escapeAttr(name)}"
        type="hidden"
        data-finance-option-value="${escapeAttr(name)}"
        value="${fieldValue(mission, name)}"
        ${optionInputDisabledAttr(disabled)}
      >
      <datalist id="${escapeAttr(datalistId)}">
        ${optionsState.items
          .map((item) => `<option value="${escapeAttr(item.display)}" data-option-id="${escapeAttr(item.id)}" data-category="${escapeAttr(item.category)}"></option>`)
          .join("")}
      </datalist>
      <span class="financeiro-missoes-field-help">Use o cadastro existente ou informe o ID no inicio do campo.</span>
    </label>
  `;
}

function renderMissionForm({ mission, capabilities, optionState }) {
  const editing = Boolean(mission?.id);
  const canCreate = capabilities.has("finance:missions:create");
  const canUpdate = capabilities.has("finance:missions:update");
  const canSubmit = editing ? canUpdate : canCreate;
  return `
    <form id="financeMissionForm" class="financeiro-missoes-form ui-stack-sm" data-editing="${editing ? "true" : "false"}">
      <div class="financeiro-missoes-form-head">
        <div>
          <h2>${editing ? "Editar fato operacional" : "Nova missao operacional"}</h2>
          <p>Os horarios de apresentacao e abandono pertencem a missao, nao aos tripulantes.</p>
        </div>
        ${editing ? `<span class="status-pill ${missionStatusClass(mission.status)}">${escapeHtml(mission.status || "-")}</span>` : ""}
      </div>
      <div id="financeMissionFormFeedback" aria-live="polite"></div>
      <div class="financeiro-missoes-form-grid">
        <label>Competencia
          <input name="competencia" type="month" required value="${fieldValue(mission, "competencia", currentCompetencia())}">
        </label>
        <label>Data da missao
          <input name="data_missao" type="date" required value="${fieldValue(mission, "data_missao")}">
        </label>
        <label>Cavok / numero do voo
          <input name="cavok_numero_voo" type="text" value="${fieldValue(mission, "cavok_numero_voo")}">
        </label>
        <label>Contratante
          <input name="contratante" type="text" value="${fieldValue(mission, "contratante")}">
        </label>
        <label>Chamado
          <input name="chamado" type="text" value="${fieldValue(mission, "chamado")}">
        </label>
        ${renderOptionCombobox({
          name: "aeronave_id",
          label: "Aeronave / equipamento",
          fallbackLabel: "Aeronave ID",
          mission,
          optionsState: optionState.equipamentos,
          placeholder: "Pesquise por prefixo, modelo ou ID",
        })}
        <label>Categoria financeira da aeronave
          <input name="categoria_financeira_aeronave" type="text" data-finance-category-field value="${fieldValue(mission, "categoria_financeira_aeronave")}">
          <span class="financeiro-missoes-field-help">Selecione a aeronave para preencher pelo cadastro quando disponivel; o campo permanece editavel.</span>
          <span class="financeiro-missoes-field-help" data-finance-category-feedback></span>
        </label>
        <label>Status
          <select name="status">
            ${["rascunho", "ativa", "cancelada", "recalculo_pendente"]
              .map((status) => `<option value="${status}" ${String(mission?.status || "ativa") === status ? "selected" : ""}>${status}</option>`)
              .join("")}
          </select>
        </label>
        ${renderOptionCombobox({
          name: "comandante_tripulante_id",
          label: "Comandante",
          fallbackLabel: "Comandante tripulante ID",
          mission,
          optionsState: optionState.tripulantes,
          disabled: editing,
          required: true,
          placeholder: "Pesquise por nome ou ID",
        })}
        ${renderOptionCombobox({
          name: "copiloto_tripulante_id",
          label: "Copiloto",
          fallbackLabel: "Copiloto tripulante ID",
          mission,
          optionsState: optionState.tripulantes,
          disabled: editing,
          required: true,
          placeholder: "Pesquise por nome ou ID",
        })}
        <label>Horario de apresentacao
          <input name="horario_apresentacao" type="datetime-local" required value="${escapeAttr(datetimeLocalValue(mission?.horario_apresentacao))}">
        </label>
        <label>Horario de abandono
          <input name="horario_abandono" type="datetime-local" required value="${escapeAttr(datetimeLocalValue(mission?.horario_abandono))}">
        </label>
        <label>Trecho
          <input name="trecho" type="text" value="${fieldValue(mission, "trecho")}">
        </label>
        <label>Operacao especial
          <input name="operacao_especial" type="text" value="${fieldValue(mission, "operacao_especial")}">
        </label>
        <label>Quantidade de pernoites
          <input name="quantidade_pernoites" type="number" min="0" step="1" value="${fieldValue(mission, "quantidade_pernoites", "0")}">
        </label>
        <label class="financeiro-missoes-check">
          <input name="houve_pernoite" type="checkbox" ${checkboxAttr(mission?.houve_pernoite)}>
          Houve pernoite
        </label>
        <label class="financeiro-missoes-check">
          <input name="cobertura_base" type="checkbox" ${checkboxAttr(mission?.cobertura_base)}>
          Cobertura de base
        </label>
        <label class="financeiro-missoes-wide">Observacoes
          <textarea name="observacoes" rows="3">${escapeHtml(mission?.observacoes || "")}</textarea>
        </label>
      </div>
      ${editing ? '<div class="hint">Troca de comandante/copiloto sera feita em etapa posterior com controle de participantes.</div>' : ""}
      <div class="form-actions ui-form-actions">
        ${canSubmit ? `<button type="submit">${editing ? "Salvar alteracoes" : "Criar missao operacional"}</button>` : '<div class="hint">Seu perfil nao possui permissao para salvar missoes operacionais.</div>'}
        ${editing ? `<a class="button-link secondary" href="${escapeAttr(buildHashHref(FINANCEIRO_MISSOES_ROUTE, { competencia: mission.competencia }))}">Novo cadastro</a>` : ""}
      </div>
    </form>
  `;
}

function formPayload(form, { editing = false } = {}) {
  const data = Object.fromEntries(new FormData(form).entries());
  data.houve_pernoite = Boolean(form.elements.houve_pernoite?.checked);
  data.cobertura_base = Boolean(form.elements.cobertura_base?.checked);
  if (editing) {
    delete data.comandante_tripulante_id;
    delete data.copiloto_tripulante_id;
  }
  return data;
}

function optionIdFromInput(input) {
  const rawValue = String(input?.value || "").trim();
  if (!rawValue) return "";
  const matchingOption = Array.from(input.list?.options || []).find((option) => option.value === rawValue);
  if (matchingOption?.dataset?.optionId) return matchingOption.dataset.optionId;
  const match = rawValue.match(/^(\d+)(?:\s*-\s*|\s|$)/);
  return match ? match[1] : "";
}

function markCrewFields(form, hasConflict) {
  ["comandante_tripulante_id", "copiloto_tripulante_id"].forEach((name) => {
    const search = form.querySelector(`[data-finance-option-search="${name}"]`);
    const input = search || form.elements[name];
    input?.classList.toggle("is-invalid", hasConflict);
    input?.setAttribute("aria-invalid", hasConflict ? "true" : "false");
  });
}

function validateMissionCrew(form, { editing = false } = {}) {
  if (editing) return true;
  const comandanteId = String(form.elements.comandante_tripulante_id?.value || "").trim();
  const copilotoId = String(form.elements.copiloto_tripulante_id?.value || "").trim();
  const feedback = document.getElementById("financeMissionFormFeedback");
  markCrewFields(form, false);
  if (!comandanteId || !copilotoId) {
    renderInlineFeedback(feedback, "Informe comandante e copiloto a partir do cadastro de tripulantes ou pelo ID.", "warning");
    return false;
  }
  if (comandanteId === copilotoId) {
    markCrewFields(form, true);
    renderInlineFeedback(feedback, "Comandante e copiloto devem ser tripulantes distintos.", "warning");
    return false;
  }
  return true;
}

function updateCategoryFeedback(form, message) {
  const feedback = form.querySelector("[data-finance-category-feedback]");
  if (feedback) feedback.textContent = message || "";
}

function syncOptionInput(input, form) {
  const name = input.dataset.financeOptionSearch;
  const hidden = form.querySelector(`[data-finance-option-value="${name}"]`);
  const optionId = optionIdFromInput(input);
  if (hidden) hidden.value = optionId;
  input.classList.toggle("is-invalid", Boolean(input.value.trim()) && !optionId);
  input.setAttribute("aria-invalid", Boolean(input.value.trim()) && !optionId ? "true" : "false");
  if (name === "aeronave_id") {
    const matchingOption = Array.from(input.list?.options || []).find((option) => option.value === input.value);
    const category = matchingOption?.dataset?.category || "";
    const categoryInput = form.elements.categoria_financeira_aeronave;
    if (!categoryInput) return;
    if (category) {
      categoryInput.value = category;
      categoryInput.dataset.categorySource = "equipamento";
      updateCategoryFeedback(form, "Preenchida pelo cadastro do equipamento.");
      return;
    }
    if (optionId) {
      if (categoryInput.dataset.categorySource === "equipamento") {
        categoryInput.value = "";
      }
      delete categoryInput.dataset.categorySource;
      updateCategoryFeedback(form, "Categoria financeira nao cadastrada para este equipamento.");
      return;
    }
    updateCategoryFeedback(form, "Informe manualmente quando a categoria nao vier do cadastro.");
  }
}

function wireOptionComboboxes(form) {
  form.querySelectorAll("[data-finance-option-search]").forEach((input) => {
    syncOptionInput(input, form);
    input.addEventListener("input", () => {
      syncOptionInput(input, form);
      markCrewFields(form, false);
    });
    input.addEventListener("change", () => {
      syncOptionInput(input, form);
      validateMissionCrew(form, { editing: form.dataset.editing === "true" });
    });
  });
  const categoryInput = form.elements.categoria_financeira_aeronave;
  categoryInput?.addEventListener("input", () => {
    categoryInput.dataset.categorySource = "manual";
    updateCategoryFeedback(
      form,
      categoryInput.value.trim()
        ? "Categoria financeira editada manualmente."
        : "Informe manualmente quando a categoria nao vier do cadastro.",
    );
  });
}

function renderFinanceiroMissoes({ filters, listPayload, detailPayload, optionState, detailError = null }) {
  const capabilities = capabilitySet();
  const sourceItems = Array.isArray(listPayload?.items) ? listPayload.items : [];
  const items = visibleMissions(sourceItems, filters);
  const pagination = listPayload?.pagination || { page: filters.page, total: sourceItems.length };
  const selectedMission = detailPayload?.mission || null;
  const formMission = selectedMission || {
    competencia: filters.competencia,
    status: "ativa",
  };
  const filterLabels = {
    competencia: "Competencia",
    status: "Status",
    busca: "Busca",
  };

  renderShell(
    `
      <div class="financeiro-missoes-page priority-page-surface ui-page-shell ui-stack">
        <div class="page-header priority-page-header ui-page-header ui-surface">
          <div>
            <h1>Missões Operacionais</h1>
            <p class="page-subtitle">Cadastre os fatos operacionais que servirao de base para as bonificacoes.</p>
          </div>
          <div class="page-header-actions">
            ${capabilities.has("finance:missions:create") ? `<a class="button-link" href="${escapeAttr(buildHashHref(FINANCEIRO_MISSOES_ROUTE, { competencia: filters.competencia }))}">Nova missao</a>` : ""}
            <a class="button-link secondary" href="${escapeAttr(buildHashHref(FINANCEIRO_MISSOES_ROUTE, { competencia: currentCompetencia() }))}">Mes atual</a>
          </div>
        </div>

        <section class="panel ui-surface financeiro-missoes-notice">
          <strong>Tela operacional</strong>
          <span>Cadastre missao, comandante, copiloto, apresentacao unica e abandono unico. Bonificações serão calculadas em etapa posterior.</span>
        </section>

        ${renderMissionSummaryCards(sourceItems)}

        <section class="panel ui-surface ui-stack-sm">
          <details class="financeiro-mobile-disclosure financeiro-missoes-filter-disclosure" open>
            <summary>Filtros da competencia</summary>
            <div class="financeiro-mobile-disclosure-body">
              <div class="financeiro-missoes-section-head">
                <div>
                  <h2>Filtros</h2>
                  <p>Refine a competencia por status, Cavok, chamado ou contratante.</p>
                </div>
              </div>
              <form id="financeMissionFilters" class="filters-bar ui-form-toolbar ui-stack-sm">
                <div class="filters-bar-main ui-filter-row">
                  <input type="month" name="competencia" value="${escapeAttr(filters.competencia)}" aria-label="Competencia">
                  <select name="status" aria-label="Status">
                    <option value="">Todos os status</option>
                    ${["rascunho", "ativa", "cancelada", "recalculo_pendente"]
                      .map((status) => `<option value="${status}" ${filters.status === status ? "selected" : ""}>${status}</option>`)
                      .join("")}
                  </select>
                  <input type="search" name="busca" value="${escapeAttr(filters.busca)}" placeholder="Buscar Cavok, chamado ou contratante" aria-label="Buscar Cavok, chamado ou contratante">
                  <button type="submit">Aplicar</button>
                  <a class="button-link secondary" href="${escapeAttr(buildHashHref(FINANCEIRO_MISSOES_ROUTE, { competencia: currentCompetencia() }))}">Limpar</a>
                </div>
                ${filterSummaryMarkup({ competencia: filters.competencia, status: filters.status, busca: filters.busca }, filterLabels, { competencia: currentCompetencia() })}
              </form>
            </div>
          </details>
        </section>

        <div id="financeMissionPageFeedback" aria-live="polite"></div>

        <div class="financeiro-missoes-layout">
          <section class="panel ui-surface ui-stack">
            <div class="financeiro-missoes-section-head">
              <div>
                <h2>Lista da competencia</h2>
                <p>${escapeHtml(String(items.length))} registro(s) exibido(s) de ${escapeHtml(String(pagination.total ?? sourceItems.length))} carregado(s).</p>
              </div>
            </div>
            <div class="table-wrap ui-table-wrap ui-table-density-compact">
              <table class="data-table responsive-cards">
                <thead>
                  <tr>
                    <th>Data</th>
                    <th>Cavok / Voo</th>
                    <th>Contratante</th>
                    <th>Aeronave</th>
                    <th>Categoria</th>
                    <th>Comandante</th>
                    <th>Copiloto</th>
                    <th>Apres.</th>
                    <th>Aband.</th>
                    <th>Status</th>
                    <th>Acoes</th>
                  </tr>
                </thead>
                <tbody>
                  ${renderMissionRows(items, filters, capabilities, optionState)}
                </tbody>
              </table>
            </div>
          </section>

          <aside class="panel ui-surface ui-stack financeiro-missoes-side">
            ${detailError ? responsiveStateMarkup({ ...requestErrorState(detailError), compact: true }) : renderMissionDetail(selectedMission, capabilities.has("finance:missions:cancel"), optionState)}
            ${renderOptionsFeedback(optionState)}
            ${renderMissionForm({ mission: formMission, capabilities, optionState })}
            <div class="financeiro-missoes-coming-soon" data-state="not-implemented">
              <strong>Bonificacoes</strong>
              <span>Nao implementado nesta etapa.</span>
            </div>
          </aside>
        </div>
      </div>
    `,
    "Missões Operacionais",
  );

  wireFinanceiroMissoesInteractions({ filters, selectedMission });
}

function wireFinanceiroMissoesInteractions({ filters, selectedMission }) {
  syncFinanceiroMissoesMobileDisclosures();

  document.getElementById("financeMissionFilters")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
    window.location.hash = buildHashHref(FINANCEIRO_MISSOES_ROUTE, payload);
  });

  const missionForm = document.getElementById("financeMissionForm");
  if (missionForm) wireOptionComboboxes(missionForm);

  missionForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button[type='submit']");
    const editing = form.dataset.editing === "true" && selectedMission?.id;
    const feedback = document.getElementById("financeMissionFormFeedback");
    if (!validateMissionCrew(form, { editing })) return;
    await withActionBusy(button, "Salvando...", async () => {
      try {
        const payload = formPayload(form, { editing });
        const result = editing
          ? await updateFinanceiroMissao(selectedMission.id, payload)
          : await createFinanceiroMissao(payload);
        const mission = result.mission || {};
        showFlash(editing ? "Missao operacional atualizada." : "Missao operacional criada.", "success");
        window.location.hash = buildHashHref(FINANCEIRO_MISSOES_ROUTE, {
          competencia: mission.competencia || payload.competencia || filters.competencia,
          status: filters.status,
          mission_id: mission.id,
        });
      } catch (error) {
        renderInlineFeedback(feedback, buildErrorMessage(error), error.status === 403 ? "warning" : "error");
      }
    });
  });

  document.getElementById("financeMissionCancelButton")?.addEventListener("click", async (event) => {
    if (!selectedMission?.id) return;
    if (!confirmAction({
      title: "Cancelar missao operacional?",
      subject: `Missao #${selectedMission.id}`,
      consequence: "O registro sera mantido com status cancelada.",
    })) return;
    const button = event.currentTarget;
    await withActionBusy(button, "Cancelando...", async () => {
      try {
        await cancelFinanceiroMissao(selectedMission.id, { motivo: "Cancelamento solicitado pela tela de Missoes Operacionais" });
        showFlash("Missao operacional cancelada.", "success");
        window.location.hash = buildHashHref(FINANCEIRO_MISSOES_ROUTE, {
          competencia: selectedMission.competencia || filters.competencia,
          status: filters.status,
          mission_id: selectedMission.id,
        });
      } catch (error) {
        renderInlineFeedback(document.getElementById("financeMissionPageFeedback"), buildErrorMessage(error), "error");
      }
    });
  });
}

function syncFinanceiroMissoesMobileDisclosures() {
  const filterDisclosure = document.querySelector(".financeiro-missoes-filter-disclosure");
  if (!filterDisclosure || typeof window === "undefined" || typeof window.matchMedia !== "function") return;
  filterDisclosure.open = !window.matchMedia("(max-width: 720px)").matches;
}

export async function renderFinanceiroMissoesPage() {
  renderPageState({
    type: "loading",
    title: "Carregando Missões Operacionais",
    detail: "Buscando registros operacionais, permissoes e opcoes de cadastro.",
  });
  try {
    const filters = readFilters();
    const capabilities = capabilitySet();
    const listPromise = listFinanceiroMissoes({
      competencia: filters.competencia,
      status: filters.status,
      page: filters.page,
      pageSize: PAGE_SIZE,
    });
    const detailPromise = filters.missionId
      ? getFinanceiroMissao(filters.missionId)
        .then((payload) => ({ payload, error: null }))
        .catch((error) => ({ payload: null, error }))
      : Promise.resolve({ payload: null, error: null });
    const [listPayload, optionState, detailResult] = await Promise.all([
      listPromise,
      loadFinanceiroMissionOptions(capabilities),
      detailPromise,
    ]);
    renderFinanceiroMissoes({
      filters,
      listPayload,
      optionState,
      detailPayload: detailResult.payload,
      detailError: detailResult.error,
    });
  } catch (error) {
    renderPageState(requestErrorState(error));
  }
}
