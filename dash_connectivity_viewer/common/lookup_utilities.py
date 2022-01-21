import flask
from caveclient import CAVEclient


def get_all_schema_tables(
    schemata,
    datastack,
    config,
):
    if isinstance(schemata, str):
        schemata = [schemata]
    client = make_client(datastack, config.server_address)
    tables = client.materialize.get_tables()
    schema_tables = []
    for t in tables:
        if t in config.omit_cell_type_tables:
            continue
        meta = client.materialize.get_table_metadata(t)
        if meta["schema"] in schemata:
            schema_tables.append(t)
    return [{"label": t, "value": t} for t in sorted(schema_tables)]


def get_type_tables(schemata, datastack, config):
    tables = get_all_schema_tables(schemata, datastack, config)

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


def make_client(datastack, server_address):
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
    auth_token = flask.g.get("auth_token", None)
    client = CAVEclient(datastack, server_address=server_address, auth_token=auth_token)
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

    df = client.materialize.query_table(
        nucleus_table,
        filter_equal_dict={config.syn_pt_root_id: root_id},
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
