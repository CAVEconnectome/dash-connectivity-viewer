from cachetools import cached, TTLCache, keys
SPLIT_SUFFIXES = ["x", "y", "z"]


#json schema column types that can act as potential columns for looking at tables
ALLOW_COLUMN_TYPES = ['integer', 'boolean', 'string', 'float']
# Helper functions for turning schema field names ot column names
def bound_pt_position(pt):
    return f"{pt}_position"

def bound_pt_root_id(pt):
    return f"{pt}_root_id"

def split_pt_position(pt_position):
    return [f"{pt_position}_{suf}" for suf in SPLIT_SUFFIXES]

_schema_cache = TTLCache(maxsize=128, ttl=86_400)
def _schema_key(schema_name, client, **kwargs):
    allow_types = kwargs.get('allow_types', ALLOW_COLUMN_TYPES)
    key = keys.hashkey(schema_name, str(allow_types), client.datastack_name)
    return key

@cached(cache=_schema_cache, key=_schema_key)
def get_col_info(schema_name, client, spatial_point='BoundSpatialPoint', allow_types=ALLOW_COLUMN_TYPES, omit_fields=[]):
    schema = client.schema.schema_definition(schema_name)
    sp_name = f"#/definitions/{spatial_point}"
    n_sp = 0
    sn = schema['$ref'].split('/')[-1]
    add_cols = []
    for k, v in schema['definitions'][sn]['properties'].items():
        if v.get('$ref','') == sp_name:
            pt_name = k
            n_sp+=1
        else:
            if k in omit_fields:
                continue
            # Field type is format if exists, type otherwise
            if v.get('format', v.get('type')) in allow_types:
                add_cols.append(k)
    if n_sp != 1:
        pt_name = None
    return pt_name, add_cols

_table_cache = TTLCache(maxsize=128, ttl=86_400)
def _table_key(table_name, client, **kwargs):
    merge_schema = kwargs.get('merge_schema', True)
    allow_types = kwargs.get('allow_types', ALLOW_COLUMN_TYPES)
    key = keys.hashkey(table_name, merge_schema, str(allow_types))
    return key

@cached(cache=_table_cache, key=_table_key)
def get_table_info(tn, client, allow_types=ALLOW_COLUMN_TYPES, merge_schema=True):
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
    if tn is None:
        return None, []
    meta = table_metadata(tn, client)
    ref_table = meta.get('reference_table')
    if ref_table is None or merge_schema is False:
        schema = meta['schema']
        extra_cols = []
    else:
        schema = table_metadata(ref_table, client).get('schema')
        _, extra_cols = get_col_info(meta['schema'], client, allow_types=allow_types, omit_fields=['target_id'])
    pt, add_cols = get_col_info(schema, client, allow_types=allow_types)
    cols = add_cols + extra_cols
    return pt, cols

_metadata_cache = TTLCache(maxsize=128, ttl=86_400)
def _metadata_key(tn, client, **kwargs):
    key = keys.hashkey(tn, client.datastack_name)
    return key

@cached(cache=_metadata_cache, key=_metadata_key)
def table_metadata(table_name, client, meta=None):
    "Caches getting table metadata"
    if meta is None:
        meta = client.materialize.get_table_metadata(table_name)
    if "schema" not in meta:
        meta["schema"] = meta.get('schema_type')
    return meta

_table_list_cache = TTLCache(maxsize=64, ttl=86_400)
def _table_list_key(tables, client):
    key = keys.hashkey('_'.join(tables), client.datastack_name)
    return key

@cached(cache=_table_list_cache, key=_table_list_key)
def populate_metadata_cache(tables, client):
    all_meta = client.materialize.get_tables_metadata()
    for tn, meta in zip(tables, all_meta):
        table_metadata(tn, client, meta=meta)
    pass
