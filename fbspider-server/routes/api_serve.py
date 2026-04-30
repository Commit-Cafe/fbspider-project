import os
from flask import Blueprint, Response, jsonify, request
import csv
import io
import json
import re
from datetime import datetime, timezone

from auth import api_admin_required, api_login_required, get_current_user, get_manageable_user_ids, resolve_target_user_id
from config import ACCOUNT_DSL_CALLBACK_INTERVAL_MINUTES, ACCOUNT_DSL_CALLBACK_LOG_DIR
from models import get_db, get_extension_state

bp = Blueprint("api_serve", __name__, url_prefix="/api")


def _query_user_id():
    return resolve_target_user_id()


def _manager_target_list():
    user = get_current_user()
    if user and user.get("role") == "admin":
        target = request.args.get("target_user_id", "").strip()
        if target == "__all__":
            return None
        return [_query_user_id()]

    if user and user.get("role") == "leader":
        target = request.args.get("target_user_id", "").strip()
        if target == "__all__":
            return get_manageable_user_ids(include_self=True) or []
        return [_query_user_id()]

    return [_query_user_id()]


def _user_query(field="user_id"):
    targets = _manager_target_list()
    if targets is None:
        return {}
    return {field: {"$in": targets}}


def _account_user_query():
    targets = _manager_target_list()
    if targets is None:
        return {}
    return {
        "$or": [
            {"user_id": {"$in": targets}},
            {"source_user_ids": {"$in": targets}},
        ]
    }


def _bm_account_count(db, user_id, bm_id):
    count = db.bm_ad_accounts.count_documents({"user_id": user_id, "bm_id": bm_id})
    if count:
        return count
    return db.ad_accounts.count_documents({
        "bm_id": bm_id,
        "$or": [
            {"user_id": user_id},
            {"source_user_ids": user_id},
        ]
    })


def _bm_accounts_query(user_id, bm_id, account_ids=None):
    acct_match = [{"bm_id": bm_id}]
    if account_ids:
        acct_match.append({"account_id": {"$in": account_ids}})
    return {
        "$and": [
            {"$or": acct_match},
            {"$or": [
                {"user_id": user_id},
                {"source_user_ids": user_id},
            ]},
        ],
    }


def _get_bm_accounts_data(db, bm):
    bm_accts = list(db.bm_ad_accounts.find({"user_id": bm["user_id"], "bm_id": bm["bm_id"]}, {"_id": 0}))
    account_ids = [ba["account_id"] for ba in bm_accts if ba.get("account_id")]
    acct_type_map = {ba["account_id"]: ba.get("account_type", "owned") for ba in bm_accts if ba.get("account_id")}
    account_query = _bm_accounts_query(bm["user_id"], bm["bm_id"], account_ids)
    accounts = list(db.ad_accounts.find(account_query, {"_id": 0}).sort("updated_at", -1))

    existing_ids = set()
    for account in accounts:
        account_id = str(account.get("account_id") or "").strip()
        if not account_id:
            continue
        existing_ids.add(account_id)
        account["bm_account_type"] = acct_type_map.get(account_id, account.get("ownership", "owned"))

    for account_id in account_ids:
        if account_id in existing_ids:
            continue
        accounts.append({
            "account_id": account_id,
            "name": "",
            "account_status": "UNKNOWN",
            "balance": "-",
            "bm_account_type": acct_type_map.get(account_id, "owned"),
            "is_placeholder": True,
        })

    accounts.sort(key=lambda item: (
        1 if item.get("is_placeholder") else 0,
        str(item.get("name") or ""),
        str(item.get("account_id") or ""),
    ))
    return accounts


def _parse_ts(value):
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _callback_log_path(filename):
    safe_name = os.path.basename(str(filename or ""))
    if not safe_name:
        return ""
    return os.path.join(ACCOUNT_DSL_CALLBACK_LOG_DIR, safe_name)


@bp.route("/accounts", methods=["GET"])
@api_login_required
def list_accounts():
    search = request.args.get("search", "")
    sort_by = request.args.get("sort", "updated_at")
    order = request.args.get("order", "desc")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 50))

    allowed_sorts = ["account_id", "name", "account_status", "balance_tous",
                     "amount_spent_tous", "currency", "updated_at", "create_date", "user_id"]
    if sort_by not in allowed_sorts:
        sort_by = "updated_at"
    direction = 1 if order == "asc" else -1

    db = get_db()
    query = _account_user_query()
    if search:
        regex = {"$regex": re.escape(search), "$options": "i"}
        query = {
            "$and": [
                query,
                {"$or": [{"account_id": regex}, {"name": regex}, {"account_status": regex}, {"user_id": regex}]},
            ]
        }

    total = db.ad_accounts.count_documents(query)
    cursor = db.ad_accounts.find(query, {"_id": 0}).sort(sort_by, direction).skip((page - 1) * per_page).limit(per_page)
    accounts = list(cursor)

    # Enrich accounts with BM name from bm_list collection
    bm_ids = list({a["bm_id"] for a in accounts if a.get("bm_id")})
    bm_name_map = {}
    if bm_ids:
        for bm_doc in db.bm_list.find({"bm_id": {"$in": bm_ids}}, {"bm_id": 1, "name": 1, "_id": 0}):
            bm_name_map[bm_doc["bm_id"]] = bm_doc.get("name", "")
    for acct in accounts:
        if not acct.get("bm_name") and acct.get("bm_id"):
            acct["bm_name"] = bm_name_map.get(acct["bm_id"], "")

    return jsonify({
        "success": True,
        "data": accounts,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page
    })


@bp.route("/accounts/<account_id>", methods=["GET"])
@api_login_required
def get_account(account_id):
    db = get_db()
    row = db.ad_accounts.find_one({
        "$and": [
            _account_user_query(),
            {"account_id": account_id},
        ]
    }, {"_id": 0})
    if not row:
        return jsonify({"success": False, "message": "Not found"}), 404
    visible_user_ids = row.get("source_user_ids") or ([row["user_id"]] if row.get("user_id") else [])
    users = list(db.ad_account_users.find({"user_id": {"$in": visible_user_ids}, "account_id": account_id}, {"_id": 0}))
    row["users"] = users
    return jsonify({"success": True, "data": row})


@bp.route("/accounts/export", methods=["GET"])
@api_login_required
def export_accounts():
    db = get_db()
    rows = list(db.ad_accounts.find(_account_user_query(), {"_id": 0}).sort("updated_at", -1))
    output = io.StringIO()
    writer = csv.writer(output)
    fields = ["user_id", "account_id", "name", "account_status", "currency", "balance", "balance_tous",
              "amount_spent", "amount_spent_tous", "adtrust_dsl", "threshold_amount",
              "paymentcard", "account_type", "ownership", "create_date", "bm_id"]
    writer.writerow(fields)
    for d in rows:
        writer.writerow([d.get(f, "") for f in fields])
    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=ad_accounts.csv"})


@bp.route("/stats", methods=["GET"])
@api_login_required
def get_stats():
    db = get_db()
    base_query = _account_user_query()
    total = db.ad_accounts.count_documents(base_query)
    active = db.ad_accounts.count_documents({**base_query, "account_status": {"$in": ["ACTIVE", "1"]}})
    disabled = db.ad_accounts.count_documents({**base_query, "account_status": {"$in": ["DISABLED", "2"]}})

    total_balance = 0
    for row in db.ad_accounts.find(base_query, {"balance_tous": 1, "_id": 0}):
        val = row.get("balance_tous") or "0"
        try:
            total_balance += float(str(val).replace("$", "").replace(",", "").strip())
        except (ValueError, AttributeError):
            pass

    return jsonify({
        "success": True,
        "data": {
            "total_accounts": total,
            "active_accounts": active,
            "disabled_accounts": disabled,
            "total_balance_usd": f"${total_balance:,.2f}",
            "bm_count": db.bm_list.count_documents(base_query),
            "pixel_count": db.pixels.count_documents(base_query),
            "ad_library_count": db.ad_library_items.count_documents(base_query),
        }
    })


@bp.route("/bms", methods=["GET"])
@api_login_required
def list_bms():
    db = get_db()
    rows = list(db.bm_list.find(_user_query(), {"_id": 0}).sort("updated_at", -1))
    for row in rows:
        accounts = _get_bm_accounts_data(db, row)
        row["account_count"] = len(accounts)
        row["account_preview"] = [
            {
                "account_id": account.get("account_id", ""),
                "name": account.get("name", ""),
                "is_placeholder": bool(account.get("is_placeholder")),
            }
            for account in accounts
        ]
    return jsonify({"success": True, "data": rows})


@bp.route("/bms/<bm_id>", methods=["GET"])
@api_login_required
def get_bm(bm_id):
    db = get_db()
    row = db.bm_list.find_one({**_user_query(), "bm_id": bm_id}, {"_id": 0})
    if not row:
        return jsonify({"success": False, "message": "Not found"}), 404
    return jsonify({"success": True, "data": row})


@bp.route("/bms/<bm_id>/accounts", methods=["GET"])
@api_login_required
def get_bm_accounts(bm_id):
    db = get_db()
    bm = db.bm_list.find_one({**_user_query(), "bm_id": bm_id}, {"_id": 0})
    if not bm:
        return jsonify({"success": True, "data": []})
    return jsonify({"success": True, "data": _get_bm_accounts_data(db, bm)})


@bp.route("/pixels", methods=["GET"])
@api_login_required
def list_pixels():
    rows = list(get_db().pixels.find(_user_query(), {"_id": 0}).sort("updated_at", -1))
    return jsonify({"success": True, "data": rows})


@bp.route("/pixels/<pixel_id>", methods=["GET"])
@api_login_required
def get_pixel(pixel_id):
    db = get_db()
    row = db.pixels.find_one({**_user_query(), "pixel_id": pixel_id}, {"_id": 0})
    if not row:
        return jsonify({"success": False, "message": "Not found"}), 404
    row["associations"] = list(db.pixel_associations.find({"user_id": row["user_id"], "pixel_id": pixel_id}, {"_id": 0}))
    return jsonify({"success": True, "data": row})


@bp.route("/pixels/<pixel_id>/purchases", methods=["GET"])
@api_login_required
def get_pixel_purchases(pixel_id):
    db = get_db()
    row = db.pixel_purchase_events.find_one(
        {**_user_query(), "pixel_id": pixel_id},
        {"_id": 0},
        sort=[("fetched_at", -1)]
    )
    if not row:
        return jsonify({"success": True, "data": None})
    try:
        row["event_data"] = json.loads(row["event_data"])
    except (json.JSONDecodeError, TypeError):
        pass
    return jsonify({"success": True, "data": row})


@bp.route("/ad-library", methods=["GET"])
@api_login_required
def list_ad_library():
    media_type = request.args.get("media_type", "")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 24))
    query = _user_query()
    if media_type:
        query["media_type"] = media_type

    db = get_db()
    total = db.ad_library_items.count_documents(query)
    rows = list(db.ad_library_items.find(query, {"_id": 0}).sort("created_at", -1).skip((page - 1) * per_page).limit(per_page))
    return jsonify({
        "success": True,
        "data": rows,
        "total": total,
        "page": page,
        "pages": (total + per_page - 1) // per_page
    })


@bp.route("/ad-library/<ad_archive_id>", methods=["GET"])
@api_login_required
def get_ad_library_item(ad_archive_id):
    row = get_db().ad_library_items.find_one({**_user_query(), "ad_archive_id": ad_archive_id}, {"_id": 0})
    if not row:
        return jsonify({"success": False, "message": "Not found"}), 404
    return jsonify({"success": True, "data": row})


@bp.route("/logs", methods=["GET"])
@api_login_required
def list_logs():
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 50))
    db = get_db()
    query = _user_query()
    total = db.action_logs.count_documents(query)
    rows = list(db.action_logs.find(query, {"_id": 0}).sort("_id", -1).skip((page - 1) * per_page).limit(per_page))
    return jsonify({"success": True, "data": rows, "total": total})


@bp.route("/dsl-push-logs", methods=["GET"])
@api_login_required
def list_dsl_push_logs():
    """List recent formatted_dsl push logs for the DSL push monitor."""
    limit = min(int(request.args.get("limit", 50)), 200)
    db = get_db()
    query = _user_query()
    query["action"] = "receive_account_dsl"
    rows = list(db.action_logs.find(query, {"_id": 0}).sort("_id", -1).limit(limit))
    return jsonify({"success": True, "data": rows})


@bp.route("/dsl-overview", methods=["GET"])
@api_login_required
def dsl_overview():
    """Overview of formatted_dsl status for all accounts."""
    db = get_db()
    query = _account_user_query()
    rows = list(db.ad_accounts.find(query, {
        "_id": 0, "account_id": 1, "name": 1, "account_status": 1,
        "formatted_dsl": 1, "formatted_dsl_tous": 1,
        "adtrust_dsl": 1, "adtrust_dsl_tous": 1,
        "currency": 1, "updated_at": 1,
        "dsl_fetch_status": 1, "dsl_fetch_error": 1,
        "dsl_fetch_attempts": 1, "dsl_fetch_source": 1,
    }).sort("updated_at", -1))
    total = len(rows)
    has_dsl = sum(1 for r in rows if r.get("formatted_dsl"))
    missing_dsl = total - has_dsl
    missing_by_reason = {}
    for row in rows:
        if row.get("formatted_dsl"):
            continue
        reason = row.get("dsl_fetch_status") or "unknown"
        missing_by_reason[reason] = missing_by_reason.get(reason, 0) + 1
    return jsonify({
        "success": True,
        "summary": {
            "total": total,
            "has_formatted_dsl": has_dsl,
            "missing_formatted_dsl": missing_dsl,
            "missing_by_reason": missing_by_reason,
        },
        "data": rows,
    })


@bp.route("/db-stats", methods=["GET"])
@api_login_required
def db_stats():
    db = get_db()
    query = _user_query()
    collections = ["ad_accounts", "bm_list", "bm_ad_accounts", "ad_account_users",
                   "pixels", "pixel_associations", "pixel_purchase_events",
                   "ad_library_items", "command_queue", "action_logs", "extension_state"]
    stats = {col: db[col].count_documents(query) for col in collections}
    return jsonify({"success": True, "data": stats})


@bp.route("/connection-state", methods=["GET"])
@api_login_required
def connection_state():
    user_id = _query_user_id()
    if not user_id or user_id == "__all__":
        return jsonify({
            "success": True,
            "data": {
                "selected_user": user_id or "",
                "has_token": False,
                "fb_user_id": "",
                "fb_user_name": "",
                "heartbeat_ok": False,
                "last_heartbeat": "",
                "last_token_time": "",
            }
        })

    token_info = get_extension_state(user_id, "token_info") or {}
    heartbeat = get_extension_state(user_id, "heartbeat") or {}
    last_token_time = get_extension_state(user_id, "last_token_time") or ""

    heartbeat_ts = heartbeat.get("timestamp", "") if isinstance(heartbeat, dict) else ""
    heartbeat_dt = _parse_ts(heartbeat_ts)
    heartbeat_ok = False
    if heartbeat_dt:
        heartbeat_ok = (datetime.now(timezone.utc) - heartbeat_dt).total_seconds() <= 120

    fb_user_id = ""
    fb_user_name = ""
    has_token = False
    if isinstance(token_info, dict):
        fb_user_id = str(token_info.get("id") or token_info.get("c_user") or token_info.get("uid") or "")
        fb_user_name = str(token_info.get("name") or "")
        has_token = bool(token_info.get("has_token") or token_info.get("token"))

    return jsonify({
        "success": True,
        "data": {
            "selected_user": user_id,
            "has_token": has_token,
            "fb_user_id": fb_user_id,
            "fb_user_name": fb_user_name,
            "heartbeat_ok": heartbeat_ok,
            "last_heartbeat": heartbeat_ts,
            "last_token_time": str(last_token_time or ""),
        }
    })


@bp.route("/clear-data", methods=["POST"])
@api_login_required
def clear_data():
    data = request.get_json(silent=True) or {}
    table_name = data.get("table", "all")
    user_id = _query_user_id()
    if not user_id or user_id == "__all__":
        return jsonify({"success": False, "message": "请选择具体用户"}), 400
    db = get_db()
    if table_name == "all":
        for col in ["ad_accounts", "bm_list", "bm_ad_accounts", "ad_account_users",
                    "pixels", "pixel_associations", "pixel_purchase_events",
                    "ad_library_items", "command_queue", "action_logs", "extension_state"]:
            db[col].delete_many({"user_id": user_id})
    else:
        allowed = ["ad_accounts", "bm_list", "pixels", "ad_library_items", "command_queue", "action_logs"]
        if table_name in allowed:
            db[table_name].delete_many({"user_id": user_id})
    return jsonify({"success": True})


@bp.route("/callback-status", methods=["GET"])
@api_admin_required
def callback_status():
    """Check scheduler status and last run info."""
    db = get_db()
    jobs = list(db.scheduled_jobs.find({}, {"_id": 1, "last_run_slot": 1, "last_status": 1,
                                             "last_finished_at": 1, "lock_owner": 1, "lock_until": 1}))
    log_dir = ACCOUNT_DSL_CALLBACK_LOG_DIR
    log_count = 0
    latest_log = None
    if os.path.isdir(log_dir):
        files = sorted([f for f in os.listdir(log_dir) if f.endswith(".json")], reverse=True)
        log_count = len(files)
        if files:
            latest_log = files[0]
    for j in jobs:
        j["_id"] = str(j["_id"])
        if j.get("last_finished_at"):
            j["last_finished_at"] = str(j["last_finished_at"])
        if j.get("lock_until"):
            j["lock_until"] = str(j["lock_until"])
    return jsonify({
        "success": True,
        "jobs": jobs,
        "log_dir": log_dir,
        "log_count": log_count,
        "latest_log": latest_log,
        "callback_interval_minutes": max(int(ACCOUNT_DSL_CALLBACK_INTERVAL_MINUTES or 10), 1),
        "server_time_utc": datetime.now(timezone.utc).isoformat(),
    })


@bp.route("/callback-logs", methods=["GET"])
@api_admin_required
def list_callback_logs():
    limit = min(max(int(request.args.get("limit", 50)), 1), 200)
    if not os.path.isdir(ACCOUNT_DSL_CALLBACK_LOG_DIR):
        return jsonify({"success": True, "data": []})

    rows = []
    for name in sorted(os.listdir(ACCOUNT_DSL_CALLBACK_LOG_DIR), reverse=True):
        if not name.endswith(".json"):
            continue
        path = os.path.join(ACCOUNT_DSL_CALLBACK_LOG_DIR, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                doc = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        rows.append({
            "filename": name,
            "stage": doc.get("stage", ""),
            "slot": doc.get("slot", ""),
            "count": doc.get("count", 0),
            "status_code": doc.get("status_code"),
            "logged_at": doc.get("logged_at", ""),
            "preview": doc.get("preview", []),
            "response": doc.get("response", ""),
            "error": doc.get("error", ""),
        })
        if len(rows) >= limit:
            break
    return jsonify({"success": True, "data": rows})


@bp.route("/callback-logs/<filename>", methods=["GET"])
@api_admin_required
def get_callback_log(filename):
    path = _callback_log_path(filename)
    if not path or not os.path.isfile(path):
        return jsonify({"success": False, "message": "Not found"}), 404
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError):
        return jsonify({"success": False, "message": "Invalid log file"}), 500
    return jsonify({"success": True, "data": doc})


@bp.route("/campaigns", methods=["GET"])
@api_login_required
def list_campaigns():
    account_id = request.args.get("account_id", "").strip()
    if not account_id:
        return jsonify({"success": False, "message": "account_id required"}), 400
    db = get_db()
    query = {"account_id": account_id}
    user_query = _user_query()
    if user_query:
        query.update(user_query)
    rows = list(db.campaigns.find(query).sort("updated_at", -1))
    for r in rows:
        r["id"] = str(r.pop("_id"))
    return jsonify({"success": True, "data": rows})
