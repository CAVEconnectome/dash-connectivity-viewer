from typing import Any

import pandas as pd

from ..caches import query_cache
from .keys import canonical_query_hash, is_live
from .query_runner import run_query


DEFAULT_DESIRED_RESOLUTION = [1, 1, 1]


class NeuronQuery:
    def __init__(
        self,
        client,
        root_id: int,
        *,
        datastack: str,
        mat_version: int | str | None,
        synapse_table: str | None = None,
        soma_table: str | None = None,
        soma_root_id_column: str = "pt_root_id",
        synapse_aggregation_rules: dict[str, dict] | None = None,
        synapse_columns: list[str] | None = None,
        synapse_position_prefix: str = "ctr_pt",
        desired_resolution: list[int] | None = None,
    ):
        self.client = client
        self.root_id = int(root_id)
        self.datastack = datastack
        self.mat_version = mat_version
        info = client.info.get_datastack_info()
        self.synapse_table = synapse_table or info.get("synapse_table")
        self.soma_table = soma_table or info.get("soma_table")
        self.soma_root_id_column = soma_root_id_column
        self.synapse_aggregation_rules = synapse_aggregation_rules or {}
        self.synapse_columns = synapse_columns
        self.synapse_position_prefix = synapse_position_prefix
        self.desired_resolution = desired_resolution or DEFAULT_DESIRED_RESOLUTION
        self.timestamp_used = None  # populated when df.attrs carries one back

    def _cache_key(self, kind: str, **extra: Any) -> str | None:
        if is_live(self.mat_version):
            return None
        payload = {"kind": kind, "ds": self.datastack, "mv": self.mat_version,
                   "syn": self.synapse_table, "rid": self.root_id,
                   "cols": tuple(self.synapse_columns) if self.synapse_columns else None,
                   **extra}
        return canonical_query_hash(payload)

    def _synapse_df(self, direction: str) -> pd.DataFrame:
        if self.synapse_table is None:
            raise ValueError("synapse_table is not configured for this datastack")
        key = self._cache_key("synapses", direction=direction)
        if key and key in query_cache:
            return query_cache[key]
        partner_col = "pre_pt_root_id" if direction == "post" else "post_pt_root_id"
        own_col = "post_pt_root_id" if direction == "post" else "pre_pt_root_id"
        qf = self.client.materialize.tables[self.synapse_table](**{own_col: self.root_id})
        query_kwargs: dict[str, Any] = {
            "split_positions": True,
            "desired_resolution": self.desired_resolution,
        }
        if self.synapse_columns is not None:
            query_kwargs["select_columns"] = self.synapse_columns
        df = run_query(qf, live=is_live(self.mat_version), **query_kwargs)
        df = df[df[partner_col] != 0].copy()
        df = df[df[partner_col] != self.root_id].copy()  # drop autapses
        if df.attrs.get("timestamp"):
            self.timestamp_used = str(df.attrs["timestamp"])
        if key:
            query_cache[key] = df
        return df

    def _aggregate(self, syn_df: pd.DataFrame, partner_col: str) -> pd.DataFrame:
        if syn_df.empty:
            return pd.DataFrame(columns=["root_id", "num_syn"])
        grp = syn_df.groupby(partner_col, sort=False)
        out = grp.size().to_frame("num_syn")
        for new_col, rule in self.synapse_aggregation_rules.items():
            out[new_col] = grp[rule["column"]].agg(rule["agg"])
        out = out.reset_index().rename(columns={partner_col: "root_id"})
        return out.sort_values("num_syn", ascending=False).reset_index(drop=True)

    def partners_out(self) -> pd.DataFrame:
        return self._aggregate(self._synapse_df("pre"), "post_pt_root_id")

    def partners_in(self) -> pd.DataFrame:
        return self._aggregate(self._synapse_df("post"), "pre_pt_root_id")

    def soma_summary(self) -> dict:
        if self.soma_table is None:
            return {"num_soma": 0, "soma_pt_position": None}
        try:
            qf = self.client.materialize.tables[self.soma_table](
                **{self.soma_root_id_column: self.root_id}
            )
            df = run_query(
                qf,
                live=is_live(self.mat_version),
                split_positions=False,
                desired_resolution=self.desired_resolution,
            )
        except Exception:
            return {"num_soma": 0, "soma_pt_position": None}
        if df.empty:
            return {"num_soma": 0, "soma_pt_position": None}
        pt_col = next((c for c in df.columns if c.endswith("pt_position")), None)
        soma_pt = None
        if pt_col is not None:
            value = df.iloc[0][pt_col]
            if hasattr(value, "tolist"):
                value = value.tolist()
            soma_pt = list(value) if value is not None else None
        return {"num_soma": int(len(df)), "soma_pt_position": soma_pt}


def connectivity_bundle(
    nq: NeuronQuery,
    *,
    include: list[str] | None = None,
    cell_type_table: str | None = None,
    decoration_tables: list[str] | None = None,
    client_factory=None,
    spatial_transform_name: str | None = None,
    depth_range: list[float] | None = None,
    layer_boundaries: list[float] | None = None,
    layer_names: list[str] | None = None,
) -> dict:
    include = set(include or ["partners_in", "partners_out", "summary"])
    # All root_id values cross the wire as JSON strings: int64 root ids overflow
    # JavaScript's Number (float64; precise up to 2^53). The frontend keeps them
    # as strings throughout; the backend converts back via int() at the body
    # boundary. Same rule applies inside aggregated partner records below.
    payload: dict[str, Any] = {
        "datastack": nq.datastack,
        "root_id": str(nq.root_id),
        "version_used": nq.mat_version if not is_live(nq.mat_version) else "live",
        "synapse_table": nq.synapse_table,
        "soma_table": nq.soma_table,
        "cell_type_table": cell_type_table,
    }
    need_in = "partners_in" in include or "summary" in include
    need_out = "partners_out" in include or "summary" in include
    pin = nq.partners_in() if need_in else None
    pout = nq.partners_out() if need_out else None

    decoration_lookup: dict[int, dict] = {}
    decoration_groups: list[dict] = []
    revalidation: dict[str, Any] | None = None
    if cell_type_table or nq.soma_table or (decoration_tables or []):
        if client_factory is None:
            raise ValueError("connectivity_bundle requires client_factory when enriching")
        from .decoration import lookup_decorations
        # Only enrich partners that will actually be in the response —
        # plus the queried root, which the SPA's "Cell" tab renders as a
        # standalone row alongside the partner tabs. Including the root
        # in this single lookup means the per-partner enrichment + the
        # root enrichment share one CAVE round-trip per decoration table.
        partner_ids: list[int] = []
        if pin is not None and "partners_in" in include:
            partner_ids.extend(int(x) for x in pin["root_id"].tolist())
        if pout is not None and "partners_out" in include:
            partner_ids.extend(int(x) for x in pout["root_id"].tolist())
        partner_ids = list(dict.fromkeys(partner_ids))  # preserve order, dedupe
        # Root included AFTER partners so it doesn't perturb the order
        # the partner enrichment iterates in. `dict.fromkeys` deduplicates
        # if the root happens to also appear as a partner (self-loop).
        decoration_ids = list(dict.fromkeys([*partner_ids, int(nq.root_id)]))
        if decoration_ids:
            decoration_lookup, decoration_groups, revalidation = lookup_decorations(
                client_factory=client_factory,
                ds=nq.datastack,
                mat_version=nq.mat_version,
                cell_type_table=cell_type_table,
                soma_table=nq.soma_table,
                soma_root_id_column=nq.soma_root_id_column,
                root_ids=decoration_ids,
                decoration_tables=decoration_tables or [],
            )

    # Spatial features. Two tiers:
    #   - median_dist_to_target_soma is plain Euclidean — runs whenever any
    #     partner has a known soma position, no transform required.
    #   - soma_depth + soma_x + soma_z + radial_dist_root_soma + median_syn_depth
    #     require an oriented standard_transform; attach_spatial_features
    #     returns empty dicts for those when none is configured.
    spatial_intrinsic: dict[int, dict[str, float]] = {}
    spatial_median_in: dict[int, float] = {}
    spatial_median_out: dict[int, float] = {}
    spatial_syn_depth_in: dict[int, float] = {}
    spatial_syn_depth_out: dict[int, float] = {}
    # Lift the transform load up so the depth-profile computation below
    # can reuse it without re-parsing the YAML / reloading the
    # standard_transform module. The per-partner spatial features still
    # gate on `decoration_lookup` (they need partner soma positions);
    # the per-cell depth profile only needs the synapse df + transform.
    from .spatial import (
        attach_spatial_features,
        compute_synapse_depth_profile,
        load_streamline,
        load_transform,
    )
    transform = load_transform(spatial_transform_name) if spatial_transform_name else None
    streamline = load_streamline(spatial_transform_name) if spatial_transform_name else None

    if decoration_lookup:
        # `nq.soma_summary()` is cached on the NeuronQuery via the underlying
        # CAVEclient call; calling here is free if the summary block also runs
        # below. Root soma is only used for radial-dist; missing → that single
        # column is omitted but the others still flow.
        root_soma = nq.soma_summary().get("soma_pt_position")
        (
            spatial_intrinsic,
            spatial_median_in,
            spatial_median_out,
            spatial_syn_depth_in,
            spatial_syn_depth_out,
        ) = attach_spatial_features(
            transform=transform,
            streamline=streamline,
            decoration_lookup=decoration_lookup,
            root_soma_position_nm=root_soma,
            # Reuse the cached synapse dfs from the aggregation step.
            syn_df_in=nq._synapse_df("post") if pin is not None else None,
            syn_df_out=nq._synapse_df("pre") if pout is not None else None,
            syn_position_prefix=nq.synapse_position_prefix,
        )

    # Per-cell synapse depth profile — populated when the datastack has a
    # transform. Independent of decoration / partner enrichment because
    # it's a property of the cell's full synapse cloud, not of any
    # particular partner.
    synapse_depth_profile = compute_synapse_depth_profile(
        transform=transform,
        syn_df_in=nq._synapse_df("post") if need_in else None,
        syn_df_out=nq._synapse_df("pre") if need_out else None,
        syn_position_prefix=nq.synapse_position_prefix,
        depth_range=depth_range,
        layer_boundaries=layer_boundaries,
        layer_names=layer_names,
    )
    if synapse_depth_profile is not None:
        payload["synapse_depth_profile"] = synapse_depth_profile

    def _enrich_records(
        df,
        median_lookup: dict[int, float],
        syn_depth_lookup: dict[int, float],
    ):
        if df is None:
            return None
        records = df.to_dict(orient="records")
        for rec in records:
            rid = int(rec["root_id"])
            extra = decoration_lookup.get(rid)
            if extra:
                rec.update(extra)
            # Spatial: intrinsic features (same for both directions) + the
            # direction-specific synapse-edge stats.
            spatial_extra = spatial_intrinsic.get(rid)
            if spatial_extra:
                rec.update(spatial_extra)
            if rid in median_lookup:
                rec["median_dist_to_target_soma"] = median_lookup[rid]
            if rid in syn_depth_lookup:
                rec["median_syn_depth"] = syn_depth_lookup[rid]
            # `pt_position` is internal scaffolding for the spatial computation;
            # strip it so the wire payload stays tight and the SPA doesn't see
            # a column it has no place to render.
            rec.pop("pt_position", None)
            # Stringify after the int-keyed decoration lookup, so the wire
            # payload preserves int64 precision for the JS client.
            rec["root_id"] = str(rid)
        return records

    if "partners_in" in include and pin is not None:
        payload["partners_in"] = _enrich_records(pin, spatial_median_in, spatial_syn_depth_in)
    if "partners_out" in include and pout is not None:
        payload["partners_out"] = _enrich_records(pout, spatial_median_out, spatial_syn_depth_out)

    # The queried cell, shaped as a single partner-record so the SPA's
    # "Cell" tab can reuse PartnersTable's column rendering. Synapse
    # columns and per-edge stats don't apply here — they're per-partner
    # by construction. We include the cell-type / soma decoration and
    # intrinsic spatial features (soma_depth / soma_x / soma_z) so the
    # tab reads as a place to find "what does CAVE know about this
    # specific cell." `radial_dist_root_soma` for the root would be 0
    # by definition (distance from itself), so we drop it as noise.
    root_rid = int(nq.root_id)
    root_rec: dict[str, Any] = {"root_id": str(root_rid)}
    extra = decoration_lookup.get(root_rid)
    if extra:
        root_rec.update(extra)
    spatial_self = spatial_intrinsic.get(root_rid)
    if spatial_self:
        for k, v in spatial_self.items():
            if k == "radial_dist_root_soma":
                continue  # zero by construction
            root_rec[k] = v
    root_rec.pop("pt_position", None)
    payload["root_record"] = root_rec
    if "summary" in include:
        soma = nq.soma_summary()
        payload["summary"] = {
            "num_partners_in": int(pin.shape[0]) if pin is not None else None,
            "num_partners_out": int(pout.shape[0]) if pout is not None else None,
            "num_syn_in": int(nq._synapse_df("post").shape[0]),
            "num_syn_out": int(nq._synapse_df("pre").shape[0]),
            **soma,
        }
    payload["timestamp_used"] = nq.timestamp_used
    payload["synapse_columns_meta"] = {
        "aggregation_rules": [
            {"name": k, **v} for k, v in nq.synapse_aggregation_rules.items()
        ],
        "synapse_table": nq.synapse_table,
    }

    # column_groups drives the SPA's two-row table header. Order matters: it's
    # the left-to-right column order. Each group has `kind` (intrinsic, synapse,
    # soma, cell_type, table, spatial) so the frontend can style them per-class.
    synapse_cols = ["num_syn"] + list(nq.synapse_aggregation_rules.keys())
    # Direction-specific spatial stats live in the synapse group so the
    # Both-tab unifier splits each into `_in` / `_out` alongside num_syn /
    # mean_size. Two columns here, registered independently because they
    # gate on different requirements:
    #   - median_dist_to_target_soma: plain Euclidean, runs without a
    #     transform whenever any partner has a soma position.
    #   - median_syn_depth: oriented-frame, requires the standard_transform.
    if spatial_median_in or spatial_median_out:
        synapse_cols.append("median_dist_to_target_soma")
    if spatial_syn_depth_in or spatial_syn_depth_out:
        synapse_cols.append("median_syn_depth")
    column_groups = [
        {"name": "id",      "kind": "intrinsic", "columns": ["root_id"]},
        {"name": "synapse", "kind": "synapse",   "columns": synapse_cols},
        *decoration_groups,
    ]
    if spatial_intrinsic:
        # Partner-intrinsic spatial columns: same value for both directions, so
        # the unifier passes them through unchanged. `soma_x` / `soma_z` give
        # the tangential coordinates so the SPA can scatter them as a
        # top-down view of the partner population.
        intrinsic_spatial_cols: list[str] = []
        sample_rec = next(iter(spatial_intrinsic.values()))
        for col in ("soma_depth", "soma_x", "soma_z", "radial_dist_root_soma"):
            if col in sample_rec:
                intrinsic_spatial_cols.append(col)
        if intrinsic_spatial_cols:
            column_groups.append({
                "name": "spatial",
                "kind": "spatial",
                "columns": intrinsic_spatial_cols,
            })
    payload["column_groups"] = column_groups

    payload["decoration_revalidation"] = revalidation
    return payload
