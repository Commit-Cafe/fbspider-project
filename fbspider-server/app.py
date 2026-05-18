import os
import io
import gzip
import json
import time
import uuid
from datetime import datetime, date
from flask import Flask, jsonify, request, g, send_from_directory
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from config import SECRET_KEY, CORS_ORIGINS
from models import init_db
from logger import logger
from scheduler import start_scheduler


class MongoJSONProvider(DefaultJSONProvider):
    """JSON provider that handles MongoDB types (datetime, ObjectId, etc.)."""
    @staticmethod
    def default(o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        # Handle bson ObjectId, Decimal128, etc.
        return str(o)

# React build output directory
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), 'frontend', 'dist')

app = Flask(__name__, static_folder=None)
app.json_provider_class = MongoJSONProvider
app.json = MongoJSONProvider(app)
app.secret_key = SECRET_KEY
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True
CORS(
    app,
    resources={r"/api/*": {"origins": CORS_ORIGINS.split(",")}},
    allow_headers=["Content-Type", "Authorization", "X-Auth-Token", "X-API-Key"],
    supports_credentials=True,
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
)

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["120 per minute"],
    storage_uri="memory://",
)

# Always init DB on startup (including gunicorn)
init_db()
start_scheduler()

# Register blueprints
from routes.api_receive import bp as receive_bp
from routes.api_serve import bp as serve_bp
from routes.api_commands import bp as commands_bp
from routes.auth import bp as auth_bp
from routes.api_device_control import bp as device_control_bp
from routes.api_keys import bp as api_keys_bp
from routes.api_open import bp as api_open_bp
from routes.api_ads import bp as ads_bp
from routes.api_upload import bp as upload_bp
from routes.api_pixel import bp as pixel_bp
from routes.api_nlp import bp as nlp_bp

app.register_blueprint(receive_bp)
app.register_blueprint(serve_bp)
app.register_blueprint(commands_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(device_control_bp)
app.register_blueprint(api_keys_bp)
app.register_blueprint(api_open_bp)
app.register_blueprint(ads_bp)
app.register_blueprint(upload_bp)
app.register_blueprint(pixel_bp)
app.register_blueprint(nlp_bp)


with app.app_context():
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "auth_api.api_login":
            view_func = app.view_functions[rule.endpoint]
            app.view_functions[rule.endpoint] = limiter.limit("5 per minute")(view_func)
            break

from ws_relay import start_ws_server
start_ws_server()


# --- Trace ID + Request Logging ---

@app.before_request
def inject_trace_id():
    g.trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
    g.start_time = time.time()


@app.after_request
def log_and_trace_response(response):
    duration_ms = (time.time() - g.start_time) * 1000 if hasattr(g, "start_time") else 0
    trace_id = getattr(g, "trace_id", "")
    user_id = getattr(g, "current_user", {}).get("username", "") if hasattr(g, "current_user") and isinstance(getattr(g, "current_user", None), dict) else ""
    response.headers["X-Trace-ID"] = trace_id

    if request.path.startswith("/api/") and not request.path.startswith("/api/health"):
        logger.info(
            "%s %s → %s (%.0fms)",
            request.method, request.path,
            response.status_code, duration_ms,
            extra={
                "trace_id": trace_id,
                "user_id": user_id,
                "extra_data": {
                    "method": request.method,
                    "path": request.path,
                    "status": response.status_code,
                    "duration_ms": round(duration_ms, 1),
                },
            },
        )
    return response


# --- Health Check ---

@app.route("/api/health")
def health():
    checks = {}
    overall = "ok"

    try:
        from models import get_db, reset_db_client
        db = get_db()
        db.command("ping")
        checks["mongo"] = "connected"
    except Exception as e:
        checks["mongo"] = f"error: {e}"
        overall = "degraded"
        try:
            reset_db_client()
            logger.warning("MongoDB 连接异常，已重置客户端，下次请求将自动重连")
        except Exception:
            pass

    from ws_relay import list_devices
    online = list_devices()
    checks["online_devices"] = len(online)
    checks["ws_port"] = 7671
    checks["device_details"] = {
        did: {"username": d.get("username"), "last_heartbeat": d.get("last_heartbeat")}
        for did, d in online.items()
    }

    code = 200 if overall == "ok" else 503
    return jsonify({"status": overall, "checks": checks}), code


# --- Serve React SPA via static routes + 404 fallback ---
# NO catch-all route — avoids any conflict with API blueprints.

@app.route('/')
def serve_index():
    return send_from_directory(FRONTEND_DIR, 'index.html')


@app.route('/assets/<path:filename>')
def serve_assets(filename):
    return send_from_directory(os.path.join(FRONTEND_DIR, 'assets'), filename)


@app.route('/fbhelper1.png')
def serve_logo():
    return send_from_directory(FRONTEND_DIR, 'fbhelper1.png')


# Keep old /static path working for extension content-main.js compatibility
@app.route('/static/<path:filename>')
def serve_legacy_static(filename):
    legacy_dir = os.path.join(os.path.dirname(__file__), 'static')
    return send_from_directory(legacy_dir, filename)


@app.after_request
def harden_api_response(response):
    # Tell proxies/VPNs: do NOT modify the response body.
    response.headers['Cache-Control'] = 'no-transform'

    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store, no-transform'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Auth-Token, X-API-Key'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        if request.headers.get('Access-Control-Request-Private-Network') == 'true':
            response.headers['Access-Control-Allow-Private-Network'] = 'true'
        if request.method == 'OPTIONS':
            response.headers['Content-Length'] = '0'
            response.status_code = 204

    # Server-side gzip: compress before sending so that Content-Length
    # matches the actual bytes on the wire.  VPN proxies see the response
    # is already compressed and leave it alone — fixing
    # ERR_CONTENT_LENGTH_MISMATCH caused by proxy re-compression.
    accept = request.headers.get('Accept-Encoding', '')
    if (
        'gzip' in accept
        and response.status_code < 300
        and not response.direct_passthrough
        and 'Content-Encoding' not in response.headers
    ):
        data = response.get_data()
        if len(data) > 256:                       # skip tiny responses
            buf = io.BytesIO()
            with gzip.GzipFile(fileobj=buf, mode='wb', compresslevel=1) as f:
                f.write(data)
            compressed = buf.getvalue()
            response.set_data(compressed)
            response.headers['Content-Encoding'] = 'gzip'
            response.headers['Content-Length'] = len(compressed)
            response.headers['Vary'] = 'Accept-Encoding'

    return response


@app.errorhandler(404)
def fallback(e):
    """For non-API 404s, serve index.html so React Router handles client-side routes."""
    if request.path.startswith('/api/'):
        return jsonify({"success": False, "message": "Not found"}), 404
    return send_from_directory(FRONTEND_DIR, 'index.html')


if __name__ == '__main__':
    init_db()
    logger.info("fbhelper Local Server starting...")
    logger.info("Dashboard: http://localhost:7150/dashboard")
    app.run(host='0.0.0.0', port=7150, debug=False, use_reloader=False)
