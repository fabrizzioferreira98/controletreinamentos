import { api, capabilitySet, config, consumeFlash, escapeHtml, routePath, showFlash, state } from "./lib.js?v=20260408-150141";

const NAV_GROUPS = [
  {
    label: "Dashboards",
    items: [
      { label: "Visão geral", href: "#/dashboard", permission: "dashboard:view", match: (route) => route === "#/dashboard" || route === "" },
      { label: "Painel TV vencimentos", href: "/painel-tv", permission: "tv_vencimentos:view" },
      { label: "Painel TV produtividade", href: "/produtividade/painel-tv", permission: "tv_produtividade:view" },
    ],
  },
  {
    label: "Operações",
    items: [
      { label: "Missões", href: "/missoes", permission: "missoes:view" },
      { label: "Pernoites", href: "/pernoites", permission: "pernoites:view" },
      { label: "Gestão de Bases", href: "/bases", permission: "bases:view" },
    ],
  },
  {
    label: "Relatórios",
    items: [
      { label: "Consolidado de habilitações", href: "#/relatorios/habilitacoes", permission: "relatorio_habilitacoes:view", match: (route) => route === "#/relatorios/habilitacoes" },
      { label: "Relatório individual", href: "#/relatorios/individual", permission: "relatorio_individual:view", match: (route) => route === "#/relatorios/individual" },
      { label: "Relatório geral de produtividade", href: "#/relatorios/produtividade", permission: "relatorio_produtividade:view", match: (route) => route === "#/relatorios/produtividade" },
    ],
  },
  {
    label: "Cadastros",
    items: [
      { label: "Tripulantes", href: "#/tripulantes", permission: "tripulantes:view", match: (route) => route.startsWith("#/tripulantes") },
      { label: "Treinamentos por tripulante", href: "#/treinamentos", permission: "treinamentos:view", match: (route) => route === "#/treinamentos" || /^#\/treinamentos\/\d+$/.test(route) || route === "#/treinamentos/new" },
      { label: "Equipamentos", href: "/equipamentos", permission: "equipamentos:view" },
      { label: "Cadastro raiz treinamentos", href: "#/treinamentos/raiz", permission: "tipos_treinamento:view", match: (route) => route === "#/treinamentos/raiz" },
    ],
  },
  {
    label: "Usuários",
    items: [
      { label: "Usuários", href: "/usuarios", permission: "usuarios:view" },
      { label: "Novo usuário", href: "/usuarios/novo", permission: "usuarios:manage" },
      { label: "Monitoramento", href: "/monitoramento", permission: "monitoramento:view" },
      { label: "Guia do usuário (PDF)", href: "/manual/usuario.pdf", permission: "monitoramento:view" },
      { label: "Destinatários de e-mail", href: "/notificacoes-email", permission: "notificacoes:view" },
      { label: "Backups", href: "/backups", permission: "backups:view" },
      { label: "Log de ações", href: "/auditoria", permission: "auditoria:view" },
    ],
  },
];

function renderFlashMarkup() {
  const flash = consumeFlash();
  if (!flash) return "";
  const kind = flash.kind === "success" ? "success" : (flash.kind === "warning" ? "warning" : "error");
  return `<div class="flash ${kind}">${escapeHtml(flash.message)}</div>`;
}

function renderInlineFlash(target, message, kind = "error") {
  if (!target) return;
  const normalizedKind = kind === "success" ? "success" : (kind === "warning" ? "warning" : "error");
  if (!message) {
    target.innerHTML = "";
    return;
  }
  target.innerHTML = `<div class="flash ${normalizedKind}">${escapeHtml(message)}</div>`;
}

async function refreshLoginSession() {
  const response = await fetch(`${config.apiBaseUrl}/api/v1/session`, {
    method: "GET",
    headers: { Accept: "application/json" },
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(`Falha HTTP ${response.status}`);
  }
  const payload = await response.json();
  state.session = payload;
  state.csrfToken = payload.csrf_token || "";
  return payload;
}

async function submitLoginRequest(payload) {
  await refreshLoginSession();
  try {
    return await api("/api/v1/session/login", {
      method: "POST",
      json: payload,
    });
  } catch (error) {
    if (error?.code !== "csrf_error") throw error;
    await refreshLoginSession();
    return api("/api/v1/session/login", {
      method: "POST",
      json: payload,
    });
  }
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

function renderNavigation(activeRoute) {
  const granted = capabilitySet();
  return NAV_GROUPS
    .map((group) => {
      const items = group.items.filter((item) => granted.has(item.permission));
      if (!items.length) return "";
      const groupActive = items.some((item) => isItemActive(item, activeRoute));
      return `
        <div class="nav-group ${groupActive ? "open" : ""}">
          <button type="button" class="nav-group-toggle ${groupActive ? "active" : ""}" data-nav-toggle>
            ${escapeHtml(group.label)}
            <span class="nav-group-caret">&#9662;</span>
          </button>
          <div class="nav-group-links">
            ${items
              .map(
                (item) => `
                  <a href="${item.href}" class="${isItemActive(item, activeRoute) ? "active" : ""}">
                    ${escapeHtml(item.label)}
                  </a>
                `,
              )
              .join("")}
          </div>
        </div>
      `;
    })
    .join("");
}

function wireShellInteractions() {
  const btn = document.getElementById("mobileMenuBtn");
  const sidebar = document.getElementById("appSidebar");
  const overlay = document.getElementById("sidebarOverlay");
  const mainColumn = document.querySelector(".main-column");
  const mobileQuery = window.matchMedia("(max-width: 900px)");
  let lastFocusedElement = null;

  function setMenuState(isOpen) {
    if (!sidebar || !overlay) return;
    sidebar.classList.toggle("open", isOpen);
    overlay.classList.toggle("show", isOpen);
    document.body.classList.toggle("sidebar-open", isOpen);
    sidebar.setAttribute("aria-hidden", isOpen ? "false" : "true");
    if (btn) {
      btn.setAttribute("aria-expanded", isOpen ? "true" : "false");
      btn.setAttribute("aria-label", isOpen ? "Fechar menu" : "Abrir menu");
    }
    if (mainColumn) {
      if (isOpen) {
        mainColumn.setAttribute("aria-hidden", "true");
      } else {
        mainColumn.removeAttribute("aria-hidden");
      }
    }
    if (isOpen) {
      lastFocusedElement = document.activeElement;
      const firstFocusable = sidebar.querySelector(".nav-group-toggle, .nav a, .logout-button");
      if (firstFocusable) requestAnimationFrame(() => firstFocusable.focus());
    } else if (lastFocusedElement && typeof lastFocusedElement.focus === "function" && document.contains(lastFocusedElement)) {
      requestAnimationFrame(() => lastFocusedElement.focus());
    }
  }

  if (btn && sidebar && overlay) {
    btn.setAttribute("aria-controls", "appSidebar");
    btn.setAttribute("aria-expanded", "false");
    btn.setAttribute("aria-label", "Abrir menu");
    sidebar.setAttribute("aria-hidden", "true");
    btn.addEventListener("click", () => setMenuState(!sidebar.classList.contains("open")));
    overlay.addEventListener("click", () => setMenuState(false));
    sidebar.addEventListener("click", (event) => {
      const link = event.target.closest("a");
      if (link && mobileQuery.matches) setMenuState(false);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") setMenuState(false);
    });
    const onViewportChange = (event) => {
      if (!event.matches) setMenuState(false);
    };
    if (typeof mobileQuery.addEventListener === "function") {
      mobileQuery.addEventListener("change", onViewportChange);
    } else if (typeof mobileQuery.addListener === "function") {
      mobileQuery.addListener(onViewportChange);
    }
  }

  document.querySelectorAll(".nav-group").forEach((navGroupEl) => {
    const toggle = navGroupEl.querySelector("[data-nav-toggle]");
    if (!toggle) return;
    toggle.setAttribute("aria-expanded", navGroupEl.classList.contains("open") ? "true" : "false");
    toggle.addEventListener("click", () => {
      if (mobileQuery.matches && !navGroupEl.classList.contains("open")) {
        document.querySelectorAll(".nav-group.open").forEach((openGroup) => {
          if (openGroup === navGroupEl) return;
          openGroup.classList.remove("open");
          openGroup.querySelector("[data-nav-toggle]")?.setAttribute("aria-expanded", "false");
        });
      }
      navGroupEl.classList.toggle("open");
      toggle.setAttribute("aria-expanded", navGroupEl.classList.contains("open") ? "true" : "false");
    });
  });
}

export function renderShell(content, title) {
  const user = state.session?.user;
  const activeRoute = routePath() || "#/dashboard";
  document.body.className = "";
  document.title = `${title} | ${config.appName}`;
  document.getElementById("app").innerHTML = `
    <div class="sidebar-overlay" id="sidebarOverlay"></div>
    <div class="app-shell">
      <aside class="sidebar" id="appSidebar">
        <div class="sidebar-top">
          <div class="brand-wrap">
            <img class="brand-image brand-image-sidebar" src="/static/logo-brasilvida.svg" alt="Brasilvida">
            <div class="brand-subtitle">Treinamentos e vencimentos da equipe</div>
          </div>
        </div>
        <nav class="nav">
          ${renderNavigation(activeRoute)}
        </nav>
        <div class="sidebar-footer">
          <div class="session-caption">Sessão iniciada como</div>
          <div class="session-user">${escapeHtml(user?.nome || "")}</div>
          <div class="session-role">${escapeHtml(user?.perfil || "")}</div>
          <button type="button" class="logout-link logout-button" id="logout-button">Sair</button>
        </div>
      </aside>
      <div class="main-column">
        <header class="topbar">
          <div class="topbar-left">
            <button class="mobile-menu-btn" id="mobileMenuBtn" aria-label="Abrir menu">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="3" y1="12" x2="21" y2="12"></line>
                <line x1="3" y1="6" x2="21" y2="6"></line>
                <line x1="3" y1="18" x2="21" y2="18"></line>
              </svg>
            </button>
            <div>
              <div class="topbar-title">Treinamentos Brasil Vida</div>
              <div class="topbar-subtitle">Um lugar único para acompanhar cadastros, treinamentos e vencimentos.</div>
            </div>
          </div>
          ${capabilitySet().has("notificacoes:view") ? '<div><a class="topbar-action" href="/notificacoes-email">E-mails e notificações</a></div>' : ""}
        </header>
        <main class="content">
          ${renderFlashMarkup()}
          ${content}
        </main>
      </div>
    </div>
  `;
  document.getElementById("logout-button")?.addEventListener("click", handleLogout);
  wireShellInteractions();
}

export function renderLoginPage(onLoggedIn) {
  document.body.className = "login-body";
  document.title = `Login | ${config.appName}`;
  document.getElementById("app").innerHTML = `
    <div class="login-background" aria-hidden="true">
      <span class="login-orb login-orb-one"></span>
      <span class="login-orb login-orb-two"></span>
      <span class="login-grid-glow"></span>
    </div>
    <main class="login-shell login-shell-spa">
      <section class="login-visual login-entrance" aria-hidden="true">
        <div class="login-visual-photo-wrap">
          <img
            class="login-visual-photo"
            src="/static/login-citation-jet.jpg?v=20260408-150141"
            alt=""
            loading="eager"
            fetchpriority="high"
            decoding="async"
          >
        </div>
        <div class="login-visual-content login-fade login-delay-1">
          <div class="login-visual-brand">
            <img class="brand-image brand-image-login-visual" src="/static/logo-brasilvida.svg" alt="Brasil Vida">
            <span class="login-visual-badge">Servidor local &bull; acesso protegido</span>
          </div>
          <div class="login-visual-copy">
            <span class="login-eyebrow">Treinamentos Brasil Vida</span>
            <h1>Referência em transporte aeromédico.</h1>
            <p>Entre para acompanhar vencimentos, cadastros, produtividade e a rotina operacional com um fluxo mais rápido e confiável.</p>
          </div>
          <div class="login-visual-metrics">
            <article class="login-metric-card">
              <span class="login-metric-label">Sessão</span>
              <strong>Autenticação com CSRF</strong>
            </article>
            <article class="login-metric-card">
              <span class="login-metric-label">Ambiente</span>
              <strong>Infraestrutura local</strong>
            </article>
            <article class="login-metric-card">
              <span class="login-metric-label">Foco</span>
              <strong>Leitura rápida e operação contínua</strong>
            </article>
          </div>
        </div>
      </section>

      <section class="login-panel">
        <div class="login-panel-header login-fade login-delay-2">
          <span class="login-chip">Acesso autenticado</span>
          <h2>Entrar no sistema</h2>
          <p>Use suas credenciais para acessar os módulos operacionais, atualizar cadastros e acompanhar a equipe com segurança.</p>
        </div>

        <div class="login-feedback" role="status" aria-live="polite">
          ${renderFlashMarkup()}
        </div>

        <form id="login-form" class="login-form login-fade login-delay-3">
          <div class="login-field">
            <label for="login-username">Login</label>
            <div class="login-input-shell">
              <input id="login-username" type="text" name="login" autocomplete="username" autocapitalize="off" spellcheck="false" required autofocus>
            </div>
          </div>

          <div class="login-field">
            <div class="login-field-heading">
              <label for="login-password">Senha</label>
              <span class="login-inline-note">Credencial administrativa do ambiente</span>
            </div>
            <div class="login-input-shell login-input-shell-password">
              <input id="login-password" type="password" name="senha" autocomplete="current-password" required>
              <button
                type="button"
                class="login-password-toggle"
                data-login-password-toggle
                aria-controls="login-password"
                aria-pressed="false"
                aria-label="Mostrar senha"
              >
                Mostrar
              </button>
            </div>
          </div>

          <div class="login-form-meta">
            <label class="login-remember-field">
              <input class="login-remember-checkbox" type="checkbox" name="remember" value="1" checked>
              <span>Manter conectado neste dispositivo</span>
            </label>
            <div class="login-form-trust">Sessão protegida e validada a cada requisição.</div>
          </div>

          <button type="submit" class="login-submit" data-login-submit>Entrar agora</button>
        </form>

        <div class="login-support-note login-fade login-delay-4">
          Para redefinição de senha ou liberação de acesso, solicite suporte ao administrador responsável por este ambiente.
        </div>
      </section>
    </main>
  `;

  const passwordToggle = document.querySelector("[data-login-password-toggle]");
  const passwordInput = document.getElementById("login-password");
  const feedbackEl = document.querySelector(".login-feedback");
  const formEl = document.getElementById("login-form");

  void refreshLoginSession().catch(() => {
    renderInlineFlash(
      feedbackEl,
      "Não foi possível preparar a sessão do navegador. Se o problema persistir, recarregue a página.",
      "warning",
    );
  });

  passwordToggle?.addEventListener("click", () => {
    if (!passwordInput) return;
    const reveal = passwordInput.type === "password";
    passwordInput.type = reveal ? "text" : "password";
    passwordToggle.textContent = reveal ? "Ocultar" : "Mostrar";
    passwordToggle.setAttribute("aria-pressed", reveal ? "true" : "false");
    passwordToggle.setAttribute("aria-label", reveal ? "Ocultar senha" : "Mostrar senha");
  });

  formEl?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const submitButton = document.querySelector("[data-login-submit]");
    const payload = {
      login: form.get("login"),
      senha: form.get("senha"),
      remember: form.get("remember") ? "1" : "0",
    };

    renderInlineFlash(feedbackEl, "");
    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = "Entrando...";
    }
    try {
      await submitLoginRequest(payload);
      showFlash("Login realizado com sucesso.", "success");
      window.location.hash = "#/dashboard";
      await onLoggedIn();
    } catch (error) {
      const message = error?.code === "csrf_error"
        ? "Sua sessão expirou ou ficou inconsistente. Atualizamos a proteção e você pode tentar entrar novamente."
        : (error.message || "Falha no login.");
      renderInlineFlash(feedbackEl, message, "error");
      document.getElementById("login-password")?.focus();
    } finally {
      if (submitButton && document.body.classList.contains("login-body")) {
        submitButton.disabled = false;
        submitButton.textContent = "Entrar agora";
      }
    }
  });
}

async function handleLogout() {
  try {
    await api("/api/v1/session/logout", { method: "POST" });
  } finally {
    state.session = null;
    state.csrfToken = "";
    showFlash("Sessão encerrada.", "success");
    window.location.hash = "#/login";
    window.location.reload();
  }
}





