import {
  capabilitySet,
  forensicTrace,
  responsiveStateMarkup,
} from "../lib.js";
import { renderShell } from "../shell.js";

export function routeAllowed(routeConfig) {
  const permissions = routeConfig?.permissions || [];
  if (!permissions.length) return true;
  const granted = capabilitySet();
  const allowed = permissions.some((permission) => granted.has(permission));
  forensicTrace("guard.route_allowed", {
    permissions,
    grantedCount: granted.size,
    allowed,
  });
  return allowed;
}

export function renderForbiddenRoute() {
  forensicTrace("guard.render_forbidden", { route: window.location.hash || "" }, { assets: true });
  renderShell(`
    <section class="panel ui-surface">
      ${responsiveStateMarkup({
        title: "Acesso negado.",
        detail: "Voce nao tem permissao para acessar esta funcionalidade.",
        type: "no-permission",
        className: "empty route-state",
      })}
    </section>
  `, "Acesso negado");
}

