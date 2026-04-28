import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  type ColumnDef,
  type ColumnFiltersState,
  type SortingState,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { useTableRows } from "../api/queries";
import { useUrlParam } from "../hooks/useUrlState";
import { FilterInput, formatCell, inferKind, type ColumnKind } from "./tableColumns";

const PAGE_SIZE = 50;
const ROW_LIMIT = 1000;

export function TableRowsView() {
  const { name } = useParams<{ name: string }>();
  const [ds] = useUrlParam("ds");
  const [mv] = useUrlParam("mv");
  const matVersion = mv ? Number(mv) : "live";
  const navigate = useNavigate();

  const data = useTableRows(ds && name ? { ds, table: name, matVersion, limit: ROW_LIMIT } : null);

  const [sorting, setSorting] = useState<SortingState>([]);
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);

  const rows = data.data?.rows ?? [];
  const columnNames = useMemo(() => data.data?.columns ?? [], [data.data?.columns]);

  // The first root-id-bearing column becomes the cross-nav target. Joined
  // tables expose `pt_root_id` from the reference table; some custom views
  // may use other names.
  const rootIdColumn = useMemo(() => {
    const candidates = ["pt_root_id", "valid_id_root_id", "target_id_root_id"];
    return candidates.find((c) => columnNames.includes(c)) ?? null;
  }, [columnNames]);

  const columnKinds = useMemo(() => {
    const kinds: Record<string, ColumnKind> = {};
    for (const c of columnNames) kinds[c] = inferKind(c, rows);
    return kinds;
  }, [columnNames, rows]);

  const categoryOptions = useMemo(() => {
    const options: Record<string, string[]> = {};
    for (const c of columnNames) {
      if (columnKinds[c] !== "category") continue;
      const values = new Set<string>();
      for (const r of rows) {
        const v = r[c];
        if (v === null || v === undefined) values.add("(none)");
        else values.add(String(v));
      }
      options[c] = [...values].sort();
    }
    return options;
  }, [columnNames, columnKinds, rows]);

  const columns = useMemo<ColumnDef<Record<string, unknown>>[]>(
    () =>
      columnNames.map((c) => {
        const kind = columnKinds[c];
        const def: ColumnDef<Record<string, unknown>> = {
          id: c,
          accessorFn: (row) => row[c],
          header: c,
          cell: (ctx) => formatCell(ctx.getValue()),
          sortingFn: kind === "number" ? "basic" : "alphanumeric",
          filterFn: filterFnFor(kind, c),
        };
        return def;
      }),
    [columnNames, columnKinds],
  );

  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting, columnFilters },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: PAGE_SIZE } },
  });

  const filteredCount = table.getFilteredRowModel().rows.length;

  const goToNeuron = (rid: string) => {
    if (!ds || !name) return;
    const params = new URLSearchParams({ ds, root: rid });
    if (mv) params.set("mv", mv);
    params.set("from", `table:${name}`);
    navigate(`/neuron?${params}`);
  };

  if (!ds || !name) return <p>Pick a datastack and a table.</p>;

  const backCarry = new URLSearchParams();
  if (ds) backCarry.set("ds", ds);
  if (mv) backCarry.set("mv", mv);

  return (
    <div className="table-rows-view">
      <h2>
        <Link to={`/tables?${backCarry}`}>tables</Link> / {name}
      </h2>
      {data.isFetching && <p>Loading…</p>}
      {data.error && <p className="error">{(data.error as Error).message}</p>}
      {data.data && (
        <div className="partners">
          <div className="actions">
            <span className="page">
              {filteredCount === rows.length
                ? `${rows.length} rows`
                : `${filteredCount} of ${rows.length} rows`}
              {rows.length === ROW_LIMIT && (
                <em> (page-1 limit; raise ROW_LIMIT to fetch more)</em>
              )}
            </span>
            <button onClick={() => table.previousPage()} disabled={!table.getCanPreviousPage()}>‹</button>
            <span className="page">
              {table.getState().pagination.pageIndex + 1} / {Math.max(1, table.getPageCount())}
            </span>
            <button onClick={() => table.nextPage()} disabled={!table.getCanNextPage()}>›</button>
            {(columnFilters.length > 0 || sorting.length > 0) && (
              <button onClick={() => { setColumnFilters([]); setSorting([]); }}>Reset</button>
            )}
          </div>

          <table>
            <thead>
              <tr>
                {table.getHeaderGroups()[0].headers.map((header) => {
                  const sort = header.column.getIsSorted();
                  const indicator = sort === "asc" ? " ▲" : sort === "desc" ? " ▼" : "";
                  return (
                    <th key={header.id}>
                      <button className="sortable" onClick={header.column.getToggleSortingHandler()}>
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {indicator}
                      </button>
                    </th>
                  );
                })}
                {rootIdColumn && <th></th>}
              </tr>
              <tr className="filters-row">
                {table.getHeaderGroups()[0].headers.map((header) => (
                  <th key={`f-${header.id}`}>
                    <FilterInput
                      kind={columnKinds[header.id]}
                      options={categoryOptions[header.id]}
                      value={header.column.getFilterValue()}
                      onChange={(v) => header.column.setFilterValue(v)}
                    />
                  </th>
                ))}
                {rootIdColumn && <th></th>}
              </tr>
            </thead>
            <tbody>
              {table.getRowModel().rows.map((row, i) => (
                <tr key={i}>
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                  ))}
                  {rootIdColumn && (
                    <td>
                      <button
                        onClick={() => goToNeuron(String(row.original[rootIdColumn]))}
                        title={`View connectivity for ${row.original[rootIdColumn]}`}
                        disabled={
                          row.original[rootIdColumn] === null ||
                          row.original[rootIdColumn] === undefined ||
                          row.original[rootIdColumn] === 0
                        }
                      >→</button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function filterFnFor(kind: ColumnKind, col: string) {
  if (kind === "category") {
    return (row: { getValue: <T>(id: string) => T }, _id: string, filterValue: unknown) => {
      if (!filterValue) return true;
      const v = row.getValue<unknown>(col);
      const display = v === null || v === undefined ? "(none)" : String(v);
      return display === filterValue;
    };
  }
  if (kind === "number") {
    return (row: { getValue: <T>(id: string) => T }, _id: string, filterValue: unknown) => {
      const range = filterValue as { min?: number; max?: number } | undefined;
      if (!range) return true;
      const v = row.getValue<number>(col);
      if (typeof v !== "number") return false;
      if (range.min !== undefined && v < range.min) return false;
      if (range.max !== undefined && v > range.max) return false;
      return true;
    };
  }
  return (row: { getValue: <T>(id: string) => T }, _id: string, filterValue: unknown) => {
    if (!filterValue) return true;
    const v = row.getValue<unknown>(col);
    const haystack = v === null || v === undefined ? "" : String(v).toLowerCase();
    return haystack.includes(String(filterValue).toLowerCase());
  };
}
