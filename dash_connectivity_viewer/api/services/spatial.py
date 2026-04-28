"""Spatial features for connectivity bundles.

Computes three per-partner columns when the datastack has a configured
`spatial.transform`:

  - `soma_depth`              µm — depth of partner's soma in the oriented frame
  - `radial_dist_root_soma`   µm — distance from partner soma to root soma along
                                   the streamline-corrected tangential plane
  - `median_dist_to_target_soma`
                              µm — median 3D distance from each connecting
                                   synapse to the *target* (postsynaptic) soma:
                                   the partner's soma for outputs, the root's
                                   soma for inputs. Each synapse's "target" is
                                   whichever side owns the receiving dendrite.

`soma_depth` and `radial_dist_root_soma` are partner-intrinsic and require
the partner to have an unambiguous soma (`num_soma == 1`).

`median_dist_to_target_soma` is per-edge and lives in the `synapse` column
group, so the SPA's Both-tab unifier splits it into `_in` / `_out` alongside
`num_syn`, `mean_size`, etc. Coverage by direction:

  - outputs: target = partner; needs partner with `num_soma == 1`
  - inputs:  target = root; populated whenever the root itself has a soma,
             regardless of the partner's `num_soma`

The transform is loaded by name from `standard_transform.datasets`; positions
are passed in nanometers (matching `desired_resolution=[1,1,1]`), so use the
`_nm` variant of the transform constructor. The companion streamline (when
the dataset publishes one) gives more accurate radial distance for partners
that span large depth ranges.
"""

from typing import Any, Callable

import numpy as np
import pandas as pd

# standard_transform's transform sequence, by `transform` name in datastack YAML.
_TRANSFORM_LOADERS: dict[str, str] = {
    "minnie_nm": "minnie_transform_nm",
    "minnie_vx": "minnie_transform_vx",
    "v1dd_nm": "v1dd_transform_nm",
    "v1dd_vx": "v1dd_transform_vx",
    "identity": "identity_transform",
}

# Companion streamlines for each transform. Each Streamline is callable on the
# *transformed* coordinate space (we pass `transform_points=False` to skip
# re-applying the transform when we've already computed it). Streamlines let
# us follow local cortical-column orientation per-depth, which is more
# accurate for radial distance across long depth ranges than just
# stripping the depth axis.
_STREAMLINE_LOADERS: dict[str, callable] = {
    "minnie_nm": lambda st: st.minnie_ds.streamline_nm,
    "minnie_vx": lambda st: st.minnie_ds.streamline_vx,
    "v1dd_nm": lambda st: st.v1dd_ds.streamline_nm,
    "v1dd_vx": lambda st: st.v1dd_ds.streamline_vx,
    "identity": lambda st: st.identity_streamline,
}


def load_transform(name: str | None):
    """Construct a standard_transform TransformSequence by short name. Returns
    None when `name` is missing/unrecognized so callers can degrade gracefully
    (no spatial columns rather than a hard failure)."""
    if not name:
        return None
    constructor = _TRANSFORM_LOADERS.get(name)
    if constructor is None:
        return None
    import standard_transform as st
    fn = getattr(st, constructor, None)
    return fn() if fn is not None else None


def load_streamline(name: str | None):
    """Look up the companion streamline for a transform name. Returns None when
    the dataset has no published streamline; callers fall back to depth-strip
    radial distance, which is correct for short depth ranges and good enough
    when the cortex curvature is mild relative to the spread of partners."""
    if not name:
        return None
    accessor = _STREAMLINE_LOADERS.get(name)
    if accessor is None:
        return None
    import standard_transform as st
    try:
        return accessor(st)
    except Exception:
        return None


def _apply_transform(transform, points: np.ndarray) -> np.ndarray:
    """Apply transform to an Nx3 array of input positions, returning Nx3 output.
    Handles the scalar case (1x3) by broadcasting through the same call."""
    if points.ndim == 1:
        return np.atleast_2d(transform.apply(points))
    return transform.apply(points)


# Output convention from standard_transform: axis 1 is depth (along the
# pia-to-white-matter axis), axes 0 and 2 are tangential. Verified empirically
# against minnie_transform_nm — a unit step in the input y direction produces
# an ~equal-magnitude unit step in output[1] with negligible cross-talk.
_DEPTH_AXIS = 1
_TANGENTIAL_AXES = (0, 2)


def compute_partner_spatial(
    transform,
    *,
    streamline=None,
    root_soma_position_nm: list[float] | None,
    partner_soma_positions: dict[int, list[float]],
) -> dict[int, dict[str, float]]:
    """Compute the partner-intrinsic spatial columns.

    Returns `{root_id: {soma_depth, radial_dist_root_soma}}` for partners that
    have a soma position. Partners without a position are simply absent from
    the dict, and the bundle assembler leaves their row's spatial cells null.

    Radial distance preference order:

    1. If `streamline` is provided, use `streamline.radial_distance(...)` —
       this projects each partner onto the cortical-column streamline that
       passes through the root soma at the partner's own depth, then takes
       the in-plane distance from there. Honors local column curvature, so
       it stays accurate when partners span large depth ranges (e.g. an L2
       root with L6 partners).
    2. Otherwise fall back to a flat depth-strip: drop axis 1 (depth) and
       take 2D Euclidean distance in axes (0, 2). This matches the streamline
       method exactly when columns are perfectly perpendicular to pia, and
       drifts a small amount when they curve. Good fallback for datastacks
       with a `transform` but no `streamline` (currently `identity` only).

    `radial_dist_root_soma` is omitted when the root itself has no clean soma
    position to compare against — the column header would be misleading
    otherwise. `soma_depth` is still produced because it's a one-sided lookup.
    """
    if transform is None or not partner_soma_positions:
        return {}

    rids = list(partner_soma_positions.keys())
    pts = np.array([partner_soma_positions[r] for r in rids], dtype=float)
    transformed = _apply_transform(transform, pts)

    radial: np.ndarray | None = None
    if root_soma_position_nm is not None:
        root_xyz = _apply_transform(transform, np.array(root_soma_position_nm, dtype=float))[0]
        if streamline is not None:
            # streamline.radial_distance: xyz0 is a single 1-D point; xyz1 is
            # an Nx3 array. We pass `transform_points=False` because we've
            # already applied the transform above — the streamline expects
            # post-transform coords on this path.
            radial = np.asarray(
                streamline.radial_distance(
                    root_xyz, transformed,
                    transform_points=False, return_angle=False,
                ),
                dtype=float,
            )
        else:
            root_tangential = root_xyz[list(_TANGENTIAL_AXES)]
            radial = np.linalg.norm(
                transformed[:, list(_TANGENTIAL_AXES)] - root_tangential,
                axis=1,
            )

    out: dict[int, dict[str, float]] = {}
    for i, rid in enumerate(rids):
        rec: dict[str, float] = {"soma_depth": float(transformed[i, _DEPTH_AXIS])}
        if radial is not None:
            rec["radial_dist_root_soma"] = float(radial[i])
        out[int(rid)] = rec
    return out


def compute_median_syn_dist(
    syn_df: pd.DataFrame,
    *,
    partner_root_id_column: str,
    syn_position_prefix: str,
    target_soma_for: Callable[[int], list[float] | None],
) -> dict[int, float]:
    """Per partner, compute the median 3D distance from each connecting
    synapse to the *target* (postsynaptic) soma.

    `target_soma_for(partner_id)` returns the soma the synapses should be
    measured against:
      - output direction → returns the partner's soma (i.e. per-partner lookup)
      - input direction  → returns the root's soma (constant, regardless of
                           partner_id; partners without their own soma still
                           get a meaningful value)

    `syn_df` already filters to one direction. `partner_root_id_column` is
    `pre_pt_root_id` for inputs or `post_pt_root_id` for outputs;
    `syn_position_prefix` is typically `ctr_pt`. Distances come back in the
    same length unit as the input positions (nm when called from the
    connectivity service); the bundle assembler converts nm → µm.
    """
    if syn_df.empty:
        return {}
    pos_cols = [f"{syn_position_prefix}_position_{a}" for a in ("x", "y", "z")]
    if any(c not in syn_df.columns for c in pos_cols):
        return {}

    out: dict[int, float] = {}
    for partner_id, group in syn_df.groupby(partner_root_id_column, sort=False):
        rid = int(partner_id)
        target = target_soma_for(rid)
        if target is None:
            continue
        pts = group[pos_cols].to_numpy(dtype=float)
        diffs = pts - np.asarray(target, dtype=float)
        dists = np.linalg.norm(diffs, axis=1)
        out[rid] = float(np.median(dists))
    return out


def attach_spatial_features(
    *,
    transform,
    streamline=None,
    decoration_lookup: dict[int, dict[str, Any]],
    root_soma_position_nm: list[float] | None,
    syn_df_in: pd.DataFrame | None,
    syn_df_out: pd.DataFrame | None,
    syn_position_prefix: str,
) -> tuple[
    dict[int, dict[str, float]],   # intrinsic features (soma_depth, radial_dist)
    dict[int, float],              # in-direction median syn dist
    dict[int, float],              # out-direction median syn dist
]:
    """Compute the spatial column families for a connectivity bundle.

    Returns three lookups keyed by partner root_id; the bundle assembler
    merges them into `partners_in` / `partners_out` records and registers
    the corresponding columns.

    Two-tier dependency:

    - `median_dist_to_target_soma` is plain 3D Euclidean distance, so it's
      computed whenever partner soma positions exist — no oriented transform
      required. Datastacks without a `spatial.transform` still get this column.
    - `soma_depth` and `radial_dist_root_soma` are meaningful only in an
      oriented frame, so they require `transform` to be non-None. Without a
      transform the intrinsic dict comes back empty and those columns are
      simply omitted from the bundle.

    Distances are converted nm → µm here so the SPA renders human-friendly
    figures (typical cortical depths ~100–1000 µm) without per-cell tricks.
    """
    # Pull soma positions out of the decoration_lookup. They were piggybacked
    # on the served records in `_fetch_num_soma_table`; here we pluck them
    # back into a clean rid → [x,y,z] map. Used by output-direction median +
    # by intrinsic depth/radial. Inputs still produce values when this is
    # empty because their target is the root, not the partner.
    partner_soma_positions: dict[int, list[float]] = {}
    for rid, rec in decoration_lookup.items():
        pt = rec.get("pt_position")
        if isinstance(pt, list) and len(pt) == 3:
            partner_soma_positions[int(rid)] = pt

    # Median synapse-to-target-soma distance. "Target" = whichever side owns
    # the receiving dendrite for that direction:
    #   - outputs: target = partner (synapse on partner's dendrite). Per-
    #     partner lookup; only populated when the partner has its own soma.
    #   - inputs:  target = root (synapse on root's dendrite). Constant
    #     across partners; populated for every input regardless of whether
    #     the partner itself has a soma. Only requires the root to have one.
    median_in: dict[int, float] = {}
    median_out: dict[int, float] = {}
    if syn_df_in is not None and root_soma_position_nm is not None:
        median_in = compute_median_syn_dist(
            syn_df_in,
            partner_root_id_column="pre_pt_root_id",
            syn_position_prefix=syn_position_prefix,
            target_soma_for=lambda _pid, _root=root_soma_position_nm: _root,
        )
    if syn_df_out is not None:
        median_out = compute_median_syn_dist(
            syn_df_out,
            partner_root_id_column="post_pt_root_id",
            syn_position_prefix=syn_position_prefix,
            target_soma_for=lambda pid, _lookup=partner_soma_positions: _lookup.get(pid),
        )
    NM_PER_UM = 1000.0
    median_in = {rid: v / NM_PER_UM for rid, v in median_in.items()}
    median_out = {rid: v / NM_PER_UM for rid, v in median_out.items()}

    # Oriented-frame features — only when the datastack has a configured
    # standard_transform. Without it, depth has no axis to project onto and
    # "radial" has no plane to live in, so we can't fabricate values. The
    # streamline (when present) makes radial distance follow local column
    # curvature; without it we fall back to a flat depth-strip.
    intrinsic: dict[int, dict[str, float]] = {}
    if transform is not None:
        intrinsic = compute_partner_spatial(
            transform,
            streamline=streamline,
            root_soma_position_nm=root_soma_position_nm,
            partner_soma_positions=partner_soma_positions,
        )

    return intrinsic, median_in, median_out
