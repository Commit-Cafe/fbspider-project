import os
import io
import gzip
import json
from datetime import datetime, date
from flask import Flask, jsonify, request, send_from_directory
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS
from config import SECRET_KEY
from models import init_db
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
    resources={r"/api/*": {"origins": r".*"}},
    allow_headers=["Content-Type", "Authorization", "X-Auth-Token", "X-API-Key"],
    supports_credentials=True,
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
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

# 启动 WebSocket 中继服务（独立线程，端口 7671）
from ws_relay import start_ws_server
start_ws_server()


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
    print("fbhelper Local Server starting...")
    print("Dashboard: http://47.129.247.139:7150/dashboard")
    app.run(host='0.0.0.0', port=7150, debug=False, use_reloader=False)
