"""Stale-while-revalidate decorations for cell-type and per-root-id soma counts.

Both kinds are cached as full per-(ds, mv, table) snapshots — a `dict[int, value]`
that maps every root_id in the table to its decoration value. Caching at this
granularity (one entry per table, not per root_id) means cross-navigation hits
reuse the same in-memory dict, and revalidation is one CAVE call regardless of
how many root_ids the request touched.
"""

import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal

import pandas as pd
from cachetools import TTLCache
from flask import current_app

from .keys import is_live
from .query_runner import run_query


_TICKET_TTL_SECONDS = 5 * 60


class DecorationService:
    """Holds the SWR caches, ticket store, and worker pool for one Flask app."""

    def __init__(self, app):
        from .swr import SwrCache  # local import: avoid cycles at module-load time
        from .revalidation import RevalidationExecutor
        from .warmup import PeriodicWarmer

        self._app = app
        # Both TTL regimes available concurrently — keyed by is_live(mat_version) at call time.
        self.cell_type_mat = SwrCache(
            soft_ttl=app.config["CACHE_DECORATION_SOFT_TTL_SECONDS"],
            hard_ttl=app.config["CACHE_DECORATION_HARD_TTL_SECONDS"],
        )
        self.cell_type_live = SwrCache(
            soft_ttl=app.config["CACHE_DECORATION_LIVE_SOFT_TTL_SECONDS"],
            hard_ttl=app.config["CACHE_DECORATION_LIVE_HARD_TTL_SECONDS"],
        )
        self.num_soma_mat = SwrCache(
            soft_ttl=app.config["CACHE_DECORATION_SOFT_TTL_SECONDS"],
            hard_ttl=app.config["CACHE_DECORATION_HARD_TTL_SECONDS"],
        )
        self.num_soma_live = SwrCache(
            soft_ttl=app.config["CACHE_DECORATION_LIVE_SOFT_TTL_SECONDS"],
            hard_ttl=app.config["CACHE_DECORATION_LIVE_HARD_TTL_SECONDS"],
        )
        # Generic table-decoration cache: any annotation table the SPA names
        # in `decoration_tables` gets fetched whole, keyed by pt_root_id, and
        # joined onto partner records. One cache, keyed (ds, mv, table) per
        # entry. The dedicated cell_type / num_soma caches above are special
        # cases that exist for backwards-compat — generic reuses the same SWR
        # mechanism.
        self.table_decorations_mat = SwrCache(
            soft_ttl=app.config["CACHE_DECORATION_SOFT_TTL_SECONDS"],
            hard_ttl=app.config["CACHE_DECORATION_HARD_TTL_SECONDS"],
            maxsize=64,  # # of distinct (ds, mv, table) snapshots in memory
        )
        self.table_decorations_live = SwrCache(
            soft_ttl=app.config["CACHE_DECORATION_LIVE_SOFT_TTL_SECONDS"],
            hard_ttl=app.config["CACHE_DECORATION_LIVE_HARD_TTL_SECONDS"],
            maxsize=64,
        )
        # Tickets: short-lived per-request snapshots so the SPA's poll can compute deltas.
        self.tickets: TTLCache = TTLCache(maxsize=4096, ttl=_TICKET_TTL_SECONDS)
        self.executor = RevalidationExecutor(
            app, max_workers=app.config["DECORATION_REVALIDATION_WORKERS"]
        )
        self.warmer = PeriodicWarmer(app)

    def cache_for(self, kind: Literal["cell_type", "num_soma", "table"], live: bool):
        if kind == "cell_type":
            return self.cell_type_live if live else self.cell_type_mat
        if kind == "table":
            return self.table_decorations_live if live else self.table_decorations_mat
        return self.num_soma_live if live else self.num_soma_mat

    # --- Tickets --------------------------------------------------------------

    def mint_ticket(self, *, ds: str, mat_version: int | str | None,
                    cell_type_table: str | None, soma_table: str | None,
                    served: dict[int, dict]) -> str:
        ticket_id = uuid.uuid4().hex
        self.tickets[ticket_id] = {
            "ds": ds,
            "mat_version": mat_version,
            "cell_type_table": cell_type_table,
            "soma_table": soma_table,
            "served": served,
            "minted_at": time.time(),
        }
        return ticket_id

    def poll_ticket(self, ticket_id: str) -> dict:
        ticket = self.tickets.get(ticket_id)
        if ticket is None:
            return {"status": "expired"}
        live = is_live(ticket["mat_version"])
        ct_table = ticket["cell_type_table"]
        soma_table = ticket["soma_table"]
        ds = ticket["ds"]
        mv = ticket["mat_version"]
        minted_at = ticket["minted_at"]

        ct_cache = self.cache_for("cell_type", live) if ct_table else None
        soma_cache = self.cache_for("num_soma", live) if soma_table else None

        # Readiness = "the cache entry has been refreshed since the ticket was minted"
        # — independent of soft/hard TTL state, which can re-stale a freshly written value.
        ct_lookup = None
        if ct_cache is not None:
            meta = ct_cache.get_with_meta((ds, mv, ct_table))
            if meta is not None and meta[1] >= minted_at:
                ct_lookup = meta[0]

        soma_lookup = None
        if soma_cache is not None:
            meta = soma_cache.get_with_meta((ds, mv, soma_table))
            if meta is not None and meta[1] >= minted_at:
                soma_lookup = meta[0]

        if (ct_table and ct_lookup is None) or (soma_table and soma_lookup is None):
            return {"status": "in_flight", "retry_after": 2}

        deltas: dict[int, dict[str, Any]] = {}
        for rid_str, served in ticket["served"].items():
            rid = int(rid_str)
            current: dict[str, Any] = {}
            if ct_lookup is not None:
                ct_rec = ct_lookup.get(rid) or {}
                for k, v in ct_rec.items():
                    current[k] = v
            if soma_lookup is not None:
                soma_rec = soma_lookup.get(rid) or {}
                current["num_soma"] = int(soma_rec.get("num_soma", 0))
                if "cell_id" in soma_rec:
                    current["cell_id"] = soma_rec["cell_id"]
            diff = {k: v for k, v in current.items() if served.get(k) != v}
            if diff:
                deltas[rid] = diff
        return {"status": "ready", "deltas": deltas}


def init_decoration_service(app) -> DecorationService:
    service = DecorationService(app)
    app.extensions["dcv_decoration"] = service
    _register_warmup_jobs(app, service)
    service.warmer.start()
    return service


def _latest_valid_version(client) -> int | None:
    metadata = client.materialize.get_versions_metadata()
    valid = [int(m["version"]) for m in metadata if m.get("valid", True)]
    return max(valid) if valid else None


def _register_warmup_jobs(app, service: "DecorationService") -> None:
    """Walk the configured datastacks directory; for each datastack with an
    enabled `decoration_warmup` block, register periodic refresh jobs. Each
    job re-resolves the latest valid materialized version at every fire and
    keys the cache by that version, so the warm cache rolls forward when new
    versions land upstream.

    Warmup is one of two sanctioned anonymous-auth code paths (the other is
    dev bypass). It uses `make_client_anonymous(env_token_var=...)` so audit
    trails record every fire, and the env-var-supplied token is preferred over
    the local cave-secret fallback.
    """
    from pathlib import Path

    import yaml

    from ..cave import make_client_anonymous

    config_dir = app.config.get("DATASTACK_CONFIG_DIR")
    if not config_dir:
        return
    config_path = Path(config_dir)
    if not config_path.is_dir():
        return

    server_address = app.config["GLOBAL_SERVER_ADDRESS"]

    for yaml_path in sorted(config_path.glob("*.yaml")):
        ds_name = yaml_path.stem
        try:
            data = yaml.safe_load(yaml_path.read_text()) or {}
        except Exception:
            continue
        warmup = (data.get("decoration_warmup") or {})
        if not warmup or not warmup.get("enabled"):
            continue
        interval = float(warmup.get("interval_seconds") or 3600.0)
        startup_delay = float(warmup.get("startup_delay_seconds") or 0.0)
        ct_tables = list(warmup.get("cell_type_tables") or [])
        warm_soma = bool(warmup.get("warm_soma_table"))
        if not ct_tables and not warm_soma:
            continue

        def make_factory(ds: str):
            def cf():
                return make_client_anonymous(
                    ds, server_address, materialize_version=None,
                    reason="warmup", env_token_var="DCV_WARMUP_AUTH_TOKEN",
                )
            return cf

        cf = make_factory(ds_name)

        for ct_table in ct_tables:
            cache = service.cell_type_mat

            def _warm_ct(_cache=cache, _cf=cf, _ds=ds_name, _table=ct_table):
                client = _cf()
                latest = _latest_valid_version(client)
                if latest is None:
                    return
                client.materialize.version = latest
                fresh = _fetch_cell_type_table(client, _table, latest)
                _cache.set((_ds, latest, _table), fresh)

            service.warmer.register(
                f"{ds_name}/cell_type/{ct_table}", _warm_ct, interval, startup_delay
            )

        if warm_soma:
            cache = service.num_soma_mat

            def _warm_soma(_cache=cache, _cf=cf, _ds=ds_name):
                client = _cf()
                latest = _latest_valid_version(client)
                if latest is None:
                    return
                client.materialize.version = latest
                soma_table = client.info.get_datastack_info().get("soma_table")
                if not soma_table:
                    return
                fresh = _fetch_num_soma_table(client, soma_table, latest)
                _cache.set((_ds, latest, soma_table), fresh)
                # Side-populate the cell-id caches from this same fetch — every
                # single-soma row is a (root_id, cell_id) pair, and the soma
                # table is the source of truth for that decoration. Saves a
                # second round-trip against the dedicated lookup view.
                _populate_cell_id_caches_from_soma(fresh, _ds, latest)

            service.warmer.register(
                f"{ds_name}/num_soma", _warm_soma, interval, startup_delay
            )


def get_decoration_service() -> DecorationService:
    return current_app.extensions["dcv_decoration"]


# -- Fetchers (live and materialized share the body; only run_query branches) -

# Forward declaration; the alias is bound below `_fetch_decoration_table`'s
# definition. Search for `_fetch_cell_type_table = _fetch_decoration_table`.


def _fetch_decoration_table(client, table: str, mat_version) -> dict[int, dict]:
    """Fetch a generic annotation table whole, return `{root_id: {col: value}}`.

    Skips system/positional/reference columns; keeps user-meaningful annotation
    fields (cell_type, status flags, scores, free text, …). Rows whose root id
    appears more than once in the table are dropped — an ambiguous mapping —
    so the joined value is always unambiguous per partner.
    """
    qf = client.materialize.tables[table]()
    df = run_query(qf, live=is_live(mat_version), split_positions=True)
    if df.empty:
        return {}
    root_col = "pt_root_id" if "pt_root_id" in df.columns else next(
        (c for c in df.columns if c.endswith("_root_id")), None
    )
    if root_col is None:
        return {}

    # Drop columns that don't carry annotation meaning. Pattern-based to cover
    # arbitrary point-prefixes (ctr_pt, pre_pt, …).
    skip_exact = {
        root_col, "id", "created", "valid", "id_ref", "created_ref",
        "valid_ref", "target_id", "deleted",
    }
    skip_suffixes = (
        "_position_x", "_position_y", "_position_z",
        "_supervoxel_id", "_root_id",
    )
    keep_cols = [
        c for c in df.columns
        if c not in skip_exact and not any(c.endswith(s) for s in skip_suffixes)
    ]

    df = df.drop_duplicates(subset=root_col, keep=False)
    out: dict[int, dict] = {}
    for _, row in df.iterrows():
        rid = row[root_col]
        if rid is None or _is_missing(rid) or int(rid) == 0:
            continue
        rec: dict = {}
        for c in keep_cols:
            v = row[c]
            if _is_missing(v):
                continue
            if hasattr(v, "item"):  # numpy scalar
                v = v.item()
            rec[c] = v
        if rec:
            out[int(rid)] = rec
    return out


# The dedicated cell-type fetcher reuses the generic decoration fetcher so
# the cell_type table also surfaces its other annotation columns (e.g.
# `classification_system`, `volume`). Result shape is `{root_id: {col: val}}`
# — same as a generic decoration table — and `lookup_decorations` merges
# every key flat (no namespace prefix) since the cell_type table is by
# convention the primary, no-conflict annotation source.
_fetch_cell_type_table = _fetch_decoration_table


def _is_missing(v) -> bool:
    """True for None / NaN / pd.NA / NaT — but False for arrays and lists.
    Used during decoration extraction so nullable-dtype rows don't carry
    `pd.NA` through to the JSON encoder.
    """
    if v is None:
        return True
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def _fetch_num_soma_table(client, soma_table: str, mat_version,
                          soma_root_id_column: str = "pt_root_id") -> dict[int, dict]:
    """Per-root-id soma decoration: `{num_soma, cell_id?, pt_position?}`.

    `cell_id` and `pt_position` are included only when a root id has exactly
    one row in the soma/nucleus table — i.e. an unambiguous persistent
    identifier and a single point. Multi-row root ids (proofreading hasn't
    separated them yet, or genuinely a single object spanning multiple nuclei)
    get `num_soma` but no `cell_id` / `pt_position`.

    Positions are returned in nanometers (`desired_resolution=[1,1,1]`) so the
    spatial service can pass them straight into a `_nm` standard_transform.
    """
    qf = client.materialize.tables[soma_table]()
    df = run_query(
        qf,
        live=is_live(mat_version),
        split_positions=True,
        desired_resolution=[1, 1, 1],
        select_columns=[soma_root_id_column, "id", "pt_position"],
    )
    if df.empty:
        return {}
    out: dict[int, dict] = {}
    for root_id, group in df.groupby(soma_root_id_column):
        rid = int(root_id)
        if rid == 0:
            continue
        rec: dict = {"num_soma": int(len(group))}
        if len(group) == 1:
            row = group.iloc[0]
            rec["cell_id"] = str(int(row["id"]))
            xs = (row.get("pt_position_x"), row.get("pt_position_y"), row.get("pt_position_z"))
            if all(v is not None and not _is_missing(v) for v in xs):
                rec["pt_position"] = [float(xs[0]), float(xs[1]), float(xs[2])]
        out[rid] = rec
    return out


def _populate_cell_id_caches_from_soma(
    soma_dict: dict[int, dict],
    datastack: str,
    mat_version: int | None,
) -> None:
    """The soma fetch is also the canonical source of cell-id ↔ root-id pairs
    for the single-soma case (the only case where cell_id is meaningful).
    Every entry in the dict that has a `cell_id` field becomes:
        _root_to_cell[(ds, root_id)]                = cell_id
        _cell_to_root_mat[(ds, mv, cell_id)]        = root_id

    Multi-soma roots are also recorded as `None` in the root→cell cache —
    they're known-ambiguous, no point re-querying.
    """
    from .cell_id import _cell_to_root_mat, _lock, _root_to_cell

    with _lock:
        for rid, rec in soma_dict.items():
            if "cell_id" in rec:
                cid = int(rec["cell_id"])
                _root_to_cell[(datastack, rid)] = cid
                if mat_version is not None:
                    _cell_to_root_mat[(datastack, int(mat_version), cid)] = rid
            else:
                _root_to_cell[(datastack, rid)] = None


# -- Lookup with SWR semantics --------------------------------------------------

def lookup_decorations(
    *,
    client_factory,           # () -> CAVEclient (captures auth + datastack + mv)
    ds: str,
    mat_version: int | str | None,
    cell_type_table: str | None,
    soma_table: str | None,
    soma_root_id_column: str,
    root_ids: list[int],
    decoration_tables: list[str] | None = None,
) -> tuple[dict[int, dict], list[dict], dict[str, Any] | None]:
    """Resolve cell_type / num_soma for `root_ids`. Returns (lookup, revalidation).

    `lookup` is `{root_id: {cell_type?, num_soma?}}` populated from cache (fresh or
    stale). `revalidation` is None on full-fresh hit; otherwise carries
    `{pending_root_ids, ticket_id, poll_url}` and a background refresh has been
    queued. If the cache had no usable hit (cold or past hard TTL) the underlying
    fetcher runs synchronously here so the response is correct, just slower.
    """
    service = get_decoration_service()
    live = is_live(mat_version)
    has_stale = False

    # ct_lookup is now a full annotation snapshot (every column from the cell-
    # type table), not just `cell_type`. Keys merge flat onto served records.
    ct_lookup: dict[int, dict[str, Any]] | None = None
    # `soma_lookup[root_id] = {"num_soma": int, "cell_id"?: str}` — cell_id only
    # present when the root has a single row in the soma table.
    soma_lookup: dict[int, dict[str, Any]] | None = None

    # First pass: read both caches synchronously. Decide which need a synchronous
    # cold fetch (no cache or hard-expired) vs an async revalidation (stale).
    cold_jobs: list[tuple[str, Any]] = []  # ("cell_type"|"num_soma", payload)

    if cell_type_table:
        ct_cache = service.cache_for("cell_type", live)
        ct_key = (ds, mat_version, cell_type_table)
        entry = ct_cache.get(ct_key)
        if entry is None:
            cold_jobs.append(("cell_type", (ct_cache, ct_key)))
        else:
            ct_lookup, freshness = entry
            if freshness == "stale":
                has_stale = True

                def _refresh_ct(_cache=ct_cache, _key=ct_key,
                                _table=cell_type_table, _mv=mat_version):
                    fresh = _fetch_cell_type_table(client_factory(), _table, _mv)
                    _cache.set(_key, fresh)

                service.executor.submit(("cell_type", ct_key), _refresh_ct)

    if soma_table:
        soma_cache = service.cache_for("num_soma", live)
        soma_key = (ds, mat_version, soma_table)
        entry = soma_cache.get(soma_key)
        if entry is None:
            cold_jobs.append(("num_soma", (soma_cache, soma_key)))
        else:
            soma_lookup, freshness = entry
            if freshness == "stale":
                has_stale = True

                def _refresh_soma(_cache=soma_cache, _key=soma_key,
                                  _table=soma_table, _mv=mat_version,
                                  _col=soma_root_id_column, _ds=ds):
                    fresh = _fetch_num_soma_table(client_factory(), _table, _mv,
                                                  soma_root_id_column=_col)
                    _cache.set(_key, fresh)
                    if not is_live(_mv):
                        _populate_cell_id_caches_from_soma(fresh, _ds, int(_mv))

                service.executor.submit(("num_soma", soma_key), _refresh_soma)

    # Generic per-table decorations. Each requested table fetches once, indexed
    # by root_id; columns merge onto partner records on the served-record loop
    # below. `table_lookups[table]` = {root_id: {col: value}} or None when cold.
    table_lookups: dict[str, dict[int, dict] | None] = {}
    for tbl in (decoration_tables or []):
        if not tbl or tbl == cell_type_table or tbl == soma_table:
            # Skip empty / dupes of the dedicated decoration paths.
            continue
        tcache = service.cache_for("table", live)
        tkey = (ds, mat_version, tbl)
        entry = tcache.get(tkey)
        if entry is None:
            cold_jobs.append(("table", (tcache, tkey, tbl)))
            table_lookups[tbl] = None  # populated by the cold-fetch loop below
        else:
            data, freshness = entry
            table_lookups[tbl] = data
            if freshness == "stale":
                has_stale = True

                def _refresh_table(_cache=tcache, _key=tkey,
                                   _table=tbl, _mv=mat_version):
                    fresh = _fetch_decoration_table(client_factory(), _table, _mv)
                    _cache.set(_key, fresh)

                service.executor.submit(("table", tkey), _refresh_table)

    # Parallelize cold fetches: they don't depend on each other, and the cell-type
    # table + soma table are usually the slowest two CAVE calls in a request.
    if cold_jobs:
        with ThreadPoolExecutor(max_workers=min(len(cold_jobs), 8)) as pool:
            futures: dict = {}
            for job in cold_jobs:
                kind = job[0]
                if kind == "cell_type":
                    cache, cache_key = job[1]
                    futures[pool.submit(_fetch_cell_type_table,
                                        client_factory(), cell_type_table, mat_version)] = (kind, cache, cache_key, None)
                elif kind == "num_soma":
                    cache, cache_key = job[1]
                    futures[pool.submit(_fetch_num_soma_table,
                                        client_factory(), soma_table, mat_version,
                                        soma_root_id_column)] = (kind, cache, cache_key, None)
                else:  # "table"
                    cache, cache_key, tbl = job[1]
                    futures[pool.submit(_fetch_decoration_table,
                                        client_factory(), tbl, mat_version)] = (kind, cache, cache_key, tbl)
            for fut, meta in futures.items():
                kind, cache, cache_key, tbl = meta
                result = fut.result()
                cache.set(cache_key, result)
                if kind == "cell_type":
                    ct_lookup = result
                elif kind == "num_soma":
                    soma_lookup = result
                    if not live:
                        _populate_cell_id_caches_from_soma(result, ds, int(mat_version))
                else:
                    table_lookups[tbl] = result

    served: dict[int, dict[str, Any]] = {}
    for rid in root_ids:
        rid = int(rid)
        rec: dict[str, Any] = {}
        if ct_lookup is not None:
            # The cell-type table contributes every annotation column flat
            # (no namespace prefix). It's by-convention the canonical source,
            # so its `cell_type` / `classification_system` / etc. land on the
            # partner record without ceremony.
            ct_rec = ct_lookup.get(rid) or {}
            for k, v in ct_rec.items():
                rec[k] = v
        if soma_lookup is not None:
            soma_rec = soma_lookup.get(rid) or {}
            rec["num_soma"] = int(soma_rec.get("num_soma", 0))
            if "cell_id" in soma_rec:
                rec["cell_id"] = soma_rec["cell_id"]
            # `pt_position` is forwarded so downstream (spatial features in
            # connectivity_bundle) can read it without re-fetching the soma
            # table. The bundle assembler strips it before serializing — it's
            # internal scaffolding, not a SPA-rendered column.
            if "pt_position" in soma_rec:
                rec["pt_position"] = soma_rec["pt_position"]
        # Generic per-table columns get a `<table>.<col>` namespace so two
        # tables that both expose `cell_type` (or anything else) coexist
        # cleanly. The SPA renders the dot-prefix as a group header above
        # the column.
        for tbl, tbl_data in table_lookups.items():
            if tbl_data is None:
                continue
            extra = tbl_data.get(rid)
            if not extra:
                continue
            for k, v in extra.items():
                rec[f"{tbl}.{k}"] = v
        if rec:
            served[rid] = rec

    # Groups metadata: each entry describes a logical group of columns the
    # frontend can render under a shared header. Built-ins (`cell_type`,
    # `soma`) keep their flat keys; per-table decorations contribute
    # namespaced columns.
    groups: list[dict] = []
    if ct_lookup is not None:
        ct_cols: set[str] = set()
        for rec in ct_lookup.values():
            ct_cols.update(rec.keys())
        # `cell_type` first if present (the canonical column drives the bar
        # plot), then any other annotation columns the table exposes.
        ordered_ct_cols = (
            (["cell_type"] if "cell_type" in ct_cols else [])
            + sorted(c for c in ct_cols if c != "cell_type")
        )
        if ordered_ct_cols:
            groups.append({
                "name": cell_type_table or "cell_type",
                "kind": "cell_type",
                "columns": ordered_ct_cols,
            })
    if soma_lookup is not None:
        soma_cols = ["num_soma"]
        # cell_id is sparse (only single-soma roots); include it in the group
        # if any served record has one so the column shows up in the table.
        if any("cell_id" in (rec or {}) for rec in served.values()):
            soma_cols.append("cell_id")
        groups.append({
            "name": soma_table or "soma",
            "kind": "soma",
            "columns": soma_cols,
        })
    for tbl, tbl_data in table_lookups.items():
        if not tbl_data:
            continue
        bare_cols: set[str] = set()
        for rec in tbl_data.values():
            bare_cols.update(rec.keys())
        if bare_cols:
            groups.append({
                "name": tbl,
                "kind": "table",
                "columns": [f"{tbl}.{c}" for c in sorted(bare_cols)],
            })

    revalidation: dict[str, Any] | None = None
    if has_stale and served:
        ticket_id = service.mint_ticket(
            ds=ds, mat_version=mat_version,
            cell_type_table=cell_type_table, soma_table=soma_table,
            served={str(k): v for k, v in served.items()},
        )
        revalidation = {
            "ticket_id": ticket_id,
            "pending_root_ids": list(served.keys()),
            "poll_url": f"/api/v1/decorations/poll?ticket={ticket_id}",
        }
    return served, groups, revalidation
