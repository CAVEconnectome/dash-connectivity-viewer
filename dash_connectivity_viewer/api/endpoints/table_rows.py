from flask import Blueprint, current_app, jsonify, request

from ..auth import auth_required, current_token, is_dev_bypass
from ..cave import request_client
from ..errors import ApiError
from ..services.datastack_config import check_live_allowed
from ..services.tables import TableQuery, parse_filters

bp = Blueprint("table_rows", __name__, url_prefix="/datastacks")


def _client_for(ds: str):
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


@bp.route("/<ds>/tables/<table>/rows", methods=["GET"])
@auth_required
def rows(ds: str, table: str):
    args = request.args.to_dict(flat=True)
    offset = int(args.get("offset", 0))
    limit = int(args.get("limit", 500))
    select_columns_raw = args.get("select_columns")
    select_columns = [c.strip() for c in select_columns_raw.split(",")] if select_columns_raw else None
    is_view_raw = args.get("is_view")
    is_view = is_view_raw.lower() in {"1", "true", "yes"} if is_view_raw is not None else None

    mat_version = args.get("mat_version") or None
    try:
        check_live_allowed(ds, mat_version)
    except ValueError as exc:
        raise ApiError(422, "live_mode_disallowed", str(exc)) from exc

    client = _client_for(ds)
    filters = parse_filters(args)

    try:
        tq = TableQuery(client, table, filters=filters, is_view=is_view, mat_version=mat_version)
    except ValueError as exc:
        raise ApiError(422, "invalid_query", str(exc)) from exc

    try:
        df = tq.rows(offset=offset, limit=limit, select_columns=select_columns)
    except KeyError as exc:
        raise ApiError(404, "table_not_found", f"No such table or view: {table}") from exc
    except Exception as exc:
        raise ApiError(502, "cave_upstream", str(exc)) from exc

    return jsonify({
        "datastack": ds,
        "table": table,
        "is_view": tq.is_view,
        "offset": offset,
        "limit": limit,
        "filters": filters,
        "row_count": int(df.shape[0]),
        "columns": list(df.columns),
        "rows": df.to_dict(orient="records"),
    })
