import dash_table
import dash_core_components as dcc
import dash_bootstrap_components as dbc
import dash_html_components as html
import flask
from .config import DEFAULT_DATASTACK, table_columns
from ..common.dash_url_helper import create_component_kwargs, State

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
        {
            "label": "Thalamic Axons",
            "value": "allen_v1_column_thalamic",
        },
        {
            "label": "Layer 5 IT PyC Subtypes",
            "value": "allen_column_l5it_types",
        },
        {
            "label": "Basket Subtypes",
            "value": "allen_column_basket_molecular",
        },
    ]
    return options


def page_layout(state: State = None):
    state = state or {}

    header_text = dbc.Row(
        [
            dbc.Col(
                html.H3(f"Neuron Target Info:"),
                width={"size": 6, "offset": 1},
            ),
        ],
    )

    input_row = html.Div(
        [
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.Div("Cell ID:"),
                            dbc.Input(
                                **create_component_kwargs(
                                    state, id_inner="anno-id", value="", type="text"
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
                        width={"size": 1, "offset": 1},
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
                                id="main-loading-placeholder",
                                children="",
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
                            html.Div("Cell Type Table:"),
                            dcc.Dropdown(
                                **create_component_kwargs(
                                    state,
                                    id_inner="cell-type-table-dropdown",
                                    options=dropdown_options(),
                                    value="allen_soma_coarse_cell_class_model_v1",
                                    clearable=False,
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
    )

    message_row = dbc.Row(
        dbc.Col(
            dbc.Alert(
                id="message-text",
                children="Please select a root id and press Submit",
                color="info",
            ),
            width=10,
        ),
        justify="center",
    )

    top_link = dbc.Row(
        [
            dbc.Col(
                dbc.Spinner(
                    size="sm",
                    children=html.Div(id="link-loading"),
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

    input_tab = dbc.Row(
        [
            dbc.Col(
                dbc.Card(
                    [
                        dbc.CardBody(
                            [
                                html.H4("All Inputs", className="card-title"),
                                html.Div(
                                    children=[
                                        dbc.Button(
                                            "Generate Link",
                                            id="all-input-link-button",
                                            color="secondary",
                                            # className="mb-3",
                                            block=True,
                                        ),
                                    ]
                                ),
                                dbc.Spinner(
                                    html.Div(
                                        "", id="all-input-link", className="card-text"
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
                    [
                        dbc.CardBody(
                            [
                                html.H4("Cell-typed Inputs", className="card-title"),
                                html.Div(
                                    children=[
                                        dbc.Button(
                                            "Generate Link",
                                            id="cell-typed-input-link-button",
                                            color="secondary",
                                            block=True,
                                        ),
                                    ]
                                ),
                                dbc.Spinner(
                                    html.Div(
                                        "",
                                        id="cell-typed-input-link",
                                        className="card-text",
                                    ),
                                    size="sm",
                                ),
                            ]
                        )
                    ]
                ),
            ),
        ],
    )

    output_tab = dbc.Row(
        [
            dbc.Col(
                dbc.Card(
                    [
                        dbc.CardBody(
                            [
                                html.H4("All Outputs", className="card-title"),
                                html.Div(
                                    children=[
                                        dbc.Button(
                                            "Generate Link",
                                            id="all-output-link-button",
                                            color="secondary",
                                            # className="mb-3",
                                            block=True,
                                        ),
                                    ]
                                ),
                                dbc.Spinner(
                                    html.Div(
                                        "", id="all-output-link", className="card-text"
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
                    [
                        dbc.CardBody(
                            [
                                html.H4("Cell-typed Outputs", className="card-title"),
                                html.Div(
                                    children=[
                                        dbc.Button(
                                            "Generate Link",
                                            id="cell-typed-output-link-button",
                                            color="secondary",
                                            block=True,
                                        ),
                                    ]
                                ),
                                dbc.Spinner(
                                    html.Div(
                                        "",
                                        id="cell-typed-output-link",
                                        className="card-text",
                                    ),
                                    size="sm",
                                ),
                            ]
                        )
                    ]
                ),
            ),
        ],
    )
    cell_links = dbc.Row(
        dbc.Col(
            html.Div(
                [
                    dbc.Button(
                        html.H5("Whole Cell Links (click to toggle visibility)"),
                        id="collapse-button",
                        color="secondary",
                        block=True,
                    ),
                    dbc.Collapse(
                        dbc.Card(
                            [
                                dbc.Tabs(
                                    [
                                        dbc.Tab(input_tab, label="Input Links"),
                                        dbc.Tab(output_tab, label="Output Links"),
                                    ]
                                )
                            ]
                        ),
                        id="collapse-card",
                        is_open=False,
                    ),
                ]
            ),
            width=6,
        ),
        justify="center",
    )

    plot_data = dbc.Row(
        dbc.Col(
            html.Div(
                [
                    dbc.Button(
                        html.H5("Output Plots (click to toggle visibility)"),
                        id="plot-collapse-button",
                        color="secondary",
                        block=True,
                    ),
                    dbc.Collapse(
                        [
                            html.Br(),
                            html.Div("", id="plot-content"),
                        ],
                        id="plot-collapse",
                        is_open=True,
                    ),
                ]
            )
        )
    )

    layout = html.Div(
        children=[
            html.Div(header_text),
            dbc.Container(input_row, fluid=True),
            html.Br(),
            html.Div(message_row),
            html.Hr(),
            html.Div(plot_data),
            html.Hr(),
            dbc.Container(cell_links),
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


#################
# URL-formatter #
#################

url_bar_and_content_div = html.Div(
    [dcc.Location(id="url", refresh=False), html.Div(id="page-layout")]
)


def app_layout():
    # https://dash.plotly.com/urls "Dynamically Create a Layout for Multi-Page App Validation"
    if flask.has_request_context():  # for real
        return url_bar_and_content_div
    # validation only
    return html.Div([url_bar_and_content_div, *page_layout()])
