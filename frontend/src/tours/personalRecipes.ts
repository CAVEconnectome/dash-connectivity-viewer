/**
 * Browser-local personal recipes — the user's own saved configurations,
 * persisted in localStorage. No backend storage.
 *
 * Storage shape (single key `dcv:recipes`):
 *
 *     { version: 1, byDs: { "<datastack>": [Recipe, ...] } }
 *
 * Single-key chosen over per-datastack keys: one read at sidebar mount,
 * atomic writes, future "export all my recipes" is a one-liner. Per-
 * datastack keys would multiply the parse/serialize work without
 * benefit at this scale (recipes are tiny JSON).
 *
 * Mutations dispatch a `dcv:personal-recipes-changed` window event so
 * sibling components (the SidebarRecipes widget) can re-read without a
 * shared state store.
 */
import type { Recipe } from "../api/types";

const STORAGE_KEY = "dcv:recipes";
const CHANGE_EVENT = "dcv:personal-recipes-changed";

interface StoredRecipes {
  version: 1;
  byDs: Record<string, Recipe[]>;
}

const EMPTY: StoredRecipes = { version: 1, byDs: {} };

function readAll(): StoredRecipes {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { version: 1, byDs: {} };
    const obj = JSON.parse(raw) as Partial<StoredRecipes>;
    if (obj && typeof obj === "object" && obj.version === 1 && obj.byDs && typeof obj.byDs === "object") {
      return { version: 1, byDs: obj.byDs as Record<string, Recipe[]> };
    }
    return { version: 1, byDs: {} };
  } catch {
    // Quota exceeded, private mode, malformed JSON — treat as empty.
    return { version: 1, byDs: {} };
  }
}

function writeAll(data: StoredRecipes): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    window.dispatchEvent(new CustomEvent(CHANGE_EVENT));
  } catch {
    // Silently degrade — we don't have a UX-affordance for storage
    // failures and they're rare. Caller's optimistic UI update will
    // simply not be reflected on next mount.
  }
}

export function listForDs(ds: string): Recipe[] {
  return readAll().byDs[ds] ?? [];
}

export function save(ds: string, recipe: Recipe): void {
  const all = readAll();
  const list = all.byDs[ds] ?? [];
  // De-dupe by id — `save` doubles as upsert. Personal recipe ids are
  // generated to be unique, but defensive against an odd retry flow.
  const next = [...list.filter((r) => r.id !== recipe.id), recipe];
  writeAll({ version: 1, byDs: { ...all.byDs, [ds]: next } });
}

export function remove(ds: string, id: string): void {
  const all = readAll();
  const list = all.byDs[ds] ?? [];
  const next = list.filter((r) => r.id !== id);
  if (next.length === list.length) return;  // nothing to do
  writeAll({ version: 1, byDs: { ...all.byDs, [ds]: next } });
}

export function exists(ds: string, id: string): boolean {
  return listForDs(ds).some((r) => r.id === id);
}

/** Generate a fresh personal-recipe id. The `personal-` prefix lets the
 *  merged sidebar list discriminate operator vs personal recipes without a
 *  separate flag, and guarantees no collision with operator ids (which
 *  come from YAML keys and never start with `personal-`). */
export function newPersonalId(): string {
  const ts = Date.now().toString(36);
  const rnd = Math.random().toString(36).slice(2, 6);
  return `personal-${ts}-${rnd}`;
}

export function isPersonalId(id: string): boolean {
  return id.startsWith("personal-");
}

/** Subscribe to mutation events. Returns an unsubscribe function. */
export function subscribe(listener: () => void): () => void {
  window.addEventListener(CHANGE_EVENT, listener);
  return () => window.removeEventListener(CHANGE_EVENT, listener);
}

// Re-export the empty constant for callers that want a stable reference.
export const EMPTY_STORE: Readonly<StoredRecipes> = EMPTY;
