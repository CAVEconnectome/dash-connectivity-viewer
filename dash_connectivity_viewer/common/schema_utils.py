from cachetools import cached, LRUCache

def get_col_info(schema_name, client, spatial_point='BoundSpatialPoint', omit_spatial_point='SpatialPoint'):
    schema = client.schema.schema_definition(schema_name)
    sp_name = f"#/definitions/{spatial_point}"
    omit_sp_name = f"#/definitions/{omit_spatial_point}"
    n_sp = 0
    sn = schema['$ref'].split('/')[-1]
    alt_cols = []
    for k, v in schema['definitions'][sn]['properties'].items():
        if v.get('$ref','') == sp_name:
            pt_name = k
            n_sp+=1
        else:
            if v.get('$ref', '') != omit_sp_name:
                alt_cols.append(k)
    if n_sp != 1:
        pt_name = None
    return pt_name, alt_cols


@cached(LRUCache(maxsize=128))
def get_table_info(tn, client):
    """Get the point column and additional columns from a table

    Parameters
    ----------
    tn : str
        Table name
    client : CAVEclient
        Client
    omit_cols : list, optional
        List of strings for tables to omit from the list. By default, ['valid', 'target_id']

    Returns
    -------
    pt
        Point column prefix
    cols
        List of additional columns names
    """
    meta = client.materialize.get_table_metadata(tn)
    ref_table = meta.get('reference_table')
    if ref_table is None:
        schema = meta['schema']
        extra_cols = []
    else:
        schema = client.materialize.get_table_metadata(ref_table).get('schema')
        _, extra_cols = get_spatial_point(meta['schema'], client)
    pt, alt_cols = get_spatial_point(schema, client)
    cols = alt_cols + extra_cols
    return pt, cols