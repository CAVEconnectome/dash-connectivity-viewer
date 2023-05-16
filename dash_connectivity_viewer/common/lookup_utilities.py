import flask
from .schema_utils import get_table_info, populate_metadata_cache
from caveclient.tools.caching import CachedClient as CAVEclient
from .dataframe_utilities import query_table_any
import numpy as np
# from concurrent.futures import ThreadPoolExecutor

def table_is_value_source(table, client):
    if table is None:
        return False
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
    populate_metadata_cache(tables, client)
    schema_tables = []
    is_val_source = {t: table_is_value_source(t, client) for t in tables if t not in config.omit_cell_type_tables}
    schema_tables = [k for k, v in is_val_source.items() if v]
    return [{"label": t, "value": t} for t in sorted(schema_tables)]

def get_type_tables(datastack, config):
    tables = get_all_schema_tables(datastack, config)

    named_options = config.cell_type_dropdown_options
    if named_options is None:
        return tables
    else:
        if len(named_options) == 0:
            named_option_dict = dict()
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
    is_live=True,
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
    df = query_table_any(
            nucleus_table,
            config.soma_pt_root_id,
            None,
            client,
            timestamp=timestamp,
            extra_query={config.nucleus_id_column: [nuc_id]},
            is_live=is_live,
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
    is_live=True,
):
    df = query_table_any(
        nucleus_table,
        config.soma_pt_root_id,
        np.array([root_id]),
        client,
        timestamp=timestamp,
        is_live=is_live,
    )

    if config.soma_table_query is not None:
        df = df.query(config.soma_table_query)

    if len(df) == 0:
        return None
    elif len(df) == 1:
        return df[config.nucleus_id_column].values[0]
    else:
        return df[config.nucleus_id_column].values
