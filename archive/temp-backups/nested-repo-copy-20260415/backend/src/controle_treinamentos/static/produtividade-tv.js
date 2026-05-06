(() => {
    const payloadNode = document.getElementById("ptvInitialPayload");
    let initialPayload = { summary: {}, rows: [], updated_at: "--" };
    try {
        initialPayload = JSON.parse(payloadNode?.textContent || "{}");
    } catch (_error) {
        initialPayload = { summary: {}, rows: [], updated_at: "--" };
    }
    const config = window.PTV_CONFIG || {};
    const currencyFormatter = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
    const moneyCache = new Map();

    const clockNode = document.getElementById("ptvClock");
    const updatedAtNode = document.getElementById("ptvUpdatedAt");
    const fullscreenBtn = document.getElementById("ptvFullscreen");
    const slides = [...document.querySelectorAll(".ptv-slide")];
    const dots = [...document.querySelectorAll(".ptv-dot")];
    const keyedNodes = {};
    document.querySelectorAll("[data-key]").forEach((node) => {
        const key = node.getAttribute("data-key");
        if (key) keyedNodes[key] = node;
    });
    let activeSlide = 0;
    let refreshing = false;
    let refreshHandle = null;
    let clockHandle = null;
    let slideHandle = null;
    let lastRenderSignature = "";

    function escapeHtml(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#39;");
    }

    function money(value) {
        const number = Number(value || 0);
        const cacheKey = Number.isFinite(number) ? number : 0;
        if (moneyCache.has(cacheKey)) {
            return moneyCache.get(cacheKey);
        }
        const formatted = currencyFormatter.format(cacheKey);
        if (moneyCache.size > 500) {
            moneyCache.clear();
        }
        moneyCache.set(cacheKey, formatted);
        return formatted;
    }

    function setNodeText(node, value) {
        if (!node) return;
        const next = String(value);
        if (node.textContent !== next) {
            node.textContent = next;
        }
    }

    function buildRenderSignature(payload) {
        const summary = payload.summary || {};
        const rows = payload.rows || [];
        const summaryToken = [
            summary.total_tripulantes || 0,
            summary.total_missoes || 0,
            summary.total_pernoites || 0,
            Number(summary.total_pago_piso || 0).toFixed(2),
            Number(summary.total_pago_produtividade || 0).toFixed(2),
            Number(summary.valor_total_consolidado || 0).toFixed(2),
            summary.tripulantes_com_adicionais || 0,
            summary.categoria_a || 0,
            summary.categoria_b || 0,
            summary.categoria_na || 0,
        ].join("|");
        const rowsToken = rows
            .slice(0, 80)
            .map((row) => [
                row.tripulante_id || 0,
                Number(row.total_missoes_validas || 0),
                Number(row.total_pernoites || 0),
                Number(row.total_produtividade || 0).toFixed(2),
                Number(row.valor_final_mes || 0).toFixed(2),
                row.criterio_fechamento || "",
            ].join(":"))
            .join(";");
        return `${rows.length}|${summaryToken}|${rowsToken}`;
    }

    function updateClock() {
        if (clockNode) {
            clockNode.textContent = new Date().toLocaleTimeString("pt-BR");
        }
    }

    function renderCards(summary) {
        const map = {
            total_tripulantes: summary.total_tripulantes || 0,
            total_missoes: summary.total_missoes || 0,
            total_pernoites: summary.total_pernoites || 0,
            total_pago_piso: money(summary.total_pago_piso || 0),
            total_pago_produtividade: money(summary.total_pago_produtividade || 0),
            valor_total_consolidado: money(summary.valor_total_consolidado || 0),
            categorias: `${summary.categoria_a || 0} / ${summary.categoria_b || 0} / ${summary.categoria_na || 0}`,
            tripulantes_com_adicionais: summary.tripulantes_com_adicionais || 0,
        };
        Object.entries(map).forEach(([key, value]) => {
            const node = keyedNodes[key];
            setNodeText(node, value);
        });
    }

    function renderList(targetId, rows, mode) {
        const root = document.getElementById(targetId);
        if (!root) return;
        if (!rows || !rows.length) {
            root.innerHTML = '<div class="ptv-item"><div class="ptv-secondary">Sem dados para exibir.</div></div>';
            return;
        }
        root.innerHTML = rows.slice(0, 5).map((row, index) => {
            if (mode === "base") {
                return `
                    <article class="ptv-item">
                        <div class="ptv-line"><div class="ptv-primary">${index + 1}. ${escapeHtml(row.base || "-")}</div><div class="ptv-primary">${escapeHtml(money(row.valor_final_mes))}</div></div>
                        <div class="ptv-secondary">Tripulantes: ${Number(row.tripulantes || 0)}</div>
                    </article>
                `;
            }
            return `
                <article class="ptv-item">
                    <div class="ptv-line"><div class="ptv-primary">${index + 1}. ${escapeHtml(row.tripulante_nome || "-")}</div><div class="ptv-primary">${escapeHtml(money(mode === "prod" ? row.total_produtividade : row.valor_final_mes))}</div></div>
                    <div class="ptv-secondary">${escapeHtml(row.base || "-")} · ${escapeHtml(row.funcao || "-")} · ${escapeHtml(row.categoria || "-")} · Missões ${Number(row.total_missoes_validas || 0)}</div>
                </article>
            `;
        }).join("");
    }

    function renderHighlights(rows, summary) {
        const root = document.getElementById("ptvHighlights");
        if (!root) return;
        const byValue = [...rows].sort((a, b) => b.valor_final_mes - a.valor_final_mes);
        const destaque = byValue[0];
        let criterioPiso = 0;
        let criterioProd = 0;
        rows.forEach((item) => {
            if (item.criterio_fechamento === "piso mínimo") criterioPiso += 1;
            if (item.criterio_fechamento === "produtividade apurada") criterioProd += 1;
        });
        root.innerHTML = `
            <article class="ptv-item">
                <div class="ptv-primary">Maior valor final</div>
                <div class="ptv-secondary">${destaque ? `${escapeHtml(destaque.tripulante_nome || "-")} · ${escapeHtml(money(destaque.valor_final_mes))}` : "Sem dados"}</div>
            </article>
            <article class="ptv-item">
                <div class="ptv-primary">Fechamento por produtividade</div>
                <div class="ptv-secondary">${Number(criterioProd)} tripulante(s)</div>
            </article>
            <article class="ptv-item">
                <div class="ptv-primary">Fechamento por piso mínimo</div>
                <div class="ptv-secondary">${Number(criterioPiso)} tripulante(s)</div>
            </article>
            <article class="ptv-item">
                <div class="ptv-primary">Valor total consolidado</div>
                <div class="ptv-secondary">${escapeHtml(money(summary.valor_total_consolidado || 0))}</div>
            </article>
        `;
    }

    function renderAlerts(rows) {
        const root = document.getElementById("ptvAlerts");
        if (!root) return;
        let withoutMission = 0;
        let lowProductivity = 0;
        let highVolume = 0;
        rows.forEach((row) => {
            const totalMissoes = Number(row.total_missoes_validas || 0);
            const produtividade = Number(row.total_produtividade || 0);
            const valorFinal = Number(row.valor_final_mes || 0);
            if (totalMissoes === 0) withoutMission += 1;
            if (produtividade < valorFinal) lowProductivity += 1;
            if (totalMissoes >= 8) highVolume += 1;
        });
        root.innerHTML = `
            <article class="ptv-item">
                <div class="ptv-primary">Sem missão no mês</div>
                <div class="ptv-secondary">${Number(withoutMission)} tripulante(s)</div>
            </article>
            <article class="ptv-item">
                <div class="ptv-primary">Fechamento por piso</div>
                <div class="ptv-secondary">${Number(lowProductivity)} ocorrência(s)</div>
            </article>
            <article class="ptv-item">
                <div class="ptv-primary">Alta carga operacional</div>
                <div class="ptv-secondary">${Number(highVolume)} tripulante(s) com >= 8 missões</div>
            </article>
        `;
    }

    function renderTopVolume(rowsByVolume) {
        const root = document.getElementById("ptvTopVolume");
        if (!root) return;
        renderList("ptvTopVolume", rowsByVolume, "prod");
    }

    function setActiveSlide(index) {
        if (!slides.length) return;
        const next = index % slides.length;
        if (next === activeSlide && slides[next]?.classList.contains("is-active")) {
            return;
        }
        activeSlide = next;
        slides.forEach((slide, i) => slide.classList.toggle("is-active", i === activeSlide));
        dots.forEach((dot, i) => dot.classList.toggle("is-active", i === activeSlide));
    }

    function buildBaseRanking(rows) {
        const map = {};
        rows.forEach((row) => {
            const key = row.base || "Sem base";
            if (!map[key]) {
                map[key] = { base: key, valor_final_mes: 0, tripulantes: 0 };
            }
            map[key].valor_final_mes += Number(row.valor_final_mes || 0);
            map[key].tripulantes += 1;
        });
        return Object.values(map).sort((a, b) => b.valor_final_mes - a.valor_final_mes);
    }

    function render(payload) {
        const summary = payload.summary || {};
        const rows = payload.rows || [];
        const signature = buildRenderSignature(payload);
        if (signature === lastRenderSignature) {
            setNodeText(updatedAtNode, `Atualizado em ${payload.updated_at || "--"}`);
            return;
        }
        lastRenderSignature = signature;
        renderCards(summary);
        const byValue = [...rows].sort((a, b) => b.valor_final_mes - a.valor_final_mes);
        const byProd = [...rows].sort((a, b) => b.total_produtividade - a.total_produtividade);
        const byVolume = [...rows].sort((a, b) => {
            const missionDiff = Number(b.total_missoes_validas || 0) - Number(a.total_missoes_validas || 0);
            if (missionDiff !== 0) return missionDiff;
            return Number(b.total_produtividade || 0) - Number(a.total_produtividade || 0);
        });
        const byBase = buildBaseRanking(rows);
        renderList("ptvRankingValor", byValue, "valor");
        renderList("ptvRankingProd", byProd, "prod");
        renderList("ptvRankingBase", byBase, "base");
        renderHighlights(rows, summary);
        renderAlerts(rows);
        renderTopVolume(byVolume);
        setNodeText(updatedAtNode, `Atualizado em ${payload.updated_at || "--"}`);
    }

    async function refresh() {
        if (refreshing || !config.endpoint) return;
        refreshing = true;
        try {
            const response = await fetch(config.endpoint, {
                headers: { "X-Requested-With": "XMLHttpRequest" },
                cache: "no-cache",
            });
            if (response.status === 304) return;
            if (!response.ok) return;
            const payload = await response.json();
            render(payload);
        } catch (_error) {
            // Keep the last known data rendered for TV continuity.
        } finally {
            refreshing = false;
        }
    }

    function startTimers() {
        if (!clockHandle) {
            clockHandle = setInterval(updateClock, 1000);
        }
        if (!refreshHandle) {
            refreshHandle = setInterval(refresh, Number(config.refreshMs || 60000));
        }
        if (!slideHandle) {
            slideHandle = setInterval(() => setActiveSlide((activeSlide + 1) % Math.max(slides.length, 1)), 12000);
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
        if (slideHandle) {
            clearInterval(slideHandle);
            slideHandle = null;
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
                // Ignore browser restrictions.
            }
        });
    }

    render(initialPayload);
    setActiveSlide(0);
    updateClock();
    startTimers();

    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            stopTimers();
            return;
        }
        updateClock();
        refresh();
        startTimers();
    });

    window.addEventListener("beforeunload", stopTimers, { once: true });
})();
