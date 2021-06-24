from caveclient.CAVEclient import CAVEclient
from dash_bootstrap_components._components.CardBody import CardBody
from dash_bootstrap_components._components.CardHeader import CardHeader
import dash_core_components as dcc
import dash_bootstrap_components as dbc
import dash_html_components as html
from dash.dependencies import Input, Output, State
from dash import callback_context
from dash_html_components.A import A

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
from ..common.lookup_utilities import make_client, get_root_id_from_nuc_id
from ..common.dataframe_utilities import stringify_root_ids
from ..common.neuron_data_base import NeuronData
from ..common.config import syn_pt_position_col

from .config import *
from .plots import bar_fig, violin_fig, scatter_fig

import datetime

try:
    from loguru import logger
    import time
except:
    logger = None

InputDatastack = Input({"id_inner": "datastack", "type": _COMPONENT_ID_TYPE}, "value")
StateRootID = State({"id_inner": "anno-id", "type": _COMPONENT_ID_TYPE}, "value")
StateCellTypeTable = (
    State(
        {"id_inner": "cell-type-table-dropdown", "type": _COMPONENT_ID_TYPE},
        "value",
    ),
)
StateAnnoType = State({"id_inner": "id-type", "type": _COMPONENT_ID_TYPE}, "value")
StateLiveQuery = State(
    {"id_inner": "live-query-toggle", "type": _COMPONENT_ID_TYPE}, "value"
)


def allowed_action_trigger(ctx, allowed_buttons):
    if not ctx.triggered:
        return False
    trigger_src = ctx.triggered[0]["prop_id"].split(".")[0]
    return trigger_src in allowed_buttons


def generic_syn_link_generation(
    sb_function, rows, info_cache, datastack, config, link_text, item_name="synapses"
):
    if rows is None or len(rows) == 0:
        return html.Div("No {item_name} to show")
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


def make_plots(nrn_data):
    if nrn_data is None:
        return html.Div("")
    violin = violin_fig(nrn_data, axon_color, dendrite_color, height=350)
    scatter = scatter_fig(nrn_data, val_colors, height=350)
    bars = bar_fig(nrn_data, val_colors, height=350)
    plot_content = dbc.Row(
        [
            dbc.Col(
                [
                    html.H5("Input/Output Depth", style={"text-align": "center"}),
                    dcc.Graph(figure=violin, style={"width": "100%", "height": "100%"}),
                ]
            ),
            dbc.Col(
                [
                    html.H5(
                        "Synapse/Target Synapse Depth", style={"text-align": "center"}
                    ),
                    dcc.Graph(figure=scatter, style={"text-align": "center"}),
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
    @app.callback(
        Output("data-table", "selected_rows"),
        Input("reset-selection", "n_clicks"),
        Input("connectivity-tab", "value"),
    )
    def reset_selection(n_clicks, tab_value):
        return []

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
            )

        if len(query_toggle) == 1:
            live_query = True
        else:
            live_query = False

        if live_query:
            timestamp = datetime.datetime.now()
        else:
            timestamp = client.materialize.get_timestamp()
            info_cache["ngl_timestamp"] = timestamp.timestamp()

        if anno_id is None or len(anno_id) == 0:
            return (
                html.Div("Please select a root id and press Submit"),
                "info",
                "",
                [],
                [],
                "Output",
                "Input",
                1,
                EMPTY_INFO_CACHE,
                make_plots(None),
            )
        else:
            if id_type == "root_id":
                root_id = int(anno_id)
            elif id_type == "nucleus_id":
                root_id = get_root_id_from_nuc_id(
                    nuc_id=int(anno_id),
                    client=client,
                    nucleus_table=NUCLEUS_TABLE,
                    timestamp=timestamp,
                    live=live_query,
                )
            info_cache["root_id"] = str(root_id)

        nrn_data = NeuronData(
            root_id,
            client=client,
            cell_type_table=ct_table_value,
            soma_table=NUCLEUS_TABLE,
            live_query=live_query,
            timestamp=timestamp,
        )

        pre_targ_df = nrn_data.pre_tab_dat()
        pre_targ_df = stringify_root_ids(pre_targ_df, stringify_cols=["root_id"])

        post_targ_df = nrn_data.post_tab_dat()
        post_targ_df = stringify_root_ids(post_targ_df, stringify_cols=["root_id"])

        n_syn_pre = pre_targ_df[num_syn_col].sum()
        n_syn_post = post_targ_df[num_syn_col].sum()

        if logger is not None:
            logger.info(
                f"Data update for {root_id} | time:{time.time() - t0:.2f} s, syn_in: {len(pre_targ_df)} , syn_out: {len(post_targ_df)}"
            )

        if live_query:
            message_text = f"Current connectivity for root id {root_id}"
        else:
            message_text = f"Connectivity for root id {root_id} materialized on {timestamp:%m/%d/%Y} (v{client.materialize.version})"

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
            make_plots(nrn_data),
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
    )
    def update_link(
        tab_value,
        rows,
        selected_rows,
        info_cache,
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
                    sb = generate_statebuilder_pre(info_cache)
                elif tab_value == "tab-post":
                    sb = generate_statebuilder_post(info_cache)
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
                    info_cache, anno_layer, preselect=len(selected_rows) == 1
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
        prevent_initial_call=True,
    )
    def generate_all_input_link(_1, _2, curr, rows, info_cache, datastack):
        if not allowed_action_trigger(callback_context, ["all-input-link-button"]):
            return "  ", "Generate Link", False
        return (
            generic_syn_link_generation(
                generate_statebuilder_post,
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
        prevent_initial_call=True,
    )
    def generate_cell_typed_input_link(_1, _2, rows, info_cache, datastack):
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
        prevent_initial_call=True,
    )
    def generate_all_output_link(_1, _2, rows, info_cache, datastack):
        if not allowed_action_trigger(callback_context, ["all-output-link-button"]):
            return "", "Generate Link", False
        return (
            generic_syn_link_generation(
                generate_statebuilder_pre,
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
        prevent_initial_call=True,
    )
    def generate_cell_typed_output_link(_1, _2, rows, info_cache, datastack):
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