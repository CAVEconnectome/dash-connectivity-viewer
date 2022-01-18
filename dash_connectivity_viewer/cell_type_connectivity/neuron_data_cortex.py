from re import A, I
from ..common.neuron_data_base import NeuronData
from .config import *


def _schema_property_table():
    return {
        "root_id": "pt_root_id",
        "include": ["classification_system", "cell_type"],
    }


def _cell_type_property_entry(cell_type_table):
    return {cell_type_table: _schema_property_table()}


def _is_inhibitory_df(df, is_inhibitory_column, valence_map):
    if len(df) == 0:
        df[is_inhibitory_column] = None

    def _is_inhibitory_row(row, valence_map):
        if pd.isna(row[valence_map[0]]):
            return np.nan
        return row[valence_map[0]] == valence_map[2]

    df[is_inhibitory_column] = df.apply(
        lambda x: _is_inhibitory_row(x, valence_map), axis=1
    )
    return df


def _extract_depth(df, depth_column, position_column, data_resolution):
    if len(df) == 0:
        df[depth_column] = None
        return df

    def _extract_depth_row(row, data_resolution):
        if np.any(pd.isna(row)):
            return np.nan
        else:
            return row[1] * data_resolution[1] / 1000

    df[depth_column] = df[position_column].apply(
        lambda x: _extract_depth_row(x, data_resolution)
    )
    return df


class NeuronDataCortex(NeuronData):
    def __init__(
        self,
        object_id,
        client,
        cell_type_table=None,
        timestamp=None,
        synapse_table=None,
        soma_table=None,
        n_threads=None,
        synapse_position_point=syn_pt_position_col,
        cell_position_point=cell_pt_position_col,
        soma_id_column=NUCLEUS_ID_COLUMN,
        id_type="root",
        soma_table_query=soma_table_query,
        valence_map={},
        soma_depth_column=soma_depth_column,
        is_inhibitory_column=is_inhibitory_column,
        synapse_depth_column=synapse_depth_column,
        cell_type_column=cell_type_column,
    ):

        self.cell_type_table = cell_type_table
        if cell_type_table is not None:
            property_tables = _cell_type_property_entry(cell_type_table)
        else:
            property_tables = {}
        self.valence_map = valence_map
        self.soma_depth_column = soma_depth_column
        self.synapse_depth_column = synapse_depth_column
        self.is_inhibitory_column = is_inhibitory_column
        self.cell_type_column = cell_type_column

        self._synapse_data_resolution = [4, 4, 40]
        self._soma_data_resolution = [4, 4, 40]

        super().__init__(
            object_id,
            client,
            property_tables=property_tables,
            timestamp=timestamp,
            synapse_table=synapse_table,
            soma_table=soma_table,
            n_threads=n_threads,
            synapse_position_point=synapse_position_point,
            cell_position_point=cell_position_point,
            soma_id_column=soma_id_column,
            id_type=id_type,
            soma_table_query=soma_table_query,
        )

    def _decorate_synapse_dataframe(self, df):
        df = self._merge_property_tables(df, "post_pt_root_id")

        if self.is_inhibitory_column is not None:
            if self.valence_map:
                df = _is_inhibitory_df(
                    df,
                    self.is_inhibitory_column,
                    self.valence_map,
                )
            else:
                df[self.is_inhibitory_column] = np.nan
        if self.soma_depth_column is not None:
            df = _extract_depth(
                df,
                self.soma_depth_column,
                self.soma_position_column,
                self._soma_data_resolution,
            )
        return df

    def pre_syn_df_plus(self):
        return self._decorate_synapse_dataframe(self.pre_syn_df())

    def post_syn_df_plus(self):
        return self._decorate_synapse_dataframe(self.post_syn_df())

    def _decorate_partner_dataframe(self, df):
        if self.soma_depth_column is not None:
            df = _extract_depth(
                df,
                self.soma_depth_column,
                self.soma_position_column,
                self._soma_data_resolution,
            )
        if self.is_inhibitory_column is not None:
            if self.valence_map:
                df = _is_inhibitory_df(
                    df,
                    self.is_inhibitory_column,
                    self.valence_map,
                )
            else:
                df[self.is_inhibitory_column] = np.nan
        return df

    def partners_in_plus(self):
        return self._decorate_partner_dataframe(self.partners_in())

    def partners_out_plus(self):
        return self._decorate_partner_dataframe(self.partners_out())

    def _get_syn_df(self):
        super()._get_syn_df()
        if self.synapse_depth_column is not None:
            for syn_df in [self._pre_syn_df, self._post_syn_df]:
                _ = _extract_depth(
                    syn_df,
                    self.synapse_depth_column,
                    self.synapse_position_column,
                    self._synapse_data_resolution,
                )
