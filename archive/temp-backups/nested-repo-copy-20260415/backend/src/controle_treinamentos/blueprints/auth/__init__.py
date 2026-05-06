from flask import Blueprint

auth_bp = Blueprint('auth', __name__)

from . import routes as routes  # noqa: E402, F401
