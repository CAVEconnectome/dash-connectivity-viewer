import pandas as pd
import numpy as np
from caveclient import CAVEclient

from dash_connectivity_viewer.common.lookup_utilities import (
    get_nucleus_id_from_root_id,
    get_root_id_from_nuc_id,
)

from .dataframe_utilities import *
from .link_utilities import voxel_resolution_from_info
from multiprocessing import cpu_count


def _soma_property_entry(soma_table, c):
    return {
        soma_table: {
            "root_id": c.soma_pt_root_id,
            "include": [c.soma_pt_position],
            "aggregate": {
                c.num_soma_prefix: {
                    "group_by": c.soma_pt_root_id,
                    "column": c.nucleus_id_column,
                    "agg": "count",
                }
            },
            "suffix": c.num_soma_suffix,
            "table_filter": c.soma_table_query,
            "data": None,
            "data_resolution": None,
        }
    }


def _synapse_properties(synapse_table, c):
    syn_props = {
        synapse_table: {
            "pre_root_id": c.pre_pt_root_id,
            "post_root_id": c.post_pt_root_id,
            "position_column": c.syn_pt_position,
            "aggregate": {
                c.num_syn_col: {
                    "column": c.syn_id_col,
                    "agg": "count",
                },
            },
        }
    }
    syn_props[synapse_table]["aggregate"].update(c.synapse_aggregation_rules)
    return syn_props


class NeuronData(object):
    def __init__(
        self,
        object_id,
        client,
        config,
        property_tables={},
        timestamp=None,
        n_threads=None,
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
            pool_maxsize=config.pool_maxsize,
        )

        self._property_tables = property_tables

        if config.synapse_table is None:
            synapse_table = client.info.get_datastack_info().get("synapse_table")
        self._synapse_table = synapse_table
        self._synapse_table_properties = _synapse_properties(synapse_table, config)

        if config.soma_table is None:
            soma_table = client.info.get_datastack_info().get("soma_table")

        self._soma_table = soma_table
        self.config = config

        self._timestamp = timestamp

        self._pre_syn_df = None
        self._post_syn_df = None
        self._synapse_data_resolution = None

        self._viewer_resolution = voxel_resolution_from_info(client.info.info_cache)

        if n_threads is None:
            n_threads = cpu_count()
        self.n_threads = n_threads

        self._partner_soma_table = None
        self._partner_root_ids = None

        if soma_table is not None:
            self._property_tables.update(
                _soma_property_entry(
                    soma_table,
                    config,
                )
            )

    @property
    def root_id(self):
        if self._root_id is None:
            new_root_id = get_root_id_from_nuc_id(
                self._nucleus_id,
                self.client,
                self.soma_table,
                self.config,
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
                self.config,
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
    def synapse_data_resolution(self):
        if self._pre_syn_df is None:
            self._get_syn_df()
        return self._synapse_data_resolution

    @property
    def property_tables(self):
        return [k for k in self._property_tables]

    def pre_syn_df(self):
        if self._pre_syn_df is None:
            self._get_syn_df()
        return self._pre_syn_df.copy()

    def post_syn_df(self):
        if self._post_syn_df is None:
            self._get_syn_df()
        return self._post_syn_df.copy()

    def _get_syn_df(self):
        self._pre_syn_df, self._post_syn_df = synapse_data(
            synapse_table=self.synapse_table,
            root_id=self.root_id,
            client=self.client,
            timestamp=self.timestamp,
            config=self.config,
            n_threads=self.n_threads,
        )
        self._synapse_data_resolution = self._pre_syn_df.attrs.get(
            "table_voxel_resolution"
        )
        self._populate_root_ids()
        self._populate_property_tables()

    def _populate_root_ids(self):
        if self._pre_syn_df is None:
            self._get_syn_df()

        self._partner_root_ids = np.unique(
            np.concatenate(
                (
                    self._pre_syn_df[self.config.post_pt_root_id].values,
                    self._post_syn_df[self.config.pre_pt_root_id].values,
                )
            )
        )

    def partners_out(self, properties=True):
        return self._targ_table("pre", properties)

    def partners_in(self, properties=True):
        return self._targ_table("post", properties)

    def _targ_table(self, side, properties):
        if side == "pre":
            prefix = "post"
            syn_df_grp = self.pre_syn_df().groupby(f"{prefix}_pt_root_id")
        elif side == "post":
            prefix = "pre"
            syn_df_grp = self.post_syn_df().groupby(f"{prefix}_pt_root_id")
        targ_df = self._make_simple_targ_df(syn_df_grp).rename(
            columns={f"{prefix}_pt_root_id": "root_id"}
        )
        if properties:
            targ_df = self._merge_property_tables(targ_df, self.config.root_id_col)
        for cn in self.config.synapse_table_columns_display:
            if cn not in targ_df.columns:
                targ_df[cn] = np.nan
        return targ_df

    def _make_simple_targ_df(self, df_grp):
        pts = df_grp[self.config.syn_pt_position].agg(list)
        num_syn = df_grp[self.config.syn_pt_position].agg(len)
        syn_df = pd.DataFrame(
            {
                self.config.syn_pt_position: pts,
                self.config.num_syn_col: num_syn,
            }
        )
        for k, v in self.config.synapse_aggregation_rules.items():
            syn_df[k] = df_grp[v["column"]].agg(v["agg"])
        return syn_df.sort_values(
            by=self.config.num_syn_col, ascending=False
        ).reset_index()

    def _populate_property_tables(self):
        dfs = property_table_data(
            self._partner_root_ids,
            self._property_tables,
            self.client,
            self.timestamp,
            self.n_threads,
        )
        for k, df in dfs.items():
            self._property_tables[k]["data"] = df
            self._property_tables[k]["data_resolution"] = df.attrs.get(
                "table_voxel_resolution"
            )

    def property_data(self, table_name):
        if self._property_tables.get(table_name).get("data") is None:
            self._populate_property_tables()
        return self._property_tables.get(table_name).get("data")

    def property_data_resolution(self, table_name):
        if self._property_tables.get(table_name).get("data") is None:
            self._populate_property_tables()
        return self._property_tables.get(table_name).get("data_resolution")

    def property_root_id_column(self, table_name):
        return self._property_tables.get(table_name).get("root_id")

    def property_columns(self, table_name):
        return [self.property_root_id_column(table_name)] + self._property_tables.get(
            table_name
        ).get("include")

    def property_column_suffix(self, table_name):
        return self._property_tables.get(table_name).get("suffix", "")

    def _merge_property_tables(self, df, merge_column):
        for tn in self.property_tables:
            df = df.merge(
                self.property_data(tn),
                left_on=merge_column,
                right_index=True,
                how="left",
                suffixes=("", self.property_column_suffix(tn)),
            )
            df.rename(
                columns={
                    c: f"{c}{self.property_column_suffix(tn)}"
                    for c in self.property_columns(tn)
                    if f"{c}{self.property_column_suffix(tn)}" not in df.columns
                },
                inplace=True,
            )

        if self.soma_table is not None:
            df[self.config.num_soma_col] = (
                df[self.config.num_soma_col].fillna(0).astype(int)
            )

        return df

    def _get_own_soma_loc(self):
        own_soma_df = get_specific_soma(
            self.soma_table,
            self.root_id,
            self.client,
            self.timestamp,
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

    def soma_location(self):
        if self.soma_table is None:
            return None
        return np.array(self._get_own_soma_loc())

    def soma_location_list(self, length):
        return np.repeat(np.atleast_2d(self.soma_location()), length, axis=0).tolist()
