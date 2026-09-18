import pandas as pd
import numpy as np
from .lookup_utilities import get_root_id_from_nuc_id, make_client
from .dataframe_utilities import _coerce_nullable_dtypes, query_table_any
from .schema_utils import get_table_info
from ..common.config import RegisterTable
from dfbridge import DataframeBridge
from copy import copy


def _table_schema(config):
    base_schema = {config.root_id_col: config.ct_cell_type_root_id}
    for ptx, sptx in zip(
        ["pt_position_x", "pt_position_y", "pt_position_z"],
        config.ct_cell_type_pt_position_split,
    ):
        base_schema[ptx] = sptx
    for k in config.value_columns:
        base_schema[k] = k
    return base_schema


class TableViewer(object):
    def __init__(
        self,
        table_name,
        client,
        config,
        timestamp=None,
        id_query=None,
        id_query_type=None,
        column_query={},
        is_live=True,
    ):
        self._client = make_client(
            datastack=client.datastack_name,
            server_address=client.server_address,
        )
        self._client.materialize.version = client.materialize.version

        pt, add_cols = get_table_info(table_name, self._client)
        config = RegisterTable(pt, add_cols, config)
        self.config = config
        self._cell_type_bridge_schema = _table_schema(config)

        if config.soma_table is None:
            soma_table = self._client.info.get_datastack_info().get("soma_table")
        else:
            soma_table = config.soma_table

        self._soma_table = soma_table
        self._table_name = table_name

        self._data = None
        self._data_resolution = config.data_resolution

        self._column_query = column_query
        self._annotation_query = None
        self._id_query = id_query
        self._id_query_type = id_query_type
        self._timestamp = timestamp
        self.is_live = is_live
        self._updated_root_ids = {}

        self._process_id_query()

    @property
    def client(self):
        return self._client

    @property
    def live_query(self):
        return self.is_live

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
        return self._data_resolution

    @property
    def cell_type_bridge(self):
        return DataframeBridge(self._cell_type_bridge_schema)

    @property
    def updated_root_ids(self):
        """dict of {queried_root_id: current_root_id} for any queried root ids
        that were not valid at the query timestamp and were substituted with the
        most-overlapping current root id."""
        return self._updated_root_ids

    def _populate_data(self):
        id_column = None
        ids = None
        if self._id_query is not None:
            id_column = self.config.ct_cell_type_root_id
            ids = self._id_query
        if self._annotation_query is not None:
            id_column = "id"
            ids = self._annotation_query

        df = query_table_any(
            self.table_name,
            id_column,
            ids,
            self.client,
            self.timestamp,
            self._column_query,
            is_live=self.is_live,
        )
        self._data = self.cell_type_bridge.reformat(df).fillna(np.nan)

    def _process_id_query(self):
        if self._id_query_type == "root":
            self._id_query = self._update_stale_root_ids(self._id_query)
            self._annotation_query = None
        elif self._id_query_type == "nucleus":
            self._id_query = self._lookup_roots_from_nucleus(self._id_query)
            self._annotation_query = None
        elif self._id_query_type == "annotation":
            self._annotation_query = copy(self._id_query)
            self._id_query = None

    def _update_stale_root_ids(self, root_ids):
        """Substitute any queried root ids that are not valid at the query
        timestamp with the most-overlapping current root id, recording each
        change in ``updated_root_ids`` so the app can warn the user."""
        if root_ids is None:
            return root_ids
        root_ids = np.atleast_1d(np.array(root_ids, dtype=np.int64))
        if len(root_ids) == 0:
            return root_ids

        is_latest = np.atleast_1d(
            self.client.chunkedgraph.is_latest_roots(
                root_ids, timestamp=self.timestamp
            )
        )

        updated = root_ids.copy()
        for idx in np.flatnonzero(~is_latest):
            old_id = int(root_ids[idx])
            new_id = self.client.chunkedgraph.suggest_latest_roots(
                old_id,
                timestamp=self.timestamp,
            )
            self._updated_root_ids[old_id] = int(new_id)
            updated[idx] = new_id
        return updated

    def _lookup_roots_from_nucleus(self, soma_ids):
        df = _coerce_nullable_dtypes(
            self.client.materialize.query_table(
                self.soma_table,
                filter_in_dict={self.config.nucleus_id_column: soma_ids},
                timestamp=self.timestamp,
            )
        )
        if self.config.soma_table_query is not None:
            df = df.query(self.config.soma_table_query)
        return df[self.config.soma_pt_root_id].values
