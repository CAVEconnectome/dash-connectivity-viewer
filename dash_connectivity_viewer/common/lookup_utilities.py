import flask
from .schema_utils import get_table_info
from caveclient.tools.caching import CachedClient as CAVEclient

def table_is_value_source(table, client):
    pt, vals = get_table_info(table, client)
    if pt is not None and len(vals) > 0:
        return True
    else:
        return False

def get_all_schema_tables(
    datastack,
    config,
):
    client = make_client(datastack, config.server_address)
    tables = client.materialize.get_tables()
    schema_tables = []
    for t in tables:
        if t in config.omit_cell_type_tables:
            continue
        if table_is_value_source(t, client):
            schema_tables.append(t)
    return [{"label": t, "value": t} for t in sorted(schema_tables)]

def get_type_tables(datastack, config):
    tables = get_all_schema_tables(datastack, config)

    named_options = config.cell_type_dropdown_options
    if named_options is None:
        return tables
    else:
        named_option_dict = {r["value"]: r["label"] for r in named_options[::-1]}

    new_tables = []
    for t in tables:
        if t["value"] in named_option_dict:
            new_tables = [
                {"label": named_option_dict.get(t["value"]), "value": t["value"]}
            ] + new_tables
        else:
            new_tables.append(t)
    return new_tables


def make_client(datastack, server_address, **kwargs):
    """Build a framework client with appropriate auth token

    Parameters
    ----------
    datastack : str
        Datastack name for client
    config : dict
        Config dict for settings such as server address.
    server_address : str, optional
        Global server address for the client, by default None. If None, uses the config dict.

    """
    try:
        auth_token = flask.g.get("auth_token", None)
    except:
        auth_token = None
    client = CAVEclient(datastack, server_address=server_address, auth_token=auth_token, **kwargs)
    return client


def get_root_id_from_nuc_id(
    nuc_id,
    client,
    nucleus_table,
    config,
    timestamp=None,
):
    """Look up current root id from a nucleus id

    Parameters
    ----------
    nuc_id : int
        Annotation id from a nucleus
    client : CAVEclient
        CAVEclient for the server in question
    nucleus_table : str
        Name of the table whose annotation ids are nucleus lookups.
    timestamp : datetime.datetime, optional
        Timestamp for live query lookup. Required if live is True. Default is None.
    live : bool, optional
        If True, uses a live query. If False, uses the materialization version set in the client.

    Returns
    -------
    [type]
        [description]
    """
    df = client.materialize.query_table(
        nucleus_table,
        filter_equal_dict={config.nucleus_id_column: nuc_id},
        timestamp=timestamp,
    )
    if len(df) == 0:
        return None
    else:
        return df.iloc[0][config.soma_pt_root_id]


def get_nucleus_id_from_root_id(
    root_id,
    client,
    nucleus_table,
    config,
    timestamp=None,
):
    filter_equal_dict = {config.soma_pt_root_id: root_id}
    if config.soma_table_query is not None:
        filter_equal_dict.update(config.soma_table_query)

    df = client.materialize.query_table(
        nucleus_table,
        filter_equal_dict=filter_equal_dict,
        timestamp=timestamp,
    )

    if config.soma_table_query is not None:
        df = df.query(config.soma_table_query)

    if len(df) == 0:
        return None
    elif len(df) == 1:
        return df[config.nucleus_id_column].values[0]
    else:
        return df[config.nucleus_id_column].values
