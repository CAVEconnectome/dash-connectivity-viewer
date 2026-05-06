# Plan: Recipes + Examples landing page (Item C)

**Status when this plan was written**: A1, A2, B, D are complete and deployed.
The container at `http://localhost:8000` is running `dcv:dev` in real-auth mode
with `DCV_CACHE_SERIALIZE=pickle`. Item C is the next piece.

This plan captures every design decision the user and I locked in across the
prior conversation so a fresh-context session can resume without re-litigating.

---

## What landed before this plan

For grounding when picking up:

- **A1 — Live timestamp pinning** (`services/request_state.py`,
  `before_request` hook in `init_request_state`). Every CAVE call within one
  live-mode request shares one `datetime.now(utc)` pinned via `flask.g`.
  Materialized mode timestamp is None for query consistency (version number
  IS the consistency primitive); derived from version metadata only when
  `suggest_current_root` needs it.
- **A2 — Delta-driven decoration cache for live mode**
  (`services/decoration.py::lookup_decorations` + `_apply_live_delta`). Warm
  bulk snapshot + per-request `client.chunkedgraph.get_delta_roots` once,
  targeted `pt_root_id__in=` fetch only for affected partners.
- **B — Stale-root auto-update** (`services/neuron.py::suggest_current_root`,
  `endpoints/connectivity.py`). When both partner directions come back empty,
  call `client.chunkedgraph.suggest_latest_roots` (note: PLURAL method name —
  this was a bug we caught), retry with the suggested root, surface
  `root_id_updated` on the response. Frontend rewrites `?root=` and shows a
  blue accent banner (`.root-swap-notice`).
- **D — Hidden columns in URL state** (`?hide=`, `?show=`, `?coll=` in
  `PartnersTable.tsx`). One-shot localStorage migration on first mount.
  Critical prerequisite for C: Examples can bake `hide`/`show`/`coll` into
  their stored URL.
- **Cache-Control headers on the SPA shell** (just before this plan).
  `index.html` is `no-cache`; hashed assets are `immutable`. Future deploys
  don't require hard reload.
- **Vectorized spatial + decoration post-processing**. Spatial 4146→21ms,
  decoration ~6× per cold table.
- **Cross-request caches** for `attach_spatial_features` and `soma_summary`
  (keyed on `(ds, mat_version, root_id, soma_table)`).
- **Cache serializer abstraction**, ready for Redis swap.

The whole feature catalog is greppable via the conversation log if needed —
this plan just covers C.

---

## Goal of C

**Discoverability.** Lower the activation cost for new and occasional users.
A landing page surfaces curated tour cards that demonstrate workflows.
Each card communicates *what data is loaded* and *what plots/filters are
configured*, so the menu itself doubles as a tour of capabilities.

---

## Naming (LOCKED IN)

- **Example** — fully specified: includes `ds + mv + root + decorations
  + plots + bindings + hidden columns`. CTA: "**Open**". Click and you land
  on a fully-configured workspace looking at a real neuron.
- **Recipe** — lightweight: only `decorations + plots + bindings + hidden
  columns + cell-filter expressions`. NO ds/mv/root. CTA: "**Apply**".
  Click and the recipe overlays onto the user's currently-loaded neuron.

User explicitly ruled out "view" (overloaded with CAVE materialized views,
table views, etc.). "Recipe" reuses existing terminology from
`templates/plots/*.yaml`. "Example" is the discoverability framing.

---

## Design decisions (LOCKED IN)

1. **Operator-curated only** for v1. No user-saved state. Lives in the
   per-datastack YAML so deployments control what's recommended.
2. **Multiple Examples + multiple Recipes per datastack.** Cards are
   datastack-grouped on the landing page.
3. **Landing page replaces `/`'s blank redirect.** Replaces the current
   `<Navigate to="/neuron" replace />` index route with a tour-card view.
4. **Sidebar widget surfaces Recipes only**, scoped to the currently-selected
   datastack. Lets a user already in the workspace apply a Recipe without
   navigating back to `/`. Examples don't appear in the sidebar (they're
   navigation-style, belong on the landing page).
5. **Apply behavior**: replace, with confirmation toast. Undo is "gravy"
   (nice-to-have, not required for v1). User said: "My instinct is to replace
   with confirmation and undo is gravy."
6. **Stale-root handling**: do nothing proactive. If an Example's
   `starting_root` is stale at the user's chosen `mv`, the existing B-path
   handles it — synapse query returns empty, `suggest_latest_roots` translates,
   the existing `root_id_updated` banner surfaces. **No special case in C.**
7. **Live-query timestamp consistency**: A1's request-state pinning means
   all CAVE queries in a single Example-loading request share one timestamp.
   No new work in C.
8. **Hidden columns in YAML**: D's URL state means Examples/Recipes can
   bake hidden columns directly into the URL via `hide=col1,col2`. No new
   schema beyond passing through.

## Schema (proposed; refine in implementation)

Per-datastack YAML in `config/datastacks/*.yaml` gains
two new top-level keys: `examples` and `recipes`.

```yaml
# minnie65_phase3_v1.yaml (excerpt — extends existing schema)
examples:
  - id: l23-pyr-deep-dive
    title: "L2/3 pyramidal — full deep-dive"
    description: "Cell type + proofreading + synapse depth, with bindings demonstrating reciprocal-pair analysis on a known interesting cell."
    mat_version: 1764
    root: "864691135571440006"
    decoration_tables:
      - cell_type_multifeature_combo
      - proofreading_status_and_strategy
    plots:
      - id: depth-profile
        summary_kind: synapse_depth_profile
      - id: ct-bar-in
        bindings: { x: "cell_type_multifeature_combo.cell_type", weight: "n_syn_in" }
      - id: scatter-pos
        bindings: { x: "soma_x", y: "soma_z", hue: "cell_type_multifeature_combo.cell_type" }
    cells: "proofreading_status_and_strategy.status_axon:eq:true"  # optional, raw URL form
    hide: ["proofreading_status_and_strategy.valid_id"]  # optional
    show: []  # optional
    coll: []  # optional collapsed groups

recipes:
  - id: depth-stratification-starter
    title: "Depth stratification starter"
    description: "Loads cell-type + soma-depth + synapse-depth-profile. Apply on any neuron to see its layered partner distribution."
    decoration_tables: [cell_type_multifeature_combo]
    plots:
      - id: depth-profile
        summary_kind: synapse_depth_profile
      - id: depth-by-ct
        bindings: { x: "soma_depth", y: "median_syn_depth_out", hue: "cell_type_multifeature_combo.cell_type" }
    hide: []
```

Schema notes:

- `plots` shape mirrors what the SPA already encodes in `?plots=` + `?viz_<id>=`.
  Backend renders to a comma-separated `?plots=` list and per-plot `?viz_<id>=`
  JSON. The Example's URL is built deterministically from this.
- `bindings` matches the `PlotBindings` interface in
  `frontend/src/api/queries.ts`. Validation against backend
  `services/plots.py::PlotSpec` happens at YAML-load time (catch typos at
  deploy, not at click).
- `summary_kind` for non-bindings panels (currently only
  `synapse_depth_profile`). Same enum as `frontend/src/plots/presets.ts`.
- `cells` is the raw `?cells=` URL value (the existing CellFilter syntax in
  `services/plots.py::_parse_cells_param`).
- `hide` / `show` / `coll` are arrays that get `.join(",")`'d into the URL.

## Backend changes

1. **YAML schema additions**: `services/datastack_config.py` parses
   `examples` and `recipes` blocks. Each entry is validated via Pydantic
   models — typo'd plot bindings or missing decorations fail at startup
   (same posture as plot-recipe loading in `services/plots.py::load_plot_specs`).

2. **New endpoint**: `GET /api/v1/datastacks/<ds>/tours` returning
   `{examples: [...], recipes: [...]}`. The SPA's landing page hits this
   per datastack to render cards.

3. **No URL minting on the backend.** Instead, return the raw YAML data
   and let the SPA construct the URL using the existing URL-state
   conventions. Keeps the backend stateless and the URL minting logic
   in one place (the SPA already builds URLs for navigations).

4. **Validation seam**: a `validate_tour(tour, datastack_config) -> list[str]`
   helper that checks every referenced decoration table exists, every
   plot binding column is loadable, etc. Run at YAML-load and on
   datastack reload. Returns warnings as a list; fatal errors raise.

## Frontend changes

1. **New route**: `<Route index element={<LandingPage />} />` replaces the
   `<Navigate to="/neuron" replace />`. Workspace shell stays mounted
   (sidebar visible) so the user can pick a datastack from the side too.

2. **`LandingPage` component**: card grid grouped by datastack. For each
   datastack, two sections: "Examples" (with `Open` buttons) and
   "Recipes" (with `Apply` buttons but disabled when no current `?root=`
   is set on the URL — clicking it would have nothing to apply onto).

3. **Card rendering**: tile with `title`, `description`, and a small
   summary of what'll load (e.g. "Loads 2 decoration tables, 3 plots").
   Click → constructs URL → `useNavigate()`.

4. **`useApplyRecipe` hook** (or inline logic): given a Recipe and the
   current URL state, compute the merged URL state and confirm with the
   user before committing. Confirmation as a toast/dialog showing what
   changes (decoration tables added/removed, plots added/removed).
   On confirm: call the existing `useSetUrlParams()` batch helper.

5. **Sidebar widget**: a "Recipes…" dropdown in the sidebar that lists
   recipes for the currently-selected datastack. Click → same apply flow
   as the landing page.

6. **Stale-root behavior is automatic**. If an Example's `starting_root`
   is no longer current at its `mat_version`, the connectivity request
   returns `root_id_updated`, the existing `.root-swap-notice` banner
   shows, the URL silently rewrites. No new code in C.

## Open design questions

These weren't fully resolved in the prior conversation; pick when implementing:

1. **What does `Apply Recipe` do when the recipe has plots that conflict
   with the user's current plots?** Replace all plots? Merge plots
   (append)? Replace `?plots=` URL param entirely vs. union with
   existing? My instinct from the user's "replace + confirm" was full
   replacement. Confirm in implementation.

2. **Cards layout — width-aware grid or fixed columns?** Probably
   responsive grid (CSS `grid-template-columns: repeat(auto-fill,
   minmax(320px, 1fr))`) so it adapts to viewport width.

3. **Should Examples list `mat_version`** prominently on the card?
   Probably yes — "Loads at v1764" is informative and lets the user
   know if it'll be subject to stale-root translation under their
   current `mv` setting.

4. **Should the landing page also surface recently-visited cells**
   (from localStorage)? Probably not for v1 — that's a "history" feature
   that's separable from operator-curated tours.

5. **Empty-state**: what if a datastack has no Examples and no Recipes?
   Probably show "No tours configured for this datastack — pick from the
   sidebar to start fresh."

## Implementation order

1. Backend YAML schema + parser + validation. (Pydantic models in
   `services/datastack_config.py`.)
2. `GET /datastacks/<ds>/tours` endpoint.
3. Smoke test backend with a minimal Example + Recipe in
   `minnie65_public.yaml`.
4. Frontend types matching the YAML.
5. URL-minting helper that turns an Example into a fully-formed URL.
6. `LandingPage` component + route.
7. `applyRecipe` flow + confirmation UI.
8. Sidebar Recipes widget.
9. End-to-end test in the browser with a real Example + Recipe.

Step 3 is the natural pause point for human review — the operator-facing
schema is the load-bearing piece; everything else is plumbing on top.

---

## Quick re-orientation for the next session

```bash
# Container is running:
docker ps | grep dcv-test

# Logs (request_timing, cache.deserialize_failed, root_translation):
docker logs -f dcv-test

# Rebuild after changes:
docker rm -f dcv-test
docker build -t dcv:dev .
docker run -d --name dcv-test -p 8000:8000 \
  -e GLOBAL_SERVER=global.daf-apis.com \
  -e AUTH_URI=global.daf-apis.com/auth \
  -e AUTH_URL=global.daf-apis.com/auth \
  -e INFO_URL=global.daf-apis.com/info \
  -e STICKY_AUTH_URL=global.daf-apis.com/sticky_auth \
  -e DCV_CACHE_SERIALIZE=pickle \
  dcv:dev

# Frontend dev (when iterating):
cd frontend
npm run build  # to rebuild dist/ in place
# ...or run vite dev server alongside Flask for HMR

# Per-datastack YAML:
ls config/datastacks/*.yaml
```

The user is a working connectomics scientist (Casey). They prefer terse
responses, value engineering correctness, and pushed back on
overengineering at multiple points. Match that posture.
