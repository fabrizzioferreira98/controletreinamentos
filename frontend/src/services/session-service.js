import { state } from "../state/app-state.js";
import { setCsrfToken } from "./csrf-service.js";
import { api } from "./api-client.js";
import { forensicTrace } from "./trace-service.js";

export async function refreshSession() {
  forensicTrace("session.service.refresh.begin", { route: window.location.hash || "" });
  const { data } = await api("/api/v1/session", { handleAuth: false });
  state.session = data;
  setCsrfToken(data.csrf_token || "");
  forensicTrace("session.service.refresh.end", {
    authenticated: Boolean(data?.authenticated),
    hasUser: Boolean(data?.user),
    permissions: data?.capabilities?.granted_permissions?.length || 0,
    csrf: data?.csrf_token ? "present" : "absent",
  });
  return data;
}

