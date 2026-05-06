from flask import Blueprint

admin_bp = Blueprint('admin', __name__)

from . import routes as routes, routes_operacional as routes_operacional  # noqa: E402, F401
