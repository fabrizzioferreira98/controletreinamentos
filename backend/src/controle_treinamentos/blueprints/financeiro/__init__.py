from flask import Blueprint

financeiro_bp = Blueprint("financeiro", __name__)

from ...api.http.financeiro import routes as api_routes  # noqa: E402, F401
