from logging import info
from nglui import statebuilder
import pandas as pd
import numpy as np
from seaborn import color_palette
from itertools import cycle
from .lookup_utilities import make_client
from .schema_utils import bound_pt_position, bound_pt_root_id
from .dataframe_utilities import rehydrate_dataframe

EMPTY_INFO_CACHE = {"aligned_volume": {}, "cell_type_column": None}
MAX_URL_LENGTH = 1_750_000
DEFAULT_NGL = "https://neuromancer-seung-import.appspot.com/"


def image_source(info_cache):
    if info_cache is None:
        return None
    return info_cache["aligned_volume"].get("image_source", "")

def aligned_volume(info_cache):
    if info_cache is None:
        return None
    return info_cache.get('aligned_volume', {}).get('name')

def seg_source(info_cache):
    if info_cache is None:
        return None
    return info_cache.get("segmentation_source", "")


def viewer_site(info_cache):
    if info_cache is None:
        return None
    return info_cache.get("viewer_site", "")


def state_server(info_cache):
    if info_cache is None:
        return None
    return f"{info_cache.get('global_server', '')}/nglstate/api/v1/post"


def root_id(info_cache):
    if info_cache is None:
        return None
    return int(info_cache.get("root_id", None))


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
    config,
    base_root_id=None,
    base_color="#ffffff",
    preselect_all=True,
    anno_column="post_pt_root_id",
    anno_layer="syns",
    data_resolution=[1,1,1],
):
    img = statebuilder.ImageLayerConfig(
        image_source(info_cache),
        contrast_controls=True,
        black=config.image_black,
        white=config.image_white,
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
        config.syn_pt_position,
        linked_segmentation_column=anno_column,
        group_column=anno_column,
        multipoint=True,
        set_position=True,
        collapse_groups=True,
        split_positions=True,
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


def generate_statebuilder_pre(
    info_cache, config, preselect=False, data_resolution=[1,1,1],
):

    img = statebuilder.ImageLayerConfig(
        image_source(info_cache),
        contrast_controls=True,
        black=config.image_black,
        white=config.image_white,
    )
    seg = statebuilder.SegmentationLayerConfig(
        seg_source(info_cache),
        fixed_ids=[root_id(info_cache)],
        fixed_id_colors=["#ffffff"],
        alpha_3d=0.8,
        timestamp=timestamp(info_cache),
    )
    points = statebuilder.PointMapper(
        config.syn_pt_position,
        linked_segmentation_column=config.root_id_col,
        set_position=True,
        multipoint=True,
        split_positions=True,
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


def generate_statebuilder_post(info_cache, config, data_resolution=[1,1,1]):
    img = statebuilder.ImageLayerConfig(
        image_source(info_cache),
        contrast_controls=True,
        black=config.image_black,
        white=config.image_white,
    )

    seg = statebuilder.SegmentationLayerConfig(
        seg_source(info_cache),
        fixed_ids=[root_id(info_cache)],
        fixed_id_colors=["#ffffff"],
        alpha_3d=0.8,
        timestamp=timestamp(info_cache),
    )
    points = statebuilder.PointMapper(
        config.syn_pt_position,
        linked_segmentation_column=config.root_id_col,
        set_position=True,
        split_positions=True,
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
    config,
    fixed_id_color="#FFFFFF",
    preselect=False,
    data_resolution=[1,1,1],
):
    points = statebuilder.PointMapper(
        point_column=config.syn_pt_position,
        linked_segmentation_column=config.root_id_col,
        group_column=config.root_id_col,
        split_positions=True,
        multipoint=True,
        set_position=True,
        collapse_groups=True,
    )

    img = statebuilder.ImageLayerConfig(
        image_source(info_cache),
        contrast_controls=True,
        black=config.image_black,
        white=config.image_white,
    )

    if preselect:
        selected_ids_column = config.root_id_col
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
    config,
    pt_column,
    cell_type_column='cell_type',
    group_annotations=False,
    multipoint=False,
    fill_null=None,
    return_as="url",
    data_resolution=[1,1,1],
):
    
    if len(selected_rows) > 0 or selected_rows is None:
        df = df.iloc[selected_rows].reset_index(drop=True)

    img = statebuilder.ImageLayerConfig(
        image_source(info_cache),
        contrast_controls=True,
        black=config.image_black,
        white=config.image_white,
    )
    seg = statebuilder.SegmentationLayerConfig(
        seg_source(info_cache),
        alpha_3d=0.8,
        timestamp=timestamp(info_cache),
    )
    # sbs = [
    #     statebuilder.StateBuilder(
    #         [img, seg],
    #         **statebuilder_kwargs(info_cache),
    #     )
    # ]
    annos = []
    if group_annotations:
        if fill_null:
            df[cell_type_column].cat.add_categories(fill_null, inplace=True)
            df[cell_type_column].fillna(fill_null, inplace=True)
        cell_types = np.sort(pd.unique(df[cell_type_column].dropna()))
        colors = color_palette("tab20").as_hex()

        for ct, clr in zip(cell_types, cycle(colors)):
            annos.append(
                statebuilder.AnnotationLayerConfig(
                    ct,
                    color=clr,
                    linked_segmentation_layer=seg.name,
                    data_resolution=data_resolution,
                    mapping_rules=statebuilder.PointMapper(
                        bound_pt_position(pt_column),
                        linked_segmentation_column=config.root_id_col,
                        set_position=True,
                        multipoint=multipoint,
                        split_positions=True,
                        mapping_set=ct,
                    )
                )
            )
        sb = statebuilder.StateBuilder([img, seg] + annos, **statebuilder_kwargs(info_cache))
        return sb.render_state(
            {ct: df.query(f"{cell_type_column}==@ct") for ct in cell_types},
            return_as=return_as,
        )
    else:
        if cell_type_column is not None:
            if len(cell_type_column)==0:
                cell_type_column=None
        anno = statebuilder.AnnotationLayerConfig(
            'Annotations',
            linked_segmentation_layer=seg.name,
            mapping_rules=statebuilder.PointMapper(
                bound_pt_position(pt_column),
                linked_segmentation_column=config.root_id_col,
                split_positions=True,
                multipoint=multipoint,
                set_position=True,
                description_column=cell_type_column,
            ),
            data_resolution=data_resolution,
        )
        sb = statebuilder.StateBuilder([img, seg, anno], **statebuilder_kwargs(info_cache))
        return sb.render_state(
            df,
            return_as=return_as,
        )

    # for ct, clr in zip(cell_types, cycle(colors)):
    #     anno = statebuilder.AnnotationLayerConfig(
    #         ct,
    #         color=clr,
    #         linked_segmentation_layer=seg.name,
    #         mapping_rules=statebuilder.PointMapper(
    #             bound_pt_position(pt_column),
    #             linked_segmentation_column=config.root_id_col,
    #             set_position=True,
    #             multipoint=multipoint,
    #             split_positions=True,
    #         ),
    #         data_resolution=data_resolution,
    #     )
    #     sbs.append(
    #         statebuilder.StateBuilder(
    #             [anno],
    #             **statebuilder_kwargs(info_cache),
    #         )
    #     )
    #     dfs.append(df.query("cell_type == @ct"))
    # csb = statebuilder.ChainedStateBuilder(sbs)
    # return csb.render_state(dfs, return_as=return_as)


def generate_statebuilder_syn_cell_types(
    info_cache,
    rows,
    config,
    cell_type_column="cell_type",
    group_annotations=True,
    multipoint=False,
    fill_null=None,
    data_resolution=[1,1,1],
    include_no_type=True,
):
    df = rehydrate_dataframe(rows, config.syn_pt_position_split)
    if fill_null and include_no_type:
        df[cell_type_column].fillna(fill_null, inplace=True)

    cell_types = np.sort(pd.unique(df[cell_type_column].dropna()))
    img = statebuilder.ImageLayerConfig(
        image_source(info_cache),
        contrast_controls=True,
        black=config.image_black,
        white=config.image_white,
    )
    seg = statebuilder.SegmentationLayerConfig(
        seg_source(info_cache),
        alpha_3d=0.8,
        fixed_ids=[int(info_cache["root_id"])],
        timestamp=timestamp(info_cache),
    )

    # sbs = [
    #     statebuilder.StateBuilder(
    #         [img, seg],
    #         **statebuilder_kwargs(info_cache),
    #     )
    # ]
    colors = color_palette("tab20").as_hex()
    annos = []
    for ct, clr in zip(cell_types, cycle(colors)):
        anno = statebuilder.AnnotationLayerConfig(
            ct,
            color=clr,
            linked_segmentation_layer=seg.name,
            mapping_rules=statebuilder.PointMapper(
                config.syn_pt_position,
                linked_segmentation_column=config.root_id_col,
                set_position=True,
                multipoint=multipoint,
                split_positions=True,
                mapping_set=ct,
            ),
            data_resolution=data_resolution,
        )
        annos.append(anno)
            # statebuilder.StateBuilder(
                # [anno],
                # **statebuilder_kwargs(info_cache),
            # )
        # )
        # dfs.append(df.query(f"{cell_type_column} == @ct"))
    sb = statebuilder.StateBuilder([img, seg] + annos, **statebuilder_kwargs(info_cache))
    # csb = statebuilder.ChainedStateBuilder(sbs)
    df_dict = {ct: df.query(f'{cell_type_column}=="{ct}"') for ct in cell_types}
    return sb, df_dict


def make_url_robust(df, sb, datastack, config):
    """Generate a url from a neuroglancer state. If too long, return through state server"""
    url = sb.render_state(df, return_as="url")
    if len(url) > MAX_URL_LENGTH:
        client = make_client(datastack, config.server_address)
        state = sb.render_state(df, return_as="dict")
        state_id = client.state.upload_state_json(state)
        ngl_url = client.info.viewer_site()
        if ngl_url is None:
            ngl_url = DEFAULT_NGL
        url = client.state.build_neuroglancer_url(state_id, ngl_url=ngl_url)
    return url
