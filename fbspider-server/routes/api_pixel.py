from flask import Blueprint, jsonify, request

from auth import api_key_required
from models import get_db
from ws_relay import (
    list_devices, pick_device, send_command, get_task_result,
    find_device_by_username, find_device_by_account, resolve_device,
)

bp = Blueprint("api_pixel", __name__, url_prefix="/api/open/pixel")

SCOPE = "device-control"


def _resolve_device(body):
    return resolve_device(body, require_login=True)


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
    pixel_name = body.get("pixel_name")
    target_account_id = body.get("target_account_id")

    if not pixel_id and not pixel_name:
        return jsonify({"success": False, "message": "缺少 pixel_id 或 pixel_name"}), 400
    if not target_account_id:
        return jsonify({"success": False, "message": "缺少 target_account_id"}), 400

    did, username, err = _resolve_device(body)
    if err:
        return jsonify({"success": False, "message": err, "matched_user": username}), 404

    params = {
        "pixel_id": str(pixel_id) if pixel_id else "",
        "target_account_id": str(target_account_id),
    }
    if body.get("business_id"):
        params["business_id"] = str(body["business_id"])
    if pixel_name:
        params["pixel_name"] = str(pixel_name)

    return _send(did, "authorize_pixel", params)


@bp.route("/batch_authorize", methods=["POST"])
@api_key_required(scope=SCOPE)
def batch_authorize():
    """批量像素授权
    Body: {
        "tasks": [
            {"pixel_id": "xxx", "target_account_id": "yyy", "business_id": "zzz"},
            {"pixel_name": "NYC01", "target_account_id": "yyy"},
            ...
        ],
        "username?": "...",
        "device?": "...",
        "interval?": 2
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
        pixel_name = str(task.get("pixel_name", ""))
        target_account_id = str(task.get("target_account_id", ""))

        if (not pixel_id and not pixel_name) or not target_account_id:
            results.append({
                "index": i,
                "pixel_id": pixel_id,
                "pixel_name": pixel_name,
                "target_account_id": target_account_id,
                "success": False,
                "message": "缺少 pixel_id/pixel_name 或 target_account_id",
            })
            continue

        cmd_params = {
            "pixel_id": pixel_id,
            "target_account_id": target_account_id,
        }
        if task.get("business_id"):
            cmd_params["business_id"] = str(task["business_id"])
        if pixel_name:
            cmd_params["pixel_name"] = pixel_name

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


# ============ BM 邀请人员 ============


@bp.route("/invite_to_bm", methods=["POST"])
@api_key_required(scope=SCOPE)
def invite_to_bm():
    """邀请人员进 BM
    Body: {
        "email": "xxx@outlook.com",
        "business_id": "1632044938058987",
        "role": "full_control",         // 可选: "full_control"(默认) / "employee"
        "username?": "...",
        "device?": "..."
    }
    """
    body = request.get_json(silent=True) or {}

    email = body.get("email")
    business_id = body.get("business_id")

    if not email:
        return jsonify({"success": False, "message": "缺少 email"}), 400
    if not business_id:
        return jsonify({"success": False, "message": "缺少 business_id"}), 400

    did, username, err = _resolve_device(body)
    if err:
        return jsonify({"success": False, "message": err, "matched_user": username}), 404

    params = {
        "email": str(email),
        "business_id": str(business_id),
    }
    if body.get("role"):
        params["role"] = str(body["role"])

    return _send(did, "invite_to_bm", params)


@bp.route("/batch_invite_to_bm", methods=["POST"])
@api_key_required(scope=SCOPE)
def batch_invite_to_bm():
    """批量邀请人员进 BM
    Body: {
        "tasks": [
            {"email": "a@outlook.com", "business_id": "1632044938058987", "role": "full_control"},
            {"email": "b@outlook.com", "business_id": "1632044938058987", "role": "employee"},
            ...
        ],
        "username?": "...",
        "device?": "...",
        "interval?": 2
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
        email = str(task.get("email", "")).strip()
        business_id = str(task.get("business_id", "")).strip()

        if not email or not business_id:
            results.append({
                "index": i,
                "email": email,
                "business_id": business_id,
                "success": False,
                "message": "缺少 email 或 business_id",
            })
            continue

        cmd_params = {
            "email": email,
            "business_id": business_id,
        }
        if task.get("role"):
            cmd_params["role"] = str(task["role"])

        try:
            task_id, cmd_err = send_command(did, "invite_to_bm", cmd_params)
        except Exception as e:
            results.append({
                "index": i,
                "email": email,
                "business_id": business_id,
                "success": False,
                "message": str(e),
            })
            continue

        if cmd_err:
            results.append({
                "index": i,
                "email": email,
                "business_id": business_id,
                "success": False,
                "message": cmd_err,
            })
            continue

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
                "email": email,
                "business_id": business_id,
                "task_id": task_id,
                "success": False,
                "message": f"任务超时 ({max_wait}s)",
            })
        else:
            results.append({
                "index": i,
                "email": email,
                "business_id": business_id,
                "task_id": task_id,
                "success": task_result.get("status") == "ok",
                "invited": task_result.get("invited", False),
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


@bp.route("/result/<task_id>", methods=["GET"])
@api_key_required(scope=SCOPE)
def result(task_id):
    r = get_task_result(task_id)
    if r is None:
        return jsonify({"success": True, "status": "pending"})
    return jsonify({"success": True, "status": "done", "result": r})


@bp.route("/search", methods=["GET"])
@api_key_required(scope=SCOPE)
def search_pixel():
    """从本地数据库搜索像素信息。

    Query params:
        name — 像素名称（模糊匹配）
        pixel_id — 像素 ID（精确匹配）
        username — 限定用户（可选）
    """
    name = request.args.get("name", "").strip()
    pixel_id = request.args.get("pixel_id", "").strip()
    username = request.args.get("username", "").strip()

    if not name and not pixel_id:
        return jsonify({"success": False, "message": "请提供 name 或 pixel_id 参数"}), 400

    db = get_db()
    query = {}
    if username:
        query["user_id"] = username
    if pixel_id:
        query["pixel_id"] = pixel_id
    if name:
        query["name"] = {"$regex": name, "$options": "i"}

    pixels = list(db.pixels.find(query, {"_id": 0, "raw_data": 0}).limit(20))

    results = []
    for p in pixels:
        results.append({
            "pixel_id": p.get("pixel_id", ""),
            "name": p.get("name", ""),
            "owner_bm_id": p.get("owner_bm_id", ""),
            "status": p.get("status", ""),
            "user_id": p.get("user_id", ""),
        })

    return jsonify({"success": True, "count": len(results), "data": results})


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
