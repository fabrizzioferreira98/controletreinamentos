import { state } from "../state/app-state.20260430-142420.4368dc041849.js";
import { setCsrfToken } from "./csrf-service.20260430-142420.91513153e829.js";
import { api } from "./api-client.20260430-142420.5a9c7b9d22cd.js";
import { forensicTrace } from "./trace-service.20260430-142420.1b893fc50952.js";

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

