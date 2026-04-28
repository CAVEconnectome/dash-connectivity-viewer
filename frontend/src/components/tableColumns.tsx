/**
 * Shared bits for the rich-table widgets (PartnersTable, TableRowsView).
 *
 * Anything two-or-more grids need lives here:
 *   - column-kind inference (category / number / string)
 *   - per-column filter input widgets (dropdown / range / contains)
 *   - cell formatting
 *
 * Extending: a new kind goes here once and both widgets pick it up.
 */

import { useState, type MouseEvent } from "react";
import { classify, profileToFilterKind, type FilterKind } from "../plots/columns";

/**
 * Legacy alias — the new shared classifier (`plots/columns.ts`) returns
 * `FilterKind`. Re-exported as `ColumnKind` so existing imports compile
 * without churn.
 */
export type ColumnKind = FilterKind;

export function inferKind(col: string, rows: Record<string, unknown>[]): ColumnKind {
  return profileToFilterKind(classify(col, rows));
}

export function formatCell(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(2);
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

/**
 * Click-to-copy renderer for opaque-id cells (root_id, cell_id).
 *
 * Long int64 ids are tedious to select-and-copy by hand because their
 * monospace text spans multiple table columns visually and cell selection
 * easily overruns. A click writes the full id to the clipboard and shows
 * a brief "copied" indicator in place of the text. Falls back to displaying
 * the value untouched when navigator.clipboard is unavailable (older
 * browsers, file:// origins).
 */
export function CopyableId({ value }: { value: unknown }) {
  const [copied, setCopied] = useState(false);
  const display = formatCell(value);
  if (display === "") return null;

  const onCopy = async (e: MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(display);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {
      // Clipboard API unavailable — leave the cell as plain text.
    }
  };

  return (
    <span
      className={`copyable-id${copied ? " copied" : ""}`}
      onClick={onCopy}
      title={copied ? "copied!" : "click to copy"}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onCopy(e as unknown as MouseEvent);
        }
      }}
    >
      {copied ? "copied!" : display}
    </span>
  );
}

interface FilterInputProps {
  kind: ColumnKind;
  options?: string[];
  value: unknown;
  onChange: (next: unknown) => void;
}

export function FilterInput({ kind, options, value, onChange }: FilterInputProps) {
  if (kind === "category") {
    return (
      <select
        value={(value as string) ?? ""}
        onChange={(e) => onChange(e.target.value || undefined)}
      >
        <option value="">all</option>
        {options?.map((o) => (
          <option key={o} value={o}>{o}</option>
        ))}
      </select>
    );
  }
  if (kind === "number") {
    return <NumberRangeInput value={value} onChange={onChange} />;
  }
  return (
    <input
      type="text"
      placeholder="contains…"
      value={(value as string) ?? ""}
      onChange={(e) => onChange(e.target.value || undefined)}
    />
  );
}

/**
 * Single-input numeric filter that accepts terse range syntax. Examples:
 *   `5`        → ≥ 5
 *   `>5`       → > 5
 *   `<10` `≤10` → ≤ 10
 *   `=5`       → exactly 5
 *   `5-10` `5..10` → 5 ≤ x ≤ 10
 */
function NumberRangeInput({ value, onChange }: { value: unknown; onChange: (next: unknown) => void }) {
  const [text, setText] = useState(() => rangeToText(value));
  return (
    <input
      type="text"
      placeholder="e.g. 5  or  5-10"
      value={text}
      onChange={(e) => {
        const next = e.target.value;
        setText(next);
        if (next.trim() === "") {
          onChange(undefined);
          return;
        }
        const parsed = parseRange(next);
        if (parsed) onChange(parsed);
      }}
    />
  );
}

function rangeToText(v: unknown): string {
  if (!v || typeof v !== "object") return "";
  const { min, max } = v as { min?: number; max?: number };
  if (min !== undefined && max !== undefined) {
    return min === max ? `=${min}` : `${min}-${max}`;
  }
  if (min !== undefined) return `≥${min}`;
  if (max !== undefined) return `≤${max}`;
  return "";
}

function parseRange(s: string): { min?: number; max?: number } | null {
  const t = s.trim();
  // =5  →  exactly 5  (encoded as min=max so the existing range filter handles it)
  const eq = t.match(/^=\s*(-?\d+(?:\.\d+)?)$/);
  if (eq) {
    const n = Number(eq[1]);
    return { min: n, max: n };
  }
  const range = t.match(/^(-?\d+(?:\.\d+)?)\s*(?:-|\.\.|to)\s*(-?\d+(?:\.\d+)?)$/);
  if (range) return { min: Number(range[1]), max: Number(range[2]) };
  const lt = t.match(/^[<≤]=?\s*(-?\d+(?:\.\d+)?)$/);
  if (lt) return { max: Number(lt[1]) };
  const gt = t.match(/^[>≥]=?\s*(-?\d+(?:\.\d+)?)$/);
  if (gt) return { min: Number(gt[1]) };
  if (/^-?\d+(\.\d+)?$/.test(t)) return { min: Number(t) };
  return null;
}
