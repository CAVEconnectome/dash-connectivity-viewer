import dash_table
import dash_core_components as dcc
import dash_bootstrap_components as dbc
import dash_html_components as html
import flask
from .app.config import DEFAULT_DATASTACK, table_columns
from .dash_url_helper import create_component_kwargs, State

title = "Connectivity Viewer"


def dropdown_options():
    # Should be made a callback
    options = [
        {
            "label": "All Soma Prediction",
            "value": "allen_soma_coarse_cell_class_model_v1",
        },
        {
            "label": "Column Census (slanted)",
            "value": "allen_v1_column_types_slanted",
        },
        {
            "label": "Column Census (straight)",
            "value": "allen_v1_column_types_v2",
        },
    ]
    return options


header_text = html.H3(f"Neuron Target Info:")
plot_header = html.H4(id="plot-response-text", children="")


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
                        html.Div("Root ID:"),
                    ],
                    width={"size": 1, "offset": 1},
                    align="end",
                ),
                dbc.Col(
                    [
                        html.Div("Cell Type Table: "),
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
                                state, id_inner="root_id", value="", type="text"
                            )
                        ),
                    ],
                    width={"size": 1, "offset": 1},
                    align="center",
                ),
                dbc.Col(
                    [
                        dcc.Dropdown(
                            **create_component_kwargs(
                                state,
                                id_inner="cell_type_table_dropdown",
                                options=dropdown_options(),
                                value="allen_soma_coarse_cell_class_model_v1",
                            )
                        ),
                    ],
                    width={"size": 2, "offset": 1},
                    align="center",
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
                    width={"size": 1, "offset": 0},
                    align="end",
                ),
                dbc.Col(
                    [
                        html.Div(
                            dcc.Loading(
                                id="main_loading",
                                children=html.Div(id="loading-spinner", children=""),
                                style={"transform": "scale(0.8)"},
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
    ]

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

    layout = html.Div(
        children=[
            html.Div(header_text),
            html.Div(input_row),
            html.Hr(),
            html.Div(plot_header),
            html.Div(id="plots", children=None),
            html.Hr(),
            top_link,
            data_table,
            dcc.Store("target-synapse-json"),
            dcc.Store("source-synapse-json"),
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
