import flask
import datetime
from dash import callback_context
import dash_core_components as dcc
import dash_bootstrap_components as dbc
import dash_html_components as html
from dash.dependencies import Input, Output, State
from ..common.dataframe_utilities import *
from ..common.link_utilities import (
    generate_statebuilder,
    generate_url_cell_types,
    EMPTY_INFO_CACHE,
    MAX_URL_LENGTH,
)
from ..common.lookup_utilities import make_client, get_root_id_from_nuc_id
from .config import *
from .ct_utils import process_dataframe

# Callbacks using data from URL-encoded parameters requires this import
from ..common.dash_url_helper import _COMPONENT_ID_TYPE

InputDatastack = Input({"id_inner": "datastack", "type": _COMPONENT_ID_TYPE}, "value")
OutputCellTypeMenuOptions = Output(
    {"id_inner": "cell-type-table-menu", "type": _COMPONENT_ID_TYPE}, "options"
)
StateCellTypeMenu = State(
    {"id_inner": "cell-type-table-menu", "type": _COMPONENT_ID_TYPE}, "value"
)
StateCellType = State({"id_inner": "cell-type", "type": _COMPONENT_ID_TYPE}, "value")
StateAnnoID = State({"id_inner": "anno-id", "type": _COMPONENT_ID_TYPE}, "value")
StateCategoryID = State({"id_inner": "id-type", "type": _COMPONENT_ID_TYPE}, "value")
StateLiveQuery = State(
    {"id_inner": "live-query-toggle", "type": _COMPONENT_ID_TYPE}, "value"
)
######################################
# register_callbacks must be defined #
######################################


def register_callbacks(app, config):
    """This function must be present and add all callbacks to the app.
    Note that inputs from url-encoded values have a different structure than other values.
    A config dict is also allowed to configure standard parameter values for use in callback functions.

    Here, we show basic examples of using the three parameters defined in the layout.page_layout function.

    Parameters
    ----------
    app : Dash app
        Pre-made dash app
    config : dict
        Dict for standard parameter values
    """

    @app.callback(
        OutputCellTypeMenuOptions,
        InputDatastack,
    )
    def cell_type_dropdown(datastack):
        try:
            client = make_client(datastack, config)
        except:
            return []

        tables = client.materialize.get_tables()
        ct_tables = []
        for t in tables:
            meta = client.materialize.get_table_metadata(t)
            if meta["schema"] == "cell_type_local":
                ct_tables.append(t)
        return [{"label": t, "value": t} for t in ct_tables]

    @app.callback(
        Output("data-table", "data"),
        Output("message-text", "children"),
        Output("main-loading-placeholder", "value"),
        Output("client-info-json", "data"),
        Output("message-text", "color"),
        Input("submit-button", "n_clicks"),
        InputDatastack,
        StateCellTypeMenu,
        StateAnnoID,
        StateCategoryID,
        StateCellType,
        StateLiveQuery,
    )
    def update_table(
        clicks,
        datastack,
        cell_type_table,
        anno_id,
        id_type,
        cell_type,
        live_query_toggle,
    ):
        try:
            client = make_client(datastack, config)
            info_cache = client.info.info_cache[datastack]
            info_cache["global_server"] = client.server_address
        except Exception as e:
            return [], str(e), "", EMPTY_INFO_CACHE, "danger"

        if cell_type_table is None:
            return [], "No Cell Type Table Selected", "", info_cache, "info"

        if len(anno_id) == 0:
            anno_id = None
            id_type = "anno_id"

        if len(live_query_toggle) == 1:
            live_query = "live"
        else:
            live_query = "static"

        if live_query == "static":
            timestamp = client.materialize.get_timestamp()
        else:
            timestamp = datetime.datetime.now()

        if anno_id is None:
            root_id = None
        else:
            if id_type == "root_id":
                root_id = int(anno_id)
                anno_id = None
            elif id_type == "nucleus_id":
                root_id = get_root_id_from_nuc_id(
                    nuc_id=int(anno_id),
                    client=client,
                    nucleus_table=NUCLEUS_TABLE,
                    timestamp=timestamp,
                    live=live_query == "live",
                )
                anno_id = None
            elif id_type == "anno_id":
                anno_id = int(anno_id)
                root_id = None
            else:
                raise ValueError('id_type must be either "root_id" or "nucleus_id"')

        if cell_type is None:
            cell_type == ""

        filter_equal_dict = {}
        if anno_id is not None and root_id is not None:
            df = pd.DataFrame(columns=ct_table_columns)
            output_report = "Please set either anno id or root id but not both"
            output_color = "warning"
        else:
            if anno_id is not None:
                filter_equal_dict.update({"id": anno_id})
            if root_id is not None:
                filter_equal_dict.update({"pt_root_id": root_id})
            if len(cell_type) > 0:
                filter_equal_dict.update({"cell_type": cell_type})
            if len(filter_equal_dict) == 0:
                filter_equal_dict = None

            try:
                if live_query == "live":
                    df = client.materialize.live_query(
                        cell_type_table,
                        filter_equal_dict=filter_equal_dict,
                        timestamp=timestamp,
                        split_positions=True,
                    )
                    output_report = (
                        f"Current state of cell type table {cell_type_table}"
                    )
                else:
                    df = client.materialize.query_table(
                        cell_type_table,
                        filter_equal_dict=filter_equal_dict,
                        split_positions=True,
                    )
                    output_report = f"Cell type table {cell_type_table} materialized on {timestamp:%m/%d/%Y} (v{client.materialize.version})"
                output_color = "success"
            except Exception as e:
                df = pd.DataFrame(columns=ct_table_columns)
                output_report = str(e)
                output_color = "danger"

        ct_df = stringify_root_ids(process_dataframe(df))
        return (
            ct_df.to_dict("records"),
            output_report,
            "",
            info_cache,
            output_color,
        )

    @app.callback(
        Output("data-table", "selected_rows"),
        Input("reset-selection", "n_clicks"),
    )
    def reset_selection(n_clicks):
        return []

    @app.callback(
        Output("ngl-link", "href"),
        Output("ngl-link", "children"),
        Output("ngl-link", "disabled"),
        Output("link-loading-placeholder", "children"),
        Input("data-table", "derived_virtual_data"),
        Input("data-table", "derived_virtual_selected_rows"),
        Input("client-info-json", "data"),
    )
    def update_link(rows, selected_rows, info_cache):
        if rows is None or len(rows) == 0:
            sb = generate_statebuilder(info_cache, anno_layer="anno")
            url = sb.render_state(None, return_as="url")
        else:
            df = pd.DataFrame(rows)
            if len(df) > MAX_DATAFRAME_LENGTH:
                url = ""
                link_name = "State Too Large"
                link_color = True
            else:
                df["pt_position"] = df.apply(assemble_pt_position, axis=1)
                url = generate_url_cell_types(selected_rows, df, info_cache)
                if len(url) > MAX_URL_LENGTH:
                    url = ""
                    link_name = "State Too Large"
                    link_color = True
                else:
                    link_name = "Filtered/Selected Rows — Neuroglancer Link"
                    link_color = False
        return url, link_name, link_color, ""

    @app.callback(
        Output("whole-table-link", "children"),
        Output("whole-table-link-loading", "children"),
        Input("whole-table-link-button", "n_clicks"),
        Input("submit-button", "n_clicks"),
        Input("data-table", "data"),
        Input("client-info-json", "data"),
        InputDatastack,
        prevent_initial_call=True,
    )
    def update_whole_table_link(_1, _2, rows, info_cache, datastack):
        ctx = callback_context
        if not ctx.triggered:
            return "", ""
        trigger_src = ctx.triggered[0]["prop_id"].split(".")[0]
        if trigger_src in [
            "submit-button",
            "client-info-json",
            "data-table",
        ]:
            return "", ""

        if rows is None or len(rows) == 0:
            return html.Div("No items to show")

        df = pd.DataFrame(rows)
        if len(df) > MAX_SERVER_DATAFRAME_LENGTH:
            df = df.sample(MAX_SERVER_DATAFRAME_LENGTH)
            sampled = True
        else:
            sampled = False

        df["pt_position"] = df.apply(assemble_pt_position, axis=1)

        if len(df) > MAX_DATAFRAME_LENGTH:
            try:
                client = make_client(datastack, config)
                state = generate_url_cell_types([], df, info_cache, return_as="dict")
                state_id = client.state.upload_state_json(state)
                url = client.state.build_neuroglancer_url(state_id)
            except Exception as e:
                return html.Div(str(e)), ""
        else:
            url = generate_url_cell_types([], df, info_cache)

        if sampled:
            link_text = f"Table Data Link (State very large — Random {MAX_SERVER_DATAFRAME_LENGTH} shown)"
        else:
            link_text = f"Table Data Link"

        return (
            html.A(link_text, href=url, target="_blank", style={"font-size": "20px"}),
            "",
        )

    pass