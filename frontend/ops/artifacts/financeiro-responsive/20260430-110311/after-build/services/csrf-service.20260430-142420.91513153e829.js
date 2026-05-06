import { state } from "../state/app-state.20260430-142420.4368dc041849.js";

export function getCsrfToken() {
  return state.csrfToken || "";
}

export function setCsrfToken(value = "") {
  state.csrfToken = value || "";
  return state.csrfToken;
}

export function clearCsrfToken() {
  state.csrfToken = "";
}

export function applyCsrfHeader(headers, method) {
  if (!["GET", "HEAD"].includes(method) && getCsrfToken() && !headers.has("X-CSRFToken")) {
    headers.set("X-CSRFToken", getCsrfToken());
  }
  return headers;
}

