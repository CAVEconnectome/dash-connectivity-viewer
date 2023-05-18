from concurrent.futures import ThreadPoolExecutor
from .schema_utils import table_metadata
import pandas as pd
import re
import numpy as np
from .transform_utils import extract_depth

DESIRED_RESOLUTION = [1, 1, 1]


def query_table_any(
    table, root_id_column, root_ids, client, timestamp, extra_query={}, is_live=True
):
    if root_ids is not None:
        root_ids = np.array(root_ids)
        root_ids = root_ids[root_ids != 0]
    ref_table = table_metadata(table, client).get("reference_table")
    if ref_table is not None:
        return _query_table_join(
            table,
            root_id_column,
            root_ids,
            client,
            timestamp,
            ref_table,
            extra_query=extra_query,
            is_live=is_live,
        )
    else:
        return _query_table_single(
            table,
            root_id_column,
            root_ids,
            client,
            timestamp,
            extra_query=extra_query,
            is_live=is_live,
        )


def _query_table_single(
    table, root_id_column, root_ids, client, timestamp, extra_query, is_live
):
    filter_kwargs = {}
    if root_ids is not None:
        if len(root_ids) == 1:
            if is_live:
                filter_kwargs["filter_equal_dict"] = {
                    table: {root_id_column: root_ids[0]}
                }
            else:
                filter_kwargs["filter_equal_dict"] = {root_id_column: root_ids[0]}
        else:
            if is_live:
                filter_kwargs["filter_in_dict"] = {table: {root_id_column: root_ids}}
            else:
                filter_kwargs["filter_in_dict"] = {root_id_column: root_ids}
    if len(extra_query) != 0:
        if "filter_in_dict" in filter_kwargs:
            if is_live:
                filter_kwargs["filter_in_dict"][table].extend(extra_query)
            else:
                filter_kwargs["filter_in_dict"].extend(extra_query)
        else:
            if is_live:
                filter_kwargs["filter_in_dict"] = {table: extra_query}
            else:
                filter_kwargs["filter_in_dict"] = extra_query
    if is_live:
        return client.materialize.live_live_query(
            table,
            timestamp=timestamp,
            split_positions=True,
            desired_resolution=DESIRED_RESOLUTION,
            allow_missing_lookups=True,
            allow_invalid_root_ids=True,
            metadata=False,
            **filter_kwargs,
        )
    else:
        return client.materialize.query_table(
            table,
            split_positions=True,
            desired_resolution=DESIRED_RESOLUTION,
            metadata=False,
            **filter_kwargs,
        )


def _query_table_join(
    table, root_id_column, root_ids, client, timestamp, ref_table, extra_query, is_live
):
    filter_kwargs = {}
    if root_ids is not None:
        if len(root_ids) == 1:
            filter_kwargs = {
                "filter_equal_dict": {ref_table: {root_id_column: root_ids[0]}}
            }
        else:
            filter_kwargs = {"filter_in_dict": {ref_table: {root_id_column: root_ids}}}
    if len(extra_query) != 0:
        if "filter_in_dict" in filter_kwargs:
            filter_kwargs["filter_in_dict"][table].extend(extra_query)
        else:
            filter_kwargs["filter_in_dict"] = {table: extra_query}
    if is_live:
        join = [[table, "target_id", ref_table, "id"]]
        return client.materialize.live_live_query(
            table,
            joins=join,
            timestamp=timestamp,
            split_positions=True,
            desired_resolution=DESIRED_RESOLUTION,
            suffixes={table: "", ref_table: "_ref"},
            allow_missing_lookups=True,
            allow_invalid_root_ids=True,
            metadata=False,
            **filter_kwargs,
        ).rename(columns={"idx": "id"})
    else:
        join = [[table, "target_id"], [ref_table, "id"]]
        return client.materialize.join_query(
            join,
            suffixes={table: "", ref_table: "_ref"},
            split_positions=True,
            desired_resolution=DESIRED_RESOLUTION,
            metadata=False,
            **filter_kwargs,
        )


def get_specific_soma(soma_table, root_id, client, timestamp, is_live):
    soma_df = query_table_any(
        soma_table, "pt_root_id", [root_id], client, timestamp, is_live=is_live
    )
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
    is_live=True,
):
    if is_live:
        syn_df = client.materialize.query_table(
            synapse_table,
            filter_equal_dict={f"{direction}_pt_root_id": root_id},
            split_positions=True,
            timestamp=timestamp,
            desired_resolution=DESIRED_RESOLUTION,
            metadata=False,
        )
    else:
        syn_df = client.materialize.query_table(
            synapse_table,
            filter_equal_dict={f"{direction}_pt_root_id": root_id},
            split_positions=True,
            desired_resolution=DESIRED_RESOLUTION,
            metadata=False,
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
    is_live,
):
    return _synapse_df(
        "pre",
        synapse_table,
        root_id,
        client,
        timestamp,
        config.syn_pt_position,
        config.synapse_table_columns_dataframe,
        is_live=is_live,
    )


def post_synapse_df(synapse_table, root_id, client, timestamp, config, is_live):
    return _synapse_df(
        "post",
        synapse_table,
        root_id,
        client,
        timestamp,
        config.syn_pt_position,
        config.synapse_table_columns_dataframe,
        is_live=is_live,
    )


def synapse_data(
    synapse_table,
    root_id,
    client,
    timestamp,
    config,
    n_threads=2,
    is_live=True,
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
            is_live,
        )
        post = exe.submit(
            post_synapse_df,
            synapse_table,
            root_id,
            client,
            timestamp,
            config,
            is_live,
        )
    return pre.result(), post.result()


def stringify_root_ids(df, stringify_cols=None):
    if stringify_cols is None:
        stringify_cols = [col for col in df.columns if re.search("_root_id$", col)]
    for col in stringify_cols:
        df[col] = df[col].astype(str)
    return df


def stringify_list(col, df):
    df[col] = df[col].apply(lambda x: str(x)[1:-1]).astype(str)
    return df


def repopulate_list(col, df):
    df[col] = df[col].apply(lambda x: [float(y) for y in x.split(",")]).astype(object)


def rehydrate_dataframe(rows, columns=[]):
    df = pd.DataFrame(rows)
    for col in columns:
        repopulate_list(col, df)
    return df


def _expand_column(df, column, len_column="num_syn"):
    def _expand_column(row):
        return [row[column]] * row[len_column]

    return np.concatenate(list(df.apply(_expand_column, axis=1)))


def _slam_column(df, column):
    return np.concatenate(df[column].values)


def rebuild_synapse_dataframe(rows, config, aligned_volume, value_cols=[]):
    if len(rows) == 0:
        return pd.DataFrame(columns=config.syn_pt_position_split + value_cols)

    df = rehydrate_dataframe(rows, config.syn_pt_position_split).replace("nan", None)
    dfnn = df.dropna(subset=config.soma_depth_column)
    data_dict = {k: _slam_column(dfnn, k) for k in config.syn_pt_position_split}

    value_cols.append(config.soma_depth_column)
    for col in value_cols:
        if col != "":
            data_dict[col] = _expand_column(dfnn, col)
    df_rh = pd.DataFrame(data_dict).replace("nan", None)

    extract_depth(
        df_rh,
        config.synapse_depth_column,
        config.syn_pt_position,
        aligned_volume,
    )
    return df_rh


def _get_single_table(
    table_name,
    root_ids,
    root_id_column,
    include_columns,
    aggregate_map,
    client,
    timestamp,
    table_filter=None,
    is_live=True,
):
    keep_columns = include_columns.copy()
    df = query_table_any(
        table_name, root_id_column, root_ids, client, timestamp, is_live=is_live
    )
    if table_filter is not None:
        df = df.query(table_filter).reset_index(drop=True)

    for k, v in aggregate_map.items():
        df[k] = df.groupby(v["group_by"])[v["column"]].transform(v["agg"])
        keep_columns.append(k)
    if len(aggregate_map) != 0:
        is_dup = df.duplicated(root_id_column, False)
        if np.any(is_dup):
            df.loc[df.index[is_dup], include_columns] = np.nan
        df.drop_duplicates(root_id_column, keep="first", inplace=True)
    else:
        df.drop_duplicates(root_id_column, keep=False, inplace=True)
    df.set_index(root_id_column, inplace=True)
    return df[keep_columns]


def property_table_data(
    root_ids,
    property_mapping,
    client,
    timestamp,
    n_threads=2,
    is_live=True,
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
                    is_live,
                )
            )
    return {tname: job.result() for tname, job in zip(property_mapping, jobs)}
