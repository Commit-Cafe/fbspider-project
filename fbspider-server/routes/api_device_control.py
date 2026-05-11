"""
设备控制 API
管理员通过前端面板向 auto-click 插件下发指令
支持手动指定设备或按账户自动路由
"""
from flask import Blueprint, jsonify, request

from auth import api_admin_required
from ws_relay import (
    list_devices, send_command, get_task_result, resolve_device,
)

bp = Blueprint("api_device_control", __name__, url_prefix="/api/device-control")


def _resolve_device(body):
    """
    解析目标设备，返回 (device_id, username, error_msg, route_trace)
    """
    trace = []

    if body.get("device"):
        mode = "manual_device"
    elif body.get("account_id"):
        mode = "account_auto_route"
    elif body.get("username"):
        mode = "username_route"
    else:
        mode = "fallback_first_online"

    trace.append({"step": "device_input", "mode": mode})

    did, username, err = resolve_device(body)
    if err:
        trace.append({"step": "device_match_failed", "reason": err})
        return None, username, err, trace
    trace.append({"step": "device_selected", "device_id": did, "username": username})
    return did, username, None, trace


def _send(device_id, action, params, route_trace=None):
    """发送指令的通用包装"""
    try:
        task_id, err = send_command(device_id, action, params)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    if err:
        return jsonify({"success": False, "message": err}), 500
    return jsonify({
        "success": True,
        "task_id": task_id,
        "device": device_id,
        "route_trace": route_trace or [],
    })


@bp.route("/devices", methods=["GET"])
@api_admin_required
def get_devices():
    """列出所有在线设备及标签页和绑定用户"""
    return jsonify({"success": True, "data": list_devices()})


@bp.route("/send", methods=["POST"])
@api_admin_required
def send():
    """通用指令发送（支持自动路由）
    Body: { "device?": "", "account_id?": "", "username?": "", "action": "...", "params": {...} }
    """
    body = request.get_json(silent=True) or {}
    action = body.get("action")
    params = body.get("params", {})

    if not action:
        return jsonify({"success": False, "message": "缺少 action"}), 400

    did, username, err, route_trace = _resolve_device(body)
    if err:
        return jsonify({"success": False, "message": err, "matched_user": username, "route_trace": route_trace}), 404

    return _send(did, action, params, route_trace)


@bp.route("/navigate", methods=["POST"])
@api_admin_required
def navigate():
    """导航到 URL"""
    body = request.get_json(silent=True) or {}
    did, username, err, route_trace = _resolve_device(body)
    if err:
        return jsonify({"success": False, "message": err, "matched_user": username, "route_trace": route_trace}), 404

    return _send(did, "navigate", {
        "url": body.get("url", ""),
        "new_tab": body.get("new_tab", True),
    }, route_trace)


@bp.route("/click", methods=["POST"])
@api_admin_required
def click():
    """点击元素"""
    body = request.get_json(silent=True) or {}
    did, username, err, route_trace = _resolve_device(body)
    if err:
        return jsonify({"success": False, "message": err, "matched_user": username, "route_trace": route_trace}), 404

    params = {"selector": body.get("selector", "")}
    if body.get("url"):
        params["url"] = body["url"]
    if body.get("account_id"):
        params["account_id"] = body["account_id"]
    if body.get("ad_type"):
        params["ad_type"] = body["ad_type"]
    return _send(did, "click", params, route_trace)


@bp.route("/update-url", methods=["POST"])
@api_admin_required
def update_url():
    """修改标签页 URL
    Body: {
        "device?": "", "account_id?": "", "username?": "",
        "url": "匹配关键字",
        "new_url?": "完整新URL",
        "set_params?": {"key": "val"},
        "remove_params?": ["key"],
        "replace?": {"old": "xxx", "new": "yyy"}
    }
    """
    body = request.get_json(silent=True) or {}
    did, username, err, route_trace = _resolve_device(body)
    if err:
        return jsonify({"success": False, "message": err, "matched_user": username, "route_trace": route_trace}), 404

    params = {}
    if body.get("url"):
        params["url"] = body["url"]
    if body.get("new_url"):
        params["new_url"] = body["new_url"]
    if body.get("set_params"):
        params["set_params"] = body["set_params"]
    if body.get("remove_params"):
        params["remove_params"] = body["remove_params"]
    if body.get("replace"):
        params["replace"] = body["replace"]

    return _send(did, "update_url", params, route_trace)


@bp.route("/toggle", methods=["POST"])
@api_admin_required
def toggle():
    """开关广告（支持自动路由）
    Body: { "account_id": "xxx", "ad_type": "adsets", "ad_id": "xxx", "enable": true/false }
    account_id 同时用于自动路由和作为广告操作参数
    """
    body = request.get_json(silent=True) or {}

    for field in ("ad_type", "ad_id", "account_id"):
        if field not in body:
            return jsonify({"success": False, "message": f"缺少 {field}"}), 400

    did, username, err, route_trace = _resolve_device(body)
    if err:
        return jsonify({"success": False, "message": err, "matched_user": username, "route_trace": route_trace}), 404

    return _send(did, "toggle_ad", {
        "ad_type": body["ad_type"],
        "ad_id": body["ad_id"],
        "account_id": body["account_id"],
        "enable": body.get("enable", False),
    }, route_trace)


@bp.route("/budget", methods=["POST"])
@api_admin_required
def budget():
    """修改预算（支持自动路由）"""
    body = request.get_json(silent=True) or {}

    for field in ("ad_type", "ad_id", "account_id", "budget"):
        if field not in body:
            return jsonify({"success": False, "message": f"缺少 {field}"}), 400

    did, username, err, route_trace = _resolve_device(body)
    if err:
        return jsonify({"success": False, "message": err, "matched_user": username, "route_trace": route_trace}), 404

    return _send(did, "set_budget", {
        "ad_type": body["ad_type"],
        "ad_id": body["ad_id"],
        "account_id": body["account_id"],
        "budget": body["budget"],
    }, route_trace)


@bp.route("/result/<task_id>", methods=["GET"])
@api_admin_required
def result(task_id):
    """查询任务结果"""
    r = get_task_result(task_id)
    if r is None:
        return jsonify({"success": True, "status": "pending"})
    return jsonify({"success": True, "status": "done", "result": r})
