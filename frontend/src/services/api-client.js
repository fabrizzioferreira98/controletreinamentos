import { config, state } from "../state/app-state.js";
import { showFlash } from "../state/flash-state.js";
import { rememberCurrentRouteForLogin } from "../state/navigation-state.js";
import { applyCsrfHeader, clearCsrfToken } from "./csrf-service.js";
import { clientCorrelationId, createTraceId, forensicTrace } from "./trace-service.js";

const DEFAULT_API_TIMEOUT_MS = 45000;

export function createApiError(message, { status = 0, code = "frontend_api_error", requestId = "", correlationId = "" } = {}) {
  const error = new Error(message);
  error.status = status;
  error.code = code;
  error.requestId = requestId;
  error.correlationId = correlationId;
  return error;
}

function apiTimeoutError(timeoutMs) {
  return createApiError(`Tempo limite excedido após ${Math.round(timeoutMs / 1000)}s.`, {
    code: "timeout",
  });
}

function routePath() {
  const hash = String(window.location.hash || "").trim();
  if (!hash) return "";
  return hash.split("?")[0] || "";
}

function clearAuthState() {
  state.session = null;
  clearCsrfToken();
}

function handleApiErrorSideEffects(error, options = {}) {
  if (error?.code === "auth_user_inactive") {
    clearAuthState();
    showFlash("Seu usuário está inativo. Contate o administrador.", "error");
    if (routePath() !== "#/login") {
      const returnRoute = rememberCurrentRouteForLogin();
      forensicTrace("api.redirect.to_login", {
        reason: "auth_user_inactive",
        from: routePath(),
        returnRoute,
        status: error.status || "",
        code: error.code || "",
      }, { assets: true });
      window.location.hash = "#/login";
    }
    return;
  }
  if (error?.status !== 401 || options.handleAuth === false) return;
  clearAuthState();
  showFlash("Sua sessão expirou. Entre novamente para continuar.", "warning");
  if (routePath() !== "#/login") {
    const returnRoute = rememberCurrentRouteForLogin();
    forensicTrace("api.redirect.to_login", {
      reason: "http_401",
      from: routePath(),
      returnRoute,
      status: error.status || "",
      code: error.code || "",
    }, { assets: true });
    window.location.hash = "#/login";
  }
}

async function readJsonResponse(response, requestId, correlationId = "") {
  try {
    return await response.json();
  } catch (_error) {
    throw createApiError("Resposta inesperada do servidor: JSON inválido.", {
      status: response.status,
      code: "invalid_json",
      requestId,
      correlationId,
    });
  }
}

export async function api(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});
  if (!headers.has("Accept")) headers.set("Accept", "application/json");
  if (options.json) headers.set("Content-Type", "application/json");
  applyCsrfHeader(headers, method);
  if (!headers.has("X-Correlation-ID")) headers.set("X-Correlation-ID", clientCorrelationId());
  if (!headers.has("X-Request-ID")) headers.set("X-Request-ID", createTraceId("webreq"));
  const outboundRequestId = headers.get("X-Request-ID") || "";
  const outboundCorrelationId = headers.get("X-Correlation-ID") || "";
  forensicTrace("api.request.begin", {
    path,
    method,
    route: routePath(),
    handleAuth: options.handleAuth !== false,
    requestId: outboundRequestId,
    correlationId: outboundCorrelationId,
  });

  const timeoutMs = Number(options.timeoutMs ?? config.apiTimeoutMs ?? DEFAULT_API_TIMEOUT_MS);
  const controller = timeoutMs > 0 && typeof AbortController !== "undefined" ? new AbortController() : null;
  const timeoutId = controller ? window.setTimeout(() => controller.abort(), timeoutMs) : null;

  let response;
  try {
    response = await fetch(`${config.apiBaseUrl}${path}`, {
      method,
      headers,
      body: options.json ? JSON.stringify(options.json) : options.body,
      cache: options.cache || "no-store",
      credentials: "include",
      signal: controller?.signal,
    });
  } catch (error) {
    const normalizedError = error?.name === "AbortError"
      ? apiTimeoutError(timeoutMs)
      : createApiError("Não foi possível conectar ao servidor.", {
          code: "network_error",
          requestId: outboundRequestId,
          correlationId: outboundCorrelationId,
        });
    normalizedError.requestId = normalizedError.requestId || outboundRequestId;
    normalizedError.correlationId = normalizedError.correlationId || outboundCorrelationId;
    normalizedError.cause = error;
    forensicTrace("api.request.network_error", {
      path,
      method,
      requestId: normalizedError.requestId,
      correlationId: normalizedError.correlationId,
      error: normalizedError,
    }, { assets: true });
    throw normalizedError;
  } finally {
    if (timeoutId) window.clearTimeout(timeoutId);
  }

  const requestId = response.headers.get("X-Request-ID") || outboundRequestId;
  const correlationId = response.headers.get("X-Correlation-ID") || outboundCorrelationId;
  const contentType = response.headers.get("Content-Type") || "";
  forensicTrace("api.response.headers", {
    path,
    method,
    status: response.status,
    ok: response.ok,
    contentType,
    cacheControl: response.headers.get("Cache-Control") || "",
    etag: response.headers.get("ETag") || "",
    requestId,
    correlationId,
  });

  if (!response.ok && contentType.includes("application/json")) {
    const payload = await readJsonResponse(response, requestId, correlationId);
    const error = new Error(payload.message || `Falha HTTP ${response.status}`);
    error.status = response.status;
    error.code = payload.code;
    error.requestId = payload.request_id || requestId;
    error.correlationId = payload.correlation_id || correlationId;
    forensicTrace("api.response.error_json", {
      path,
      method,
      status: response.status,
      code: error.code,
      requestId: error.requestId,
      correlationId: error.correlationId,
    }, { assets: true });
    handleApiErrorSideEffects(error, options);
    throw error;
  }

  if (!response.ok) {
    const error = new Error(`Falha HTTP ${response.status}`);
    error.status = response.status;
    error.requestId = requestId;
    error.correlationId = correlationId;
    forensicTrace("api.response.error_non_json", {
      path,
      method,
      status: response.status,
      requestId,
      correlationId,
    }, { assets: true });
    handleApiErrorSideEffects(error, options);
    throw error;
  }

  if (contentType.includes("application/json")) {
    const data = await readJsonResponse(response, requestId, correlationId);
    forensicTrace("api.response.ok_json", {
      path,
      method,
      status: response.status,
      requestId,
      correlationId,
      topLevelKeys: data && typeof data === "object" ? Object.keys(data).slice(0, 20) : [],
    });
    return { response, data, requestId, correlationId };
  }

  forensicTrace("api.response.ok_blob", { path, method, status: response.status, requestId, correlationId });
  return { response, data: await response.blob(), requestId, correlationId };
}

