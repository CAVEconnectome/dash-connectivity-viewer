import flask
import datetime
from dash import callback_context
from dash import dcc
from dash import html
from .config import CellTypeConfig, RegisterTable

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
from ..common.schema_utils import get_table_info
from ..common.table_lookup import TableViewer

# Callbacks using data from URL-encoded parameters requires this import
from ..common.dash_url_helper import _COMPONENT_ID_TYPE

InputDatastack = Input({"id_inner": "datastack", "type": _COMPONENT_ID_TYPE}, "value")
InputCellTypeMenu = Input(
    {"id_inner": "cell-type-table-menu", "type": _COMPONENT_ID_TYPE}, "value"
)

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
StateValueSearch = State(
    {"id_inner": "value-column-search", "type": _COMPONENT_ID_TYPE}, "value"
)

OutputLiveQueryToggle = Output(
    {"id_inner": "live-query-toggle", "type": _COMPONENT_ID_TYPE},
    "options",
)
OutputLiveQueryValue = Output(
    {"id_inner": "live-query-toggle", "type": _COMPONENT_ID_TYPE}, "value"
)
OutputValueSearch = Output(
    {"id_inner": "value-column-search", "type": _COMPONENT_ID_TYPE}, "options"
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
    def define_datastack(datastack):
        if datastack is None:
            datastack = ""

        if len(datastack) == 0:
            return c.default_datastack
        else:
            return datastack

    @app.callback(
        Output("header-bar", 'children'),
        InputDatastack,
    )
    def set_header(datastack):
        return html.H3(f"Table Info — {datastack}", className="bg-primary text-white p-2 mb-2 text-center")

    @app.callback(
        OutputCellTypeMenuOptions,
        InputDatastack,
    )
    def cell_type_dropdown(datastack):
        return get_type_tables(datastack, c)

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
        OutputValueSearch,
        InputDatastack,
        InputCellTypeMenu,
    )
    def update_value_search_list(datastack, table_name):
        if table_name is None:
            return []
        client = make_client(datastack, c.server_address)
        _, cols = get_table_info(table_name, client, merge_schema=False)
        return [{"label": i, "value": i} for i in cols]


    @app.callback(
        Output("group-by", "options"),
        Input("submit-button", "n_clicks"),
        StateCellTypeMenu,
        InputDatastack,
    )
    def update_groupby_list(_, cell_type_table, datastack):
        if cell_type_table == "" or cell_type_table is None:
            return {}
        else:
            client = make_client(datastack, c.server_address)
            _, cols = get_table_info(cell_type_table, client, allow_types=['boolean', 'integer', 'string'])
            return {k: k for k in cols}

    @app.callback(
        Output("data-table", "columns"),
        Output("pt-column", "data"),
        Output("value-columns", "data"),
        Input("submit-button", "n_clicks"),
        InputDatastack,
        StateCellTypeMenu,
    )
    def define_table_columns(_, datastack, cell_type_table):
        client = make_client(datastack, c.server_address)
        pt, cols = get_table_info(cell_type_table, client)
        reg_con = RegisterTable(pt, cols, c)
        return (
            [{"name": i, "id": i} for i in reg_con.ct_table_columns],
            pt,
            cols,
        )

    @app.callback(
        Output("data-table", "data"),
        Output("message-text", "children"),
        Output("main-loading-placeholder", "value"),
        Output("client-info-json", "data"),
        Output("message-text", "color"),
        Output("data-resolution-json", "data"),
        Input("submit-button", "n_clicks"),
        InputDatastack,
        StateCellTypeMenu,
        StateAnnoID,
        StateCategoryID,
        StateCellType,
        StateLiveQuery,
        StateValueSearch,
    )
    def update_table(
        clicks,
        datastack,
        cell_type_table,
        anno_id,
        id_type,
        value_search,
        live_query_toggle,
        value_search_field,
    ):
        try:
            client = make_client(datastack, c.server_address)
            info_cache = client.info.get_datastack_info()
            info_cache["global_server"] = client.server_address
        except Exception as e:
            return [], str(e), "", EMPTY_INFO_CACHE, "danger", c.data_resolution

        if cell_type_table is None:
            return [], "No Table Selected", "", info_cache, "info", c.data_resolution

        if len(anno_id) == 0:
            anno_id = None
        else:
            anno_id = [int(x) for x in anno_id.split(",")]

        live_query = len(live_query_toggle) == 1

        if live_query and not c.disallow_live_query:
            timestamp = datetime.datetime.utcnow()
        else:
            timestamp = None
            timestamp_ngl = client.materialize.get_timestamp()
            info_cache["ngl_timestamp"] = timestamp_ngl.timestamp()

        anno_type_lookup = {
            "root_id": "root",
            "nucleus_id": "nucleus",
            "anno_id": "annotation",
        }

        annotation_filter = {}
        if value_search is not None or value_search_field is not None:
            if len(value_search_field) > 0 and len(value_search) > 0:
                annotation_filter = {value_search_field: value_search.split(',')}

        try:
            tv = TableViewer(
                cell_type_table,
                client,
                c,
                id_query=anno_id,
                id_query_type=anno_type_lookup[id_type],
                column_query=annotation_filter,
                timestamp=timestamp,
                is_live=live_query,
            )
            df = tv.table_data()
            if live_query:
                output_report = f"Current state of table {cell_type_table}"
            else:
                output_report = f"Table {cell_type_table} materialized on {timestamp_ngl:%m/%d/%Y} (v{client.materialize.version})"
            output_color = "success"
        except Exception as e:
            df = pd.DataFrame(columns=c.ct_table_columns)
            output_report = str(e)
            output_color = "danger"

        ct_df = stringify_root_ids(df, stringify_cols=[c.root_id_col])

        return (
            ct_df.to_dict("records"),
            output_report,
            "",
            info_cache,
            output_color,
            c.data_resolution,
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
        Input("data-resolution-json", "data"),
        Input("pt-column", "data"),
        Input("do-group", "value"),
        Input("group-by", "value"),
    )
    def update_link(
        rows,
        selected_rows,
        info_cache,
        data_resolution,
        pt_column,
        do_group,
        group_column,
    ):
        def state_text(n):
            return f"Neuroglancer: ({n} rows)"

        if info_cache is None:
            return "", "No datastack set", True, ""

        if pt_column is None:
            return "", "No clear point field in table", True, ""

        if 1 in do_group:
            do_group = True
        else:
            do_group = False

        if group_column is None:
            do_group = False
        else:
            if len(group_column) == 0:
                do_group = False

        if rows is None or len(rows) == 0:
            sb = generate_statebuilder(info_cache, c, anno_layer="anno")
            url = sb.render_state(None, return_as="url")
            link_name = state_text(0)
            link_color = True
        else:
            df = pd.DataFrame(rows)
            if len(df) > c.max_dataframe_length and len(selected_rows) == 0:
                url = ""
                link_name = "State Too Large"
                link_color = True
            else:
                url = generate_url_cell_types(
                    selected_rows,
                    df,
                    info_cache,
                    c,
                    pt_column,
                    group_annotations=do_group,
                    cell_type_column=group_column,
                    data_resolution=data_resolution,
                )
                if len(url) > MAX_URL_LENGTH:
                    url = ""
                    link_name = "State Too Large"
                    link_color = True
                else:
                    if len(selected_rows) == 0:
                        link_name = state_text(len(df))
                    else:
                        link_name = state_text(len(selected_rows))
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
        Input("data-resolution-json", "data"),
        Input("pt-column", "data"),
        Input("do-group", "value"),
        Input("group-by", "value"),
        prevent_initial_call=True,
    )
    def update_whole_table_link(_1, _2, rows, info_cache, datastack, data_resolution, pt_column, do_group, group_column):
        ctx = callback_context
        if not ctx.triggered:
            return ""
        trigger_src = ctx.triggered[0]["prop_id"].split(".")[0]
        if trigger_src in [
            "submit-button",
            "client-info-json",
            "data-table",
            "pt-column",
            "do-group",
            "group-by",
        ]:
            return "", "Generate Link", False

        if rows is None or len(rows) == 0:
            return html.Div("No items to show"), "Error", True

        if pt_column is None:
            return "", "No clear point field in table", True, ""

        if 1 in do_group:
            do_group = True
        else:
            do_group = False

        if group_column is None:
            do_group = False
        else:
            if len(group_column) == 0:
                do_group = False

        df = pd.DataFrame(rows)
        if len(df) > c.max_server_dataframe_length:
            df = df.sample(c.max_server_dataframe_length)
            sampled = True
        else:
            sampled = False

        if len(df) > c.max_dataframe_length:
            try:
                client = make_client(datastack, c.server_address)
                state = generate_url_cell_types(
                    [],
                    df,
                    info_cache,
                    c,
                    pt_column,
                    group_annotations=do_group,
                    cell_type_column=group_column,
                    data_resolution=data_resolution,
                    return_as="dict",
                )
                state_id = client.state.upload_state_json(state)
                ngl_url = client.info.viewer_site()
                if ngl_url is None:
                    ngl_url = DEFAULT_NGL
                url = client.state.build_neuroglancer_url(state_id, ngl_url=ngl_url)
            except Exception as e:
                return html.Div(str(e)), "Error", True
        else:
            url = generate_url_cell_types(
                [],
                df,
                info_cache,
                c,
                pt_column,
                group_annotations=do_group,
                cell_type_column=group_column,
                data_resolution= data_resolution,
            )

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
