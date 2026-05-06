from __future__ import annotations

import argparse
import base64
import json
import math
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib import parse

import capture_habilitacoes_visual_audit as base


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
ROUTE = "#/financeiro/missoes"
SLUG = "financeiro-missoes"


@dataclass(frozen=True)
class AuditState:
    key: str
    label: str
    hash_query: str = ""
    prepare: str = ""
    expected_text: str = ""


VIEWPORTS = [
    base.Viewport("desktop", 1920, 1080, "desktop/TV Full HD"),
    base.Viewport("desktop", 1600, 900, "desktop widescreen"),
    base.Viewport("desktop", 1366, 768, "notebook comum"),
    base.Viewport("desktop", 1280, 720, "TV/notebook HD"),
    base.Viewport("tablet", 1024, 768, "tablet landscape"),
    base.Viewport("tablet", 768, 1024, "tablet portrait"),
    base.Viewport("mobile", 390, 844, "mobile"),
]

STATES = [
    AuditState("estado-vazio", "Estado vazio", "?busca=__empty__", expected_text="Nenhuma missão operacional encontrada"),
    AuditState("nova-missao", "Nova missão", expected_text="Nova missão"),
    AuditState("missao-selecionada", "Missão selecionada", "?mission_id=101", expected_text="Missão salva #101"),
    AuditState("editando-missao", "Editando missão", "?mission_id=101", "focus-form", "Editando missão existente"),
    AuditState("previa-sem-dados", "Prévia sem dados", expected_text="Informe data, aeronave, tripulação"),
    AuditState("previa-disponivel", "Prévia disponível", prepare="fill-preview", expected_text="Valor estimado"),
    AuditState("pendencia-calculo", "Pendência de cálculo", "?mission_id=102", expected_text="Bloqueios atuais"),
    AuditState("recalculando", "Recalculando", "?mission_id=101", "recalculating", "Recalculando missão"),
    AuditState("recalculado-sucesso", "Recalculado com sucesso", "?mission_id=101&preview_status=recalculada", expected_text="Cálculo vigente atualizado"),
    AuditState("erro-recalculo", "Erro de recálculo", "?mission_id=101", "recalc-error", "Erro de recálculo"),
]

STABILITY_VIEWPORTS = [
    base.Viewport("stability", 1366, 768, "navegacao notebook"),
    base.Viewport("stability", 390, 844, "navegacao mobile"),
]

TRIPULANTES = [
    {"id": 11, "nome": "Ana Comandante", "base": "BSB", "funcao_operacional": "Comandante"},
    {"id": 12, "nome": "Bruno Copiloto", "base": "BSB", "funcao_operacional": "Copiloto"},
    {"id": 13, "nome": "Carla Reserva", "base": "PMW", "funcao_operacional": "Comandante"},
]

EQUIPAMENTOS = [
    {"id": 21, "nome": "PR-BVA", "categoria_financeira": "categoria a"},
    {"id": 22, "nome": "PT-TBO", "categoria_financeira": "categoria b"},
]

MISSIONS = [
    {
        "id": 101,
        "org_id": 1,
        "competencia": "2026-05",
        "data_missao": "2026-05-04",
        "cavok_numero_voo": "CAVOK-101",
        "aeronave_id": 21,
        "aeronave_nome": "PR-BVA",
        "categoria_financeira_aeronave": "categoria a",
        "comandante_tripulante_id": 11,
        "comandante_nome": "Ana Comandante",
        "copiloto_tripulante_id": 12,
        "copiloto_nome": "Bruno Copiloto",
        "horario_apresentacao": "2026-05-04T08:00:00",
        "horario_abandono": "2026-05-04T18:30:00",
        "status": "ativa",
        "contratante": "Brasil Vida",
        "chamado": "CH-101",
        "trecho": "BSB-PMW-BSB",
        "houve_pernoite": False,
        "quantidade_pernoites": 0,
        "cobertura_base": False,
        "operacao_especial": "",
        "observacoes": "Missao de auditoria visual.",
        "participantes": [
            {"tripulante_id": 11, "funcao": "comandante"},
            {"tripulante_id": 12, "funcao": "copiloto"},
        ],
    },
    {
        "id": 102,
        "org_id": 1,
        "competencia": "2026-05",
        "data_missao": "2026-05-05",
        "cavok_numero_voo": "CAVOK-102",
        "aeronave_id": 22,
        "aeronave_nome": "PT-TBO",
        "categoria_financeira_aeronave": "categoria b",
        "comandante_tripulante_id": 13,
        "comandante_nome": "Carla Reserva",
        "copiloto_tripulante_id": 12,
        "copiloto_nome": "Bruno Copiloto",
        "horario_apresentacao": "2026-05-05T09:00:00",
        "horario_abandono": "2026-05-05T15:00:00",
        "status": "recalculo_pendente",
        "contratante": "Brasil Vida",
        "chamado": "CH-102",
        "trecho": "BSB-GYN-BSB",
        "houve_pernoite": False,
        "quantidade_pernoites": 0,
        "cobertura_base": True,
        "operacao_especial": "Palmas turboélice",
        "observacoes": "Missao com parametro pendente.",
        "participantes": [
            {"tripulante_id": 13, "funcao": "comandante"},
            {"tripulante_id": 12, "funcao": "copiloto"},
        ],
    },
]


class FixtureProxyHandler(SimpleHTTPRequestHandler):
    frontend_dir = FRONTEND_DIST

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, directory=str(self.frontend_dir), **kwargs)

    def handle(self) -> None:
        try:
            super().handle()
        except ConnectionResetError:
            return

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/"):
            self._write_api("GET")
            return
        self._serve_spa()

    def do_POST(self) -> None:  # noqa: N802
        if self.path.startswith("/api/"):
            self._write_api("POST")
            return
        self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)

    def do_PATCH(self) -> None:  # noqa: N802
        if self.path.startswith("/api/"):
            self._write_api("PATCH")
            return
        self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)

    def _json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def _write_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _write_api(self, method: str) -> None:
        parsed = parse.urlsplit(self.path)
        path = parsed.path.rstrip("/")
        query = parse.parse_qs(parsed.query)
        if path == "/api/v1/session" and method == "GET":
            self._write_json(session_payload())
            return
        if path == "/api/v1/tripulantes" and method == "GET":
            self._write_json({"items": TRIPULANTES, "pagination": {"page": 1, "pages": 1, "total": len(TRIPULANTES)}})
            return
        if path == "/api/v1/equipamentos/options" and method == "GET":
            self._write_json({"options": EQUIPAMENTOS})
            return
        if path == "/api/v1/financeiro/bonificacoes/horaria" and method == "GET":
            self._write_json(hourly_payload())
            return
        if path == "/api/v1/financeiro/missoes" and method == "GET":
            self._write_json(mission_list_payload(query))
            return
        if path == "/api/v1/financeiro/missoes/preview" and method == "POST":
            self._write_json(preview_payload(self._json_body()))
            return
        mission_id, suffix = parse_mission_path(path)
        if mission_id:
            if suffix == "" and method == "GET":
                self._write_json({"mission": mission_by_id(mission_id)})
                return
            if suffix == "preflight-calculo" and method == "GET":
                self._write_json(preflight_payload(mission_id))
                return
            if suffix == "recalcular" and method == "POST":
                time.sleep(1.2)
                self._write_json({
                    "mission_id": mission_id,
                    "competence": "2026-05",
                    "calculation_status": "calculado",
                    "recalculated_at": iso_now(),
                    "affected_calculations": 2,
                    "warnings": [],
                    "errors": [],
                    "current_result": hourly_payload()["items"],
                })
                return
            if suffix == "" and method == "PATCH":
                mission = {**mission_by_id(mission_id), **self._json_body()}
                self._write_json({"mission": mission})
                return
        self._write_json({"message": f"Fixture visual nao cobre {method} {path}", "code": "visual_fixture_miss"}, 404)

    def _serve_spa(self) -> None:
        parsed = parse.urlsplit(self.path)
        raw_path = parse.unquote(parsed.path.lstrip("/"))
        file_path = (self.frontend_dir / raw_path).resolve() if raw_path else self.frontend_dir / "index.html"
        try:
            file_path.relative_to(self.frontend_dir.resolve())
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not file_path.exists() or file_path.is_dir():
            file_path = self.frontend_dir / "index.html"
        self.path = "/" + file_path.relative_to(self.frontend_dir).as_posix()
        super().do_GET()


def iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def session_payload() -> dict[str, Any]:
    permissions = [
        "finance:missions:read",
        "finance:missions:create",
        "finance:missions:update",
        "finance:missions:cancel",
        "finance:missions:recalculate",
        "finance:bonuses:read",
        "tripulantes:view",
        "equipamentos:view",
    ]
    return {
        "authenticated": True,
        "csrf_token": "visual-audit-csrf",
        "user": {"id": "visual", "nome": "QA Visual", "login": "qa_visual", "perfil": "gestora"},
        "capabilities": {"granted_permissions": permissions},
    }


def parse_mission_path(path: str) -> tuple[int, str]:
    prefix = "/api/v1/financeiro/missoes/"
    if not path.startswith(prefix):
        return 0, ""
    parts = path.removeprefix(prefix).split("/")
    try:
        mission_id = int(parts[0])
    except (TypeError, ValueError):
        return 0, ""
    return mission_id, "/".join(parts[1:])


def mission_by_id(mission_id: int) -> dict[str, Any]:
    return next((mission for mission in MISSIONS if int(mission["id"]) == int(mission_id)), MISSIONS[0])


def mission_list_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    busca = (query.get("busca") or [""])[0]
    status = (query.get("status") or [""])[0]
    items = [] if busca == "__empty__" else list(MISSIONS)
    if status:
        items = [mission for mission in items if mission.get("status") == status]
    return {"items": items, "pagination": {"page": 1, "pages": 1, "total": len(items), "page_size": 50}}


def hourly_payload() -> dict[str, Any]:
    return {
        "items": [
            {
                "id": 9001,
                "mission_id": 101,
                "missao_operacional_id": 101,
                "tripulante_id": 11,
                "funcao": "comandante",
                "status": "calculado",
                "valor_estimado": "720.00",
                "competencia": "2026-05",
            },
            {
                "id": 9002,
                "mission_id": 101,
                "missao_operacional_id": 101,
                "tripulante_id": 12,
                "funcao": "copiloto",
                "status": "calculado",
                "valor_estimado": "510.00",
                "competencia": "2026-05",
            },
        ],
        "pagination": {"page": 1, "pages": 1, "total": 2},
    }


def preflight_payload(mission_id: int) -> dict[str, Any]:
    if int(mission_id) == 102:
        return {
            "calculavel": False,
            "bloqueios": [
                {
                    "code": "parametro_pendente",
                    "message": "Parametro financeiro da categoria b ainda pendente na competencia.",
                    "severity": "alta",
                    "next_action": "Revise o cadastro de parametros financeiros.",
                }
            ],
            "next_action": "Resolver parametro financeiro antes do recalculo.",
        }
    return {"calculavel": True, "bloqueios": [], "next_action": ""}


def preview_payload(payload: dict[str, Any]) -> dict[str, Any]:
    required = [
        "data_missao",
        "aeronave_id",
        "categoria_financeira_aeronave",
        "comandante_tripulante_id",
        "copiloto_tripulante_id",
        "horario_apresentacao",
        "horario_abandono",
    ]
    missing = [field for field in required if not str(payload.get(field) or "").strip()]
    if missing:
        return {"preview": {"status": "pendente_dados", "campos_faltantes": [{"label": field} for field in missing]}}
    return {
        "preview": {
            "status": "disponivel",
            "estado_calculo": "estimado",
            "base_calculo": "Bonificação horária operacional",
            "horas_consideradas": {"jornada_total_minutos": 630},
            "tripulantes_considerados": [
                {"tripulante_id": payload.get("comandante_tripulante_id"), "funcao": "comandante"},
                {"tripulante_id": payload.get("copiloto_tripulante_id"), "funcao": "copiloto"},
            ],
            "pendencias": [],
            "inconsistencias": [],
            "observacoes": ["Prévia de auditoria visual. Não persiste dados."],
            "valor_estimado": "1230.00",
            "generated_at": iso_now(),
        }
    }


def start_fixture_proxy() -> tuple[ThreadingHTTPServer, str]:
    if not FRONTEND_DIST.exists():
        raise base.CaptureError(f"Build frontend nao encontrado em {FRONTEND_DIST}.")
    port = base.choose_local_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), FixtureProxyHandler)
    thread = threading.Thread(target=server.serve_forever, name="financeiro-missoes-visual-proxy", daemon=True)
    thread.start()
    return server, f"http://localhost:{port}"


def state_url(base_url: str, state: AuditState) -> str:
    return f"{base_url.rstrip('/')}/{ROUTE}{state.hash_query}"


def wait_for_missions_page(cdp: base.CDPClient, state: AuditState, timeout: float = 45.0) -> dict[str, Any]:
    expression = f"""
    new Promise((resolve) => {{
      const started = Date.now();
      const timeoutMs = {int(timeout * 1000)};
      const expected = {json.dumps(state.expected_text)};
      const expectsEmptyFilter = {json.dumps("__empty__" in state.hash_query)};
      const check = () => {{
        const text = document.body ? document.body.innerText : "";
        const routeOk = (window.location.hash || "").split("?")[0] === "{ROUTE}";
        const loading = /Carregando Missoes Operacionais|Carregando Missões Operacionais/i.test(text);
        const expectedOk = !expected || text.includes(expected);
        const hasPage = /Missões operacionais|Missoes operacionais/i.test(text);
        const staleEmptyFilter = !expectsEmptyFilter && text.includes("Busca: __empty__");
        const minSettled = Date.now() - started > 350;
        const ready = document.readyState === "complete" && routeOk && hasPage && expectedOk && !loading && !staleEmptyFilter && minSettled;
        if (ready) {{
          const finish = () => requestAnimationFrame(() => requestAnimationFrame(() => resolve({{
            route: window.location.hash,
            title: document.title,
            textSample: text.slice(0, 1600),
            hasTarget: hasPage,
            expectedOk,
            timedOut: false,
          }})));
          if (document.fonts && document.fonts.ready) document.fonts.ready.then(finish).catch(finish);
          else finish();
          return;
        }}
        if (Date.now() - started > timeoutMs) {{
          resolve({{
            route: window.location.hash,
            title: document.title,
            textSample: text.slice(0, 1600),
            hasTarget: hasPage,
            expectedOk,
            timedOut: true,
          }});
          return;
        }}
        setTimeout(check, 200);
      }};
      check();
    }})
    """
    return base.runtime_value(cdp, expression, timeout=timeout)


def prepare_state(cdp: base.CDPClient, state: AuditState) -> None:
    if state.prepare == "focus-form":
        base.runtime_value(cdp, "document.querySelector('#financeMissionForm')?.scrollIntoView({block:'start'}); true", timeout=5)
        time.sleep(0.2)
        return
    if state.prepare == "fill-preview":
        expression = """
        (() => {
          const form = document.querySelector('#financeMissionForm');
          if (!form) return false;
          const set = (name, value) => {
            const field = form.elements[name];
            if (!field) return;
            field.value = value;
            field.dispatchEvent(new Event('input', { bubbles: true }));
            field.dispatchEvent(new Event('change', { bubbles: true }));
          };
          set('competencia', '2026-05');
          set('data_missao', '2026-05-04');
          set('aeronave_id', '21');
          set('categoria_financeira_aeronave', 'categoria a');
          set('comandante_tripulante_id', '11');
          set('copiloto_tripulante_id', '12');
          set('horario_apresentacao', '2026-05-04T08:00');
          set('horario_abandono', '2026-05-04T18:30');
          return true;
        })()
        """
        base.runtime_value(cdp, expression, timeout=5)
        base.runtime_value(
            cdp,
            """
            new Promise((resolve) => {
              const started = Date.now();
              const check = () => {
                const card = document.querySelector('[data-finance-preview-card]');
                if (card?.dataset.previewState === 'disponivel') return resolve(true);
                if (Date.now() - started > 12000) return resolve(false);
                setTimeout(check, 200);
              };
              check();
            })
            """,
            timeout=14,
        )
        return
    if state.prepare == "recalculating":
        base.runtime_value(
            cdp,
            """
            (() => {
              const button = document.querySelector('#financeMissionRecalculateButton');
              const feedback = document.querySelector('#financeMissionRecalculateFeedback');
              if (button) {
                button.disabled = true;
                button.textContent = 'Recalculando...';
                button.dataset.busy = '1';
              }
              if (feedback) {
                feedback.innerHTML = '<div class="inline-feedback info ui-feedback">Recalculando missão. Aguarde a atualização do cálculo vigente.</div>';
              }
              return true;
            })()
            """,
            timeout=5,
        )
        return
    if state.prepare == "recalc-error":
        base.runtime_value(
            cdp,
            """
            (() => {
              const feedback = document.querySelector('#financeMissionRecalculateFeedback');
              if (feedback) {
                feedback.innerHTML = '<div class="inline-feedback error ui-feedback">Erro de recálculo. O backend recusou o processamento; revise as pendências e tente novamente.</div>';
              }
              return true;
            })()
            """,
            timeout=5,
        )


def collect_metrics(cdp: base.CDPClient) -> dict[str, Any]:
    expression = """
    (() => {
      const doc = document.documentElement;
      const body = document.body;
      const viewport = { width: window.innerWidth, height: window.innerHeight };
      const scrollWidth = Math.max(doc?.scrollWidth || 0, body?.scrollWidth || 0);
      const scrollHeight = Math.max(doc?.scrollHeight || 0, body?.scrollHeight || 0);
      const selectorMap = {
        page: '.financeiro-missoes-page',
        header: '.financeiro-missoes-page .page-header',
        summary: '.financeiro-missoes-summary-grid',
        filters: '#financeMissionFilters',
        layout: '.financeiro-missoes-layout',
        list: '.financeiro-missoes-list-panel',
        side: '.financeiro-missoes-side',
        form: '#financeMissionForm',
        preview: '[data-finance-preview-card]',
        empty: '.financeiro-missoes-empty-state',
        tableWrap: '.financeiro-missoes-page .table-wrap.ui-table-wrap'
      };
      const rects = {};
      const counts = {};
      const visibility = {};
      for (const [key, selector] of Object.entries(selectorMap)) {
        const nodes = Array.from(document.querySelectorAll(selector));
        counts[key] = nodes.length;
        const node = nodes[0];
        if (!node) {
          visibility[key] = false;
          rects[key] = null;
          continue;
        }
        const rect = node.getBoundingClientRect();
        const style = window.getComputedStyle(node);
        visibility[key] = rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
        rects[key] = { left: Math.round(rect.left), top: Math.round(rect.top), right: Math.round(rect.right), bottom: Math.round(rect.bottom), width: Math.round(rect.width), height: Math.round(rect.height) };
      }
      const tableWrap = document.querySelector('.financeiro-missoes-page .table-wrap.ui-table-wrap');
      const internalTableOverflow = tableWrap ? tableWrap.scrollWidth > tableWrap.clientWidth + 2 : false;
      const duplicatedContent = document.querySelectorAll('.financeiro-missoes-page').length > 1;
      const buttons = Array.from(document.querySelectorAll('.financeiro-missoes-page button, .financeiro-missoes-page .button-link'));
      const overlappingButtons = [];
      for (let i = 0; i < buttons.length; i += 1) {
        const a = buttons[i].getBoundingClientRect();
        if (a.width <= 0 || a.height <= 0) continue;
        for (let j = i + 1; j < buttons.length; j += 1) {
          const b = buttons[j].getBoundingClientRect();
          if (b.width <= 0 || b.height <= 0) continue;
          const overlap = !(a.right <= b.left + 1 || b.right <= a.left + 1 || a.bottom <= b.top + 1 || b.bottom <= a.top + 1);
          if (overlap) overlappingButtons.push(`${buttons[i].textContent.trim()} / ${buttons[j].textContent.trim()}`);
        }
      }
      const offscreen = Array.from(document.querySelectorAll('.financeiro-missoes-page *'))
        .map((node) => {
          const rect = node.getBoundingClientRect();
          if (!rect || rect.width <= 0 || rect.height <= 0) return null;
          const style = window.getComputedStyle(node);
          if (style.visibility === 'hidden' || style.display === 'none') return null;
          if (rect.left >= -2 && rect.right <= viewport.width + 2) return null;
          return {
            tag: node.tagName.toLowerCase(),
            className: String(node.className || '').slice(0, 140),
            text: (node.innerText || node.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 140),
            left: Math.round(rect.left),
            right: Math.round(rect.right),
            width: Math.round(rect.width)
          };
        })
        .filter(Boolean)
        .slice(0, 25);
      return {
        url: location.href,
        route: location.hash,
        title: document.title,
        viewport,
        scrollWidth,
        scrollHeight,
        horizontalOverflow: scrollWidth > viewport.width + 2,
        verticalScroll: scrollHeight > viewport.height + 2,
        internalTableOverflow,
        duplicatedContent,
        overlappingButtons,
        counts,
        visibility,
        rects,
        offscreen,
        previewState: document.querySelector('[data-finance-preview-card]')?.dataset.previewState || '',
        bodyTextSample: (document.body?.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 2000)
      };
    })()
    """
    return base.runtime_value(cdp, expression, timeout=10)


def issue_from_metrics(viewport: base.Viewport, state: AuditState, page_state: dict[str, Any], metrics: dict[str, Any], image: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    context = f"{state.label} / {viewport.width}x{viewport.height}"
    if image.get("nearlyBlank"):
        issues.append(issue(context, "CRITICO", "Screenshot vazio ou quase branco.", "Verificar carregamento, assets e autenticacao da SPA."))
    if page_state.get("timedOut") or not page_state.get("hasTarget") or not page_state.get("expectedOk"):
        issues.append(issue(context, "CRITICO", "Estado esperado nao estabilizou na rota de Missões.", "Revisar fixtures, roteamento hash e carregamento async."))
    if metrics.get("horizontalOverflow"):
        issues.append(issue(context, "ALTO", f"Scroll horizontal no documento: scrollWidth={metrics.get('scrollWidth')} viewport={viewport.width}.", "Revisar grid, painel, tabela, filtros e header."))
    if metrics.get("internalTableOverflow") and state.key == "estado-vazio":
        issues.append(issue(context, "ALTO", "Tabela/lista gera overflow interno no estado vazio.", "Garantir empty state fora da primeira celula e sem tabela comprimida."))
    if metrics.get("duplicatedContent"):
        issues.append(issue(context, "ALTO", "Conteudo de Missões duplicado no DOM.", "Verificar render duplo e cleanup de rota."))
    if metrics.get("overlappingButtons"):
        issues.append(issue(context, "MEDIO", "Botões sobrepostos detectados.", "Revisar grid/flex das ações do painel e header."))
    side = (metrics.get("rects") or {}).get("side") or {}
    if viewport.width >= 1280 and side and side.get("width", 0) < 440:
        issues.append(issue(context, "ALTO", f"Painel operacional estreito: {side.get('width')}px.", "Manter largura util do painel em desktop/notebook."))
    visibility = metrics.get("visibility") or {}
    required = ["header", "summary", "filters", "layout", "side", "form", "preview"]
    for key in required:
        if not visibility.get(key):
            issues.append(issue(context, "MEDIO", f"Bloco essencial ausente ou invisivel: {key}.", "Revisar condicoes de renderizacao e CSS responsivo."))
    if state.key == "estado-vazio" and not visibility.get("empty"):
        issues.append(issue(context, "ALTO", "Empty state nao ficou visivel.", "Renderizar empty state centralizado ocupando a lista."))
    return issues


def issue(context: str, severity: str, description: str, recommendation: str) -> dict[str, Any]:
    return {
        "context": context,
        "severity": severity,
        "description": description,
        "recommendation": recommendation,
    }


def capture_state(cdp: base.CDPClient, base_url: str, output_dir: Path, viewport: base.Viewport, state: AuditState) -> dict[str, Any]:
    base.set_viewport(cdp, viewport)
    cdp.call("Page.navigate", {"url": state_url(base_url, state)}, timeout=20)
    initial_state = state if not state.prepare else AuditState(state.key, state.label, state.hash_query)
    page_state = wait_for_missions_page(cdp, initial_state)
    prepare_state(cdp, state)
    if state.prepare:
        page_state = wait_for_missions_page(cdp, state, timeout=20)
    metrics = collect_metrics(cdp)
    path = output_dir / f"{SLUG}__{state.key}__{viewport.width}x{viewport.height}.png"
    capture = base.capture_png(cdp, path, full_page=False, viewport=viewport)
    capture["image"] = base.image_metrics(path)
    issues = issue_from_metrics(viewport, state, page_state, metrics, capture["image"])
    for item in issues:
        item["evidence"] = str(path)
    return {
        "state": {"key": state.key, "label": state.label},
        "viewport": viewport.__dict__,
        "page_state": page_state,
        "metrics": metrics,
        "capture": capture,
        "issues": issues,
    }


def capture_navigation_stability(cdp: base.CDPClient, base_url: str, output_dir: Path, viewport: base.Viewport) -> dict[str, Any]:
    base.set_viewport(cdp, viewport)
    cdp.call("Page.navigate", {"url": state_url(base_url, STATES[0])}, timeout=20)
    wait_for_missions_page(cdp, STATES[0])
    expression = f"""
    new Promise((resolve) => {{
      window.location.hash = '{ROUTE}?busca=__empty__';
      setTimeout(() => {{
        window.location.hash = '{ROUTE}?mission_id=101';
      }}, 20);
      setTimeout(() => {{
        const text = document.body?.innerText || '';
        resolve({{
          route: window.location.hash,
          hasOldEmpty: text.includes('Nenhuma missão operacional encontrada'),
          hasSelected: text.includes('Missão salva #101'),
          pageCount: document.querySelectorAll('.financeiro-missoes-page').length,
          textSample: text.slice(0, 1200),
        }});
      }}, 2500);
    }})
    """
    result = base.runtime_value(cdp, expression, timeout=8)
    path = output_dir / f"{SLUG}__navigation-stability__{viewport.width}x{viewport.height}.png"
    capture = base.capture_png(cdp, path, full_page=False, viewport=viewport)
    issues = []
    if result.get("hasOldEmpty") or not result.get("hasSelected") or result.get("pageCount") != 1:
        item = issue(
            f"navegacao / {viewport.width}x{viewport.height}",
            "ALTO",
            "Troca rapida de hash manteve conteudo antigo, perdeu destino final ou duplicou pagina.",
            "Manter guarda de renderizacao contra respostas async antigas.",
        )
        item["evidence"] = str(path)
        issues.append(item)
    return {
        "viewport": viewport.__dict__,
        "result": result,
        "capture": capture,
        "issues": issues,
    }


def all_pngs(output_dir: Path) -> list[Path]:
    return sorted(output_dir.glob(f"{SLUG}__*.png"))


def build_contact_sheet(output_dir: Path) -> Path | None:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    paths = all_pngs(output_dir)
    if not paths:
        return None
    thumbs = []
    for path in paths[:80]:
        with Image.open(path) as img:
            thumb = img.convert("RGB")
            thumb.thumbnail((300, 190))
            canvas = Image.new("RGB", (320, 236), "white")
            canvas.paste(thumb, ((320 - thumb.width) // 2, 34))
            ImageDraw.Draw(canvas).text((8, 8), path.name.replace(f"{SLUG}__", "")[:44], fill=(20, 30, 40))
            thumbs.append(canvas)
    columns = 4
    rows = math.ceil(len(thumbs) / columns)
    sheet = Image.new("RGB", (columns * 320, rows * 236), (245, 247, 250))
    for index, thumb in enumerate(thumbs):
        sheet.paste(thumb, ((index % columns) * 320, (index // columns) * 236))
    path = output_dir / f"{SLUG}__contact-sheet.png"
    sheet.save(path)
    return path


def validate(results: dict[str, Any]) -> dict[str, Any]:
    issues = results.get("issues") or []
    expected = len(results.get("captures") or []) + len(results.get("navigation_stability") or [])
    actual = len([path for path in results.get("files", []) if str(path).endswith(".png") and "contact-sheet" not in str(path)])
    return {
        "expected_screenshots": expected,
        "actual_screenshots": actual,
        "issue_count": len(issues),
        "ok": actual >= expected and not issues,
    }


def markdown_report(results: dict[str, Any]) -> str:
    lines = [
        "# Auditoria visual - Financeiro / Missões",
        "",
        "## Rota",
        f"- SPA: `{ROUTE}`",
        f"- URL base: `{results['base_url']}`",
        f"- Gerado em: `{results['generated_at']}`",
        "",
        "## Breakpoints",
        "| Viewport | Estados capturados | Resultado |",
        "| --- | --- | --- |",
    ]
    for viewport in VIEWPORTS:
        state_count = len([entry for entry in results["captures"] if entry["viewport"]["width"] == viewport.width and entry["viewport"]["height"] == viewport.height])
        viewport_issues = [item for item in results["issues"] if f"{viewport.width}x{viewport.height}" in item["context"]]
        lines.append(f"| {viewport.width}x{viewport.height} | {state_count} | {'OK' if not viewport_issues else 'Ver problemas'} |")
    lines.extend(["", "## Estados", "| Estado | Capturas | Resultado |", "| --- | --- | --- |"])
    for state in STATES:
        state_entries = [entry for entry in results["captures"] if entry["state"]["key"] == state.key]
        state_issues = [item for item in results["issues"] if item["context"].startswith(state.label)]
        lines.append(f"| {state.label} | {len(state_entries)} | {'OK' if not state_issues else 'Ver problemas'} |")
    lines.extend(["", "## Problemas"])
    if results["issues"]:
        lines.append("| Contexto | Severidade | Descrição | Evidência | Recomendação |")
        lines.append("| --- | --- | --- | --- | --- |")
        for item in results["issues"]:
            evidence = Path(item.get("evidence", "")).name
            lines.append(f"| {item['context']} | {item['severity']} | {item['description']} | [{evidence}]({evidence}) | {item['recommendation']} |")
    else:
        lines.append("- Nenhum problema automatico detectado em overflow, blocos essenciais, duplicidade, botoes sobrepostos e estabilidade de hash.")
    lines.extend(["", "## Estabilidade de navegação", "| Viewport | Resultado | Evidência |", "| --- | --- | --- |"])
    for entry in results["navigation_stability"]:
        viewport = entry["viewport"]
        evidence = Path(entry["capture"]["path"]).name
        lines.append(f"| {viewport['width']}x{viewport['height']} | {'OK' if not entry['issues'] else 'Ver problemas'} | [{evidence}]({evidence}) |")
    lines.extend(["", "## Arquivos"])
    for file_path in results["files"]:
        file_name = Path(file_path).name
        lines.append(f"- [{file_name}]({file_name})")
    validation = results["validation"]
    lines.extend([
        "",
        "## Status final",
        f"- Screenshots esperados: `{validation['expected_screenshots']}`",
        f"- Screenshots encontrados: `{validation['actual_screenshots']}`",
        f"- Problemas automaticos: `{validation['issue_count']}`",
        f"- Resultado: `{'OK' if validation['ok'] else 'FALHA'}`",
    ])
    return "\n".join(lines) + "\n"


def run(args: argparse.Namespace) -> int:
    output_root = Path(args.output_root or REPO_ROOT / "runtime" / "visual-audit" / SLUG)
    output_dir = output_root / now_stamp()
    output_dir.mkdir(parents=True, exist_ok=True)
    proxy, capture_base_url = start_fixture_proxy()
    chrome_path = base.find_chromium()
    debug_port = base.choose_debug_port()
    user_data_dir = Path(tempfile.mkdtemp(prefix="ct-missoes-audit-"))
    process = base.launch_chromium(chrome_path, debug_port, user_data_dir)
    cdp: base.CDPClient | None = None
    results: dict[str, Any] = {
        "generated_at": iso_now(),
        "route": ROUTE,
        "base_url": capture_base_url,
        "browser": str(chrome_path),
        "viewports": [viewport.__dict__ for viewport in VIEWPORTS],
        "states": [state.__dict__ for state in STATES],
        "captures": [],
        "navigation_stability": [],
        "issues": [],
        "files": [],
    }
    try:
        base.wait_for_devtools(debug_port)
        cdp = base.CDPClient(base.new_page_ws_url(debug_port))
        base.enable_page(cdp)
        selected_viewports = VIEWPORTS[: args.max_viewports] if args.max_viewports else VIEWPORTS
        selected_states = STATES[: args.max_states] if args.max_states else STATES
        for viewport in selected_viewports:
            for state in selected_states:
                print(f"[capture] {state.key} {viewport.width}x{viewport.height}", flush=True)
                entry = capture_state(cdp, capture_base_url, output_dir, viewport, state)
                results["captures"].append(entry)
                results["issues"].extend(entry["issues"])
        if not args.skip_stability:
            for viewport in STABILITY_VIEWPORTS:
                print(f"[navigation] {viewport.width}x{viewport.height}", flush=True)
                entry = capture_navigation_stability(cdp, capture_base_url, output_dir, viewport)
                results["navigation_stability"].append(entry)
                results["issues"].extend(entry["issues"])
    finally:
        if cdp is not None:
            cdp.close()
        process.terminate()
        try:
            process.wait(timeout=5)
        except Exception:
            process.kill()
        proxy.shutdown()
        proxy.server_close()
        shutil.rmtree(user_data_dir, ignore_errors=True)
    contact_sheet = build_contact_sheet(output_dir)
    files = all_pngs(output_dir)
    if contact_sheet and contact_sheet not in files:
        files.append(contact_sheet)
    results["files"] = [str(path) for path in sorted(files)]
    results["validation"] = validate(results)
    metadata_path = output_dir / f"{SLUG}__metadata.json"
    report_path = output_dir / f"{SLUG}__relatorio.md"
    metadata_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(markdown_report(results), encoding="utf-8")
    print(f"OUTPUT_DIR={output_dir}")
    print(f"REPORT={report_path}")
    print(f"METADATA={metadata_path}")
    print(f"VALIDATION_OK={results['validation']['ok']}")
    return 0 if results["validation"]["ok"] else 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Captura auditoria visual responsiva de Financeiro > Missoes.")
    parser.add_argument("--output-root", default="", help="Diretorio raiz para salvar evidencias.")
    parser.add_argument("--max-viewports", type=int, default=0, help="Diagnostico: captura apenas os N primeiros viewports.")
    parser.add_argument("--max-states", type=int, default=0, help="Diagnostico: captura apenas os N primeiros estados.")
    parser.add_argument("--skip-stability", action="store_true", help="Pula teste rapido de estabilidade de hash.")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
