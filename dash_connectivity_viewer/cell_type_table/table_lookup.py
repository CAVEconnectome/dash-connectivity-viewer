import pandas as pd
import numpy as np
from ..common.lookup_utilities import get_root_id_from_nuc_id
from .config import *
from ..common.link_utilities import voxel_resolution_from_info
from caveclient import CAVEclient
from copy import copy


class TableViewer(object):
    def __init__(
        self,
        table_name,
        client,
        bound_point="pt",
        id_query=None,
        id_query_type=None,
        soma_table=None,
        column_query={},
        soma_id_column=NUCLEUS_ID_COLUMN,
        soma_table_query=soma_table_query,
        timestamp=None,
    ):

        self._client = CAVEclient(
            datastack_name=client.datastack_name,
            server_address=client.server_address,
            auth_token=client.auth.token,
        )

        if soma_table is None:
            soma_table = client.info.get_datastack_info().get("soma_table")
        self._soma_table = soma_table
        self._soma_id_column = soma_id_column
        self._soma_table_query = soma_table_query
        self._soma_root_id_column = bound_pt_root_id(cell_pt_position_col)

        self._table_name = table_name

        for k, v in column_query.items():
            if isinstance(v, str):
                column_query[k] = [v]
        self._column_query = column_query

        self._data = None
        self._data_resolution = None
        self._data_root_id_column = bound_pt_root_id(bound_point)
        self._data_position_column = bound_pt_position(bound_point)

        self._annotation_query = None
        self._id_query = id_query
        self._id_query_type = id_query_type
        self._timestamp = timestamp

        self._process_id_query()

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
    def table_name(self):
        return self._table_name

    @property
    def soma_table(self):
        return self._soma_table

    def table_data(self):
        if self._data is None:
            self._populate_data()
        return self._data

    @property
    def table_resolution(self):
        if self._data_resolution is None:
            self._populate_data()
        return self._data_resolution

    def _populate_data(self):
        filter_in_dict = {}
        if self._id_query is not None:
            filter_in_dict.update({self._data_root_id_column: self._id_query})
        if self._annotation_query is not None:
            filter_in_dict.update({"id": self._annotation_query})
        filter_in_dict.update(self._column_query)
        df = self.client.materialize.query_table(
            self.table_name,
            filter_in_dict=filter_in_dict,
            timestamp=self.timestamp,
            split_positions=True,
        )

        self._data = df
        self._data_resolution = df.attrs.get("table_voxel_resolution")

    def _process_id_query(self):
        if self._id_query_type == "root":
            self._id_query = self._id_query
            self._annotation_query = None
        elif self._id_query_type == "nucleus":
            self._id_query = self._lookup_roots_from_nucleus(self._id_query)
            self._annotation_query = None
        elif self._id_query_type == "annotation":
            self._annotation_query = copy(self._id_query)
            self._id_query = None

    def _lookup_roots_from_nucleus(self, soma_ids):
        df = self.client.materialize.query_table(
            self.soma_table,
            filter_in_dict={self._soma_id_column: soma_ids},
            timestamp=self.timestamp,
        )
        if self._soma_table_query is not None:
            df = df.query(self._soma_table)
        return df[self._soma_root_id_column].values
