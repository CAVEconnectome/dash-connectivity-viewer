// Types mirror the JSON shapes returned by the Flask backend.

export interface ApiError {
  code: string;
  message: string;
  hint?: string | null;
  details?: Record<string, unknown>;
}

export interface DatastackInfo {
  datastack: string;
  aligned_volume: { name?: string; description?: string; image_source?: string };
  viewer_site: string | null;
  soma_table: string | null;
  synapse_table: string | null;
  voxel_resolution: [number, number, number] | null;
  live_mode: boolean;
}

export interface DatastacksListResponse {
  datastacks: string[];
}

export interface CellIdLookupResponse {
  // Either or both keys are populated; entries map to null on no match.
  cell_to_root: Record<string, string | null>;
  root_to_cell: Record<string, string | null>;
}

export interface VersionMetadata {
  version: number;
  expires_on: string | null;
  valid: boolean;
}

export interface VersionsResponse {
  versions: VersionMetadata[];
}

export interface TableListItem {
  name: string;
  kind: "table" | "view";
  /** Free-text description from CAVE table metadata. Long; the SPA truncates
   *  with a "show more" toggle. Null when the metadata endpoint had nothing
   *  for this table — happens for views (no batch view-metadata endpoint),
   *  or when the upstream metadata fetch failed. */
  description?: string | null;
  /** Annotation schema, e.g. "synapse", "cell_type_local", "cell_type_reference",
   *  "bound_tag". Useful as a chip — the user can scan for the kind of table
   *  they're after without reading every name. */
  schema_type?: string | null;
  /** When set, this is a reference table that points its `target_id` at rows
   *  in `reference_table`. Surfaced as a small "→ <table>" badge in the UI. */
  reference_table?: string | null;
  /** Voxel resolution in nm/voxel for this table's points. Mostly informative;
   *  shown compactly as "4×4×40 nm" in the card detail row. */
  voxel_resolution?: [number, number, number] | null;
  /** Row count on the materialized version we queried metadata against.
   *  Null when CAVE didn't populate `valid_row_count` for this table. */
  row_count?: number | null;
}

export interface TablesResponse {
  tables: TableListItem[];
  /** Mirrors the requested mode: `null` for live, integer for a specific
   *  materialization. The SPA's "tables (live)" / "v<N>" label keys off this. */
  mat_version: number | null;
  /** The version actually used to fetch the names + metadata. In live mode
   *  this resolves to the latest valid materialized version (CAVE doesn't
   *  expose a stable live table set). Lets the SPA disclose "live, showing
   *  v<N>" when it wants to without having to re-run the version lookup. */
  effective_mat_version: number | null;
}

/** Full distinct-string-values dict for a table, returned by the
 *  `/datastacks/<ds>/tables/<table>/values` endpoint. Maps each string-typed
 *  column to its complete universe of values across the entire table —
 *  not just the loaded slice — so category filter dropdowns surface every
 *  selectable choice even when the table is too large to load in full. */
export interface TableUniqueValuesResponse {
  table: string;
  values: Record<string, string[]>;
}

export interface TableRowsResponse {
  datastack: string;
  table: string;
  is_view: boolean;
  offset: number;
  limit: number;
  filters: Record<string, unknown>;
  row_count: number;
  /** True when the response was capped at `limit` and matching rows beyond
   *  the cap may exist. The SPA flips into "server mode" filter dispatch
   *  on this signal and shows a partial-results disclosure. */
  limit_hit: boolean;
  columns: string[];
  rows: Record<string, unknown>[];
}

// Note on root_id: int64 CAVE root ids exceed JS Number precision (float64,
// safe up to 2^53). The backend serializes them as JSON strings and the SPA
// keeps them as strings throughout — never call Number() on a root id.
export interface PartnerRecord {
  root_id: string;
  // Optional because the unified Both-tab row schema replaces this with a pair
  // of `n_syn_in` / `n_syn_out` columns; directional-tab rows always carry it.
  num_syn?: number;
  cell_type?: string | null;
  num_soma?: number;
  cell_id?: string | null;  // present only when num_soma == 1 (unique nucleus)
  // any aggregation columns from synapse_aggregation_rules:
  [k: string]: unknown;
}

export interface ConnectivitySummary {
  num_partners_in: number | null;
  num_partners_out: number | null;
  num_syn_in: number;
  num_syn_out: number;
  num_soma: number;
  soma_pt_position: [number, number, number] | null;
}

/**
 * One logical group of partner-record columns. The frontend renders these as
 * a two-row header: top row is the group `name` spanning its `columns`, bottom
 * row is the bare column header (last segment after the dot in dotted names).
 *
 * `kind`:
 *   "intrinsic" — root_id
 *   "synapse"   — num_syn + aggregation rules
 *   "cell_type" — the dedicated cell_type column (from `cell_type_table`)
 *   "soma"      — num_soma + cell_id
 *   "table"     — a generic decoration table; columns are dotted keys
 */
export interface ColumnGroup {
  name: string;
  kind: "intrinsic" | "synapse" | "cell_type" | "soma" | "table";
  columns: string[];
}

export interface ConnectivityBundle {
  datastack: string;
  root_id: string;
  version_used: number | "live";
  timestamp_used: string | null;
  synapse_table: string;
  soma_table: string | null;
  cell_type_table: string | null;
  partners_in?: PartnerRecord[];
  partners_out?: PartnerRecord[];
  /** The queried cell itself, shaped as a single partner-style record so
   *  the SPA's "Cell" tab can reuse the same column-rendering machinery
   *  as the partner tabs. Holds intrinsic + cell-type + decoration +
   *  spatial annotations; synapse-group fields don't apply (per-edge
   *  stats are per-partner by construction). */
  root_record?: PartnerRecord;
  summary?: ConnectivitySummary;
  synapse_columns_meta: {
    aggregation_rules: { name: string; column: string; agg: string }[];
    synapse_table: string;
  };
  column_groups: ColumnGroup[];
  decoration_revalidation: {
    ticket_id: string;
    pending_root_ids: string[];
    poll_url: string;
  } | null;
  /** Per-cell synapse-depth distribution. Populated only when the
   *  datastack has a `spatial.transform` configured. The summary panel
   *  in the analytics rail consumes this directly — `bin_edges` has
   *  N+1 entries; `counts_in` and `counts_out` are length-N parallel
   *  arrays of synapse counts in the oriented frame.
   *
   *  `depth_range` / `layer_boundaries` / `layer_names` echo the
   *  datastack-level spatial config so the client-side renderer can
   *  draw layer guides without a second fetch. All three are null when
   *  the datastack hasn't configured them. */
  synapse_depth_profile?: {
    bin_edges: number[];
    counts_in: number[];
    counts_out: number[];
    depth_axis_name: string;
    depth_range: [number, number] | null;
    layer_boundaries: number[] | null;
    layer_names: string[] | null;
  };
}

export interface LinkResponse {
  url: string;
  shortened: boolean;
}

// Plotly's figure JSON. We don't try to type the full Plotly trace shape —
// react-plotly.js consumes it as `data`/`layout` directly. The backend builds
// it server-side via go.Figure.to_json().
export interface PlotResponse {
  figure: { data: unknown[]; layout: Record<string, unknown> };
  meta?: {
    /** Rows after cell-filter mask (or before, if no filter is active). */
    matched_count: number;
    /** Rows before cell-filter mask. Equal to matched_count when no filter. */
    pre_filter_count: number;
    filtered: boolean;
  };
}
