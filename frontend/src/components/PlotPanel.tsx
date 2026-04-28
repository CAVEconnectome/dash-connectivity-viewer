import { lazy, Suspense, useMemo, type ReactNode } from "react";
import { usePlot, type PlotBindings } from "../api/queries";
import { applyTheme } from "../plots/theme";

// Lazy-load react-plotly.js so the ~2MB plotly bundle is only fetched when a
// user actually views a plot — datastack picking, partner browsing, and link
// generation all stay snappy.
const Plot = lazy(async () => {
  const [{ default: createPlotlyComponent }, Plotly] = await Promise.all([
    import("react-plotly.js/factory"),
    import("plotly.js-cartesian-dist-min"),
  ]);
  return { default: createPlotlyComponent(Plotly.default) };
});

interface Props {
  ds: string;
  spec: string;
  rootId: string;
  matVersion: number | "live";
  decorationTables?: string[];
  /** Legacy single-column override. New code should pass `bindings` instead. */
  column?: string | null;
  /** Multi-channel binding for dynamic plots. */
  bindings?: PlotBindings | null;
  height?: number;
  // Optional rendered into the panel above the figure — typically a title +
  // a column picker for column-bound plots. Always rendered, even during
  // loading / error, so the picker stays interactive.
  header?: ReactNode;
  /** Brush / lasso selection callback. Each emitted point's `customdata` is
   *  expected to be the underlying row's `root_id` string (the backend ships
   *  `customdata` on every trace). Called with the deduped list of selected
   *  root_ids on every selection event; called with `[]` when the user
   *  clears the selection. */
  onSelected?: (rootIds: string[]) => void;
}

interface PlotlySelectionEvent {
  points?: Array<{ customdata?: unknown } | undefined>;
}

export function PlotPanel({ ds, spec, rootId, matVersion, decorationTables, column, bindings, height = 320, header, onSelected }: Props) {
  const plot = usePlot({ ds, spec, rootId, matVersion, decorationTables, column, bindings });

  // Theme-merged figure: inject our colorway / fonts / gridlines from CSS
  // tokens. PlotPanel still owns `margin` after this, so the header-aware
  // top spacing stays under one owner.
  const themed = useMemo(
    () => (plot.data ? applyTheme(plot.data.figure) : null),
    [plot.data],
  );

  return (
    <div className={`plot-panel${plot.error ? " error" : ""}`}>
      {header}
      {plot.isFetching && <div className="loading">Loading {spec}…</div>}
      {plot.error && (
        <div className="error">
          <strong>{spec}:</strong> {(plot.error as Error).message}
        </div>
      )}
      {themed && !plot.isFetching && !plot.error && (
        <Suspense fallback={<div className="loading">Loading plot library…</div>}>
          <Plot
            data={themed.data as never}
            layout={{
              ...(themed.layout as object),
              autosize: true,
              margin: { l: 50, r: 16, t: header ? 16 : 36, b: 40 },
              // Box / lasso are the conventional selection tools. Showing
              // them in the modebar lets the user choose; either fires
              // `onSelected` with the same payload shape.
              dragmode: onSelected ? "select" : undefined,
            }}
            style={{ width: "100%", height: `${height}px` }}
            useResizeHandler
            config={{ displaylogo: false, responsive: true }}
            onSelected={
              onSelected
                ? ((event: PlotlySelectionEvent | undefined) => {
                    const points = event?.points ?? [];
                    const ids = points
                      .map((p) => (p && typeof p.customdata === "string" ? p.customdata : null))
                      .filter((x): x is string => !!x);
                    // Dedupe — a single point can appear in multiple traces
                    // (e.g. categorical hue split sub-traces for the same row).
                    onSelected([...new Set(ids)]);
                  }) as never
                : undefined
            }
            onDeselect={onSelected ? (() => onSelected([])) as never : undefined}
          />
        </Suspense>
      )}
    </div>
  );
}
