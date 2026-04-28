from pathlib import Path
from typing import Any

import yaml
from cachetools import LRUCache
from pydantic import BaseModel, Field

from flask import current_app


DEFAULT_SYNAPSE_COLUMNS = ["id", "pre_pt_root_id", "post_pt_root_id", "size", "ctr_pt_position"]


class AggregationRule(BaseModel):
    column: str
    agg: str  # any string accepted by pandas .agg() — "mean", "sum", "max", etc.


class SpatialConfig(BaseModel):
    """Per-datastack spatial transform configuration.

    `transform` names a constructor in `standard_transform.datasets`. Currently
    supported: `minnie_vx`, `minnie_nm`, `v1dd_vx`, `v1dd_nm`, `identity`.
    The `_nm` variants accept positions in nanometers (which is what the API
    serves at `desired_resolution=[1,1,1]`); `_vx` variants accept voxel
    coordinates. Choose based on what the connectivity service hands the
    spatial computation — currently `_nm`.

    Datastacks with no transform configured simply omit the spatial columns
    from the connectivity bundle; the SPA renders without them.
    """
    transform: str | None = None


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
    synapse_position_prefix: str = "ctr_pt"
    synapse_columns: list[str] | None = Field(default_factory=lambda: list(DEFAULT_SYNAPSE_COLUMNS))
    synapse_aggregation_rules: dict[str, AggregationRule] = Field(default_factory=dict)
    spatial: SpatialConfig = Field(default_factory=SpatialConfig)
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

    def merged_synapse_columns(self) -> list[str] | None:
        if self.synapse_columns is None:
            return None  # pull every column
        cols = list(self.synapse_columns)
        for rule in self.synapse_aggregation_rules.values():
            if rule.column not in cols:
                cols.append(rule.column)
        return cols

    def aggregation_rules_for_neuron_query(self) -> dict[str, dict]:
        return {name: rule.model_dump() for name, rule in self.synapse_aggregation_rules.items()}


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
