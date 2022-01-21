import flask
import datetime
from dash import callback_context
from dash import dcc
from dash import html
from .config import CellTypeConfig

from dash.dependencies import Input, Output, State
from ..common.dataframe_utilities import *
from ..common.link_utilities import (
    DEFAULT_NGL,
    generate_statebuilder,
    generate_url_cell_types,
    EMPTY_INFO_CACHE,
    MAX_URL_LENGTH,
)
from ..common.lookup_utilities import (
    get_type_tables,
    make_client,
)
from .table_lookup import TableViewer
from .ct_utils import process_dataframe

# Callbacks using data from URL-encoded parameters requires this import
from ..common.dash_url_helper import _COMPONENT_ID_TYPE

InputDatastack = Input({"id_inner": "datastack", "type": _COMPONENT_ID_TYPE}, "value")
OutputDatastack = Output({"id_inner": "datastack", "type": _COMPONENT_ID_TYPE}, "value")
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
    c = CellTypeConfig(config)

    @app.callback(
        OutputDatastack,
        InputDatastack,
    )
    def define_datastack(_):
        return c.default_datastack

    @app.callback(
        OutputCellTypeMenuOptions,
        InputDatastack,
    )
    def cell_type_dropdown(datastack):
        return get_type_tables(c.allowed_cell_type_schema, datastack, c)

    @app.callback(
        Output("data-table", "columns"),
        InputDatastack,
    )
    def define_table_columns(_):
        return [{"name": i, "id": i} for i in c.ct_table_columns]

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
            client = make_client(datastack, c.server_address)
            info_cache = client.info.get_datastack_info()
            info_cache["global_server"] = client.server_address
        except Exception as e:
            return [], str(e), "", EMPTY_INFO_CACHE, "danger"

        if cell_type_table is None:
            return [], "No Cell Type Table Selected", "", info_cache, "info"

        if len(anno_id) == 0:
            anno_id = None
        else:
            anno_id = [int(x) for x in anno_id.split(",")]

        live_query = len(live_query_toggle) == 1

        if live_query:
            timestamp = datetime.datetime.now()
        else:
            timestamp = client.materialize.get_timestamp()
            info_cache["ngl_timestamp"] = timestamp.timestamp()

        anno_type_lookup = {
            "root_id": "root",
            "nucleus_id": "nucleus",
            "anno_id": "annotation",
        }

        if cell_type is None or len(cell_type) == 0:
            annotation_filter = {}
        else:
            annotation_filter = {"cell_type": cell_type}

        try:
            tv = TableViewer(
                cell_type_table,
                client,
                c,
                id_query=anno_id,
                id_query_type=anno_type_lookup[id_type],
                column_query=annotation_filter,
                timestamp=timestamp,
            )
            df = tv.table_data()

            if live_query:
                output_report = f"Current state of cell type table {cell_type_table}"
            else:
                output_report = f"Table {cell_type_table} materialized on {timestamp:%m/%d/%Y} (v{client.materialize.version})"
            output_color = "success"
        except Exception as e:
            df = pd.DataFrame(columns=c.ct_table_columns)
            output_report = str(e)
            output_color = "danger"

        ct_df = stringify_root_ids(process_dataframe(df, "pt_root_id", "pt"))
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
            sb = generate_statebuilder(info_cache, c, anno_layer="anno")
            url = sb.render_state(None, return_as="url")
            link_name = "Table View Neuroglancer Link"
            link_color = (True,)
        else:
            df = pd.DataFrame(rows)
            if len(df) > c.max_dataframe_length:
                url = ""
                link_name = "State Too Large"
                link_color = True
            else:
                df["pt_position"] = df.apply(assemble_pt_position, axis=1)
                url = generate_url_cell_types(selected_rows, df, info_cache, c)
                if len(url) > MAX_URL_LENGTH:
                    url = ""
                    link_name = "State Too Large"
                    link_color = True
                else:
                    link_name = "Table View Neuroglancer Link"
                    link_color = False
        return url, link_name, link_color, ""

    @app.callback(
        Output("whole-table-link", "children"),
        Output("whole-table-link-button", "children"),
        Output("whole-table-link-button", "disabled"),
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
            return ""
        trigger_src = ctx.triggered[0]["prop_id"].split(".")[0]
        if trigger_src in [
            "submit-button",
            "client-info-json",
            "data-table",
        ]:
            return "", "Generate Link", False

        if rows is None or len(rows) == 0:
            return html.Div("No items to show"), "Error", True

        df = pd.DataFrame(rows)
        if len(df) > c.max_server_dataframe_length:
            df = df.sample(c.max_server_dataframe_length)
            sampled = True
        else:
            sampled = False

        df["pt_position"] = df.apply(assemble_pt_position, axis=1)

        if len(df) > c.max_dataframe_length:
            try:
                client = make_client(datastack, c.server_address)
                state = generate_url_cell_types([], df, info_cache, c, return_as="dict")
                state_id = client.state.upload_state_json(state)
                ngl_url = client.info.viewer_site()
                if ngl_url is None:
                    ngl_url = DEFAULT_NGL
                url = client.state.build_neuroglancer_url(state_id, ngl_url=ngl_url)
            except Exception as e:
                return html.Div(str(e)), "Error", True
        else:
            url = generate_url_cell_types([], df, info_cache, c)

        if sampled:
            link_text = f"Neuroglancer Link (State very large — Random {c.max_server_dataframe_length} shown)"
        else:
            link_text = f"Neuroglancer Link"

        return (
            html.A(link_text, href=url, target="_blank", style={"font-size": "20px"}),
            "Link Generated",
            True,
        )

    pass