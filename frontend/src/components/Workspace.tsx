import { useEffect, useState } from "react";
import { Outlet, useLocation, useNavigate, Link } from "react-router-dom";
import {
  useDatastackInfo,
  useDatastacks,
  useMakeSegmentsLinkMutation,
  useTours,
  useVersions,
} from "../api/queries";
import type { Recipe } from "../api/types";
import { parseMatVersion, useSetUrlParams, useUrlParam } from "../hooks/useUrlState";
import { buildRecipeOpenParams } from "../tours/urlMint";
import { useApplyRecipe } from "../tours/useApplyRecipe";
import {
  listForDs as listPersonalRecipes,
  remove as removePersonalRecipe,
  subscribe as subscribePersonalRecipes,
} from "../tours/personalRecipes";
import { recipeToYaml } from "../tours/recipeYaml";
import { ShareMenu } from "./ShareMenu";

const SIDEBAR_COLLAPSED_KEY = "dcv:sidebar_collapsed";

function loadSidebarCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

/**
 * Per-tab cached URL state for the major views, so navigating to Tours
 * (or applying a recipe) and back doesn't destroy a complex Neuron view
 * or Table browser configuration.
 *
 * Stored in sessionStorage rather than localStorage — the user explicitly
 * said this history doesn't need to persist, and per-tab semantics are
 * better here: two tabs don't fight over a shared cached URL, and a fresh
 * tab gets a fresh slate. Survives reload of the same tab, which is the
 * useful property.
 *
 * `tables` collapses both `/tables` and `/tables/<name>` because the
 * "Table browser" nav button is a single entry point — restoring to the
 * specific table the user was on is friendlier than dumping them back to
 * the list.
 */
type ViewFamily = "neuron" | "tables";

function pathFamily(pathname: string): ViewFamily | null {
  if (pathname === "/neuron") return "neuron";
  if (pathname === "/tables" || pathname.startsWith("/tables/")) return "tables";
  return null;
}

const VIEW_SNAPSHOT_PREFIX = "dcv:view:";

interface ViewSnapshot {
  pathname: string;
  search: string;
}

function writeViewSnapshot(pathname: string, search: string): void {
  const family = pathFamily(pathname);
  if (!family) return;
  try {
    sessionStorage.setItem(
      `${VIEW_SNAPSHOT_PREFIX}${family}`,
      JSON.stringify({ pathname, search } satisfies ViewSnapshot),
    );
  } catch {
    // sessionStorage can throw in private mode / quota — silently degrade
    // to the no-snapshot path; it's a UX nicety, not a correctness feature.
  }
}

function readViewSnapshot(family: ViewFamily): ViewSnapshot | null {
  try {
    const raw = sessionStorage.getItem(`${VIEW_SNAPSHOT_PREFIX}${family}`);
    if (!raw) return null;
    const obj = JSON.parse(raw) as Partial<ViewSnapshot>;
    if (typeof obj?.pathname === "string" && typeof obj?.search === "string") {
      return { pathname: obj.pathname, search: obj.search };
    }
  } catch {
    // ignore
  }
  return null;
}

export function Workspace() {
  const [ds] = useUrlParam("ds");
  const [mv] = useUrlParam("mv");
  const setUrl = useSetUrlParams();
  const navigate = useNavigate();
  const location = useLocation();

  // Snapshot the current URL on every location change. Pin-cushioning this
  // on every render is fine — sessionStorage writes are cheap and the
  // pathFamily gate skips writes for the landing page / 404. The snapshot
  // overwrites itself, so no growth.
  useEffect(() => {
    writeViewSnapshot(location.pathname, location.search);
  }, [location.pathname, location.search]);

  // Build a restore-aware navigation URL for a view family. If a snapshot
  // exists for the same datastack, restore it; otherwise fall back to a
  // bare `?ds=&mv=` URL. ds/mv always reflect the current sidebar state,
  // not the snapshot's — the sidebar is the user's lever for those, and
  // a stale snapshot mustn't override their explicit choice. Drops `from`
  // since it's a transient breadcrumb marker, not real view state.
  const navigateToView = (family: ViewFamily) => {
    const fallbackPath = family === "neuron" ? "/neuron" : "/tables";
    const snapshot = readViewSnapshot(family);
    const snapshotDs = snapshot
      ? new URLSearchParams(snapshot.search).get("ds")
      : null;
    let pathname = fallbackPath;
    let params: URLSearchParams;
    if (snapshot && snapshotDs === ds) {
      pathname = snapshot.pathname;
      params = new URLSearchParams(snapshot.search);
    } else {
      params = new URLSearchParams();
    }
    if (ds) params.set("ds", ds); else params.delete("ds");
    if (mv) params.set("mv", mv); else params.delete("mv");
    params.delete("from");
    const qs = params.toString();
    navigate(`${pathname}${qs ? `?${qs}` : ""}`);
  };

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
          // Vertical "CAVE Data Viewer ›" label — uses the otherwise-
          // wasted collapsed-strip space to brand the app and signal
          // that the strip is interactive. Click anywhere on the
          // button expands the sidebar.
          <button
            className="sidebar-toggle vertical"
            onClick={toggleSidebar}
            title="Expand sidebar"
            aria-label="Expand sidebar"
          >
            <span className="vertical-label">CAVE Data Viewer</span>
            <span className="vertical-chevron">›</span>
          </button>
        ) : (
          <>
            <div className="sidebar-header">
              <h1>CAVE Data Viewer</h1>
              <button
                className="sidebar-toggle"
                onClick={toggleSidebar}
                title="Collapse sidebar"
                aria-label="Collapse sidebar"
              >
                ‹
              </button>
            </div>
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
                onClick={() => navigate(`/${ds ? `?ds=${ds}${mv ? `&mv=${mv}` : ""}` : ""}`)}
                title="Operator-curated examples and recipes"
              >
                Examples and Recipes
              </button>
              <button
                onClick={() => navigateToView("neuron")}
                disabled={!ds}
                title="Resumes your last neuron view if you've been here before"
              >
                Neuron view
              </button>
              <button
                onClick={() => navigateToView("tables")}
                disabled={!ds}
                title="Resumes your last table browser view if you've been here before"
              >
                Table browser
              </button>
            </nav>
            {ds && <ShareMenu ds={ds} />}
            {ds && <SidebarRecipes ds={ds} mv={mv} />}
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

/**
 * Sidebar widget surfacing operator-curated Recipes scoped to the current
 * datastack. Examples don't appear here — they're navigation-style and
 * belong on the landing page (`/`); the sidebar is for "I'm already in the
 * workspace, overlay this configuration onto my cell" gestures.
 *
 * The Apply CTA is disabled when no `?root=` is set, with a tooltip
 * explaining why. Same hook (`useApplyRecipe`) the landing page uses, so
 * the confirmation flow and URL-state semantics stay identical regardless
 * of where the user triggers an Apply from.
 *
 * Defaults to closed (`<details>` without `open`) — tours are a tour-of-
 * capabilities feature, not a primary workflow, so the widget shouldn't
 * dominate the sidebar's vertical space. Per-session collapse state is
 * native browser behavior; we don't persist it.
 */
function SidebarRecipes({ ds, mv }: { ds: string; mv: string | null }) {
  const tours = useTours(ds);
  const [root] = useUrlParam("root");
  const navigate = useNavigate();
  const applyRecipe = useApplyRecipe();
  // Personal recipes live in localStorage. Subscribe to mutation events
  // emitted by `personalRecipes.save/remove` so the list re-renders when
  // ShareMenu (a sibling, not a parent) writes a new entry.
  const [, setPersonalTick] = useState(0);
  useEffect(() => subscribePersonalRecipes(() => setPersonalTick((n) => n + 1)), []);
  const personalRecipes: Recipe[] = listPersonalRecipes(ds);

  const operatorRecipes: Recipe[] = tours.data?.recipes ?? [];

  // Always show the disclosure once we know about either list. Loading
  // state is tracked separately so the user sees "loading…" rather than
  // a missing section while tours.data is in flight.
  const toursLoading = tours.isLoading;
  if (personalRecipes.length === 0 && operatorRecipes.length === 0 && !toursLoading) {
    return null;
  }

  // Apply when a cell is loaded; otherwise Open the recipe into a fresh
  // /neuron with the configuration preset and no root. Same logic as the
  // landing-page RecipeCard so the UX is consistent regardless of where
  // the user clicks Recipes from.
  const canApply = !!root;
  const onClick = (r: Recipe) => {
    if (canApply) {
      applyRecipe(r);
    } else {
      const params = buildRecipeOpenParams(ds, r, mv);
      navigate(`/neuron?${params.toString()}`);
    }
  };
  const total = personalRecipes.length + operatorRecipes.length;
  const summaryText =
    toursLoading && operatorRecipes.length === 0
      ? `Recipes (${personalRecipes.length}+…)`
      : `Recipes (${total})`;

  return (
    <details className="sidebar-recipes" open>
      <summary>{summaryText}</summary>
      {personalRecipes.length > 0 ? (
        <div className="recipes-group">
          <h4 className="sidebar-recipes-group">My recipes</h4>
          <ul>
            {personalRecipes.map((r) => (
              <PersonalRecipeRow
                key={r.id}
                ds={ds}
                recipe={r}
                root={root}
                canApply={canApply}
                onApply={() => onClick(r)}
              />
            ))}
          </ul>
        </div>
      ) : null}
      <div className="recipes-group">
        <h4 className="sidebar-recipes-group">Operator recipes</h4>
        {operatorRecipes.length > 0 ? (
          <ul>
            {operatorRecipes.map((r) => (
              <li key={r.id}>
                <button
                  type="button"
                  onClick={() => onClick(r)}
                  title={
                    canApply
                      ? `Apply: overlay onto cell ${root!.slice(0, 6)}…${root!.slice(-4)}` +
                        (r.description ? `\n\n${r.description}` : "")
                      : "Open: preconfigure the workspace, then pick a cell" +
                        (r.description ? `\n\n${r.description}` : "")
                  }
                >
                  {r.title}
                  <span className="sidebar-recipes-cta">{canApply ? "Apply" : "Open"}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : toursLoading ? (
          <p className="muted">Loading…</p>
        ) : (
          <p className="muted sidebar-recipes-empty">
            No operator recipes for this datastack. Visit{" "}
            <button
              type="button"
              className="link-button"
              onClick={() =>
                navigate(`/${ds ? `?ds=${ds}${mv ? `&mv=${mv}` : ""}` : ""}`)
              }
            >
              Examples and Recipes
            </button>{" "}
            to load one from a YAML file.
          </p>
        )}
      </div>
    </details>
  );
}

function PersonalRecipeRow({
  ds,
  recipe,
  root,
  canApply,
  onApply,
}: {
  ds: string;
  recipe: Recipe;
  root: string | null;
  canApply: boolean;
  onApply: () => void;
}) {
  const onDownload = () => {
    const yaml = recipeToYaml(recipe);
    const blob = new Blob([yaml], { type: "application/x-yaml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    // Slugify title for filename; fall back to the id if the title is
    // entirely non-alphanumeric.
    const slug = recipe.title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/(^-|-$)/g, "");
    a.download = `${slug || recipe.id}.recipe.yaml`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };
  const onDelete = () => {
    if (!window.confirm(`Delete personal recipe "${recipe.title}"?`)) return;
    removePersonalRecipe(ds, recipe.id);
  };
  return (
    <li className="sidebar-recipes-personal">
      <button
        type="button"
        onClick={onApply}
        title={
          canApply
            ? `Apply: overlay onto cell ${root!.slice(0, 6)}…${root!.slice(-4)}` +
              (recipe.description ? `\n\n${recipe.description}` : "")
            : "Open: preconfigure the workspace, then pick a cell" +
              (recipe.description ? `\n\n${recipe.description}` : "")
        }
      >
        {recipe.title}
        <span className="sidebar-recipes-cta">{canApply ? "Apply" : "Open"}</span>
      </button>
      <div className="sidebar-recipes-row-actions">
        <button type="button" onClick={onDownload} title="Download as YAML">YAML</button>
        <button type="button" onClick={onDelete} title="Delete this personal recipe">×</button>
      </div>
    </li>
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
