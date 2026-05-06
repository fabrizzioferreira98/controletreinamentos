from flask import Blueprint

operacoes_bp = Blueprint('operacoes', __name__)

from ...api.http.operacoes import routes as api_routes  # noqa: E402, F401
from . import routes as routes  # noqa: E402, F401
