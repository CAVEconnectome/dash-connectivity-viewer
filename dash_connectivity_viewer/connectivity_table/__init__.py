from dash import Dash

from .callbacks import register_callbacks
from .layout import title, page_layout, app_layout
from .external_stylesheets import external_stylesheets
from ..common.dash_url_helper import setup
import flask
from functools import partial

__version__ = "0.0.1"


def create_app(name=__name__, config={}, **kwargs):
    if "external_stylesheets" not in kwargs:
        kwargs["external_stylesheets"] = external_stylesheets
    app = Dash(name, **kwargs)
    app.title = title
    config_layout = partial(app_layout, config=config)
    config_pl = partial(page_layout, config=config)
    app.layout = config_layout
    setup(app, page_layout=config_pl)
    register_callbacks(app, config)
    return app
