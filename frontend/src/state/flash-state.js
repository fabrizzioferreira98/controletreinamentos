import { state } from "./app-state.js";

const FLASH_STORAGE_KEY = "controle_treinamentos.flash.v1";

export function normalizeFlashKind(kind) {
  if (kind === "success" || kind === "warning" || kind === "info" || kind === "loading") return kind;
  return "error";
}

function writeStoredFlash(flash) {
  try {
    window.sessionStorage?.setItem(FLASH_STORAGE_KEY, JSON.stringify(flash));
  } catch (_error) {
    // sessionStorage can be unavailable in restricted browser contexts.
  }
}

function readStoredFlash() {
  try {
    const raw = window.sessionStorage?.getItem(FLASH_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.message) return null;
    return {
      message: String(parsed.message),
      kind: normalizeFlashKind(parsed.kind),
    };
  } catch (_error) {
    return null;
  }
}

function clearStoredFlash() {
  try {
    window.sessionStorage?.removeItem(FLASH_STORAGE_KEY);
  } catch (_error) {
    // best effort only
  }
}

export function showFlash(message, kind = "error") {
  const flash = { message: String(message || ""), kind: normalizeFlashKind(kind) };
  state.flash = flash;
  if (flash.message) writeStoredFlash(flash);
}

export function consumeFlash() {
  const flash = state.flash || readStoredFlash();
  state.flash = null;
  clearStoredFlash();
  return flash;
}

