"""
API Key 管理接口（admin only）
"""
from flask import Blueprint, jsonify, request

from auth import api_admin_required, get_current_user
from models import create_api_key, list_api_keys, revoke_api_key, delete_api_key

bp = Blueprint("api_keys", __name__, url_prefix="/api/keys")


@bp.route("", methods=["GET"])
@api_admin_required
def list_keys():
    """列出所有 API Keys"""
    username = request.args.get("username", "").strip() or None
    return jsonify({"success": True, "data": list_api_keys(username)})


@bp.route("", methods=["POST"])
@api_admin_required
def create_key():
    """创建 API Key
    Body: { "username": "目标用户", "name": "描述", "expires_days?": 90, "scopes?": ["device-control"] }
    """
    body = request.get_json(silent=True) or {}
    username = body.get("username", "").strip()
    if not username:
        user = get_current_user()
        username = user["username"] if user else ""
    if not username:
        return jsonify({"success": False, "message": "缺少 username"}), 400

    name = body.get("name", "")
    expires_days = body.get("expires_days")
    if expires_days is not None:
        try:
            expires_days = int(expires_days)
        except (ValueError, TypeError):
            return jsonify({"success": False, "message": "expires_days 必须是整数"}), 400

    scopes = body.get("scopes") or ["device-control"]

    result = create_api_key(username, name=name, expires_days=expires_days, scopes=scopes)
    return jsonify({"success": True, "data": result})


@bp.route("/<key_id>/revoke", methods=["POST"])
@api_admin_required
def revoke_key(key_id):
    """撤销 API Key"""
    ok = revoke_api_key(key_id)
    if not ok:
        return jsonify({"success": False, "message": "未找到或已撤销"}), 404
    return jsonify({"success": True})


@bp.route("/<key_id>", methods=["DELETE"])
@api_admin_required
def delete_key(key_id):
    """删除 API Key"""
    ok = delete_api_key(key_id)
    if not ok:
        return jsonify({"success": False, "message": "未找到"}), 404
    return jsonify({"success": True})
