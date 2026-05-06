import os
from pathlib import Path

from flask import Flask, send_from_directory
from flask_cors import CORS

from .auth import auth_required
from .config import configure_app
from .errors import register_error_handlers
from .endpoints import api_bp
from .json_provider import NumpyJSONProvider
from .services.decoration import init_decoration_service
from .services.request_state import init_request_state
from .services.timing import init_timing


def create_app(config_overrides: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.json = NumpyJSONProvider(app)
    configure_app(app, overrides=config_overrides)
    CORS(
        app,
        resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
        supports_credentials=True,
    )
    register_error_handlers(app)
    init_decoration_service(app)
    init_timing(app)
    init_request_state(app)
    app.register_blueprint(api_bp, url_prefix="/api/v1")
    _register_spa(app)
    return app


def _register_spa(app: Flask) -> None:
    """Serve the built React SPA for non-API routes when the build output
    is on disk.

    The Vite build produces `frontend/dist/` with `index.html` + an
    `assets/` subtree. In production (Docker) we copy that into the
    image and Flask serves it directly — same-origin with the API,
    which keeps the middle-auth cookie flow simple. In dev nobody has
    `frontend/dist/`, so this is a no-op and Vite's dev server (port
    5173, proxying `/api/*` to Flask on 5001) handles the SPA.

    Path resolution order: `DCV_SPA_DIR` env var → `frontend/dist`
    relative to CWD. The latter matches the dev repo layout when a
    developer runs `npm run build` for any reason.

    Routing:
      - `/<path>` returns the file at `frontend/dist/<path>` if it
        exists (covers `assets/*`, `vite.svg`, etc.).
      - Otherwise returns `index.html` so React Router can handle the
        client-side route (`/neuron/...`, `/table/...`, etc.).
      - `/api/*` is unaffected — Flask's URL matcher prefers the more
        specific blueprint route.

    Auth model — pattern borrowed from CAVEconnectome/Tourguide
    (`flask_app/api.py`):
      - SPA shell (`index.html`) is gated behind `@auth_required`. A
        user landing on a shared URL like `/neuron/864...` first hits
        middle-auth's redirect-to-login, signs in, and is bounced back
        to the same URL with a `middle_auth_token=...` query param.
        middle-auth-client cashes that into a cookie, redirects to the
        clean URL, and the SPA loads with the cookie set. Subsequent
        XHR calls to `/api/v1/...` carry the cookie automatically
        (same-origin).
      - Static assets (JS/CSS/icons referenced from index.html) are
        NOT auth-gated. Auth providers can't redirect-back through XHR
        asset loads — the redirect-and-callback flow only makes sense
        for top-level navigations. Asset requests carry the same cookie
        the original document carried, so they're effectively gated by
        the document's auth even without a per-request decorator.
      - Dev mode: `DCV_DEV_AUTH_BYPASS=1` makes `auth_required` a
        no-op (see `auth.py`), so local testing doesn't need a CAVE
        token in cookies.
    """
    spa_dir_str = os.environ.get("DCV_SPA_DIR") or "frontend/dist"
    spa_dir = Path(spa_dir_str).resolve()
    if not (spa_dir / "index.html").is_file():
        return  # dev mode — Vite serves the SPA

    # Auth-gated shell handler. Defined separately so the decorator only
    # wraps the index.html branch — assets stay public.
    @auth_required
    def _serve_spa_index():
        resp = send_from_directory(spa_dir, "index.html")
        # `index.html` references hashed asset filenames; the browser
        # MUST re-validate it on every load so a deploy that changes
        # those hashes is picked up immediately. Without this header,
        # browsers cache index.html (sometimes for hours) and continue
        # serving stale JS even after a docker push. The hashed assets
        # themselves are immutable per build, so they get cached long
        # by their default headers.
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def _serve_spa(path: str):
        # Static assets get streamed straight off disk, no auth gate.
        # SPA history routes (no matching file) flow through the
        # auth-required shell handler so the user lands logged in.
        if path and (spa_dir / path).is_file():
            resp = send_from_directory(spa_dir, path)
            # Hashed bundles (e.g. assets/index-DzLY8k3E.js) are
            # immutable per build — content-addressed by Vite. Long
            # max-age is correct here; the index.html `no-cache` above
            # ensures clients pick up new hash references on each
            # navigation, so they fetch the new bundle URL anyway.
            if path.startswith("assets/"):
                resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return resp
        return _serve_spa_index()
