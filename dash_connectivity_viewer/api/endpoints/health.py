from flask import Blueprint, jsonify

from ... import __version__

bp = Blueprint("health", __name__)


@bp.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@bp.route("/version")
def version():
    return jsonify({"version": __version__})
