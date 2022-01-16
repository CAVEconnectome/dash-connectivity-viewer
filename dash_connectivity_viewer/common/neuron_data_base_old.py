import pandas as pd
import numpy as np
import datetime
from functools import lru_cache
from typing import *
from caveclient import CAVEclient
import datetime

import plotly.graph_objects as go
from .client_patch import patch_client
from .dataframe_utilities import *
from .config import *
from .link_utilities import voxel_resolution_from_info


class NeuronData(object):
    def __init__(
        self,
        oid: int,
        client: CAVEclient,
        synapse_table: str = None,
        cell_type_table: str = None,
        soma_table: str = None,
        timestamp: Union[datetime.datetime, None] = None,
        axon_only: bool = False,
        split_threshold: float = 0.7,
        live_query: bool = True,
    ) -> None:
        self._oid = oid
        self._client = patch_client(client)

        self._live_query = live_query

        if timestamp is None:
            timestamp = datetime.datetime.now()

        self._timestamp = timestamp
        self.axon_only = axon_only

        if synapse_table is None:
            synapse_table = client.info.get_datastack_info()["synapse_table"]
        self.synapse_table = synapse_table
        self.soma_table = soma_table
        self.cell_type_table = cell_type_table
        self.split_threshold = split_threshold
        self._post_syn_df = None
        self._pre_syn_df = None
        self.voxel_resolution = voxel_resolution_from_info(client.info.info_cache)

    @property
    def oid(self) -> int:
        return self._oid

    @property
    def client(self) -> CAVEclient:
        return self._client

    @property
    def timestamp(self) -> datetime.datetime:
        return self._timestamp

    @property
    def live_query(self) -> bool:
        return self._live_query

    def pre_syn_df(self) -> pd.DataFrame:
        if self._pre_syn_df is None:
            self._get_syn_df()
        return self._pre_syn_df

    def post_syn_df(self) -> pd.DataFrame:
        if self._post_syn_df is None:
            self._get_syn_df()
        return self._post_syn_df

    @lru_cache(maxsize=1)
    def pre_targ_simple_df(self) -> pd.DataFrame:
        syn_df_grp = self.pre_syn_df().groupby("post_pt_root_id")
        targ_simple_df = self._make_simple_targ_df(syn_df_grp)
        return targ_simple_df.rename(columns={"post_pt_root_id": "root_id"})

    @lru_cache(maxsize=1)
    def post_targ_simple_df(self) -> pd.DataFrame:
        syn_df_grp = self.post_syn_df().groupby("pre_pt_root_id")
        targ_simple_df = self._make_simple_targ_df(syn_df_grp)
        return targ_simple_df.rename(columns={"pre_pt_root_id": "root_id"})

    def _make_simple_targ_df(self, df_grp):
        pts = df_grp["ctr_pt_position"].agg(list)
        net_size = df_grp["size"].agg(sum)
        mean_size = df_grp["size"].agg(np.mean)
        num_syn = df_grp["ctr_pt_position"].agg(len)
        return (
            pd.DataFrame(
                {
                    "ctr_pt_position": pts,
                    "num_syn": num_syn,
                    "net_syn_size": net_size,
                    "mean_syn_size": mean_size.astype(int),
                }
            )
            .sort_values(by="num_syn", ascending=False)
            .reset_index()
        )

    def _get_syn_df(self):
        self._pre_syn_df, self._post_syn_df = synapse_data(
            self.synapse_table,
            self.oid,
            self.client,
            self.timestamp,
            live_query=self.live_query,
        )

    @lru_cache(maxsize=1)
    def syn_df(self) -> pd.DataFrame:
        pre_df = self.pre_syn_df()
        pre_df["direction"] = "pre"
        post_df = self.post_syn_df()
        post_df["direction"] = "post"
        syn_df = pd.concat([pre_df, post_df])
        syn_df["x"] = 0
        return syn_df

    def _get_own_soma_loc(self):
        own_soma_df = get_specific_soma(
            self.soma_table,
            self.oid,
            self.client,
            self.timestamp,
            live_query=self.live_query,
        )
        if len(own_soma_df) != 1:
            own_soma_loc = np.nan
        else:
            own_soma_loc = own_soma_df["pt_position"].values[0]
        return own_soma_loc

    @lru_cache(maxsize=1)
    def soma_location(self) -> np.ndarray:
        if self.soma_table is None:
            return None
        return np.array(self._get_own_soma_loc())

    def soma_location_list(self, length: int) -> list:
        return np.repeat(np.atleast_2d(self.soma_location()), length, axis=0).tolist()

    def _get_ct_soma_df(self, target_ids):
        targ_ct_soma_df = cell_typed_soma_df(
            self.soma_table,
            self.cell_type_table,
            target_ids,
            self.client,
            self.timestamp,
            live_query=self.live_query,
        )
        return targ_ct_soma_df

    def _target_ids(self):
        pre_oids = self.pre_syn_df()["post_pt_root_id"]
        post_oids = self.post_syn_df()["pre_pt_root_id"]
        return np.unique(np.concatenate([pre_oids, post_oids]))

    @lru_cache(maxsize=5)
    def targ_soma_df(self):
        return self._get_ct_soma_df(self._target_ids())

    def _compute_pre_targ_df(self):
        pre_df = self.pre_syn_df()
        targ_soma_df = self.targ_soma_df()

        pre_targ_df = pre_df.merge(
            targ_soma_df,
            left_on="post_pt_root_id",
            right_on="pt_root_id",
            how="left",
        ).drop(columns=["pt_root_id"])
        pre_targ_df[num_soma_col].fillna(0, inplace=True)
        pre_targ_df[num_soma_col] = pre_targ_df[num_soma_col].astype(int)

        pre_targ_df[own_soma_col] = self.soma_location_list(len(pre_targ_df))
        return pre_targ_df

    @lru_cache(maxsize=5)
    def pre_targ_df(self) -> pd.DataFrame:
        return self._compute_pre_targ_df().fillna(np.nan)

    def _compute_post_targ_df(self):
        post_df = self.post_syn_df()
        targ_soma_df = self.targ_soma_df()

        post_targ_df = post_df.merge(
            targ_soma_df,
            left_on="pre_pt_root_id",
            right_on="pt_root_id",
            how="left",
        ).drop(columns=["pt_root_id"])
        post_targ_df[num_soma_col].fillna(0, inplace=True)
        post_targ_df[num_soma_col] = post_targ_df[num_soma_col].astype(int)
        post_targ_df[own_soma_col] = self.soma_location_list(len(post_targ_df))
        return post_targ_df

    @lru_cache(maxsize=5)
    def post_targ_df(self) -> pd.DataFrame:
        return self._compute_post_targ_df().fillna(np.nan)

    def _compute_tab_dat(self, direction):
        if direction == "pre":
            df = self.pre_targ_df()
            merge_column = "post_pt_root_id"
        elif direction == "post":
            df = self.post_targ_df()
            merge_column = "pre_pt_root_id"
        if len(df) == 0:
            df["ctr_pt_position"] = []
            df[num_syn_col] = []
            df[net_size_col] = []
            df[mean_size_col] = []
        else:
            df[num_syn_col] = df.groupby(merge_column).transform("count")[
                "ctr_pt_position"
            ]
            df[net_size_col] = (
                df[[merge_column, "size"]]
                .groupby(merge_column)
                .transform("sum")["size"]
            )
            df[mean_size_col] = (
                df[[merge_column, "size"]]
                .groupby(merge_column)
                .transform("mean")["size"]
            ).astype(int)

        df_unique = (
            df.drop_duplicates(subset=merge_column)
            .drop(columns=["size"])
            .drop(columns="ctr_pt_position")
        )

        pt_df = df.groupby(merge_column)["ctr_pt_position"].agg(list)
        df_unique = df_unique.merge(pt_df, left_on=merge_column, right_index=True)

        tab_dat = df_unique.sort_values(by=num_syn_col, ascending=False)
        tab_dat[merge_column] = tab_dat[merge_column].astype(
            str
        )  # Dash can't handle int64
        return tab_dat

    @lru_cache(maxsize=5)
    def pre_tab_dat(self) -> pd.DataFrame:
        return (
            self._compute_tab_dat("pre")
            .fillna(np.nan)
            .drop(columns=["pre_pt_root_id"])
            .rename(columns={"post_pt_root_id": "root_id"})
        )

    @lru_cache(maxsize=5)
    def post_tab_dat(self) -> pd.DataFrame:
        return (
            self._compute_tab_dat("post")
            .fillna(np.nan)
            .drop(columns=["post_pt_root_id"])
            .rename(columns={"pre_pt_root_id": "root_id"})
        )
