import numpy as np
from ..common.schema_utils import get_table_info
from ..common.table_lookup import TableViewer
from ..common.neuron_data_base import NeuronData
from ..common.transform_utils import extract_depth, compute_depth_y
from ..common.config import RegisterTable

ALLOW_COLUMN_TYPES_DISCRETE = ['integer', 'boolean', 'string']
class NeuronDataCortex(NeuronData):
    def __init__(
        self,
        object_id,
        client,
        config,
        value_table=None,
        timestamp=None,
        n_threads=None,
        id_type="root",
        is_live=True,
    ):
        self.config = config
        super().__init__(
            object_id,
            client,
            config,
            timestamp=timestamp,
            n_threads=n_threads,
            id_type=id_type,
            is_live=is_live,
        )
        self.value_table = value_table
        self._value_data = None
        self._value_columns = None
    
    @property
    def aligned_volume(self):
        return self.client.info.get_datastack_info()['aligned_volume']['name']

    def create_table_viewer(self, root_ids):
        pt, vals = get_table_info(self.value_table, self.client, allow_types=ALLOW_COLUMN_TYPES_DISCRETE)
        cfg = RegisterTable(pt, vals, self.config)
        return TableViewer(
            self.value_table,
            self.client,
            cfg,
            timestamp=self.timestamp,
            id_query=root_ids,
            id_query_type="root",
            is_live=self.is_live,
        )

    def _decorate_synapse_dataframe(self, df, merge_column):
        df = self._merge_property_tables(df, merge_column)

        if self.config.soma_depth_column is not None and self.soma_table is not None:
            df = extract_depth(
                df,
                self.config.soma_depth_column,
                self.config.soma_position_agg,
                self.aligned_volume,
            )

        return df

    def pre_syn_df_plus(self):
        return self._decorate_synapse_dataframe(
            self.pre_syn_df(), self.config.post_pt_root_id
        )

    def post_syn_df_plus(self):
        return self._decorate_synapse_dataframe(
            self.post_syn_df(), self.config.pre_pt_root_id
        )

    def _decorate_partner_dataframe(self, df):
        if self.config.soma_depth_column is not None and self.soma_table is not None:
            df = extract_depth(
                df,
                self.config.soma_depth_column,
                self.config.soma_position_agg,
                self.aligned_volume,
            )
        val_df = self.value_data
        if val_df is None:
            return df
        else:
            return df.merge(
                val_df,
                on=self.config.root_id_col,
                how='left',
            )

    def partners_in_plus(self):
        return self._decorate_partner_dataframe(self.partners_in())

    def partners_out_plus(self):
        return self._decorate_partner_dataframe(self.partners_out())

    @property
    def value_data(self):
        if self.value_table is None:
            return None
        if self._value_data is None:
            root_ids = np.unique(
                np.concatenate(
                    (
                        self.pre_syn_df()[self.config.post_pt_root_id],
                        self.post_syn_df()[self.config.pre_pt_root_id],
                    )
                )
            )
            tl = self.create_table_viewer(root_ids)
            self._value_data = tl.table_data().drop_duplicates(
                self.config.root_id_col, keep=False
            )[self.value_table_columns]
        return self._value_data

    @property
    def value_table_columns(self):
        if self._value_columns is None:
            _, self._value_columns = get_table_info(self.value_table, self.client)
        return [self.config.root_id_col] + self._value_columns

    def _get_syn_df(self):
        super()._get_syn_df()
        if self.config.synapse_depth_column is not None:
            for syn_df in [self._pre_syn_df, self._post_syn_df]:
                extract_depth(
                    syn_df,
                    self.config.synapse_depth_column,
                    self.config.syn_pt_position,
                    self.aligned_volume,
                )

    def soma_depth(self):
        return compute_depth_y(
            self.soma_location(), self.aligned_volume
        )
