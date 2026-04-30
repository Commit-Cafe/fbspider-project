from flask import Blueprint, jsonify, request

from auth import api_login_required, api_user_manager_required, get_current_user, login_user, logout_user
from models import (
    change_user_password,
    create_auth_session,
    create_user,
    delete_auth_session,
    delete_user,
    delete_user_sessions,
    get_user_summary,
    get_user_by_username,
    list_users,
    normalize_role,
    update_user,
    verify_user_credentials,
)

bp = Blueprint("auth_api", __name__, url_prefix="/api/auth")


@bp.route("/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    user = verify_user_credentials(username, password)
    if not user:
        return jsonify({"success": False, "message": "用户名或密码错误"}), 401

    login_user(user["username"])

    token = None
    if data.get("issue_token", True):
        token = create_auth_session(user["username"], data.get("client_type", "extension"))

    return jsonify({
        "success": True,
        "user": user,
        "token": token,
        "summary": get_user_summary(user["username"])
    })


@bp.route("/logout", methods=["POST"])
def api_logout():
    token = request.headers.get("X-Auth-Token", "")
    auth_header = request.headers.get("Authorization", "")
    if not token and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    if token:
        delete_auth_session(token)
    logout_user()
    return jsonify({"success": True})


@bp.route("/me", methods=["GET"])
@api_login_required
def api_me():
    user = get_current_user()
    return jsonify({
        "success": True,
        "user": user,
        "summary": get_user_summary(user["username"])
    })


@bp.route("/change-password", methods=["POST"])
@api_login_required
def api_change_password():
    data = request.get_json(silent=True) or {}
    user = get_current_user()
    try:
        change_user_password(
            user["username"],
            data.get("current_password", ""),
            data.get("new_password", "")
        )
        return jsonify({"success": True})
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400


def _can_manage_user(actor, target_user):
    if not actor or not target_user:
        return False
    if actor.get("role") == "admin":
        return True
    if actor.get("role") != "leader":
        return False
    return target_user.get("created_by") == actor.get("username") and target_user.get("role") == "user"


@bp.route("/users", methods=["GET"])
@api_user_manager_required
def api_list_users():
    actor = get_current_user()
    rows = []
    user_rows = list_users() if actor.get("role") == "admin" else list_users(created_by=actor["username"])
    for user in user_rows:
        row = dict(user)
        row["summary"] = get_user_summary(user["username"])
        rows.append(row)
    return jsonify({"success": True, "data": rows})


@bp.route("/users", methods=["POST"])
@api_user_manager_required
def api_create_user():
    data = request.get_json(silent=True) or {}
    actor = get_current_user()
    role = normalize_role(data.get("role", "user"))
    if actor.get("role") == "leader" and role != "user":
        return jsonify({"success": False, "message": "组长只能创建普通用户"}), 403
    try:
        user = create_user(
            data.get("username", ""),
            data.get("password", ""),
            role,
            data.get("status", "active"),
            data.get("display_name", ""),
            created_by=actor["username"],
        )
        return jsonify({"success": True, "data": user})
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400


@bp.route("/users/<username>", methods=["PUT"])
@api_user_manager_required
def api_update_user(username):
    data = request.get_json(silent=True) or {}
    actor = get_current_user()
    target_user = get_user_by_username(username)
    if not target_user:
        return jsonify({"success": False, "message": "用户不存在"}), 404
    if not _can_manage_user(actor, target_user):
        return jsonify({"success": False, "message": "Forbidden"}), 403
    if actor.get("role") == "leader" and "role" in data and normalize_role(data.get("role")) != "user":
        return jsonify({"success": False, "message": "组长只能将用户设置为普通用户"}), 403
    try:
        user = update_user(username, data)
        if data.get("status") == "disabled":
            delete_user_sessions(username)
        return jsonify({"success": True, "data": user})
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400


@bp.route("/users/<username>", methods=["DELETE"])
@api_user_manager_required
def api_delete_user(username):
    actor = get_current_user()
    target_user = get_user_by_username(username)
    if not target_user:
        return jsonify({"success": False, "message": "用户不存在"}), 404
    if not _can_manage_user(actor, target_user):
        return jsonify({"success": False, "message": "Forbidden"}), 403
    try:
        delete_user(username)
        return jsonify({"success": True})
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
