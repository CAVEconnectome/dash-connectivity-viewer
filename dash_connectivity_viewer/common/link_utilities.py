from nglui import statebuilder
from nglui.statebuilder import PointAnnotation
import pandas as pd
import numpy as np
from seaborn import color_palette
from itertools import cycle
from .schema_utils import bound_pt_position
from .dataframe_utilities import rehydrate_dataframe

EMPTY_INFO_CACHE = {"aligned_volume": {}, "cell_type_column": None}


def image_source(info_cache):
    if info_cache is None:
        return None
    return info_cache["aligned_volume"].get("image_source", "")


def aligned_volume(info_cache):
    if info_cache is None:
        return None
    return info_cache.get("aligned_volume", {}).get("name")


def seg_source(info_cache):
    if info_cache is None:
        return None
    return info_cache.get("segmentation_source", "")


def viewer_site(info_cache):
    if info_cache is None:
        return None
    return info_cache.get("viewer_site", "") or None


def state_server(info_cache):
    if info_cache is None:
        return None
    return f"{info_cache.get('global_server', '')}/nglstate/api/v1/post"


def root_id(info_cache):
    if info_cache is None:
        return None
    rid = info_cache.get("root_id", None)
    if rid is None:
        return None
    return int(rid)


def timestamp(info_cache):
    if info_cache is None:
        return None
    return info_cache.get("ngl_timestamp", None)


def voxel_resolution_from_info(info_cache):
    try:
        vr = [
            info_cache.get("viewer_resolution_x"),
            info_cache.get("viewer_resolution_y"),
            info_cache.get("viewer_resolution_z"),
        ]
        if any(v is None for v in vr):
            return None
        return vr
    except Exception:
        return None


def _image_contrast_shader(black, white):
    return (
        f"#uicontrol invlerp normalized(range=[{black}, {white}])\n"
        "void main() {\n"
        "  emitGrayscale(normalized());\n"
        "}\n"
    )


def _make_viewer(info_cache, config):
    res = voxel_resolution_from_info(info_cache)
    vs = statebuilder.ViewerState(
        target_site="spelunker",
        dimensions=res,
        infer_coordinates=res is None,
    )
    img_src = image_source(info_cache)
    if img_src:
        vs.add_image_layer(
            source=img_src,
            name="img",
        )
    seg_src = seg_source(info_cache)
    if seg_src:
        vs.add_segmentation_layer(source=seg_src, name="seg", alpha_3d=0.8)
    return vs


def _explode_position_df(df, position_split_cols):
    """One row per point — the 4.x equivalent of 3.x PointMapper(multipoint=True).

    Coerces stringified list cells (from dcc.Store JSON round-trip) back to lists,
    then explodes the three position columns simultaneously.
    """
    if df is None or len(df) == 0:
        return df
    cols = [c for c in position_split_cols if c in df.columns]
    if not cols:
        return df
    df = df.copy()
    for col in cols:
        sample = df[col].iloc[0]
        if isinstance(sample, str):
            df[col] = df[col].apply(
                lambda x: [float(y) for y in x.split(",")]
                if isinstance(x, str) and x else x
            )
    return df.explode(cols).reset_index(drop=True)


def _to_url(vs, info_cache, client, shorten):
    return vs.to_url(
        target_url=viewer_site(info_cache),
        shorten=shorten,
        client=client,
    )


def _unique_int_ids(df, col):
    if df is None or col not in df.columns or len(df) == 0:
        return []
    return (
        pd.to_numeric(df[col], errors="coerce")
        .dropna()
        .astype(np.int64)
        .unique()
        .tolist()
    )


def _add_dual_linked_synapse_layer(
    vs,
    df,
    config,
    name,
    *,
    base_root_id,
    partner_column,
    color=None,
    data_resolution=None,
    filter_by_segmentation=False,
):
    """Add a synapse annotation layer where each point links to BOTH the
    queried cell (`base_root_id`) and the per-row partner id from
    `partner_column`.

    nglui's `AnnotationLayer.add_points` only accepts a single `segment_column`,
    so we build PointAnnotation objects directly to attach two segment ids per
    annotation. Returns the new layer (or None when nothing was added).
    """
    if df is None or len(df) == 0:
        return None
    exploded = _explode_position_df(df, config.syn_pt_position_split)
    if exploded is None or len(exploded) == 0:
        return None
    pt_cols = [c for c in config.syn_pt_position_split if c in exploded.columns]
    if len(pt_cols) != 3:
        return None
    pts = exploded[pt_cols].to_numpy()

    if partner_column in exploded.columns:
        partners = pd.to_numeric(exploded[partner_column], errors="coerce")
    else:
        partners = pd.Series([np.nan] * len(exploded))

    base_seg = int(base_root_id) if base_root_id is not None else None

    annos = []
    for pt, partner in zip(pts, partners):
        seg_ids = []
        if base_seg is not None:
            seg_ids.append(base_seg)
        if pd.notna(partner):
            partner_int = int(partner)
            if partner_int != 0 and partner_int != base_seg:
                seg_ids.append(partner_int)
        annos.append(
            PointAnnotation(
                point=[float(x) for x in pt],
                segments=seg_ids if seg_ids else None,
                resolution=data_resolution,
            )
        )

    vs.add_annotation_layer(name=name, linked_segmentation="seg", color=color)
    layer = vs.get_layer(name)
    layer.add_annotations(annos)
    if filter_by_segmentation:
        layer.filter_by_segmentation = True
    return layer


def generate_statebuilder(
    info_cache,
    config,
    df=None,
    *,
    client=None,
    base_root_id=None,
    base_color="#ffffff",
    preselect_all=True,
    anno_column="post_pt_root_id",
    anno_layer="syns",
    data_resolution=[1, 1, 1],
    shorten="if_long",
):
    """Empty/overview viewer state. Returns a Neuroglancer URL.

    With df=None this produces an empty state with image + segmentation only.
    With a dataframe, points are added under `anno_layer`, and partner ids in
    `anno_column` are pre-selected on the segmentation layer.
    """
    vs = _make_viewer(info_cache, config)

    if base_root_id is not None:
        vs.add_segments(segments=[base_root_id], segment_colors={base_root_id: base_color})

    if preselect_all and df is not None:
        partner_ids = _unique_int_ids(df, anno_column)
        if partner_ids:
            vs.add_segments(segments=partner_ids)

    if df is not None and len(df) > 0:
        _add_dual_linked_synapse_layer(
            vs,
            df,
            config,
            anno_layer,
            base_root_id=base_root_id,
            partner_column=anno_column,
            data_resolution=data_resolution,
            filter_by_segmentation=True,
        )

    return _to_url(vs, info_cache, client, shorten)


def generate_statebuilder_pre(
    info_cache,
    config,
    df=None,
    *,
    client=None,
    data_resolution=[1, 1, 1],
    shorten="if_long",
):
    """Output (pre→) synapses on a single root_id. Returns a Neuroglancer URL."""
    vs = _make_viewer(info_cache, config)

    rid = root_id(info_cache)
    if rid is not None:
        vs.add_segments(segments=[rid], segment_colors={rid: "#ffffff"})

    if df is not None and len(df) > 0:
        _add_dual_linked_synapse_layer(
            vs,
            df,
            config,
            "output_syns",
            base_root_id=rid,
            partner_column=config.root_id_col,
            data_resolution=data_resolution,
        )

    return _to_url(vs, info_cache, client, shorten)


def generate_statebuilder_post(
    info_cache,
    config,
    df=None,
    *,
    client=None,
    data_resolution=[1, 1, 1],
    shorten="if_long",
):
    """Input (post→) synapses on a single root_id. Returns a Neuroglancer URL."""
    vs = _make_viewer(info_cache, config)

    rid = root_id(info_cache)
    if rid is not None:
        vs.add_segments(segments=[rid], segment_colors={rid: "#ffffff"})

    if df is not None and len(df) > 0:
        _add_dual_linked_synapse_layer(
            vs,
            df,
            config,
            "input_syns",
            base_root_id=rid,
            partner_column=config.root_id_col,
            data_resolution=data_resolution,
        )

    return _to_url(vs, info_cache, client, shorten)


def generate_statebuider_syn_grouped(
    info_cache,
    anno_name,
    config,
    df=None,
    *,
    client=None,
    fixed_id_color="#FFFFFF",
    preselect=False,
    data_resolution=[1, 1, 1],
    shorten="if_long",
):
    """Synapses to/from selected partners. Returns a Neuroglancer URL.

    The 3.x UI-grouping (`collapse_groups`, `group_column`) has no spelunker
    equivalent; per-row segment links via `segment_column` are preserved.
    """
    vs = _make_viewer(info_cache, config)

    rid = root_id(info_cache)
    if rid is not None:
        vs.add_segments(segments=[rid], segment_colors={rid: fixed_id_color})

    if preselect and df is not None:
        partner_ids = _unique_int_ids(df, config.root_id_col)
        if partner_ids:
            vs.add_segments(segments=partner_ids)

    if df is not None and len(df) > 0:
        _add_dual_linked_synapse_layer(
            vs,
            df,
            config,
            anno_name,
            base_root_id=rid,
            partner_column=config.root_id_col,
            data_resolution=data_resolution,
            filter_by_segmentation=True,
        )

    return _to_url(vs, info_cache, client, shorten)


def generate_url_cell_types(
    selected_rows,
    df,
    info_cache,
    config,
    pt_column,
    *,
    client=None,
    cell_type_column="cell_type",
    group_annotations=False,
    multipoint=False,
    fill_null=None,
    return_as="url",
    data_resolution=[1, 1, 1],
    shorten="if_long",
):
    """Cell-type table → Neuroglancer URL (or state dict if return_as='dict').

    With group_annotations=True, produces one colored annotation layer per
    unique cell_type value (tab20 palette). Otherwise a single layer with
    cell_type as the description column.
    """
    if df is None:
        df = pd.DataFrame()

    if selected_rows is not None and len(selected_rows) > 0:
        df = df.iloc[selected_rows].reset_index(drop=True)

    vs = _make_viewer(info_cache, config)

    pt_position = bound_pt_position(pt_column)
    pt_split = [f"{pt_position}_{s}" for s in ("x", "y", "z")]

    use_ct_col = cell_type_column if cell_type_column else None
    if use_ct_col == "":
        use_ct_col = None

    if group_annotations and use_ct_col and use_ct_col in df.columns:
        if fill_null is not None:
            df = df.copy()
            if str(df[use_ct_col].dtype) == "category":
                if fill_null not in df[use_ct_col].cat.categories:
                    df[use_ct_col] = df[use_ct_col].cat.add_categories(fill_null)
            df[use_ct_col] = df[use_ct_col].fillna(fill_null)

        cell_types = np.sort(pd.unique(df[use_ct_col].dropna()))
        colors = color_palette("tab20").as_hex()
        for ct, clr in zip(cell_types, cycle(colors)):
            sub = df[df[use_ct_col] == ct]
            if multipoint:
                sub = _explode_position_df(sub, pt_split)
            if len(sub) == 0:
                continue
            vs.add_points(
                data=sub,
                name=str(ct),
                point_column=pt_position,
                segment_column=config.root_id_col,
                linked_segmentation="seg",
                color=clr,
                data_resolution=data_resolution,
            )
    else:
        sub = df
        if multipoint and len(sub) > 0:
            sub = _explode_position_df(sub, pt_split)
        if len(sub) > 0:
            description_col = use_ct_col if use_ct_col in sub.columns else None
            vs.add_points(
                data=sub,
                name="Annotations",
                point_column=pt_position,
                segment_column=config.root_id_col,
                linked_segmentation="seg",
                description_column=description_col,
                data_resolution=data_resolution,
            )

    if return_as == "dict":
        return vs.to_dict()
    if return_as == "url":
        return _to_url(vs, info_cache, client, shorten)
    raise ValueError(f"Unsupported return_as: {return_as!r}")


def generate_statebuilder_syn_cell_types(
    info_cache,
    rows,
    config,
    *,
    client=None,
    cell_type_column="cell_type",
    group_annotations=True,
    multipoint=False,
    fill_null=None,
    data_resolution=[1, 1, 1],
    include_no_type=True,
    shorten="if_long",
):
    """Synapses colored by partner cell type. Returns a Neuroglancer URL."""
    df = rehydrate_dataframe(rows, config.syn_pt_position_split)
    if fill_null and include_no_type and cell_type_column in df.columns:
        df = df.copy()
        df[cell_type_column] = df[cell_type_column].fillna(fill_null)

    cell_types = np.sort(pd.unique(df[cell_type_column].dropna())) if cell_type_column in df.columns else np.array([])

    vs = _make_viewer(info_cache, config)

    rid = info_cache.get("root_id") if info_cache else None
    rid_int = int(rid) if rid is not None else None
    if rid_int is not None:
        vs.add_segments(segments=[rid_int], segment_colors={rid_int: "#ffffff"})

    colors = color_palette("tab20").as_hex()
    for ct, clr in zip(cell_types, cycle(colors)):
        sub = df[df[cell_type_column] == ct]
        if len(sub) == 0:
            continue
        _add_dual_linked_synapse_layer(
            vs,
            sub,
            config,
            str(ct),
            base_root_id=rid_int,
            partner_column=config.root_id_col,
            color=clr,
            data_resolution=data_resolution,
        )

    return _to_url(vs, info_cache, client, shorten)
