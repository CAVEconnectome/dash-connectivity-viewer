import { useEffect, useState } from "react";
import { useCellIdLookupMutation, useConnectivity, useDatastackInfo, useTables } from "../api/queries";
import { useSetUrlParams, useUrlParam } from "../hooks/useUrlState";
import { AnalyticsRail } from "./AnalyticsRail";
import { PartnersPane } from "./PartnersPane";

export function NeuronView() {
  const [ds] = useUrlParam("ds");
  const [mv] = useUrlParam("mv");
  const [root] = useUrlParam("root");
  const [decRaw] = useUrlParam("dec"); // comma-separated decoration table names
  const setUrl = useSetUrlParams();
  const decorationTables = decRaw ? decRaw.split(",").filter(Boolean) : [];

  const [draftRoot, setDraftRoot] = useState(root ?? "");
  const [draftCellId, setDraftCellId] = useState("");
  const [draftDecorations, setDraftDecorations] = useState<string[]>(decorationTables);
  // Decoration picker collapses to a chip showing the active count; opens on
  // click for editing. Form's id fields stay editable at all times — typical
  // workflow is "punch in a new id, hit Load" and re-expanding the form via
  // a separate Edit click was friction. Persists per-session in component state.
  const [decorationsOpen, setDecorationsOpen] = useState(false);

  // Datastack info tells us whether the cell-id lookup is wired for this
  // dataset. Some operators omit the config keys and the lookup endpoint will
  // 422; in that case we hide the input.
  const info = useDatastackInfo(ds);
  const cellLookup = useCellIdLookupMutation();

  // Keep the form drafts in sync with URL state — cross-nav (table → neuron,
  // partner → partner) and back/forward updates the URL params, and the
  // visible inputs should reflect that without the user having to retype.
  useEffect(() => { setDraftRoot(root ?? ""); }, [root]);
  useEffect(() => { setDraftDecorations(decorationTables); }, [decRaw]);  // eslint-disable-line

  // Collapse the decorations picker whenever navigation lands on a new root.
  // Without this, the picker stays sticky across `→` cross-nav and Load
  // submissions, making the form visually grow on every partner navigation
  // until the user thinks to manually click the chip closed.
  useEffect(() => { setDecorationsOpen(false); }, [root]);

  const matVersion = mv ? Number(mv) : "live";
  // Don't Number(root) — int64 root ids overflow JS Number precision (2^53);
  // keep them as strings end-to-end. Backend accepts strings on every entry point.
  const rootId = root || null;

  // Tables/views list for the cell-type picker. Backend returns:
  //   live mode  → tables only
  //   materialized → tables + views
  // …so we just hand the response straight through to the dropdown.
  const tables = useTables(ds, matVersion);

  const connectivity = useConnectivity(
    ds && rootId
      ? { ds, rootId, matVersion, decorationTables }
      : null,
  );

  if (!ds) return <p>Pick a datastack from the sidebar to begin.</p>;

  const decorationsCount = draftDecorations.filter(Boolean).length;
  const decorationsLabel =
    decorationsCount === 0
      ? "no decorations"
      : decorationsCount === 1
        ? "1 decoration"
        : `${decorationsCount} decorations`;

  return (
    <div className="neuron-view">
      <form
        className="root-form"
        onSubmit={async (e) => {
          e.preventDefault();
          let resolvedRoot = draftRoot.trim() || null;
          const cid = draftCellId.trim();
          if (cid) {
            const result = await cellLookup.mutateAsync({
              ds, matVersion, cellIds: [cid],
            });
            const mapped = result.cell_to_root[cid];
            if (mapped) {
              resolvedRoot = mapped;
              setDraftRoot(mapped);
              setDraftCellId("");
            } else {
              return; // leave the URL alone; the error renders below
            }
          }
          setUrl({
            root: resolvedRoot,
            dec: draftDecorations.length > 0 ? draftDecorations.join(",") : null,
          });
        }}
      >
        <div className="root-form-row">
          <label>
            Root ID
            <input
              type="text"
              inputMode="numeric"
              placeholder="e.g. 864691135855914798"
              value={draftRoot}
              onChange={(e) => setDraftRoot(e.target.value)}
              size={22}
            />
          </label>
          {info.data && info.data.soma_table && (
            <label>
              Cell ID
              <input
                type="text"
                inputMode="numeric"
                placeholder="e.g. 271700"
                value={draftCellId}
                onChange={(e) => setDraftCellId(e.target.value)}
                size={10}
                title="Persistent nucleus id; resolves to a current root id on submit"
              />
            </label>
          )}
          <button
            type="button"
            className={`decorations-chip${decorationsOpen ? " open" : ""}`}
            onClick={() => setDecorationsOpen((v) => !v)}
            title={decorationsOpen ? "Hide decoration picker" : "Show decoration picker"}
          >
            {decorationsLabel} <span className="chevron">{decorationsOpen ? "▾" : "▸"}</span>
          </button>
          <button type="submit">Load</button>
        </div>
        {decorationsOpen && (
          <fieldset className="decorations-picker">
            <legend>Decoration tables</legend>
            {draftDecorations.map((tbl, i) => (
              <span key={i} className="decoration-row">
                <select
                  value={tbl}
                  onChange={(e) => {
                    const next = [...draftDecorations];
                    next[i] = e.target.value;
                    setDraftDecorations(next.filter(Boolean));
                  }}
                  disabled={!tables.data}
                >
                  <option value="">— remove —</option>
                  {tables.data?.tables.map((t) => (
                    <option key={t.name} value={t.name}>
                      {t.kind === "view" ? `${t.name}  (view)` : t.name}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() => setDraftDecorations(draftDecorations.filter((_, j) => j !== i))}
                  title="Remove"
                >×</button>
              </span>
            ))}
            <button
              type="button"
              onClick={() => setDraftDecorations([...draftDecorations, ""])}
              disabled={!tables.data}
            >+ add decoration</button>
          </fieldset>
        )}
      </form>

      {cellLookup.isPending && <p>Resolving cell id…</p>}
      {cellLookup.error && (
        <p className="error">cell-id lookup failed: {cellLookup.error.message}</p>
      )}
      {cellLookup.data && draftCellId === "" && Object.values(cellLookup.data.cell_to_root).every((v) => v === null) && (
        <p className="error">No cell with that id was found.</p>
      )}
      {connectivity.isFetching && <p>Loading…</p>}
      {connectivity.error && (
        <p className="error">{(connectivity.error as Error).message}</p>
      )}

      {connectivity.data && ds && rootId && (
        <>
          <Summary bundle={connectivity.data} />

          <div className="workbench">
            <div className="analytics-rail">
              <AnalyticsRail
                ds={ds}
                rootId={rootId}
                matVersion={matVersion}
                bundle={connectivity.data}
                decorationTables={decorationTables}
              />
            </div>

            <div className="tables-pane">
              <PartnersPane
                ds={ds}
                rootId={rootId!}
                matVersion={matVersion}
                bundle={connectivity.data}
                decorationTables={decorationTables}
              />
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function Summary({ bundle }: { bundle: import("../api/types").ConnectivityBundle }) {
  const s = bundle.summary;
  return (
    <div className="summary">
      <strong>v{bundle.version_used}</strong>{" "}
      {s && (
        <>
          {s.num_partners_in} inputs / {s.num_partners_out} outputs ·{" "}
          {s.num_syn_in} input syns / {s.num_syn_out} output syns ·{" "}
          {s.num_soma} soma
        </>
      )}
      <RevalidationBadge bundle={bundle} />
    </div>
  );
}

/**
 * Status pill that surfaces the SWR revalidation state of decoration columns.
 *
 * The connectivity bundle ships served records sourced from cache; if any
 * cache entry was past its soft TTL, the backend kicked off a background
 * refetch and tagged the bundle with `decoration_revalidation` (a polling
 * ticket). The SPA polls until the refresh lands, then `mergeDecorationDeltas`
 * clears the field — meaning the displayed cell_type / num_soma values are
 * authoritative as of the request timestamp.
 *
 *   pending → amber chip with spinning glyph; some decoration cells may
 *             still flip in-place when the poll resolves
 *   done    → muted green check; the values you see are final
 *
 * The fresh-on-first-load case (no ticket ever issued) shows "done"
 * immediately, which is correct — no revalidation was needed.
 */
function RevalidationBadge({ bundle }: { bundle: import("../api/types").ConnectivityBundle }) {
  const pending = bundle.decoration_revalidation != null;
  const nPending = bundle.decoration_revalidation?.pending_root_ids.length ?? 0;
  if (pending) {
    return (
      <span
        className="reval-badge pending"
        title={`Background refresh in flight for ${nPending} partners — values may flip in place when it lands.`}
      >
        <span className="spin" aria-hidden>↻</span>{" "}refreshing decorations
      </span>
    );
  }
  return (
    <span className="reval-badge done" title="Decoration values are current.">
      ✓ up to date
    </span>
  );
}
