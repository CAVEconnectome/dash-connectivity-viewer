from ..common.config import CommonConfig, RegisterTable
from ..common.schema_utils import bound_pt_position, bound_pt_root_id, split_pt_position
import copy


class CellTypeConfig(CommonConfig):
    def __init__(self, config):
        super().__init__(config)

        self.allowed_cell_type_schema_bridge = config.get("ct_cell_type_schema", {})
        self.ct_cell_type_point = None
        self.value_columns = []
        self.omit_cell_type_tables = config.get("omit_cell_type_tables", [])
        self.cell_type_dropdown_options = config.get("cell_type_dropdown_options", [])

    @property
    def ct_cell_type_pt_position(self):
        if self.ct_cell_type_point is None:
            return None
        return bound_pt_position(self.ct_cell_type_point)

    @property
    def ct_cell_type_pt_position_split(self):
        if self.ct_cell_type_point is []:
            return None
        return split_pt_position(self.ct_cell_type_pt_position)

    @property
    def ct_cell_type_root_id(self):
        if self.ct_cell_type_point is None:
            return None
        return bound_pt_root_id(self.ct_cell_type_point)

    @property
    def ct_table_columns(self):
        return (
            [
                self.root_id_col,
            ]
            + self.value_columns
            + self.ct_cell_type_pt_position_split
        )