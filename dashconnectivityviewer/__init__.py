from dash import Dash

import dash_bootstrap_components as dbc
from .callbacks import register_callbacks
from .layout import layout, title
from .external_stylesheets import external_stylesheets

__version__ = "0.0.1"



def create_app(config={}):
    app = Dash(__name__, external_stylesheets=external_stylesheets)
    app.title = title
    app.layout = layout
    register_callbacks(app, config)
    return app
