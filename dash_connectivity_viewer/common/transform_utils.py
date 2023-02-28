from collections import defaultdict
try:
    import standard_transform
    tform_available = True
except:
    tform_available = False

transform_lookup = defaultdict(standard_transform.identity_transform)
if tform_available:
    transform_lookup['minnie65_phase3'] = standard_transform.minnie_transform_nm()
    transform_lookup['v1dd'] = standard_transform.v1dd_transform_nm()

def get_transform(aligned_volume):
    return transform_lookup[aligned_volume]