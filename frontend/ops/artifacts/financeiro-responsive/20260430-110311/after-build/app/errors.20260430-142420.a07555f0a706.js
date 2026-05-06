import {
  buildErrorMessage,
  forensicTrace,
  responsiveStateMarkup,
  showFlash,
} from "../lib.20260430-142420.cf58b4b4395e.js";
import { renderShell } from "../shell.20260430-142420.eed3fe973fa2.js";

export function registerGlobalErrorHandlers() {
  window.addEventListener("error", (event) => {
    forensicTrace("global.error", {
      message: event.message,
      filename: event.filename || "",
      lineno: event.lineno || 0,
      colno: event.colno || 0,
      error: event.error || "",
    }, { assets: true });
    showFlash(`Falha no frontend: ${event.message}`, "error");
  });
  window.addEventListener("unhandledrejection", (event) => {
    forensicTrace("global.unhandledrejection", { reason: event.reason || "" }, { assets: true });
    showFlash(`Falha no frontend: ${event.reason?.message || "Promise rejeitada."}`, "error");
  });
}

export function isSessionValidationUnavailable(error) {
  return ["auth_backend_unavailable", "service_unavailable", "network_error", "timeout"].includes(error?.code)
    || error?.status === 503;
}

export function renderSessionValidationUnavailable(error, retry) {
  forensicTrace("render.session_unavailable", { error }, { assets: true });
  document.body.className = "";
  document.title = "Sessao indisponivel";
  document.getElementById("app").innerHTML = `
    <main class="content">
      <section class="panel ui-surface">
        ${responsiveStateMarkup({
          title: "Nao foi possivel validar sua sessao agora.",
          detail: buildErrorMessage(error),
          actionLabel: "Tentar novamente",
          actionId: "session-retry-button",
          type: "error",
          className: "empty route-state",
        })}
      </section>
    </main>
  `;
  document.getElementById("session-retry-button")?.addEventListener("click", () => void retry());
}

export function renderRouteFailure(error, retry) {
  const message = buildErrorMessage(error);
  forensicTrace("render.route_failure", { error, message }, { assets: true });
  showFlash(message, "error");
  // Contract keeps id="route-retry-button" for the retry action rendered by responsiveStateMarkup.
  renderShell(`
    <section class="panel ui-surface">
      ${responsiveStateMarkup({
        title: "Não foi possível carregar esta tela.",
        detail: message,
        actionLabel: "Tentar novamente",
        actionId: "route-retry-button",
        type: "error",
        className: "empty route-state",
      })}
    </section>
  `, "Falha ao carregar");
  document.getElementById("route-retry-button")?.addEventListener("click", () => void retry());
}

