from pathlib import Path
from typing import Any

import yaml
from cachetools import LRUCache
from pydantic import BaseModel, Field

from flask import current_app


# Schema-level default for `SynapseConfig.columns`. Limited to fields that
# are truly universal across CAVE synapse tables: every synapse row has an
# `id`, the two partner roots, and a position column for the configured
# `position_prefix`. `size` is *common* but not guaranteed (BANC happens to
# have it; some tables don't), so it lives in aligned-volume / datastack
# YAMLs that have actually verified the table schema, not here. Aggregation
# rules referencing `size` (or any other non-default column) are also
# absent from the schema-level default for the same reason.
DEFAULT_SYNAPSE_COLUMNS = ["id", "pre_pt_root_id", "post_pt_root_id", "ctr_pt_position"]


class AggregationRule(BaseModel):
    column: str
    agg: str  # any string accepted by pandas .agg() — "mean", "sum", "max", etc.


class SpatialConfig(BaseModel):
    """Spatial transform configuration, keyed by aligned_volume.

    The aligned_volume identifies a coordinate-space and reference geometry that
    can be shared across multiple datastacks (e.g. `minnie65_public` and
    `minnie65_phase3_v1` both live in aligned_volume `minnie65_phase3`). So
    spatial config lives in `api/aligned_volumes/<aligned_volume>.yaml`, not in
    the per-datastack YAML — proofreading versions of the same volume need
    identical depth axes and layer boundaries to be visually comparable.

    `transform` names a constructor in `standard_transform.datasets`. Currently
    supported: `minnie_vx`, `minnie_nm`, `v1dd_vx`, `v1dd_nm`, `identity`.
    The `_nm` variants accept positions in nanometers (which is what the API
    serves at `desired_resolution=[1,1,1]`); `_vx` variants accept voxel
    coordinates. Choose based on what the connectivity service hands the
    spatial computation — currently `_nm`.

    Aligned volumes with no transform configured (or no YAML at all) simply
    omit the spatial columns from the connectivity bundle; the SPA renders
    without them. That's the right default for non-cortex datasets like the
    fly brain-and-nerve-cord — there's no pia-to-white-matter axis to project
    onto.

    `depth_range` and the layer-boundary fields below feed the plot
    backend's depth-axis decoration. They're only meaningful in the
    *oriented* frame, so an aligned_volume without `transform` should leave
    them null — the plot backend short-circuits guides when the frame can't
    be calibrated.

    `depth_range` (µm) fixes the depth-axis range on plots whose x or y
    is bound to a depth-shaped column, so different neurons (or the same
    neuron at different mat versions) share a coordinate system instead
    of each chart auto-fitting to its own data.

    `layer_boundaries` (µm, ordered top-to-bottom) defines the depths at
    which one cortical region ends and the next begins; N values give
    N+1 regions. Drawn as subtle dotted background lines on every
    depth-axis plot.

    `layer_names` is parallel to `layer_boundaries` — `layer_names[i]`
    labels the region whose *bottom* is `layer_boundaries[i]` (so the
    first name is the region between `depth_range[0]` and the first
    boundary). If shorter than `layer_boundaries`, the trailing regions
    are unlabeled (e.g. white matter below L6).
    """
    transform: str | None = None
    depth_range: list[float] | None = None
    layer_boundaries: list[float] | None = None
    layer_names: list[str] | None = None


class SynapseConfig(BaseModel):
    """Synapse-table column conventions.

    Layered loading:

    - aligned_volume YAML supplies the defaults — the segmentation pipeline
      typically drives these and they're shared across every datastack
      mounted on the same volume (different mat versions of the same
      proofreading effort all see the same synapse columns).
    - per-datastack YAML overrides individual fields. A datastack that
      omits the `synapse:` block entirely inherits everything; one that
      sets only `synapse: {position_prefix: foo}` inherits `columns` /
      `aggregation_rules` and overrides only the prefix.

    The override is field-by-field, so callers don't have to re-state the
    full list of columns just to change one field.

    `position_prefix` is the column-name stem for the synapse-position
    triple (`<prefix>_position_x/y/z`). Most CAVE synapse tables use
    `ctr_pt`; some pipelines use other points (anchor, post-anchor) and
    set this accordingly.

    `columns` is the column projection for synapse queries. Setting it to
    `null` (YAML `~`) pulls every column — good for ad-hoc exploration,
    bad for production because it bloats the cached DataFrame. The default
    list keeps the synapse cache compact while still carrying the columns
    needed for aggregation rules below.

    `aggregation_rules` are the per-partner summary stats run on the
    synapse DataFrame: each entry adds a column to the partner table by
    grouping synapses on partner root_id and applying `agg` to `column`.
    Common pattern: `{mean_size: {column: size, agg: mean}}` to add a
    mean-synapse-size column.
    """
    position_prefix: str = "ctr_pt"
    columns: list[str] | None = Field(default_factory=lambda: list(DEFAULT_SYNAPSE_COLUMNS))
    aggregation_rules: dict[str, AggregationRule] = Field(default_factory=dict)

    def merged_columns(self) -> list[str] | None:
        """Effective column projection, including any columns referenced by
        aggregation rules but not in the explicit `columns` list. Returns
        None when `columns` is None, which signals "select every column" to
        the synapse-query layer."""
        if self.columns is None:
            return None
        cols = list(self.columns)
        for rule in self.aggregation_rules.values():
            if rule.column not in cols:
                cols.append(rule.column)
        return cols

    def aggregation_rules_for_neuron_query(self) -> dict[str, dict]:
        """Plain-dict view of the aggregation rules for `NeuronQuery`, which
        accepts `{name: {column, agg}}` rather than the validated AggregationRule
        instances."""
        return {name: rule.model_dump() for name, rule in self.aggregation_rules.items()}


class AlignedVolumeConfig(BaseModel):
    """Per-aligned-volume configuration.

    Carries the spatial transform (the original motivation — datastacks of
    the same volume share a coordinate system) and synapse defaults
    (segmentation-pipeline-driven, also typically shared across the volume's
    datastacks). Per-datastack YAMLs can override either.

    Left as its own model so further aligned-volume-scoped settings (shared
    color palettes, default Neuroglancer image layers, etc.) can land here
    without touching every datastack YAML.
    """
    spatial: SpatialConfig = Field(default_factory=SpatialConfig)
    synapse: SynapseConfig = Field(default_factory=SynapseConfig)


class DecorationWarmup(BaseModel):
    """Periodic warming for whole-table decoration caches.

    Each registered job fetches `(datastack, latest_valid_mat_version, table)`
    on a periodic schedule. The latest version is resolved at every fire (not
    pinned at config time) so the cache rolls forward as new mat versions are
    published. Live mode is never warmed.

    `startup_delay_seconds` defers the first run after pod boot — set to a few
    minutes in autoscaling deployments so a scale-up event doesn't thunder into
    CAVE the moment new pods come up. Random jitter up to 60s is added on top.

    `enabled` must be true to register any jobs from this config; off by default
    so the dev server doesn't warm anything unless explicitly opted in.
    """
    enabled: bool = False
    cell_type_tables: list[str] = Field(default_factory=list)
    warm_soma_table: bool = False  # warms the datastack info's default soma_table
    interval_seconds: float = 3600.0
    startup_delay_seconds: float = 0.0


class DatastackConfig(BaseModel):
    # Per-datastack synapse override. Field-by-field: any field explicitly set
    # in the YAML's `synapse:` block wins over the aligned_volume's defaults;
    # fields omitted inherit. Omit the `synapse:` key entirely (or set to null)
    # to inherit everything — the common case when a datastack uses the same
    # synapse table conventions as the rest of its aligned_volume.
    synapse: SynapseConfig | None = None
    decoration_warmup: DecorationWarmup | None = None
    # Whether to expose the "live" query mode to the SPA. CAVE always *can* serve
    # live queries against any datastack, but for public datasets users effectively
    # only have the released materializations — surfacing "live" is misleading and
    # can drift from what's published. Set false for public/release datastacks.
    live_mode: bool = True

    # ---- cell-id lookup -------------------------------------------------------
    # Cell ids (typically nucleus ids) are persistent identifiers that survive
    # proofreading splits/merges; root ids are not. The forward direction
    # (cell_id → current root_id) uses a materialized view that the dataset
    # operators provide. The reverse direction (root_id → cell_id) walks one or
    # more annotation tables. Datastacks without these resources omit the keys;
    # the SPA hides the cell-id input when the config is empty.
    cell_id_lookup_view: str | None = None       # materialized view: id → pt_root_id (+ pt_supervoxel_id)
    root_id_lookup_main_table: str | None = None # primary table: pt_root_id → id
    root_id_lookup_alt_tables: list[str] = Field(default_factory=list)


# Cache stores `(cfg, signature)` so we can invalidate when a watched YAML
# changes mtime — without this, the dev workflow needs a server restart for
# every YAML edit because Flask's debug reloader only watches .py files.
_config_cache: LRUCache = LRUCache(maxsize=64)


def _yaml_signature(paths: list[Path]) -> tuple:
    """Stable mtime signature across the (possibly two) YAML sources for a
    given datastack. Files that don't exist contribute -1 so creation is
    detected too."""
    return tuple((str(p), p.stat().st_mtime) if p.is_file() else (str(p), -1.0) for p in paths)


def load_datastack_config(datastack: str) -> DatastackConfig:
    """Resolve `<datastack>.yaml`. Bundled `api/datastacks/` is always checked;
    `DCV_DATASTACK_CONFIG_DIR` is checked second and wins on conflict, letting
    operators ship deployment-specific overrides without forking the package.
    Datastacks with no YAML in either location fall back to schema defaults.

    Cached per `(bundled.yaml mtime, override.yaml mtime)`, so editing a YAML
    in dev invalidates the entry on the next request — no server restart.
    """
    bundled_dir = Path(__file__).parent.parent / "datastacks"
    extra_dir = current_app.config.get("DATASTACK_CONFIG_DIR")
    paths = [bundled_dir / f"{datastack}.yaml"]
    if extra_dir:
        paths.append(Path(extra_dir) / f"{datastack}.yaml")

    signature = _yaml_signature(paths)
    cached = _config_cache.get(datastack)
    if cached is not None and cached[1] == signature:
        return cached[0]

    cfg = DatastackConfig()
    for path in paths:
        if path.is_file():
            data: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
            cfg = DatastackConfig.model_validate(data)
    _config_cache[datastack] = (cfg, signature)
    return cfg


def clear_datastack_config_cache() -> None:
    _config_cache.clear()
    _aligned_volume_config_cache.clear()
    _aligned_volume_name_cache.clear()


# Same caching pattern as `_config_cache` — stash mtime for hot-reload in dev,
# but key by aligned_volume name (e.g. "minnie65_phase3") rather than datastack.
_aligned_volume_config_cache: LRUCache = LRUCache(maxsize=64)


def load_aligned_volume_config(aligned_volume: str | None) -> AlignedVolumeConfig:
    """Resolve `aligned_volumes/<aligned_volume>.yaml`. Same bundled+override
    pattern as `load_datastack_config`: bundled `api/aligned_volumes/` is
    checked first, `DCV_ALIGNED_VOLUME_CONFIG_DIR` second and wins on conflict.

    Aligned volumes with no YAML in either location fall back to schema
    defaults — i.e. no transform, no depth axis, no layer guides. That's the
    right behavior for any volume the deployment hasn't characterized yet
    (typical for non-cortex datasets), so callers don't have to special-case
    "is there a YAML for this volume."
    """
    if not aligned_volume:
        return AlignedVolumeConfig()

    bundled_dir = Path(__file__).parent.parent / "aligned_volumes"
    extra_dir = current_app.config.get("ALIGNED_VOLUME_CONFIG_DIR")
    paths = [bundled_dir / f"{aligned_volume}.yaml"]
    if extra_dir:
        paths.append(Path(extra_dir) / f"{aligned_volume}.yaml")

    signature = _yaml_signature(paths)
    cached = _aligned_volume_config_cache.get(aligned_volume)
    if cached is not None and cached[1] == signature:
        return cached[0]

    cfg = AlignedVolumeConfig()
    for path in paths:
        if path.is_file():
            data: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
            cfg = AlignedVolumeConfig.model_validate(data)
    _aligned_volume_config_cache[aligned_volume] = (cfg, signature)
    return cfg


# Aligned-volume name is a stable property of a datastack — never changes
# during a deployment's lifetime. Cache it process-wide rather than re-reading
# the datastack-info round-trip on every request.
_aligned_volume_name_cache: dict[str, str | None] = {}


def resolve_aligned_volume_name(datastack: str, client) -> str | None:
    """Look up the aligned_volume name for `datastack` via `client.info`.

    `client.info.get_datastack_info()` returns a dict whose `aligned_volume`
    key is itself a `{"name": "minnie65_phase3", ...}` dict — that's where
    the volume name lives. (`InfoServiceClient` has no standalone
    `get_aligned_volume()` method; calling it would silently fail back here
    and the spatial transform would never load.) Cached by datastack so
    subsequent requests skip the info-service round-trip.
    """
    if datastack in _aligned_volume_name_cache:
        return _aligned_volume_name_cache[datastack]
    try:
        info = client.info.get_datastack_info()
    except Exception:
        info = None
    name: str | None = None
    if isinstance(info, dict):
        av = info.get("aligned_volume")
        if isinstance(av, dict):
            raw = av.get("name")
            if isinstance(raw, str) and raw:
                name = raw
    _aligned_volume_name_cache[datastack] = name
    return name


def aligned_volume_config_for(datastack: str, client) -> AlignedVolumeConfig:
    """Convenience: resolve aligned_volume name and load its config in one
    call. Endpoints use this immediately after building the CAVE client,
    then read `cfg.spatial.*` for transform / depth_range / layer guides."""
    return load_aligned_volume_config(resolve_aligned_volume_name(datastack, client))


def resolve_synapse_config(
    av_cfg: AlignedVolumeConfig, ds_cfg: DatastackConfig
) -> SynapseConfig:
    """Effective synapse config = aligned_volume defaults with per-datastack
    overrides applied field-by-field.

    Datastacks that omit a `synapse:` block inherit everything from the
    aligned_volume. Datastacks that set only a subset of fields (e.g.
    `synapse: {position_prefix: anchor_pt}`) inherit the rest. The
    aligned_volume YAML is the right place to put conventions shared by
    every datastack on the volume; the per-datastack YAML carries
    exceptions.

    Pydantic's `model_fields_set` distinguishes "explicitly set" from
    "default-constructed" so a per-datastack `synapse: {columns: ~}`
    legitimately overrides to "select every column" without us mistaking
    the explicit-None for an absent field.
    """
    if ds_cfg.synapse is None:
        return av_cfg.synapse
    base = av_cfg.synapse.model_dump()
    for field in ds_cfg.synapse.model_fields_set:
        base[field] = getattr(ds_cfg.synapse, field)
    return SynapseConfig.model_validate(base)


def synapse_config_for(datastack: str, client) -> SynapseConfig:
    """Convenience: resolve aligned_volume + datastack synapse configs and
    return the merged result. Endpoints use this to drive `NeuronQuery`'s
    `synapse_position_prefix` / `synapse_columns` / aggregation arguments."""
    av_cfg = aligned_volume_config_for(datastack, client)
    ds_cfg = load_datastack_config(datastack)
    return resolve_synapse_config(av_cfg, ds_cfg)


def latest_valid_mat_version(client) -> int | None:
    """Pick the freshest valid materialization version for a datastack, or
    None when the datastack has no valid versions.

    Used by endpoints that want to substitute a "live" request with a
    real materialization — table listing / row queries fall back to this
    so the user can pick "live" in the picker and still get views and
    cached responses (live mode has neither). Failures of the upstream
    versions-metadata call return None so the caller can degrade rather
    than refuse the page.
    """
    try:
        metadata = client.materialize.get_versions_metadata()
    except Exception:
        return None
    valid = [int(m["version"]) for m in metadata if m.get("valid", True)]
    return max(valid) if valid else None


def check_live_allowed(datastack: str, mat_version: int | str | None) -> None:
    """Raise ValueError if `mat_version` requests live but the datastack disallows it.

    Endpoints catch this and translate to a 422. Defense in depth: the SPA already
    hides 'live' from the version picker for these datastacks, but a direct API
    caller bypassing the SPA still gets a clean refusal.
    """
    # Local import keeps this helper available without forcing a `keys` dep cycle.
    from .keys import is_live

    if not is_live(mat_version):
        return
    cfg = load_datastack_config(datastack)
    if not cfg.live_mode:
        raise ValueError(
            f"Datastack {datastack!r} disallows live mode; "
            f"pass an explicit ?mat_version=<int>."
        )
