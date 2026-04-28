import { useCallback, useMemo } from "react";
import type { ConnectivityBundle } from "../api/types";
import { useUrlParam } from "../hooks/useUrlState";
import {
  type ColumnBoundPlotDescriptor,
  type PlotDescriptor,
  plotRegistry,
} from "../plots/registry";
import {
  encodePlotsList,
  encodeSelParam,
  newPlotId,
  parsePlotsList,
  PLOTS_KEY,
  selKey,
} from "../plots/urlState";
import { listVizColumns } from "../plots/vizColumns";
import { DynamicPlotPanel } from "./DynamicPlotPanel";
import { PlotPanel } from "./PlotPanel";

interface Props {
  ds: string;
  rootId: string;
  matVersion: number | "live";
  bundle: ConnectivityBundle;
  decorationTables: string[];
}

/**
 * Renders the left-pane analytics rail.
 *
 * Three panel types:
 *   - **Static** (registry-defined): fixed backend spec, no runtime config.
 *   - **Column-bound** (registry-defined, legacy): single x-axis picker;
 *     auto-dispatches between bar and histogram backend specs based on
 *     column kind. Persists the binding via `?viz_<id>=<col>`.
 *   - **Dynamic** (runtime-creatable): user adds via "+ Add plot"; each
 *     panel exposes x/y/hue/size pickers; backend auto-picks chart kind
 *     (1 axis → histogram, 2 axes → scatter). Active dynamic panels live
 *     in URL state at `?plots=<id>,<id>,...`. Each panel's bindings live
 *     at `?viz_<id>={...json...}`.
 *
 * Adding a new panel = appending to the `?plots=` list with a fresh id.
 * Removing one = dropping the id and clearing its `?viz_<id>=` key.
 */
export function AnalyticsRail({ ds, rootId, matVersion, bundle, decorationTables }: Props) {
  const [plotsRaw, setPlotsRaw] = useUrlParam(PLOTS_KEY);
  const dynamicPanelIds = useMemo(() => parsePlotsList(plotsRaw), [plotsRaw]);

  // Pick a default `source` for new dynamic panels: prefer partners_out
  // since it's typically smaller / faster to render. The user can pick
  // a different source later via a "From preset" submenu (deferred).
  const addDynamicPanel = () => {
    const id = newPlotId();
    setPlotsRaw(encodePlotsList([...dynamicPanelIds, id]));
  };

  const removeDynamicPanel = (id: string) => {
    const remaining = dynamicPanelIds.filter((p) => p !== id);
    setPlotsRaw(remaining.length > 0 ? encodePlotsList(remaining) : null);
    // Also drop the bindings + selection keys. We can't access useUrlParam
    // here for arbitrary keys, so we mutate window.location's URLSearchParams
    // through history.replaceState. Tiny, scoped, doesn't trigger a full
    // react-router navigation.
    const params = new URLSearchParams(window.location.search);
    params.delete(`viz_${id}`);
    params.delete(selKey(id));
    const newSearch = params.toString();
    const newUrl =
      window.location.pathname +
      (newSearch ? `?${newSearch}` : "") +
      window.location.hash;
    window.history.replaceState(null, "", newUrl);
  };

  /**
   * Write a brush selection from a dynamic panel into the URL. Empty
   * selections drop the key entirely so it doesn't pollute the URL when
   * the user clears the brush.
   *
   * Uses history.replaceState rather than the react-router setter to keep
   * brushing fast (no full re-render of the route hierarchy on every drag
   * tweak). PartnersPane reads via useSearchParams so it still re-renders.
   */
  const writePlotSelection = useCallback(
    (plotId: string, source: "partners_in" | "partners_out" | "partners_both", ids: string[]) => {
      const params = new URLSearchParams(window.location.search);
      const key = selKey(plotId);
      if (ids.length === 0) {
        params.delete(key);
      } else {
        params.set(key, encodeSelParam({ source, ids }));
      }
      const newSearch = params.toString();
      const newUrl =
        window.location.pathname +
        (newSearch ? `?${newSearch}` : "") +
        window.location.hash;
      window.history.replaceState(null, "", newUrl);
      // Nudge react-router's params hook so subscribers re-render. Setting
      // the same value (or null) still triggers the hook because the URL
      // changed via replaceState above.
      window.dispatchEvent(new PopStateEvent("popstate"));
    },
    [],
  );

  return (
    <div className="plots">
      {plotRegistry.map((d) =>
        d.kind === "static" ? (
          <PlotPanel
            key={d.id}
            ds={ds}
            spec={d.spec}
            rootId={rootId}
            matVersion={matVersion}
            height={260}
          />
        ) : d.kind === "column-bound" ? (
          <ColumnBoundPlot
            key={d.id}
            descriptor={d}
            ds={ds}
            rootId={rootId}
            matVersion={matVersion}
            bundle={bundle}
            decorationTables={decorationTables}
          />
        ) : null,
      )}
      {dynamicPanelIds.map((id) => (
        <DynamicPlotPanel
          key={id}
          descriptor={{
            id,
            title: "Custom plot",
            kind: "dynamic",
            spec: "dynamic",
          }}
          ds={ds}
          rootId={rootId}
          matVersion={matVersion}
          bundle={bundle}
          decorationTables={decorationTables}
          onClose={() => removeDynamicPanel(id)}
          onSelected={(ids) => writePlotSelection(id, "partners_both", ids)}
        />
      ))}
      <div className="add-plot-row">
        <button
          type="button"
          className="add-plot-button"
          onClick={addDynamicPanel}
          title="Add a new plot panel"
        >
          + Add plot
        </button>
      </div>
    </div>
  );
}

interface ColumnBoundProps {
  descriptor: ColumnBoundPlotDescriptor;
  ds: string;
  rootId: string;
  matVersion: number | "live";
  bundle: ConnectivityBundle;
  decorationTables: string[];
}

/**
 * Column-bound plot: column choices are computed from the descriptor's
 * `source` frame in the bundle (partners_out by default). The picker self-
 * disables when no decoration columns are loaded — the user has to add a
 * decoration table or cell-type table for the picker to populate.
 *
 * If the persisted column from the URL no longer matches an available choice
 * (e.g. user removed the decoration table that supplied it), the picker
 * resets to "no selection" and the plot renders an empty placeholder rather
 * than 422-ing the backend.
 */
function ColumnBoundPlot({
  descriptor,
  ds,
  rootId,
  matVersion,
  bundle,
  decorationTables,
}: ColumnBoundProps) {
  const [col, setCol] = useUrlParam(`viz_${descriptor.id}`);

  const rows = (bundle[descriptor.source] ?? []) as Record<string, unknown>[];
  const choices = useMemo(
    () => listVizColumns(rows, bundle.column_groups),
    [rows, bundle.column_groups],
  );
  const validChoice = choices.find((c) => c.key === col);

  const header = (
    <div className="plot-panel-header">
      <span className="plot-panel-title">{descriptor.title}</span>
      <select
        value={validChoice?.key ?? ""}
        onChange={(e) => setCol(e.target.value || null)}
        disabled={choices.length === 0}
      >
        <option value="">— pick a column —</option>
        {choices.map((c) => (
          <option key={c.key} value={c.key}>
            {c.group} / {c.display}  ({c.kind})
          </option>
        ))}
      </select>
    </div>
  );

  if (!validChoice) {
    return (
      <div className="plot-panel">
        {header}
        <div className="loading">
          {choices.length === 0
            ? "Add a decoration table to plot a column."
            : "Pick a column to plot."}
        </div>
      </div>
    );
  }

  const spec = validChoice.kind === "histogram" ? descriptor.histogramSpec : descriptor.barSpec;

  return (
    <PlotPanel
      ds={ds}
      spec={spec}
      rootId={rootId}
      matVersion={matVersion}
      decorationTables={decorationTables}
      column={validChoice.key}
      height={260}
      header={header}
    />
  );
}

// re-export for the type contract — PlotDescriptor isn't used directly here but
// callers may want to import alongside.
export type { PlotDescriptor };
