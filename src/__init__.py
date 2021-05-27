from dash import Dash
import dash_bootstrap_components as dbc
from .callbacks import register_callbacks
from .layout import layout, title

__version__ = "0.0.1"

external_stylesheets = [dbc.themes.FLATLY]


def create_app(config={}):
    app = Dash(__name__, external_stylesheets=external_stylesheets)
    app.title = title
    app.layout = layout
    register_callbacks(app, config)
    return app
