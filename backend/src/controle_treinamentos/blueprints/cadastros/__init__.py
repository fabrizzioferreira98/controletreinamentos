from flask import Blueprint

cadastros_bp = Blueprint('cadastros', __name__)

from ...api.http.cadastros import routes as api_routes  # noqa: E402, F401
from ...api.http.cadastros import routes_training_program as routes_training_program  # noqa: E402, F401
from . import routes as routes, routes_catalogos as routes_catalogos, routes_file as routes_file, routes_treinamentos as routes_treinamentos, routes_tripulante_views as routes_tripulante_views  # noqa: E402, F401
