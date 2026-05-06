from flask import Blueprint

relatorios_bp = Blueprint('relatorios', __name__)

from . import routes as routes  # noqa: E402, F401
from ...api.http.relatorios import routes as api_routes  # noqa: E402, F401
