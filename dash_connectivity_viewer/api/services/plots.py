"""Server-side plot rendering.

Plot recipes are declarative `PlotSpec` objects (loaded from YAML templates).
Server materializes the requested data slice from a `NeuronQuery`, applies any
optional decoration (cell_type / num_soma), passes through a `kind`-specific
builder that produces a Plotly figure, and returns its JSON to the client.

The PlotSpec abstraction is the seam where a future Bokeh / HoloViews backend
could plug in — the spec stays, the builders swap.
"""

import json
import re
from pathlib import Path
from typing import Literal

import pandas as pd
import plotly.graph_objects as go
import yaml
from flask import current_app
from pydantic import BaseModel, ConfigDict, Field

from .categorical import (
    NULL_COLOR,
    NULL_LABEL,
    categorical_palette as _categorical_palette,
    get_unique_values,
    greyscale_ramp as _greyscale_ramp,
    resolve_categorical_color_map,
)
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


# ----- cell filter ------------------------------------------------------------

# Operators applied row-wise against a decoration column. Strings vs numerics
# are kept loose: comparisons coerce to float when both sides parse, otherwise
# string-compare. `in` / `notin` use `|`-separated values inside the URL.
CellFilterOp = Literal[
    "eq", "ne", "gt", "gte", "lt", "lte", "in", "notin", "nonnull", "null",
]


class CellFilter(BaseModel):
    """One predicate against a decoration column. Predicates AND together."""
    table: str          # decoration table name (or cell-type table)
    column: str         # bare column name on that table
    op: CellFilterOp
    value: str | None = None   # null for nonnull/null ops; pipe-split for in/notin


def _parse_cells_param(raw: str | None) -> list[CellFilter]:
    """Parse the `cells=<table>.<col>:<op>:<val>[,...]` URL param into filters.

    Tolerates leading/trailing whitespace and empty entries. Bad clauses raise
    ValueError so the endpoint returns a 422 the user can fix from the URL.

    Clauses prefixed with `~` are disabled (the SPA's "off" toggle). They're
    skipped silently — the backend only sees the active filter set, so it
    doesn't have to track enable/disable state. Disabled clauses still need
    to parse cleanly so a typo'd disabled predicate is caught the moment the
    user toggles it back on.
    """
    if not raw:
        return []
    out: list[CellFilter] = []
    for clause in raw.split(","):
        clause = clause.strip()
        if not clause:
            continue
        disabled = clause.startswith("~")
        if disabled:
            clause = clause[1:].strip()
            if not clause:
                continue
        # Split on the first two colons only — values may legitimately contain
        # colons (e.g. ISO timestamps in the future).
        head, _, rest = clause.partition(":")
        op_str, _, value = rest.partition(":")
        if not head or not op_str:
            raise ValueError(f"cells clause {clause!r} must be 'table.col:op:val'")
        if "." not in head:
            raise ValueError(f"cells clause {clause!r} must qualify column as table.col")
        table, _, column = head.partition(".")
        if not table or not column:
            raise ValueError(f"cells clause {clause!r} has empty table or column")
        if op_str not in ("eq", "ne", "gt", "gte", "lt", "lte", "in", "notin", "nonnull", "null"):
            raise ValueError(f"cells clause {clause!r} has unknown op {op_str!r}")
        if disabled:
            continue  # parsed for validation, then dropped
        out.append(CellFilter(
            table=table.strip(),
            column=column.strip(),
            op=op_str,  # type: ignore[arg-type]
            value=value if value != "" else None,
        ))
    return out


# Truthy-ish strings that map to True for boolean-coerced comparisons. The
# proofreading_status_and_strategy.status_axon column lands on the SPA as
# Python booleans, but in the URL the user types "t" or "true". Coerce both
# sides to a normalized lowercase string before equality checks.
_BOOL_TRUE = {"true", "t", "1", "yes", "y"}
_BOOL_FALSE = {"false", "f", "0", "no", "n"}


def _normalize_for_compare(v):
    """Coerce a cell value into a comparable scalar.

    - `pd.NA` / NaN / None → None
    - bool → unchanged (so `_coerce_pair` can match against truthy/falsy strings)
    - everything else → unchanged (numeric coercion happens in `_coerce_pair`)
    """
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def _coerce_pair(left, right: str):
    """Coerce both sides for comparison. Returns (a, b) as a comparable pair.

    Booleans on the left expand `right` against the truthy/falsy string sets so
    `eq:t` / `eq:true` / `eq:1` all match a True value.
    """
    if left is None:
        return None, right
    if isinstance(left, bool):
        rl = right.strip().lower()
        if rl in _BOOL_TRUE:
            return left, True
        if rl in _BOOL_FALSE:
            return left, False
        return left, right
    # Try numeric on both sides; fall back to string if either side fails.
    try:
        return float(left), float(right)
    except (TypeError, ValueError):
        return str(left), str(right)


def _apply_cell_filters(df: pd.DataFrame, filters: list[CellFilter]) -> pd.DataFrame:
    """Apply each predicate as a row mask. Missing columns raise ValueError so
    the user gets a clear 422 instead of an empty plot.

    Operates on the *materialized* dataframe — by the time we get here the
    decoration columns have been merged on as `<table>.<column>` keys.
    """
    if not filters:
        return df
    if df.empty:
        return df
    for f in filters:
        col = f"{f.table}.{f.column}"
        if col not in df.columns:
            raise ValueError(
                f"cells filter references column {col!r} which is not loaded — "
                f"add the table to decoration_tables, or remove the predicate."
            )
        series = df[col]
        if f.op == "nonnull":
            mask = series.notna()
        elif f.op == "null":
            mask = series.isna()
        elif f.op in ("in", "notin"):
            wanted = [v.strip() for v in (f.value or "").split("|") if v.strip()]
            normalized = series.map(_normalize_for_compare)
            mask = normalized.astype(str).isin(wanted)
            if f.op == "notin":
                mask = ~mask
        else:
            if f.value is None:
                raise ValueError(f"cells op {f.op!r} requires a value")
            def _cmp(v, _op=f.op, _rhs=f.value):
                a, b = _coerce_pair(_normalize_for_compare(v), _rhs)
                if a is None:
                    return False
                try:
                    if _op == "eq":  return a == b
                    if _op == "ne":  return a != b
                    if _op == "gt":  return a >  b
                    if _op == "gte": return a >= b
                    if _op == "lt":  return a <  b
                    if _op == "lte": return a <= b
                except TypeError:
                    return False
                return False
            mask = series.map(_cmp).astype(bool)
        df = df[mask]
    return df


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
    one axis → histogram (numeric x) or bar (non-numeric x / weight bound),
    two axes → scatter. Static specs (`dynamic=False`) keep `kind` exactly.

    `hue` and `size` are runtime channels for scatter / colored histogram.
    `color` is kept as a deprecated alias for `hue` so existing YAMLs that
    grouped bars by color continue to work; the resolver normalizes to `hue`.

    `weight` applies only on bar plots: when set, the implicit-count `groupby
    .size()` is replaced with `groupby[weight].sum()` so the bars show
    "synapses by cell type" rather than "partners per cell type".

    `color_map` is internal scratch space. The resolver fills it with a
    `{value: hex}` mapping for cell-type-table-backed hues so colors are
    deterministic and consistent across plots; builders apply it to
    `marker.color` directly. Excluded from JSON and not user-settable.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str = ""
    kind: Literal["bar", "histogram", "scatter", "stripplot"]
    data_query: DataQuery
    x: str | None = None       # column name on the source frame
    y: str | None = None       # column name; bar implies count if omitted
    hue: str | None = None     # column name for color/group split
    color: str | None = None   # deprecated alias for `hue` (back-compat)
    size: str | None = None    # numeric column → marker size for scatter
    weight: str | None = None  # numeric column to sum on bar; replaces row-count
    bins: int | None = None    # histogram only
    dynamic: bool = False      # accept runtime `bindings` overrides + auto-pick kind
    needs_cell_type: bool = False
    layout: LayoutOverrides = Field(default_factory=LayoutOverrides)
    color_map: dict | None = Field(default=None, exclude=True)
    # Full universe of distinct values for `x` when x is categorical and
    # provenance traces back to a cell-type / decoration table. Used by
    # `_build_bar` and `_build_stripplot` to render every category — even
    # ones with zero observations — as an explicit x-axis slot, so the
    # user can see true zeros (e.g. "this neuron has no PV partners")
    # rather than silently-missing buckets. None when x is intrinsic /
    # numeric / synthetic — fall back to observed-only ordering.
    x_universe: list | None = Field(default=None, exclude=True)


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

def _format_label(col: str | None) -> str | None:
    """Render a bound-column reference for human-facing labels.

    Decoration-table columns ship as `<table>.<col>` (the dot is the
    internal join key — see `_provenance_for`). For axis titles and
    the colorbar header the dot is hard to read at small font sizes
    (`/` reads as a separator more clearly than `.`, which fights with
    the period as sentence punctuation). Bare-column references pass
    through unchanged. Weight-summed bars and synthetic columns
    (`direction`, `count`) have no dot to begin with.
    """
    if col is None:
        return None
    return col.replace(".", "/", 1) if "." in col else col


def _apply_auto_titles(fig: go.Figure, spec: PlotSpec) -> None:
    """Auto-fill axis titles from the bound columns when not already set.

    Plotly doesn't derive axis titles from explicitly-supplied trace data
    (only for `plotly.express` shorthand), so without this the SPA's
    collapsed picker chip would have to show every binding verbatim to
    convey what's plotted. With auto-titles, the chart self-documents:
    x-axis = `spec.x`, y-axis = `spec.y` / `spec.weight` / "count" depending
    on what the builder produced. Called *after* `_apply_layout` so any
    explicit override on the spec still wins.

    Decoration columns are rendered as `<table>/<col>` (slash form) rather
    than the internal `<table>.<col>` join key — see `_format_label`.
    """
    layout = fig.layout
    current_x = (
        layout.xaxis.title.text
        if layout.xaxis and layout.xaxis.title
        else None
    )
    current_y = (
        layout.yaxis.title.text
        if layout.yaxis and layout.yaxis.title
        else None
    )

    updates: dict = {}
    if not current_x and spec.x:
        updates["xaxis_title"] = _format_label(spec.x)
    if not current_y:
        if spec.y:
            updates["yaxis_title"] = _format_label(spec.y)
        elif spec.kind == "bar":
            # Implicit-count or weight-sum bars — name the y-axis after
            # what the bars are summing so the user reads "n_syn_in" or
            # "count" directly off the chart.
            updates["yaxis_title"] = _format_label(spec.weight) or "count"
        elif spec.kind == "histogram":
            updates["yaxis_title"] = "count"
    if updates:
        fig.update_layout(**updates)


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


def _provenance_for(col: str, cell_type_table: str | None) -> tuple[str | None, str]:
    """Return `(table, bare_column)` for a column reference.

    Decoration-table columns ship as `<table>.<col>` after `lookup_decorations`
    merges them in. Cell-type-table columns flatten to bare names by
    convention (`cell_type`, `classification_system`, etc.).

    Bare names without a configured cell-type table → `(None, col)`. Synapse
    columns (`n_syn_in`, `num_syn`) and synthetic columns (`direction`)
    take this branch and the caller falls back to plotly's default colorway.
    """
    if "." in col:
        tbl, _, bare = col.partition(".")
        return tbl, bare
    if cell_type_table:
        return cell_type_table, col
    return None, col


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

    # Explicit-y path takes whatever the dataframe says; weight is a no-op
    # here because the user already chose what the bars should add up to.
    if spec.y is not None:
        fig = go.Figure([go.Bar(
            x=data[spec.x], y=data[spec.y],
            customdata=_customdata(data), showlegend=False,
        )])
        return fig

    # Implicit-aggregation path. Weight column (when set) replaces the
    # row-count: `groupby(...)[weight].sum()` instead of `.size()`. Lets the
    # user plot "synapses by cell type" by binding `x=cell_type, weight=n_syn_in`
    # rather than the default "partners per cell type".
    use_weight = bool(spec.weight) and spec.weight in data.columns
    group_cols = [spec.x] + ([hue] if hue else [])
    if use_weight:
        # `dropna=False` on groupby so null x/hue still produces a bar; the
        # weight `.sum()` of an all-null bin is 0 (pandas skips NaN in sum).
        agg = (
            data.groupby(group_cols, dropna=False)[spec.weight]
                .sum()
                .reset_index(name=spec.weight)
        )
        y_col = spec.weight
    else:
        agg = data.groupby(group_cols, dropna=False).size().reset_index(name="count")
        y_col = "count"

    agg[spec.x] = agg[spec.x].fillna(NULL_LABEL).astype(str)

    # X-axis ordering. Categorical x goes case-folded alphabetical with the
    # null bucket pinned to the end — so "BC" sits in the same x-position
    # whether the user is looking at neuron A or neuron B, which is the
    # whole point of having shareable per-neuron plots: visual comparison
    # across views relies on stable axis layout. Numeric x keeps the
    # legacy "tallest bars first" sort (useful for a top-N read on a
    # discrete-numeric axis like num_soma).
    x_is_categorical = not pd.api.types.is_numeric_dtype(data[spec.x])
    x_categoryarray: list[str] | None = (
        _categorical_x_order(agg[spec.x], spec.x_universe) if x_is_categorical else None
    )

    if hue:
        agg[hue] = agg[hue].fillna(NULL_LABEL).astype(str)
        fig = go.Figure()
        # When the resolver computed a universe-pinned color_map, apply it
        # per trace so bar colors line up with the same hue value's color
        # in any scatter plot on the rail. Without a color_map we fall back
        # to plotly's colorway, which the SPA's theme injects from `--cat-*`.
        for hue_value, sub in agg.groupby(hue, dropna=False):
            label = NULL_LABEL if pd.isna(hue_value) else str(hue_value)
            marker = None
            if spec.color_map is not None:
                marker = {"color": spec.color_map.get(label, NULL_COLOR)}
            fig.add_trace(go.Bar(x=sub[spec.x], y=sub[y_col], name=label, marker=marker))
        fig.update_layout(barmode="stack")
        if x_categoryarray is not None:
            # categoryorder=array forces plotly to honor our explicit ordering
            # even when individual traces only contribute a subset of the x
            # values (the typical hue-split case).
            fig.update_xaxes(categoryorder="array", categoryarray=x_categoryarray)
        return fig

    # No hue: one trace. Sort by alphabetical x for categorical, otherwise
    # legacy y-descending. Per-bar colors still come from `color_map` when
    # the resolver populated one — keeps cell-type colors consistent even
    # without a hue binding.
    if x_categoryarray is not None:
        # `reindex` orders the bars to match `x_categoryarray`. When
        # `spec.x_universe` is set, the array also contains universe-only
        # values (cell types not present in this neuron's data). Filling
        # those missing rows with **explicit zeros** is the whole point of
        # the universe path — the user reads "this neuron has zero PV
        # partners" rather than "PV is missing from the chart". Hover shows
        # "0", which is the correct signal.
        agg = (
            agg.set_index(spec.x)
               .reindex(x_categoryarray)
               .reset_index()
        )
        agg[y_col] = agg[y_col].fillna(0)
    else:
        agg = agg.sort_values(y_col, ascending=False)
    # `showlegend=False` on the single-trace path so plotly doesn't render a
    # legend with an auto-named "trace 0" entry — there's no hue split to
    # disambiguate, the bar speaks for itself. Multi-trace branches above
    # keep the legend (each trace is a hue value).
    bar_kwargs: dict = {"x": agg[spec.x], "y": agg[y_col], "showlegend": False}
    if spec.color_map is not None:
        bar_kwargs["marker"] = {
            "color": [spec.color_map.get(v, NULL_COLOR) for v in agg[spec.x]],
        }
    fig = go.Figure([go.Bar(**bar_kwargs)])
    if x_categoryarray is not None:
        fig.update_xaxes(categoryorder="array", categoryarray=x_categoryarray)
    return fig


def _build_histogram(data: pd.DataFrame, spec: PlotSpec) -> go.Figure:
    """Histogram of `x` (default) or `y`. The resolver picks `kind=histogram`
    when only one of x/y is bound on a dynamic spec — this builder honors
    whichever side is set. `showlegend=False` because there's only one trace
    and plotly's default "trace 0" label adds no information.
    """
    if spec.x is None and spec.y is None:
        raise ValueError("histogram requires `x` or `y`")
    if spec.x is not None:
        fig = go.Figure([go.Histogram(x=data[spec.x], nbinsx=spec.bins, showlegend=False)])
    else:
        fig = go.Figure([go.Histogram(y=data[spec.y], nbinsy=spec.bins, showlegend=False)])
    return fig


# --- scatter + hue rules --------------------------------------------------

# Three-tier hue convention. Backend-side enforcement keeps the policy in one
# place, and the resolver can return a clean 422 when the user binds a hue
# column with too many distinct non-numeric values to be meaningfully colored.
# `_HUE_PALETTE_MAX` is 10 to align with `frontend/src/styles.css`'s
# `--cat-*` tokens (and matplotlib's tab10) so plotly's colorway and our
# explicit-color path produce identical hexes for ≤10 distinct values.
_HUE_PALETTE_MAX = 10         # ≤10 → split per category, distinct hues
_HUE_GREYSCALE_MAX = 30       # 11–30 → split per category, greyscale ramp / HSL
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


def _build_scatter(data: pd.DataFrame, spec: PlotSpec) -> go.Figure:
    if spec.x is None or spec.y is None:
        raise ValueError("scatter plot requires both `x` and `y`")
    hue = _resolve_hue(spec)
    customdata_all = _customdata(data)

    # Default radius matches `_build_stripplot`'s `POINT_SIZE` so the analytics
    # rail's two density-style plots read with a consistent dot weight.
    # Bound `size` swaps the scalar for a per-point series via `_scale_size`.
    marker_size: pd.Series | float = 4.0
    if spec.size and spec.size in data.columns:
        marker_size = _scale_size(data[spec.size])

    fig = go.Figure()
    if hue is None or hue not in data.columns:
        marker = {"size": marker_size if not isinstance(marker_size, float) else marker_size}
        # Single trace with no hue split → no legend (auto-named "trace 0"
        # otherwise). Hue branches below keep the legend per-trace.
        fig.add_trace(go.Scatter(
            x=data[spec.x], y=data[spec.y],
            mode="markers", marker=marker,
            customdata=customdata_all,
            showlegend=False,
        ))
        return fig

    hue_col = data[hue]
    n_unique = int(hue_col.nunique(dropna=False))
    is_numeric = pd.api.types.is_numeric_dtype(hue_col)

    # When the resolver populated a universe-pinned color_map (cell-type
    # column case), every tier below uses it for `marker.color`. The map's
    # NULL_LABEL key is NULL_COLOR, so missing-bucket coloring is automatic.
    color_map = spec.color_map

    if n_unique <= _HUE_PALETTE_MAX:
        # Categorical palette. Without color_map we let plotly cycle through
        # the SPA's `--cat-*` colorway. With color_map we override per trace
        # so the same hue value lands on the same color across every plot.
        for value, sub in data.groupby(hue_col.fillna(NULL_LABEL), dropna=False):
            label = NULL_LABEL if pd.isna(value) else str(value)
            sub_marker_size = marker_size.loc[sub.index] if hasattr(marker_size, "loc") else marker_size
            marker: dict = {"size": sub_marker_size}
            if color_map is not None:
                marker["color"] = color_map.get(label, NULL_COLOR)
            fig.add_trace(go.Scatter(
                x=sub[spec.x], y=sub[spec.y],
                mode="markers", name=label,
                marker=marker,
                customdata=sub["root_id"].astype(str).tolist() if "root_id" in sub.columns else None,
            ))
        return fig

    if n_unique <= _HUE_GREYSCALE_MAX:
        # 11-30 distinct values. Numeric values keep a sequential greyscale
        # ramp — preserves visual ordering, useful for discrete-numeric hue
        # like num_soma (0, 1, 2, ...). Non-numeric (e.g. cell_type with 18
        # labels) gets either the universe-pinned color_map (for cell-type
        # hues) or an HSL-rotation palette (for everything else) so labels
        # don't read as an ordered gradient.
        ramp = _greyscale_ramp(n_unique) if is_numeric else _categorical_palette(n_unique)
        for i, (value, sub) in enumerate(data.groupby(hue_col.fillna(NULL_LABEL), dropna=False)):
            label = NULL_LABEL if pd.isna(value) else str(value)
            sub_marker_size = marker_size.loc[sub.index] if hasattr(marker_size, "loc") else marker_size
            color = (
                color_map.get(label, NULL_COLOR)
                if (color_map is not None and not is_numeric)
                else ramp[i]
            )
            fig.add_trace(go.Scatter(
                x=sub[spec.x], y=sub[spec.y],
                mode="markers", name=label,
                marker={"size": sub_marker_size, "color": color},
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

    # >30 numeric: single trace, continuous colorscale. The colorbar handles
    # the hue legend visually, so no need for a per-trace legend entry.
    marker = {
        "size": marker_size,
        "color": pd.to_numeric(hue_col, errors="coerce"),
        "colorscale": _VIRIDIS_NAME,
        "showscale": True,
        "colorbar": {"title": {"text": _format_label(hue), "font": {"size": 10}}},
    }
    fig.add_trace(go.Scatter(
        x=data[spec.x], y=data[spec.y],
        mode="markers", marker=marker, showlegend=False,
        customdata=customdata_all,
    ))
    return fig


def _categorical_x_order(x_str: pd.Series, universe: list | None = None) -> list[str]:
    """Case-folded alphabetical order for the x-axis, with the null bucket
    pinned to the end (only when null is actually observed).

    When `universe` is given, every value in it occupies an x-axis slot —
    cell types not present in the current neuron's data still appear as
    empty buckets so the user reads "true zero" instead of "missing data".
    Observed-only values that aren't in the universe are still kept too:
    proofreading drift between the cached universe and the current frame
    shouldn't make a row vanish from the chart.

    When `universe` is None (intrinsic / numeric / synthetic x), only the
    observed values are listed — the universe path doesn't apply.
    """
    observed = list(dict.fromkeys(x_str.tolist()))
    has_null = NULL_LABEL in observed
    if universe:
        keys = {str(v) for v in universe if v is not None and str(v) != NULL_LABEL}
        keys.update(v for v in observed if v != NULL_LABEL)
        ordered = sorted(keys, key=lambda s: s.casefold())
    else:
        ordered = sorted((v for v in observed if v != NULL_LABEL), key=lambda s: s.casefold())
    if has_null:
        ordered.append(NULL_LABEL)
    return ordered


def _build_stripplot(data: pd.DataFrame, spec: PlotSpec) -> go.Figure:
    """Categorical-x by numeric-y rendered as a jittered point cloud per
    bucket.

    The user binds `x=cell_type, y=net_size_out` and gets one strip per cell
    type — same x-axis ordering as the bar plot, so a stripplot of synapse
    sizes can sit alongside a bar of synapse counts and the columns line up
    one-to-one. Hue gets the universe-pinned color_map and renders side-by-
    side strips within each x bucket via `boxmode='group'`. Without hue,
    each x bucket is its own trace so the universe color_map maps cleanly
    bucket → color (mirrors `_build_bar`'s no-hue branch).

    Implemented on `go.Box` with the box itself made transparent — this is
    the documented plotly idiom for a stripplot. `boxpoints='all'` renders
    every underlying row; `jitter` spreads them horizontally so dense
    clusters don't overlap.
    """
    if spec.x is None or spec.y is None:
        raise ValueError("stripplot requires both `x` and `y`")
    hue = _resolve_hue(spec)

    HIDDEN_BOX = dict(
        fillcolor="rgba(0,0,0,0)",
        line=dict(color="rgba(0,0,0,0)"),
    )
    # Tuned for dense connectomics distributions: heavy stacking happens at
    # the low end of `net_size` etc., so we lean on transparency + spread to
    # let the density read visually.
    #   - jitter 0.7 (≈ 70% of the bucket width) so points fill the column
    #   - marker.size 4 — small enough that 50+ overlapping dots still
    #     reveal individual contributors
    #   - marker.opacity 0.55 — ~3 stacked dots saturate to ~90% opacity, so
    #     the user can tell "a few" from "many" by darkness alone
    POINT_JITTER = 0.7
    POINT_SIZE = 4
    POINT_OPACITY = 0.55

    x_str = data[spec.x].fillna(NULL_LABEL).astype(str)

    fig = go.Figure()
    if hue is None or hue not in data.columns:
        # No hue → one trace per x bucket so the color_map maps cleanly
        # bucket → color. Legend is suppressed because each trace is just
        # a redundant copy of the x-axis label.
        for label, sub in data.assign(_x=x_str).groupby("_x", dropna=False, sort=False):
            color = (
                spec.color_map.get(label, NULL_COLOR)
                if spec.color_map is not None
                else None
            )
            marker: dict = {"size": POINT_SIZE, "opacity": POINT_OPACITY}
            if color is not None:
                marker["color"] = color
            fig.add_trace(go.Box(
                x=[label] * len(sub),
                y=sub[spec.y],
                name=label,
                showlegend=False,
                boxpoints="all",
                jitter=POINT_JITTER,
                pointpos=0,
                marker=marker,
                customdata=sub["root_id"].astype(str).tolist() if "root_id" in sub.columns else None,
                **HIDDEN_BOX,
            ))
    else:
        # Hue → one trace per hue value. `boxmode='group'` side-by-sides them
        # within each x bucket so direction=pre and direction=post for the
        # same cell type sit next to each other rather than overlapping.
        hue_str = data[hue].fillna(NULL_LABEL).astype(str)
        for value, sub in data.assign(_x=x_str, _hue=hue_str).groupby("_hue", dropna=False, sort=False):
            label = NULL_LABEL if pd.isna(value) else str(value)
            color = (
                spec.color_map.get(label, NULL_COLOR)
                if spec.color_map is not None
                else None
            )
            marker = {"size": POINT_SIZE, "opacity": POINT_OPACITY}
            if color is not None:
                marker["color"] = color
            fig.add_trace(go.Box(
                x=sub["_x"],
                y=sub[spec.y],
                name=label,
                boxpoints="all",
                jitter=POINT_JITTER,
                pointpos=0,
                marker=marker,
                customdata=sub["root_id"].astype(str).tolist() if "root_id" in sub.columns else None,
                **HIDDEN_BOX,
            ))
        fig.update_layout(boxmode="group")

    # Pin every universe value as an x-axis slot — empty buckets show as
    # labels with no points (the "true zero" signal mirrored from bars).
    fig.update_xaxes(
        categoryorder="array",
        categoryarray=_categorical_x_order(x_str, spec.x_universe),
    )
    return fig


_BUILDERS = {
    "bar": _build_bar,
    "histogram": _build_histogram,
    "scatter": _build_scatter,
    "stripplot": _build_stripplot,
}


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
    """Reverse the y-axis when y is bound to a depth-shaped column so pia
    sits at the top, matching the anatomical convention. Only the y-axis
    flips — flipping the x-axis would just reverse reading order without
    aiding interpretation, so a horizontal histogram of `soma_depth` keeps
    its natural left-to-right (pia → white matter) layout.
    """
    if _is_depth_column(spec.y):
        fig.update_yaxes(autorange="reversed")


# Depth-guide styling. Subtle gray lines + slightly stronger labels so the
# guides read as background context — the data points should remain the
# visual focus. `dash="dot"` distinguishes layer boundaries from a chart's
# normal axis gridlines (solid).
_DEPTH_LINE_COLOR = "rgba(120, 120, 120, 0.45)"
_DEPTH_LABEL_COLOR = "rgba(120, 120, 120, 0.95)"


def _target_oriented_position(
    nq: NeuronQuery, transform
) -> dict[str, float] | None:
    """Compute the target (root) neuron's soma position in oriented coords.

    Returns `{soma_depth, soma_x, soma_z}` (all µm) or None when either the
    soma position isn't available (soma table missing / target not in the
    soma table) or when no transform is configured for this datastack.
    Callers degrade silently — the marker is a nicety, not load-bearing.

    Mirrors the per-partner pipeline (`compute_partner_spatial`) so the
    marker lands in the exact same coordinate frame as the data points
    it annotates. `soma_x` / `soma_z` come from the tangential axes
    (output[0] / output[2]); `soma_depth` from the depth axis (output[1]).
    """
    if transform is None:
        return None
    pos = nq.soma_summary().get("soma_pt_position")
    if pos is None:
        return None
    import numpy as _np
    try:
        # Module-private constants on `spatial`; re-importing here keeps
        # plots.py from depending on spatial at import time (same lazy
        # pattern resolve_plot uses for `attach_spatial_features`).
        from .spatial import _apply_transform, _DEPTH_AXIS, _TANGENTIAL_AXES
        transformed = _apply_transform(transform, _np.array(pos, dtype=float))
        return {
            "soma_depth": float(transformed[0][_DEPTH_AXIS]),
            "soma_x": float(transformed[0][_TANGENTIAL_AXES[0]]),
            "soma_z": float(transformed[0][_TANGENTIAL_AXES[1]]),
        }
    except Exception:
        return None


# Reference-marker styling for the cell-position glyph. Black on light
# backgrounds, semi-transparent so it reads as a guide rather than a
# data point. `circle-open` keeps the inside transparent so it doesn't
# obscure data points sitting at the same coordinate.
_CELL_MARKER_COLOR = "rgba(0, 0, 0, 0.85)"
_CELL_MARKER_SIZE = 14
_CELL_MARKER_LINE_WIDTH = 1.2


def _axis_target_value(
    col: str | None, target_pos: dict[str, float] | None
) -> tuple[float | None, str | None]:
    """Return `(value, kind)` for a bound axis when the target neuron has
    an analogue in the oriented frame.

    `kind` is the column family — `"depth"` for any depth-shaped column
    (`soma_depth`, `median_syn_depth_out`, ...), `"soma_x"` / `"soma_z"`
    for the tangential axes. Used by the marker code to label its hover
    string and by the SPA-side gate to decide whether to show the toggle.

    Decoration columns (`<table>.<col>`) are stripped to their bare name
    before classification — same convention as `_is_depth_column`.
    """
    if not col or not target_pos:
        return None, None
    bare = col.rsplit(".", 1)[-1]
    if _is_depth_column(bare):
        return target_pos["soma_depth"], "depth"
    if bare == "soma_x":
        return target_pos["soma_x"], "soma_x"
    if bare == "soma_z":
        return target_pos["soma_z"], "soma_z"
    return None, None


def _apply_cell_position_marker(
    fig: go.Figure,
    spec: PlotSpec,
    target_pos: dict[str, float] | None,
) -> None:
    """Annotate the chart with the target neuron's own location.

    Per axis, classifies the bound column against the cell's oriented
    coords:
      - depth-shaped (`soma_depth`, `median_syn_depth_*`) → cell's soma_depth
      - `soma_x` → cell's soma_x
      - `soma_z` → cell's soma_z

    Then:
      - **Both axes mappable** → single open black circle at the target's
        coordinate. For an `soma_x` × `soma_z` scatter this marks the
        cell's actual position in the cortex-flat plane; for a
        `soma_depth` × `median_syn_depth_out` scatter it sits on the
        diagonal at (target_depth, target_depth) and reads as a depth
        reference rather than a topographic location (per the SPA
        tooltip on the toggle).
      - **One axis mappable** → thin black dashed line at the target's
        value on that axis (hline if y is the spatial axis, vline if x).
      - **Neither** → no-op.

    No-op when `target_pos` is None. Lines / markers live on
    `layer="below"` so data traces remain the visual focus.
    """
    if target_pos is None:
        return
    x_val, x_kind = _axis_target_value(spec.x, target_pos)
    y_val, y_kind = _axis_target_value(spec.y, target_pos)
    if x_val is None and y_val is None:
        return

    if x_val is not None and y_val is not None:
        # Both axes spatial. Open circle keeps the glyph from obscuring
        # data points at the same coordinate. Hover names the axes —
        # cleaner than the raw values alone, especially for the diagonal
        # case where the two coords numerically equal each other.
        fig.add_trace(go.Scatter(
            x=[x_val],
            y=[y_val],
            mode="markers",
            marker={
                "symbol": "circle-open",
                "size": _CELL_MARKER_SIZE,
                "color": _CELL_MARKER_COLOR,
                "line": {"width": _CELL_MARKER_LINE_WIDTH, "color": _CELL_MARKER_COLOR},
            },
            name="cell soma",
            showlegend=False,
            hovertemplate=(
                f"cell soma<br>{x_kind}: {x_val:.1f}<br>{y_kind}: {y_val:.1f}<extra></extra>"
            ),
        ))
        return

    line_kwargs = dict(
        color=_CELL_MARKER_COLOR,
        width=_CELL_MARKER_LINE_WIDTH,
        dash="dash",
    )
    if y_val is not None:
        fig.add_hline(y=y_val, line=line_kwargs, layer="below")
    else:
        fig.add_vline(x=x_val, line=line_kwargs, layer="below")


def _apply_depth_guides(
    fig: go.Figure,
    spec: PlotSpec,
    depth_range: list[float] | None,
    layer_boundaries: list[float] | None,
    layer_names: list[str] | None,
) -> None:
    """Per-datastack background guides on depth-axis plots. Two effects:

    1. **Range fix.** When `depth_range` is set, the depth axis (whichever
       of x or y is bound to a depth-shaped column) is pinned to that
       range — different neurons / different mat versions render in a
       shared coordinate system instead of each chart auto-fitting its
       own data extent.
    2. **Layer guides.** Each value in `layer_boundaries` becomes a
       dotted background line on the depth axis; `layer_names` (if
       supplied) annotates the regions between boundaries with
       cortical-layer labels (L1 / L2/3 / L4 / ...).

    No-op when both `depth_range` and `layer_boundaries` are absent, or
    when neither axis is bound to a depth column. Y-axis depth and x-axis
    depth are handled symmetrically — though the `_maybe_flip_depth` flip
    only applies on the y side, the range-pin here reverses the y-axis
    range tuple to preserve pia-on-top, and overrides any prior
    `autorange="reversed"`.
    """
    if not depth_range and not layer_boundaries:
        return
    x_is_depth = _is_depth_column(spec.x)
    y_is_depth = _is_depth_column(spec.y)
    if not x_is_depth and not y_is_depth:
        return

    # Build per-axis update dicts. `showgrid=False` + `zeroline=False`
    # suppress the default tick gridlines on the depth axis — the dotted
    # layer-boundary lines below serve the same "horizontal reference"
    # role, so leaving the regular grid on creates two parallel sets of
    # near-horizontal lines that read as visual noise. Tick labels stay
    # so the numeric scale remains readable.
    #
    # Range pin. y-axis range tuple is reversed (`[hi, lo]`) so plotly
    # renders pia at top while overriding any prior `autorange="reversed"`
    # — setting `range` already overrides autorange in plotly, but we
    # also pass `autorange=False` to be explicit.
    y_update: dict = {"showgrid": False, "zeroline": False}
    x_update: dict = {"showgrid": False, "zeroline": False}
    if depth_range and len(depth_range) == 2:
        lo, hi = float(depth_range[0]), float(depth_range[1])
        if y_is_depth:
            y_update["range"] = [hi, lo]
            y_update["autorange"] = False
        if x_is_depth:
            x_update["range"] = [lo, hi]
            x_update["autorange"] = False
    if y_is_depth:
        fig.update_yaxes(**y_update)
    if x_is_depth:
        fig.update_xaxes(**x_update)

    # Boundary lines. `layer="below"` puts them behind data traces so
    # bars / strips / scatter dots remain the visual focus.
    if layer_boundaries:
        for boundary in layer_boundaries:
            if y_is_depth:
                fig.add_hline(
                    y=float(boundary),
                    line=dict(color=_DEPTH_LINE_COLOR, width=1, dash="dot"),
                    layer="below",
                )
            if x_is_depth:
                fig.add_vline(
                    x=float(boundary),
                    line=dict(color=_DEPTH_LINE_COLOR, width=1, dash="dot"),
                    layer="below",
                )

    # Layer-name annotations at each region's midpoint. Only meaningful
    # when both `depth_range` (to bound the first/last region) and
    # `layer_names` are supplied. `layer_names[i]` labels the region
    # whose bottom is `layer_boundaries[i]`; trailing regions without a
    # name (e.g. white matter below L6) are simply unlabeled.
    if depth_range and layer_boundaries and layer_names:
        edges = [float(depth_range[0])] + [float(b) for b in layer_boundaries] + [float(depth_range[1])]
        for i, name in enumerate(layer_names):
            if i + 1 >= len(edges):
                break
            top, bottom = edges[i], edges[i + 1]
            mid = (top + bottom) / 2.0
            if y_is_depth:
                fig.add_annotation(
                    xref="paper", yref="y",
                    x=0.005, y=mid,
                    text=name, showarrow=False,
                    font=dict(size=10, color=_DEPTH_LABEL_COLOR),
                    xanchor="left", yanchor="middle",
                )
            elif x_is_depth:
                fig.add_annotation(
                    xref="x", yref="paper",
                    x=mid, y=0.99,
                    text=name, showarrow=False,
                    font=dict(size=10, color=_DEPTH_LABEL_COLOR),
                    xanchor="center", yanchor="top",
                )


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
    depth_range: list[float] | None = None,
    layer_boundaries: list[float] | None = None,
    layer_names: list[str] | None = None,
    cell_filters: list[CellFilter] | None = None,
    show_cell_depth: bool = True,
) -> dict:
    """Materialize `spec.data_query` against `nq` (with optional decoration),
    dispatch to the kind-specific builder, return Plotly figure JSON.

    Two override paths:
      - Legacy `column_override` — drops onto `spec.x` (single-axis column-
        bound plots).
      - `bindings: {x?, y?, hue?, size?, weight?}` — preferred. For dynamic
        specs (`spec.dynamic=True`), `kind` auto-resolves from bound axes:
        x AND y → scatter; one axis with non-numeric x or weight bound →
        bar; one axis with numeric x and no weight → histogram. Static specs
        still use their declared kind; bindings just override the channels.

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
        "weight": bindings.get("weight") if bindings.get("weight") is not None else spec.weight,
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
    # Kind auto-pick for dynamic specs is deferred until after the decoration
    # merge — we need to know whether `bound["x"]` is numeric on the resolved
    # frame to choose between histogram (numeric x → bin & count) and bar
    # (categorical x → discrete groups). Static specs keep their declared kind.
    spec = spec.model_copy(update={
        "x": bound["x"],
        "y": bound["y"],
        "hue": bound["hue"],
        "size": bound["size"],
        "weight": bound["weight"],
        "color": None,  # consumed; resolver works off `hue` now.
    })

    # Auto-extend decoration_tables to cover every table referenced by a cell
    # filter — the user's intent is "filter by these columns", they shouldn't
    # also have to remember to load the table. Cell-type table is its own slot,
    # so don't double-add it.
    cell_filters = cell_filters or []
    decoration_tables = list(decoration_tables or [])
    for f in cell_filters:
        if f.table != cell_type_table and f.table not in decoration_tables:
            decoration_tables.append(f.table)

    served: dict[int, dict] = {}
    needs_decoration = bool(cell_type_table or nq.soma_table or decoration_tables)
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

    # Apply cell filters AFTER decoration columns are materialized — predicates
    # reference `<table>.<col>` which only exists post-merge. Stash the pre/post
    # counts so the SPA can show "N / M cells" under the analytics rail.
    pre_filter_count = int(len(df))
    if cell_filters:
        df = _apply_cell_filters(df, cell_filters)
    matched_count = int(len(df))

    # Spatial features. Same two-tier rule as connectivity_bundle:
    #   - median_dist_to_target_soma — plain Euclidean, no transform needed
    #   - soma_depth, soma_x, soma_z, radial_dist_root_soma, median_syn_depth
    #     — require an oriented transform
    # Both tiers require partner soma positions, which means the soma
    # decoration must have been fetched above (it's part of `served`).
    if served:
        from .spatial import attach_spatial_features, load_streamline, load_transform
        transform = load_transform(spatial_transform_name) if spatial_transform_name else None
        streamline = load_streamline(spatial_transform_name) if spatial_transform_name else None
        root_soma = nq.soma_summary().get("soma_pt_position")
        source = spec.data_query.source
        # Unified frames need both directions' synapse stats; single-direction
        # frames only need the matching one. attach_spatial_features takes
        # None for the side it should skip.
        want_in = source in ("partners_in", "partners_both")
        want_out = source in ("partners_out", "partners_both")
        intrinsic, median_in, median_out, syn_depth_in, syn_depth_out = attach_spatial_features(
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
            for col in ("soma_depth", "soma_x", "soma_z", "radial_dist_root_soma"):
                df[col] = df["root_id"].astype(int).map(
                    lambda rid, _c=col: intrinsic.get(rid, {}).get(_c)
                )

        # Per-direction synapse-edge columns. Mirror the SPA's unified-table
        # schema: on `partners_both` they appear as `<col>_in` / `<col>_out`,
        # on single-direction sources just `<col>`. Two columns share this
        # plumbing — `median_dist_to_target_soma` and `median_syn_depth`.
        def _attach_per_direction(col_name: str, lookup_in: dict, lookup_out: dict) -> None:
            if source == "partners_both":
                if lookup_in:
                    df[f"{col_name}_in"] = df["root_id"].astype(int).map(
                        lambda rid, _l=lookup_in: _l.get(rid)
                    )
                if lookup_out:
                    df[f"{col_name}_out"] = df["root_id"].astype(int).map(
                        lambda rid, _l=lookup_out: _l.get(rid)
                    )
            else:
                lookup = lookup_in if source == "partners_in" else lookup_out
                if lookup:
                    df[col_name] = df["root_id"].astype(int).map(
                        lambda rid, _l=lookup: _l.get(rid)
                    )

        _attach_per_direction("median_dist_to_target_soma", median_in, median_out)
        _attach_per_direction("median_syn_depth", syn_depth_in, syn_depth_out)

    # Dynamic kind dispatch happens here (post-decoration-merge) so we can
    # inspect dtypes on the resolved frame:
    #   - x AND y, x categorical, y numeric → stripplot (one jittered cloud
    #     per x bucket; same x-axis ordering as bar so views align)
    #   - x AND y, both numeric (or both categorical) → scatter
    #   - x only, x non-numeric or weight bound → bar
    #   - x only, x numeric, no weight → histogram
    #   - y only → histogram
    if spec.dynamic:
        has_x = spec.x is not None
        has_y = spec.y is not None
        has_weight = spec.weight is not None
        if has_x and has_y:
            x_series = df[spec.x] if spec.x in df.columns else None
            y_series = df[spec.y] if spec.y in df.columns else None
            x_is_numeric = x_series is not None and pd.api.types.is_numeric_dtype(x_series)
            y_is_numeric = y_series is not None and pd.api.types.is_numeric_dtype(y_series)
            # Categorical x + numeric y is the stripplot signature. The
            # reverse (numeric x + categorical y) falls through to scatter
            # for now — if it turns out to be a common ask, swapping to a
            # horizontal stripplot is a one-line change.
            chosen = "stripplot" if (not x_is_numeric and y_is_numeric) else "scatter"
        elif has_x and not has_y:
            x_series = df[spec.x] if spec.x in df.columns else None
            x_is_numeric = x_series is not None and pd.api.types.is_numeric_dtype(x_series)
            chosen = "bar" if (not x_is_numeric or has_weight) else "histogram"
        elif has_y and not has_x:
            chosen = "histogram"
        else:
            raise ValueError(
                "dynamic plot needs at least one of `x` or `y` bound — pick a column."
            )
        spec = spec.model_copy(update={"kind": chosen})

    # Universe lookup helper. Returns the cached list of distinct values for
    # `col` when (a) the column exists on the resolved frame, (b) it's
    # categorical, and (c) provenance traces to a cell-type / decoration
    # table. Returns None for intrinsic / synthetic / numeric columns —
    # those fall through to plotly's default colorway and to observed-only
    # x-axis ordering.
    def _column_universe(col: str | None) -> list | None:
        if not col or col not in df.columns:
            return None
        if pd.api.types.is_numeric_dtype(df[col]):
            return None
        table, bare = _provenance_for(col, cell_type_table)
        if not table:
            return None
        universe = get_unique_values(
            client_factory=client_factory,
            ds=nq.datastack,
            mat_version=nq.mat_version,
            table=table,
            column=bare,
        )
        return universe or None

    hue_universe = _column_universe(spec.hue)
    # Stash on spec only for kinds where the x-axis is categorical and the
    # builder honors `spec.x_universe` (true-zero rendering on bar / strip).
    x_universe = (
        _column_universe(spec.x) if spec.kind in ("bar", "stripplot") else None
    )

    # Universe-pinned color map. Hue wins when both x and hue are categorical
    # and traceable — that's the conventional plotly convention (hue drives
    # color). Without hue, bar and stripplot fall back to coloring by the x
    # bucket so cell-type colors stay consistent with a hue-driven plot of
    # the same column elsewhere on the rail.
    color_map = None
    if hue_universe:
        color_map = resolve_categorical_color_map(
            universe=hue_universe,
            observed=df[spec.hue].dropna().unique().tolist(),
        )
    elif x_universe and not spec.hue:
        color_map = resolve_categorical_color_map(
            universe=x_universe,
            observed=df[spec.x].dropna().unique().tolist(),
        )
    spec = spec.model_copy(update={"color_map": color_map, "x_universe": x_universe})

    # Validate axes (x/y) strictly — there's no chart without them, so a
    # missing column should surface as a clear 422 the user can fix from
    # the URL. `weight` is a no-op on non-bar kinds (silently ignored)
    # so it's not in the strict-validation set.
    for ch in ("x", "y"):
        col = getattr(spec, ch)
        if col and col not in df.columns:
            raise ValueError(
                f"Column {col!r} (bound to `{ch}`) is not on the partner "
                f"records — pick one of the active decoration columns."
            )
    # Hue / size gracefully degrade when missing: drop the binding so the
    # chart still renders (no color split / fixed marker size) instead of
    # 422-ing the request. Common case: a preset binds `hue=cell_type`
    # but no cell-type table is loaded for this datastack — the SPA-side
    # presets.ts comment at STATIC_PLOT_PRESETS already documents this
    # as the intended degrade behavior; this enforces it server-side too.
    for ch in ("hue", "size"):
        col = getattr(spec, ch)
        if col and col not in df.columns:
            spec = spec.model_copy(update={ch: None})
    # Histogram needs *something* to bin; scatter and stripplot need both
    # axes; bar needs at least x.
    if spec.kind == "histogram" and not (spec.x or spec.y):
        raise ValueError("histogram needs `x` or `y` bound.")
    if spec.kind == "scatter" and (spec.x is None or spec.y is None):
        raise ValueError("scatter plot requires both `x` and `y` bound.")
    if spec.kind == "stripplot" and (spec.x is None or spec.y is None):
        raise ValueError("stripplot requires both `x` and `y` bound.")
    if spec.kind == "bar" and not spec.x:
        raise ValueError("bar plot requires `x` bound.")

    builder = _BUILDERS.get(spec.kind)
    if builder is None:
        raise ValueError(f"Unknown plot kind: {spec.kind!r}")
    fig = builder(df, spec)
    _apply_layout(fig, spec.layout)
    _apply_auto_titles(fig, spec)
    _maybe_flip_depth(fig, spec)
    _apply_depth_guides(fig, spec, depth_range, layer_boundaries, layer_names)
    if show_cell_depth:
        # Reuse the spatial transform already loaded for partner spatial
        # features (lazy-load if no decoration ran — common for plots whose
        # axes are intrinsic-only and which therefore skipped the soma path).
        from .spatial import load_transform as _lt
        target_pos = _target_oriented_position(nq, _lt(spatial_transform_name))
        _apply_cell_position_marker(fig, spec, target_pos)
    # Plotly's to_json returns a JSON string; parse it back so Flask jsonify
    # nests it as a real object rather than a quoted string.
    return {
        "figure": json.loads(fig.to_json()),
        "meta": {
            "matched_count": matched_count,
            "pre_filter_count": pre_filter_count,
            "filtered": bool(cell_filters),
        },
    }
