from .config import *


def process_dataframe(df, root_id_column, pt_column):
    df["num_anno"] = df.groupby(root_id_column).transform("count")[
        f"{bound_pt_position(pt_column)}_x"
    ]
    return df
