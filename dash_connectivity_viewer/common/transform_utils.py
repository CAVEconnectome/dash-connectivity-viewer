from collections import defaultdict
import standard_transform

transform_lookup = defaultdict(standard_transform.identity_transform)
transform_lookup['minnie65_phase3'] = standard_transform.minnie_transform_nm()
transform_lookup['v1dd'] = standard_transform.v1dd_transform_nm()

def get_transform(aligned_volume):
    return transform_lookup[aligned_volume]

def extract_depth(df, depth_column, position_column, aligned_volume):
    if len(df) == 0:
        df[depth_column] = None
        return df
    tform = get_transform(aligned_volume)
    df[depth_column] = tform.apply_dataframe(position_column, df, projection='y')
    return df

def compute_depth_y(pt, aligned_volume):
    tform = get_transform(aligned_volume)
    return tform.apply_project('y', pt)
