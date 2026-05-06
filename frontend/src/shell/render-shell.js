import {
  api,
  buildErrorMessage,
  capabilitySet,
  config,
  consumeFlash,
  enhanceOperationalSurfaces,
  escapeAttr,
  escapeHtml,
  forensicTrace,
  initialsForName,
  routePath,
  showFlash,
  state,
  setDocumentScrollLock,
  trapFocusWithin,
} from "../lib.js";

import {
  renderNavigation,
  resolveActiveNavigation,
} from "./navigation.js";
import { BACKEND_LINKS } from "../compat/backend-links.js";
import { STATIC_ASSETS } from "../compat/static-assets.js";

const SHELL_DRAWER_QUERY = "(max-width: 1024px)";
const SHELL_TABLET_RAIL_QUERY = "(min-width: 1025px) and (max-width: 1279px)";
const SHELL_NOTEBOOK_COLLAPSED_QUERY = "(min-width: 1025px) and (max-width: 1279px)";
const SIDEBAR_DEFAULT_STATE = "expanded";
const SIDEBAR_STATES = new Set(["expanded", "iconic"]);
const SIDEBAR_STATE_ALIASES = new Map([
  ["compact", "iconic"],
  ["collapsed", "iconic"],
  ["rail", "iconic"],
  ["mobileDrawer", SIDEBAR_DEFAULT_STATE],
]);
let shellInteractionAbortController = null;

function normalizeSidebarState(value) {
  if (SIDEBAR_STATE_ALIASES.has(value)) return SIDEBAR_STATE_ALIASES.get(value);
  return SIDEBAR_STATES.has(value) ? value : SIDEBAR_DEFAULT_STATE;
}

function defaultSidebarStateForViewport() {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return SIDEBAR_DEFAULT_STATE;
  }
  if (window.matchMedia(SHELL_DRAWER_QUERY).matches) return SIDEBAR_DEFAULT_STATE;
  if (window.matchMedia(SHELL_TABLET_RAIL_QUERY).matches) return "iconic";
  if (window.matchMedia(SHELL_NOTEBOOK_COLLAPSED_QUERY).matches) return "iconic";
  return SIDEBAR_DEFAULT_STATE;
}

function resolveSidebarStateForViewport(value) {
  const normalizedState = normalizeSidebarState(value);
  if (
    typeof window !== "undefined"
    && typeof window.matchMedia === "function"
    && window.matchMedia(SHELL_DRAWER_QUERY).matches
  ) {
    return SIDEBAR_DEFAULT_STATE;
  }
  if (
    typeof window !== "undefined"
    && typeof window.matchMedia === "function"
    && window.matchMedia(SHELL_TABLET_RAIL_QUERY).matches
    && normalizedState === SIDEBAR_DEFAULT_STATE
  ) {
    return "iconic";
  }
  return normalizedState;
}

function nextSidebarState(value) {
  const normalizedState = normalizeSidebarState(value);
  if (normalizedState === "expanded") return "iconic";
  return SIDEBAR_DEFAULT_STATE;
}

function sidebarModeToggleLabel(value) {
  return normalizeSidebarState(value) === "iconic" ? "Expandir menu" : "Recolher menu";
}

function sidebarStorageKey() {
  const user = state.session?.user || {};
  const userKey = user.id || user.usuario_id || user.login || user.email || user.nome || "anon";
  return `controle-treinamentos:sidebar-state:v2:${String(userKey)}`;
}

function readStoredSidebarState() {
  try {
    if (typeof window === "undefined" || !window.localStorage) return null;
    const storedState = window.localStorage.getItem(sidebarStorageKey());
    if (!storedState) return null;
    return normalizeSidebarState(storedState);
  } catch (_error) {
    return null;
  }
}

function readSidebarState() {
  const storedState = readStoredSidebarState();
  return storedState ? resolveSidebarStateForViewport(storedState) : defaultSidebarStateForViewport();
}

function writeSidebarState(value) {
  try {
    if (typeof window === "undefined" || !window.localStorage) return;
    window.localStorage.setItem(sidebarStorageKey(), normalizeSidebarState(value));
  } catch (_error) {
    // localStorage can be blocked by browser policy; the shell still works without persistence.
  }
}

function renderLogoutIcon() {
  return `
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
      <path d="M16 17l5-5-5-5"></path>
      <path d="M21 12H9"></path>
    </svg>
  `;
}

function renderProfileIcon() {
  return `
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
      <circle cx="12" cy="8" r="4"></circle>
      <path d="M4 21a8 8 0 0 1 16 0"></path>
    </svg>
  `;
}

function renderSidebarModeIcon() {
  return `
    <svg class="sidebar-mode-toggle-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.05" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
      <g class="sidebar-mode-icon-collapse">
        <rect x="4" y="5" width="16" height="14" rx="3"></rect>
        <path d="M9 5v14"></path>
        <path d="M15 9l-3 3 3 3"></path>
      </g>
      <g class="sidebar-mode-icon-expand">
        <rect x="4" y="5" width="16" height="14" rx="3"></rect>
        <path d="M9 5v14"></path>
        <path d="M12 9l3 3-3 3"></path>
      </g>
    </svg>
  `;
}

function flashAccessibilityAttrs(kind) {
  const role = kind === "error" || kind === "warning" ? "alert" : "status";
  const live = role === "alert" ? "assertive" : "polite";
  return `role="${role}" aria-live="${live}"`;
}

export function renderFlashMarkup() {
  const flash = consumeFlash();
  if (!flash) return "";
  const kind = ["success", "warning", "info", "loading"].includes(flash.kind) ? flash.kind : "error";
  return `<div class="flash ${kind} ui-alert" data-kind="${kind}" ${flashAccessibilityAttrs(kind)}>${escapeHtml(flash.message)}</div>`;
}

export function renderInlineFlash(target, message, kind = "error") {
  if (!target) return;
  const normalizedKind = ["success", "warning", "info", "loading"].includes(kind) ? kind : "error";
  if (!message) {
    target.innerHTML = "";
    return;
  }
  target.innerHTML = `<div class="flash ${normalizedKind} ui-alert" data-kind="${normalizedKind}" ${flashAccessibilityAttrs(normalizedKind)}>${escapeHtml(message)}</div>`;
}

function wireShellInteractions() {
  shellInteractionAbortController?.abort();
  shellInteractionAbortController = typeof AbortController === "function" ? new AbortController() : null;
  const listenerOptions = shellInteractionAbortController ? { signal: shellInteractionAbortController.signal } : undefined;
  const passiveListenerOptions = shellInteractionAbortController ? { signal: shellInteractionAbortController.signal, passive: true } : { passive: true };
  const btn = document.getElementById("mobileMenuBtn");
  const closeBtn = document.getElementById("sidebarCloseBtn");
  const modeToggle = document.getElementById("sidebarModeToggle");
  const sidebar = document.getElementById("appSidebar");
  const overlay = document.getElementById("sidebarOverlay");
  const appShell = document.querySelector(".app-shell");
  const mainColumn = document.querySelector(".main-column");
  const drawerQuery = window.matchMedia(SHELL_DRAWER_QUERY);
  const responsiveStateQueries = [
    drawerQuery,
    window.matchMedia(SHELL_TABLET_RAIL_QUERY),
    window.matchMedia(SHELL_NOTEBOOK_COLLAPSED_QUERY),
  ];
  const hoverFlyoutQuery = window.matchMedia("(hover: hover) and (pointer: fine)");
  const navGroupSyncers = [];
  let lastFocusedElement = null;

  function isElementVisible(element) {
    if (!(element instanceof Element)) return false;
    const style = window.getComputedStyle(element);
    return style.display !== "none" && style.visibility !== "hidden" && element.getClientRects().length > 0;
  }

  function firstVisibleFocusable(root, selectors) {
    if (!root) return null;
    return Array.from(root.querySelectorAll(selectors)).find(isElementVisible) || null;
  }

  function isRailMode() {
    if (!sidebar || drawerQuery.matches) return false;
    return responsiveStateQueries[1].matches || normalizeSidebarState(sidebar.dataset.sidebarState) !== SIDEBAR_DEFAULT_STATE;
  }

  function isIconRailMode() {
    if (!sidebar || drawerQuery.matches) return false;
    return responsiveStateQueries[1].matches || normalizeSidebarState(sidebar.dataset.sidebarState) === "iconic";
  }

  function syncAllNavGroups() {
    navGroupSyncers.forEach((syncer) => syncer());
  }

  function tooltipElement() {
    let tooltip = document.getElementById("sidebarRailTooltip");
    if (tooltip) return tooltip;
    tooltip = document.createElement("div");
    tooltip.id = "sidebarRailTooltip";
    tooltip.className = "sidebar-rail-tooltip";
    tooltip.setAttribute("role", "tooltip");
    tooltip.hidden = true;
    document.body.appendChild(tooltip);
    return tooltip;
  }

  function hideRailTooltip(trigger = null) {
    const tooltip = document.getElementById("sidebarRailTooltip");
    if (!tooltip) return;
    tooltip.dataset.state = "closed";
    tooltip.hidden = true;
    if (trigger) {
      trigger.removeAttribute("aria-describedby");
    } else {
      document.querySelectorAll("[aria-describedby='sidebarRailTooltip']").forEach((describedElement) => {
        describedElement.removeAttribute("aria-describedby");
      });
    }
  }

  function showRailTooltip(trigger) {
    if (!(trigger instanceof Element) || drawerQuery.matches) return;
    const isModeToggle = trigger.matches("[data-sidebar-mode-toggle]");
    if (!isIconRailMode() && !isModeToggle) return;
    const label = trigger.getAttribute("data-tooltip");
    if (!label) return;
    const tooltip = tooltipElement();
    tooltip.textContent = label;
    tooltip.hidden = false;
    tooltip.dataset.state = "open";
    trigger.setAttribute("aria-describedby", tooltip.id);
    const rect = trigger.getBoundingClientRect();
    const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 0;
    const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
    const gutter = 10;
    const tooltipRect = tooltip.getBoundingClientRect();
    const left = Math.min(rect.right + 10, Math.max(gutter, viewportWidth - tooltipRect.width - gutter));
    const preferredTop = trigger.matches("[data-nav-toggle]")
      ? rect.top - tooltipRect.height - 6
      : rect.top + (rect.height - tooltipRect.height) / 2;
    const top = Math.min(
      Math.max(gutter, preferredTop),
      Math.max(gutter, viewportHeight - tooltipRect.height - gutter),
    );
    tooltip.style.left = `${Math.round(left)}px`;
    tooltip.style.top = `${Math.round(top)}px`;
  }

  function closeNavFlyouts(except = null) {
    document.querySelectorAll(".nav-group.flyout-open").forEach((openGroup) => {
      if (openGroup === except) return;
      openGroup.classList.remove("flyout-open");
      const openToggle = openGroup.querySelector("[data-nav-toggle]");
      const openLinks = openGroup.querySelector(".nav-group-links");
      openLinks?.style.removeProperty("--nav-flyout-left");
      openLinks?.style.removeProperty("--nav-flyout-top");
      openLinks?.style.removeProperty("--nav-flyout-max-height");
      openLinks?.style.removeProperty("--nav-flyout-width");
      openToggle?.setAttribute("aria-expanded", "false");
      if (openLinks && isRailMode()) openLinks.hidden = true;
    });
  }

  function positionNavFlyout(navGroupEl) {
    if (!isRailMode() || !navGroupEl) return;
    const links = navGroupEl.querySelector(".nav-group-links");
    if (!links || links.hidden) return;
    const rect = navGroupEl.getBoundingClientRect();
    const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 0;
    const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
    const gutter = 12;
    const preferredLeft = Math.round(rect.right + 8);
    const maxAvailableWidth = Math.max(240, viewportWidth - preferredLeft - gutter);
    const flyoutWidth = Math.min(320, maxAvailableWidth);
    const maxHeight = Math.min(520, Math.max(220, viewportHeight - (gutter * 2)));
    const measuredHeight = Math.min(links.scrollHeight || maxHeight, maxHeight);
    const top = Math.min(
      Math.max(gutter, Math.round(rect.top)),
      Math.max(gutter, viewportHeight - measuredHeight - gutter),
    );
    links.style.setProperty("--nav-flyout-left", `${preferredLeft}px`);
    links.style.setProperty("--nav-flyout-top", `${top}px`);
    links.style.setProperty("--nav-flyout-max-height", `${maxHeight}px`);
    links.style.setProperty("--nav-flyout-width", `${flyoutWidth}px`);
  }

  function syncOpenFlyoutPositions() {
    document.querySelectorAll(".nav-group.flyout-open").forEach((openGroup) => positionNavFlyout(openGroup));
  }

  function syncSidebarModeToggle(value) {
    if (!modeToggle) return;
    const normalizedState = normalizeSidebarState(value);
    const label = sidebarModeToggleLabel(normalizedState);
    modeToggle.dataset.sidebarModeState = normalizedState;
    modeToggle.setAttribute("aria-label", label);
    modeToggle.removeAttribute("title");
    modeToggle.setAttribute("data-tooltip", label);
  }

  function setSidebarState(nextState, options = {}) {
    const persist = options.persist !== false;
    const normalizedState = resolveSidebarStateForViewport(nextState);
    if (appShell) appShell.dataset.sidebarState = normalizedState;
    if (sidebar) sidebar.dataset.sidebarState = normalizedState;
    if (persist) writeSidebarState(normalizedState);
    syncSidebarModeToggle(normalizedState);
    closeNavFlyouts();
    hideRailTooltip();
    syncAllNavGroups();
  }

  function syncResponsiveSidebarState() {
    setSidebarState(readStoredSidebarState() || defaultSidebarStateForViewport(), { persist: false });
  }

  function syncDrawerSemantics(isDrawer, isOpen = sidebar?.classList.contains("open")) {
    if (!sidebar) return;
    if (appShell) appShell.dataset.sidebarViewport = isDrawer ? "drawer" : "rail";
    sidebar.dataset.sidebarViewport = isDrawer ? "drawer" : "rail";
    if ("inert" in sidebar) {
      sidebar.inert = isDrawer && !isOpen;
    }
    if (isDrawer) {
      sidebar.setAttribute("role", "dialog");
      if (isOpen) {
        sidebar.setAttribute("aria-modal", "true");
      } else {
        sidebar.removeAttribute("aria-modal");
      }
      sidebar.setAttribute("aria-hidden", isOpen ? "false" : "true");
    } else {
      sidebar.removeAttribute("role");
      sidebar.removeAttribute("aria-modal");
      sidebar.setAttribute("aria-hidden", "false");
    }
  }

  function setMainColumnInert(isInert) {
    if (!mainColumn) return;
    if ("inert" in mainColumn) {
      mainColumn.inert = isInert;
    }
    if (isInert) {
      mainColumn.setAttribute("aria-hidden", "true");
    } else {
      mainColumn.removeAttribute("aria-hidden");
    }
  }

  function setMenuState(isOpen) {
    if (!sidebar || !overlay) return;
    const isDrawer = drawerQuery.matches;
    sidebar.classList.toggle("open", isOpen);
    overlay.classList.toggle("show", isOpen && isDrawer);
    sidebar.dataset.overlayState = isOpen && isDrawer ? "open" : "closed";
    sidebar.dataset.overlaySurface = isDrawer ? "modal-drawer" : "persistent-navigation";
    overlay.dataset.overlayState = isOpen && isDrawer ? "open" : "closed";
    document.body.classList.toggle("sidebar-open", isOpen && isDrawer);
    setDocumentScrollLock("shell-sidebar", isOpen && isDrawer);
    syncDrawerSemantics(isDrawer, isOpen);
    if (btn) {
      btn.setAttribute("aria-expanded", isOpen ? "true" : "false");
      btn.setAttribute("aria-label", isOpen ? "Fechar menu" : "Abrir menu");
    }
    if (closeBtn) {
      closeBtn.setAttribute("aria-expanded", isOpen ? "true" : "false");
    }
    if (isOpen && isDrawer) {
      lastFocusedElement = document.activeElement;
    }
    setMainColumnInert(isOpen && isDrawer);
    syncAllNavGroups();
    if (isOpen && isDrawer) {
      const firstFocusable = firstVisibleFocusable(sidebar, ".sidebar-close-btn, .sidebar-mode-toggle, .sidebar-state-button, .nav-primary-link, .nav-group-toggle, .nav a, .logout-button");
      if (firstFocusable) requestAnimationFrame(() => firstFocusable.focus());
    } else if (isDrawer && lastFocusedElement && typeof lastFocusedElement.focus === "function" && document.contains(lastFocusedElement)) {
      requestAnimationFrame(() => lastFocusedElement.focus());
    }
  }

  if (btn && sidebar && overlay) {
    btn.setAttribute("aria-controls", "appSidebar");
    btn.setAttribute("aria-expanded", "false");
    btn.setAttribute("aria-label", "Abrir menu");
    modeToggle?.addEventListener("click", () => {
      if (drawerQuery.matches) return;
      setSidebarState(nextSidebarState(sidebar.dataset.sidebarState), { persist: true });
    }, listenerOptions);
    if (drawerQuery.matches) {
      setMenuState(false);
    } else {
      syncDrawerSemantics(false, false);
    }
    btn.addEventListener("click", () => setMenuState(!sidebar.classList.contains("open")), listenerOptions);
    closeBtn?.addEventListener("click", () => setMenuState(false), listenerOptions);
    overlay.addEventListener("click", () => setMenuState(false), listenerOptions);
    sidebar.addEventListener("click", (event) => {
      const link = event.target.closest("a");
      if (link && drawerQuery.matches) setMenuState(false);
    }, listenerOptions);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeNavFlyouts();
        hideRailTooltip(document.querySelector("[aria-describedby='sidebarRailTooltip']"));
        syncAllNavGroups();
        setMenuState(false);
        return;
      }
      if (event.key !== "Tab" || !sidebar.classList.contains("open") || !drawerQuery.matches) return;
      trapFocusWithin(sidebar, event);
    }, listenerOptions);
    const onViewportChange = () => {
      closeNavFlyouts();
      hideRailTooltip(document.querySelector("[aria-describedby='sidebarRailTooltip']"));
      syncResponsiveSidebarState();
      if (!drawerQuery.matches) {
        setMenuState(false);
        syncDrawerSemantics(false, false);
      } else if (!sidebar.classList.contains("open")) {
        syncDrawerSemantics(true, false);
      }
      syncAllNavGroups();
      syncOpenFlyoutPositions();
    };
    responsiveStateQueries.forEach((query) => {
      if (typeof query.addEventListener === "function") {
        query.addEventListener("change", onViewportChange, listenerOptions);
      } else if (typeof query.addListener === "function") {
        query.addListener(onViewportChange);
      }
    });
  }

  const navScrollRegion = sidebar?.querySelector(".nav.ui-navigation-list");
  navScrollRegion?.addEventListener("scroll", syncOpenFlyoutPositions, passiveListenerOptions);
  navScrollRegion?.addEventListener("scroll", () => hideRailTooltip(document.querySelector("[aria-describedby='sidebarRailTooltip']")), passiveListenerOptions);
  window.addEventListener("resize", syncOpenFlyoutPositions, passiveListenerOptions);
  window.addEventListener("resize", () => hideRailTooltip(document.querySelector("[aria-describedby='sidebarRailTooltip']")), passiveListenerOptions);

  document.querySelectorAll(".nav-group").forEach((navGroupEl, index) => {
    const toggle = navGroupEl.querySelector("[data-nav-toggle]");
    const links = navGroupEl.querySelector(".nav-group-links");
    if (!toggle) return;
    if (links) {
      links.id = links.id || `nav-group-links-${index + 1}`;
      toggle.setAttribute("aria-controls", links.id);
    }
    const syncNavGroupState = () => {
      const railMode = isRailMode();
      const expanded = navGroupEl.classList.contains("open");
      const flyoutOpen = navGroupEl.classList.contains("flyout-open");
      navGroupEl.dataset.navMode = railMode ? "flyout" : "accordion";
      toggle.setAttribute("aria-expanded", railMode ? (flyoutOpen ? "true" : "false") : (expanded ? "true" : "false"));
      if (links) links.hidden = railMode ? !flyoutOpen : !expanded;
      if (railMode && flyoutOpen) requestAnimationFrame(() => positionNavFlyout(navGroupEl));
    };
    navGroupSyncers.push(syncNavGroupState);
    syncNavGroupState();
    let flyoutCloseTimer = 0;
    const clearFlyoutCloseTimer = () => {
      if (!flyoutCloseTimer) return;
      window.clearTimeout(flyoutCloseTimer);
      flyoutCloseTimer = 0;
    };
    const openRailFlyout = () => {
      if (!isRailMode()) return;
      clearFlyoutCloseTimer();
      closeNavFlyouts(navGroupEl);
      navGroupEl.classList.add("flyout-open");
      syncNavGroupState();
      requestAnimationFrame(() => positionNavFlyout(navGroupEl));
    };
    const scheduleRailFlyoutClose = () => {
      if (!isRailMode()) return;
      clearFlyoutCloseTimer();
      flyoutCloseTimer = window.setTimeout(() => {
        navGroupEl.classList.remove("flyout-open");
        syncNavGroupState();
      }, 160);
    };
    toggle.addEventListener("click", (event) => {
      if (isRailMode()) {
        event.preventDefault();
        const willOpen = !navGroupEl.classList.contains("flyout-open");
        navGroupEl.classList.toggle("flyout-open", willOpen);
        if (willOpen) {
          openRailFlyout();
        } else {
          syncNavGroupState();
        }
        return;
      }
      navGroupEl.classList.remove("flyout-open");
      if (drawerQuery.matches && !navGroupEl.classList.contains("open")) {
        document.querySelectorAll(".nav-group.open").forEach((openGroup) => {
          if (openGroup === navGroupEl) return;
          openGroup.classList.remove("open");
          const openToggle = openGroup.querySelector("[data-nav-toggle]");
          const openLinks = openGroup.querySelector(".nav-group-links");
          openToggle?.setAttribute("aria-expanded", "false");
          if (openLinks) openLinks.hidden = true;
        });
      }
      navGroupEl.classList.toggle("open");
      syncNavGroupState();
    }, listenerOptions);
    navGroupEl.addEventListener("pointerenter", () => {
      if (!hoverFlyoutQuery.matches) return;
      openRailFlyout();
    }, listenerOptions);
    navGroupEl.addEventListener("pointerleave", () => {
      if (!hoverFlyoutQuery.matches) return;
      scheduleRailFlyoutClose();
    }, listenerOptions);
    navGroupEl.addEventListener("focusin", (event) => {
      if (!isRailMode()) return;
      if (event.target === toggle || links?.contains(event.target)) openRailFlyout();
    }, listenerOptions);
    navGroupEl.addEventListener("focusout", () => {
      if (!isRailMode()) return;
      window.setTimeout(() => {
        if (navGroupEl.contains(document.activeElement)) return;
        navGroupEl.classList.remove("flyout-open");
        syncNavGroupState();
      }, 0);
    }, listenerOptions);
    links?.addEventListener("click", (event) => {
      if (!isRailMode()) return;
      const link = event.target.closest("a");
      if (!link) return;
      navGroupEl.classList.remove("flyout-open");
      syncNavGroupState();
    }, listenerOptions);
  });

  sidebar?.querySelectorAll("[data-tooltip]").forEach((trigger) => {
    trigger.addEventListener("pointerenter", () => {
      if (!hoverFlyoutQuery.matches) return;
      showRailTooltip(trigger);
    }, listenerOptions);
    trigger.addEventListener("pointerleave", () => hideRailTooltip(trigger), listenerOptions);
    trigger.addEventListener("focusin", () => showRailTooltip(trigger), listenerOptions);
    trigger.addEventListener("focusout", () => hideRailTooltip(trigger), listenerOptions);
    trigger.addEventListener("click", () => hideRailTooltip(trigger), listenerOptions);
  });

  document.addEventListener("click", (event) => {
    if (!isRailMode() || !sidebar) return;
    const target = event.target;
    if (!(target instanceof Element)) return;
    if (!sidebar.contains(target) || !target.closest(".nav-group")) {
      closeNavFlyouts();
      syncAllNavGroups();
    }
  }, listenerOptions);

  setSidebarState(readSidebarState(), { persist: false });
}

export function renderShell(content, title) {
  const user = state.session?.user;
  const activeRoute = routePath();
  const expectedRoute = state.navigationRender?.routeKey || activeRoute;
  if (expectedRoute && activeRoute && expectedRoute !== activeRoute) {
    forensicTrace("shell.render.skip_stale_route", {
      title,
      expectedRoute,
      activeRoute,
      bootId: state.navigationRender?.bootId || 0,
    }, { assets: true });
    return false;
  }
  forensicTrace("shell.render.begin", {
    title,
    route: activeRoute,
    contentLength: String(content || "").length,
    authenticated: Boolean(state.session?.authenticated),
  }, { assets: true });
  const activeNavigation = resolveActiveNavigation(activeRoute);
  const routeContext = activeNavigation
    ? `${activeNavigation.groupLabel} / ${activeNavigation.itemLabel}`
    : title;
  const sidebarState = readSidebarState();
  const userDisplayName = user?.nome || "";
  const userRole = user?.perfil || "";
  const userInitials = initialsForName(userDisplayName || userRole);
  const sessionLabel = [userDisplayName || "Usuário", userRole].filter(Boolean).join(" - ");
  const sidebarModeLabel = sidebarModeToggleLabel(sidebarState);
  document.body.className = "";
  document.title = `${title} | ${config.appName}`;
  document.getElementById("app").innerHTML = `
    <div class="sidebar-overlay ui-overlay-backdrop" id="sidebarOverlay" data-overlay-backdrop="shell" aria-hidden="true"></div>
    <div class="app-shell ui-app-frame" data-route-context="${escapeAttr(activeNavigation?.groupLabel || "Produto")}" data-sidebar-contract="sidebar-v1" data-sidebar-state="${escapeAttr(sidebarState)}">
      <aside class="sidebar ui-inverse-surface" id="appSidebar" aria-label="Navegação do sistema" data-overlay-panel="navigation-drawer" data-overlay-state="closed" data-sidebar-contract="sidebar-v1" data-sidebar-state="${escapeAttr(sidebarState)}">
        <div class="sidebar-top">
          <button type="button" class="sidebar-close-btn" id="sidebarCloseBtn" aria-label="Fechar menu" aria-controls="appSidebar" aria-expanded="false">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
          <div class="brand-wrap ui-stack-xs">
            <img class="brand-image brand-image-sidebar" src="${STATIC_ASSETS.logoBrasilVida}" alt="Brasilvida">
            <div class="brand-subtitle">Treinamentos e vencimentos da equipe</div>
          </div>
          <button type="button" class="sidebar-mode-toggle" id="sidebarModeToggle" data-sidebar-mode-toggle data-sidebar-mode-state="${escapeAttr(sidebarState)}" data-tooltip="${escapeAttr(sidebarModeLabel)}" aria-label="${escapeAttr(sidebarModeLabel)}">
            ${renderSidebarModeIcon()}
          </button>
        </div>
        <nav class="nav ui-navigation-list" aria-label="Navegação principal">
          ${renderNavigation(activeRoute)}
        </nav>
        <div class="sidebar-footer ui-stack-xs" data-session-footer>
          <div class="session-card" title="${escapeAttr(sessionLabel)}" data-tooltip="${escapeAttr(sessionLabel)}" aria-label="Sessão atual: ${escapeAttr(sessionLabel)}" data-session-surface>
            <span class="session-avatar" aria-hidden="true">${escapeHtml(userInitials)}</span>
            <span class="session-copy">
              <span class="session-caption">Usuário conectado</span>
              <span class="session-user">${escapeHtml(userDisplayName)}</span>
              <span class="session-role">${escapeHtml(userRole)}</span>
            </span>
            <span class="session-presence" aria-label="Sessão ativa">
              <span class="session-presence-dot" aria-hidden="true"></span>
              <span class="session-presence-label">Ativa</span>
            </span>
          </div>
          <div class="session-actions" aria-label="Ações da sessão">
            <div class="session-profile-summary" role="note" aria-label="Papel atual: ${escapeAttr(userRole || "Não informado")}" title="Papel atual">
              <span class="profile-action-icon" aria-hidden="true">${renderProfileIcon()}</span>
              <span class="profile-action-copy">
                <span class="profile-action-label">Perfil local</span>
                <span class="profile-action-value">${escapeHtml(userRole || "Não informado")}</span>
              </span>
            </div>
            <button type="button" class="logout-link logout-button" id="logout-button" aria-label="Sair do sistema" title="Sair do sistema" data-tooltip="Sair do sistema">
              <span class="logout-icon" aria-hidden="true">${renderLogoutIcon()}</span>
              <span class="logout-label">Sair do sistema</span>
            </button>
          </div>
        </div>
      </aside>
      <div class="main-column">
        <header class="topbar ui-sticky-surface">
          <div class="topbar-left">
            <button type="button" class="mobile-menu-btn" id="mobileMenuBtn" aria-label="Abrir menu" aria-controls="appSidebar" aria-expanded="false">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="3" y1="12" x2="21" y2="12"></line>
                <line x1="3" y1="6" x2="21" y2="6"></line>
                <line x1="3" y1="18" x2="21" y2="18"></line>
              </svg>
            </button>
            <div>
              <div class="topbar-title">Treinamentos Brasil Vida</div>
              <div class="topbar-subtitle">${escapeHtml(routeContext)}</div>
            </div>
          </div>
          <div class="topbar-context ui-cluster">
            <span class="route-context-chip">${escapeHtml(activeNavigation?.groupLabel || "Produto")}</span>
            ${capabilitySet().has("notificacoes:view") ? `<a class="topbar-action" href="${BACKEND_LINKS.notificacoesEmail}">E-mails e notificações</a>` : ""}
          </div>
        </header>
        <main class="content ui-content-region">
          ${renderFlashMarkup()}
          ${content}
        </main>
      </div>
    </div>
  `;
  document.getElementById("logout-button")?.addEventListener("click", handleLogout);
  enhanceOperationalSurfaces(document.getElementById("app"));
  wireShellInteractions();
  forensicTrace("shell.render.end", {
    title,
    route: activeRoute,
    activeNavigation: activeNavigation
      ? { groupLabel: activeNavigation.groupLabel, itemLabel: activeNavigation.itemLabel, href: activeNavigation.href }
      : null,
    contentLength: String(content || "").length,
  }, { assets: true });
}

function renderLogoutError(message) {
  const content = document.querySelector("main.content");
  if (!content) return;
  let target = content.querySelector("[data-logout-feedback]");
  if (!target) {
    target = document.createElement("div");
    target.dataset.logoutFeedback = "true";
    content.prepend(target);
  }
  renderInlineFlash(target, message, "error");
}

async function handleLogout() {
  try {
    forensicTrace("logout.begin", { route: routePath() || "" });
    const { data } = await api("/api/v1/session/logout", { method: "POST", handleAuth: false });
    if (data?.code !== "logout_ok" || data?.authenticated !== false) {
      throw new Error("Resposta inesperada ao encerrar a sessão.");
    }
    state.session = null;
    state.csrfToken = "";
    showFlash("Sessão encerrada.", "success");
    forensicTrace("logout.redirect", { to: `${window.location.origin}/#/login` }, { assets: true });
    window.location.replace(`${window.location.origin}/#/login`);
  } catch (error) {
    const message = buildErrorMessage(error);
    showFlash(message, "error");
    renderLogoutError(message);
  }
}

