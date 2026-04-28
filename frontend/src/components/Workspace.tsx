import { useEffect, useState } from "react";
import { Outlet, useNavigate, Link } from "react-router-dom";
import { useDatastackInfo, useVersions } from "../api/queries";
import { useSetUrlParams, useUrlParam } from "../hooks/useUrlState";
import { TokenBanner } from "./TokenBanner";

const KNOWN_DATASTACKS = ["minnie65_public"];

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

  const versions = useVersions(ds);
  const info = useDatastackInfo(ds);
  const liveAllowed = info.data?.live_mode !== false;
  const [from] = useUrlParam("from");

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
          <button
            className="sidebar-toggle"
            onClick={toggleSidebar}
            title="Expand sidebar"
            aria-label="Expand sidebar"
          >
            ›
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
              >
                <option value="">— select —</option>
                {KNOWN_DATASTACKS.map((d) => (
                  <option key={d} value={d}>{d}</option>
                ))}
              </select>
            </label>

            <label>
              Materialization
              <select
                value={mv ?? "live"}
                onChange={(e) => setUrl({ mv: e.target.value === "live" ? null : e.target.value })}
                disabled={!versions.data}
              >
                {liveAllowed && <option value="live">live</option>}
                {versions.data?.versions.filter((v) => v.valid).map((v) => (
                  <option key={v.version} value={String(v.version)}>v{v.version}</option>
                ))}
              </select>
            </label>

            {info.data && (
              <details className="info">
                <summary>Datastack info</summary>
                <p><strong>Synapse table:</strong> {info.data.synapse_table}</p>
                <p><strong>Soma table:</strong> {info.data.soma_table}</p>
                <p><strong>Voxel:</strong> {info.data.voxel_resolution?.join(" × ")}</p>
              </details>
            )}

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
