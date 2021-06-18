from .config import *


def process_dataframe(df):
    df["soma_depth_um"] = df["pt_position_y"].apply(
        lambda x: voxel_resolution[1] * x / 1000
    )
    df["num_anno"] = df.groupby("pt_root_id").transform("count")["pt_position_x"]
    return df
