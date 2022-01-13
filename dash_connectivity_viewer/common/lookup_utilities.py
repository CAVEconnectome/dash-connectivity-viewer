import flask
from caveclient import CAVEclient
from .config import soma_table_query


def get_all_schema_tables(schema, datastack, config, server_address=None):
    client = make_client(datastack, config, server_address=server_address)
    tables = client.materialize.get_tables()
    schema_tables = []
    for t in tables:
        meta = client.materialize.get_table_metadata(t)
        if meta["schema"] == schema:
            schema_tables.append(t)
    return [{"label": t, "value": t} for t in schema_tables]


def make_client(datastack, config, server_address=None):
    """Build a framework client with appropriate auth token

    Parameters
    ----------
    datastack : str
        Datastack name for client
    config : dict
        Config dict for settings such as server address.
    server_address : str, optional
        Global server address for the client, by default None. If None, uses the config dict.

    Returns
    -------
    [type]
        [description]
    """
    auth_token = flask.g.get("auth_token", None)
    if server_address is None:
        server_address = config.get("SERVER_ADDRESS")

    print(datastack, server_address, auth_token)
    client = CAVEclient(datastack, server_address=server_address, auth_token=auth_token)
    return client


def get_root_id_from_nuc_id(
    nuc_id,
    client,
    nucleus_table,
    cell_root_id_column,
    soma_id_column,
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
        filter_equal_dict={soma_id_column: nuc_id},
        timestamp=timestamp,
    )
    if len(df) == 0:
        return None
    else:
        return df.iloc[0][cell_root_id_column]


def get_nucleus_id_from_root_id(
    root_id, client, nucleus_table, cell_root_id_column, soma_id_column, timestamp=None
):

    df = client.materialize.query_table(
        nucleus_table,
        filter_equal_dict={cell_root_id_column: root_id},
        timestamp=timestamp,
    )

    if soma_table_query is not None:
        df = df.query(soma_table_query)

    if len(df) == 0:
        return None
    elif len(df) == 1:
        return df[soma_id_column].values[0]
    else:
        return df[soma_id_column].values
