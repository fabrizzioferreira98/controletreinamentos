from __future__ import annotations

import argparse
import base64
import json
import math
import os
import random
import shutil
import socket
import string
import struct
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.cookiejar import CookieJar
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib import error, parse, request


REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTE = "#/relatorios/habilitacoes"
SLUG = "relatorios-consolidado-habilitacoes"
DEFAULT_BASE_URL = "http://127.0.0.1:5000"
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


@dataclass(frozen=True)
class Viewport:
    category: str
    width: int
    height: int
    label: str = ""


VIEWPORTS = [
    Viewport("mobile", 320, 568, "mobile muito estreito"),
    Viewport("mobile", 360, 640, "mobile comum"),
    Viewport("mobile", 375, 667, "iPhone SE / compacto"),
    Viewport("mobile", 390, 844, "iPhone moderno"),
    Viewport("mobile", 414, 896, "mobile grande"),
    Viewport("mobile", 430, 932, "mobile grande atual"),
    Viewport("tablet", 768, 1024, "tablet vertical"),
    Viewport("tablet", 820, 1180, "iPad Air vertical"),
    Viewport("tablet", 1024, 768, "tablet horizontal"),
    Viewport("tablet", 1180, 820, "iPad Air horizontal"),
    Viewport("desktop", 1280, 720, "notebook HD"),
    Viewport("desktop", 1366, 768, "notebook comum"),
    Viewport("desktop", 1440, 900, "desktop/notebook medio"),
    Viewport("desktop", 1536, 864, "desktop escalado"),
    Viewport("desktop", 1600, 900, "desktop widescreen"),
    Viewport("desktop", 1920, 1080, "Full HD"),
    Viewport("desktop", 2560, 1440, "QHD"),
    Viewport("tv", 1920, 1080, "TV Full HD"),
    Viewport("tv", 2560, 1440, "TV QHD"),
    Viewport("tv", 3840, 2160, "TV 4K"),
]

STABILITY_VIEWPORTS = [
    Viewport("stability", 390, 844),
    Viewport("stability", 768, 1024),
    Viewport("stability", 1366, 768),
    Viewport("stability", 1920, 1080),
    Viewport("stability", 3840, 2160),
]


class CaptureError(RuntimeError):
    pass


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


def ensure_repo_importable() -> None:
    repo = str(REPO_ROOT)
    if repo not in sys.path:
        sys.path.insert(0, repo)


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def find_chromium() -> Path:
    candidates = [
        os.environ.get("CHROME_PATH", ""),
        os.environ.get("EDGE_PATH", ""),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for candidate in candidates:
        if candidate:
            path = Path(candidate)
            if path.exists():
                return path
    for name in ("chrome", "chrome.exe", "msedge", "msedge.exe", "chromium", "chromium-browser"):
        resolved = shutil.which(name)
        if resolved:
            return Path(resolved)
    raise CaptureError("Chrome/Edge/Chromium nao encontrado para captura.")


def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def choose_debug_port() -> int:
    for _ in range(80):
        port = random.randint(9300, 9900)
        if not port_open(port):
            return port
    raise CaptureError("Nao foi possivel reservar uma porta local para DevTools.")


def choose_local_port() -> int:
    for _ in range(80):
        port = random.randint(8700, 9299)
        if not port_open(port):
            return port
    raise CaptureError("Nao foi possivel reservar porta local para proxy da SPA.")


def http_json(url: str, *, method: str = "GET", timeout: float = 10.0) -> Any:
    req = request.Request(url, method=method)
    with request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_devtools(port: int, timeout: float = 20.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    last_error = ""
    url = f"http://127.0.0.1:{port}/json/version"
    while time.time() < deadline:
        try:
            return http_json(url, timeout=1.0)
        except Exception as exc:  # noqa: BLE001 - only used for readiness polling.
            last_error = str(exc)
            time.sleep(0.25)
    raise CaptureError(f"DevTools nao ficou pronto em {timeout:.0f}s. Ultimo erro: {last_error}")


def launch_chromium(chrome_path: Path, port: int, user_data_dir: Path) -> subprocess.Popen:
    args = [
        str(chrome_path),
        "--headless=new",
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-client-side-phishing-detection",
        "--disable-default-apps",
        "--disable-dev-shm-usage",
        "--disable-extensions",
        "--disable-features=Translate,BackForwardCache",
        "--disable-popup-blocking",
        "--disable-renderer-backgrounding",
        "--force-device-scale-factor=1",
        "--high-dpi-support=1",
        "--window-size=1280,720",
        "about:blank",
    ]
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class FrontendProxyHandler(SimpleHTTPRequestHandler):
    backend_base_url = DEFAULT_BASE_URL
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

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API.
        if self._should_proxy():
            self._proxy()
            return
        self._serve_spa()

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler API.
        if self._should_proxy():
            self._proxy(head_only=True)
            return
        self._serve_spa(head_only=True)

    def _should_proxy(self) -> bool:
        parsed = parse.urlsplit(self.path)
        return parsed.path.startswith("/api/") or parsed.path.startswith("/static/")

    def _proxy(self, *, head_only: bool = False) -> None:
        target = f"{self.backend_base_url.rstrip('/')}{self.path}"
        headers = {}
        for key in [
            "Accept",
            "Accept-Language",
            "Cookie",
            "Content-Type",
            "If-Modified-Since",
            "If-None-Match",
            "X-Correlation-ID",
            "X-CSRFToken",
            "X-Request-ID",
            "X-Requested-With",
        ]:
            value = self.headers.get(key)
            if value:
                headers[key] = value
        req = request.Request(target, method="HEAD" if head_only else "GET", headers=headers)
        try:
            with request.urlopen(req, timeout=45) as response:
                body = b"" if head_only else response.read()
                self.send_response(response.status)
                for key, value in response.headers.items():
                    lowered = key.lower()
                    if lowered in {"connection", "content-encoding", "content-length", "transfer-encoding"}:
                        continue
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if not head_only:
                    self.wfile.write(body)
        except error.HTTPError as exc:
            body = b"" if head_only else exc.read()
            self.send_response(exc.code)
            for key, value in exc.headers.items():
                lowered = key.lower()
                if lowered in {"connection", "content-encoding", "content-length", "transfer-encoding"}:
                    continue
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if not head_only:
                self.wfile.write(body)
        except Exception as exc:  # noqa: BLE001 - convert proxy failures into visible HTTP errors.
            body = f"Proxy local da auditoria falhou ao buscar {target}: {exc}".encode("utf-8")
            self.send_response(HTTPStatus.BAD_GATEWAY)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if not head_only:
                self.wfile.write(body)

    def _serve_spa(self, *, head_only: bool = False) -> None:
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
        if head_only:
            super().do_HEAD()
        else:
            super().do_GET()


def start_frontend_proxy(backend_base_url: str) -> tuple[ThreadingHTTPServer, str]:
    if not FRONTEND_DIST.exists():
        raise CaptureError(f"Build frontend nao encontrado em {FRONTEND_DIST}.")
    port = choose_local_port()
    handler = type(
        "BoundFrontendProxyHandler",
        (FrontendProxyHandler,),
        {"backend_base_url": backend_base_url, "frontend_dir": FRONTEND_DIST},
    )
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, name="visual-audit-frontend-proxy", daemon=True)
    thread.start()
    return server, f"http://localhost:{port}"


class WebSocket:
    def __init__(self, ws_url: str):
        parsed = parse.urlparse(ws_url)
        if parsed.scheme != "ws":
            raise CaptureError(f"URL WebSocket invalida: {ws_url}")
        self.host = parsed.hostname or "127.0.0.1"
        self.port = parsed.port or 80
        self.path = parsed.path or "/"
        if parsed.query:
            self.path = f"{self.path}?{parsed.query}"
        self.sock = socket.create_connection((self.host, self.port), timeout=20)
        self.sock.settimeout(60)
        self._handshake()

    def _handshake(self) -> None:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        headers = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        self.sock.sendall(headers.encode("ascii"))
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self.sock.recv(4096)
            if not chunk:
                break
            response += chunk
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise CaptureError(f"Handshake WebSocket falhou: {response[:200]!r}")

    def send_text(self, payload: str) -> None:
        data = payload.encode("utf-8")
        header = bytearray([0x81])
        length = len(data)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(data))
        self.sock.sendall(bytes(header) + mask + masked)

    def _read_exact(self, size: int) -> bytes:
        data = bytearray()
        while len(data) < size:
            chunk = self.sock.recv(size - len(data))
            if not chunk:
                raise CaptureError("Conexao WebSocket encerrada durante leitura.")
            data.extend(chunk)
        return bytes(data)

    def recv_text(self) -> str:
        chunks: list[bytes] = []
        while True:
            first, second = self._read_exact(2)
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._read_exact(8))[0]
            mask = self._read_exact(4) if masked else b""
            payload = self._read_exact(length) if length else b""
            if masked:
                payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
            if opcode == 0x8:
                raise CaptureError("Conexao WebSocket fechada pelo navegador.")
            if opcode == 0x9:
                self._send_pong(payload)
                continue
            if opcode in (0x0, 0x1):
                chunks.append(payload)
                if first & 0x80:
                    return b"".join(chunks).decode("utf-8")

    def _send_pong(self, payload: bytes) -> None:
        header = bytearray([0x8A])
        length = len(payload)
        header.append(0x80 | length)
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class CDPClient:
    def __init__(self, ws_url: str):
        self.ws = WebSocket(ws_url)
        self.next_id = 1
        self.events: list[dict[str, Any]] = []

    def call(self, method: str, params: dict[str, Any] | None = None, timeout: float = 60.0) -> Any:
        message_id = self.next_id
        self.next_id += 1
        payload = {"id": message_id, "method": method}
        if params is not None:
            payload["params"] = params
        self.ws.send_text(json.dumps(payload, separators=(",", ":")))
        deadline = time.time() + timeout
        while time.time() < deadline:
            raw = self.ws.recv_text()
            message = json.loads(raw)
            if message.get("id") == message_id:
                if "error" in message:
                    raise CaptureError(f"CDP {method} falhou: {message['error']}")
                return message.get("result")
            self.events.append(message)
        raise CaptureError(f"Timeout em CDP {method}.")

    def close(self) -> None:
        self.ws.close()


def new_page_ws_url(port: int) -> str:
    encoded = parse.quote("about:blank", safe="")
    endpoints = [
        (f"http://127.0.0.1:{port}/json/new?{encoded}", "PUT"),
        (f"http://127.0.0.1:{port}/json/new?{encoded}", "GET"),
    ]
    last_error = ""
    for url, method in endpoints:
        try:
            payload = http_json(url, method=method)
            ws_url = payload.get("webSocketDebuggerUrl")
            if ws_url:
                return ws_url
        except Exception as exc:  # noqa: BLE001 - fallback across Chrome variants.
            last_error = str(exc)
    pages = http_json(f"http://127.0.0.1:{port}/json/list")
    for page in pages:
        ws_url = page.get("webSocketDebuggerUrl")
        if ws_url:
            return ws_url
    raise CaptureError(f"Nao foi possivel abrir alvo CDP. Ultimo erro: {last_error}")


def url_join(base_url: str, route: str = ROUTE) -> str:
    return f"{base_url.rstrip('/')}/{route}"


def health_check(base_url: str) -> dict[str, Any]:
    try:
        return http_json(f"{base_url.rstrip('/')}/healthz", timeout=8.0)
    except Exception as exc:  # noqa: BLE001 - report readiness failure clearly.
        raise CaptureError(f"Aplicacao local nao respondeu em /healthz: {exc}") from exc


def make_session_cookie(login_hint: str = "") -> dict[str, Any]:
    ensure_repo_importable()
    from flask import session
    from flask_login import login_user

    from backend.src.controle_treinamentos import create_app
    from backend.src.controle_treinamentos.core.auth_contract import establish_auth_session
    from backend.src.controle_treinamentos.db import get_db
    from backend.src.controle_treinamentos.models import User

    app = create_app()
    selected = None
    with app.app_context():
        db = get_db()
        candidates: list[tuple[str, tuple[Any, ...]]] = []
        if login_hint:
            candidates.append(
                (
                    """
                    SELECT id, nome, login, email, perfil, ativo, permissao_modulos_json
                    FROM usuarios
                    WHERE login = %s AND ativo = 1
                    LIMIT 1
                    """,
                    (login_hint,),
                )
            )
        candidates.append(
            (
                """
                SELECT id, nome, login, email, perfil, ativo, permissao_modulos_json
                FROM usuarios
                WHERE ativo = 1 AND perfil = 'gestora'
                ORDER BY
                    CASE
                        WHEN login = 'qa_admin' THEN 0
                        WHEN login LIKE 'qa_%%' THEN 1
                        ELSE 2
                    END,
                    id
                LIMIT 1
                """,
                (),
            )
        )
        for query, params in candidates:
            row = db.execute(query, params).fetchone()
            if row:
                selected = row
                break

    if selected is None:
        raise CaptureError("Nao ha usuario QA/gestora ativo para sessao local de auditoria.")

    with app.test_request_context("/"):
        session.clear()
        establish_auth_session(remember_requested=False)
        user = User(
            selected["id"],
            selected["nome"],
            selected["login"],
            selected["email"],
            selected["perfil"],
            selected["ativo"],
            selected.get("permissao_modulos_json", "[]"),
        )
        login_user(user, remember=False, fresh=True)
        now = int(time.time())
        session["auth_user_snapshot"] = {
            "id": str(selected["id"]),
            "nome": selected["nome"] or "",
            "login": selected["login"] or "",
            "email": selected["email"] or "",
            "perfil": selected["perfil"] or "",
            "ativo": int(selected["ativo"] or 0),
            "permissao_modulos_json": selected.get("permissao_modulos_json", "[]"),
            "captured_at": now,
        }
        session["auth_user_snapshot_ts"] = now
        serializer = app.session_interface.get_signing_serializer(app)
        if serializer is None:
            raise CaptureError("Nao foi possivel obter serializer de sessao Flask.")
        cookie_value = serializer.dumps(dict(session))
        return {
            "name": app.config.get("SESSION_COOKIE_NAME", "session"),
            "value": cookie_value,
            "path": app.config.get("SESSION_COOKIE_PATH") or "/",
            "sameSite": "Lax",
            "secure": bool(app.config.get("SESSION_COOKIE_SECURE")),
            "httpOnly": bool(app.config.get("SESSION_COOKIE_HTTPONLY", True)),
            "login": selected["login"],
            "user_id": str(selected["id"]),
            "mode": "signed-local-session",
        }


def api_login_cookie(base_url: str) -> dict[str, Any] | None:
    login = os.environ.get("E2E_LOGIN", "").strip()
    password = os.environ.get("E2E_PASSWORD", "").strip()
    if not login or not password:
        return None
    jar = CookieJar()
    opener = request.build_opener(request.HTTPCookieProcessor(jar))
    session_response = opener.open(
        request.Request(f"{base_url.rstrip('/')}/api/v1/session", headers={"Accept": "application/json"}),
        timeout=10,
    )
    csrf_token = json.loads(session_response.read().decode("utf-8")).get("csrf_token") or ""
    body = json.dumps({"login": login, "senha": password}).encode("utf-8")
    login_request = request.Request(
        f"{base_url.rstrip('/')}/api/v1/session/login",
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-CSRFToken": csrf_token,
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    try:
        response = opener.open(login_request, timeout=10)
        payload = json.loads(response.read().decode("utf-8"))
        if not payload.get("authenticated"):
            return None
    except error.HTTPError:
        return None
    session_cookie = next((cookie for cookie in jar if cookie.name), None)
    if session_cookie is None:
        return None
    return {
        "name": session_cookie.name,
        "value": session_cookie.value,
        "path": session_cookie.path or "/",
        "sameSite": "Lax",
        "secure": bool(session_cookie.secure),
        "httpOnly": True,
        "login": login,
        "user_id": "",
        "mode": "api-login-e2e",
    }


def resolve_auth_cookie(base_url: str) -> dict[str, Any]:
    cookie = api_login_cookie(base_url)
    if cookie is not None:
        return cookie
    return make_session_cookie(os.environ.get("E2E_LOGIN", "").strip())


def report_data_snapshot() -> dict[str, Any]:
    ensure_repo_importable()
    from backend.src.controle_treinamentos import create_app
    from backend.src.controle_treinamentos.application.relatorios import get_habilitacoes_report_data
    from backend.src.controle_treinamentos.db import get_db

    app = create_app()
    with app.app_context():
        payload = get_habilitacoes_report_data(get_db())
    summary = payload.get("summary") or {}
    total_habilitacoes = int(summary.get("total_habilitacoes") or 0)
    total_tripulantes = int(summary.get("total_tripulantes") or 0)
    return {
        "mode": "real-db" if total_habilitacoes or total_tripulantes else "empty-real-db",
        "summary": summary,
        "items_count": len(payload.get("items") or []),
        "emitted_at": payload.get("emitted_at") or "",
    }


def enable_page(cdp: CDPClient) -> None:
    cdp.call("Page.enable")
    cdp.call("Runtime.enable")
    cdp.call("Network.enable")


def apply_cookie(cdp: CDPClient, base_url: str, cookie: dict[str, Any]) -> None:
    params = {
        "url": base_url.rstrip("/") + "/",
        "name": cookie["name"],
        "value": cookie["value"],
        "path": cookie.get("path") or "/",
        "httpOnly": bool(cookie.get("httpOnly", True)),
        "secure": bool(cookie.get("secure", False)),
        "sameSite": cookie.get("sameSite", "Lax"),
    }
    result = cdp.call("Network.setCookie", params)
    if not result.get("success"):
        raise CaptureError("Falha ao aplicar cookie de sessao no navegador.")


def set_viewport(cdp: CDPClient, viewport: Viewport) -> None:
    mobile = viewport.category == "mobile"
    cdp.call(
        "Emulation.setDeviceMetricsOverride",
        {
            "width": viewport.width,
            "height": viewport.height,
            "deviceScaleFactor": 1,
            "mobile": mobile,
            "screenWidth": viewport.width,
            "screenHeight": viewport.height,
            "positionX": 0,
            "positionY": 0,
        },
    )
    cdp.call("Emulation.setTouchEmulationEnabled", {"enabled": mobile or viewport.category == "tablet"})


def runtime_value(cdp: CDPClient, expression: str, timeout: float = 60.0) -> Any:
    result = cdp.call(
        "Runtime.evaluate",
        {
            "expression": expression,
            "awaitPromise": True,
            "returnByValue": True,
            "timeout": int(timeout * 1000),
        },
        timeout=timeout + 5,
    )
    if "exceptionDetails" in result:
        raise CaptureError(f"Runtime.evaluate falhou: {result['exceptionDetails']}")
    return (result.get("result") or {}).get("value")


def wait_for_stable_page(cdp: CDPClient, timeout: float = 70.0) -> dict[str, Any]:
    expression = f"""
    new Promise((resolve) => {{
      const started = Date.now();
      const timeoutMs = {int(timeout * 1000)};
      const check = () => {{
        const bodyText = document.body ? document.body.innerText : "";
        const routeOk = (window.location.hash || "").split("?")[0] === "{ROUTE}";
        const hasTarget = /Consolidado de habilita/i.test(bodyText) || /Falha ao carregar o consolidado/i.test(bodyText) || /Acesso negado/i.test(bodyText);
        const loading = /Carregando consolidado/i.test(bodyText);
        const ready = document.readyState === "complete" && routeOk && hasTarget && !loading;
        if (ready) {{
          const finish = () => requestAnimationFrame(() => requestAnimationFrame(() => resolve({{
            route: window.location.hash,
            title: document.title,
            textSample: bodyText.slice(0, 1200),
            hasTarget: /Consolidado de habilita/i.test(bodyText),
            hasError: /Falha ao carregar|Acesso negado|Rota nao encontrada|NÃ£o foi possÃ­vel conectar/i.test(bodyText),
          }})));
          if (document.fonts && document.fonts.ready) {{
            document.fonts.ready.then(finish).catch(finish);
          }} else {{
            finish();
          }}
          return;
        }}
        if (Date.now() - started > timeoutMs) {{
          resolve({{
            route: window.location.hash,
            title: document.title,
            textSample: bodyText.slice(0, 1200),
            hasTarget: /Consolidado de habilita/i.test(bodyText),
            hasError: true,
            timedOut: true,
          }});
          return;
        }}
        setTimeout(check, 250);
      }};
      check();
    }})
    """
    return runtime_value(cdp, expression, timeout=timeout)


def navigate_and_wait(cdp: CDPClient, url: str) -> dict[str, Any]:
    cdp.call("Page.navigate", {"url": url}, timeout=20)
    state = wait_for_stable_page(cdp)
    time.sleep(0.25)
    return state


def capture_png(cdp: CDPClient, path: Path, *, full_page: bool, viewport: Viewport) -> dict[str, Any]:
    params: dict[str, Any] = {"format": "png", "fromSurface": True}
    metrics: dict[str, Any] | None = None
    if full_page:
        metrics = cdp.call("Page.getLayoutMetrics")
        content = metrics.get("contentSize") or {}
        width = max(viewport.width, math.ceil(float(content.get("width") or viewport.width)))
        height = max(viewport.height, math.ceil(float(content.get("height") or viewport.height)))
        params.update(
            {
                "captureBeyondViewport": True,
                "clip": {"x": 0, "y": 0, "width": width, "height": height, "scale": 1},
            }
        )
    result = cdp.call("Page.captureScreenshot", params, timeout=120)
    data = base64.b64decode(result["data"])
    path.write_bytes(data)
    return {
        "path": str(path),
        "bytes": len(data),
        "fullPage": full_page,
        "layoutMetrics": metrics,
    }


def collect_dom_metrics(cdp: CDPClient) -> dict[str, Any]:
    expression = """
    (() => {
      const doc = document.documentElement;
      const body = document.body;
      const viewport = { width: window.innerWidth, height: window.innerHeight };
      const scrollWidth = Math.max(doc?.scrollWidth || 0, body?.scrollWidth || 0);
      const scrollHeight = Math.max(doc?.scrollHeight || 0, body?.scrollHeight || 0);
      const selectors = {
        header: ".page-header, .priority-page-header, .ui-page-header",
        filters: "#habilitacoes-filter-form, .filters-bar",
        summaryCards: ".summary-card",
        table: ".consolidated-table, table",
        tableWrap: ".consolidated-table-wrap, .ui-table-wrap",
        nav: ".app-sidebar, .nav-shell, nav, .app-nav",
        actions: ".page-header-actions",
        error: ".route-state, .ui-feedback[data-kind='error']"
      };
      const counts = {};
      const visibility = {};
      for (const [key, selector] of Object.entries(selectors)) {
        const nodes = Array.from(document.querySelectorAll(selector));
        counts[key] = nodes.length;
        visibility[key] = nodes.some((node) => {
          const rect = node.getBoundingClientRect();
          const style = window.getComputedStyle(node);
          return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
        });
      }
      const offscreen = Array.from(document.querySelectorAll("body *"))
        .map((node) => {
          const rect = node.getBoundingClientRect();
          if (!rect || rect.width <= 0 || rect.height <= 0) return null;
          const style = window.getComputedStyle(node);
          if (style.visibility === "hidden" || style.display === "none") return null;
          const overLeft = rect.left < -2;
          const overRight = rect.right > viewport.width + 2;
          if (!overLeft && !overRight) return null;
          const className = typeof node.className === "string" ? node.className : "";
          return {
            tag: node.tagName.toLowerCase(),
            className: className.slice(0, 160),
            text: (node.innerText || node.textContent || "").trim().replace(/\\s+/g, " ").slice(0, 160),
            left: Math.round(rect.left),
            right: Math.round(rect.right),
            width: Math.round(rect.width)
          };
        })
        .filter(Boolean)
        .slice(0, 30);
      return {
        url: location.href,
        route: location.hash,
        title: document.title,
        viewport,
        scrollWidth,
        scrollHeight,
        horizontalOverflow: scrollWidth > viewport.width + 2,
        verticalScroll: scrollHeight > viewport.height + 2,
        counts,
        visibility,
        offscreen,
        bodyTextSample: (document.body?.innerText || "").trim().replace(/\\s+/g, " ").slice(0, 1800),
      };
    })()
    """
    return runtime_value(cdp, expression, timeout=10)


def image_metrics(path: Path) -> dict[str, Any]:
    try:
        from PIL import Image, ImageStat
    except ImportError:
        return {"available": False}
    with Image.open(path) as img:
        stat = ImageStat.Stat(img.convert("RGB"))
        extrema = img.convert("RGB").getextrema()
        mean = stat.mean
        variance = stat.var
        nearly_blank = max(variance) < 8 and min(mean) > 245
        return {
            "available": True,
            "width": img.width,
            "height": img.height,
            "mode": img.mode,
            "mean": [round(value, 2) for value in mean],
            "variance": [round(value, 2) for value in variance],
            "extrema": extrema,
            "nearlyBlank": nearly_blank,
        }


def expected_filename(viewport: Viewport, kind: str) -> str:
    return f"{SLUG}__{viewport.category}__{viewport.width}x{viewport.height}__{kind}.png"


def stability_filename(viewport: Viewport, pass_number: int) -> str:
    return f"{SLUG}__stability__{viewport.width}x{viewport.height}__pass-{pass_number}.png"


def issue_from_metrics(viewport: Viewport, metrics: dict[str, Any], state: dict[str, Any], image: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    viewport_key = f"{viewport.category} {viewport.width}x{viewport.height}"
    if image.get("nearlyBlank"):
        issues.append(
            {
                "viewport": viewport_key,
                "severity": "CRITICO",
                "description": "Screenshot aparenta estar vazio ou quase todo branco.",
                "recommendation": "Investigar carregamento inicial, autenticação e assets antes de validar responsividade.",
            }
        )
    if state.get("timedOut") or not state.get("hasTarget"):
        issues.append(
            {
                "viewport": viewport_key,
                "severity": "CRITICO",
                "description": "A tela alvo nao estabilizou com o titulo do Consolidado de Habilitações.",
                "recommendation": "Corrigir carregamento/roteamento ou revisar tempo de API antes de usar a evidencia visual.",
            }
        )
    if state.get("hasError"):
        issues.append(
            {
                "viewport": viewport_key,
                "severity": "CRITICO",
                "description": "A pagina renderizou estado de erro, acesso negado ou falha de carregamento.",
                "recommendation": "Validar autenticação, permissões e resposta de `/api/v1/relatorios/habilitacoes`.",
            }
        )
    if metrics.get("horizontalOverflow"):
        issues.append(
            {
                "viewport": viewport_key,
                "severity": "ALTO" if viewport.width <= 820 else "MEDIO",
                "description": f"Overflow horizontal detectado: document.scrollWidth={metrics.get('scrollWidth')} para viewport={viewport.width}.",
                "recommendation": "Revisar containers, ações do header, tabela e largura mínima de cards/filtros nesse breakpoint.",
            }
        )
    visibility = metrics.get("visibility") or {}
    for key, label in [
        ("header", "header/título"),
        ("filters", "filtros"),
        ("summaryCards", "cards de resumo"),
        ("table", "tabela/listagem"),
    ]:
        if not visibility.get(key):
            issues.append(
                {
                    "viewport": viewport_key,
                    "severity": "ALTO",
                    "description": f"Bloco essencial invisível ou ausente: {label}.",
                    "recommendation": "Verificar regras responsivas e permissões de renderização do componente.",
                }
            )
    return issues


def capture_viewport_set(
    cdp: CDPClient,
    base_url: str,
    output_dir: Path,
    viewport: Viewport,
) -> dict[str, Any]:
    set_viewport(cdp, viewport)
    state = navigate_and_wait(cdp, url_join(base_url))
    metrics = collect_dom_metrics(cdp)
    viewport_path = output_dir / expected_filename(viewport, "viewport")
    fullpage_path = output_dir / expected_filename(viewport, "fullpage")
    viewport_capture = capture_png(cdp, viewport_path, full_page=False, viewport=viewport)
    fullpage_capture = capture_png(cdp, fullpage_path, full_page=True, viewport=viewport)
    viewport_image = image_metrics(viewport_path)
    fullpage_image = image_metrics(fullpage_path)
    issues = issue_from_metrics(viewport, metrics, state, viewport_image)
    return {
        "viewport": viewport.__dict__,
        "state": state,
        "metrics": metrics,
        "captures": {
            "viewport": {**viewport_capture, "image": viewport_image},
            "fullpage": {**fullpage_capture, "image": fullpage_image},
        },
        "issues": issues,
    }


def capture_stability(
    cdp: CDPClient,
    base_url: str,
    output_dir: Path,
    viewport: Viewport,
) -> dict[str, Any]:
    set_viewport(cdp, viewport)
    state = navigate_and_wait(cdp, url_join(base_url))
    pass_results = []
    for index in (1, 2):
        path = output_dir / stability_filename(viewport, index)
        capture = capture_png(cdp, path, full_page=False, viewport=viewport)
        capture["image"] = image_metrics(path)
        capture["sha256"] = sha256(path)
        pass_results.append(capture)
        if index == 1:
            time.sleep(1.5)
    return {
        "viewport": viewport.__dict__,
        "state": state,
        "passes": pass_results,
        "stableHash": pass_results[0]["sha256"] == pass_results[1]["sha256"],
    }


def sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def all_screenshot_paths(output_dir: Path) -> list[Path]:
    return sorted(path for path in output_dir.glob(f"{SLUG}__*.png") if "__contact-sheet__" not in path.name)


def validate_outputs(output_dir: Path, results: dict[str, Any]) -> dict[str, Any]:
    expected = []
    for viewport in VIEWPORTS:
        expected.append(output_dir / expected_filename(viewport, "viewport"))
        expected.append(output_dir / expected_filename(viewport, "fullpage"))
    for viewport in STABILITY_VIEWPORTS:
        expected.append(output_dir / stability_filename(viewport, 1))
        expected.append(output_dir / stability_filename(viewport, 2))
    missing = [str(path) for path in expected if not path.exists()]
    pattern_failures = []
    for path in all_screenshot_paths(output_dir):
        parts = path.name.split("__")
        if not path.name.endswith(".png") or len(parts) != 4 or parts[0] != SLUG:
            pattern_failures.append(str(path))
    blank = []
    wrong_screen = []
    for entry in results.get("captures", []):
        viewport_path = Path(entry["captures"]["viewport"]["path"])
        if entry["captures"]["viewport"].get("image", {}).get("nearlyBlank"):
            blank.append(str(viewport_path))
        if not entry.get("state", {}).get("hasTarget"):
            wrong_screen.append(str(viewport_path))
    return {
        "expectedCount": len(expected),
        "actualCount": len(all_screenshot_paths(output_dir)),
        "missing": missing,
        "patternFailures": pattern_failures,
        "blankOrNearlyBlank": blank,
        "wrongScreenCandidates": wrong_screen,
        "ok": not missing and not pattern_failures and not blank and not wrong_screen,
    }


def markdown_report(output_dir: Path, results: dict[str, Any]) -> str:
    route_url = results["route_url"]
    route = results["route"]
    generated_at = results["generated_at"]
    environment = results["environment"]
    data_snapshot = results["data_snapshot"]
    validation = results["validation"]
    files = [Path(path).name for path in results["files"]]
    issues = results["issues"]
    stability = results["stability"]

    lines: list[str] = []
    lines.append(f"# Auditoria visual - Relatórios / Consolidado de Habilitações")
    lines.append("")
    lines.append("## 1. Rota auditada")
    lines.append("")
    lines.append(f"- URL usada: `{route_url}`")
    lines.append(f"- Rota SPA: `{route}`")
    lines.append("- Origem da rota: `frontend/src/app/route-registry.js` e menu `frontend/src/shell/navigation.js`")
    lines.append("")
    lines.append("## 2. Data/hora da captura")
    lines.append("")
    lines.append(f"- Captura gerada em: `{generated_at}`")
    lines.append("")
    lines.append("## 3. Ambiente usado")
    lines.append("")
    lines.append(f"- URL da SPA capturada: `{environment['base_url']}`")
    lines.append(f"- Backend real usado pelo proxy: `{environment.get('backend_base_url', environment['base_url'])}`")
    lines.append(f"- Navegador: `{environment['browser']}`")
    lines.append(f"- Estratégia de captura: `{environment['capture_strategy']}`")
    lines.append(f"- Autenticação da auditoria: `{environment['auth_mode']}`")
    lines.append(f"- Usuário técnico usado: `{environment['auth_login']}`")
    lines.append(f"- Healthcheck: `{json.dumps(environment['health'], ensure_ascii=False)}`")
    lines.append("")
    lines.append("## 4. Dados carregados")
    lines.append("")
    lines.append(f"- Modo de dados: `{data_snapshot['mode']}`")
    lines.append(f"- Grupos retornados: `{data_snapshot.get('items_count')}`")
    lines.append(f"- Total de tripulantes: `{data_snapshot.get('summary', {}).get('total_tripulantes')}`")
    lines.append(f"- Total de habilitações: `{data_snapshot.get('summary', {}).get('total_habilitacoes')}`")
    lines.append(f"- Emissão reportada pelo backend: `{data_snapshot.get('emitted_at')}`")
    lines.append("")
    lines.append("## 5. Viewports testados")
    lines.append("")
    lines.append("| # | Categoria | Viewport | Cenário |")
    lines.append("| --- | --- | --- | --- |")
    for index, viewport in enumerate(VIEWPORTS, start=1):
        lines.append(f"| {index} | {viewport.category} | {viewport.width}x{viewport.height} | {viewport.label} |")
    lines.append("")
    lines.append("## 6. Arquivos gerados")
    lines.append("")
    for file_name in files:
        lines.append(f"- [{file_name}]({file_name})")
    lines.append("")
    lines.append("## 7. Problemas encontrados")
    lines.append("")
    if issues:
        lines.append("| Viewport | Severidade | Descrição | Evidência | Recomendação |")
        lines.append("| --- | --- | --- | --- | --- |")
        for issue in issues:
            evidence = issue.get("evidence", "")
            lines.append(
                f"| {issue['viewport']} | {issue['severity']} | {issue['description']} | [{Path(evidence).name}]({Path(evidence).name}) | {issue['recommendation']} |"
            )
    else:
        lines.append("- Nenhum problema automático foi detectado nos checks de carregamento, blocos essenciais, tela em branco e overflow horizontal.")
    lines.append("")
    lines.append("## 8. Recomendações sem implementação")
    lines.append("")
    if issues:
        unique_recommendations = []
        for issue in issues:
            recommendation = issue["recommendation"]
            if recommendation not in unique_recommendations:
                unique_recommendations.append(recommendation)
        for recommendation in unique_recommendations:
            lines.append(f"- {recommendation}")
    else:
        lines.append("- Revisar visualmente os screenshots de mobile e TV para refinamentos finos de densidade, hierarquia e legibilidade.")
    lines.append("- Não foi aplicada nenhuma correção nesta tarefa.")
    lines.append("")
    lines.append("## 9. Observações de responsividade")
    lines.append("")
    for entry in results["captures"]:
        viewport = entry["viewport"]
        metrics = entry["metrics"]
        lines.append(
            f"- `{viewport['category']} {viewport['width']}x{viewport['height']}`: "
            f"scroll vertical={metrics.get('verticalScroll')}, "
            f"overflow horizontal={metrics.get('horizontalOverflow')}, "
            f"scrollWidth={metrics.get('scrollWidth')}, scrollHeight={metrics.get('scrollHeight')}."
        )
    lines.append("")
    lines.append("## 10. Observações de estabilidade visual")
    lines.append("")
    lines.append("| Viewport | Pass 1 | Pass 2 | Hash idêntico | Observação |")
    lines.append("| --- | --- | --- | --- | --- |")
    for item in stability:
        viewport = item["viewport"]
        pass_1 = Path(item["passes"][0]["path"]).name
        pass_2 = Path(item["passes"][1]["path"]).name
        stable = "sim" if item["stableHash"] else "não"
        note = "Sem oscilação binária detectada." if item["stableHash"] else "Diferença binária entre capturas; comparar visualmente para descartar relógios, animações ou flicker."
        lines.append(f"| {viewport['width']}x{viewport['height']} | [{pass_1}]({pass_1}) | [{pass_2}]({pass_2}) | {stable} | {note} |")
    lines.append("")
    lines.append("## 11. Conferência final")
    lines.append("")
    lines.append(f"- Arquivos esperados: `{validation['expectedCount']}`")
    lines.append(f"- Arquivos encontrados: `{validation['actualCount']}`")
    lines.append(f"- Nomes fora do padrão: `{len(validation['patternFailures'])}`")
    lines.append(f"- Arquivos ausentes: `{len(validation['missing'])}`")
    lines.append(f"- Screenshots vazios/quase brancos: `{len(validation['blankOrNearlyBlank'])}`")
    lines.append(f"- Candidatos de tela errada: `{len(validation['wrongScreenCandidates'])}`")
    lines.append(f"- Status geral da conferência: `{'OK' if validation['ok'] else 'FALHA'}`")
    lines.append("")
    lines.append("## 12. Escopo de alterações")
    lines.append("")
    lines.append("- Arquivos de produção alterados: `não`.")
    lines.append("- Script auxiliar criado: `tools/screenshots/capture_habilitacoes_visual_audit.py`.")
    lines.append("- Pasta de evidências: esta pasta do relatório.")
    lines.append("")
    lines.append("## 13. Como executar novamente")
    lines.append("")
    lines.append("```powershell")
    lines.append(r".\.venv\Scripts\python.exe tools\screenshots\capture_habilitacoes_visual_audit.py")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def build_contact_sheet(output_dir: Path) -> Path | None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None
    viewport_files = [output_dir / expected_filename(viewport, "viewport") for viewport in VIEWPORTS]
    thumbs = []
    for path in viewport_files:
        if not path.exists():
            continue
        with Image.open(path) as img:
            thumb = img.convert("RGB")
            thumb.thumbnail((360, 240))
            canvas = Image.new("RGB", (380, 286), "white")
            canvas.paste(thumb, ((380 - thumb.width) // 2, 34))
            draw = ImageDraw.Draw(canvas)
            draw.text((10, 10), path.name.replace(f"{SLUG}__", ""), fill=(20, 30, 40))
            thumbs.append(canvas)
    if not thumbs:
        return None
    columns = 4
    rows = math.ceil(len(thumbs) / columns)
    sheet = Image.new("RGB", (columns * 380, rows * 286), (245, 247, 250))
    for index, thumb in enumerate(thumbs):
        x = (index % columns) * 380
        y = (index // columns) * 286
        sheet.paste(thumb, (x, y))
    path = output_dir / f"{SLUG}__contact-sheet__viewports.png"
    sheet.save(path)
    return path


def run(args: argparse.Namespace) -> int:
    load_env(REPO_ROOT / ".env")
    backend_base_url = args.base_url or os.environ.get("VISUAL_AUDIT_BASE_URL") or DEFAULT_BASE_URL
    output_root = Path(args.output_root or REPO_ROOT / "runtime" / "visual-audit" / SLUG)
    output_dir = output_root / now_stamp()
    output_dir.mkdir(parents=True, exist_ok=True)

    health = health_check(backend_base_url)
    data_snapshot = report_data_snapshot()
    auth_cookie = resolve_auth_cookie(backend_base_url)
    proxy_server, capture_base_url = start_frontend_proxy(backend_base_url)
    chrome_path = find_chromium()
    debug_port = choose_debug_port()
    user_data_dir = Path(tempfile.mkdtemp(prefix="ct-hab-capture-"))
    process = launch_chromium(chrome_path, debug_port, user_data_dir)

    results: dict[str, Any] = {
        "generated_at": iso_now(),
        "route": ROUTE,
        "route_url": url_join(capture_base_url),
        "environment": {
            "base_url": capture_base_url,
            "backend_base_url": backend_base_url,
            "browser": str(chrome_path),
            "capture_strategy": "chromium-devtools-protocol + local-static-frontend-proxy",
            "auth_mode": auth_cookie["mode"],
            "auth_login": auth_cookie["login"],
            "health": health,
        },
        "data_snapshot": data_snapshot,
        "captures": [],
        "stability": [],
        "issues": [],
        "files": [],
    }

    cdp: CDPClient | None = None
    try:
        wait_for_devtools(debug_port)
        cdp = CDPClient(new_page_ws_url(debug_port))
        enable_page(cdp)
        apply_cookie(cdp, capture_base_url, auth_cookie)
        selected_viewports = VIEWPORTS[: args.max_viewports] if args.max_viewports else VIEWPORTS
        selected_stability_viewports = [] if args.skip_stability else STABILITY_VIEWPORTS
        for viewport in selected_viewports:
            print(f"[capture] {viewport.category} {viewport.width}x{viewport.height}", flush=True)
            entry = capture_viewport_set(cdp, capture_base_url, output_dir, viewport)
            for issue in entry["issues"]:
                issue["evidence"] = entry["captures"]["viewport"]["path"]
            results["captures"].append(entry)
            results["issues"].extend(entry["issues"])

        for viewport in selected_stability_viewports:
            print(f"[stability] {viewport.width}x{viewport.height}", flush=True)
            results["stability"].append(capture_stability(cdp, capture_base_url, output_dir, viewport))
    finally:
        if cdp is not None:
            cdp.close()
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        proxy_server.shutdown()
        proxy_server.server_close()
        shutil.rmtree(user_data_dir, ignore_errors=True)

    contact_sheet = build_contact_sheet(output_dir)
    files = all_screenshot_paths(output_dir)
    if contact_sheet:
        files.append(contact_sheet)
    results["files"] = [str(path) for path in sorted(files)]
    results["validation"] = validate_outputs(output_dir, results)

    metadata_path = output_dir / f"{SLUG}__metadata.json"
    write_json(metadata_path, results)
    report_path = output_dir / f"{SLUG}__relatorio.md"
    report_path.write_text(markdown_report(output_dir, results), encoding="utf-8")

    print(f"OUTPUT_DIR={output_dir}")
    print(f"REPORT={report_path}")
    print(f"METADATA={metadata_path}")
    print(f"VALIDATION_OK={results['validation']['ok']}")
    return 0 if results["validation"]["ok"] else 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Captura screenshots responsivos do Relatorios > Consolidado de Habilitacoes."
    )
    parser.add_argument("--base-url", default="", help="Base URL do sistema local. Padrao: http://127.0.0.1:5000")
    parser.add_argument("--output-root", default="", help="Diretorio raiz para salvar evidencias.")
    parser.add_argument("--max-viewports", type=int, default=0, help="Diagnostico: captura apenas os N primeiros viewports.")
    parser.add_argument("--skip-stability", action="store_true", help="Diagnostico: pula capturas duplas de estabilidade.")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
