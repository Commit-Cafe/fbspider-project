from functools import wraps

from flask import g, jsonify, redirect, request, session, url_for

from models import get_user_by_token, get_user_by_api_key, get_user_public, list_users


def _extract_bearer_token():
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    return request.headers.get("X-Auth-Token", "").strip()


def get_current_user():
    if hasattr(g, "current_user"):
        return g.current_user

    user = None

    # 1. API Key (X-API-Key header)
    api_key = request.headers.get("X-API-Key", "").strip()
    if api_key:
        user = get_user_by_api_key(api_key)
        if user:
            g.auth_via = "api_key"
            g.current_user = user
            return user

    # 2. Bearer token
    token = _extract_bearer_token()
    if token:
        user = get_user_by_token(token)
        g.auth_token = token
        g.auth_via = "token"
    else:
        # 3. Session
        username = session.get("auth_username", "")
        if username:
            user = get_user_public(username)
            g.auth_via = "session"

    if user and user.get("status") != "active":
        user = None

    g.current_user = user
    return user


def login_user(username):
    session["auth_username"] = username


def logout_user():
    session.pop("auth_username", None)


def is_admin():
    user = get_current_user()
    return bool(user and user.get("role") == "admin")


def is_user_manager():
    user = get_current_user()
    return bool(user and user.get("role") in {"admin", "leader"})


def get_manageable_user_ids(include_self=True):
    user = get_current_user()
    if not user:
        return []

    if user.get("role") == "admin":
        return None

    if user.get("role") == "leader":
        user_ids = [row["username"] for row in list_users(created_by=user["username"]) if row.get("username")]
        if include_self and user.get("username"):
            user_ids.insert(0, user["username"])
        deduped = []
        for user_id in user_ids:
            if user_id and user_id not in deduped:
                deduped.append(user_id)
        return deduped

    return [user["username"]] if include_self and user.get("username") else []


def resolve_target_user_id(default_to_current=True):
    user = get_current_user()
    if not user:
        return ""

    target = (
        request.args.get("target_user_id")
        or (request.get_json(silent=True) or {}).get("target_user_id", "")
        or request.form.get("target_user_id", "")
    ).strip()

    if user.get("role") == "admin" and target:
        return target

    if user.get("role") == "leader" and target:
        if target == "__all__":
            return target
        manageable = get_manageable_user_ids(include_self=True) or []
        if target in manageable:
            return target

    return user["username"] if default_to_current else target


def page_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not get_current_user():
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def page_admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = get_current_user()
        if not user:
            return redirect(url_for("login", next=request.path))
        if user.get("role") != "admin":
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)
    return wrapped


def api_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not get_current_user():
            return jsonify({"success": False, "message": "Unauthorized"}), 401
        return view(*args, **kwargs)
    return wrapped


def api_admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"success": False, "message": "Unauthorized"}), 401
        if user.get("role") != "admin":
            return jsonify({"success": False, "message": "Forbidden"}), 403
        return view(*args, **kwargs)
    return wrapped


def api_key_required(scope=None):
    """允许 API Key 或 admin 用户访问。如指定 scope，API Key 需包含该 scope。"""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = get_current_user()
            if not user:
                return jsonify({"success": False, "message": "Unauthorized"}), 401
            via = getattr(g, "auth_via", "")
            if via == "api_key":
                if scope and scope not in (user.get("_api_key_scopes") or []):
                    return jsonify({"success": False, "message": f"API Key 缺少 scope: {scope}"}), 403
                return view(*args, **kwargs)
            # 非 API Key 则要求 admin
            if user.get("role") != "admin":
                return jsonify({"success": False, "message": "Forbidden"}), 403
            return view(*args, **kwargs)
        return wrapped
    return decorator


def api_user_manager_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"success": False, "message": "Unauthorized"}), 401
        if user.get("role") not in {"admin", "leader"}:
            return jsonify({"success": False, "message": "Forbidden"}), 403
        return view(*args, **kwargs)
    return wrapped
