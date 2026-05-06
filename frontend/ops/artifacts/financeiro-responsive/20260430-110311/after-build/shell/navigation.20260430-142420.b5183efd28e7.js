import {
  capabilitySet,
  escapeAttr,
  escapeHtml,
} from "../lib.20260430-142420.cf58b4b4395e.js";
import {
  BACKEND_LINK_BOUNDARIES,
  BACKEND_LINKS,
} from "../compat/backend-links.20260430-142420.db0529350261.js";

export const NAV_GROUPS = [
  {
    label: "Dashboards",
    icon: "dashboard",
    items: [
      { label: "Painel Geral", href: "#/dashboard", permission: "dashboard:view", match: (route) => route === "#/dashboard", icon: "dashboard", primary: true },
    ],
  },
  {
    label: "Operações",
    icon: "operations",
    items: [
      { label: "Gestão de Bases", href: BACKEND_LINKS.bases, permission: "bases:view", icon: "pin" },
    ],
  },
  {
    label: "Relatórios",
    icon: "reports",
    items: [
      { label: "Consolidado de habilitações", href: "#/relatorios/habilitacoes", permission: "relatorio_habilitacoes:view", match: (route) => route === "#/relatorios/habilitacoes", icon: "bars" },
      { label: "Relatório individual", href: "#/relatorios/individual", permission: "relatorio_individual:view", match: (route) => route === "#/relatorios/individual", icon: "user" },
    ],
  },
  {
    label: "Financeiro",
    icon: "bars",
    items: [
      { label: "Missões", href: "#/financeiro/missoes", permission: "finance:missions:read", match: (route) => route.startsWith("#/financeiro/missoes"), icon: "operations" },
      { label: "Bonificações", href: "#/financeiro/bonificacoes", permission: "finance:bonuses:read", match: (route) => route.startsWith("#/financeiro/bonificacoes"), icon: "bars" },
      { label: "Fechamento e Parâmetros", href: "#/financeiro/fechamento-parametros", permissions: ["finance:parameters:read", "finance:periods:read"], match: (route) => route.startsWith("#/financeiro/fechamento-parametros"), icon: "database" },
    ],
  },
  {
    label: "Cadastros",
    icon: "records",
    items: [
      { label: "Tripulantes", href: "#/tripulantes", permissions: ["tripulantes:view", "relatorio_individual:view"], match: (route) => route.startsWith("#/tripulantes"), icon: "crew" },
      { label: "Treinamentos por tripulante", href: "#/treinamentos", permission: "treinamentos:view", match: (route) => route === "#/treinamentos" || /^#\/treinamentos\/\d+$/.test(route) || route === "#/treinamentos/new", icon: "training" },
      { label: "Equipamentos", href: BACKEND_LINKS.equipamentos, permission: "equipamentos:view", icon: "wrench" },
      { label: "Cadastro raiz treinamentos", href: "#/treinamentos/raiz", permission: "tipos_treinamento:view", match: (route) => route === "#/treinamentos/raiz", icon: "database" },
    ],
  },
  {
    label: "Usuários",
    icon: "users",
    items: [
      { label: "Usuários", href: BACKEND_LINKS.usuarios, permission: "usuarios:view", icon: "users" },
      { label: "Monitoramento", href: BACKEND_LINKS.monitoramento, permission: "monitoramento:view", icon: "monitor" },
      { label: "Guia do usuário (PDF)", href: BACKEND_LINKS.manualUsuarioPdf, permission: "monitoramento:view", icon: "document" },
      { label: "Destinatários de e-mail", href: BACKEND_LINKS.notificacoesEmail, permission: "notificacoes:view", icon: "mail" },
      { label: "Backups", href: BACKEND_LINKS.backups, permission: "backups:view", icon: "cloud" },
      { label: "Log de ações", href: BACKEND_LINKS.auditoria, permission: "auditoria:view", icon: "list" },
    ],
  },
];

const NAV_ICON_SVGS = Object.freeze({
  bars: `<svg class="nav-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M6 20V10"></path><path d="M12 20V4"></path><path d="M18 20v-7"></path></svg>`,
  bed: `<svg class="nav-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M4 18V6"></path><path d="M4 13h16"></path><path d="M20 18v-6a3 3 0 0 0-3-3H9v4"></path><path d="M7 9h2"></path></svg>`,
  cloud: `<svg class="nav-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M17.5 18H7a4 4 0 1 1 .8-7.9 5.5 5.5 0 0 1 10.4 1.7A3.2 3.2 0 0 1 17.5 18Z"></path></svg>`,
  crew: `<svg class="nav-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M16 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2"></path><circle cx="9.5" cy="7" r="4"></circle><path d="M22 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>`,
  dashboard: `<svg class="nav-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><rect x="4" y="4" width="6" height="6" rx="1.4"></rect><rect x="14" y="4" width="6" height="6" rx="1.4"></rect><rect x="4" y="14" width="6" height="6" rx="1.4"></rect><rect x="14" y="14" width="6" height="6" rx="1.4"></rect></svg>`,
  database: `<svg class="nav-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><ellipse cx="12" cy="5" rx="7" ry="3"></ellipse><path d="M5 5v14c0 1.7 3.1 3 7 3s7-1.3 7-3V5"></path><path d="M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3"></path></svg>`,
  document: `<svg class="nav-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z"></path><path d="M14 3v5h5"></path><path d="M9 13h6"></path><path d="M9 17h4"></path></svg>`,
  list: `<svg class="nav-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M9 6h11"></path><path d="M9 12h11"></path><path d="M9 18h11"></path><path d="M4 6h.01"></path><path d="M4 12h.01"></path><path d="M4 18h.01"></path></svg>`,
  mail: `<svg class="nav-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><rect x="3" y="5" width="18" height="14" rx="2"></rect><path d="m4 7 8 6 8-6"></path></svg>`,
  monitor: `<svg class="nav-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><rect x="3" y="4" width="18" height="13" rx="2"></rect><path d="M8 21h8"></path><path d="M12 17v4"></path><path d="m7 12 3-3 3 3 4-5"></path></svg>`,
  operations: `<svg class="nav-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M5 16c3.5-.8 7.2-3.8 9-7.8l1.7-3.7 3.8 3.8-3.7 1.7c-4 1.8-7 5.5-7.8 9l-1.2-2.8Z"></path><path d="M14 8l2 2"></path><path d="M5 19l3-3"></path></svg>`,
  pin: `<svg class="nav-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z"></path><circle cx="12" cy="10" r="2.5"></circle></svg>`,
  records: `<svg class="nav-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M4 7h16"></path><path d="M4 12h16"></path><path d="M4 17h10"></path><path d="M6 3h12a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z"></path></svg>`,
  reports: `<svg class="nav-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M5 20V10"></path><path d="M12 20V4"></path><path d="M19 20v-7"></path></svg>`,
  rocket: `<svg class="nav-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M5 15c1-5 4-9 9-11 2-.8 4-.8 5-.3.5 1 .5 3-.3 5-2 5-6 8-11 9Z"></path><path d="M14 6l4 4"></path><path d="M6 18l-2 2"></path><path d="M9 19l-1 2"></path></svg>`,
  training: `<svg class="nav-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="m3 7 9-4 9 4-9 4-9-4Z"></path><path d="M7 10v5c0 1.8 2.2 3 5 3s5-1.2 5-3v-5"></path></svg>`,
  user: `<svg class="nav-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><circle cx="12" cy="8" r="4"></circle><path d="M4 21a8 8 0 0 1 16 0"></path></svg>`,
  userPlus: `<svg class="nav-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><circle cx="9" cy="8" r="4"></circle><path d="M2 21a7 7 0 0 1 14 0"></path><path d="M19 8v6"></path><path d="M16 11h6"></path></svg>`,
  users: `<svg class="nav-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M22 21v-2a4 4 0 0 0-3-3.9"></path><path d="M16 3.1a4 4 0 0 1 0 7.8"></path></svg>`,
  wrench: `<svg class="nav-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M14.7 6.3a4 4 0 0 0 5 5L11 20a2.8 2.8 0 1 1-4-4l8.7-8.7Z"></path></svg>`,
});

function navigationIcon(name) {
  return NAV_ICON_SVGS[name] || NAV_ICON_SVGS.document;
}

function itemBoundary(item) {
  if (item.href.startsWith("#")) return "spa_viva";
  return BACKEND_LINK_BOUNDARIES[item.href] || "ambigua_pendente";
}

function isItemActive(item, activeRoute) {
  if (typeof item.match === "function") {
    return item.match(activeRoute);
  }
  if (item.href.startsWith("#")) {
    return item.href === activeRoute;
  }
  return window.location.pathname === item.href;
}

function itemAllowed(item, granted) {
  const permissions = item.permissions || (item.permission ? [item.permission] : []);
  if (!permissions.length) return true;
  return permissions.some((permission) => granted.has(permission));
}

export function resolveActiveNavigation(activeRoute) {
  const granted = capabilitySet();
  for (const group of NAV_GROUPS) {
    const items = group.items.filter((item) => itemAllowed(item, granted));
    const item = items.find((candidate) => isItemActive(candidate, activeRoute));
    if (item) {
      return {
        groupLabel: group.label,
        itemLabel: item.label,
        href: item.href,
      };
    }
  }
  return null;
}

export function renderNavigation(activeRoute) {
  const granted = capabilitySet();
  const visibleGroups = NAV_GROUPS
    .map((group) => {
      const items = group.items.filter((item) => itemAllowed(item, granted));
      return {
        group,
        groupItems: items.filter((item) => !item.primary),
        primaryItems: items.filter((item) => item.primary),
      };
    })
    .filter(({ groupItems, primaryItems }) => groupItems.length || primaryItems.length);

  const primaryMarkup = visibleGroups
    .flatMap(({ primaryItems }) => primaryItems)
    .map((item) => renderNavItem(item, activeRoute, "nav-primary-link"))
    .join("");

  const groupMarkup = visibleGroups
    .map(({ group, groupItems }) => {
      if (!groupItems.length) return "";
      const groupActive = groupItems.some((item) => isItemActive(item, activeRoute));
      return `
        <div class="nav-group ${groupActive ? "open nav-group-active" : ""}" data-nav-group="${escapeAttr(group.label)}" data-nav-active-child="${groupActive ? "true" : "false"}">
          <button type="button" class="nav-group-toggle ${groupActive ? "active" : ""}" data-nav-toggle data-nav-active="${groupActive ? "true" : "false"}" aria-label="${escapeAttr(group.label)}" title="${escapeAttr(group.label)}" data-tooltip="${escapeAttr(group.label)}" aria-haspopup="true">
            <span class="nav-active-indicator" aria-hidden="true"></span>
            ${navigationIcon(group.icon)}
            <span class="nav-group-label">${escapeHtml(group.label)}</span>
            <span class="nav-group-caret" aria-hidden="true">&#9662;</span>
          </button>
          <div class="nav-group-links">
            <div class="nav-flyout-title" aria-hidden="true">${escapeHtml(group.label)}</div>
            ${groupItems.map((item) => renderNavItem(item, activeRoute)).join("")}
          </div>
        </div>
      `;
    })
    .join("");

  return `
    ${primaryMarkup ? `<div class="nav-primary">${primaryMarkup}</div>` : ""}
    ${groupMarkup}
  `;
}

function renderNavItem(item, activeRoute, className = "") {
  const itemActive = isItemActive(item, activeRoute);
  const classes = ["nav-link", className, itemActive ? "active" : ""].filter(Boolean).join(" ");
  const navLevel = item.primary ? "primary" : "subitem";
  return `
    <a href="${escapeAttr(item.href)}" class="${escapeAttr(classes)}" data-nav-active="${itemActive ? "true" : "false"}" data-nav-boundary="${escapeAttr(itemBoundary(item))}" data-nav-level="${escapeAttr(navLevel)}" data-tooltip="${escapeAttr(item.label)}" aria-label="${escapeAttr(item.label)}" title="${escapeAttr(item.label)}" ${itemActive ? 'aria-current="page"' : ""}>
      <span class="nav-active-indicator" aria-hidden="true"></span>
      ${navigationIcon(item.icon)}
      <span class="nav-link-label">${escapeHtml(item.label)}</span>
    </a>
  `;
}

