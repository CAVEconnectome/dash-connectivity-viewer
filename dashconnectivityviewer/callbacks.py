from annotationframeworkclient.frameworkclient import FrameworkClient
from .app.dataframe_utilities import stringify_root_ids
import dash_core_components as dcc
import dash_bootstrap_components as dbc
import dash_html_components as html
from dash.dependencies import Input, Output, State
from urllib.parse import parse_qs

from .app.link_utilities import (
    generate_statebuilder,
    generate_statebuilder_pre,
    generate_statebuilder_post,
    generate_url_synapses,
)

from .app.dataframe_utilities import minimal_synapse_columns

from .app.neuron_data_base import NeuronData, table_columns
from .app.config import *
from .app.plots import *
import flask 

try:
    from loguru import logger
    import time
except:
    logger = None


def register_callbacks(app, config):

    server_address = config.get("SERVER_ADDRESS", DEFAULT_SERVER_ADDRESS)

    @app.callback(
        Output("data-table", "selected_rows"),
        Input("reset-selection", "n_clicks"),
        Input("connectivity-tab", "value"),
    )
    def reset_selection(n_clicks, tab_value):
        return []

    @app.callback(
        Output("plots", "children"),
        Output("loading-spinner", "children"),
        Output("plot-response-text", "children"),
        Output("target-synapse-json", "data"),
        Output("source-synapse-json", "data"),
        Output("target-table-json", "data"),
        Output("source-table-json", "data"),
        Output("output-tab", "label"),
        Output("input-tab", "label"),
        Output("reset-selection", "n_clicks"),
        Output("client-info-json", "data"),
        Input("submit-button", "n_clicks"),
        State("root_id", "value"),
        State("cell_type_table_dropdown", "value"),
    )
    def update_data(n_clicks, search, input_value, ct_table_value):
        if logger is not None:
            t0 = time.time()
        qd = parse_qs(search[1:])
        #datastack_name = qd.get('datastack', [DEFAULT_DATASTACK])[0]
        datastack_name = DEFAULT_DATASTACK
        auth_token = flask.g.get('auth_token', None)
        print('datastack_name', datastack_name)
        print('auth_token',auth_token )
        client = FrameworkClient(
            datastack_name, server_address=server_address, auth_token=auth_token
        )

        if len(input_value) == 0:
            return (
                html.Div("No plots to show yet"),
                "",
                "",
                [],
                [],
                [],
                [],
                "Output",
                "Input",
                1,
                client.info.info_cache[datastack_name],
            )
        input_root_id = int(input_value)
        nrn_data = NeuronData(
            input_root_id, client=client, cell_type_table=ct_table_value
        )

        try:
            vfig = violin_fig(
                nrn_data, axon_color, dendrite_color, height=500, width=300
            )
            sfig = scatter_fig(nrn_data, valence_colors=val_colors, height=500)
            bfig = bar_fig(nrn_data, val_colors, height=500, width=500)
        except Exception as e:
            return (
                html.Div(str(e)),
                "",
                "",
                [],
                [],
                [],
                [],
                "Output",
                "Input",
                1,
                client.info.info_cache[datastack_name],
            )

        pre_tab_records = nrn_data.pre_tab_dat().to_dict("records")
        post_tab_records = nrn_data.post_tab_dat().to_dict("records")


        pre_targ_df = nrn_data.pre_targ_df()[minimal_synapse_columns]
        pre_targ_df = stringify_root_ids(pre_targ_df)

        post_targ_df = nrn_data.post_targ_df()[minimal_synapse_columns]
        post_targ_df = stringify_root_ids(post_targ_df)

        if logger is not None:
            logger.info(
                f"Data update for {input_root_id} | time:{time.time() - t0:.2f} s, syn_in: {len(pre_targ_df)} , syn_out: {len(post_targ_df)}"
            )

        return (
            dbc.Row(
                [
                    dcc.Graph(figure=vfig),
                    dcc.Graph(figure=sfig),
                    dcc.Graph(figure=bfig),
                ],
                justify="center",
                align="center",
                no_gutters=True,
            ),
            "",
            f"Data for {input_root_id}",
            pre_targ_df.to_dict("records"),
            post_targ_df.to_dict("records"),
            pre_tab_records,
            post_tab_records,
            f"Output (n = {pre_targ_df.shape[0]})",
            f"Input (n = {post_targ_df.shape[0]})",
            np.random.randint(30_000_000),
            client.info.info_cache[datastack_name],
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
        Output("ngl_link", "href"),
        Input("connectivity-tab", "value"),
        Input("data-table", "derived_virtual_data"),
        Input("data-table", "derived_virtual_selected_rows"),
        Input("target-synapse-json", "data"),
        Input("source-synapse-json", "data"),
        Input("client-info-json", "data"),
    )
    def update_link(
        tab_value,
        rows,
        selected_rows,
        syn_records_target,
        syn_records_source,
        info_cache,
    ):
        if rows is None or len(rows) == 0:
            rows = {}
            sb = generate_statebuilder(info_cache)
            return sb.render_state(None, return_as="url")
        elif len(selected_rows) == 0:
            if tab_value == "tab-pre":
                syn_df = pd.DataFrame(syn_records_target)
                syn_df["pre_pt_root_id"] = syn_df["pre_pt_root_id"].astype(int)
                syn_df["post_pt_root_id"] = syn_df["post_pt_root_id"].astype(int)
                sb = generate_statebuilder_pre(info_cache)
                return sb.render_state(syn_df, return_as="url")
            elif tab_value == "tab-post":
                syn_df = pd.DataFrame(syn_records_source)
                syn_df["pre_pt_root_id"] = syn_df["pre_pt_root_id"].astype(int)
                syn_df["post_pt_root_id"] = syn_df["post_pt_root_id"].astype(int)
                sb = generate_statebuilder_post(info_cache)
            return sb.render_state(syn_df, return_as="url")
        else:
            dff = pd.DataFrame(rows)
            if tab_value == "tab-pre":
                return generate_url_synapses(
                    selected_rows,
                    dff,
                    pd.DataFrame(syn_records_target),
                    "pre",
                    info_cache,
                )
            elif tab_value == "tab-post":
                return generate_url_synapses(
                    selected_rows,
                    dff,
                    pd.DataFrame(syn_records_source),
                    "post",
                    info_cache,
                )

    pass