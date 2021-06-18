import flask
from annotationframeworkclient import FrameworkClient


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
    client = FrameworkClient(
        datastack, server_address=server_address, auth_token=auth_token
    )
    return client


def get_root_id_from_nuc_id(nuc_id, client, nucleus_table, timestamp=None, live=True):
    """Look up current root id from a nucleus id

    Parameters
    ----------
    nuc_id : int
        Annotation id from a nucleus
    client : FrameworkClient
        FrameworkClient for the server in question
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
    if live:
        df = client.materialize.live_query(
            nucleus_table, timestamp=timestamp, filter_equal_dict={"id": nuc_id}
        )
    else:
        df = client.materialize.query_table(
            nucleus_table, filter_equal_dict={"id": nuc_id}
        )
    if len(df) == 0:
        return None
    else:
        return df.iloc[0]["pt_root_id"]


def get_root_id_from_point(point_string, client, timestamp):