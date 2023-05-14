from typing import DefaultDict
from dash import html
from dash import dash_table
from dash import dcc
import dash_bootstrap_components as dbc
import flask

from ..common.dash_url_helper import create_component_kwargs, State

#####################
# title must be set #
#####################

# The title gives the title of the app in the browser tab
title = "Annotation Table Viewer"

###################################################################
# page_layout must be defined to take a state and return a layout #
###################################################################


def page_layout(state: State = {}):
    """This function returns the layout object for the dash app.
    The state parameter allows for URL-encoded parameter values.

    Parameters
    ----------
    state : State, optional
        URL state, a series of dicts that can provide parameter values, by default None

    Returns
    -------
    layout : list
        List of layout components for the dash app.
    """
    header_row = dbc.Row(
        [
            dbc.Col(
                html.Div(id='header-bar'),
                width={"size": 12},
            ),
        ],
    )

    cell_type_query = html.Div(
        children=[
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.Div("Annotation Table:"),
                            dcc.Dropdown(
                                **create_component_kwargs(
                                    state,
                                    id_inner="cell-type-table-menu",
                                    placeholder="Select a Table",
                                    options=[],
                                    value=None,
                                ),
                            ),
                        ],
                        width={"size": 3, "offset": 1},
                        align="end",
                    ),
                    dbc.Col(
                        [
                            dbc.Checklist(
                                **create_component_kwargs(
                                    state,
                                    id_inner="live-query-toggle",
                                    options=[
                                        {"label": "Live Query", "value": 1},
                                    ],
                                    value=[
                                        1,
                                    ],
                                    switch=True,
                                    style={
                                        "bottom-margin": "10px",
                                        "font-size": "16px",
                                    },
                                )
                            ),
                        ],
                        width={"size": 1, "offset": 0},
                        align="center",
                    ),
                    dbc.Col(
                        dbc.Button(
                            children="Submit",
                            id="submit-button",
                            color="primary",
                            style={"font-size": "18px"},
                        ),
                        width={"size": 1},
                        align="center",
                    ),
                    dbc.Col(
                        dcc.Loading(
                            id="main-loading",
                            children=html.Div(
                                id="main-loading-placeholder", children=""
                            ),
                            type="default",
                            style={"transform": "scale(0.8)"},
                        ),
                        align="end",
                    ),
                ],
                justify="start",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.Div("Cell IDs (optional):"),
                            dbc.Input(
                                **create_component_kwargs(
                                    state,
                                    id_inner="anno-id",
                                    value="",
                                    type="text",
                                ),
                            ),
                        ],
                        width={"size": 2, "offset": 1},
                        align="end",
                    ),
                    dbc.Col(
                        [
                            dcc.Dropdown(
                                **create_component_kwargs(
                                    state,
                                    id_inner="id-type",
                                    options=[
                                        {
                                            "label": "Root ID",
                                            "value": "root_id",
                                        },
                                        {
                                            "label": "Nucleus ID",
                                            "value": "nucleus_id",
                                        },
                                        {
                                            "label": "Annotation ID",
                                            "value": "anno_id",
                                        },
                                    ],
                                    value="root_id",
                                    style={
                                        "margin-left": "12px",
                                        "font-size": "12px",
                                    },
                                    clearable=False,
                                )
                            ),
                        ],
                        width={"size": 1},
                        align="end",
                    ),
                    dbc.Col(
                        [html.Div(children="", id="report-text")],
                    ),
                ],
                justify="start",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            
                            html.Div("Value Search (optional):"),
                            dbc.Input(
                                **create_component_kwargs(
                                    state,
                                    value="",
                                    id_inner="cell-type",
                                    type="text",
                                ),
                            ),
                        ],
                        width={"size": 2, "offset": 1},
                    ),
                    dbc.Col(
                        [
                            html.Div("Search Column:"),
                            dcc.Dropdown(
                                **create_component_kwargs(
                                    state,
                                    id_inner="value-column-search",
                                    options=[],
                                    value="",
                                    style={
                                        "margin-left": "12px",
                                        "font-size": "12px",
                                    },
                                    clearable=False,
                                )
                            ),
                        ],
                        width={"size": 1},
                        align="end",
                    )
                ],
                justify="state",
            ),
            html.Hr(),
        ]
    )

    message_row = dbc.Alert(
        id="message-text",
        children="Please select a cell type table and press Submit",
        color="info",
    )

    data_table = html.Div(
        dbc.Row(
            [
                dbc.Col(
                    dash_table.DataTable(
                        id="data-table",
                        columns=[{"id": "", "name": ""}],
                        data=[],
                        css=[
                            {
                                "selector": "table",
                                "rule": "table-layout: auto",
                            }
                        ],
                        style_cell={
                            "height": "auto",
                            "width": "12%",
                            "minWidth": "10%",
                            "maxWidth": "15%",
                            "whiteSpace": "normal",
                            "font-size": "11px",
                        },
                        style_header={"font-size": "12px", "fontWeight": "bold"},
                        sort_action="native",
                        sort_mode="multi",
                        filter_action="native",
                        row_selectable="multi",
                        page_current=0,
                        page_action="native",
                        page_size=50,
                        export_format="csv",
                        export_headers="names",
                    ),
                    width=10,
                )
            ],
            justify="center",
        )
    )

    ngl_link = dbc.Row(
        [
            dbc.Col(
                dbc.Spinner(
                    size="sm", children=html.Div(id="link-loading-placeholder")
                ),
                width=1,
                align="center",
            ),
            dbc.Col(
                dbc.Button(
                    children="Table View Neuroglancer Link",
                    id="ngl-link",
                    href="",
                    target="_blank",
                    style={"font-size": "16px"},
                    color="primary",
                    external_link=True,
                    disabled=False,
                ),
                width=3,
                align="start",
            ),
            dbc.Col(
                dbc.Button(
                    id="reset-selection",
                    children="Reset Selection",
                    color="warning",
                    size="sm",
                ),
                width=1,
            ),
            dbc.Col(
                html.A(
                    "Instructions for filtering the table",
                    href="https://dash.plotly.com/datatable/filtering",
                    style={"font-size": "15px"},
                    target="_blank",
                ),
                align="center",
                width={"size": 2, "offset": 3},
            ),
        ],
        justify="start",
    )

    whole_column_link = dbc.Row(
        [
            dbc.Col(
                dbc.Card(
                    [
                        dbc.CardBody(
                            [
                                html.H4("Whole Table Link", className="card-title"),
                                html.Div(
                                    children=[
                                        dbc.Button(
                                            "Generate Link",
                                            id="whole-table-link-button",
                                            color="secondary",
                                            className="d-grid gap-2 col-6 mx-auto",
                                        ),
                                    ]
                                ),
                                dbc.Spinner(
                                    dbc.Row(
                                        html.Div(
                                            "", id="whole-table-link", className="card-text"
                                        ),
                                        justify='center',
                                        align='center',
                                    ),
                                    size="sm",
                                ),
                            ]
                        )
                    ]
                ),
            ),
            dbc.Col(
                dbc.Card(
                    dbc.CardBody(
                        [
                            html.H4('Annotation Grouping', className='card-title'),
                            dbc.Checklist(
                                options=[
                                    {"label": "Group annotations", "value": 1},
                                ],
                                value=[],
                                id="do-group",
                                switch=True,
                            ),
                            dcc.Dropdown(
                                options={},
                                value='cell_type',
                                id='group-by',
                                searchable=False,
                            ),
                        ]
                    )
                )
            )
        ],
    )

    datastack_comp = (
        dcc.Input(
            **create_component_kwargs(
                state,
                id_inner="datastack",
                value="",
                type="text",
            ),
        ),
    )

    title_row = dbc.Row(
        [
            dbc.Col(
                html.H3("Table Viewer"),
                width={"size": 6, "offset": 1},
            ),
        ],
    )

    layout = html.Div(
        children=[
            header_row,
            dbc.Container(cell_type_query, fluid=True),
            dbc.Container(message_row),
            dbc.Container(whole_column_link),
            html.Hr(),
            html.Div(ngl_link),
            html.Div(data_table),
            html.Div(datastack_comp, style={"display": "none"}),
            dcc.Store(id="client-info-json"),
            dcc.Store(id="table-resolution-json"),
            dcc.Store(id='data-resolution-json'),
            dcc.Store(id='pt-column'),
            dcc.Store(id='value-columns'),
        ]
    )
    return layout


######################################################
# Leave this rest alone for making the template work #
######################################################

url_bar_and_content_div = html.Div(
    [dcc.Location(id="url", refresh=False), html.Div(id="page-layout")]
)


def app_layout():
    # https://dash.plotly.com/urls "Dynamically Create a Layout for Multi-Page App Validation"
    if flask.has_request_context():  # for real
        return url_bar_and_content_div
    # validation only
    return html.Div([url_bar_and_content_div, *page_layout()])
