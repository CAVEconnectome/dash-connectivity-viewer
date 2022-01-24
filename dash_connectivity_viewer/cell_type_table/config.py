from ..common.config import CommonConfig, bound_pt_position, bound_pt_root_id


class CellTypeConfig(CommonConfig):
    def __init__(self, config):
        super().__init__(config)

        self.allowed_cell_type_schema_bridge = config.get("ct_cell_type_schema", {})
        self.allowed_cell_type_schema = list(
            self.allowed_cell_type_schema_bridge.keys()
        )

        self.ct_cell_type_point = config.get("ct_schema_soma_pt", "pt")
        self.ct_cell_type_pt_position = bound_pt_position(self.ct_cell_type_point)
        self.ct_cell_type_root_id = bound_pt_root_id(self.ct_cell_type_point)
        self.omit_cell_type_tables = config.get("omit_cell_type_tables", [])
        self.cell_type_dropdown_options = config.get("cell_type_dropdown_options", [])
        self.ct_table_columns = [
            "id",
            "pt_root_id",
            "classification_system",
            "cell_type",
            "pt_position_x",
            "pt_position_y",
            "pt_position_z",
        ]
