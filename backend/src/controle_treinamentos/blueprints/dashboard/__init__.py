from flask import Blueprint

dashboard_bp = Blueprint('dashboard', __name__)

from . import routes as routes  # noqa: E402, F401
from ...api.http.dashboard import routes as api_routes  # noqa: E402, F401
