from dash import dash_table
from dash import dcc
from dash import html
import dash_bootstrap_components as dbc
import flask
from ..common.dash_url_helper import create_component_kwargs, State

title = "Synapse Table Viewer"

url_bar_and_content_div = html.Div(
    [dcc.Location(id="url", refresh=False), html.Div(id="page-layout")]
)


def page_layout(state: State = None):
    state = state or {}
    
    header_row = dbc.Row(
        [
            dbc.Col(
                html.Div(id='header-bar'),
                width={"size": 12},
            ),
        ],
    )


    input_row = [
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.Div("Cell ID:"),
                    ],
                    align="end",
                ),
            ],
            justify="start",
        ),
        dbc.Row(
            [
                dbc.Col(
                    [
                        dbc.Input(
                            **create_component_kwargs(
                                state,
                                id_inner="anno-id",
                                value="",
                                type="text",
                                # style={"font-size": "18px"},
                            )
                        ),
                    ],
                    align="start",
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
                            )
                        ),
                    ],
                    align="center",
                ),
                dbc.Col(
                    [
                        dbc.Button(
                            id="submit-button",
                            children="Submit",
                            color="primary",
                            style={"font-size": "16px", "align": "left"},
                        ),
                    ],
                    align="start",
                ),
                dbc.Col(
                    [
                        html.Div(
                            dcc.Loading(
                                id="main-loading",
                                children=html.Div(id="loading-spinner", children=""),
                                style={"transform": "scale(1)"},
                                type="default",
                            )
                        )
                    ],
                    align="center",
                ),
            ],
            justify="start",
        ),
        dbc.Row(
            [
                dbc.Col(
                    [
                        dcc.Dropdown(
                            **create_component_kwargs(
                                state,
                                id_inner="cell-id-type",
                                options=[
                                    {"label": "Root ID", "value": "root_id"},
                                    {"label": "Nucleus ID", "value": "nucleus_id"},
                                ],
                                value="root_id",
                                clearable=False,
                            )
                        ),
                    ],
                    width=2,
                    align="end",
                ),
            ],
            justify="start",
        ),
    ]

    message_row = dbc.Alert(
        id="message-text",
        children="Please select a neuron id",
        color="info",
    )

    data_table = html.Div(
        [
            dcc.Tabs(
                id="connectivity-tab",
                value="tab-pre",
                children=[
                    dcc.Tab(id="input-tab", label="Input", value="tab-post"),
                    dcc.Tab(id="output-tab", label="Output", value="tab-pre"),
                ],
            ),
            html.Div(
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
                                        "rule": "table-layout: fixed",
                                    }
                                ],
                                style_cell={
                                    "height": "auto",
                                    "whiteSpace": "normal",
                                    "font-size": "11px",
                                },
                                style_header={
                                    "font-size": "12px",
                                    "fontWeight": "bold",
                                },
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
                        ),
                    ],
                    justify="center",
                )
            ),
        ]
    )

    cell_links = html.Div(
        [
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Button(
                            "Generate All Input Link",
                            id="all-input-link-button",
                            color="secondary",
                        ),
                    ),
                    dbc.Col(
                        dbc.Button(
                            "Generate All Output Link",
                            id="all-output-link-button",
                            color="secondary",
                        )
                    ),
                ]
            ),
            dbc.Row(
                [
                    dbc.Col(
                        html.Div("", id="all-input-link"),
                    ),
                    dbc.Col(html.Div("", id="all-output-link")),
                ]
            ),
        ]
    )

    top_link = dbc.Row(
        [
            dbc.Col(
                dbc.Spinner(size="sm", children=html.Div(id="link-loading")),
                width=1,
                align="center",
            ),
            dbc.Col(
                [
                    dbc.Button(
                        children="Neuroglancer Link",
                        color="primary",
                        external_link=True,
                        target="_blank",
                        id="ngl_link",
                        href="",
                        disabled=False,
                    ),
                ],
            ),
            dbc.Col(
                dbc.Button(
                    id="reset-selection",
                    children="Reset Selection",
                    color="warning",
                    size="sm",
                ),
            ),
        ],
        justify="left",
    )

    layout = html.Div(
        children=[
            header_row,
            dbc.Container(
                input_row,
                fluid=True,
            ),
            html.Hr(),
            dbc.Container(message_row),
            # html.Hr(),
            dbc.Container(cell_links),
            html.Hr(),
            dbc.Container(top_link, fluid=True),
            data_table,
            dcc.Store("target-table-json"),
            dcc.Store("source-table-json"),
            dcc.Store("client-info-json"),
            dcc.Store("synapse-table-resolution-json"),
            html.Div(
                dcc.Input(
                    **create_component_kwargs(
                        state,
                        id_inner="datastack",
                        value="",
                    ),
                ),
                style={"display": "none"},
            ),
        ]
    )

    return layout


def app_layout():
    # https://dash.plotly.com/urls "Dynamically Create a Layout for Multi-Page App Validation"
    if flask.has_request_context():  # for real
        return url_bar_and_content_div
    # validation only
    return html.Div([url_bar_and_content_div, *page_layout()])
