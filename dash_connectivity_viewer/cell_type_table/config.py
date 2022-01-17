from ..common.config import *

allowed_cell_type_schema = os.environ.get(
    "CT_CELL_TYPE_SCHEMA", "cell_type_local"
).split(",")

ct_table_columns = [
    "id",
    "pt_root_id",
    "classification_system",
    "cell_type",
    "pt_position_x",
    "pt_position_y",
    "pt_position_z",
    "num_anno",
]
