import { useEffect, useState } from "react";
import { Outlet, useNavigate, Link } from "react-router-dom";
import {
  useDatastackInfo,
  useDatastacks,
  useMakeSegmentsLinkMutation,
  useVersions,
} from "../api/queries";
import { parseMatVersion, useSetUrlParams, useUrlParam } from "../hooks/useUrlState";
import { TokenBanner } from "./TokenBanner";

const SIDEBAR_COLLAPSED_KEY = "dcv:sidebar_collapsed";

function loadSidebarCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

export function Workspace() {
  const [ds] = useUrlParam("ds");
  const [mv] = useUrlParam("mv");
  const setUrl = useSetUrlParams();
  const navigate = useNavigate();

  const datastacks = useDatastacks();
  const versions = useVersions(ds);
  const info = useDatastackInfo(ds);
  const [from] = useUrlParam("from");

  // "live" is always offered in the picker. Datastacks with `live_mode: false`
  // (public release datastacks) still gate the connectivity / plots / links
  // endpoints — picking "live" for those falls back to "browse the latest
  // version" in the table view but errors out on the neuron view. This keeps
  // the table-browsing affordance available everywhere without giving a
  // misleading impression that connectivity queries can run live on a
  // release datastack.

  // Show whatever's in `?ds=` even if it's not in the allowlist response yet
  // (race on first paint, or operator forgot to add it). The select still
  // renders the URL value so the picker reads as "in sync" with the URL.
  const allowed = datastacks.data?.datastacks ?? [];
  const dsOptions = ds && !allowed.includes(ds) ? [ds, ...allowed] : allowed;

  const [sidebarCollapsed, setSidebarCollapsed] = useState(loadSidebarCollapsed);
  const toggleSidebar = () => {
    setSidebarCollapsed((prev) => {
      const next = !prev;
      try { localStorage.setItem(SIDEBAR_COLLAPSED_KEY, next ? "1" : "0"); } catch { /* ignore */ }
      return next;
    });
  };

  // Default the version picker to the latest valid materialization on first
  // load. Even when live mode is allowed, "latest valid" is the better default
  // — live drifts as proofreading lands, materialization is a stable reference
  // point. User can flip to "live" explicitly when they want it.
  useEffect(() => {
    if (!info.data || !versions.data) return;
    if (!mv) {
      const latest = versions.data.versions.find((v) => v.valid);
      if (latest) setUrl({ mv: String(latest.version) });
    }
  }, [info.data, versions.data, mv, setUrl]);

  return (
    <div className={`workspace${sidebarCollapsed ? " sidebar-collapsed" : ""}`}>
      <aside className="sidebar">
        {sidebarCollapsed ? (
          // Vertical "Connectivity Viewer ›" label — uses the otherwise-
          // wasted collapsed-strip space to brand the app and signal
          // that the strip is interactive. Click anywhere on the
          // button expands the sidebar.
          <button
            className="sidebar-toggle vertical"
            onClick={toggleSidebar}
            title="Expand sidebar"
            aria-label="Expand sidebar"
          >
            <span className="vertical-label">Connectivity Viewer</span>
            <span className="vertical-chevron">›</span>
          </button>
        ) : (
          <>
            <div className="sidebar-header">
              <h1>Connectivity Viewer</h1>
              <button
                className="sidebar-toggle"
                onClick={toggleSidebar}
                title="Collapse sidebar"
                aria-label="Collapse sidebar"
              >
                ‹
              </button>
            </div>
            <TokenBanner />

            <label>
              Datastack
              <select
                value={ds ?? ""}
                onChange={(e) => setUrl({ ds: e.target.value || null, mv: null })}
                disabled={datastacks.isError}
              >
                <option value="">
                  {datastacks.isFetching && !datastacks.data ? "loading…" : "— select —"}
                </option>
                {dsOptions.map((d) => (
                  <option key={d} value={d}>{d}</option>
                ))}
              </select>
              {datastacks.isError && (
                <div className="error-row">
                  <span>datastack list failed: {datastacks.error instanceof Error ? datastacks.error.message : "unknown"}</span>
                  <button onClick={() => datastacks.refetch()} disabled={datastacks.isFetching}>
                    {datastacks.isFetching ? "retrying…" : "retry"}
                  </button>
                </div>
              )}
            </label>

            <label>
              Materialization
              <select
                value={mv ?? "live"}
                // Write "live" as an explicit URL value rather than clearing
                // `?mv=` — that way the auto-default-to-latest effect below
                // (which keys off `!mv`) doesn't immediately overwrite the
                // user's choice the moment they pick "live".
                onChange={(e) => setUrl({ mv: e.target.value })}
                disabled={!ds || versions.isError}
              >
                <option value="live">live</option>
                {/* Show the URL's current mv immediately so the select isn't empty
                    while versions.data is in flight (cold CAVE call can be slow). */}
                {mv && !versions.data && (
                  <option value={mv}>v{mv}{versions.isFetching ? " (loading…)" : ""}</option>
                )}
                {versions.data?.versions.filter((v) => v.valid).map((v) => (
                  <option key={v.version} value={String(v.version)}>v{v.version}</option>
                ))}
              </select>
              {versions.isError && (
                <div className="error-row">
                  <span>versions failed: {versions.error instanceof Error ? versions.error.message : "unknown"}</span>
                  <button onClick={() => versions.refetch()} disabled={versions.isFetching}>
                    {versions.isFetching ? "retrying…" : "retry"}
                  </button>
                </div>
              )}
            </label>

            {info.data && (
              <details className="info">
                <summary>Datastack info</summary>
                <p><strong>Synapse table:</strong> {info.data.synapse_table}</p>
                <p><strong>Soma table:</strong> {info.data.soma_table}</p>
                <p><strong>Voxel:</strong> {info.data.voxel_resolution?.join(" × ")}</p>
              </details>
            )}
            {info.data && <NeutralNeuroglancerLink ds={ds!} mv={mv} />}

            <nav className="nav">
              <button
                onClick={() => navigate(`/neuron${ds ? `?ds=${ds}${mv ? `&mv=${mv}` : ""}` : ""}`)}
                disabled={!ds}
              >
                Neuron view
              </button>
              <button
                onClick={() => navigate(`/tables${ds ? `?ds=${ds}${mv ? `&mv=${mv}` : ""}` : ""}`)}
                disabled={!ds}
              >
                Table browser
              </button>
            </nav>
          </>
        )}
      </aside>
      <main className="main">
        {from && <Breadcrumb from={from} ds={ds} mv={mv} />}
        <Outlet />
      </main>
    </div>
  );
}

interface BreadcrumbProps {
  from: string;
  ds: string | null;
  mv: string | null;
}

/**
 * Renders a tiny "← from <neuron 864...>" / "← from table <ct_name>" link
 * driven by the `from=` URL param that cross-nav handlers set when they jump
 * between views. Pure derivation — no state of its own.
 */
function Breadcrumb({ from, ds, mv }: BreadcrumbProps) {
  const [kind, value] = from.split(":", 2);
  const params = new URLSearchParams();
  if (ds) params.set("ds", ds);
  if (mv) params.set("mv", mv);

  let label: string;
  let to: string;
  if (kind === "neuron" && value) {
    params.set("root", value);
    label = `neuron ${value.slice(0, 6)}…${value.slice(-4)}`;
    to = `/neuron?${params}`;
  } else if (kind === "table" && value) {
    label = `table ${value}`;
    to = `/tables?${params}`;
  } else {
    return null;
  }

  return (
    <div className="breadcrumb">
      <Link to={to}>← back to {label}</Link>
    </div>
  );
}

interface NeutralNeuroglancerLinkProps {
  ds: string;
  mv: string | null;
}

/**
 * "Open in Neuroglancer" affordance for the sidebar's Datastack-info block.
 * Empty `root_ids` means the segments-link endpoint composes a viewer with
 * just the datastack's default image + segmentation layers, no segments
 * pinned and no point annotations — a neutral landing for "I want to look
 * around this dataset before I have a specific cell in mind."
 *
 * In live mode the connectivity flow is gated on release datastacks but the
 * neutral viewer is fine — there's no live-vs-materialized data being read,
 * we're just composing a default Neuroglancer state. The mutation forwards
 * the URL's mat_version verbatim; backend endpoint accepts both.
 */
function NeutralNeuroglancerLink({ ds, mv }: NeutralNeuroglancerLinkProps) {
  const matVersion = parseMatVersion(mv);
  const makeLink = useMakeSegmentsLinkMutation();
  const open = async () => {
    try {
      const result = await makeLink.mutateAsync({ ds, matVersion, rootIds: [] });
      window.open(result.url, "_blank");
    } catch {
      // Error message renders below; nothing to do here.
    }
  };
  return (
    <p className="ngl-link-row">
      <button
        type="button"
        className="link-button"
        onClick={open}
        disabled={makeLink.isPending}
      >
        {makeLink.isPending ? "opening…" : "Open in Neuroglancer ↗"}
      </button>
      {makeLink.isError && (
        <span className="error">
          {(makeLink.error as Error).message}
        </span>
      )}
    </p>
  );
}
