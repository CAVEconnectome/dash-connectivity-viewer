import dash_table
import dash_core_components as dcc
import dash_bootstrap_components as dbc
import dash_html_components as html
import flask
from .config import DEFAULT_DATASTACK, table_columns
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
                                    "width": "12%",
                                    "minWidth": "10%",
                                    "maxWidth": "15%",
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
                # width={"size": 2, "offset": 0},
            ),
            dbc.Col(
                dbc.Button(
                    id="reset-selection",
                    children="Reset Selection",
                    color="warning",
                    size="sm",
                ),
                # width={"size": 2, "offset": 0},
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
            dbc.Container(message_row),
            # html.Hr(),
            dbc.Container(cell_links),
            html.Hr(),
            dbc.Container(top_link, fluid=True),
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
