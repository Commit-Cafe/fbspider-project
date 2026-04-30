from flask import Blueprint, jsonify, request

from auth import api_login_required, get_current_user, resolve_target_user_id
from models import add_command, complete_command, get_db, poll_commands

bp = Blueprint("api_commands", __name__, url_prefix="/api/commands")


def _command_user():
    target = resolve_target_user_id()
    if target == "__all__":
        return ""
    return target


@bp.route("/poll", methods=["GET"])
@api_login_required
def poll():
    import sys
    primary = _command_user()
    already = {primary} if primary else set()
    commands = poll_commands(primary) if primary else []

    # The extension sends extra identity hints so we can match commands that
    # were stored under a different user_id variant.
    extra_ids = set()

    # 1. flask_user — the extension's own Flask login username
    flask_user = request.args.get("flask_user", "").strip()
    if flask_user:
        extra_ids.add(flask_user)

    # 2. fb_user_id — the Facebook c_user numeric ID
    fb_user = request.args.get("fb_user_id", "").strip()
    if fb_user:
        extra_ids.add(fb_user)
        # Reverse lookup: c_user → ad_accounts.source_user_ids → user_id
        db = get_db()
        for doc in db.ad_accounts.find(
            {"source_user_ids": fb_user}, {"user_id": 1}
        ).limit(10):
            uid = doc.get("user_id", "")
            if uid:
                extra_ids.add(uid)

    # Poll for each unique user_id we haven't checked yet
    for uid in extra_ids:
        if uid not in already:
            commands.extend(poll_commands(uid))
            already.add(uid)

    # Debug: log when commands are found
    if commands:
        print(f"[poll-debug] primary={primary} extra={extra_ids} found={len(commands)} ids={[c.get('id') for c in commands]}", file=sys.stderr, flush=True)

    return jsonify({"success": True, "commands": commands})


@bp.route("/create", methods=["POST"])
@api_login_required
def create():
    data = request.get_json(silent=True) or {}
    command_type = data.get("command_type", "")
    params = data.get("params", {})
    user_id = _command_user()
    if not user_id:
        return jsonify({"success": False, "message": "请选择具体用户后再发送命令"}), 400

    valid_commands = [
        "refresh_all_accounts", "refresh_account", "refresh_bm_list",
        "share_pixel", "remove_pixel_user", "remove_pixel_partner",
        "remove_pixel_adaccount", "update_account_name",
        "delete_hidden_admin", "refresh_token", "refresh_pixels",
        "refresh_hidden_accounts", "fetch_campaigns", "toggle_campaign",
        "create_ad"
    ]
    if command_type not in valid_commands:
        return jsonify({"success": False, "message": f"Invalid command: {command_type}"}), 400

    cmd_id = add_command(user_id, command_type, params)
    return jsonify({"success": True, "command_id": cmd_id})


@bp.route("/<cmd_id>/complete", methods=["PUT"])
@api_login_required
def complete(cmd_id):
    data = request.get_json(silent=True) or {}
    complete_command(cmd_id, data.get("result"))
    return jsonify({"success": True})


@bp.route("/history", methods=["GET"])
@api_login_required
def history():
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    user_id = _command_user()
    if not user_id:
        return jsonify({"success": False, "message": "请选择具体用户"}), 400
    db = get_db()
    total = db.command_queue.count_documents({"user_id": user_id})
    rows = list(db.command_queue.find({"user_id": user_id}).sort("_id", -1).skip((page - 1) * per_page).limit(per_page))
    for row in rows:
        row["id"] = str(row.pop("_id"))
    return jsonify({"success": True, "data": rows, "total": total})
