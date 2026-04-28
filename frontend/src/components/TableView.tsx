import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTables } from "../api/queries";
import { useUrlParam } from "../hooks/useUrlState";

export function TableView() {
  const [ds] = useUrlParam("ds");
  const [mv] = useUrlParam("mv");
  const matVersion = mv ? Number(mv) : "live";
  const tables = useTables(ds, matVersion);
  const [filter, setFilter] = useState("");

  const visible = useMemo(() => {
    if (!tables.data) return [];
    const needle = filter.trim().toLowerCase();
    if (!needle) return tables.data.tables;
    return tables.data.tables.filter((t) => t.name.toLowerCase().includes(needle));
  }, [tables.data, filter]);

  const carry = (table: string) => {
    const params = new URLSearchParams();
    if (ds) params.set("ds", ds);
    if (mv) params.set("mv", mv);
    return `/tables/${encodeURIComponent(table)}?${params}`;
  };

  if (!ds) return <p>Pick a datastack.</p>;

  return (
    <div className="table-view">
      <div className="root-form">
        <label>
          Filter
          <input
            type="text"
            placeholder="search by name…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            size={36}
          />
        </label>
        <span className="hint">
          {tables.data
            ? `${visible.length} of ${tables.data.tables.length} ${
                tables.data.mat_version === null ? "tables (live)" : "tables + views"
              }`
            : "loading…"}
        </span>
      </div>

      {tables.isFetching && <p>Loading…</p>}
      {tables.error && <p className="error">{(tables.error as Error).message}</p>}

      {tables.data && (
        <ul className="tables-list">
          {visible.map((t) => (
            <li key={t.name}>
              <span className={`kind kind-${t.kind}`}>{t.kind}</span>
              <Link to={carry(t.name)}>{t.name}</Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
