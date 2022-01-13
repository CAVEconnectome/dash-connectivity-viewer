from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import re
import numpy as np
from .config import *

soma_table_columns = [
    "pt_root_id",
    soma_position_col,
    num_soma_col,
]

cell_type_table_columns = [
    "pt_root_id",
    ct_col,
]

synapse_table_columns = [
    "id",
    "pre_pt_root_id",
    "post_pt_root_id",
    "size",
]

soma_position_cols = [soma_position_col, own_soma_col]
minimal_synapse_columns = ["pre_pt_root_id", "post_pt_root_id", syn_pt_position_col]

# Columns that given nan value unless num_soma==1.
single_soma_cols = [soma_position_col, ct_col]


def assemble_pt_position(row, prefix=""):
    return np.array(
        [
            row[f"{prefix}pt_position_x"],
            row[f"{prefix}pt_position_y"],
            row[f"{prefix}pt_position_z"],
        ]
    )


def radial_distance(row, colx, coly, voxel_resolution):
    if np.any(pd.isnull(row[colx])) or np.any(pd.isnull(row[coly])):
        return np.nan
    else:
        delv = np.array(row[colx] - row[coly])
        rad_inds = [0, 2]
        return np.linalg.norm(voxel_resolution[rad_inds] * delv[rad_inds]) / 1000


def get_specific_soma(soma_table, root_id, client, timestamp, live_query=True):
    if live_query:
        soma_df = client.materialize.live_query(
            soma_table,
            filter_equal_dict={"pt_root_id": root_id},
            timestamp=timestamp,
        )
    else:
        soma_df = client.materialize.query_table(
            soma_table,
            filter_equal_dict={"pt_root_id": root_id},
        )
    return soma_df


def get_soma_df(soma_table, root_ids, client, timestamp=None, live_query=True):
    if live_query:
        soma_df = client.materialize.live_query(
            soma_table,
            filter_in_dict={"pt_root_id": root_ids},
            timestamp=timestamp,
            split_positions=True,
        )
    else:
        soma_df = client.materialize.query_table(
            soma_table,
            filter_in_dict={"pt_root_id": root_ids},
            split_positions=True,
        )

    soma_df[num_soma_col] = (
        soma_df.query(soma_table_query)
        .groupby("pt_root_id")
        .transform("count")["valid"]
    )

    if len(soma_df) == 0:
        soma_df["pt_position"] = []
    else:
        soma_df["pt_position"] = soma_df.apply(assemble_pt_position, axis=1).values

    soma_df.rename(columns={"pt_position": soma_position_col}, inplace=True)

    soma_df["pt_root_id"] = soma_df["pt_root_id"].astype("Int64")

    return soma_df[soma_table_columns]


def get_ct_df(cell_type_table, root_ids, client, timestamp=None, live_query=True):
    if live_query:
        ct_df = client.materialize.live_query(
            cell_type_table,
            filter_in_dict={"pt_root_id": root_ids},
            timestamp=timestamp,
            split_positions=True,
        )
    else:
        ct_df = client.materialize.query_table(
            cell_type_table,
            filter_in_dict={"pt_root_id": root_ids},
            split_positions=True,
        )

    if len(ct_df) == 0:
        ct_df["pt_position"] = []
    else:
        ct_df["pt_position"] = ct_df.apply(assemble_pt_position, axis=1).values

    ct_df.drop_duplicates(subset="pt_root_id", inplace=True)
    ct_df["pt_root_id"] = ct_df["pt_root_id"].astype("Int64")

    return ct_df[cell_type_table_columns]


def _multirun_get_ct_soma(
    soma_table, cell_type_table, root_ids, client, timestamp, n_split=None
):
    if n_split is None:
        n_split = min(max(len(root_ids) // TARGET_ROOT_ID_PER_CALL, 1), MAX_CHUNKS)
    if len(root_ids) == 0:
        soma_df = get_soma_df(soma_table, [], client, timestamp, live_query=False)
        if cell_type_table is not None:
            ct_df = get_ct_df(cell_type_table, [], client, timestamp, live_query=False)
        else:
            ct_df = None
    else:
        root_ids_split = np.array_split(root_ids, n_split)
        out_soma = []
        out_ct = []
        with ThreadPoolExecutor(max_workers=(2 * n_split)) as exe:
            out_soma = [
                exe.submit(
                    get_soma_df, soma_table, rid, client, timestamp, live_query=True
                )
                for rid in root_ids_split
            ]
            if cell_type_table is not None:
                out_ct = [
                    exe.submit(
                        get_ct_df,
                        cell_type_table,
                        rid,
                        client,
                        timestamp,
                        live_query=True,
                    )
                    for rid in root_ids_split
                ]

        soma_df = pd.concat([out.result() for out in out_soma])
        if cell_type_table is not None:
            ct_df = pd.concat([out.result() for out in out_ct])
        else:
            ct_df = None

    client.materialize.session.close()
    client.materialize.cg_client.session.close()
    client.chunkedgraph.session.close()

    return soma_df, ct_df


def _static_get_ct_soma(soma_table, cell_type_table, root_ids, client):
    with ThreadPoolExecutor(2) as exe:
        soma_out = exe.submit(
            get_soma_df, soma_table, root_ids, client, live_query=False
        )
        soma_df = soma_out.result()
        if cell_type_table is not None:
            ct_out = exe.submit(
                get_ct_df, cell_type_table, root_ids, client, live_query=False
            )
            ct_df = ct_out.result()
        else:
            ct_df = None
    return soma_df, ct_df


def cell_typed_soma_df(
    soma_table, cell_type_table, root_ids, client, timestamp, live_query=True
):
    if live_query:
        soma_df, ct_df = _multirun_get_ct_soma(
            soma_table, cell_type_table, root_ids, client, timestamp
        )
    else:
        soma_df, ct_df = _static_get_ct_soma(
            soma_table, cell_type_table, root_ids, client
        )

    if ct_df is not None:
        soma_ct_df = ct_df.merge(
            soma_df.drop_duplicates(subset="pt_root_id"),
            on="pt_root_id",
            how="outer",
        )
    else:
        soma_ct_df = soma_df

    multisoma_ind = soma_ct_df.query("num_soma>1").index
    for col in single_soma_cols:
        if col in soma_ct_df.columns:
            soma_ct_df.loc[multisoma_ind, col] = pd.NA
    return soma_ct_df


def _synapse_df(
    direction,
    synapse_table,
    root_id,
    client,
    timestamp,
    live_query=True,
    synapse_position_column=syn_pt_position_col,
    exclude_autapses=True,
):
    if live_query:
        syn_df = client.materialize.live_query(
            synapse_table,
            filter_equal_dict={f"{direction}_pt_root_id": root_id},
            timestamp=timestamp,
            split_positions=True,
        )
    else:
        syn_df = client.materialize.query_table(
            synapse_table,
            filter_equal_dict={f"{direction}_pt_root_id": root_id},
            split_positions=True,
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
    return syn_df[synapse_table_columns + [synapse_position_column]]


def pre_synapse_df(
    synapse_table, root_id, client, timestamp, live_query, synapse_position_column
):
    return _synapse_df(
        "pre",
        synapse_table,
        root_id,
        client,
        timestamp,
        live_query,
        synapse_position_column,
    )


def post_synapse_df(
    synapse_table, root_id, client, timestamp, live_query, synapse_position_column
):
    return _synapse_df(
        "post",
        synapse_table,
        root_id,
        client,
        timestamp,
        live_query,
        synapse_position_column,
    )


def synapse_data(
    synapse_table,
    root_id,
    client,
    timestamp,
    live_query=True,
    n_threads=2,
    synapse_position_column=syn_pt_position_col,
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
            live_query=live_query,
            synapse_position_column=synapse_position_column,
        )
        post = exe.submit(
            post_synapse_df,
            synapse_table,
            root_id,
            client,
            timestamp,
            live_query=live_query,
            synapse_position_column=synapse_position_column,
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
    client,
    timestamp,
):
    keep_columns = [root_id_column] + include_columns
    df = client.materialize.query_table(
        table_name,
        filter_in_dict={root_id_column: root_ids},
        timestamp=timestamp,
    )
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
                    attrs["root_id"],
                    attrs["include"],
                    client,
                    timestamp,
                )
            )
    return {tname: job.result() for tname, job in zip(property_mapping, jobs)}