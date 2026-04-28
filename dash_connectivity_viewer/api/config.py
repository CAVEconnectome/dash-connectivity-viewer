import os

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix


_DEFAULTS = {
    "GLOBAL_SERVER_ADDRESS": "https://global.daf-apis.com",
    "DEFAULT_DATASTACK": None,
    "CORS_ORIGINS": ["http://localhost:5173"],
    "SPELUNKER_URL": "https://spelunker.cave-explorer.org",
    "CACHE_QUERY_TTL_SECONDS": 15 * 60,
    "CACHE_TABLE_META_TTL_SECONDS": 60 * 60,
    "CACHE_INFO_TTL_SECONDS": 24 * 60 * 60,
    "CACHE_DECORATION_SOFT_TTL_SECONDS": 4 * 60 * 60,
    "CACHE_DECORATION_HARD_TTL_SECONDS": 24 * 60 * 60,
    "CACHE_DECORATION_LIVE_SOFT_TTL_SECONDS": 5 * 60,
    "CACHE_DECORATION_LIVE_HARD_TTL_SECONDS": 30 * 60,
    "DECORATION_REVALIDATION_WORKERS": 4,
    "LINK_TEMPLATE_DIR": None,
    "PLOT_TEMPLATE_DIR": None,
    "DATASTACK_CONFIG_DIR": None,
}


def configure_app(app: Flask, overrides: dict | None = None) -> None:
    app.config.update(_DEFAULTS)
    for key in _DEFAULTS:
        env_value = os.environ.get(f"DCV_{key}")
        if env_value is not None:
            app.config[key] = _coerce(_DEFAULTS[key], env_value)
    if overrides:
        app.config.update(overrides)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)


def _coerce(default, raw: str):
    if isinstance(default, bool):
        return raw.lower() in {"1", "true", "yes", "on"}
    if isinstance(default, int):
        return int(raw)
    if isinstance(default, list):
        return [item.strip() for item in raw.split(",") if item.strip()]
    return raw
