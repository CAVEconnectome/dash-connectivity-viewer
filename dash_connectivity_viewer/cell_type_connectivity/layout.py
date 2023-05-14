from dash import dash_table
from dash import dcc
import dash_bootstrap_components as dbc
from dash import html
import flask
from ..common.dash_url_helper import create_component_kwargs, State

title = "Connectivity Viewer"


def make_input_row(state):
    return html.Div(
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
                                        {
                                            "label": "Live Query",
                                            "value": 1,
                                        },
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
                            html.Div("Table:"),
                            dcc.Dropdown(
                                **create_component_kwargs(
                                    state,
                                    id_inner="cell-type-table-dropdown",
                                    options=[],
                                    value="",
                                    clearable=True,
                                )
                            ),
                        ],
                        width={"size": 3, "offset": 1},
                        align="end",
                    ),
                ],
                justify="start",
            ),
        ]
    )


def make_message_row(state):
    return dbc.Row(
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


def make_table_link_row(state):
    return dbc.Row(
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


def make_data_table_content():
    return html.Div(
        dbc.Row(
            [
                dbc.Col(
                    dash_table.DataTable(
                        id="data-table",
                        columns=[{"name": i, "id": i} for i in [""]],
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
                        page_size=30,
                        export_format="csv",
                        export_headers="names",
                    ),
                    width=10,
                ),
            ],
            justify="center",
        )
    )

def make_input_link_tab():
    return [
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
                                    className="d-grid gap-2 col-6 mx-auto",
                                    style={"align-items":"center", "justify-content":"center"}
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
        dbc.Col(
            dbc.Card(
                [
                    dbc.CardBody(
                        [
                            html.H4("Grouped Inputs", className="card-title"),
                            html.Div(
                                children=[
                                    dbc.Button(
                                        "Generate Link",
                                        id="cell-typed-input-link-button",
                                        color="secondary",
                                        className="d-grid gap-2 col-6 mx-auto",
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
    ]

def make_output_link_tab():
    return [
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
                                    className="d-grid gap-2 col-6 mx-auto",
                                    style={"align-items":"center", "justify-content":"center"},
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
            ],
            style={"width": "18rem"},
        ),
        dbc.Card(
            [
                dbc.CardBody(
                    [
                        html.H4("Grouped Outputs", className="card-title"),
                        html.Div(
                            children=[
                                dbc.Button(
                                    "Generate Link",
                                    id="cell-typed-output-link-button",
                                    color="secondary",
                                    className="d-grid gap-2 col-6 mx-auto",
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
    ]

def page_layout(state: State = None):
    state = state or {}

    header_text = dbc.Row(
        [
            dbc.Col(
                html.Div(id='header-bar'),
                width={"size": 12},
            ),
        ],
    )
    input_row = make_input_row(state)
    message_row = make_message_row(state)
    top_link = make_table_link_row(state)
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
            make_data_table_content(),
        ]
    )


    input_tab = make_input_link_tab()
    output_tab = make_output_link_tab()

    cell_links = [
        dbc.Row(
            [
                dbc.Col(
                    dbc.CardGroup(
                        input_tab + output_tab,
                    ),
                    width={"size": 10, "offset": 1},
                ),
            ]
        ),
        dbc.Row(
            dbc.Col(
                dbc.Card(
                    dbc.CardBody(
                        [
                            dbc.Row(
                                [
                                    dbc.Col(
                                        [
                                            html.H5(
                                                "Annotation grouping:",
                                                className="card-title",
                                            ),
                                            dbc.Checklist(
                                                options=[
                                                    {
                                                        "label": "Include No Type",
                                                        "value": 1,
                                                    },
                                                ],
                                                value=[],
                                                switch=True,
                                                style={"font-size": "16px"},
                                                id='no-type-annotation',
                                            ),
                                        ],
                                        width={"size": 2},
                                    ),
                                    dbc.Col(
                                        dcc.Dropdown(
                                            options={},
                                            value="",
                                            id="group-by",
                                            searchable=True,
                                        ),
                                        width={'size': 8},
                                    ),
                                ],
                            ),
                        ]
                    )
                ),
                width={"size": 10, "offset": 1},
            ),
        ),
    ]

    plot_data = [
        dbc.Row(
            [
                dbc.Col(
                    dbc.CardGroup(
                        [
                            dbc.Card(
                                dbc.CardBody(
                                    html.Div(
                                        "",
                                        id="violin-plot",
                                        className="text-center v-100 h-100",
                                    ),
                                )
                            ),
                            dbc.Card(
                                dbc.CardBody(
                                    html.Div("", id="scatter-plot", className="text-center h-100 v-100"),
                                )
                            ),
                            dbc.Card(
                                dbc.CardBody(
                                    html.Div("", id="bar-plot", className="text-center v-100 h-100"),
                                )
                            ),
                        ],
                    className="h-100",
                    ),
                )
            ],
        ),
        dbc.Row(
            dbc.Col(
                dbc.Card(
                    dbc.CardBody(
                        [
                            dbc.Row(
                                [
                                    dbc.Col(
                                        [
                                            html.Div(
                                                "Color by value:",
                                                style={'align-content': 'right'},
                                            ),
                                        ],
                                        style={'align-content': 'right'},
                                        width={"size": 1, 'offset':1},
                                    ),
                                    dbc.Col(
                                        dcc.Dropdown(
                                            options={"cell_type": "cell_type"},
                                            value="cell_type",
                                            id="plot-color-value",
                                        ),  
                                        style={"align-content": "left"},
                                        width={'size': 9},
                                    ),
                                ],
                            ),
                        ]
                    )
                ),
                # width={"size": 12},
            ),
        ),
    ]

    main_tab = dbc.Row(
        [
            dbc.Col(
                dbc.Tabs(
                    [
                        dbc.Tab(html.Div(), label="Table Only"),
                        dbc.Tab(plot_data, label="Plots"),
                        dbc.Tab(cell_links, label="Neuroglancer Links")
                    ],
                ),
                width={'size': 10, 'offset': 1},
            )
        ]
    )

    layout = html.Div(
        children=[
            header_text,
            dbc.Container(input_row, fluid=True),
            html.Br(),
            html.Div(message_row),
            html.Hr(),
            html.Div(main_tab),
            # html.Div(plot_data),
            # html.Hr(),
            # dbc.Container(cell_links),
            html.Hr(),
            top_link,
            data_table,
            dcc.Store("target-table-json"),
            dcc.Store("source-table-json"),
            dcc.Store("client-info-json"),
            dcc.Store("synapse-table-resolution-json"),
            dcc.Store("value-columns"),
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
