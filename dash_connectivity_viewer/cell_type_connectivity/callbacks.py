import datetime
from caveclient import CAVEclient
from dash_bootstrap_components._components.CardBody import CardBody
from dash_bootstrap_components._components.CardHeader import CardHeader
from dash import dcc
import dash_bootstrap_components as dbc
from dash import html
from dash.dependencies import Input, Output, State
from dash import callback_context

A = html.A
from functools import partial

from ..common.link_utilities import (
    generate_statebuilder,
    generate_statebuilder_pre,
    generate_statebuilder_post,
    generate_statebuider_syn_grouped,
    generate_statebuilder_syn_cell_types,
    EMPTY_INFO_CACHE,
    MAX_URL_LENGTH,
    make_url_robust,
)
from ..common.dash_url_helper import _COMPONENT_ID_TYPE
from ..common.lookup_utilities import (
    get_type_tables,
    make_client,
    get_root_id_from_nuc_id,
)
from ..common.dataframe_utilities import stringify_root_ids

from .config import *
from .neuron_data_cortex import NeuronDataCortex as NeuronData
from .cortex_panels import *

try:
    from loguru import logger
    import time
except:
    logger = None

InputDatastack = Input({"id_inner": "datastack", "type": _COMPONENT_ID_TYPE}, "value")
StateRootID = State({"id_inner": "anno-id", "type": _COMPONENT_ID_TYPE}, "value")
StateCellTypeTable = State(
    {"id_inner": "cell-type-table-dropdown", "type": _COMPONENT_ID_TYPE},
    "value",
)
OutputCellTypeOptions = Output(
    {"id_inner": "cell-type-table-dropdown", "type": _COMPONENT_ID_TYPE},
    "options",
)
InputCellTypeOptions = Input(
    {"id_inner": "cell-type-table-dropdown", "type": _COMPONENT_ID_TYPE},
    "options",
)

StateAnnoType = State({"id_inner": "id-type", "type": _COMPONENT_ID_TYPE}, "value")
StateLiveQuery = State(
    {"id_inner": "live-query-toggle", "type": _COMPONENT_ID_TYPE}, "value"
)


def cell_type_column_lookup(ct, schema_lookup, client):
    if ct is None:
        return {}
    schema = client.materialize.get_table_metadata(ct)["schema"]
    return schema_lookup.get(schema)


def allowed_action_trigger(ctx, allowed_buttons):
    if not ctx.triggered:
        return False
    trigger_src = ctx.triggered[0]["prop_id"].split(".")[0]
    return trigger_src in allowed_buttons


def generic_syn_link_generation(
    sb_function,
    rows,
    info_cache,
    datastack,
    config,
    link_text,
    item_name="synapses",
):
    if rows is None or len(rows) == 0:
        return html.Div(f"No {item_name} to show")
    else:
        syn_df = pd.DataFrame(rows)
        sb = sb_function(info_cache)
    try:
        url = make_url_robust(
            syn_df.sort_values(by=num_syn_col, ascending=False),
            sb,
            datastack,
            config,
        )
    except Exception as e:
        return html.Div(str(e))

    return html.A(link_text, href=url, target="_blank", style={"font-size": "20px"})


def make_plots(ndat):
    if ndat is None:
        return html.Div("")
    violin = violin_fig(ndat, vis_config, height=350)
    scatter = scatter_fig(ndat, vis_config, width=450, height=350)
    if ndat.valence_map is not None:
        bars = split_bar_fig(ndat, vis_config, height=350)
    else:
        bars = single_bar_fig(ndat, vis_config, height=350)

    plot_content = dbc.Row(
        [
            dbc.Col(
                html.Div(
                    [
                        html.H5("Input/Output Depth", style={"text-align": "center"}),
                        dcc.Graph(
                            figure=violin, style={"width": "100%", "height": "100%"}
                        ),
                    ],
                    style={"align-content": "right"},
                )
            ),
            dbc.Col(
                [
                    html.H5(
                        "Synapse/Target Synapse Depth", style={"text-align": "center"}
                    ),
                    dcc.Graph(
                        figure=scatter, style={"text-align": "center", "width": "100%"}
                    ),
                ]
            ),
            dbc.Col(
                [
                    html.H5(
                        "Target Synapse by Cell Type", style={"text-align": "center"}
                    ),
                    dcc.Graph(figure=bars, style={"text-align": "center"}),
                ]
            ),
        ],
    )

    return html.Div(plot_content)


def register_callbacks(app, config):
    valence_map_table = config.get("valence_map_table", {})

    @app.callback(
        Output("data-table", "selected_rows"),
        Input("reset-selection", "n_clicks"),
        Input("connectivity-tab", "value"),
    )
    def reset_selection(n_clicks, tab_value):
        return []

    @app.callback(
        OutputCellTypeOptions,
        InputDatastack,
    )
    def cell_type_dropdown(datastack):
        return get_type_tables(allowed_cell_type_schema, datastack, config)

    @app.callback(
        Output("message-text", "children"),
        Output("message-text", "color"),
        Output("main-loading-placeholder", "children"),
        Output("target-table-json", "data"),
        Output("source-table-json", "data"),
        Output("output-tab", "label"),
        Output("input-tab", "label"),
        Output("reset-selection", "n_clicks"),
        Output("client-info-json", "data"),
        Output("plot-content", "children"),
        Output("synapse-table-resolution-json", "data"),
        Input("submit-button", "n_clicks"),
        InputDatastack,
        StateRootID,
        StateAnnoType,
        StateCellTypeTable,
        StateLiveQuery,
    )
    def update_data(_1, datastack_name, anno_id, id_type, ct_table_value, query_toggle):
        if logger is not None:
            t0 = time.time()

        try:
            client = make_client(datastack_name, config)
            info_cache = client.info.info_cache[datastack_name]
            info_cache["global_server"] = client.server_address
        except Exception as e:
            return (
                html.Div(str(e)),
                "danger",
                "",
                [],
                [],
                "Output",
                "Input",
                1,
                EMPTY_INFO_CACHE,
                make_plots(None),
                None,
            )

        if len(query_toggle) == 1 and not config.get("DISALLOW_LIVE_QUERY", False):
            live_query = True
        else:
            live_query = False

        if live_query:
            timestamp = datetime.datetime.now()
        else:
            timestamp = client.materialize.get_timestamp()
            info_cache["ngl_timestamp"] = timestamp.timestamp()

        if anno_id is None or len(anno_id) == 0 or len(ct_table_value) == 0:
            return (
                html.Div(
                    "Please select a cell id and cell type table and press Submit"
                ),
                "info",
                "",
                [],
                [],
                "Output",
                "Input",
                1,
                EMPTY_INFO_CACHE,
                make_plots(None),
                None,
            )
        else:
            if id_type == "root_id":
                object_id = int(anno_id)
                object_id_type = "root"
            elif id_type == "nucleus_id":
                object_id = int(anno_id)
                object_id_type = "nucleus"
            else:
                raise ValueError('id_type must be either "root_id" or "nucleus_id"')

        nrn_data = NeuronData(
            object_id,
            client=client,
            cell_type_table=ct_table_value,
            timestamp=timestamp,
            synapse_table=SYNAPSE_TABLE,
            soma_table=NUCLEUS_TABLE,
            n_threads=2,
            synapse_position_point=syn_pt_position_col,
            cell_position_point=cell_pt_position_col,
            soma_id_column=NUCLEUS_ID_COLUMN,
            id_type=object_id_type,
            soma_table_query=soma_table_query,
            valence_map=valence_map_table.get(ct_table_value),
            soma_depth_column=soma_depth_column,
            is_inhibitory_column=is_inhibitory_column,
            synapse_depth_column=synapse_depth_column,
            cell_type_column=cell_type_column_lookup(
                ct_table_value, config.get("cell_type_column_schema_lookup", {}), client
            ),
        )

        root_id = nrn_data.root_id
        info_cache["root_id"] = str(root_id)

        pre_targ_df = nrn_data.partners_out_plus()
        pre_targ_df = stringify_root_ids(pre_targ_df, stringify_cols=[root_id_col])

        post_targ_df = nrn_data.partners_in_plus()
        post_targ_df = stringify_root_ids(post_targ_df, stringify_cols=[root_id_col])

        n_syn_pre = pre_targ_df[num_syn_col].sum()
        n_syn_post = post_targ_df[num_syn_col].sum()
        syn_resolution = nrn_data.synapse_data_resolution

        if logger is not None:
            logger.info(
                f"Data update for {root_id} | time:{time.time() - t0:.2f} s, syn_in: {len(pre_targ_df)} , syn_out: {len(post_targ_df)}"
            )

        if live_query:
            message_text = f"Current connectivity for root id {root_id}"
        else:
            message_text = f"Connectivity for root id {root_id} materialized on {timestamp:%m/%d/%Y} (v{client.materialize.version})"

        plts = make_plots(nrn_data)

        del nrn_data
        del client

        return (
            html.Div(message_text),
            "success",
            "",
            pre_targ_df.to_dict("records"),
            post_targ_df.to_dict("records"),
            f"Output (n = {n_syn_pre})",
            f"Input (n = {n_syn_post})",
            1,
            info_cache,
            plts,
            syn_resolution,
        )

    @app.callback(
        Output("data-table", "data"),
        Input("connectivity-tab", "value"),
        Input("target-table-json", "data"),
        Input("source-table-json", "data"),
    )
    def update_table(
        tab_value,
        pre_data,
        post_data,
    ):
        if tab_value == "tab-pre":
            return pre_data
        elif tab_value == "tab-post":
            return post_data
        else:
            return []

    @app.callback(
        Output("ngl-link", "href"),
        Output("ngl-link", "children"),
        Output("ngl-link", "disabled"),
        Output("link-loading", "children"),
        Input("connectivity-tab", "value"),
        Input("data-table", "derived_virtual_data"),
        Input("data-table", "derived_virtual_selected_rows"),
        Input("client-info-json", "data"),
        Input("synapse-table-resolution-json", "data"),
    )
    def update_link(
        tab_value,
        rows,
        selected_rows,
        info_cache,
        synapse_data_resolution,
    ):
        large_state_text = (
            "Table Too Large - Please Filter or Use Whole Cell Neuroglancer Links"
        )
        small_state_text = "Table View Neuroglancer Link"

        if rows is None or len(rows) == 0:
            rows = {}
            sb = generate_statebuilder(info_cache)
            return sb.render_state(None, return_as="url"), small_state_text, False, ""
        else:
            syn_df = pd.DataFrame(rows)
            if len(selected_rows) == 0:
                if tab_value == "tab-pre":
                    sb = generate_statebuilder_pre(
                        info_cache, data_resolution=synapse_data_resolution
                    )
                elif tab_value == "tab-post":
                    sb = generate_statebuilder_post(
                        info_cache, data_resolution=synapse_data_resolution
                    )
                else:
                    raise ValueError('tab must be "tab-pre" or "tab-post"')
                url = sb.render_state(
                    syn_df.sort_values(by=num_syn_col, ascending=False), return_as="url"
                )
            else:
                if tab_value == "tab-pre":
                    anno_layer = "Output Synapses"
                elif tab_value == "tab-post":
                    anno_layer = "Input Synapses"
                sb = generate_statebuider_syn_grouped(
                    info_cache,
                    anno_layer,
                    preselect=len(selected_rows) == 1,
                    data_resolution=synapse_data_resolution,
                )
                url = sb.render_state(syn_df.iloc[selected_rows], return_as="url")

        if len(url) > MAX_URL_LENGTH:
            return "", large_state_text, True, ""
        else:
            return url, small_state_text, False, ""

    @app.callback(
        Output("all-input-link", "children"),
        Output("all-input-link-button", "children"),
        Output("all-input-link-button", "disabled"),
        Input("all-input-link-button", "n_clicks"),
        Input("all-input-link-button", "children"),
        Input("submit-button", "n_clicks"),
        Input("source-table-json", "data"),
        Input("client-info-json", "data"),
        InputDatastack,
        Input("synapse-table-resolution-json", "data"),
        prevent_initial_call=True,
    )
    def generate_all_input_link(
        _1, _2, curr, rows, info_cache, datastack, data_resolution
    ):
        if not allowed_action_trigger(callback_context, ["all-input-link-button"]):
            return "  ", "Generate Link", False
        return (
            generic_syn_link_generation(
                partial(generate_statebuilder_post, data_resolution=data_resolution),
                rows,
                info_cache,
                datastack,
                config,
                "Neuroglancer Link",
                "Inputs",
            ),
            "Link Generated",
            True,
        )

    @app.callback(
        Output("cell-typed-input-link", "children"),
        Output("cell-typed-input-link-button", "children"),
        Output("cell-typed-input-link-button", "disabled"),
        Input("cell-typed-input-link-button", "n_clicks"),
        Input("submit-button", "n_clicks"),
        Input("source-table-json", "data"),
        Input("client-info-json", "data"),
        InputDatastack,
        Input("synapse-table-resolution-json", "data"),
        prevent_initial_call=True,
    )
    def generate_cell_typed_input_link(
        _1, _2, rows, info_cache, datastack, data_resolution
    ):
        if not allowed_action_trigger(
            callback_context, ["cell-typed-input-link-button"]
        ):
            return "  ", "Generate Link", False
        sb, dfs = generate_statebuilder_syn_cell_types(
            info_cache,
            rows,
            cell_type_column="cell_type",
            position_column=syn_pt_position_col,
            multipoint=True,
            fill_null="NoType",
            data_resolution=data_resolution,
        )
        try:
            url = make_url_robust(dfs, sb, datastack, config)
        except Exception as e:
            return html.Div(str(e))
        return (
            html.A(
                "Cell Typed Input Link",
                href=url,
                target="_blank",
                style={"font-size": "20px"},
            ),
            "Link Generated",
            True,
        )

    @app.callback(
        Output("all-output-link", "children"),
        Output("all-output-link-button", "children"),
        Output("all-output-link-button", "disabled"),
        Input("all-output-link-button", "n_clicks"),
        Input("submit-button", "n_clicks"),
        Input("target-table-json", "data"),
        Input("client-info-json", "data"),
        InputDatastack,
        Input("synapse-table-resolution-json", "data"),
        prevent_initial_call=True,
    )
    def generate_all_output_link(_1, _2, rows, info_cache, datastack, data_resolution):
        if not allowed_action_trigger(callback_context, ["all-output-link-button"]):
            return "", "Generate Link", False
        return (
            generic_syn_link_generation(
                partial(generate_statebuilder_pre, data_resolution=data_resolution),
                rows,
                info_cache,
                datastack,
                config,
                "All Output Link",
                "Outputs",
            ),
            "Link Generated",
            True,
        )

    @app.callback(
        Output("cell-typed-output-link", "children"),
        Output("cell-typed-output-link-button", "children"),
        Output("cell-typed-output-link-button", "disabled"),
        Input("cell-typed-output-link-button", "n_clicks"),
        Input("submit-button", "n_clicks"),
        Input("target-table-json", "data"),
        Input("client-info-json", "data"),
        InputDatastack,
        Input("synapse-table-resolution-json", "data"),
        prevent_initial_call=True,
    )
    def generate_cell_typed_output_link(
        _1, _2, rows, info_cache, datastack, data_resolution
    ):
        if not allowed_action_trigger(
            callback_context, ["cell-typed-output-link-button"]
        ):
            return "  ", "Generate Link", False
        sb, dfs = generate_statebuilder_syn_cell_types(
            info_cache,
            rows,
            cell_type_column="cell_type",
            position_column=syn_pt_position_col,
            multipoint=True,
            fill_null="NoType",
            data_resolution=data_resolution,
        )
        try:
            url = make_url_robust(dfs, sb, datastack, config)
        except Exception as e:
            return html.Div(str(e))
        return (
            html.A(
                "Cell Typed Output Link",
                href=url,
                target="_blank",
                style={"font-size": "20px"},
            ),
            "Link Generated",
            True,
        )

    @app.callback(
        Output("collapse-card", "is_open"),
        Input("collapse-button", "n_clicks"),
        State("collapse-card", "is_open"),
    )
    def toggle_collapse(n, is_open):
        if n:
            return not is_open
        return is_open

    @app.callback(
        Output("plot-collapse", "is_open"),
        Input("plot-collapse-button", "n_clicks"),
        State("plot-collapse", "is_open"),
    )
    def toggle_plot_collapse(n, is_open):
        if n:
            return not is_open
        return is_open

    pass