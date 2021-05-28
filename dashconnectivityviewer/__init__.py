from dash import Dash

import dash_bootstrap_components as dbc
from .callbacks import register_callbacks
from .layout import title, page_layout, app_layout
from .external_stylesheets import external_stylesheets
from .dash_url_helper import setup
import flask

__version__ = "0.0.1"



def create_app(dash_kwargs={}, config={}):
    if 'external_stylesheets' not in dash_kwargs:
        dash_kwargs['external_stylesheets']=external_stylesheets
    app = Dash(__name__, **dash_kwargs)
    app.title = title
    app.layout = app_layout
    setup(app, page_layout=page_layout)
    register_callbacks(app, config)
    return app
