import dash_table
import dash_core_components as dcc
import dash_bootstrap_components as dbc
import dash_html_components as html
import flask
from .config import DEFAULT_DATASTACK, table_columns, hidden_columns
from ..common.dash_url_helper import create_component_kwargs, State

title = "Synapse Table Viewer"

header_text = html.H3(f"Connectivity Info:")


url_bar_and_content_div = html.Div(
    [dcc.Location(id="url", refresh=False), html.Div(id="page-layout")]
)


def page_layout(state: State = None):
    state = state or {}

    input_row = [
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.Div("Cell ID:"),
                    ],
                    width={"size": 2, "offset": 1},
                    align="end",
                ),
            ],
            justify="start",
        ),
        dbc.Row(
            [
                dbc.Col(
                    [
                        dcc.Input(
                            **create_component_kwargs(
                                state,
                                id_inner="anno-id",
                                value="",
                                type="text",
                                style={"font-size": "18px"},
                            )
                        ),
                    ],
                    width={"size": 1, "offset": 1},
                    align="start",
                ),
                dbc.Col(
                    [
                        dbc.Button(
                            id="submit-button",
                            children="Submit",
                            color="primary",
                            style={"font-size": "16px"},
                        ),
                    ],
                    width={"size": 1, "offset": 1},
                    align="start",
                ),
                dbc.Col(
                    [
                        dcc.RadioItems(
                            **create_component_kwargs(
                                state,
                                id_inner="live-query-toggle",
                                value="live",
                                options=[
                                    {"label": "Live", "value": "live"},
                                    {"label": "Static", "value": "static"},
                                ],
                                labelStyle={"font-size": "14px", "display": "block"},
                            ),
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
                    width={"size": 1, "offset": 0},
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
                            )
                        ),
                    ],
                    width={"size": 2, "offset": 1},
                    align="end",
                ),
            ],
            justify="start",
        ),
    ]

    message_row = dbc.Row(
        [
            dbc.Col(
                [html.Div(id="message-text", children="Please select a neuron id")],
                width={"size": 6, "offset": 1},
                align="start",
            )
        ]
    )

    data_table = html.Div(
        [
            dcc.Tabs(
                id="connectivity-tab",
                value="tab-pre",
                children=[
                    dcc.Tab(id="output-tab", label="Output", value="tab-pre"),
                    dcc.Tab(id="input-tab", label="Input", value="tab-post"),
                ],
            ),
            html.Div(
                dbc.Row(
                    [
                        dbc.Col(
                            dash_table.DataTable(
                                id="data-table",
                                columns=[{"name": i, "id": i} for i in table_columns],
                                data=[],
                                css=[
                                    {
                                        "selector": "table",
                                        "rule": "table-layout: fixed",
                                    }
                                ],
                                style_cell={
                                    "height": "auto",
                                    "width": "20%",
                                    "minWidth": "20%",
                                    "maxWidth": "20%",
                                    "whiteSpace": "normal",
                                },
                                sort_action="native",
                                sort_mode="multi",
                                filter_action="native",
                                row_selectable="multi",
                                page_current=0,
                                page_action="native",
                                page_size=50,
                            ),
                            width=10,
                        ),
                    ],
                    justify="center",
                )
            ),
        ]
    )

    # cell_links = dbc.Row(
    #     [
    #         dbc.Col(
    #             [
    #                 html.A(
    #                     "All Inputs",
    #                     id="input_ngl_link",
    #                     href="",
    #                     target="_blank",
    #                     style={"font-size": "20px"},
    #                 ),
    #             ],
    #             width={"size": 1, "offset": 1},
    #         ),
    #         dbc.Col(
    #             [
    #                 html.A(
    #                     "All Outputs",
    #                     id="output_ngl_link",
    #                     href="",
    #                     target="_blank",
    #                     style={"font-size": "20px"},
    #                 ),
    #             ],
    #             width={"size": 1, "offset": 0},
    #         ),
    #         dbc.Col(
    #             [
    #                 html.A(
    #                     "Whole Cell",
    #                     id="whole_cell_ngl_link",
    #                     href="",
    #                     target="_blank",
    #                     style={"font-size": "20px"},
    #                 )
    #             ]
    #         ),
    #     ],
    #     align="end",
    # )

    top_link = dbc.Row(
        [
            dbc.Col(
                [
                    html.A(
                        "Neuroglancer Link",
                        id="ngl_link",
                        href="",
                        target="_blank",
                        style={"font-size": "20px"},
                    ),
                ],
                width={"size": 2, "offset": 1},
            ),
            dbc.Col(
                dbc.Button(
                    id="reset-selection", children="Reset Selection", color="primary"
                ),
                width={"size": 2, "offset": 0},
            ),
        ],
        justify="left",
    )

    layout = html.Div(
        children=[
            html.Div(header_text),
            dbc.Container(
                input_row,
                fluid=True,
            ),
            html.Hr(),
            html.Div(message_row),
            # html.Hr(),
            # cell_links,
            html.Hr(),
            top_link,
            data_table,
            dcc.Store("target-table-json"),
            dcc.Store("source-table-json"),
            dcc.Store("client-info-json"),
            html.Div(
                dcc.Input(
                    **create_component_kwargs(
                        state,
                        id_inner="datastack",
                        value=DEFAULT_DATASTACK,
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
