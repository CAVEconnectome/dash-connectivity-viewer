from flask import Blueprint, current_app, jsonify, request

from ..auth import auth_required, current_token, is_dev_bypass
from ..cave import request_client
from ..errors import ApiError
from ..services.datastack_config import check_live_allowed, load_datastack_config
from ..services.links import load_templates, resolve_link
from ..services.neuron import NeuronQuery

bp = Blueprint("links", __name__, url_prefix="/datastacks")


@bp.route("/<ds>/links", methods=["POST"])
@auth_required
def make_link(ds: str):
    body = request.get_json(silent=True) or {}
    template_name = body.get("template")
    if not template_name:
        raise ApiError(422, "missing_template", "request body must include 'template'")
    query = body.get("query") or {}
    root_id = query.get("root_id")
    if root_id is None:
        raise ApiError(422, "missing_root_id", "query.root_id is required")
    selected_partner_ids = query.get("selected_partner_ids")
    mat_version = request.args.get("mat_version") or None

    try:
        check_live_allowed(ds, mat_version)
    except ValueError as exc:
        raise ApiError(422, "live_mode_disallowed", str(exc)) from exc

    templates = load_templates()
    template = templates.get(template_name)
    if template is None:
        raise ApiError(404, "template_not_found",
                       f"No link template named {template_name!r}",
                       hint=f"available: {sorted(templates.keys())}")

    # Same hardened auth dispatch as /connectivity. No silent cave-secret fallback.
    try:
        client = request_client(
            datastack_name=ds,
            server_address=current_app.config["GLOBAL_SERVER_ADDRESS"],
            auth_token=current_token(),
            dev_bypass=is_dev_bypass(),
            materialize_version=mat_version,
        )
    except ValueError as exc:
        raise ApiError(401, "no_auth_token", str(exc)) from exc

    cfg = load_datastack_config(ds)
    nq = NeuronQuery(
        client,
        root_id=int(root_id),
        datastack=ds,
        mat_version=mat_version,
        synapse_columns=cfg.merged_synapse_columns(),
        synapse_position_prefix=cfg.synapse_position_prefix,
    )
    try:
        result = resolve_link(
            template=template,
            nq=nq,
            client=client,
            selected_partner_ids=selected_partner_ids,
            spelunker_url=current_app.config["SPELUNKER_URL"],
        )
    except Exception as exc:
        raise ApiError(502, "link_render_failed",
                       f"Failed to render link: {type(exc).__name__}: {exc}") from exc
    return jsonify(result)
