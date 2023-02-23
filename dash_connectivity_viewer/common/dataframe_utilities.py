from concurrent.futures import ThreadPoolExecutor
from .schema_utils import table_metadata
import pandas as pd
import re
import numpy as np

DESIRED_RESOLUTION = [1,1,1]

def query_table_any(table, root_id_column, root_ids, client, timestamp, extra_query={}):
    ref_table = table_metadata(table, client).get('reference_table')
    if ref_table is not None:
        return _query_table_join(table, root_id_column, root_ids, client, timestamp, ref_table, extra_query=extra_query)
    else:
        return _query_table_single(table, root_id_column, root_ids, client, timestamp, extra_query=extra_query)

def _query_table_single(table, root_id_column, root_ids, client, timestamp, extra_query):
    filter_kwargs = {}
    if root_ids is not None:
        if len(root_ids) == 1:
            filter_kwargs['filter_equal_dict'] = {table: {root_id_column: root_ids[0]}}
        else:
            filter_kwargs['filter_in_dict'] = {table: {root_id_column: root_ids}}
    if len(extra_query) != 0:
        if 'filter_in_dict' in filter_kwargs:
            filter_kwargs['filter_in_dict'][table].extend(extra_query)
        else:
            filter_kwargs['filter_in_dict'] = {table: extra_query}
    return client.materialize.live_live_query(
        table,
        timestamp=timestamp,
        split_positions=True,
        desired_resolution=DESIRED_RESOLUTION,
        **filter_kwargs,
    )

def _query_table_join(table, root_id_column, root_ids, client, timestamp, ref_table, extra_query):
    join = [[table, 'target_id', ref_table, 'id']]
    filter_kwargs = {}
    if root_ids is not None:
        if len(root_ids) == 1:
            filter_kwargs = {'filter_equal_dict': {ref_table: {root_id_column: root_ids[0]}}}
        else:
            filter_kwargs = {'filter_in_dict': {ref_table: {root_id_column: root_ids}}}
    if len(extra_query) != 0:
        if 'filter_in_dict' in filter_kwargs:
            filter_kwargs['filter_in_dict'][ref_table].extend(extra_query)
        else:
            filter_kwargs['filter_in_dict'] = {ref_table: extra_query}
    return client.materialize.live_live_query(
        table,
        joins=join,
        timestamp=timestamp,
        split_positions=True,
        desired_resolution=DESIRED_RESOLUTION,
        suffixes={table: '', ref_table:'_ref'},
        allow_missing_lookups=True,
        **filter_kwargs,
    ).rename(columns={'idx': 'id'})


def get_specific_soma(soma_table, root_id, client, timestamp):
    soma_df = query_table_any(soma_table, 'pt_root_id', [root_id], client, timestamp)
    return soma_df


def _synapse_df(
    direction,
    synapse_table,
    root_id,
    client,
    timestamp,
    synapse_position_column,
    synapse_table_columns,
    exclude_autapses=True,
):
    syn_df = client.materialize.query_table(
        synapse_table,
        filter_equal_dict={f"{direction}_pt_root_id": root_id},
        split_positions=True,
        timestamp=timestamp,
        desired_resolution=DESIRED_RESOLUTION,
    )
    if exclude_autapses:
        syn_df = syn_df.query("pre_pt_root_id != post_pt_root_id").reset_index(
            drop=True
        )
    return syn_df[synapse_table_columns]


def pre_synapse_df(
    synapse_table,
    root_id,
    client,
    timestamp,
    config,
):
    return _synapse_df(
        "pre",
        synapse_table,
        root_id,
        client,
        timestamp,
        config.syn_pt_position,
        config.synapse_table_columns_dataframe,
    )


def post_synapse_df(synapse_table, root_id, client, timestamp, config):
    return _synapse_df(
        "post",
        synapse_table,
        root_id,
        client,
        timestamp,
        config.syn_pt_position,
        config.synapse_table_columns_dataframe,
    )


def synapse_data(
    synapse_table,
    root_id,
    client,
    timestamp,
    config,
    n_threads=2,
):
    if n_threads > 2:
        n_threads = 2
    with ThreadPoolExecutor(n_threads) as exe:
        pre = exe.submit(
            pre_synapse_df,
            synapse_table,
            root_id,
            client,
            timestamp,
            config,
        )
        post = exe.submit(
            post_synapse_df,
            synapse_table,
            root_id,
            client,
            timestamp,
            config,
        )
    return pre.result(), post.result()


def stringify_root_ids(df, stringify_cols=None):
    if stringify_cols is None:
        stringify_cols = [col for col in df.columns if re.search("_root_id$", col)]
    for col in stringify_cols:
        df[col] = df[col].astype(str)
    return df

def stringify_list(col, df):
    df[col] = df[col].apply(lambda x : str(x)[1:-1]).astype(str)
    return df

def repopulate_list(col, df):
    df[col] = df[col].apply(lambda x: [float(y) for y in x.split(',')]).astype(object)

def _get_single_table(
    table_name,
    root_ids,
    root_id_column,
    include_columns,
    aggregate_map,
    client,
    timestamp,
    table_filter=None,
):
    keep_columns = include_columns.copy()
    try:
        df = query_table_any(table_name, root_id_column, root_ids, client, timestamp)
        if table_filter is not None:
            df = df.query(table_filter).reset_index(drop=True)

        for k, v in aggregate_map.items():
            df[k] = df.groupby(v["group_by"])[v["column"]].transform(v["agg"])
            keep_columns.append(k)
        if len(aggregate_map) != 0:
            df.loc[df.index[df.duplicated(root_id_column, False)], include_columns] = np.nan
            df.drop_duplicates(root_id_column, keep="first", inplace=True)
        else:
            df.drop_duplicates(root_id_column, keep=False, inplace=True)
        df.set_index(root_id_column, inplace=True)
        return df[keep_columns]
    except:
        for k in aggregate_map.keys():
            keep_columns.append(k)
        return pd.DataFrame(columns=keep_columns)


def property_table_data(
    root_ids,
    property_mapping,
    client,
    timestamp,
    n_threads=1,
):
    if len(property_mapping) == 0:
        return {}

    jobs = []
    with ThreadPoolExecutor(n_threads) as exe:
        for table_name, attrs in property_mapping.items():
            jobs.append(
                exe.submit(
                    _get_single_table,
                    table_name,
                    root_ids,
                    attrs.get("root_id"),
                    attrs.get("include", []),
                    attrs.get("aggregate", {}),
                    client,
                    timestamp,
                    attrs.get("table_filter", None),
                )
            )
    return {tname: job.result() for tname, job in zip(property_mapping, jobs)}
