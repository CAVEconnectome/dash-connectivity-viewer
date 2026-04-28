# dash-connectivity-viewer

A Flask API + React/TypeScript SPA for browsing CAVE (Connectome Annotation
Versioning Engine) connectivity data.

The package name `dash_connectivity_viewer` is historical; the runtime no
longer depends on Dash.

## Layout

- `dash_connectivity_viewer/api/` — Flask backend
- `frontend/` — Vite + React + TypeScript SPA
- `dash_connectivity_viewer/api/datastacks/*.yaml` — per-datastack config
  (synapse columns, aggregation rules, cell-id lookup tables, warmup)
- `dash_connectivity_viewer/api/templates/{links,plots}/*.yaml` — declarative
  Neuroglancer link recipes and Plotly figure specs

## Running locally

```bash
# Backend (uv-managed). AirPlay squats on port 5000 — use 5001 locally.
DCV_DEV_AUTH_BYPASS=1 DCV_PORT=5001 uv run python run_api.py

# Frontend
cd frontend
npm install
npm run dev
```

`DCV_DEV_AUTH_BYPASS=1` skips the middle-auth-client check so a local dev
environment doesn't need a CAVE token in cookies. Production must run without it.

Additional datastack configs can be loaded by setting
`DCV_DATASTACK_CONFIG_DIR` to a directory of YAML files alongside the bundled
ones in `api/datastacks/`.

## Architecture notes

See `CLAUDE.md` for the architecture overview, caching strategy, and the
connectomics-specific design decisions baked into the SPA.
