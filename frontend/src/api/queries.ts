import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type {
  CellIdLookupResponse,
  ConnectivityBundle,
  DatastackInfo,
  LinkResponse,
  PlotResponse,
  TableRowsResponse,
  TablesResponse,
  VersionsResponse,
} from "./types";

export function useDatastackInfo(ds: string | null) {
  return useQuery<DatastackInfo>({
    queryKey: ["info", ds],
    queryFn: () => apiFetch<DatastackInfo>(`/api/v1/datastacks/${ds}/info`),
    enabled: !!ds,
    staleTime: 60 * 60 * 1000, // 1h — info_cache is server-side too
  });
}

export function useVersions(ds: string | null) {
  return useQuery<VersionsResponse>({
    queryKey: ["versions", ds],
    queryFn: () => apiFetch<VersionsResponse>(`/api/v1/datastacks/${ds}/versions`),
    enabled: !!ds,
    staleTime: 60 * 60 * 1000,
  });
}

export function useTables(ds: string | null, matVersion: number | "live" | null) {
  return useQuery<TablesResponse>({
    queryKey: ["tables", ds, matVersion],
    queryFn: () =>
      apiFetch<TablesResponse>(`/api/v1/datastacks/${ds}/tables`, {
        query: { mat_version: matVersion === "live" ? undefined : matVersion ?? undefined },
      }),
    enabled: !!ds,
    staleTime: 60 * 60 * 1000,
  });
}

export interface TableRowsArgs {
  ds: string;
  table: string;
  matVersion: number | "live" | null;
  limit?: number;
  offset?: number;
  isView?: boolean;
  // Reserved column-filters: anything else here is forwarded as ?col=val.
  filters?: Record<string, string>;
}

export function useTableRows(args: TableRowsArgs | null) {
  return useQuery<TableRowsResponse>({
    queryKey: args
      ? ["table_rows", args.ds, args.table, args.matVersion, args.limit, args.offset, args.isView, args.filters]
      : ["table_rows", "disabled"],
    queryFn: () =>
      apiFetch<TableRowsResponse>(
        `/api/v1/datastacks/${args!.ds}/tables/${args!.table}/rows`,
        {
          query: {
            mat_version: args!.matVersion === "live" ? undefined : args!.matVersion ?? undefined,
            limit: args!.limit ?? 1000,
            offset: args!.offset ?? 0,
            is_view: args!.isView === undefined ? undefined : args!.isView ? "true" : "false",
            ...(args!.filters ?? {}),
          },
        },
      ),
    enabled: !!args && !!args.table,
    staleTime: 5 * 60 * 1000,
  });
}

export interface ConnectivityArgs {
  ds: string;
  rootId: string;  // string to preserve int64 precision (see types.ts)
  matVersion: number | "live" | null;
  include?: ("partners_in" | "partners_out" | "summary")[];
  cellTypeTable?: string | null;
  decorationTables?: string[];
}

export function useConnectivity(args: ConnectivityArgs | null) {
  const queryKey: QueryKey = args
    ? ["connectivity", args.ds, args.rootId, args.matVersion, args.cellTypeTable,
       (args.decorationTables ?? []).join(","), args.include]
    : ["connectivity", "disabled"];

  const query = useQuery<ConnectivityBundle>({
    queryKey,
    queryFn: () =>
      apiFetch<ConnectivityBundle>(
        `/api/v1/datastacks/${args!.ds}/neuron/${args!.rootId}/connectivity`,
        {
          method: "POST",
          query: { mat_version: args!.matVersion === "live" ? undefined : args!.matVersion ?? undefined },
          body: {
            include: args!.include ?? ["partners_in", "partners_out", "summary"],
            cell_type_table: args!.cellTypeTable ?? null,
            decoration_tables: args!.decorationTables ?? [],
          },
        },
      ),
    enabled: !!args && !!args.rootId,
    staleTime: 5 * 60 * 1000, // matches server query_cache TTL roughly
  });

  useDecorationRevalidationPoll(query.data, queryKey);
  return query;
}

interface DecorationPollResponse {
  status: "ready" | "in_flight" | "expired";
  retry_after?: number;
  deltas?: Record<string, { cell_type?: string | null; num_soma?: number }>;
}

/**
 * When the connectivity bundle response carries `decoration_revalidation`, the
 * server has served stale cell_type/num_soma values and queued a background
 * refresh. This effect schedules a single delayed poll, then on `ready` merges
 * the deltas into the cached bundle so any displayed cell_type / num_soma
 * column updates without a full refetch. Self-healing: a failed poll falls
 * through silently — the next /connectivity request will reflect the truth.
 */
function useDecorationRevalidationPoll(
  bundle: ConnectivityBundle | undefined,
  queryKey: QueryKey,
): void {
  const qc = useQueryClient();
  const ticketId = bundle?.decoration_revalidation?.ticket_id ?? null;
  const pollUrl = bundle?.decoration_revalidation?.poll_url ?? null;

  useEffect(() => {
    if (!ticketId || !pollUrl) return;
    let cancelled = false;
    let timer: number | null = null;

    const tick = (delayMs: number) => {
      timer = window.setTimeout(async () => {
        if (cancelled) return;
        try {
          const resp = await apiFetch<DecorationPollResponse>(pollUrl);
          if (cancelled) return;
          if (resp.status === "ready" && resp.deltas) {
            qc.setQueryData<ConnectivityBundle>(queryKey, (prev) =>
              prev ? mergeDecorationDeltas(prev, resp.deltas!) : prev,
            );
          } else if (resp.status === "in_flight") {
            tick((resp.retry_after ?? 2) * 1000);
          }
          // status === "expired": nothing to do; ticket is gone.
        } catch {
          // Swallow: best-effort. Next /connectivity will reflect the latest.
        }
      }, delayMs);
    };

    tick(3000); // first poll after 3s — gives the background revalidation time to land
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [ticketId, pollUrl, queryKey, qc]);
}

function mergeDecorationDeltas(
  bundle: ConnectivityBundle,
  deltas: Record<string, { cell_type?: string | null; num_soma?: number }>,
): ConnectivityBundle {
  const apply = (rows: ConnectivityBundle["partners_in"]) => {
    if (!rows) return rows;
    return rows.map((r) => {
      const d = deltas[r.root_id];
      return d ? { ...r, ...d } : r;
    });
  };
  return {
    ...bundle,
    partners_in: apply(bundle.partners_in),
    partners_out: apply(bundle.partners_out),
    decoration_revalidation: null, // ticket consumed; clear so we don't re-poll
  };
}

export interface MakeLinkArgs {
  ds: string;
  template: string;
  rootId: string;
  selectedPartnerIds?: string[];
  matVersion: number | "live" | null;
}

export interface PlotBindings {
  x?: string | null;
  y?: string | null;
  hue?: string | null;
  size?: string | null;
  x_scope?: "pre" | "post" | "both" | null;
  y_scope?: "pre" | "post" | "both" | null;
}

export interface PlotArgs {
  ds: string;
  spec: string;          // plot spec name, matches templates/plots/<name>.yaml
  rootId: string;
  matVersion: number | "live" | null;
  decorationTables?: string[];
  /** Legacy single-column override (column-bound plots). Maps to `bindings.x`
   *  on the backend. New code should use `bindings` directly. */
  column?: string | null;
  /** Multi-channel binding: backend auto-picks chart kind for `dynamic` specs
   *  (1 axis → histogram, 2 axes → scatter). Wins over `column` when set. */
  bindings?: PlotBindings | null;
}

function bindingsCacheKey(b: PlotBindings | null | undefined): string {
  if (!b) return "";
  return `${b.x ?? ""}|${b.y ?? ""}|${b.hue ?? ""}|${b.size ?? ""}|${b.x_scope ?? ""}|${b.y_scope ?? ""}`;
}

function hasAnyBinding(b: PlotBindings | null | undefined): boolean {
  if (!b) return false;
  return !!(b.x || b.y || b.hue || b.size);
}

export function usePlot(args: PlotArgs | null) {
  return useQuery<PlotResponse>({
    queryKey: args
      ? ["plot", args.ds, args.spec, args.rootId, args.matVersion,
         (args.decorationTables ?? []).join(","), args.column ?? "", bindingsCacheKey(args.bindings)]
      : ["plot", "disabled"],
    queryFn: () =>
      apiFetch<PlotResponse>(
        `/api/v1/datastacks/${args!.ds}/plots/${args!.spec}`,
        {
          method: "POST",
          query: { mat_version: args!.matVersion === "live" ? undefined : args!.matVersion ?? undefined },
          body: {
            root_id: args!.rootId,
            decoration_tables: args!.decorationTables ?? [],
            column: args!.column ?? null,
            bindings: args!.bindings ?? undefined,
          },
        },
      ),
    // Disabled when nothing is bound — the backend would 422 on a dynamic spec
    // with no axes; legacy column-bound plots gate on `column`.
    enabled: !!args && !!args.rootId && (!!args.column || hasAnyBinding(args.bindings)),
    staleTime: 5 * 60 * 1000,
  });
}

export interface CellIdLookupArgs {
  ds: string;
  matVersion: number | "live" | null;
  cellIds?: string[];
  rootIds?: string[];
}

export function useCellIdLookupMutation() {
  return useMutation<CellIdLookupResponse, Error, CellIdLookupArgs>({
    mutationFn: (args) =>
      apiFetch<CellIdLookupResponse>(
        `/api/v1/datastacks/${args.ds}/cell-ids/lookup`,
        {
          method: "POST",
          query: { mat_version: args.matVersion === "live" ? undefined : args.matVersion ?? undefined },
          body: {
            cell_ids: args.cellIds ?? [],
            root_ids: args.rootIds ?? [],
          },
        },
      ),
  });
}

export function useMakeLinkMutation() {
  return useMutation<LinkResponse, Error, MakeLinkArgs>({
    mutationFn: (args) =>
      apiFetch<LinkResponse>(`/api/v1/datastacks/${args.ds}/links`, {
        method: "POST",
        query: { mat_version: args.matVersion === "live" ? undefined : args.matVersion ?? undefined },
        body: {
          template: args.template,
          query: {
            root_id: args.rootId,
            selected_partner_ids: args.selectedPartnerIds,
          },
        },
      }),
  });
}
