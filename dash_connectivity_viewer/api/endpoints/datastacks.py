from cachetools.keys import hashkey
from flask import Blueprint, current_app, jsonify, request

from ..auth import auth_required, current_token, is_dev_bypass
from ..caches import table_meta_cache
from ..cave import request_client
from ..errors import ApiError
from ..services.datastack_config import load_datastack_config
from ..services.keys import is_live

bp = Blueprint("datastacks", __name__, url_prefix="/datastacks")


def _client_for(ds: str) -> "object":
    mat_version = request.args.get("mat_version") or None
    try:
        return request_client(
            datastack_name=ds,
            server_address=current_app.config["GLOBAL_SERVER_ADDRESS"],
            auth_token=current_token(),
            dev_bypass=is_dev_bypass(),
            materialize_version=mat_version,
        )
    except ValueError as exc:
        raise ApiError(401, "no_auth_token", str(exc)) from exc


@bp.route("/<ds>/info")
@auth_required
def info(ds: str):
    client = _client_for(ds)
    info_dict = client.info.get_datastack_info()
    cfg = load_datastack_config(ds)
    return jsonify({
        "datastack": ds,
        "aligned_volume": info_dict.get("aligned_volume", {}),
        "viewer_site": info_dict.get("viewer_site"),
        "soma_table": info_dict.get("soma_table"),
        "synapse_table": info_dict.get("synapse_table"),
        "voxel_resolution": info_dict.get("viewer_resolution_x") and [
            info_dict.get("viewer_resolution_x"),
            info_dict.get("viewer_resolution_y"),
            info_dict.get("viewer_resolution_z"),
        ],
        "live_mode": cfg.live_mode,
    })


@bp.route("/<ds>/versions")
@auth_required
def versions(ds: str):
    client = _client_for(ds)
    metadata = client.materialize.get_versions_metadata()
    out = []
    for entry in metadata:
        out.append({
            "version": entry["version"],
            "expires_on": entry["expires_on"].isoformat() if entry.get("expires_on") else None,
            "valid": entry.get("valid", True),
        })
    out.sort(key=lambda v: v["version"], reverse=True)
    return jsonify({"versions": out})


@bp.route("/<ds>/tables")
@auth_required
def tables(ds: str):
    mv_raw = request.args.get("mat_version") or None
    live_mode = is_live(mv_raw)
    mv_for_key = None if live_mode else int(mv_raw)
    cache_key = hashkey("tables_and_views", ds, mv_for_key)
    if cache_key in table_meta_cache:
        return jsonify(table_meta_cache[cache_key])
    client = _client_for(ds)
    items = [{"name": name, "kind": "table"} for name in sorted(client.materialize.get_tables())]
    # Views are only available when a specific mat_version is set; live mode is tables-only.
    if not live_mode:
        try:
            view_names = client.materialize.get_views()
        except Exception:
            view_names = []
        items.extend({"name": name, "kind": "view"} for name in sorted(view_names))
    payload = {"tables": items, "mat_version": mv_for_key}
    table_meta_cache[cache_key] = payload
    return jsonify(payload)


@bp.route("/<ds>/tables/<table>/values")
@auth_required
def table_values(ds: str, table: str):
    client = _client_for(ds)
    cache_key = hashkey("values", ds, table, getattr(client.materialize, "version", None))
    if cache_key in table_meta_cache:
        return jsonify(table_meta_cache[cache_key])
    try:
        values = client.materialize.get_unique_string_values(table)
    except Exception as exc:
        raise ApiError(502, "cave_upstream", str(exc)) from exc
    payload = {"table": table, "values": values}
    table_meta_cache[cache_key] = payload
    return jsonify(payload)
