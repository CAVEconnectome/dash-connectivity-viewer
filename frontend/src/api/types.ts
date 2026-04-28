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

export interface TablesResponse {
  tables: { name: string; kind: "table" | "view" }[];
  mat_version: number | null;
}

export interface TableRowsResponse {
  datastack: string;
  table: string;
  is_view: boolean;
  offset: number;
  limit: number;
  filters: Record<string, unknown>;
  row_count: number;
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
}
