import {
  api,
  config,
  consumeReturnRoute,
  forensicTrace,
  hashQuery,
  refreshSession,
  showFlash,
  state,
} from "../lib.js";

import {
  renderFlashMarkup,
  renderInlineFlash,
} from "./render-shell.js";
import { resolveLoginDestination } from "./redirects.js";
import { STATIC_ASSETS } from "../compat/static-assets.js";

let loginSessionRefreshPromise = null;

async function refreshLoginSession({ force = false } = {}) {
  if (!force && state.csrfToken) {
    return state.session || { authenticated: false, csrf_token: state.csrfToken };
  }
  if (!force && loginSessionRefreshPromise) {
    return loginSessionRefreshPromise;
  }
  loginSessionRefreshPromise = refreshSession().finally(() => {
    loginSessionRefreshPromise = null;
  });
  return loginSessionRefreshPromise;
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
    await refreshLoginSession({ force: true });
    return api("/api/v1/session/login", {
      method: "POST",
      json: payload,
    });
  }
}

export function renderLoginPage(onLoggedIn) {
  forensicTrace("login.render.begin", {
    route: window.location.hash || "",
    hasCsrf: Boolean(state.csrfToken),
  }, { assets: true });
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
            src="${STATIC_ASSETS.loginCitationJet}"
            alt=""
            loading="eager"
            fetchpriority="high"
            decoding="async"
          >
        </div>
        <div class="login-visual-content login-fade login-delay-1">
          <div class="login-visual-brand">
            <img class="brand-image brand-image-login-visual" src="${STATIC_ASSETS.logoBrasilVida}" alt="Brasil Vida">
            <span class="login-visual-badge">Servidor local &bull; acesso protegido</span>
          </div>
          <div class="login-visual-copy">
            <span class="login-eyebrow">Treinamentos Brasil Vida</span>
            <h1>Referência em transporte aeromédico.</h1>
            <p>Entre para acompanhar vencimentos, cadastros e a rotina operacional com um fluxo mais r&aacute;pido e confi&aacute;vel.</p>
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
    forensicTrace("login.submit.begin", { route: window.location.hash || "" });
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
      submitButton.setAttribute("aria-busy", "true");
      submitButton.textContent = "Entrando...";
    }
    try {
      const { data } = await submitLoginRequest(payload);
      const hashNext = hashQuery().get("next") || "";
      const explicitDestination = resolveLoginDestination(hashNext, { fallbackHash: "" });
      const storedDestination = explicitDestination.value
        ? explicitDestination
        : resolveLoginDestination(consumeReturnRoute(), { fallbackHash: "" });
      const destination = storedDestination.value
        ? storedDestination
        : resolveLoginDestination(data?.next || data?.capabilities?.landing_url);
      showFlash("Login realizado com sucesso.", "success");
      forensicTrace("login.submit.success", {
        destination,
        hashNext,
        next: data?.next || "",
        landing: data?.capabilities?.landing_url || "",
      }, { assets: true });
      if (destination.kind === "path") {
        forensicTrace("login.redirect.path", { to: destination.value }, { assets: true });
        window.location.assign(destination.value);
        return;
      }
      forensicTrace("login.redirect.hash", { to: destination.value }, { assets: true });
      window.location.hash = destination.value;
      await onLoggedIn();
    } catch (error) {
      forensicTrace("login.submit.error", { error }, { assets: true });
      const message = error?.code === "csrf_error"
        ? "Sua sessão expirou ou ficou inconsistente. Atualizamos a proteção e você pode tentar entrar novamente."
        : (error.message || "Falha no login.");
      renderInlineFlash(feedbackEl, message, "error");
      document.getElementById("login-password")?.focus();
    } finally {
      if (submitButton && document.body.classList.contains("login-body")) {
        submitButton.disabled = false;
        submitButton.removeAttribute("aria-busy");
        submitButton.textContent = "Entrar agora";
      }
    }
  });
}

