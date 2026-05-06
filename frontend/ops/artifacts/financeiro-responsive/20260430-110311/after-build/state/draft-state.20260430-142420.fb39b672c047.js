export const CRITICAL_DRAFT_TTL_MS = 8 * 60 * 60 * 1000;

const DRAFT_SCHEMA_VERSION = 1;
const DRAFT_STORAGE_PREFIX = "controle_treinamentos.critical_draft.v1";

function storageGet(key) {
  try {
    return window.sessionStorage?.getItem(key) || "";
  } catch (_error) {
    return "";
  }
}

function storageSet(key, value) {
  try {
    window.sessionStorage?.setItem(key, value);
  } catch (_error) {
    // Draft persistence is a resilience layer; forms must still work without storage.
  }
}

function storageRemove(key) {
  try {
    window.sessionStorage?.removeItem(key);
  } catch (_error) {
    // Ignore storage restrictions.
  }
}

function normalizeFormKey(formKey) {
  return String(formKey || "")
    .trim()
    .replace(/[^a-zA-Z0-9:._-]+/g, "_")
    .slice(0, 180);
}

function normalizeDraftValue(value) {
  if (Array.isArray(value)) return value.map((item) => normalizeDraftValue(item));
  if (value && typeof value === "object") return stableDraftObject(value);
  if (typeof value === "boolean") return value;
  if (value === null || value === undefined) return "";
  return String(value);
}

function stableDraftObject(value = {}) {
  return Object.keys(value || {})
    .sort()
    .reduce((acc, key) => {
      acc[key] = normalizeDraftValue(value[key]);
      return acc;
    }, {});
}

export function stableDraftSignature(fields = {}) {
  return JSON.stringify(stableDraftObject(fields));
}

export function draftStorageKey(formKey) {
  const normalized = normalizeFormKey(formKey);
  return normalized ? `${DRAFT_STORAGE_PREFIX}:${normalized}` : "";
}

export function clearDraft(formKey) {
  const key = draftStorageKey(formKey);
  if (!key) return;
  storageRemove(key);
}

export function writeDraft(formKey, fields = {}, { baselineSignature = "", route = "" } = {}) {
  const key = draftStorageKey(formKey);
  const normalizedFields = stableDraftObject(fields);
  if (!key || Object.keys(normalizedFields).length === 0) {
    clearDraft(formKey);
    return null;
  }
  const now = Date.now();
  const payload = {
    version: DRAFT_SCHEMA_VERSION,
    formKey: normalizeFormKey(formKey),
    baselineSignature: String(baselineSignature || ""),
    route: String(route || ""),
    fields: normalizedFields,
    savedAt: now,
    expiresAt: now + CRITICAL_DRAFT_TTL_MS,
  };
  storageSet(key, JSON.stringify(payload));
  return payload;
}

export function readDraft(formKey, baselineSignature = "") {
  const key = draftStorageKey(formKey);
  if (!key) return null;
  const raw = storageGet(key);
  if (!raw) return null;
  try {
    const payload = JSON.parse(raw);
    if (!payload || payload.version !== DRAFT_SCHEMA_VERSION) {
      clearDraft(formKey);
      return null;
    }
    if (Number(payload.expiresAt || 0) <= Date.now()) {
      clearDraft(formKey);
      return null;
    }
    if (String(payload.baselineSignature || "") !== String(baselineSignature || "")) {
      clearDraft(formKey);
      return null;
    }
    if (!payload.fields || typeof payload.fields !== "object" || Array.isArray(payload.fields)) {
      clearDraft(formKey);
      return null;
    }
    return {
      fields: stableDraftObject(payload.fields),
      savedAt: Number(payload.savedAt || 0),
      route: String(payload.route || ""),
      baselineSignature: String(payload.baselineSignature || ""),
    };
  } catch (_error) {
    clearDraft(formKey);
    return null;
  }
}
