from re import A
import pandas as pd
import numpy as np
import datetime
from functools import lru_cache
from caveclient import CAVEclient
import datetime

from dash_connectivity_viewer.common.lookup_utilities import (
    get_nucleus_id_from_root_id,
    get_root_id_from_nuc_id,
)

from .dataframe_utilities import *
from .config import *
from .link_utilities import voxel_resolution_from_info
from multiprocessing import cpu_count


class NeuronData(object):
    def __init__(
        self,
        object_id,
        client,
        property_tables={},
        timestamp=None,
        synapse_table=None,
        soma_table=None,
        n_threads=None,
        synapse_position_point=syn_pt_position_col,
        cell_position_point=cell_pt_position_col,
        soma_id_column="id",
        id_type="root",
    ):

        if id_type == "root":
            self._root_id = object_id
            self._nucleus_id = None
        elif id_type == "nucleus":
            self._root_id = None
            self._nucleus_id = object_id

        self._client = CAVEclient(
            datastack_name=client.datastack_name,
            server_address=client.server_address,
            auth_token=client.auth.token,
            pool_block=True,
            pool_maxsize=2 * MAX_CHUNKS,
        )

        self._property_tables = property_tables

        if synapse_table is None:
            synapse_table = client.info.get_datastack_info()["synapse_table"]
        self._synapse_table = synapse_table

        if soma_table is None:
            soma_table = client.info.get_datastack_info()["soma_table"]
        self._soma_table = soma_table
        self._soma_id_column = soma_id_column

        self._timestamp = timestamp

        self._pre_syn_df = None
        self._post_syn_df = None

        self._viewer_resolution = voxel_resolution_from_info(client.info.info_cache)

        if n_threads is None:
            n_threads = cpu_count()
        self.n_threads = n_threads

        self._synapse_position_point = synapse_position_point
        self._cell_position_point = cell_position_point

    @property
    def synapse_position_column(self):
        return f"{self._synapse_position_point}_position"

    @property
    def cell_position_column(self):
        return f"{self._cell_position_point}_position"

    @property
    def cell_root_id_column(self):
        return f"{self._cell_position_point}_root_id"

    @property
    def root_id(self):
        if self._root_id is None:
            new_root_id = get_root_id_from_nuc_id(
                self._nucleus_id,
                self.client,
                self.soma_table,
                self.cell_root_id_column,
                self._soma_id_column,
                self.timestamp,
            )
            if new_root_id is None:
                raise Exception("Nucleus ID not found in soma table")
            else:
                self._root_id = new_root_id
        return self._root_id

    @property
    def nucleus_id(self):
        if self._nucleus_id is None:
            self._nucleus_id = get_nucleus_id_from_root_id(
                self._root_id,
                self.client,
                self.soma_table,
                self.cell_root_id_column,
                self._soma_id_column,
                self.timestamp,
            )
        return self._nucleus_id

    @property
    def client(self):
        return self._client

    @property
    def live_query(self):
        return self._timestamp is not None

    @property
    def timestamp(self):
        return self._timestamp

    @property
    def synapse_table(self):
        return self._synapse_table

    @property
    def soma_table(self):
        return self._soma_table

    @property
    def property_tables(self):
        return [k for k in self._property_tables]

    def pre_syn_df(self):
        if self._pre_syn_df is None:
            self._get_syn_df()
        return self._pre_syn_df

    def post_syn_df(self):
        if self._post_syn_df is None:
            self._get_syn_df()
        return self._post_syn_df

    def _get_syn_df(self):
        self._pre_syn_df, self._post_syn_df = synapse_data(
            synapse_table=self.synapse_table,
            root_id=self.root_id,
            client=self.client,
            timestamp=self.timestamp,
            live_query=self.live_query,
            n_threads=self.n_threads,
            synapse_position_column=self.synapse_position_column,
        )
        self._populate_property_tables()

    @lru_cache(2)
    def partners_out(self, simple=True):
        return self._targ_table("pre", simple)

    @lru_cache(2)
    def partners_in(self, simple=True):
        return self._targ_table("post", simple)

    def _targ_table(self, side, simple):
        if side == "pre":
            prefix = "post"
            syn_df_grp = self.pre_syn_df().groupby(f"{prefix}_pt_root_id")
        elif side == "post":
            prefix = "pre"
            syn_df_grp = self.post_syn_df().groupby(f"{prefix}_pt_root_id")
        targ_simple_df = self._make_simple_targ_df(syn_df_grp).rename(
            columns={f"{prefix}_pt_root_id": "root_id"}
        )
        if simple:
            return targ_simple_df
        else:
            return self._merge_property_tables(targ_simple_df)

    def _make_simple_targ_df(self, df_grp):
        pts = df_grp[self.synapse_position_column].agg(list)
        net_size = df_grp["size"].agg(sum)
        mean_size = df_grp["size"].agg(np.mean)
        num_syn = df_grp[self.synapse_position_column].agg(len)
        return (
            pd.DataFrame(
                {
                    self.synapse_position_column: pts,
                    "num_syn": num_syn,
                    "net_syn_size": net_size,
                    "mean_syn_size": mean_size.astype(int),
                }
            )
            .sort_values(by="num_syn", ascending=False)
            .reset_index()
        )

    def _populate_property_tables(self):
        root_ids = np.unique(
            np.concatenate(
                [
                    self.partners_in(simple=True)["root_id"],
                    self.partners_out(simple=True)["root_id"],
                ]
            )
        )
        dfs = property_table_data(
            root_ids, self._property_tables, self.client, self.timestamp, self.n_threads
        )
        for k, df in dfs.items():
            self._property_tables[k]["data"] = df

    def property_data(self, table_name):
        if self._property_tables.get(table_name).get("data") is not None:
            self._populate_property_tables()
        return self._property_tables.get(table_name).get("data")

    def property_root_id_column(self, table_name):
        return self._property_tables.get(table_name).get("root_id")

    def property_columns(self, table_name):
        return [self.property_root_id_column(table_name)] + self._property_tables.get(
            table_name
        ).get("include")

    def property_column_suffix(self, table_name):
        return self._property_tables.get(table_name).get("suffix", "")

    def _merge_property_tables(self, df):
        for tn in self.property_tables:
            df = (
                df.merge(
                    self.property_data(tn),
                    left_on="root_id",
                    right_on=self.property_root_id_column(tn),
                    how="left",
                )
                .drop(columns=self.property_root_id_column(tn))
                .rename(
                    columns={
                        c: f"{c}{self.property_column_suffix(tn)}"
                        for c in self.property_columns(tn)
                    }
                )
            )
        return df

    def _get_own_soma_loc(self):
        own_soma_df = get_specific_soma(
            self.soma_table,
            self.root_id,
            self.client,
            self.timestamp,
            live_query=self.live_query,
        )
        if len(own_soma_df) != 1:
            own_soma_loc = np.nan
        else:
            own_soma_loc = own_soma_df[self.cell_position_column].values[0]
        return own_soma_loc

    def syn_all_df(self):
        pre_df = self.pre_syn_df()
        pre_df["direction"] = "pre"
        post_df = self.post_syn_df()
        post_df["direction"] = "post"
        syn_df = pd.concat([pre_df, post_df])
        syn_df["x"] = 0
        return syn_df

    @lru_cache(maxsize=1)
    def soma_location(self):
        if self.soma_table is None:
            return None
        return np.array(self._get_own_soma_loc())

    def soma_location_list(self, length):
        return np.repeat(np.atleast_2d(self.soma_location()), length, axis=0).tolist()