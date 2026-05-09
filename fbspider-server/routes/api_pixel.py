from flask import Blueprint, jsonify, request

from auth import api_key_required
from ws_relay import (
    list_devices, pick_device, send_command, get_task_result,
    find_device_by_username, find_device_by_account,
)

bp = Blueprint("api_pixel", __name__, url_prefix="/api/open/pixel")

SCOPE = "device-control"


def _check_device_logged_in(did):
    """检查设备是否已登录，返回 (username, error_msg)"""
    dev_info = list_devices().get(did, {})
    username = dev_info.get("username")
    if not username:
        return None, "所有在线设备均未登录 Facebook，请先在浏览器中登录 Facebook 并刷新插件页面"
    return username, None


def _resolve_device(body):
    if body.get("device"):
        did = pick_device(body["device"])
        if not did:
            return None, None, f"没有匹配 {body['device']} 的在线设备"
        username, err = _check_device_logged_in(did)
        if err:
            return None, None, err
        return did, username, None

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
    username, err = _check_device_logged_in(did)
    if err:
        return None, None, err
    return did, username, None


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

    params = {
        "pixel_id": str(pixel_id),
        "target_account_id": str(target_account_id),
    }
    if body.get("business_id"):
        params["business_id"] = str(body["business_id"])

    return _send(did, "authorize_pixel", params)


@bp.route("/batch_authorize", methods=["POST"])
@api_key_required(scope=SCOPE)
def batch_authorize():
    """批量像素授权
    Body: {
        "tasks": [
            {"pixel_id": "xxx", "target_account_id": "yyy", "business_id": "zzz"},
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

        cmd_params = {
            "pixel_id": pixel_id,
            "target_account_id": target_account_id,
        }
        if task.get("business_id"):
            cmd_params["business_id"] = str(task["business_id"])

        try:
            task_id, cmd_err = send_command(did, "authorize_pixel", cmd_params)
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


# ============ 像素分享给广告账户 ============


@bp.route("/share_to_ad_account", methods=["POST"])
@api_key_required(scope=SCOPE)
def share_to_ad_account():
    """像素分享给广告账户
    Body: {
        "pixel_id": "xxx",
        "target_account_ids": ["yyy", "zzz"],   // 广告账户 ID 列表（支持批量）
        "business_id?": "bbb",
        "username?": "...",
        "device?": "..."
    }
    也兼容单个: "target_account_id": "yyy"
    """
    body = request.get_json(silent=True) or {}

    pixel_id = body.get("pixel_id")
    if not pixel_id:
        return jsonify({"success": False, "message": "缺少 pixel_id"}), 400

    # 支持数组或单个
    target_account_ids = body.get("target_account_ids")
    target_account_id = body.get("target_account_id")
    if not target_account_ids and not target_account_id:
        return jsonify({"success": False, "message": "缺少 target_account_ids 或 target_account_id"}), 400

    did, username, err = _resolve_device(body)
    if err:
        return jsonify({"success": False, "message": err, "matched_user": username}), 404

    params = {
        "pixel_id": str(pixel_id),
    }
    if target_account_ids:
        params["target_account_ids"] = [str(a) for a in target_account_ids]
    else:
        params["target_account_id"] = str(target_account_id)

    if body.get("business_id"):
        params["business_id"] = str(body["business_id"])
    if body.get("pixel_name"):
        params["pixel_name"] = str(body["pixel_name"])
    if body.get("pixel_asset_id"):
        params["pixel_asset_id"] = str(body["pixel_asset_id"])

    return _send(did, "share_pixel_to_ad_account", params)


@bp.route("/batch_share_to_ad_account", methods=["POST"])
@api_key_required(scope=SCOPE)
def batch_share_to_ad_account():
    """批量像素分享给广告账户
    Body: {
        "tasks": [
            {"pixel_id": "xxx", "target_account_ids": ["yyy", "zzz"], "business_id": "bbb"},
            ...
        ],
        "username?": "...",
        "device?": "...",
        "interval?": 2
    }
    也兼容单个: "target_account_id": "yyy"
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
        if not pixel_id:
            results.append({
                "index": i, "pixel_id": pixel_id,
                "success": False, "message": "缺少 pixel_id",
            })
            continue

        cmd_params = {"pixel_id": pixel_id}

        target_ids = task.get("target_account_ids")
        target_id = task.get("target_account_id")
        if target_ids:
            cmd_params["target_account_ids"] = [str(a) for a in target_ids]
        elif target_id:
            cmd_params["target_account_id"] = str(target_id)
        else:
            results.append({
                "index": i, "pixel_id": pixel_id,
                "success": False, "message": "缺少 target_account_ids 或 target_account_id",
            })
            continue

        if task.get("business_id"):
            cmd_params["business_id"] = str(task["business_id"])
        if task.get("pixel_name"):
            cmd_params["pixel_name"] = str(task["pixel_name"])
        if task.get("pixel_asset_id"):
            cmd_params["pixel_asset_id"] = str(task["pixel_asset_id"])

        try:
            task_id, cmd_err = send_command(did, "share_pixel_to_ad_account", cmd_params)
        except Exception as e:
            results.append({
                "index": i, "pixel_id": pixel_id,
                "success": False, "message": str(e),
            })
            continue

        if cmd_err:
            results.append({
                "index": i, "pixel_id": pixel_id,
                "success": False, "message": cmd_err,
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
                "index": i, "pixel_id": pixel_id,
                "task_id": task_id,
                "success": False, "message": f"任务超时 ({max_wait}s)",
            })
        else:
            results.append({
                "index": i, "pixel_id": pixel_id,
                "task_id": task_id,
                "success": task_result.get("status") == "ok",
                "authorized": task_result.get("authorized", False),
                "message": task_result.get("message", ""),
            })

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
