from flask import Blueprint, current_app, jsonify, request

from ..auth import auth_required, current_token, is_dev_bypass
from ..cave import request_client
from ..errors import ApiError
from ..services.datastack_config import check_live_allowed, load_datastack_config
from ..services.neuron import NeuronQuery, connectivity_bundle

bp = Blueprint("connectivity", __name__, url_prefix="/datastacks")


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


@bp.route("/<ds>/neuron/<int:root_id>/connectivity", methods=["POST"])
@auth_required
def connectivity(ds: str, root_id: int):
    body = request.get_json(silent=True) or {}
    include = body.get("include")
    cell_type_table = body.get("cell_type_table")
    decoration_tables = body.get("decoration_tables") or []
    mat_version = request.args.get("mat_version") or None

    try:
        check_live_allowed(ds, mat_version)
    except ValueError as exc:
        raise ApiError(422, "live_mode_disallowed", str(exc)) from exc

    cfg = load_datastack_config(ds)
    rules = body.get("synapse_aggregation_rules") or cfg.aggregation_rules_for_neuron_query()
    synapse_columns = body.get("synapse_columns", cfg.merged_synapse_columns())

    # Capture the user's auth token + dev_bypass flag in the request thread;
    # the background revalidator runs after the request context is gone and
    # needs both available via closure to dispatch the same hardened client
    # builder (no silent cave-secret fallback in production).
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

    try:
        client = client_factory()
    except ValueError as exc:
        raise ApiError(401, "no_auth_token", str(exc)) from exc
    nq = NeuronQuery(
        client,
        root_id=root_id,
        datastack=ds,
        mat_version=mat_version,
        synapse_aggregation_rules=rules,
        synapse_columns=synapse_columns,
        synapse_position_prefix=cfg.synapse_position_prefix,
    )
    try:
        payload = connectivity_bundle(
            nq,
            include=include,
            cell_type_table=cell_type_table,
            decoration_tables=decoration_tables,
            client_factory=client_factory,
            spatial_transform_name=cfg.spatial.transform,
        )
    except ValueError as exc:
        raise ApiError(409, "neuron_query_failed", str(exc)) from exc
    except Exception as exc:
        raise ApiError(502, "cave_upstream", str(exc)) from exc
    return jsonify(payload)
