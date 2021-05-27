import requests
from .config import MAX_CHUNKS


def patch_client(client):
    http = requests.adapters.HTTPAdapter(
        pool_maxsize=2 * MAX_CHUNKS, max_retries=2, pool_block=True
    )
    client.materialize.session.mount("http://", http)
    client.materialize.session.mount("https://", http)

    client.materialize.cg_client.session.mount("http://", http)
    client.materialize.cg_client.session.mount("https://", http)

    client.chunkedgraph.session.mount("http://", http)
    client.chunkedgraph.session.mount("http://", http)
    return client
