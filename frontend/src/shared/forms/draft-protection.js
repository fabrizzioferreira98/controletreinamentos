import {
  clearDraft,
  readDraft,
  stableDraftSignature,
  writeDraft,
} from "../../state/draft-state.js";
import { forensicTrace } from "../../services/trace-service.js";

const CONTROL_SELECTOR = "input, select, textarea";
const IGNORED_INPUT_TYPES = new Set(["file", "button", "submit", "reset", "image", "hidden"]);
const DEFAULT_LEAVE_MESSAGE = "Ha alteracoes nao salvas nesta tela. Sair agora pode descartar o rascunho local.";
const DEFAULT_RESTORE_MESSAGE = "Rascunho local recuperado. Revise e salve para persistir no sistema.";

const activeContexts = new Set();
let beforeUnloadInstalled = false;
let internalNavigationGuardInstalled = false;

function resolveElement(ref) {
  if (!ref) return null;
  if (typeof ref === "string") return document.getElementById(ref) || document.querySelector(ref);
  return ref;
}

function isControlEligible(control, includeSet) {
  if (!control?.name || !includeSet.has(control.name)) return false;
  if (control.disabled || control.dataset.draftExclude === "true") return false;
  const type = String(control.getAttribute("type") || "").toLowerCase();
  return !IGNORED_INPUT_TYPES.has(type);
}

function collectControls(form, includeSet) {
  return Array.from(form.querySelectorAll(CONTROL_SELECTOR)).filter((control) => isControlEligible(control, includeSet));
}

function readControlValue(controls) {
  const first = controls[0];
  const type = String(first?.getAttribute("type") || "").toLowerCase();
  if (type === "checkbox") {
    if (controls.length === 1) return Boolean(first.checked);
    return controls.filter((control) => control.checked).map((control) => String(control.value || "on"));
  }
  if (type === "radio") {
    return String(controls.find((control) => control.checked)?.value || "");
  }
  return String(first?.value ?? "");
}

function readFormFields(form, includeSet) {
  const grouped = collectControls(form, includeSet).reduce((acc, control) => {
    acc[control.name] = acc[control.name] || [];
    acc[control.name].push(control);
    return acc;
  }, {});
  return Object.keys(grouped).reduce((acc, name) => {
    acc[name] = readControlValue(grouped[name]);
    return acc;
  }, {});
}

function normalizedJson(value) {
  return stableDraftSignature({ value });
}

function diffFromBaseline(currentFields, baselineFields) {
  return Object.keys(currentFields).reduce((acc, name) => {
    if (normalizedJson(currentFields[name]) !== normalizedJson(baselineFields[name])) {
      acc[name] = currentFields[name];
    }
    return acc;
  }, {});
}

function applyFieldValue(controls, value) {
  const first = controls[0];
  const type = String(first?.getAttribute("type") || "").toLowerCase();
  if (type === "checkbox") {
    if (controls.length === 1) {
      first.checked = Boolean(value);
    } else {
      const selected = new Set(Array.isArray(value) ? value.map(String) : []);
      controls.forEach((control) => {
        control.checked = selected.has(String(control.value || "on"));
      });
    }
  } else if (type === "radio") {
    controls.forEach((control) => {
      control.checked = String(control.value || "") === String(value || "");
    });
  } else {
    first.value = String(value ?? "");
  }
  controls.forEach((control) => {
    control.dispatchEvent(new Event("input", { bubbles: true }));
    control.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

function applyDraftFields(form, includeSet, fields) {
  const controls = collectControls(form, includeSet);
  const grouped = controls.reduce((acc, control) => {
    acc[control.name] = acc[control.name] || [];
    acc[control.name].push(control);
    return acc;
  }, {});
  Object.keys(fields || {}).forEach((name) => {
    if (!grouped[name]) return;
    applyFieldValue(grouped[name], fields[name]);
  });
}

function renderRestoreNotice(target, message = DEFAULT_RESTORE_MESSAGE) {
  if (!target) return;
  const notice = document.createElement("div");
  notice.className = "flash warning ui-alert";
  notice.dataset.kind = "warning";
  notice.dataset.draftRestore = "true";
  notice.setAttribute("role", "status");
  notice.setAttribute("aria-live", "polite");
  notice.textContent = message;
  target.appendChild(notice);
}

function contextIsActive(context) {
  return Boolean(context?.form && document.contains(context.form));
}

export function hasDirtyCriticalForms() {
  for (const context of Array.from(activeContexts)) {
    if (!contextIsActive(context)) {
      activeContexts.delete(context);
      continue;
    }
    if (context.isDirty()) return true;
  }
  return false;
}

function clearActiveDrafts(reason) {
  activeContexts.forEach((context) => {
    if (!contextIsActive(context) || !context.isDirty()) return;
    context.clear({ reason });
  });
}

function installBeforeUnloadGuard() {
  if (beforeUnloadInstalled) return;
  beforeUnloadInstalled = true;
  window.addEventListener("beforeunload", (event) => {
    if (!hasDirtyCriticalForms()) return undefined;
    event.preventDefault();
    event.returnValue = "";
    return "";
  });
}

function installInternalNavigationGuard() {
  if (internalNavigationGuardInstalled) return;
  internalNavigationGuardInstalled = true;
  document.addEventListener(
    "click",
    (event) => {
      if (event.defaultPrevented || !hasDirtyCriticalForms()) return;
      const link = event.target?.closest?.("a[href]");
      if (!link || link.target || link.dataset.allowDirtyNavigation === "true") return;
      const href = String(link.getAttribute("href") || "").trim();
      if (!href.startsWith("#/") || href === String(window.location.hash || "")) return;
      if (window.confirm(DEFAULT_LEAVE_MESSAGE)) {
        clearActiveDrafts("user_confirmed_navigation");
        return;
      }
      event.preventDefault();
      event.stopPropagation();
    },
    true,
  );
}

export function wireCriticalFormDraftProtection({
  form,
  formKey,
  baselineFields = {},
  includeFields = null,
  feedbackTarget = null,
  restoreMessage = DEFAULT_RESTORE_MESSAGE,
} = {}) {
  const formEl = resolveElement(form);
  const normalizedFormKey = String(formKey || "").trim();
  if (!formEl || !normalizedFormKey) return null;

  const includeSet = new Set(includeFields || Object.keys(baselineFields));
  const baseline = Object.keys(baselineFields || {}).reduce((acc, name) => {
    if (includeSet.has(name)) acc[name] = baselineFields[name];
    return acc;
  }, {});
  const baselineSignature = stableDraftSignature(baseline);
  let dirty = false;
  let suppressEvents = false;

  function syncDirty({ write = true } = {}) {
    const current = readFormFields(formEl, includeSet);
    const changedFields = diffFromBaseline(current, baseline);
    dirty = Object.keys(changedFields).length > 0;
    formEl.dataset.dirtyState = dirty ? "dirty" : "clean";
    if (!write) return changedFields;
    if (dirty) {
      writeDraft(normalizedFormKey, changedFields, {
        baselineSignature,
        route: window.location.hash || "",
      });
      forensicTrace("critical_draft.write", {
        formKey: normalizedFormKey,
        fieldCount: Object.keys(changedFields).length,
        route: window.location.hash || "",
      });
    } else {
      clearDraft(normalizedFormKey);
    }
    return changedFields;
  }

  function onFormChange() {
    if (suppressEvents) return;
    syncDirty();
  }

  const stored = readDraft(normalizedFormKey, baselineSignature);
  if (stored?.fields && Object.keys(stored.fields).length > 0) {
    suppressEvents = true;
    applyDraftFields(formEl, includeSet, stored.fields);
    suppressEvents = false;
    renderRestoreNotice(resolveElement(feedbackTarget), restoreMessage);
    forensicTrace("critical_draft.restore", {
      formKey: normalizedFormKey,
      fieldCount: Object.keys(stored.fields).length,
      route: stored.route || "",
    });
  }

  formEl.addEventListener("input", onFormChange);
  formEl.addEventListener("change", onFormChange);

  const context = {
    form: formEl,
    formKey: normalizedFormKey,
    isDirty: () => dirty,
    clear({ reason = "manual" } = {}) {
      dirty = false;
      formEl.dataset.dirtyState = "clean";
      clearDraft(normalizedFormKey);
      forensicTrace("critical_draft.clear", {
        formKey: normalizedFormKey,
        reason,
        route: window.location.hash || "",
      });
    },
  };
  activeContexts.add(context);
  installBeforeUnloadGuard();
  installInternalNavigationGuard();
  syncDirty({ write: false });

  return {
    clear: context.clear,
    refresh: syncDirty,
    isDirty: () => dirty,
  };
}
