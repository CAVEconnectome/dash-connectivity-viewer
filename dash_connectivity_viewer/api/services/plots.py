"""Server-side plot rendering.

Plot recipes are declarative `PlotSpec` objects (loaded from YAML templates).
Server materializes the requested data slice from a `NeuronQuery`, applies any
optional decoration (cell_type / num_soma), passes through a `kind`-specific
builder that produces a Plotly figure, and returns its JSON to the client.

The PlotSpec abstraction is the seam where a future Bokeh / HoloViews backend
could plug in — the spec stays, the builders swap.
"""

import colorsys
import json
import re
from pathlib import Path
from typing import Literal

import pandas as pd
import plotly.graph_objects as go
import yaml
from flask import current_app
from pydantic import BaseModel, Field

from .neuron import NeuronQuery


# ----- schema -----------------------------------------------------------------

class DataQuery(BaseModel):
    """`source` selects the dataframe the plot draws from:
      - `partners_in`  — input partners only.
      - `partners_out` — output partners only.
      - `partners_both` — unified frame: one row per unique partner root_id,
        synapse counts and aggregations split into _in / _out columns
        (mirrors the SPA's "Both" tab; computed by `_build_unified_frame`).
    """
    source: Literal["partners_in", "partners_out", "partners_both"]


class LayoutOverrides(BaseModel):
    title: str | None = None
    xaxis_title: str | None = None
    yaxis_title: str | None = None
    width: int | None = None
    height: int | None = None
    showlegend: bool | None = None


class PlotSpec(BaseModel):
    """A plot recipe.

    `kind` is the *primary* chart type. When `dynamic=True`, the resolver may
    override `kind` at request time based on which axes the caller binds:
    one axis → histogram, two axes → scatter. Static specs (`dynamic=False`)
    keep `kind` exactly.

    `hue` and `size` are runtime channels for scatter / colored histogram.
    `color` is kept as a deprecated alias for `hue` so existing YAMLs that
    grouped bars by color continue to work; the resolver normalizes to `hue`.
    """
    name: str
    description: str = ""
    kind: Literal["bar", "histogram", "scatter"]
    data_query: DataQuery
    x: str | None = None       # column name on the source frame
    y: str | None = None       # column name; bar implies count if omitted
    hue: str | None = None     # column name for color/group split
    color: str | None = None   # deprecated alias for `hue` (back-compat)
    size: str | None = None    # numeric column → marker size for scatter
    bins: int | None = None    # histogram only
    dynamic: bool = False      # accept runtime `bindings` overrides + auto-pick kind
    needs_cell_type: bool = False
    layout: LayoutOverrides = Field(default_factory=LayoutOverrides)


# ----- loader -----------------------------------------------------------------

def load_plot_specs() -> dict[str, PlotSpec]:
    """Reload templates fresh on every call — they're tiny YAMLs."""
    out: dict[str, PlotSpec] = {}
    bundled_dir = Path(__file__).parent.parent / "templates" / "plots"
    _load_dir(bundled_dir, out)
    extra_dir = current_app.config.get("PLOT_TEMPLATE_DIR")
    if extra_dir:
        _load_dir(Path(extra_dir), out)
    return out


def _load_dir(path: Path, out: dict[str, PlotSpec]) -> None:
    if not path.is_dir():
        return
    for yaml_path in sorted(path.glob("*.yaml")):
        try:
            data = yaml.safe_load(yaml_path.read_text()) or {}
        except Exception:
            continue
        if "name" not in data:
            data["name"] = yaml_path.stem
        try:
            spec = PlotSpec.model_validate(data)
        except Exception:
            continue
        out[spec.name] = spec


# ----- builders ---------------------------------------------------------------

def _apply_layout(fig: go.Figure, layout: LayoutOverrides) -> None:
    update: dict = {}
    if layout.title is not None:
        update["title"] = layout.title
    if layout.xaxis_title is not None:
        update["xaxis_title"] = layout.xaxis_title
    if layout.yaxis_title is not None:
        update["yaxis_title"] = layout.yaxis_title
    if layout.width is not None:
        update["width"] = layout.width
    if layout.height is not None:
        update["height"] = layout.height
    if layout.showlegend is not None:
        update["showlegend"] = layout.showlegend
    if update:
        fig.update_layout(**update)


def _resolve_hue(spec: PlotSpec) -> str | None:
    """`hue` wins over the deprecated `color` alias."""
    return spec.hue or spec.color


def _customdata(data: pd.DataFrame) -> list[str] | None:
    """Per-point root_id payload so the SPA can map plot-event picks back to
    table rows (drives the brushing feature). Always emitted when the column
    is present; consumers ignore it if they don't need it."""
    if "root_id" not in data.columns:
        return None
    return data["root_id"].astype(str).tolist()


def _build_bar(data: pd.DataFrame, spec: PlotSpec) -> go.Figure:
    if spec.x is None:
        raise ValueError("bar plot requires `x`")
    hue = _resolve_hue(spec)
    if spec.y is None:
        # Implicit count: group by x (and hue if given), tally rows.
        group_cols = [spec.x] + ([hue] if hue else [])
        counts = data.groupby(group_cols, dropna=False).size().reset_index(name="count")
        counts[spec.x] = counts[spec.x].fillna("(none)").astype(str)
        if hue:
            counts[hue] = counts[hue].fillna("(none)").astype(str)
            fig = go.Figure()
            for hue_value, sub in counts.groupby(hue, dropna=False):
                fig.add_trace(go.Bar(x=sub[spec.x], y=sub["count"], name=str(hue_value)))
            fig.update_layout(barmode="stack")
        else:
            counts = counts.sort_values("count", ascending=False)
            fig = go.Figure([go.Bar(x=counts[spec.x], y=counts["count"])])
    else:
        fig = go.Figure([go.Bar(x=data[spec.x], y=data[spec.y], customdata=_customdata(data))])
    return fig


def _build_histogram(data: pd.DataFrame, spec: PlotSpec) -> go.Figure:
    """Histogram of `x` (default) or `y`. The resolver picks `kind=histogram`
    when only one of x/y is bound on a dynamic spec — this builder honors
    whichever side is set.
    """
    if spec.x is None and spec.y is None:
        raise ValueError("histogram requires `x` or `y`")
    if spec.x is not None:
        fig = go.Figure([go.Histogram(x=data[spec.x], nbinsx=spec.bins)])
    else:
        fig = go.Figure([go.Histogram(y=data[spec.y], nbinsy=spec.bins)])
    return fig


# --- scatter + hue rules --------------------------------------------------

# Mirrors the SPA's three-tier hue convention. Backend-side enforcement keeps
# the policy in one place, and the resolver can return a clean 422 when the
# user binds a hue column with too many distinct non-numeric values to be
# meaningfully colored.
_HUE_PALETTE_MAX = 12         # ≤12 → split per category, distinct hues
_HUE_GREYSCALE_MAX = 30       # 13–30 → split per category, greyscale ramp
_VIRIDIS_NAME = "Viridis"     # >30 numeric → continuous colorscale


def _scale_size(values: pd.Series, lo_px: float = 4.0, hi_px: float = 20.0) -> pd.Series:
    """Scale a numeric column linearly into [lo_px, hi_px] for marker.size.
    NaN / non-numeric → median size. Constant column → all rows at hi_px so
    the dimension still renders distinctly."""
    s = pd.to_numeric(values, errors="coerce")
    finite = s.dropna()
    if finite.empty:
        return pd.Series([hi_px] * len(values), index=values.index)
    lo, hi = float(finite.min()), float(finite.max())
    if hi <= lo:
        return pd.Series([hi_px] * len(values), index=values.index)
    fill = lo  # NaN → smallest size
    return ((s.fillna(fill) - lo) * (hi_px - lo_px) / (hi - lo)) + lo_px


def _greyscale_ramp(n: int) -> list[str]:
    """Evenly-spaced grey hex values from #333333 to #bbbbbb. Used for
    discrete-numeric hue at 13-30 distinct values, where the implicit
    ordering of the values makes a sequential ramp meaningful."""
    if n <= 0:
        return []
    if n == 1:
        return ["#666666"]
    lo, hi = 0x33, 0xbb
    out: list[str] = []
    for i in range(n):
        v = int(lo + (hi - lo) * i / (n - 1))
        out.append(f"#{v:02x}{v:02x}{v:02x}")
    return out


def _categorical_palette(n: int) -> list[str]:
    """Generate `n` visually-distinct categorical colors via HSL rotation.

    Used for the 13-30 distinct *non-numeric* hue case where ordering would
    be misleading (e.g. cell_type with 18 unique labels). Saturation /
    lightness are restrained to match the SPA's low-saturation aesthetic;
    alternating lightness across adjacent hues breaks the visual gradient
    that pure-rotation produces.

    For n ≤ 12 we still defer to Plotly's colorway (driven by the SPA's
    `--cat-*` CSS tokens via `theme.ts`), so this function is only called
    in the 13-30 range.
    """
    if n <= 0:
        return []
    out: list[str] = []
    for i in range(n):
        h = (i / n)                      # full hue rotation, 0..1
        l = 0.50 + (0.06 if i % 2 == 0 else -0.06)
        s = 0.55                         # restrained saturation
        r, g, b = colorsys.hls_to_rgb(h, l, s)
        out.append(f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}")
    return out


def _build_scatter(data: pd.DataFrame, spec: PlotSpec) -> go.Figure:
    if spec.x is None or spec.y is None:
        raise ValueError("scatter plot requires both `x` and `y`")
    hue = _resolve_hue(spec)
    customdata_all = _customdata(data)

    marker_size: pd.Series | float = 7.0
    if spec.size and spec.size in data.columns:
        marker_size = _scale_size(data[spec.size])

    fig = go.Figure()
    if hue is None or hue not in data.columns:
        marker = {"size": marker_size if not isinstance(marker_size, float) else marker_size}
        fig.add_trace(go.Scatter(
            x=data[spec.x], y=data[spec.y],
            mode="markers", marker=marker,
            customdata=customdata_all,
        ))
        return fig

    hue_col = data[hue]
    n_unique = int(hue_col.nunique(dropna=False))
    is_numeric = pd.api.types.is_numeric_dtype(hue_col)

    if n_unique <= _HUE_PALETTE_MAX:
        # Categorical palette: one trace per value (Plotly cycles through colorway).
        for value, sub in data.groupby(hue_col.fillna("(none)"), dropna=False):
            sub_marker_size = marker_size.loc[sub.index] if hasattr(marker_size, "loc") else marker_size
            fig.add_trace(go.Scatter(
                x=sub[spec.x], y=sub[spec.y],
                mode="markers", name=str(value),
                marker={"size": sub_marker_size},
                customdata=sub["root_id"].astype(str).tolist() if "root_id" in sub.columns else None,
            ))
        return fig

    if n_unique <= _HUE_GREYSCALE_MAX:
        # 13-30 distinct values. Numeric values keep a sequential greyscale
        # ramp — preserves visual ordering, useful for discrete-numeric hue
        # like num_soma (0, 1, 2, ...). Non-numeric (e.g. cell_type with 18
        # labels) gets a generated distinct-hue palette so categorical labels
        # don't read as an ordered gradient.
        palette = _greyscale_ramp(n_unique) if is_numeric else _categorical_palette(n_unique)
        for i, (value, sub) in enumerate(data.groupby(hue_col.fillna("(none)"), dropna=False)):
            sub_marker_size = marker_size.loc[sub.index] if hasattr(marker_size, "loc") else marker_size
            fig.add_trace(go.Scatter(
                x=sub[spec.x], y=sub[spec.y],
                mode="markers", name=str(value),
                marker={"size": sub_marker_size, "color": palette[i]},
                customdata=sub["root_id"].astype(str).tolist() if "root_id" in sub.columns else None,
            ))
        return fig

    if not is_numeric:
        # >30 distinct non-numeric: nothing useful to show. The resolver
        # converts ValueError into a 422 with a hint pointing the user
        # toward a numeric / lower-cardinality column.
        raise ValueError(
            f"hue column {hue!r} has {n_unique} distinct non-numeric values "
            f"— pick a numeric column for a continuous colorscale, or a "
            f"categorical column with ≤{_HUE_GREYSCALE_MAX} distinct values."
        )

    # >30 numeric: single trace, continuous colorscale.
    marker = {
        "size": marker_size,
        "color": pd.to_numeric(hue_col, errors="coerce"),
        "colorscale": _VIRIDIS_NAME,
        "showscale": True,
        "colorbar": {"title": {"text": hue, "font": {"size": 10}}},
    }
    fig.add_trace(go.Scatter(
        x=data[spec.x], y=data[spec.y],
        mode="markers", marker=marker,
        customdata=customdata_all,
    ))
    return fig


_BUILDERS = {"bar": _build_bar, "histogram": _build_histogram, "scatter": _build_scatter}


# --- depth-axis auto-reversal -------------------------------------------------

# Match column names whose bare suffix carries `depth` as a discrete word —
# e.g. `soma_depth`, `depth`, `pia_depth_um`. Avoids false-positives like
# `depth_class` (still depth-like, ok) or `width` (not a match).
_DEPTH_PATTERN = re.compile(r'(?:^|_)depth(?:$|_)', re.IGNORECASE)


def _is_depth_column(name: str | None) -> bool:
    if not name:
        return False
    bare = name.rsplit(".", 1)[-1]
    return bool(_DEPTH_PATTERN.search(bare))


def _maybe_flip_depth(fig: go.Figure, spec: PlotSpec) -> None:
    """Auto-reverse plot axes bound to depth-like columns so 0 (pia) sits at
    the top of the figure rather than the bottom — matches the anatomical
    convention where depth grows downward into the cortex.
    """
    if _is_depth_column(spec.x):
        fig.update_xaxes(autorange="reversed")
    if _is_depth_column(spec.y):
        fig.update_yaxes(autorange="reversed")


# --- unified frame + direction-scope helpers ---------------------------------

# Direction-class values written into the synthetic `direction` column on the
# unified frame. The SPA exposes this as a hue-bind option so the user can
# color points by which side of the connection the partner sits on.
_DIRECTION_PRE = "presynaptic"     # n_syn_in > 0, n_syn_out == 0
_DIRECTION_POST = "postsynaptic"   # n_syn_out > 0, n_syn_in == 0
_DIRECTION_RECIP = "reciprocal"    # both > 0


def _direction_class(row) -> str:
    has_in = (row.get("n_syn_in") or 0) > 0
    has_out = (row.get("n_syn_out") or 0) > 0
    if has_in and has_out:
        return _DIRECTION_RECIP
    if has_in:
        return _DIRECTION_PRE
    return _DIRECTION_POST


def _apply_scope_filter(df: pd.DataFrame, scope: str) -> pd.DataFrame:
    """Filter the unified frame by per-axis direction scope.

    `scope`:
      - "pre"  → rows where the partner gives input  (`n_syn_in > 0`)
      - "post" → rows where the partner receives output (`n_syn_out > 0`)
      - "both" → no filter

    The "loose" semantics include reciprocal partners in both pre and post
    scopes — usually what the user wants ("show all input partners",
    not "show only input-only partners"). Strict-direction analysis is
    expressed by combining x_scope=post + y_scope=pre, which intersects
    to reciprocal partners only.
    """
    if scope == "pre":
        return df[df["n_syn_in"].fillna(0) > 0]
    if scope == "post":
        return df[df["n_syn_out"].fillna(0) > 0]
    return df


def _build_unified_frame(nq: NeuronQuery) -> pd.DataFrame:
    """Mirror the SPA's `unifyPartners` server-side: one row per unique
    partner root_id, `num_syn` split into `n_syn_in` / `n_syn_out`, and each
    `synapse_aggregation_rules` column split into `<name>_in` / `<name>_out`
    with null in the missing direction.

    Lets dynamic plots reach across both directions on a single row — e.g.
    scatter `n_syn_in` vs `n_syn_out` with `hue = cell_type` to find
    reciprocal partners stratified by class.
    """
    pin = nq.partners_in()
    pout = nq.partners_out()
    rule_names = list(nq.synapse_aggregation_rules.keys())

    by_root: dict[int, dict] = {}

    if not pout.empty:
        for _, r in pout.iterrows():
            rid = int(r["root_id"])
            rec = {"root_id": rid, "n_syn_out": int(r["num_syn"]), "n_syn_in": 0}
            for name in rule_names:
                rec[f"{name}_out"] = r.get(name)
                rec[f"{name}_in"] = None
            by_root[rid] = rec

    if not pin.empty:
        for _, r in pin.iterrows():
            rid = int(r["root_id"])
            if rid in by_root:
                existing = by_root[rid]
                existing["n_syn_in"] = int(r["num_syn"])
                for name in rule_names:
                    existing[f"{name}_in"] = r.get(name)
            else:
                rec = {"root_id": rid, "n_syn_out": 0, "n_syn_in": int(r["num_syn"])}
                for name in rule_names:
                    rec[f"{name}_out"] = None
                    rec[f"{name}_in"] = r.get(name)
                by_root[rid] = rec

    if not by_root:
        return pd.DataFrame(columns=["root_id", "n_syn_out", "n_syn_in"])
    return pd.DataFrame(list(by_root.values()))


# ----- resolver ---------------------------------------------------------------

def resolve_plot(
    *,
    spec: PlotSpec,
    nq: NeuronQuery,
    cell_type_table: str | None,
    decoration_tables: list[str] | None,
    column_override: str | None,
    bindings: dict[str, str | None] | None = None,
    client_factory,
    spatial_transform_name: str | None = None,
) -> dict:
    """Materialize `spec.data_query` against `nq` (with optional decoration),
    dispatch to the kind-specific builder, return Plotly figure JSON.

    Two override paths:
      - Legacy `column_override` — drops onto `spec.x` (single-axis column-
        bound plots).
      - `bindings: {x?, y?, hue?, size?}` — preferred. For dynamic specs
        (`spec.dynamic=True`), `kind` auto-resolves from bound axes:
        x XOR y → histogram, x AND y → scatter. Static specs still use
        their declared kind; bindings just override the channel columns.

    `bindings` wins when present; `column_override` is honored only when
    `bindings` doesn't supply an `x`. This keeps existing callers working.
    """
    if spec.data_query.source == "partners_in":
        df = nq.partners_in().copy()
    elif spec.data_query.source == "partners_out":
        df = nq.partners_out().copy()
    else:  # partners_both — unified frame spanning both directions
        df = _build_unified_frame(nq)
        # Synthetic 'direction' column on the unified frame so the SPA can
        # bind hue to it; values mirror the direction-class buckets used by
        # the per-axis scope filter below.
        if not df.empty:
            df["direction"] = df.apply(_direction_class, axis=1)

    # Merge legacy + new override paths into a single bindings map.
    bindings = bindings or {}
    bound = {
        "x": bindings.get("x") if bindings.get("x") is not None else (column_override or spec.x),
        "y": bindings.get("y") if bindings.get("y") is not None else spec.y,
        "hue": bindings.get("hue") if bindings.get("hue") is not None else _resolve_hue(spec),
        "size": bindings.get("size") if bindings.get("size") is not None else spec.size,
    }
    # Per-axis scope filter (only meaningful on the unified frame). Each
    # value is "pre" / "post" / "both"; "both" means no filter for that axis.
    # Filters compose via AND — set x_scope=post AND y_scope=pre to select
    # reciprocal partners.
    x_scope = (bindings.get("x_scope") or "both") if bindings else "both"
    y_scope = (bindings.get("y_scope") or "both") if bindings else "both"
    if spec.data_query.source == "partners_both" and not df.empty:
        df = _apply_scope_filter(df, x_scope)
        df = _apply_scope_filter(df, y_scope)
    # Auto-pick chart kind for dynamic specs based on bound axes.
    kind: Literal["bar", "histogram", "scatter"] = spec.kind
    if spec.dynamic:
        has_x, has_y = bound["x"] is not None, bound["y"] is not None
        if has_x and has_y:
            kind = "scatter"
        elif has_x or has_y:
            kind = "histogram"
        else:
            raise ValueError(
                "dynamic plot needs at least one of `x` or `y` bound — pick a column."
            )
    spec = spec.model_copy(update={
        "kind": kind,
        "x": bound["x"],
        "y": bound["y"],
        "hue": bound["hue"],
        "size": bound["size"],
        "color": None,  # consumed; resolver works off `hue` now.
    })

    served: dict[int, dict] = {}
    needs_decoration = bool(cell_type_table or nq.soma_table or (decoration_tables or []))
    if needs_decoration:
        from .decoration import lookup_decorations
        # Pass the datastack's soma_table so num_soma / cell_id columns are
        # available as bar-plot grouping targets. The SWR + warmup machinery
        # means the second request hits the cached soma snapshot instantly.
        served, _groups, _reval = lookup_decorations(
            client_factory=client_factory,
            ds=nq.datastack,
            mat_version=nq.mat_version,
            cell_type_table=cell_type_table,
            soma_table=nq.soma_table,
            soma_root_id_column=nq.soma_root_id_column,
            root_ids=df["root_id"].astype(int).tolist(),
            decoration_tables=decoration_tables or [],
        )
        # Each served record carries arbitrary keys (flat for cell_type_table,
        # `<table>.<col>` for decoration_tables). Materialize them as columns.
        # `pt_position` is internal scaffolding for the spatial computation
        # below — drop it from the column materialization so it doesn't leak
        # into the figure as an array-valued column.
        if served:
            all_keys: set[str] = set()
            for rec in served.values():
                all_keys.update(rec.keys())
            all_keys.discard("pt_position")
            for k in all_keys:
                df[k] = df["root_id"].astype(int).map(
                    lambda rid, _k=k: served.get(rid, {}).get(_k)
                )

    # Spatial features. Same two-tier rule as connectivity_bundle:
    #   - median_dist_to_target_soma — plain Euclidean, no transform needed
    #   - soma_depth, radial_dist_root_soma — require an oriented transform
    # Both tiers require partner soma positions, which means the soma
    # decoration must have been fetched above (it's part of `served`).
    if served:
        from .spatial import attach_spatial_features, load_streamline, load_transform
        transform = load_transform(spatial_transform_name) if spatial_transform_name else None
        streamline = load_streamline(spatial_transform_name) if spatial_transform_name else None
        root_soma = nq.soma_summary().get("soma_pt_position")
        source = spec.data_query.source
        # Unified frames need both directions' median; single-direction frames
        # only need the matching one. attach_spatial_features takes None for
        # the side it should skip.
        want_in = source in ("partners_in", "partners_both")
        want_out = source in ("partners_out", "partners_both")
        intrinsic, median_in, median_out = attach_spatial_features(
            transform=transform,
            streamline=streamline,
            decoration_lookup=served,
            root_soma_position_nm=root_soma,
            syn_df_in=nq._synapse_df("post") if want_in else None,
            syn_df_out=nq._synapse_df("pre") if want_out else None,
            syn_position_prefix=nq.synapse_position_prefix,
        )
        # Intrinsic columns only materialize when the transform was available.
        if intrinsic:
            for col in ("soma_depth", "radial_dist_root_soma"):
                df[col] = df["root_id"].astype(int).map(
                    lambda rid, _c=col: intrinsic.get(rid, {}).get(_c)
                )
        if source == "partners_both":
            # Per-direction median columns matching the SPA's unified table —
            # `median_dist_to_target_soma_in` and `_out` so plots can compare
            # them on the same row.
            if median_in:
                df["median_dist_to_target_soma_in"] = df["root_id"].astype(int).map(
                    lambda rid: median_in.get(rid)
                )
            if median_out:
                df["median_dist_to_target_soma_out"] = df["root_id"].astype(int).map(
                    lambda rid: median_out.get(rid)
                )
        else:
            median_lookup = median_in if source == "partners_in" else median_out
            if median_lookup:
                df["median_dist_to_target_soma"] = df["root_id"].astype(int).map(
                    lambda rid: median_lookup.get(rid)
                )

    # Validate every bound channel exists on the dataframe. Helps users
    # diagnose stale URL state (e.g. a binding pointing to a decoration
    # column that's no longer loaded).
    for ch in ("x", "y", "hue", "size"):
        col = getattr(spec, ch)
        if col and col not in df.columns:
            raise ValueError(
                f"Column {col!r} (bound to `{ch}`) is not on the partner "
                f"records — pick one of the active decoration columns."
            )
    # Histogram needs *something* to bin; scatter needs both x and y.
    if spec.kind == "histogram" and not (spec.x or spec.y):
        raise ValueError("histogram needs `x` or `y` bound.")
    if spec.kind == "scatter" and (spec.x is None or spec.y is None):
        raise ValueError("scatter plot requires both `x` and `y` bound.")
    if spec.kind == "bar" and not spec.x:
        raise ValueError("bar plot requires `x` bound.")

    builder = _BUILDERS.get(spec.kind)
    if builder is None:
        raise ValueError(f"Unknown plot kind: {spec.kind!r}")
    fig = builder(df, spec)
    _apply_layout(fig, spec.layout)
    _maybe_flip_depth(fig, spec)
    # Plotly's to_json returns a JSON string; parse it back so Flask jsonify
    # nests it as a real object rather than a quoted string.
    return {"figure": json.loads(fig.to_json())}
