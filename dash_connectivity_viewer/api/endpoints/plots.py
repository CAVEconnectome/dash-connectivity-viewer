from flask import Blueprint, current_app, jsonify, request

from ..auth import auth_required, current_token, is_dev_bypass
from ..cave import request_client
from ..errors import ApiError
from ..services.datastack_config import check_live_allowed, load_datastack_config
from ..services.neuron import NeuronQuery
from ..services.plots import load_plot_specs, resolve_plot

bp = Blueprint("plots", __name__, url_prefix="/datastacks")


@bp.route("/<ds>/plots/<spec_name>", methods=["POST"])
@auth_required
def make_plot(ds: str, spec_name: str):
    body = request.get_json(silent=True) or {}
    root_id = body.get("root_id")
    if root_id is None:
        raise ApiError(422, "missing_root_id", "request body must include 'root_id'")
    cell_type_table = body.get("cell_type_table")
    decoration_tables = body.get("decoration_tables") or []
    column_override = body.get("column")
    # New multi-channel binding shape: {x?, y?, hue?, size?}. When present,
    # takes precedence over the legacy single `column` override; the resolver
    # auto-picks chart kind for `dynamic` specs based on which axes are bound.
    bindings = body.get("bindings") or None
    mat_version = request.args.get("mat_version") or None

    try:
        check_live_allowed(ds, mat_version)
    except ValueError as exc:
        raise ApiError(422, "live_mode_disallowed", str(exc)) from exc

    specs = load_plot_specs()
    spec = specs.get(spec_name)
    if spec is None:
        raise ApiError(404, "plot_not_found",
                       f"No plot spec named {spec_name!r}",
                       hint=f"available: {sorted(specs.keys())}")

    try:
        token = current_token()
        bypass = is_dev_bypass()
        server_address = current_app.config["GLOBAL_SERVER_ADDRESS"]

        def client_factory():
            return request_client(
                datastack_name=ds,
                server_address=server_address,
                auth_token=token,
                dev_bypass=bypass,
                materialize_version=mat_version,
            )

        client = client_factory()
    except ValueError as exc:
        raise ApiError(401, "no_auth_token", str(exc)) from exc

    cfg = load_datastack_config(ds)
    nq = NeuronQuery(
        client,
        root_id=int(root_id),
        datastack=ds,
        mat_version=mat_version,
        synapse_aggregation_rules=cfg.aggregation_rules_for_neuron_query(),
        synapse_columns=cfg.merged_synapse_columns(),
        synapse_position_prefix=cfg.synapse_position_prefix,
    )
    try:
        result = resolve_plot(
            spec=spec, nq=nq,
            cell_type_table=cell_type_table,
            decoration_tables=decoration_tables,
            column_override=column_override,
            bindings=bindings,
            client_factory=client_factory,
            spatial_transform_name=cfg.spatial.transform,
        )
    except ValueError as exc:
        raise ApiError(422, "plot_invalid_request", str(exc)) from exc
    except Exception as exc:
        raise ApiError(502, "plot_render_failed",
                       f"Failed to render plot: {type(exc).__name__}: {exc}") from exc
    return jsonify(result)
