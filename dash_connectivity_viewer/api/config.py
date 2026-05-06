import os

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix


_DEFAULTS = {
    "GLOBAL_SERVER_ADDRESS": "https://global.daf-apis.com",
    "DEFAULT_DATASTACK": None,
    # Allowlist of datastacks the SPA's picker offers. The list is also the
    # only thing the listing endpoint returns — endpoints themselves don't
    # gate on it (CAVE auth is the security boundary). Override per-deployment
    # via `DCV_DATASTACKS_ALLOWED` (comma-separated). Default ships the three
    # development datastacks: minnie65_public + minnie65_phase3_v1 (cortex,
    # shared aligned_volume `minnie65_phase3`) and brain_and_nerve_cord
    # (different aligned_volume, no spatial config — exercises the
    # "no transform" branches of the bundle assembler and SPA).
    "DATASTACKS_ALLOWED": [
        "minnie65_public",
        "minnie65_phase3_v1",
        "brain_and_nerve_cord",
    ],
    "CORS_ORIGINS": ["http://localhost:5173"],
    "SPELUNKER_URL": "https://spelunker.cave-explorer.org",
    "CACHE_QUERY_TTL_SECONDS": 15 * 60,
    "CACHE_TABLE_META_TTL_SECONDS": 60 * 60,
    # Frozen materializations are immutable, so this is effectively forever.
    # The 7-day ceiling exists only because cachetools.TTLCache requires a
    # finite TTL; it also bounds memory if a config or proxy quirk makes us
    # accumulate keys across many datastacks.
    "CACHE_UNIQUE_VALUES_TTL_SECONDS": 7 * 24 * 60 * 60,
    "CACHE_INFO_TTL_SECONDS": 24 * 60 * 60,
    # Spatial-features payload (per-partner soma_depth, soma_x/z,
    # radial_dist, median_dist, median_syn_depth) is invariant for a
    # frozen materialization. 30 minutes covers a typical exploration
    # session; live mode short-circuits the cache by including
    # mat_version="live" in the key (always fresh).
    "CACHE_SPATIAL_FEATURES_TTL_SECONDS": 30 * 60,
    # Soma summary (num_soma + soma_pt_position) for the queried cell.
    # Same invariance argument as spatial features.
    "CACHE_SOMA_SUMMARY_TTL_SECONDS": 30 * 60,
    "CACHE_DECORATION_SOFT_TTL_SECONDS": 4 * 60 * 60,
    "CACHE_DECORATION_HARD_TTL_SECONDS": 24 * 60 * 60,
    "CACHE_DECORATION_LIVE_SOFT_TTL_SECONDS": 5 * 60,
    "CACHE_DECORATION_LIVE_HARD_TTL_SECONDS": 30 * 60,
    "DECORATION_REVALIDATION_WORKERS": 4,
    "LINK_TEMPLATE_DIR": None,
    "PLOT_TEMPLATE_DIR": None,
    "DATASTACK_CONFIG_DIR": None,
    "ALIGNED_VOLUME_CONFIG_DIR": None,
}


def configure_app(app: Flask, overrides: dict | None = None) -> None:
    app.config.update(_DEFAULTS)
    for key in _DEFAULTS:
        env_value = os.environ.get(f"DCV_{key}")
        if env_value is not None:
            app.config[key] = _coerce(_DEFAULTS[key], env_value)
    # middle-auth-client and CAVEclient ship with their own `GLOBAL_SERVER`
    # env var (host only, e.g. `global.daf-apis.com`) used for the initial
    # global / datastack-discovery API. Our config historically called the
    # same value `GLOBAL_SERVER_ADDRESS` (with scheme). When operators set
    # `GLOBAL_SERVER` for middle-auth and don't separately set
    # `DCV_GLOBAL_SERVER_ADDRESS`, derive ours from it so the deployment
    # has a single source of truth.
    if (
        os.environ.get("DCV_GLOBAL_SERVER_ADDRESS") is None
        and os.environ.get("GLOBAL_SERVER")
    ):
        bare = os.environ["GLOBAL_SERVER"].strip()
        # Allow operators to set either `host` or `https://host`; normalize
        # to a full URL.
        if not bare.startswith(("http://", "https://")):
            bare = f"https://{bare}"
        app.config["GLOBAL_SERVER_ADDRESS"] = bare.rstrip("/")
    if overrides:
        app.config.update(overrides)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)


def _coerce(default, raw: str):
    if isinstance(default, bool):
        return raw.lower() in {"1", "true", "yes", "on"}
    if isinstance(default, int):
        return int(raw)
    if isinstance(default, list):
        return [item.strip() for item in raw.split(",") if item.strip()]
    return raw
