from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import re
import numpy as np


def assemble_pt_position(row, prefix=""):
    return np.array(
        [
            row[f"{prefix}pt_position_x"],
            row[f"{prefix}pt_position_y"],
            row[f"{prefix}pt_position_z"],
        ]
    )


def get_specific_soma(soma_table, root_id, client, timestamp):
    soma_df = client.materialize.query_table(
        soma_table,
        filter_equal_dict={"pt_root_id": root_id},
        timestamp=timestamp,
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
):
    syn_df = client.materialize.query_table(
        synapse_table,
        filter_equal_dict={f"{direction}_pt_root_id": root_id},
        split_positions=True,
        timestamp=timestamp,
    )

    grp = re.search("^(.*)pt_position", synapse_position_column)
    prefix = grp.groups()[0]

    syn_df[synapse_position_column] = syn_df.apply(
        lambda x: assemble_pt_position(x, prefix=prefix),
        axis=1,
    ).values

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
    df = client.materialize.query_table(
        table_name,
        filter_in_dict={root_id_column: root_ids},
        timestamp=timestamp,
    )
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


def property_table_data(
    root_ids,
    property_mapping,
    client,
    timestamp,
    n_threads=1,
):
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
