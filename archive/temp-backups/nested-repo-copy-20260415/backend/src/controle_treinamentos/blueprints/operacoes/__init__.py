from flask import Blueprint

operacoes_bp = Blueprint('operacoes', __name__)

from . import routes as routes  # noqa: E402, F401
