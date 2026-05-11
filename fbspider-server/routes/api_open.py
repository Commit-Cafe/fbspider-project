"""
开放 API — 通过 API Key 访问设备控制功能
Header: X-API-Key: fbk_xxxxx

所有端点复用 api_device_control 的核心逻辑，
但认证方式改为 API Key（或 admin token）。
"""
from flask import Blueprint, jsonify, request

from auth import api_key_required
from ws_relay import (
    list_devices, pick_device, send_command, get_task_result,
    find_device_by_username, find_device_by_account, resolve_device,
)

bp = Blueprint("api_open", __name__, url_prefix="/api/open")

SCOPE = "device-control"


def _resolve_device(body):
    return resolve_device(body, require_login=False)


def _send(device_id, action, params):
    try:
        task_id, err = send_command(device_id, action, params)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    if err:
        return jsonify({"success": False, "message": err}), 500
    return jsonify({"success": True, "task_id": task_id, "device": device_id})


# ============ 端点 ============

@bp.route("/devices", methods=["GET"])
@api_key_required(scope=SCOPE)
def devices():
    """列出所有在线设备"""
    return jsonify({"success": True, "data": list_devices()})


@bp.route("/send", methods=["POST"])
@api_key_required(scope=SCOPE)
def send():
    """通用指令
    Body: { "device?": "", "account_id?": "", "username?": "", "action": "...", "params": {...} }
    """
    body = request.get_json(silent=True) or {}
    action = body.get("action")
    params = body.get("params", {})
    if not action:
        return jsonify({"success": False, "message": "缺少 action"}), 400

    did, username, err = _resolve_device(body)
    if err:
        return jsonify({"success": False, "message": err, "matched_user": username}), 404
    return _send(did, action, params)


@bp.route("/navigate", methods=["POST"])
@api_key_required(scope=SCOPE)
def navigate():
    """导航到 URL"""
    body = request.get_json(silent=True) or {}
    did, username, err = _resolve_device(body)
    if err:
        return jsonify({"success": False, "message": err, "matched_user": username}), 404
    return _send(did, "navigate", {
        "url": body.get("url", ""),
        "new_tab": body.get("new_tab", True),
    })


@bp.route("/click", methods=["POST"])
@api_key_required(scope=SCOPE)
def click():
    """点击元素"""
    body = request.get_json(silent=True) or {}
    did, username, err = _resolve_device(body)
    if err:
        return jsonify({"success": False, "message": err, "matched_user": username}), 404
    params = {"selector": body.get("selector", "")}
    if body.get("url"):
        params["url"] = body["url"]
    return _send(did, "click", params)


@bp.route("/update-url", methods=["POST"])
@api_key_required(scope=SCOPE)
def update_url():
    """修改标签页 URL"""
    body = request.get_json(silent=True) or {}
    did, username, err = _resolve_device(body)
    if err:
        return jsonify({"success": False, "message": err, "matched_user": username}), 404
    params = {}
    for key in ("url", "new_url", "set_params", "remove_params", "replace"):
        if body.get(key):
            params[key] = body[key]
    return _send(did, "update_url", params)


@bp.route("/toggle", methods=["POST"])
@api_key_required(scope=SCOPE)
def toggle():
    """开关广告"""
    body = request.get_json(silent=True) or {}
    for field in ("ad_type", "ad_id", "account_id"):
        if field not in body:
            return jsonify({"success": False, "message": f"缺少 {field}"}), 400

    did, username, err = _resolve_device(body)
    if err:
        return jsonify({"success": False, "message": err, "matched_user": username}), 404
    return _send(did, "toggle_ad", {
        "ad_type": body["ad_type"],
        "ad_id": body["ad_id"],
        "account_id": body["account_id"],
        "enable": body.get("enable", False),
    })


@bp.route("/budget", methods=["POST"])
@api_key_required(scope=SCOPE)
def budget():
    """修改预算"""
    body = request.get_json(silent=True) or {}
    for field in ("ad_type", "ad_id", "account_id", "budget"):
        if field not in body:
            return jsonify({"success": False, "message": f"缺少 {field}"}), 400

    did, username, err = _resolve_device(body)
    if err:
        return jsonify({"success": False, "message": err, "matched_user": username}), 404
    return _send(did, "set_budget", {
        "ad_type": body["ad_type"],
        "ad_id": body["ad_id"],
        "account_id": body["account_id"],
        "budget": body["budget"],
    })


@bp.route("/result/<task_id>", methods=["GET"])
@api_key_required(scope=SCOPE)
def result(task_id):
    """查询任务结果"""
    r = get_task_result(task_id)
    if r is None:
        return jsonify({"success": True, "status": "pending"})
    return jsonify({"success": True, "status": "done", "result": r})
