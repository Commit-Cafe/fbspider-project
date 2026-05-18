"""
api_nlp.py

自然语言命令 API — 接收自然语言文本，解析后自动路由到对应的操作。

支持的命令:
  分享像素到账户 (支持多任务、多目标)
  分享像素到BM   (支持多任务、多像素)
  分享BM         (邀请人员进BM，支持多任务)
"""
import time

from flask import Blueprint, jsonify, request

from auth import api_key_required
from command_parser import parse_command
from ws_relay import resolve_device, send_command, get_task_result

bp = Blueprint("api_nlp", __name__, url_prefix="/api/open/nlp")

SCOPE = "device-control"


@bp.route("/execute", methods=["POST"])
@api_key_required(scope=SCOPE)
def execute():
    """
    接收自然语言命令并执行。

    Body: {
        "command": "分享像素到BM\n1.将像素：NYC02\n分享到BM：32321312322323",
        "username?": "...",
        "device?": "...",
        "interval?": 2
    }
    """
    body = request.get_json(silent=True) or {}
    command_text = body.get("command", "").strip()

    if not command_text:
        return jsonify({"success": False, "message": "缺少 command 参数"}), 400

    parsed = parse_command(command_text)

    if parsed.get("error"):
        return jsonify({
            "success": False,
            "message": parsed["error"],
            "parsed": parsed,
        }), 400

    did, username, err = resolve_device(body, require_login=True)
    if err:
        return jsonify({"success": False, "message": err, "matched_user": username}), 404

    action = parsed["action"]
    interval = max(1, min(body.get("interval", 2), 10))

    if action == "share_pixel_to_account":
        return _handle_share_to_account(did, parsed, body, interval)
    elif action == "share_pixel_to_bm":
        return _handle_share_to_bm(did, parsed, body, interval)
    elif action == "share_bm":
        return _handle_share_bm(did, parsed, body, interval)
    else:
        return jsonify({"success": False, "message": "无法识别的命令"}), 400


def _execute_single(device_id, action, cmd_params, max_wait=30):
    """
    发送单条命令并等待结果。

    Returns:
        dict with success/message/etc.
    """
    try:
        task_id, cmd_err = send_command(device_id, action, cmd_params)
    except Exception as e:
        return {"success": False, "message": str(e)}

    if cmd_err:
        return {"success": False, "message": cmd_err, "task_id": task_id}

    waited = 0
    task_result = None
    while waited < max_wait:
        time.sleep(2)
        waited += 2
        task_result = get_task_result(task_id)
        if task_result is not None:
            break

    if task_result is None:
        return {"success": False, "message": f"任务超时 ({max_wait}s)", "task_id": task_id}

    return {
        "success": task_result.get("status") == "ok",
        "task_id": task_id,
        "authorized": task_result.get("authorized", False),
        "invited": task_result.get("invited", False),
        "message": task_result.get("message", ""),
    }


def _handle_share_to_account(device_id, parsed, body, interval):
    """处理「分享像素到广告账户」命令 — 多任务，每个任务可能包含多像素 + 多目标账户"""
    tasks = parsed.get("tasks", [])
    all_results = []
    idx = 0

    for task in tasks:
        pixel_names = task.get("pixel_names", [])
        pixel_ids = task.get("pixel_ids", [])
        target_ids = task.get("target_account_ids", [])

        if task.get("_error"):
            all_results.append({"index": idx, "success": False, "message": task["_error"]})
            idx += 1
            continue

        for target_id in target_ids:
            pixel_list = []
            for pn in pixel_names:
                pixel_list.append({"pixel_name": pn, "pixel_id": ""})
            for pid in pixel_ids:
                pixel_list.append({"pixel_id": pid, "pixel_name": ""})

            for px in pixel_list:
                cmd_params = {
                    "pixel_id": px.get("pixel_id", ""),
                    "target_account_id": target_id,
                }
                if px.get("pixel_name"):
                    cmd_params["pixel_name"] = px["pixel_name"]
                source_bm = task.get("source_bm_id") or body.get("business_id")
                if source_bm:
                    cmd_params["business_id"] = str(source_bm)

                r = _execute_single(device_id, "share_pixel_to_ad_account", cmd_params)
                r["index"] = idx
                r["pixel_name"] = px.get("pixel_name", "")
                r["pixel_id"] = px.get("pixel_id", "")
                r["target_account_id"] = target_id
                all_results.append(r)
                idx += 1
                time.sleep(interval)

    success_count = sum(1 for r in all_results if r.get("success"))
    return jsonify({
        "success": True,
        "action": "share_pixel_to_account",
        "total": len(all_results),
        "success_count": success_count,
        "fail_count": len(all_results) - success_count,
        "results": all_results,
    })


def _handle_share_to_bm(device_id, parsed, body, interval):
    """处理「分享像素到BM」命令 — 多任务，每个任务可能包含多像素 + 多目标BM"""
    tasks = parsed.get("tasks", [])
    all_results = []
    idx = 0

    for task in tasks:
        pixel_names = task.get("pixel_names", [])
        pixel_ids = task.get("pixel_ids", [])
        target_bms = task.get("target_bm_ids", [])

        if task.get("_error"):
            all_results.append({"index": idx, "success": False, "message": task["_error"]})
            idx += 1
            continue

        pixel_list = []
        for pn in pixel_names:
            pixel_list.append({"pixel_name": pn, "pixel_id": ""})
        for pid in pixel_ids:
            pixel_list.append({"pixel_id": pid, "pixel_name": ""})

        for target_bm in target_bms:
            for px in pixel_list:
                cmd_params = {
                    "pixel_id": px.get("pixel_id", ""),
                    "target_account_id": target_bm,
                }
                if px.get("pixel_name"):
                    cmd_params["pixel_name"] = px["pixel_name"]
                source_bm = task.get("source_bm_id") or body.get("business_id")
                if source_bm:
                    cmd_params["business_id"] = str(source_bm)

                r = _execute_single(device_id, "authorize_pixel", cmd_params)
                r["index"] = idx
                r["pixel_name"] = px.get("pixel_name", "")
                r["pixel_id"] = px.get("pixel_id", "")
                r["target_bm_id"] = target_bm
                all_results.append(r)
                idx += 1
                time.sleep(interval)

    success_count = sum(1 for r in all_results if r.get("success"))
    return jsonify({
        "success": True,
        "action": "share_pixel_to_bm",
        "total": len(all_results),
        "success_count": success_count,
        "fail_count": len(all_results) - success_count,
        "results": all_results,
    })


def _handle_share_bm(device_id, parsed, body, interval):
    """处理「分享BM」命令 — 邀请人员进BM，多任务"""
    tasks = parsed.get("tasks", [])
    all_results = []
    idx = 0

    for task in tasks:
        bm_ids = task.get("bm_ids", [])
        emails = task.get("emails", [])

        if task.get("_error"):
            all_results.append({"index": idx, "success": False, "message": task["_error"]})
            idx += 1
            continue

        for bm_id in bm_ids:
            for email in emails:
                cmd_params = {
                    "email": email,
                    "business_id": bm_id,
                }
                if body.get("role"):
                    cmd_params["role"] = str(body["role"])

                r = _execute_single(device_id, "invite_to_bm", cmd_params)
                r["index"] = idx
                r["email"] = email
                r["business_id"] = bm_id
                all_results.append(r)
                idx += 1
                time.sleep(interval)

    success_count = sum(1 for r in all_results if r.get("success"))
    return jsonify({
        "success": True,
        "action": "share_bm",
        "total": len(all_results),
        "success_count": success_count,
        "fail_count": len(all_results) - success_count,
        "results": all_results,
    })


@bp.route("/parse", methods=["POST"])
@api_key_required(scope=SCOPE)
def parse_only():
    """
    仅解析命令，不执行。用于预览/调试。

    Body: {
        "command": "分享像素到BM\n1.将像素：NYC02\n分享到BM：32321312322323"
    }
    """
    body = request.get_json(silent=True) or {}
    command_text = body.get("command", "").strip()

    if not command_text:
        return jsonify({"success": False, "message": "缺少 command 参数"}), 400

    parsed = parse_command(command_text)
    return jsonify({"success": True, "parsed": parsed})
