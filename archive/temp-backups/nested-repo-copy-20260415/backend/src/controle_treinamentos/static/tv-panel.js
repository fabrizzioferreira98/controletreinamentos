(() => {
    const config = window.TV_PANEL_CONFIG || {};
    const initialPayloadEl = document.getElementById("tvInitialPayload");
    let initialPayload = {};
    if (initialPayloadEl) {
        try {
            initialPayload = JSON.parse(initialPayloadEl.textContent || "{}");
        } catch (_error) {
            initialPayload = {};
        }
    }
    const refreshMs = Math.max(15000, Number(config.refreshSeconds || 60) * 1000);
    const baseFilter = config.baseFilter || "";
    const timeFormatter = new Intl.DateTimeFormat("pt-BR", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
    });
    const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
        weekday: "short",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
    });

    const summaryContainer = document.getElementById("tvSummaryCards");
    const upcomingList = document.getElementById("tvUpcomingList");
    const criticalList = document.getElementById("tvCriticalList");
    const expiredList = document.getElementById("tvExpiredList");
    const baseRankingList = document.getElementById("tvBaseRankingList");
    const pilotRankingList = document.getElementById("tvPilotRankingList");
    const alertRotator = document.getElementById("tvAlertRotator");
    const lastUpdate = document.getElementById("tvLastUpdate");
    const clockNode = document.getElementById("tvClock");
    const dateNode = document.getElementById("tvDate");
    const connectionState = document.getElementById("tvConnectionState");
    const newsbarTrack = document.getElementById("tvNewsbarTrack");
    const fullscreenBtn = document.getElementById("tvFullscreenBtn");

    const panelNodes = [...document.querySelectorAll("[data-panel-rotate]")];
    const summaryCards = summaryContainer
        ? [...summaryContainer.querySelectorAll(".tv-card")]
            .map((card, index) => ({
                key: card.dataset.key,
                strong: card.querySelector("strong"),
                delay: `${index * 45}ms`,
            }))
            .filter((item) => item.key && item.strong)
        : [];
    let panelBatchIndex = 0;
    let alertIndex = 0;
    let alertMessages = [];
    let previousSummary = {};
    let refreshing = false;
    let currentPayload = initialPayload;
    let cachedMaxPanelItems = 4;
    let listSignature = {
        upcoming: "",
        critical: "",
        expired: "",
        base: "",
        pilot: "",
    };
    let newsbarSignature = "";
    let alertSignature = "";
    let alertTickHandle = null;
    let panelRotateHandle = null;
    let refreshHandle = null;
    let clockHandle = null;
    let resizeRaf = null;
    let lastRenderedDateKey = "";

    function toneByItem(item) {
        const days = item?.days_remaining;
        if (days == null) return "tone-safe";
        if (days < 0 || days <= 15) return "tone-critical";
        if (days <= 60) return "tone-warning";
        return "tone-safe";
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#39;");
    }

    function statusClassName(item) {
        const raw = String(item?.status_class || "status-gray").trim();
        return /^[a-z0-9_-]+$/i.test(raw) ? raw : "status-gray";
    }

    function maxPanelItems() {
        const h = window.innerHeight || 1080;
        if (h <= 820) return 1;
        if (h <= 940) return 2;
        if (h <= 1080) return 3;
        return 4;
    }

    function refreshMaxPanelItemsCache() {
        cachedMaxPanelItems = maxPanelItems();
    }

    function daysLabel(item) {
        if (item.days_remaining == null) return "Sem vencimento informado";
        if (item.days_remaining < 0) return `Vencida ha ${Math.abs(item.days_remaining)} dia(s)`;
        if (item.days_remaining === 0) return "Vence hoje";
        return `Vence em ${item.days_remaining} dia(s)`;
    }

    function animateNumber(node, from, to, duration = 650) {
        const start = performance.now();
        const origin = Number.isFinite(from) ? from : 0;
        const target = Number.isFinite(to) ? to : 0;
        if (origin === target) {
            node.textContent = String(target);
            return;
        }
        function step(now) {
            const progress = Math.min(1, (now - start) / duration);
            const eased = 1 - Math.pow(1 - progress, 3);
            const value = Math.round(origin + (target - origin) * eased);
            node.textContent = String(value);
            if (progress < 1) requestAnimationFrame(step);
        }
        requestAnimationFrame(step);
    }

    function renderSummary(summary = {}) {
        summaryCards.forEach((item) => {
            const key = item.key;
            const value = Number(summary[key] || 0);
            animateNumber(item.strong, Number(previousSummary[key] || 0), value);
        });
        previousSummary = { ...summary };
    }

    function buildListSignature(items = []) {
        return items
            .map((item) => `${item.tripulante_id || ""}:${item.habilitacao_nome || ""}:${item.status_key || ""}:${item.days_remaining ?? "n"}`)
            .join("|");
    }

    function renderTrainingList(node, items, emptyMessage) {
        if (!node) return;
        if (!items || !items.length) {
            node.innerHTML = `<div class="tv-empty">${escapeHtml(emptyMessage)}</div>`;
            return;
        }
        node.innerHTML = items.slice(0, cachedMaxPanelItems).map((item) => `
            <article class="tv-list-item">
                <div class="tv-list-line">
                    <div class="tv-list-title">${escapeHtml(item.tripulante_nome)}</div>
                    <span class="tv-status ${statusClassName(item)}${item.pulse ? " tv-status-pulse" : ""}">${escapeHtml(item.status_label)}</span>
                </div>
                <div class="tv-list-subtitle">${escapeHtml(item.tripulante_base || "-")} - ${escapeHtml(item.habilitacao_nome)}</div>
                <div class="tv-list-subtitle">${escapeHtml(item.due_date_label)} - ${escapeHtml(daysLabel(item))}</div>
            </article>
        `).join("");
    }

    function renderBaseRanking(items) {
        renderSimpleRanking(baseRankingList, items, "base", "total_pendencias", "Nenhuma pendencia por base.");
    }

    function renderPilotRanking(items) {
        if (!pilotRankingList) return;
        if (!items || !items.length) {
            pilotRankingList.innerHTML = `<div class="tv-empty">Nenhum tripulante com pendencias no momento.</div>`;
            return;
        }
        pilotRankingList.innerHTML = items.slice(0, cachedMaxPanelItems).map((item, index) => `
            <article class="tv-list-item">
                <div class="tv-list-line">
                    <div class="tv-list-title">${index + 1}. ${escapeHtml(item.tripulante_nome)}</div>
                    <span class="tv-status status-orange">${Number(item.total || 0)} pendencia(s)</span>
                </div>
                <div class="tv-list-subtitle">Base: ${escapeHtml(item.base || "-")}</div>
            </article>
        `).join("");
    }

    function renderSimpleRanking(node, items, labelKey, valueKey, emptyMessage) {
        if (!node) return;
        if (!items || !items.length) {
            node.innerHTML = `<div class="tv-empty">${escapeHtml(emptyMessage)}</div>`;
            return;
        }
        node.innerHTML = items.slice(0, cachedMaxPanelItems).map((item, index) => `
            <article class="tv-list-item">
                <div class="tv-list-line">
                    <div class="tv-list-title">${index + 1}. ${escapeHtml(item[labelKey])}</div>
                    <span class="tv-status status-red">${Number(item[valueKey] || 0)} pendencia(s)</span>
                </div>
            </article>
        `).join("");
    }

    function renderAlerts(alerts) {
        const nextMessages = (alerts || []).map((item) => item.message);
        const nextSignature = nextMessages.join("|");
        if (nextSignature === alertSignature) {
            return;
        }
        alertSignature = nextSignature;
        alertMessages = nextMessages;
        alertIndex = 0;
        renderAlertTick();
    }

    function buildNewsbarItems(payload = {}) {
        const summary = payload.summary || {};
        const items = [];
        const critical = payload.criticos || [];
        const expired = payload.vencidos || [];
        const upcoming = payload.proximos_vencimentos || [];

        if ((summary.total_vencido || 0) > 0) {
            items.push({ tone: "tone-critical", message: `${summary.total_vencido} habilitacao(oes) vencida(s) requer(em) acao imediata` });
        }
        if ((summary.total_critico_15 || 0) > 0) {
            items.push({ tone: "tone-critical", message: `${summary.total_critico_15} caso(s) critico(s) ate 15 dias` });
        }
        if ((summary.total_vencer_30 || 0) > 0) {
            items.push({ tone: "tone-warning", message: `${summary.total_vencer_30} habilitacao(oes) vencem em ate 30 dias` });
        }

        critical.slice(0, 2).forEach((item) => {
            items.push({
                tone: toneByItem(item),
                message: `Critico: ${item.tripulante_nome} | ${item.habilitacao_nome} | ${daysLabel(item)}`,
            });
        });
        expired.slice(0, 2).forEach((item) => {
            items.push({
                tone: "tone-critical",
                message: `Vencida: ${item.tripulante_nome} | ${item.habilitacao_nome} | ${daysLabel(item)}`,
            });
        });
        upcoming.slice(0, 2).forEach((item) => {
            items.push({
                tone: toneByItem(item),
                message: `Proximo vencimento: ${item.tripulante_nome} | ${item.habilitacao_nome} | ${daysLabel(item)}`,
            });
        });

        if (!items.length) {
            items.push({ tone: "tone-safe", message: "Operacao estavel: nenhum alerta critico de vencimento no momento" });
        }
        return items;
    }

    function renderNewsbar(payload = {}) {
        if (!newsbarTrack) return;
        const items = buildNewsbarItems(payload);
        const duplicated = [...items, ...items];
        const nextSignature = duplicated.map((item) => `${item.tone}:${item.message}`).join("|");
        if (nextSignature === newsbarSignature) {
            return;
        }
        newsbarSignature = nextSignature;
        newsbarTrack.innerHTML = duplicated.map((item, index) => `
            <span class="tv-newsbar-item ${escapeHtml(item.tone)}">${escapeHtml(item.message)}</span>
            ${index < duplicated.length - 1 ? '<span class="tv-newsbar-sep">|</span>' : ""}
        `).join("");

        // Restart ticker animation on every data refresh.
        newsbarTrack.style.animation = "none";
        void newsbarTrack.offsetHeight;
        newsbarTrack.style.animation = "";
    }

    function renderAlertTick() {
        if (!alertRotator) return;
        if (!alertMessages.length) {
            alertRotator.innerHTML = '<div class="tv-alert-item">Sem alertas no momento.</div>';
            return;
        }
        const message = alertMessages[alertIndex % alertMessages.length];
        if (!alertRotator.firstElementChild || !alertRotator.firstElementChild.classList.contains("tv-alert-item")) {
            alertRotator.innerHTML = '<div class="tv-alert-item"></div>';
        }
        alertRotator.firstElementChild.textContent = message;
        alertIndex += 1;
    }

    function updateTimestamp(now = new Date()) {
        if (!clockNode || !dateNode) return;
        clockNode.textContent = timeFormatter.format(now);
        const dateKey = `${now.getFullYear()}-${now.getMonth()}-${now.getDate()}`;
        if (dateKey !== lastRenderedDateKey) {
            lastRenderedDateKey = dateKey;
            dateNode.textContent = dateFormatter.format(now);
        }
    }

    function rotatePanels() {
        if (!panelNodes.length || window.innerWidth < 1300) return;
        const batchSize = 3;
        if (panelNodes.length <= batchSize) {
            panelNodes.forEach((panel) => panel.classList.remove("tv-rotate-hidden"));
            return;
        }
        const start = (panelBatchIndex * batchSize) % panelNodes.length;
        const highlighted = new Set([
            panelNodes[start],
            panelNodes[(start + 1) % panelNodes.length],
            panelNodes[(start + 2) % panelNodes.length],
        ]);
        panelNodes.forEach((panel) => panel.classList.toggle("tv-rotate-hidden", !highlighted.has(panel)));
        panelBatchIndex += 1;
    }

    function render(payload = {}) {
        currentPayload = payload;
        renderSummary(payload.summary || {});
        const upcoming = payload.proximos_vencimentos || [];
        const critical = payload.criticos || [];
        const expired = payload.vencidos || [];
        const baseRanking = payload.ranking_bases || [];
        const pilotRanking = payload.ranking_tripulantes || [];

        const upcomingSig = buildListSignature(upcoming.slice(0, cachedMaxPanelItems));
        if (upcomingSig !== listSignature.upcoming) {
            renderTrainingList(upcomingList, upcoming, "Sem proximos vencimentos.");
            listSignature.upcoming = upcomingSig;
        }

        const criticalSig = buildListSignature(critical.slice(0, cachedMaxPanelItems));
        if (criticalSig !== listSignature.critical) {
            renderTrainingList(criticalList, critical, "Nenhum caso critico ate 15 dias.");
            listSignature.critical = criticalSig;
        }

        const expiredSig = buildListSignature(expired.slice(0, cachedMaxPanelItems));
        if (expiredSig !== listSignature.expired) {
            renderTrainingList(expiredList, expired, "Nenhuma habilitacao vencida.");
            listSignature.expired = expiredSig;
        }

        const baseSig = baseRanking
            .slice(0, cachedMaxPanelItems)
            .map((item) => `${item.base || ""}:${item.total_pendencias || 0}`)
            .join("|");
        if (baseSig !== listSignature.base) {
            renderBaseRanking(baseRanking);
            listSignature.base = baseSig;
        }

        const pilotSig = pilotRanking
            .slice(0, cachedMaxPanelItems)
            .map((item) => `${item.tripulante_nome || ""}:${item.total || 0}`)
            .join("|");
        if (pilotSig !== listSignature.pilot) {
            renderPilotRanking(pilotRanking);
            listSignature.pilot = pilotSig;
        }

        renderAlerts(payload.alerts || []);
        renderNewsbar(payload);
        if (lastUpdate) {
            lastUpdate.textContent = payload.generated_at_label || "--";
        }
    }

    async function refreshData() {
        if (refreshing) return;
        refreshing = true;
        const url = baseFilter
            ? `${config.endpoints.dados}?base=${encodeURIComponent(baseFilter)}`
            : config.endpoints.dados;
        try {
            const response = await fetch(url, {
                headers: { "X-Requested-With": "XMLHttpRequest" },
                cache: "no-cache",
            });
            if (response.status === 304) {
                connectionState.textContent = "Conectado";
                connectionState.classList.remove("tv-disconnected");
                return;
            }
            if (!response.ok) {
                throw new Error("Falha ao atualizar painel.");
            }
            const payload = await response.json();
            render(payload);
            connectionState.textContent = "Conectado";
            connectionState.classList.remove("tv-disconnected");
        } catch (_error) {
            connectionState.textContent = "Sem conexao - exibindo ultima leitura";
            connectionState.classList.add("tv-disconnected");
        } finally {
            refreshing = false;
        }
    }

    function startTimers() {
        if (!clockHandle) {
            clockHandle = setInterval(() => updateTimestamp(), 1000);
        }
        if (!refreshHandle) {
            refreshHandle = setInterval(() => refreshData(), refreshMs);
        }
        if (!alertTickHandle) {
            alertTickHandle = setInterval(() => renderAlertTick(), 8000);
        }
        if (!panelRotateHandle) {
            panelRotateHandle = setInterval(() => rotatePanels(), 12000);
        }
    }

    function stopTimers() {
        if (clockHandle) {
            clearInterval(clockHandle);
            clockHandle = null;
        }
        if (refreshHandle) {
            clearInterval(refreshHandle);
            refreshHandle = null;
        }
        if (alertTickHandle) {
            clearInterval(alertTickHandle);
            alertTickHandle = null;
        }
        if (panelRotateHandle) {
            clearInterval(panelRotateHandle);
            panelRotateHandle = null;
        }
    }

    if (fullscreenBtn) {
        fullscreenBtn.addEventListener("click", async () => {
            try {
                if (!document.fullscreenElement) {
                    await document.documentElement.requestFullscreen();
                } else {
                    await document.exitFullscreen();
                }
            } catch (_error) {
                // Intentionally noop for browsers that block fullscreen requests.
            }
        });
    }

    summaryCards.forEach((item) => {
        if (item.strong?.parentElement) {
            item.strong.parentElement.style.animationDelay = item.delay;
        }
    });
    refreshMaxPanelItemsCache();
    render(initialPayload);
    updateTimestamp();
    rotatePanels();
    startTimers();

    window.addEventListener("resize", () => {
        if (resizeRaf) return;
        resizeRaf = requestAnimationFrame(() => {
            resizeRaf = null;
            const previous = cachedMaxPanelItems;
            refreshMaxPanelItemsCache();
            if (previous !== cachedMaxPanelItems) {
                listSignature = { upcoming: "", critical: "", expired: "", base: "", pilot: "" };
                render(currentPayload);
            }
        });
    }, { passive: true });

    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            stopTimers();
            return;
        }
        updateTimestamp();
        refreshData();
        startTimers();
    });

    window.addEventListener("beforeunload", stopTimers, { once: true });
})();
