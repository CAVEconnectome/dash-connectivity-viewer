from flask import Flask
from flask_cors import CORS

from .config import configure_app
from .errors import register_error_handlers
from .endpoints import api_bp
from .json_provider import NumpyJSONProvider
from .services.decoration import init_decoration_service


def create_app(config_overrides: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.json = NumpyJSONProvider(app)
    configure_app(app, overrides=config_overrides)
    CORS(
        app,
        resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
        supports_credentials=True,
    )
    register_error_handlers(app)
    init_decoration_service(app)
    app.register_blueprint(api_bp, url_prefix="/api/v1")
    return app
