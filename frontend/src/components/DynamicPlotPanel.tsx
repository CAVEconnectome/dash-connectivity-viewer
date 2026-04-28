import { useMemo } from "react";
import type { ConnectivityBundle } from "../api/types";
import { useUrlParam } from "../hooks/useUrlState";
import { classify, type ColumnProfile } from "../plots/columns";
import { directionalColumnNames, unifyColumnGroups, unifyPartners } from "../plots/unify";
import {
  AXIS_SCOPES,
  encodeVizParam,
  parseVizParam,
  vizParamKey,
  type AxisScope,
  type PlotBindings,
} from "../plots/urlState";
import type { DynamicPlotDescriptor } from "../plots/registry";
import { PlotPanel } from "./PlotPanel";

interface Props {
  descriptor: DynamicPlotDescriptor;
  ds: string;
  rootId: string;
  matVersion: number | "live";
  bundle: ConnectivityBundle;
  decorationTables: string[];
  /** Optional close handler — when present a "✕" button appears in the
   *  panel header so the user can drop the panel from `?plots=`. */
  onClose?: () => void;
  /** Brush / lasso selection callback (proxied to PlotPanel). Receives the
   *  deduped list of selected partner root_ids — the AnalyticsRail uses this
   *  to write the per-plot URL `?sel_<id>=` key for cross-component filtering. */
  onSelected?: (rootIds: string[]) => void;
}

type Channel = "x" | "y" | "hue" | "size";

const CHANNEL_LABEL: Record<Channel, string> = {
  x: "x",
  y: "y",
  hue: "hue",
  size: "size",
};

/**
 * Per-row column option for the channel pickers, with classification info
 * so each picker can grey out columns that aren't suitable for that channel.
 * (e.g. a string column can be x/y but not size; an id-shaped column is
 * always rejected; a high-cardinality non-numeric column can't drive hue.)
 */
interface ColumnOption {
  group: string;
  key: string;
  display: string;
  profile: ColumnProfile;
}

/**
 * Produce picker options spanning *both* directions' columns. Walks the
 * unified column groups (which split the synapse group into _in / _out
 * pairs) and classifies each column against the unified rows.
 *
 * Also injects a synthetic `direction` option in a "synthetic" group —
 * a hue-only channel that the backend computes as a categorical column on
 * the unified frame (presynaptic / postsynaptic / reciprocal).
 */
function listColumnOptions(bundle: ConnectivityBundle): ColumnOption[] {
  const directional = directionalColumnNames(bundle.column_groups);
  const unifiedRows = unifyPartners(
    bundle.partners_out ?? [],
    bundle.partners_in ?? [],
    directional,
  ) as unknown as Record<string, unknown>[];
  const unifiedGroups = unifyColumnGroups(bundle.column_groups, directional);

  const options: ColumnOption[] = [];
  for (const g of unifiedGroups) {
    if (g.kind === "intrinsic") continue;
    for (const col of g.columns) {
      const profile = classify(col, unifiedRows);
      const display = col.includes(".") ? col.slice(col.indexOf(".") + 1) : col;
      options.push({ group: g.name, key: col, display, profile });
    }
  }
  // Synthetic direction-class hue. Backend computes it server-side on the
  // unified frame so we don't materialize the column on the SPA. Hue-only;
  // not useful as x/y (it's a 3-value enum) or size (not numeric).
  options.push({
    group: "synthetic",
    key: "direction",
    display: "direction (pre / post / reciprocal)",
    profile: {
      vocabulary: "categorical-palette",
      cardinality: 3,
      isNumeric: false,
      isIdShaped: false,
      suitableFor: { x: false, y: false, hue: true, size: false },
    },
  });
  return options;
}

/**
 * Runtime-configurable plot panel.
 *
 * Reads/writes its bindings to a JSON-encoded URL key (`?viz_<id>={...}`).
 * The header carries four channel pickers (x / y / hue / size); only
 * options whose `suitableFor[channel]` is true are selectable. Hue/size
 * pickers are visually disabled when the binding combo doesn't render
 * them (e.g. size on a histogram).
 *
 * Backend dispatch: 1-of-(x,y) bound → histogram. Both bound → scatter.
 * The `<PlotPanel>` is reused to do the actual fetch + theme + render.
 */
export function DynamicPlotPanel({
  descriptor,
  ds,
  rootId,
  matVersion,
  bundle,
  decorationTables,
  onClose,
  onSelected,
}: Props) {
  const [raw, setRaw] = useUrlParam(vizParamKey(descriptor.id));
  const bindings: PlotBindings = useMemo(() => parseVizParam(raw), [raw]);
  const setChannel = (ch: Channel, value: string | null) => {
    const next: PlotBindings = { ...bindings, [ch]: value || undefined };
    const encoded = encodeVizParam(next);
    setRaw(encoded === "{}" ? null : encoded);
  };
  const setScope = (axis: "x_scope" | "y_scope", value: AxisScope) => {
    const next: PlotBindings = { ...bindings, [axis]: value };
    const encoded = encodeVizParam(next);
    setRaw(encoded === "{}" ? null : encoded);
  };

  const options = useMemo(() => listColumnOptions(bundle), [bundle]);

  // Visual hints for disabled channels:
  //   - histogram (only x XOR y bound) hides hue / size from the user (they're ignored).
  //   - scatter shows all four.
  const haveAxis = !!(bindings.x || bindings.y);
  const haveScatter = !!(bindings.x && bindings.y);

  const xScope: AxisScope = (bindings.x_scope ?? "both") as AxisScope;
  const yScope: AxisScope = (bindings.y_scope ?? "both") as AxisScope;

  const header = (
    <div className="plot-panel-header dynamic">
      <span className="plot-panel-title" title={descriptor.title}>
        {descriptor.title}
      </span>
      <div className="dynamic-pickers">
        {(Object.keys(CHANNEL_LABEL) as Channel[]).map((ch) => {
          const ignored =
            (ch === "hue" && !haveScatter) ||
            (ch === "size" && !haveScatter);
          const isAxis = ch === "x" || ch === "y";
          const scopeAxis = ch === "x" ? "x_scope" : "y_scope";
          const scopeValue = ch === "x" ? xScope : yScope;
          return (
            <span key={ch} className={`dynamic-picker-group${isAxis ? " axis" : ""}`}>
              <ChannelPicker
                channel={ch}
                value={bindings[ch] ?? null}
                options={options}
                disabledReason={ignored ? "needs both x and y" : null}
                onChange={(v) => setChannel(ch, v)}
              />
              {isAxis && (
                <ScopeSelect
                  value={scopeValue}
                  onChange={(v) => setScope(scopeAxis, v)}
                />
              )}
            </span>
          );
        })}
        {onClose && (
          <button
            type="button"
            className="dynamic-close"
            onClick={onClose}
            title="Remove this plot"
            aria-label="Remove this plot"
          >
            ✕
          </button>
        )}
      </div>
    </div>
  );

  if (!haveAxis) {
    return (
      <div className="plot-panel">
        {header}
        <div className="loading">Pick at least one axis to plot.</div>
      </div>
    );
  }

  return (
    <PlotPanel
      ds={ds}
      spec={descriptor.spec}
      rootId={rootId}
      matVersion={matVersion}
      decorationTables={decorationTables}
      bindings={bindings}
      height={300}
      header={header}
      onSelected={onSelected}
    />
  );
}

interface ScopeSelectProps {
  value: AxisScope;
  onChange: (v: AxisScope) => void;
}

const SCOPE_LABEL: Record<AxisScope, string> = {
  both: "both",
  pre: "pre",
  post: "post",
};

const SCOPE_TOOLTIP: Record<AxisScope, string> = {
  both: "all partners (no direction filter)",
  pre: "presynaptic to root (input partners)",
  post: "postsynaptic to root (output partners)",
};

/**
 * Per-axis pre/post scope selector. Sits next to the channel picker for
 * x and y on dynamic panels (the only place the unified frame is used).
 * Combine x=post, y=pre to isolate reciprocal partners.
 */
function ScopeSelect({ value, onChange }: ScopeSelectProps) {
  return (
    <select
      className={`dynamic-scope${value !== "both" ? " active" : ""}`}
      value={value}
      onChange={(e) => onChange(e.target.value as AxisScope)}
      title={`scope: ${SCOPE_TOOLTIP[value]}`}
    >
      {AXIS_SCOPES.map((s) => (
        <option key={s} value={s}>{SCOPE_LABEL[s]}</option>
      ))}
    </select>
  );
}

interface ChannelPickerProps {
  channel: Channel;
  value: string | null;
  options: ColumnOption[];
  disabledReason: string | null;
  onChange: (v: string | null) => void;
}

function ChannelPicker({ channel, value, options, disabledReason, onChange }: ChannelPickerProps) {
  // Group options for the dropdown via <optgroup>. Greyed entries (not
  // suitable for this channel) stay visible but disabled, so users see
  // what columns *exist* and why they're unavailable.
  const grouped = useMemo(() => {
    const byGroup = new Map<string, ColumnOption[]>();
    for (const opt of options) {
      if (!byGroup.has(opt.group)) byGroup.set(opt.group, []);
      byGroup.get(opt.group)!.push(opt);
    }
    return [...byGroup.entries()];
  }, [options]);

  return (
    <label className={`dynamic-picker${disabledReason ? " disabled" : ""}`} title={disabledReason ?? ""}>
      <span className="dynamic-picker-label">{CHANNEL_LABEL[channel]}</span>
      <select
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value || null)}
        disabled={!!disabledReason}
      >
        <option value="">—</option>
        {grouped.map(([groupName, opts]) => (
          <optgroup key={groupName} label={groupName}>
            {opts.map((o) => (
              <option
                key={o.key}
                value={o.key}
                disabled={!o.profile.suitableFor[channel]}
              >
                {o.display}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
    </label>
  );
}
