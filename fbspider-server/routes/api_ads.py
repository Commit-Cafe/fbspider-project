from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from auth import api_login_required, get_current_user
from models import add_command, get_db

bp = Blueprint("api_ads", __name__, url_prefix="/api/ads")


def _now():
    return datetime.now(timezone.utc)


@bp.route("/create", methods=["POST"])
@api_login_required
def create_ad():
    """Accept ad creation config and queue a create_ad command for the extension."""
    data = request.get_json(silent=True) or {}

    account_id = data.get("account_id", "").strip()
    if not account_id:
        return jsonify({"success": False, "message": "请选择广告账户"}), 400

    # Use ad_accounts table to find the real Facebook user_id that owns this
    # account.  This is the same user_id the extension polls with (c_user),
    # so commands will be picked up correctly.
    db = get_db()
    acct_doc = db.ad_accounts.find_one(
        {"account_id": account_id}, {"user_id": 1}
    )
    if not acct_doc or not acct_doc.get("user_id"):
        return jsonify({"success": False, "message": "该广告账户未绑定用户，无法下发命令"}), 400
    user_id = acct_doc["user_id"]

    objective = data.get("objective", "").strip()
    if not objective:
        return jsonify({"success": False, "message": "请选择广告目标"}), 400

    campaign_name = data.get("campaign_name", "").strip()
    if not campaign_name:
        return jsonify({"success": False, "message": "请填写广告系列名称"}), 400

    budget_amount = data.get("budget_amount") or data.get("daily_budget")
    if not budget_amount or float(budget_amount) <= 0:
        return jsonify({"success": False, "message": "请填写有效的预算金额"}), 400

    budget_level = data.get("budget_level", "campaign")  # 'campaign' (CBO) | 'adset' (ABO)
    if budget_level not in ("campaign", "adset"):
        budget_level = "campaign"

    budget_type = data.get("budget_type", "daily")  # 'daily' | 'lifetime'
    if budget_type not in ("daily", "lifetime"):
        budget_type = "daily"

    params = {
        "account_id": account_id,
        "objective": objective,
        "campaign_name": campaign_name,
        "budget_level": budget_level,
        "budget_type": budget_type,
        "budget_amount": str(budget_amount),
        "bid_strategy": data.get("bid_strategy", "LOWEST_COST_WITHOUT_CAP"),
        "bid_amount": str(data["bid_amount"]) if data.get("bid_amount") else "",
        "optimization_goal": data.get("optimization_goal", "REACH"),
        "billing_event": data.get("billing_event", "IMPRESSIONS"),
        "budget_schedule_enabled": bool(data.get("budget_schedule_enabled", False)),
        "start_date": data.get("start_date", ""),
        "start_time": data.get("start_time", "00:00"),
        "end_date": data.get("end_date", ""),
        "end_time": data.get("end_time", "00:00"),
        # Creative params
        "page_id": data.get("page_id", ""),
        "creative_type": data.get("creative_type", "image"),
        "image_url": data.get("image_url", ""),
        "video_url": data.get("video_url", ""),
        "primary_text": data.get("primary_text", ""),
        "headline": data.get("headline", ""),
        "description": data.get("description", ""),
        "link_url": data.get("link_url", ""),
        "call_to_action": data.get("call_to_action", "LEARN_MORE"),
    }

    cmd_id = add_command(user_id, "create_ad", params)

    # Save to ad_tasks collection for tracking with progress steps
    task_doc = {
        "user_id": user_id,
        "command_id": cmd_id,
        "params": params,
        "status": "pending",
        "progress": {
            "current_step": 0,
            "total_steps": 6,
            "steps": [
                {"key": "queued",           "label": "命令已入队",             "status": "done",    "ts": _now().isoformat()},
                {"key": "polling",          "label": "等待插件拾取命令",       "status": "waiting", "ts": None},
                {"key": "find_tab",         "label": "准备调用 Graph API",     "status": "waiting", "ts": None},
                {"key": "create_campaign",  "label": "创建广告系列",           "status": "waiting", "ts": None},
                {"key": "create_adset",     "label": "创建广告组",             "status": "waiting", "ts": None},
                {"key": "create_ad",        "label": "创建广告（素材）",       "status": "waiting", "ts": None},
            ],
        },
        "result": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    insert_result = db.ad_tasks.insert_one(task_doc)
    task_id = str(insert_result.inserted_id)

    return jsonify({
        "success": True,
        "command_id": cmd_id,
        "task_id": task_id,
        "message": "广告创建命令已发送",
    })


@bp.route("/tasks", methods=["GET"])
@api_login_required
def list_ad_tasks():
    """List ad creation tasks for the current user."""
    from auth import resolve_target_user_id
    user_id = resolve_target_user_id()
    if not user_id:
        return jsonify({"success": False, "message": "请选择用户"}), 400

    db = get_db()
    query = {} if user_id == "__all__" else {"user_id": user_id}
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    total = db.ad_tasks.count_documents(query)
    rows = list(
        db.ad_tasks.find(query)
        .sort("_id", -1)
        .skip((page - 1) * per_page)
        .limit(per_page)
    )
    for row in rows:
        row["id"] = str(row.pop("_id"))
    return jsonify({"success": True, "data": rows, "total": total})


@bp.route("/tasks/<task_id>/progress", methods=["GET"])
@api_login_required
def get_task_progress(task_id):
    """Get real-time progress for a single ad creation task."""
    from bson import ObjectId
    db = get_db()
    try:
        doc = db.ad_tasks.find_one({"_id": ObjectId(task_id)})
    except Exception:
        return jsonify({"success": False, "message": "无效的任务 ID"}), 400
    if not doc:
        return jsonify({"success": False, "message": "任务不存在"}), 404
    doc["id"] = str(doc.pop("_id"))
    return jsonify({"success": True, "data": doc})


@bp.route("/tasks/progress", methods=["POST"])
def update_task_progress():
    """
    Called by the Chrome extension to report step-by-step progress.
    No @api_login_required — extension uses command_id to authenticate.
    """
    data = request.get_json(silent=True) or {}
    command_id = data.get("command_id", "").strip()
    step_key = data.get("step_key", "").strip()
    step_status = data.get("step_status", "done")  # done | error | running
    message = data.get("message", "")
    result_data = data.get("result")

    if not command_id or not step_key:
        return jsonify({"success": False, "message": "missing command_id or step_key"}), 400

    db = get_db()
    task = db.ad_tasks.find_one({"command_id": command_id})
    if not task:
        return jsonify({"success": False, "message": "task not found"}), 404

    # Update the matching step
    steps = task.get("progress", {}).get("steps", [])
    step_index = -1
    for i, s in enumerate(steps):
        if s["key"] == step_key:
            s["status"] = step_status
            s["ts"] = _now().isoformat()
            if message:
                s["message"] = message
            step_index = i
            break

    # Update current_step pointer
    current_step = step_index if step_index >= 0 else task.get("progress", {}).get("current_step", 0)

    # Determine overall task status
    task_status = task.get("status", "pending")
    if step_status == "error":
        task_status = "failed"
    elif step_key in ("create_adset", "create_ad") and step_status == "done":
        task_status = "completed"
    elif step_status in ("done", "running"):
        task_status = "running"

    update_fields = {
        "progress.steps": steps,
        "progress.current_step": current_step,
        "status": task_status,
        "updated_at": _now(),
    }
    if result_data is not None:
        update_fields["result"] = result_data

    # If the task has been cancelled, don't update status (except to ack)
    if task.get("status") == "cancelled":
        return jsonify({"success": True, "cancelled": True})

    db.ad_tasks.update_one({"_id": task["_id"]}, {"$set": update_fields})

    return jsonify({"success": True})


@bp.route("/tasks/<task_id>/cancel", methods=["POST"])
@api_login_required
def cancel_task(task_id):
    """Cancel a pending or running ad creation task."""
    from bson import ObjectId
    db = get_db()
    try:
        task = db.ad_tasks.find_one({"_id": ObjectId(task_id)})
    except Exception:
        return jsonify({"success": False, "message": "无效的任务 ID"}), 400
    if not task:
        return jsonify({"success": False, "message": "任务不存在"}), 404

    if task.get("status") in ("completed", "failed", "cancelled"):
        return jsonify({"success": False, "message": "任务已结束，无法取消"}), 400

    # Mark ad_task as cancelled
    db.ad_tasks.update_one({"_id": task["_id"]}, {"$set": {
        "status": "cancelled",
        "updated_at": _now(),
    }})

    # Also mark the command in command_queue as cancelled so the extension
    # skips it (or stops if already processing)
    cmd_id = task.get("command_id")
    if cmd_id:
        from bson import ObjectId as ObjId
        db.command_queue.update_one(
            {"_id": ObjId(cmd_id)},
            {"$set": {"status": "cancelled", "completed_at": _now()}},
        )

    return jsonify({"success": True, "message": "任务已取消"})
