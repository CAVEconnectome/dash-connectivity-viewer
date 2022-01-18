from logging import info
from nglui import statebuilder
import pandas as pd
import numpy as np
from seaborn import color_palette
from itertools import cycle
from .lookup_utilities import make_client
from .config import (
    root_id_col,
    syn_pt_position_col,
    bound_pt_root_id,
    bound_pt_position,
)

EMPTY_INFO_CACHE = {"aligned_volume": {}}
MAX_URL_LENGTH = 1_750_000


def image_source(info_cache):
    return info_cache["aligned_volume"].get("image_source", "")


def seg_source(info_cache):
    return info_cache.get("segmentation_source", "")


def viewer_site(info_cache):
    return info_cache.get("viewer_site", "")


def state_server(info_cache):
    return f"{info_cache.get('global_server', '')}/nglstate/api/v1/post"


def root_id(info_cache):
    return int(info_cache.get("root_id", None))


def timestamp(info_cache):
    return info_cache.get("ngl_timestamp", None)


def voxel_resolution_from_info(info_cache):
    try:
        vr = [
            int(info_cache.get("viewer_resolution_x")),
            int(info_cache.get("viewer_resolution_y")),
            int(info_cache.get("viewer_resolution_z")),
        ]
        return vr
    except:
        return None


def statebuilder_kwargs(info_cache):
    return dict(
        url_prefix=viewer_site(info_cache),
        state_server=state_server(info_cache),
        resolution=voxel_resolution_from_info(info_cache),
    )


def generate_statebuilder(
    info_cache,
    base_root_id=None,
    base_color="#ffffff",
    preselect_all=True,
    anno_column="post_pt_root_id",
    anno_layer="syns",
    data_resolution=None,
):
    img = statebuilder.ImageLayerConfig(
        image_source(info_cache), contrast_controls=True, black=0.35, white=0.65
    )
    if preselect_all:
        selected_ids_column = [anno_column]
    else:
        selected_ids_column = None
    if base_root_id is None:
        base_root_id = []
        base_color = [None]
    else:
        base_root_id = [base_root_id]
        base_color = [base_color]

    seg = statebuilder.SegmentationLayerConfig(
        seg_source(info_cache),
        selected_ids_column=selected_ids_column,
        fixed_ids=base_root_id,
        fixed_id_colors=base_color,
        alpha_3d=0.8,
        timestamp=timestamp(info_cache),
    )

    points = statebuilder.PointMapper(
        bound_pt_position(syn_pt_position_col),
        linked_segmentation_column=anno_column,
        group_column=anno_column,
        multipoint=True,
        set_position=True,
    )
    anno = statebuilder.AnnotationLayerConfig(
        anno_layer,
        mapping_rules=points,
        linked_segmentation_layer=seg.name,
        filter_by_segmentation=True,
        data_resolution=data_resolution,
    )

    sb = statebuilder.StateBuilder(
        [img, seg, anno],
        **statebuilder_kwargs(info_cache),
    )
    return sb


def generate_statebuilder_pre(info_cache, preselect=False, data_resolution=None):

    img = statebuilder.ImageLayerConfig(
        image_source(info_cache),
        contrast_controls=True,
        black=0.35,
        white=0.65,
    )
    seg = statebuilder.SegmentationLayerConfig(
        seg_source(info_cache),
        fixed_ids=[root_id(info_cache)],
        fixed_id_colors=["#ffffff"],
        alpha_3d=0.8,
        timestamp=timestamp(info_cache),
    )
    points = statebuilder.PointMapper(
        bound_pt_position(syn_pt_position_col),
        linked_segmentation_column=root_id_col,
        set_position=True,
        multipoint=True,
    )
    anno = statebuilder.AnnotationLayerConfig(
        "output_syns",
        mapping_rules=points,
        linked_segmentation_layer=seg.name,
        data_resolution=data_resolution,
    )
    sb = statebuilder.StateBuilder(
        [img, seg, anno],
        **statebuilder_kwargs(info_cache),
    )
    return sb


def generate_statebuilder_post(info_cache, data_resolution=None):
    img = statebuilder.ImageLayerConfig(
        image_source(info_cache), contrast_controls=True, black=0.35, white=0.65
    )

    seg = statebuilder.SegmentationLayerConfig(
        seg_source(info_cache),
        fixed_ids=[root_id(info_cache)],
        fixed_id_colors=["#ffffff"],
        alpha_3d=0.8,
        timestamp=timestamp(info_cache),
    )
    points = statebuilder.PointMapper(
        bound_pt_position(syn_pt_position_col),
        linked_segmentation_column=root_id_col,
        set_position=True,
        multipoint=True,
    )
    anno = statebuilder.AnnotationLayerConfig(
        "input_syns",
        mapping_rules=points,
        linked_segmentation_layer=seg.name,
        data_resolution=data_resolution,
    )
    sb = statebuilder.StateBuilder(
        [img, seg, anno],
        **statebuilder_kwargs(info_cache),
    )
    return sb


def generate_statebuider_syn_grouped(
    info_cache,
    anno_name,
    fixed_id_color="#FFFFFF",
    preselect=False,
    data_resolution=None,
):
    points = statebuilder.PointMapper(
        point_column=bound_pt_position(syn_pt_position_col),
        linked_segmentation_column=root_id_col,
        group_column=root_id_col,
        multipoint=True,
        set_position=True,
    )

    img = statebuilder.ImageLayerConfig(
        image_source(info_cache),
        contrast_controls=True,
        black=0.35,
        white=0.65,
    )

    if preselect:
        selected_ids_column = root_id_col
    else:
        selected_ids_column = None

    seg = statebuilder.SegmentationLayerConfig(
        seg_source(info_cache),
        fixed_ids=[root_id(info_cache)],
        fixed_id_colors=[fixed_id_color],
        selected_ids_column=selected_ids_column,
        alpha_3d=0.8,
        timestamp=timestamp(info_cache),
    )

    anno = statebuilder.AnnotationLayerConfig(
        anno_name,
        mapping_rules=points,
        linked_segmentation_layer=seg.name,
        filter_by_segmentation=True,
        data_resolution=data_resolution,
    )

    sb = statebuilder.StateBuilder(
        [img, seg, anno],
        **statebuilder_kwargs(info_cache),
    )

    return sb


def generate_url_cell_types(
    selected_rows,
    df,
    info_cache,
    position_column="pt_position",
    multipoint=False,
    fill_null=None,
    return_as="url",
    data_resolution=None,
):
    if len(selected_rows) > 0 or selected_rows is None:
        df = df.iloc[selected_rows].reset_index(drop=True)
    if fill_null:
        df["cell_type"].cat.add_categories(fill_null, inplace=True)
        df["cell_type"].fillna(fill_null, inplace=True)

    cell_types = pd.unique(df["cell_type"].dropna())
    img = statebuilder.ImageLayerConfig(
        image_source(info_cache), contrast_controls=True, black=0.35, white=0.65
    )
    seg = statebuilder.SegmentationLayerConfig(
        seg_source(info_cache),
        alpha_3d=0.8,
        timestamp=timestamp(info_cache),
    )
    sbs = [
        statebuilder.StateBuilder(
            [img, seg],
            **statebuilder_kwargs(info_cache),
        )
    ]
    dfs = [None]
    colors = color_palette("tab20").as_hex()
    for ct, clr in zip(cell_types, cycle(colors)):
        anno = statebuilder.AnnotationLayerConfig(
            ct,
            color=clr,
            linked_segmentation_layer=seg.name,
            mapping_rules=statebuilder.PointMapper(
                position_column,
                linked_segmentation_column="pt_root_id",
                set_position=True,
                multipoint=multipoint,
                data_resolution=data_resolution,
            ),
        )
        sbs.append(
            statebuilder.StateBuilder(
                [anno],
                **statebuilder_kwargs(info_cache),
            )
        )
        dfs.append(df.query("cell_type == @ct"))
    csb = statebuilder.ChainedStateBuilder(sbs)
    return csb.render_state(dfs, return_as=return_as)


def generate_statebuilder_syn_cell_types(
    info_cache,
    rows,
    cell_type_column="cell_type",
    position_column=syn_pt_position_col,
    multipoint=False,
    fill_null=None,
    data_resolution=None,
):
    df = pd.DataFrame(rows)
    if fill_null:
        df[cell_type_column].fillna(fill_null, inplace=True)

    cell_types = pd.unique(df[cell_type_column].dropna())
    img = statebuilder.ImageLayerConfig(
        image_source(info_cache), contrast_controls=True, black=0.35, white=0.65
    )
    seg = statebuilder.SegmentationLayerConfig(
        seg_source(info_cache),
        alpha_3d=0.8,
        fixed_ids=[int(info_cache["root_id"])],
        timestamp=timestamp(info_cache),
    )
    sbs = [
        statebuilder.StateBuilder(
            [img, seg],
            **statebuilder_kwargs(info_cache),
        )
    ]
    dfs = [None]
    colors = color_palette("tab20").as_hex()
    for ct, clr in zip(cell_types, cycle(colors)):
        anno = statebuilder.AnnotationLayerConfig(
            ct,
            color=clr,
            linked_segmentation_layer=seg.name,
            mapping_rules=statebuilder.PointMapper(
                bound_pt_position(position_column),
                linked_segmentation_column=root_id_col,
                set_position=True,
                multipoint=multipoint,
            ),
            data_resolution=data_resolution,
        )
        sbs.append(
            statebuilder.StateBuilder(
                [anno],
                **statebuilder_kwargs(info_cache),
            )
        )
        dfs.append(df.query(f"{cell_type_column} == @ct"))
    csb = statebuilder.ChainedStateBuilder(sbs)
    return csb, dfs


def make_url_robust(df, sb, datastack, config):
    """Generate a url from a neuroglancer state. If too long, return through state server"""
    url = sb.render_state(df, return_as="url")
    if len(url) > MAX_URL_LENGTH:
        client = make_client(datastack, config)
        state = sb.render_state(df, return_as="dict")
        state_id = client.state.upload_state_json(state)
        url = client.state.build_neuroglancer_url(state_id)
    return url
