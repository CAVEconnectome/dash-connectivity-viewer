"""Spatial features for connectivity bundles.

Two families of columns, both gated on a configured `spatial.transform`:

  **Partner-intrinsic** (one value per partner; same for both directions):
  - `soma_depth`              µm — partner's soma depth in the oriented frame
  - `soma_x`, `soma_z`        µm — partner's soma tangential coordinates
                                   (axes 0 and 2 of the transform output —
                                   the cortex-flat plane orthogonal to depth).
                                   Lets the SPA scatter `soma_x` vs `soma_z`
                                   to render the partner population as a
                                   top-down view of cortical layout.
  - `radial_dist_root_soma`   µm — distance from partner soma to root soma
                                   along the streamline-corrected tangential
                                   plane.

  **Per-direction (synapse-edge)** (one value per partner per direction;
  unified-tab splits these into `_in` / `_out` next to `num_syn`):
  - `median_dist_to_target_soma`
                              µm — median 3D distance from each connecting
                                   synapse to the *target* (postsynaptic) soma.
                                   Plain Euclidean, no transform required.
  - `median_syn_depth`        µm — median depth of the connecting synapses
                                   in the oriented frame. Requires transform.
                                   Useful for "where on the dendrite does this
                                   partner contact" — values cluster near the
                                   target soma's depth when synapses are
                                   somatic / proximal, drift toward layer
                                   boundaries for distal contacts.

Coverage rules for the per-direction columns:

  - `median_dist_to_target_soma`
      outputs: target = partner; needs partner soma.
      inputs:  target = root;   needs root soma; partner soma optional.
  - `median_syn_depth`
      Both directions: only needs synapse positions and a transform. The
      partner's soma isn't relevant — we're reporting where the synapses
      themselves sit in cortical depth.

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
        # `transformed[i]` is `[tangential_a, depth, tangential_b]` in µm
        # (the standard_transform output is already in micrometers; the
        # `_nm` suffix on the loader names refers to the *input* unit).
        # Naming the tangential axes `soma_x` / `soma_z` mirrors the array
        # indices (0 and 2) and is short enough to read in chip / picker
        # labels. Together with `soma_depth` they give a full 3-tuple.
        rec: dict[str, float] = {
            "soma_depth": float(transformed[i, _DEPTH_AXIS]),
            "soma_x": float(transformed[i, _TANGENTIAL_AXES[0]]),
            "soma_z": float(transformed[i, _TANGENTIAL_AXES[1]]),
        }
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


def compute_synapse_depth_profile(
    *,
    transform,
    syn_df_in: pd.DataFrame | None,
    syn_df_out: pd.DataFrame | None,
    syn_position_prefix: str,
    depth_range: list[float] | None = None,
    layer_boundaries: list[float] | None = None,
    layer_names: list[str] | None = None,
    n_bins: int = 40,
) -> dict | None:
    """Per-direction histogram of synapse depths in the oriented frame.

    Used by the SPA's "Synapse depth profile" summary panel — a top-level
    figure answering "where in cortex does this neuron collect inputs and
    deposit outputs?" as a two-color (input + output) histogram. The
    computation rides on the same transform + synapse positions that
    drive the per-partner spatial features, so the marginal cost over the
    rest of the bundle is tiny.

    Returns `None` when `transform` is None — depth has no axis to project
    onto without an oriented frame, so we don't fabricate one.

    Bins span `depth_range` when provided (datastack-configured), so
    different neurons of the same datastack share a coordinate system and
    histograms are visually comparable. Without `depth_range` the bins
    span the observed min/max across both directions — still self-
    consistent within a single chart but not comparable across neurons.

    Output:
        {
            "bin_edges":  [float * (n_bins + 1)],
            "counts_in":  [int * n_bins],   # synapses on root's dendrite
            "counts_out": [int * n_bins],   # synapses on partner dendrites
            "depth_axis_name": "soma_depth",
        }
    `counts_in` / `counts_out` are zero-arrays when the corresponding
    `syn_df` is None or has no usable position columns — caller doesn't
    have to special-case the directionless setup.
    """
    if transform is None:
        return None

    pos_cols = [f"{syn_position_prefix}_position_{a}" for a in ("x", "y", "z")]

    def _depths(syn_df: pd.DataFrame | None) -> np.ndarray:
        if syn_df is None or syn_df.empty:
            return np.empty(0, dtype=float)
        if any(c not in syn_df.columns for c in pos_cols):
            return np.empty(0, dtype=float)
        pts = syn_df[pos_cols].to_numpy(dtype=float)
        return _apply_transform(transform, pts)[:, _DEPTH_AXIS]

    depths_in = _depths(syn_df_in)
    depths_out = _depths(syn_df_out)
    if depths_in.size == 0 and depths_out.size == 0:
        return None

    if depth_range and len(depth_range) == 2:
        lo, hi = float(depth_range[0]), float(depth_range[1])
    else:
        # Combined extent across both directions so the two histograms
        # share an x-axis. `np.concatenate` over an empty side is fine.
        combined = np.concatenate(
            [depths_in if depths_in.size else np.empty(0),
             depths_out if depths_out.size else np.empty(0)]
        )
        lo, hi = float(combined.min()), float(combined.max())
        if hi <= lo:  # degenerate single-depth case — pad ±1 µm so np.histogram is happy
            lo, hi = lo - 1.0, hi + 1.0

    edges = np.linspace(lo, hi, n_bins + 1)
    counts_in, _ = np.histogram(depths_in, bins=edges) if depths_in.size else (np.zeros(n_bins, dtype=int), edges)
    counts_out, _ = np.histogram(depths_out, bins=edges) if depths_out.size else (np.zeros(n_bins, dtype=int), edges)
    # Echo the depth-range / layer config alongside the counts so the SPA
    # can draw layer guides client-side without a second fetch. None
    # values pass through cleanly — frontend treats absent fields as
    # "no guides," same default behaviour as elsewhere.
    return {
        "bin_edges": edges.tolist(),
        "counts_in": counts_in.astype(int).tolist(),
        "counts_out": counts_out.astype(int).tolist(),
        # Display label for the depth axis on the SPA-rendered chart.
        # Reads more accurately as "Synapse depth" than `soma_depth` —
        # these *are* synapse positions in the oriented frame, not soma
        # positions, even though they share the same coordinate system.
        "depth_axis_name": "Synapse depth",
        "depth_range": [lo, hi] if depth_range else None,
        "layer_boundaries": list(layer_boundaries) if layer_boundaries else None,
        "layer_names": list(layer_names) if layer_names else None,
    }


def compute_median_syn_depth(
    syn_df: pd.DataFrame,
    *,
    transform,
    partner_root_id_column: str,
    syn_position_prefix: str,
) -> dict[int, float]:
    """Per partner, median synapse depth in the oriented (cortical) frame.

    Each connecting synapse's position is run through the cortical transform
    so axis 1 reads as depth-from-pia, then we median that axis per partner.
    Result is in µm (the transform's output unit), matching `soma_depth`.

    Returns `{partner_id: median_depth}`. Partners with no synapses in
    `syn_df` (after the per-direction filter) are simply absent from the
    result; their cell renders null. Empty / missing-position-column input
    short-circuits to an empty dict so callers can compose cleanly.
    """
    if syn_df.empty or transform is None:
        return {}
    pos_cols = [f"{syn_position_prefix}_position_{a}" for a in ("x", "y", "z")]
    if any(c not in syn_df.columns for c in pos_cols):
        return {}

    out: dict[int, float] = {}
    for partner_id, group in syn_df.groupby(partner_root_id_column, sort=False):
        rid = int(partner_id)
        pts = group[pos_cols].to_numpy(dtype=float)
        transformed = _apply_transform(transform, pts)
        out[rid] = float(np.median(transformed[:, _DEPTH_AXIS]))
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
    dict[int, dict[str, float]],   # intrinsic features (soma_depth, soma_x, soma_z, radial_dist)
    dict[int, float],              # in-direction median syn distance to target soma
    dict[int, float],              # out-direction median syn distance to target soma
    dict[int, float],              # in-direction median syn depth (oriented)
    dict[int, float],              # out-direction median syn depth (oriented)
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
    syn_depth_in: dict[int, float] = {}
    syn_depth_out: dict[int, float] = {}
    if transform is not None:
        intrinsic = compute_partner_spatial(
            transform,
            streamline=streamline,
            root_soma_position_nm=root_soma_position_nm,
            partner_soma_positions=partner_soma_positions,
        )
        # Per-direction synapse-depth median. Only the synapse positions
        # are needed (no partner-soma dependency), so this populates for
        # every partner with synapses regardless of `num_soma`.
        if syn_df_in is not None:
            syn_depth_in = compute_median_syn_depth(
                syn_df_in,
                transform=transform,
                partner_root_id_column="pre_pt_root_id",
                syn_position_prefix=syn_position_prefix,
            )
        if syn_df_out is not None:
            syn_depth_out = compute_median_syn_depth(
                syn_df_out,
                transform=transform,
                partner_root_id_column="post_pt_root_id",
                syn_position_prefix=syn_position_prefix,
            )

    return intrinsic, median_in, median_out, syn_depth_in, syn_depth_out
