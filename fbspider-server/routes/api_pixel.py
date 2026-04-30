from flask import Blueprint, jsonify, request

from auth import api_key_required
from ws_relay import (
    list_devices, pick_device, send_command, get_task_result,
    find_device_by_username, find_device_by_account,
)

bp = Blueprint("api_pixel", __name__, url_prefix="/api/open/pixel")

SCOPE = "device-control"


def _resolve_device(body):
    if body.get("device"):
        did = pick_device(body["device"])
        if not did:
            return None, None, f"没有匹配 {body['device']} 的在线设备"
        dev_info = list_devices().get(did, {})
        return did, dev_info.get("username"), None

    if body.get("account_id"):
        did, username, err = find_device_by_account(body["account_id"])
        if err:
            return None, username, err
        return did, username, None

    if body.get("username"):
        did = find_device_by_username(body["username"])
        if not did:
            return None, body["username"], f"用户 {body['username']} 没有在线设备"
        return did, body["username"], None

    did = pick_device()
    if not did:
        return None, None, "没有在线设备"
    dev_info = list_devices().get(did, {})
    return did, dev_info.get("username"), None


def _send(device_id, action, params):
    try:
        task_id, err = send_command(device_id, action, params)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    if err:
        return jsonify({"success": False, "message": err}), 500
    return jsonify({"success": True, "task_id": task_id, "device": device_id})


@bp.route("/authorize", methods=["POST"])
@api_key_required(scope=SCOPE)
def authorize():
    body = request.get_json(silent=True) or {}

    pixel_id = body.get("pixel_id")
    target_account_id = body.get("target_account_id")

    if not pixel_id:
        return jsonify({"success": False, "message": "缺少 pixel_id"}), 400
    if not target_account_id:
        return jsonify({"success": False, "message": "缺少 target_account_id"}), 400

    did, username, err = _resolve_device(body)
    if err:
        return jsonify({"success": False, "message": err, "matched_user": username}), 404

    return _send(did, "authorize_pixel", {
        "pixel_id": str(pixel_id),
        "target_account_id": str(target_account_id),
    })


@bp.route("/batch_authorize", methods=["POST"])
@api_key_required(scope=SCOPE)
def batch_authorize():
    """批量像素授权
    Body: {
        "tasks": [
            {"pixel_id": "xxx", "target_account_id": "yyy"},
            ...
        ],
        "username?": "...",
        "device?": "...",
        "interval?": 2       // 每条任务间隔秒数，默认 2
    }
    """
    import time
    body = request.get_json(silent=True) or {}

    tasks = body.get("tasks")
    if not tasks or not isinstance(tasks, list):
        return jsonify({"success": False, "message": "缺少 tasks 列表"}), 400

    interval = max(1, min(body.get("interval", 2), 10))

    did, username, err = _resolve_device(body)
    if err:
        return jsonify({"success": False, "message": err, "matched_user": username}), 404

    results = []
    for i, task in enumerate(tasks):
        pixel_id = str(task.get("pixel_id", ""))
        target_account_id = str(task.get("target_account_id", ""))

        if not pixel_id or not target_account_id:
            results.append({
                "index": i,
                "pixel_id": pixel_id,
                "target_account_id": target_account_id,
                "success": False,
                "message": "缺少 pixel_id 或 target_account_id",
            })
            continue

        try:
            task_id, cmd_err = send_command(did, "authorize_pixel", {
                "pixel_id": pixel_id,
                "target_account_id": target_account_id,
            })
        except Exception as e:
            results.append({
                "index": i,
                "pixel_id": pixel_id,
                "target_account_id": target_account_id,
                "success": False,
                "message": str(e),
            })
            continue

        if cmd_err:
            results.append({
                "index": i,
                "pixel_id": pixel_id,
                "target_account_id": target_account_id,
                "success": False,
                "message": cmd_err,
            })
            continue

        # 轮询等待结果
        max_wait = 30
        waited = 0
        task_result = None
        while waited < max_wait:
            time.sleep(2)
            waited += 2
            task_result = get_task_result(task_id)
            if task_result is not None:
                break

        if task_result is None:
            results.append({
                "index": i,
                "pixel_id": pixel_id,
                "target_account_id": target_account_id,
                "task_id": task_id,
                "success": False,
                "message": f"任务超时 ({max_wait}s)",
            })
        else:
            results.append({
                "index": i,
                "pixel_id": pixel_id,
                "target_account_id": target_account_id,
                "task_id": task_id,
                "success": task_result.get("status") == "ok",
                "authorized": task_result.get("authorized", False),
                "message": task_result.get("message", ""),
            })

        # 任务间间隔，避免被 Facebook 限流
        if i < len(tasks) - 1:
            time.sleep(interval)

    success_count = sum(1 for r in results if r.get("success"))
    return jsonify({
        "success": True,
        "total": len(tasks),
        "success_count": success_count,
        "fail_count": len(tasks) - success_count,
        "results": results,
    })


@bp.route("/result/<task_id>", methods=["GET"])
@api_key_required(scope=SCOPE)
def result(task_id):
    r = get_task_result(task_id)
    if r is None:
        return jsonify({"success": True, "status": "pending"})
    return jsonify({"success": True, "status": "done", "result": r})


@bp.route("/devices", methods=["GET"])
@api_key_required(scope=SCOPE)
def devices():
    return jsonify({"success": True, "data": list_devices()})
