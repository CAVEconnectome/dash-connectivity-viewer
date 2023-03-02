import datetime
import pandas as pd
from functools import partial

from dash import dcc, html, callback_context
from dash.dependencies import Input, Output, State
import dash_bootstrap_components as dbc

from .config import TypedConnectivityConfig
from ..common import table_lookup as tbl
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
)
from ..common.schema_utils import get_table_info
from ..common.dataframe_utilities import (
    stringify_root_ids, stringify_list, rehydrate_dataframe, rebuild_synapse_dataframe
)
from ..cell_type_table.config import CellTypeConfig
from .neuron_data_cortex import NeuronDataCortex as NeuronData
from .cortex_panels import *

try:
    from loguru import logger
    import time
except:
    logger = None

InputDatastack = Input({"id_inner": "datastack", "type": _COMPONENT_ID_TYPE}, "value")
OutputDatastack = Output({"id_inner": "datastack", "type": _COMPONENT_ID_TYPE}, "value")

StateRootID = State({"id_inner": "anno-id", "type": _COMPONENT_ID_TYPE}, "value")
StateCellTypeTable = State(
    {"id_inner": "cell-type-table-dropdown", "type": _COMPONENT_ID_TYPE},
    "value",
)
OutputCellTypeMenuOptions = Output(
    {"id_inner": "cell-type-table-dropdown", "type": _COMPONENT_ID_TYPE},
    "options",
)
OutputCellTypeValue = Output(
    {"id_inner": "cell-type-table-dropdown", "type": _COMPONENT_ID_TYPE},
    "value",
)

StateAnnoType = State({"id_inner": "id-type", "type": _COMPONENT_ID_TYPE}, "value")
StateLiveQuery = State(
    {"id_inner": "live-query-toggle", "type": _COMPONENT_ID_TYPE}, "value"
)
StateLinkGroupValue = State('group-by', 'value')

OutputLiveQueryToggle = Output(
    {"id_inner": "live-query-toggle", "type": _COMPONENT_ID_TYPE},
    "options",
)
OutputLiveQueryValue = Output(
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

def combine_columns(c, c_tbl):
    pass

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
        syn_df = rehydrate_dataframe(rows, config.syn_pt_position_split)
        sb = sb_function(info_cache)
    try:
        url = make_url_robust(
            syn_df.sort_values(by=config.num_syn_col, ascending=False),
            sb,
            datastack,
            config,
        )
    except Exception as e:
        return html.Div(str(e))

    return html.A(link_text, href=url, target="_blank", style={"font-size": "20px"})

def make_plots(rows, config, aligned_volume, color_column):
    df = rebuild_synapse_dataframe(
        rows,
        config,
        aligned_volume,
        value_cols=[color_column],
    )
    scatter_fig = scatter_fig_df(df, config, color_column, width=450, height=350)

    return scatter_fig

def make_plots_old(ndat, config, color_column):
    if ndat is None:
        return html.Div("")
    if config.show_depth_plots and ndat.soma_table:
        violin = violin_fig(ndat, height=350)
        scatter = scatter_fig(ndat, color_column, width=450, height=350)

    # if ndat.value_table is not None:
        # if ndat.valence_map is not None:
    #         bars = split_bar_fig(ndat, height=350)
    #     else:
    #         bars = single_bar_fig(ndat, height=350)

    row_contents = []
    if config.show_depth_plots and ndat.soma_table:
        row_contents.append(
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
            )
        )
        row_contents.append(
            dbc.Col(
                [
                    html.H5(
                        "Synapse/Target Synapse Depth", style={"text-align": "center"}
                    ),
                    dcc.Graph(
                        figure=scatter, style={"text-align": "center", "width": "100%"}
                    ),
                ]
            )
        )
    # if ndat.cell_type_table is not None:
    #     row_contents.append(
    #         dbc.Col(
    #             [
    #                 html.H5(
    #                     "Target Synapse by Cell Type", style={"text-align": "center"}
    #                 ),
    #                 dcc.Graph(figure=bars, style={"text-align": "center"}),
    #             ]
    #         )
    #     )
    plot_content = dbc.Row(row_contents)

    return html.Div(plot_content)


def register_callbacks(app, config):

    c = TypedConnectivityConfig(config)
    c_tbl = CellTypeConfig(config)

    @app.callback(
        Output("data-table", "selected_rows"),
        Input("reset-selection", "n_clicks"),
        Input("connectivity-tab", "value"),
    )
    def reset_selection(n_clicks, tab_value):
        return []

    @app.callback(
        Output("data-table", "columns"),
        Output("group-by", "options"),
        Input("submit-button", "n_clicks"),
        InputDatastack,
        StateCellTypeTable,
    )
    def define_table_columns(_, datastack, cell_type_table):
        client = make_client(datastack, c.server_address)
        _, val_cols = get_table_info(cell_type_table, client)
        table_cons = c.table_columns + val_cols
        return (
            [{"name": i, "id": i} for i in table_cons],
            [{"label": k, "value": k} for k in val_cols],
        )

    @app.callback(
        OutputDatastack,
        InputDatastack,
    )
    def define_datastack(datastack):
        if datastack is None:
            datastack = ""

        if len(datastack) == 0:
            return c.default_datastack
        else:
            return datastack

    @app.callback(
        OutputLiveQueryToggle,
        OutputLiveQueryValue,
        InputDatastack,
        StateLiveQuery,
    )
    def disable_live_query(_, lq):
        options_active = [{"label": "Live Query", "value": 1}]
        options_disabled = [{"label": "Live Query", "value": 1, "disabled": True}]
        if c.disallow_live_query:
            return options_disabled, ""
        else:
            return options_active, lq

    @app.callback(
        OutputCellTypeMenuOptions,
        InputDatastack,
    )
    def set_cell_type_dropdown(datastack):
        return get_type_tables(datastack, c)

    @app.callback(
        OutputCellTypeValue,
        InputDatastack,
    )
    def default_cell_type_option(_):
        return c.default_cell_type_option

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
            client = make_client(datastack_name, c.server_address)
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

        if not ct_table_value:
            ct_table_value = None
        info_cache["cell_type_column"] = ct_table_value

        if len(query_toggle) == 1 and not c.disallow_live_query:
            live_query = True
        else:
            live_query = False

        if live_query:
            timestamp = datetime.datetime.utcnow()
        else:
            timestamp = None
            timestamp_ngl = client.materialize.get_timestamp()
            info_cache["ngl_timestamp"] = timestamp_ngl.timestamp()

        if anno_id is None or len(anno_id) == 0:
            return (
                html.Div("Please select a cell id and press Submit"),
                "info",
                "",
                [],
                [],
                "Output",
                "Input",
                1,
                EMPTY_INFO_CACHE,
                make_plots(None, c, None),
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

        try:
            if ct_table_value:
                schema_name = client.materialize.get_table_metadata(ct_table_value)[
                    "schema_type"
                ]
            else:
                schema_name = None

            nrn_data = NeuronData(
                object_id=object_id,
                client=client,
                config=c,
                value_table=ct_table_value,
                timestamp=timestamp,
                id_type=object_id_type,
                n_threads=2,
            )

            root_id = nrn_data.root_id
            info_cache["root_id"] = str(root_id)

            pre_targ_df = nrn_data.partners_out_plus()
            pre_targ_df = stringify_root_ids(
                pre_targ_df, stringify_cols=[c.root_id_col]
            )

            post_targ_df = nrn_data.partners_in_plus()
            post_targ_df = stringify_root_ids(
                post_targ_df, stringify_cols=[c.root_id_col]
            )

            n_syn_pre = pre_targ_df[c.num_syn_col].sum()
            n_syn_post = post_targ_df[c.num_syn_col].sum()

            for col in nrn_data.config.syn_pt_position_split:
                stringify_list(col, pre_targ_df)
                stringify_list(col, post_targ_df)


            if logger is not None:
                logger.info(
                    f"Data update for {root_id} | time:{time.time() - t0:.2f} s, syn_in: {len(pre_targ_df)} , syn_out: {len(post_targ_df)}"
                )
            if nrn_data.nucleus_id is not None and nrn_data.soma_table is not None:
                nuc_id_text = f"  (nucleus id: {nrn_data.nucleus_id})"
            else:
                nuc_id_text = ""
            if ct_table_value:
                ct_text = f"table {ct_table_value}"
            else:
                ct_text = "no cell type table"

            if live_query:
                message_text = f"Current connectivity for root id {root_id}{nuc_id_text} and {ct_text}"
            else:
                message_text = f"Connectivity for root id {root_id}{nuc_id_text} and {ct_text} materialized on {timestamp_ngl:%m/%d/%Y} (v{client.materialize.version})"

            plts = make_plots(nrn_data, c, None)
            syn_res = nrn_data.synapse_data_resolution
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
                syn_res,
            )
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
                make_plots(None, c),
                None,
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

        def small_state_text(n):
            return f"Neuroglancer: ({n} partners)"

        if info_cache is None:
            return "", "No datastack set", True, ""

        if rows is None or len(rows) == 0:
            rows = {}
            sb = generate_statebuilder(info_cache, c)
            return (
                sb.render_state(None, return_as="url"),
                small_state_text(0),
                False,
                "",
            )
        else:
            syn_df = rehydrate_dataframe(rows, c.syn_pt_position_split)

            if len(selected_rows) == 0:
                if tab_value == "tab-pre":
                    sb = generate_statebuilder_pre(
                        info_cache, c, data_resolution=synapse_data_resolution
                    )
                elif tab_value == "tab-post":
                    sb = generate_statebuilder_post(
                        info_cache, c, data_resolution=synapse_data_resolution
                    )
                else:
                    raise ValueError('tab must be "tab-pre" or "tab-post"')
                url = sb.render_state(
                    syn_df.sort_values(by=c.num_syn_col, ascending=False),
                    return_as="url",
                )
                small_out_text = small_state_text(len(syn_df))

            else:
                if tab_value == "tab-pre":
                    anno_layer = "Output Synapses"
                elif tab_value == "tab-post":
                    anno_layer = "Input Synapses"
                sb = generate_statebuider_syn_grouped(
                    info_cache,
                    anno_layer,
                    c,
                    preselect=len(selected_rows) == 1,
                    data_resolution=synapse_data_resolution,
                )
                url = sb.render_state(
                    syn_df.iloc[selected_rows].sort_values(
                        by=c.num_syn_col, ascending=False
                    ),
                    return_as="url",
                )
                small_out_text = small_state_text(len(selected_rows))

        if len(url) > MAX_URL_LENGTH:
            return "", large_state_text, True, ""
        else:
            return url, small_out_text, False, ""

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
                partial(
                    generate_statebuilder_post,
                    config=c,
                    data_resolution=data_resolution,
                ),
                rows,
                info_cache,
                datastack,
                c,
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
        Input('group-by', 'value'),
        prevent_initial_call=True,
    )
    def generate_cell_typed_input_link(
        _1, _2, rows, info_cache, datastack, data_resolution, value_column,
    ):
        if value_column is None:
            return "  ", "No Annotation Column Set", True
        if not allowed_action_trigger(
            callback_context, ["cell-typed-input-link-button"]
        ):
            return "  ", "Generate Link", False

        sb, dfs = generate_statebuilder_syn_cell_types(
            info_cache,
            rows,
            c,
            cell_type_column=value_column,
            multipoint=True,
            fill_null="NoType",
            data_resolution=data_resolution,
        )
        try:
            url = make_url_robust(dfs, sb, datastack, c)
        except Exception as e:
            return html.Div(str(e))
        return (
            html.A(
                "Grouped Input Link",
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
                partial(
                    generate_statebuilder_pre, config=c, data_resolution=data_resolution
                ),
                rows,
                info_cache,
                datastack,
                c,
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
        Input('group-by', 'value'),
        prevent_initial_call=True,
    )
    def generate_cell_typed_output_link(
        _1, _2, rows, info_cache, datastack, data_resolution, value_column,
    ):
        if value_column is None:
            return "  ", "No Annotation Column Set", True

        if not allowed_action_trigger(
            callback_context, ["cell-typed-output-link-button"]
        ):
            return "  ", "Generate Link", False
        sb, df_dict = generate_statebuilder_syn_cell_types(
            info_cache,
            rows,
            c,
            cell_type_column=value_column,
            multipoint=True,
            fill_null="NoType",
            data_resolution=data_resolution,
        )
        try:
            url = make_url_robust(df_dict, sb, datastack, c)
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