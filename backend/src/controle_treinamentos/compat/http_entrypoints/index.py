import sys
import traceback
from uuid import uuid4

from flask import Flask, jsonify


def _make_fallback_app(*, error_ref: str):
    fallback = Flask(__name__)

    @fallback.route("/", defaults={"path": ""})
    @fallback.route("/<path:path>")
    def boot_error_handler(path):
        return jsonify(
            {
                "success": False,
                "error": "BOOT_FAILURE",
                "message": "Falha interna ao inicializar a aplicacao.",
                "error_ref": error_ref,
            }
        ), 500

    return fallback


def _init_wsgi_compat_app():
    try:
        from backend.src.controle_treinamentos import create_app

        return create_app()
    except BaseException as exc:
        error_ref = uuid4().hex
        error_details = traceback.format_exc()
        sys.stderr.write(f"[APP BOOT FAILURE][ref={error_ref}] {exc}\n{error_details}\n")
        try:
            return _make_fallback_app(error_ref=error_ref)
        except BaseException:
            def raw_wsgi_app(environ, start_response):
                body = f"BOOT_FAILURE ref={error_ref}".encode()
                start_response(
                    "500 Internal Server Error",
                    [
                        ("Content-Type", "text/plain"),
                        ("Content-Length", str(len(body))),
                    ],
                )
                return [body]

            return raw_wsgi_app


app = _init_wsgi_compat_app()
