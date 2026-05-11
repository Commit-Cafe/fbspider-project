import json
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient, ASCENDING, DESCENDING
from logger import logger
from werkzeug.security import generate_password_hash, check_password_hash
from config import MONGO_URI, MONGO_DB

_client = None
USER_COLLECTION = "fbhelper_users"


def normalize_role(role):
    role = str(role or "").strip().lower()
    if role == "admin":
        return "admin"
    if role == "leader":
        return "leader"
    return "user"


def get_db():
    global _client
    if _client is None:
        _client = MongoClient(
            MONGO_URI,
            connectTimeoutMS=5000,
            serverSelectionTimeoutMS=5000,
            maxPoolSize=20,
            minPoolSize=2,
            retryWrites=True,
        )
    return _client[MONGO_DB]


def init_db():
    db = get_db()
    logger.info("Creating MongoDB indexes...")

    _ensure_ad_accounts_indexes(db)
    _ensure_fbhelper_acc_indexes(db)
    _ensure_api_key_indexes(db)
    db.bm_list.create_index([("user_id", ASCENDING), ("bm_id", ASCENDING)], unique=True)
    db.bm_ad_accounts.create_index([("user_id", ASCENDING), ("bm_id", ASCENDING), ("account_id", ASCENDING)], unique=True)
    db.ad_account_users.create_index([("user_id", ASCENDING), ("account_id", ASCENDING), ("ad_user_id", ASCENDING)], unique=True)
    db.pixels.create_index([("user_id", ASCENDING), ("pixel_id", ASCENDING)], unique=True)
    db.pixel_associations.create_index([("user_id", ASCENDING), ("pixel_id", ASCENDING), ("assoc_type", ASCENDING), ("assoc_id", ASCENDING)], unique=True)
    db.pixel_purchase_events.create_index([("user_id", ASCENDING), ("pixel_id", ASCENDING)])
    db.ad_library_items.create_index([("user_id", ASCENDING), ("ad_archive_id", ASCENDING)], unique=True)
    db.campaigns.create_index([("account_id", ASCENDING), ("campaign_id", ASCENDING)], unique=True)
    db.campaigns.create_index([("user_id", ASCENDING), ("account_id", ASCENDING)])
    db.command_queue.create_index([("user_id", ASCENDING), ("status", ASCENDING)])
    db.action_logs.create_index([("user_id", ASCENDING)])
    db.extension_state.create_index([("user_id", ASCENDING), ("key", ASCENDING)], unique=True)
    db[USER_COLLECTION].create_index([("username", ASCENDING)], unique=True)
    db[USER_COLLECTION].create_index([("role", ASCENDING), ("status", ASCENDING)])
    db[USER_COLLECTION].create_index([("created_by", ASCENDING), ("created_at", ASCENDING)])
    db.auth_sessions.create_index([("token_hash", ASCENDING)], unique=True)
    db.auth_sessions.create_index([("username", ASCENDING), ("expires_at", DESCENDING)])

    ensure_default_admin()
    logger.info("All indexes created successfully.")


def _now():
    return datetime.now(timezone.utc)


def _ensure_fbhelper_acc_indexes(db):
    for index_name in ("user_id_1_account_id_1", "account_id_1"):
        try:
            db.fbhelper_acc.drop_index(index_name)
        except Exception:
            pass

    latest_rows = {}
    cursor = db.fbhelper_acc.find({}, {"_id": 1, "account_id": 1, "updated_at": 1}).sort("updated_at", DESCENDING)
    duplicate_ids = []
    for row in cursor:
        account_id = str(row.get("account_id") or "").strip()
        if not account_id:
            duplicate_ids.append(row["_id"])
            continue
        if account_id in latest_rows:
            duplicate_ids.append(row["_id"])
            continue
        latest_rows[account_id] = row["_id"]

    if duplicate_ids:
        db.fbhelper_acc.delete_many({"_id": {"$in": duplicate_ids}})

    db.fbhelper_acc.create_index([("account_id", ASCENDING)], unique=True)
    db.fbhelper_acc.create_index([("user_id", ASCENDING)])


def _ensure_ad_accounts_indexes(db):
    for index_name in ("user_id_1_account_id_1", "account_id_1"):
        try:
            db.ad_accounts.drop_index(index_name)
        except Exception:
            pass

    latest_rows = {}
    duplicate_ids = []
    cursor = db.ad_accounts.find(
        {},
        {"_id": 1, "account_id": 1, "user_id": 1, "source_user_ids": 1, "updated_at": 1},
    ).sort("updated_at", DESCENDING)
    for row in cursor:
        account_id = str(row.get("account_id") or "").strip()
        if not account_id:
            duplicate_ids.append(row["_id"])
            continue

        source_user_ids = []
        for value in row.get("source_user_ids") or []:
            text = str(value or "").strip()
            if text and text not in source_user_ids:
                source_user_ids.append(text)
        current_user_id = str(row.get("user_id") or "").strip()
        if current_user_id and current_user_id not in source_user_ids:
            source_user_ids.append(current_user_id)

        if account_id in latest_rows:
            latest_rows[account_id]["source_user_ids"].extend(source_user_ids)
            duplicate_ids.append(row["_id"])
            continue

        latest_rows[account_id] = {
            "_id": row["_id"],
            "source_user_ids": source_user_ids,
        }

    for summary in latest_rows.values():
        unique_users = []
        for user_id in summary["source_user_ids"]:
            if user_id and user_id not in unique_users:
                unique_users.append(user_id)
        db.ad_accounts.update_one(
            {"_id": summary["_id"]},
            {"$set": {"source_user_ids": unique_users}},
        )

    if duplicate_ids:
        db.ad_accounts.delete_many({"_id": {"$in": duplicate_ids}})

    db.ad_accounts.create_index([("account_id", ASCENDING)], unique=True)
    db.ad_accounts.create_index([("user_id", ASCENDING)])
    db.ad_accounts.create_index([("source_user_ids", ASCENDING)])


def _ensure_api_key_indexes(db):
    collection = db[API_KEY_COLLECTION]
    target_name = "key_hash_1"
    target_filter = {"key_hash": {"$type": "string"}}
    indexes = collection.index_information()

    # 兼容旧版本：早期 API Key 文档可能在明文字段 key 上建过唯一索引。
    # 现在文档只保存 key_hash，不再写入 key；如果旧索引还在，MongoDB 会把缺失值视为 null，
    # 从而在第二次插入时触发 duplicate key: { key: null }。
    for index_name, index_info in list(indexes.items()):
      if index_info.get("key") == [("key", 1)]:
          try:
              collection.drop_index(index_name)
          except Exception:
              pass
          indexes.pop(index_name, None)

    key_hash_index = indexes.get(target_name)

    if key_hash_index:
        existing_key = key_hash_index.get("key")
        is_unique = bool(key_hash_index.get("unique"))
        existing_filter = key_hash_index.get("partialFilterExpression")
        if existing_key == [("key_hash", 1)] and is_unique and existing_filter == target_filter:
            pass
        else:
            try:
                collection.drop_index(target_name)
            except Exception:
                pass

    collection.create_index(
        [("key_hash", ASCENDING)],
        unique=True,
        partialFilterExpression=target_filter,
    )
    collection.create_index([("username", ASCENDING)])


def _to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def ensure_default_admin():
    db = get_db()
    admin = db[USER_COLLECTION].find_one({"username": "admin"})
    if admin:
        patch = {}
        if not admin.get("password_hash"):
            temp_password = secrets.token_urlsafe(16)
            patch["password_hash"] = generate_password_hash(temp_password)
            logger.warning("admin 用户缺少密码，已生成随机密码（请通过运维手段重置）: %s", temp_password)
        if admin.get("role") != "admin":
            patch["role"] = "admin"
        if admin.get("status") != "active":
            patch["status"] = "active"
        if not admin.get("display_name"):
            patch["display_name"] = "System Admin"
        if patch:
            patch["updated_at"] = _now()
            db[USER_COLLECTION].update_one({"username": "admin"}, {"$set": patch})
        return

    default_password = secrets.token_urlsafe(16)
    db[USER_COLLECTION].insert_one({
        "username": "admin",
        "password_hash": generate_password_hash(default_password),
        "role": "admin",
        "status": "active",
        "display_name": "System Admin",
        "created_by": "",
        "created_at": _now(),
        "updated_at": _now(),
        "last_login_at": None,
    })
    logger.warning("首次创建 admin 用户，临时密码: %s（请尽快登录修改）", default_password)


def _token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_user_by_username(username):
    db = get_db()
    if not username:
        return None
    return db[USER_COLLECTION].find_one({"username": str(username)})


def list_users(created_by=None):
    db = get_db()
    query = {}
    if created_by is not None:
        query["created_by"] = str(created_by or "").strip()
    rows = list(db[USER_COLLECTION].find(query, {"password_hash": 0}).sort("created_at", ASCENDING))
    for row in rows:
        row.pop("_id", None)
    return rows


def create_user(username, password, role="user", status="active", display_name="", created_by=""):
    db = get_db()
    username = str(username or "").strip()
    if not username:
        raise ValueError("用户名不能为空")
    if get_user_by_username(username):
        raise ValueError("用户名已存在")
    if len(str(password or "")) < 6:
        raise ValueError("密码至少 6 位")
    role = normalize_role(role)
    status = "disabled" if status == "disabled" else "active"
    db[USER_COLLECTION].insert_one({
        "username": username,
        "password_hash": generate_password_hash(password),
        "role": role,
        "status": status,
        "display_name": str(display_name or username).strip(),
        "created_by": str(created_by or "").strip(),
        "created_at": _now(),
        "updated_at": _now(),
        "last_login_at": None,
    })
    return get_user_public(username)


def update_user(username, updates):
    db = get_db()
    username = str(username or "").strip()
    user = get_user_by_username(username)
    if not user:
        raise ValueError("用户不存在")

    payload = {"updated_at": _now()}
    if "display_name" in updates:
        payload["display_name"] = str(updates.get("display_name") or username).strip()
    if "role" in updates:
        payload["role"] = normalize_role(updates.get("role"))
    if "status" in updates:
        payload["status"] = "disabled" if updates.get("status") == "disabled" else "active"
    if updates.get("password"):
        if len(str(updates["password"])) < 6:
            raise ValueError("密码至少 6 位")
        payload["password_hash"] = generate_password_hash(updates["password"])

    db[USER_COLLECTION].update_one({"username": username}, {"$set": payload})
    return get_user_public(username)


def delete_user(username):
    db = get_db()
    username = str(username or "").strip()
    if username == "admin":
        raise ValueError("默认管理员不可删除")
    db[USER_COLLECTION].delete_one({"username": username})
    db.auth_sessions.delete_many({"username": username})
    _remove_user_from_ad_accounts(db, username)
    for col in ["ad_accounts", "bm_list", "bm_ad_accounts", "ad_account_users",
                "fbhelper_acc", "pixels", "pixel_associations", "pixel_purchase_events",
                "ad_library_items", "command_queue", "action_logs", "extension_state"]:
        if col == "ad_accounts":
            continue
        db[col].delete_many({"user_id": username})


def _remove_user_from_ad_accounts(db, username):
    db.ad_accounts.update_many(
        {"source_user_ids": username},
        {"$pull": {"source_user_ids": username}},
    )

    rows = list(db.ad_accounts.find({"user_id": username}, {"_id": 1, "source_user_ids": 1}))
    for row in rows:
        remaining_users = [str(value).strip() for value in (row.get("source_user_ids") or []) if str(value).strip()]
        if remaining_users:
            db.ad_accounts.update_one(
                {"_id": row["_id"]},
                {"$set": {"user_id": remaining_users[0], "source_user_ids": remaining_users}},
            )
        else:
            db.ad_accounts.delete_one({"_id": row["_id"]})


def verify_user_credentials(username, password):
    username = str(username or "").strip()
    password = str(password or "")
    user = get_user_by_username(username)
    if not user or user.get("status") != "active":
        return None
    if not check_password_hash(user.get("password_hash", ""), password):
        return None
    get_db()[USER_COLLECTION].update_one(
        {"username": user["username"]},
        {"$set": {"last_login_at": _now()}}
    )
    return get_user_public(user["username"])


def create_auth_session(username, client_type="extension", ttl_days=30):
    db = get_db()
    token = secrets.token_urlsafe(32)
    db.auth_sessions.insert_one({
        "username": username,
        "client_type": client_type,
        "token_hash": _token_hash(token),
        "created_at": _now(),
        "last_seen_at": _now(),
        "expires_at": _now() + timedelta(days=ttl_days),
    })
    return token


def get_user_by_token(token):
    db = get_db()
    if not token:
        return None
    session_doc = db.auth_sessions.find_one({
        "token_hash": _token_hash(token),
        "expires_at": {"$gt": _now()}
    })
    if not session_doc:
        return None
    db.auth_sessions.update_one(
        {"_id": session_doc["_id"]},
        {"$set": {"last_seen_at": _now()}}
    )
    user = get_user_by_username(session_doc["username"])
    if not user or user.get("status") != "active":
        return None
    return get_user_public(user["username"])


def delete_auth_session(token):
    if not token:
        return
    get_db().auth_sessions.delete_one({"token_hash": _token_hash(token)})


def delete_user_sessions(username):
    get_db().auth_sessions.delete_many({"username": username})


def get_user_public(username):
    user = get_user_by_username(username)
    if not user:
        return None
    user.pop("_id", None)
    user.pop("password_hash", None)
    return user


def get_user_summary(username):
    db = get_db()
    return {
        "user_id": username,
        "ad_accounts": db.ad_accounts.count_documents({
            "$or": [
                {"user_id": username},
                {"source_user_ids": username},
            ]
        }),
        "bm_count": db.bm_list.count_documents({"user_id": username}),
        "pixel_count": db.pixels.count_documents({"user_id": username}),
        "ad_library_count": db.ad_library_items.count_documents({"user_id": username}),
    }


def change_user_password(username, current_password, new_password):
    user = get_user_by_username(username)
    if not user or user.get("status") != "active":
        raise ValueError("用户不存在或已禁用")
    current_password = str(current_password or "")
    new_password = str(new_password or "")
    if not check_password_hash(user.get("password_hash", ""), current_password):
        raise ValueError("当前密码错误")
    if len(new_password) < 6:
        raise ValueError("新密码至少 6 位")
    get_db()[USER_COLLECTION].update_one(
        {"username": username},
        {"$set": {
            "password_hash": generate_password_hash(new_password),
            "updated_at": _now()
        }}
    )


def upsert_ad_account(user_id, data):
    db = get_db()
    now = _now()
    doc = {
        "user_id": user_id,
        "account_id": data.get("account_id"),
        "name": data.get("name"),
        "account_status": data.get("account_status"),
        "currency": data.get("currency"),
        "balance": data.get("balance"),
        "balance_tous": data.get("balance_tous"),
        "threshold_amount": data.get("threshold_amount"),
        "threshold_amount_tous": data.get("threshold_amount_tous"),
        "adtrust_dsl": data.get("adtrust_dsl"),
        "adtrust_dsl_tous": data.get("adtrust_dsl_tous"),
        "amount_spent": data.get("amount_spent"),
        "amount_spent_tous": data.get("amount_spent_tous"),
        "paymentcard": data.get("paymentcard"),
        "account_type": data.get("account_type"),
        "ownership": data.get("ownership"),
        "ownershipid": data.get("ownershipid"),
        "create_date": data.get("create_date"),
        "next_bill_date": data.get("next_bill_date"),
        "timezone_name": data.get("timezone_name"),
        "business_country_code": data.get("business_country_code"),
        "disable_reason": data.get("disable_reason"),
        "account_currency_ratio_to_usd": data.get("account_currency_ratio_to_usd"),
        "spend_cap": data.get("spend_cap"),
        "funding_source_details": data.get("funding_source_details"),
        "bm_id": data.get("bm_id") or (data["business"].get("id", "") if isinstance(data.get("business"), dict) else "") or (data["owner_business"].get("id", "") if isinstance(data.get("owner_business"), dict) else ""),
        "bm_name": data.get("bm_name") or (data["owner_business"].get("name", "") if isinstance(data.get("owner_business"), dict) else ""),
        "formatted_dsl": data.get("formatted_dsl", ""),
        "formatted_dsl_tous": data.get("formatted_dsl_tous", ""),
        "dsl_fetch_status": data.get("dsl_fetch_status", "success" if data.get("formatted_dsl") else ""),
        "dsl_fetch_error": data.get("dsl_fetch_error", ""),
        "dsl_fetch_attempts": data.get("dsl_fetch_attempts", 0),
        "dsl_fetch_source": data.get("dsl_fetch_source", ""),
        "owner_business_name": data.get("owner_business_name", ""),
        "raw_data": json.dumps(data, ensure_ascii=False, default=str),
        "updated_at": now,
    }
    db.ad_accounts.update_one(
        {"account_id": data.get("account_id")},
        {
            "$set": doc,
            "$addToSet": {"source_user_ids": user_id},
        },
        upsert=True,
    )
    db.fbhelper_acc.update_one(
        {"account_id": data.get("account_id")},
        {"$set": {
            "user_id": user_id,
            "account_id": data.get("account_id"),
            "name": data.get("name"),
            "account_status": data.get("account_status"),
            "currency": data.get("currency"),
            "account_dsl": _extract_account_dsl(data),
            "adtrust_dsl": data.get("adtrust_dsl"),
            "adtrust_dsl_tous": data.get("adtrust_dsl_tous"),
            "formatted_dsl": data.get("formatted_dsl", ""),
            "formatted_dsl_tous": data.get("formatted_dsl_tous", ""),
            "dsl_fetch_status": doc.get("dsl_fetch_status", ""),
            "dsl_fetch_error": doc.get("dsl_fetch_error", ""),
            "dsl_fetch_attempts": doc.get("dsl_fetch_attempts", 0),
            "dsl_fetch_source": doc.get("dsl_fetch_source", ""),
            "balance": data.get("balance"),
            "balance_tous": data.get("balance_tous"),
            "threshold_amount": data.get("threshold_amount"),
            "threshold_amount_tous": data.get("threshold_amount_tous"),
            "amount_spent": data.get("amount_spent"),
            "amount_spent_tous": data.get("amount_spent_tous"),
            "bm_id": doc.get("bm_id", ""),
            "owner_business_name": data.get("owner_business_name", ""),
            "raw_data": doc["raw_data"],
            "updated_at": now,
        }},
        upsert=True,
    )


def update_account_dsl_status(user_id, account_id, payload):
    db = get_db()
    now = _now()
    updates = {
        "updated_at": now,
    }
    allowed_fields = [
        "formatted_dsl", "formatted_dsl_tous",
        "dsl_fetch_status", "dsl_fetch_error",
        "dsl_fetch_attempts", "dsl_fetch_source",
    ]
    for field in allowed_fields:
        if field in payload:
            updates[field] = payload.get(field)

    db.ad_accounts.update_one(
        {"account_id": account_id},
        {
            "$set": updates,
            "$addToSet": {"source_user_ids": user_id},
            "$setOnInsert": {"user_id": user_id, "account_id": account_id},
        },
        upsert=True,
    )
    db.fbhelper_acc.update_one(
        {"account_id": account_id},
        {
            "$set": {
                "user_id": user_id,
                "account_id": account_id,
                "updated_at": now,
                "formatted_dsl": updates.get("formatted_dsl", ""),
                "formatted_dsl_tous": updates.get("formatted_dsl_tous", ""),
                "dsl_fetch_status": updates.get("dsl_fetch_status", ""),
                "dsl_fetch_error": updates.get("dsl_fetch_error", ""),
                "dsl_fetch_attempts": updates.get("dsl_fetch_attempts", 0),
                "dsl_fetch_source": updates.get("dsl_fetch_source", ""),
            }
        },
        upsert=True,
    )


def _extract_numeric(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    if not text:
        return None
    if text in {"不限额", "unlimited", "UNLIMITED"}:
        return -1.0
    cleaned = "".join(ch for ch in text if ch.isdigit() or ch in {".", ",", "-"})
    if not cleaned:
        return None
    try:
        return float(cleaned.replace(",", ""))
    except ValueError:
        return None


def _extract_account_dsl(data):
    raw_dsl = _extract_numeric(data.get("formatted_dsl"))
    if raw_dsl is not None:
        return round(raw_dsl, 2)
    raw_dsl = _extract_numeric(data.get("adtrust_dsl"))
    if raw_dsl is not None:
        return round(raw_dsl, 2)
    raw_dsl = _extract_numeric(data.get("formatted_dsl_tous"))
    if raw_dsl is not None:
        return round(raw_dsl, 2)
    raw_dsl = _extract_numeric(data.get("adtrust_dsl_tous"))
    if raw_dsl is not None:
        return round(raw_dsl, 2)
    return 0.0


def upsert_bm(user_id, data):
    db = get_db()
    doc = {
        "user_id": user_id,
        "bm_id": data.get("id"),
        "name": data.get("name"),
        "bmtype": data.get("bmtype", ""),
        "is_restricted": _to_bool(data.get("isRestricted")),
        "verification_status": data.get("verification_status", ""),
        "created_time": data.get("created_time", ""),
        "sharing_eligibility_status": data.get("sharing_eligibility_status", ""),
        "can_create_ad_account": _to_bool(data.get("can_create_ad_account", True)),
        "extended_credit_id": data.get("extended_credit_id", ""),
        "partner_relationships": json.dumps(data.get("partner_relationships", {}), default=str),
        "business_users": json.dumps(data.get("business_users", {}), default=str),
        "is_disabled_for_integrity": _to_bool(data.get("is_disabled_for_integrity")),
        "created_by": data.get("created_by", ""),
        "permitted_roles": data.get("permitted_roles", ""),
        "raw_data": json.dumps(data, ensure_ascii=False, default=str),
        "updated_at": _now(),
    }
    db.bm_list.update_one(
        {"user_id": user_id, "bm_id": data.get("id")},
        {"$set": doc},
        upsert=True,
    )


def upsert_bm_ad_account(user_id, bm_id, account_id, account_type="owned"):
    db = get_db()
    db.bm_ad_accounts.update_one(
        {"user_id": user_id, "bm_id": bm_id, "account_id": account_id},
        {"$set": {"user_id": user_id, "bm_id": bm_id, "account_id": account_id, "account_type": account_type}},
        upsert=True,
    )


def upsert_ad_account_user(user_id, account_id, ad_user_id, user_name="", role="", is_hidden=0, raw_data=""):
    db = get_db()
    db.ad_account_users.update_one(
        {"user_id": user_id, "account_id": account_id, "ad_user_id": ad_user_id},
        {"$set": {
            "user_id": user_id, "account_id": account_id, "ad_user_id": ad_user_id,
            "user_name": user_name, "role": role, "is_hidden": is_hidden, "raw_data": raw_data,
        }},
        upsert=True,
    )


def upsert_pixel(user_id, data):
    db = get_db()
    doc = {
        "user_id": user_id,
        "pixel_id": data.get("pixel_id"),
        "name": data.get("name", ""),
        "owner_bm_id": data.get("owner_bm_id", ""),
        "status": data.get("status", ""),
        "assigned_users": json.dumps(data.get("assigned_users", []), default=str),
        "assigned_partners": json.dumps(data.get("assigned_partners", []), default=str),
        "assigned_adaccounts": json.dumps(data.get("assigned_adaccounts", []), default=str),
        "raw_data": json.dumps(data, ensure_ascii=False, default=str),
        "updated_at": _now(),
    }
    db.pixels.update_one(
        {"user_id": user_id, "pixel_id": data.get("pixel_id")},
        {"$set": doc},
        upsert=True,
    )


def upsert_pixel_association(user_id, pixel_id, assoc_type, assoc_id, assoc_name="", raw_data=""):
    db = get_db()
    db.pixel_associations.update_one(
        {"user_id": user_id, "pixel_id": pixel_id, "assoc_type": assoc_type, "assoc_id": assoc_id},
        {"$set": {
            "user_id": user_id, "pixel_id": pixel_id, "assoc_type": assoc_type,
            "assoc_id": assoc_id, "assoc_name": assoc_name, "raw_data": raw_data,
        }},
        upsert=True,
    )


def save_pixel_purchases(user_id, pixel_id, event_data):
    db = get_db()
    db.pixel_purchase_events.delete_many({"user_id": user_id, "pixel_id": pixel_id})
    db.pixel_purchase_events.insert_one({
        "user_id": user_id,
        "pixel_id": pixel_id,
        "event_data": json.dumps(event_data, ensure_ascii=False, default=str),
        "fetched_at": _now(),
    })


def upsert_ad_library_item(user_id, data):
    db = get_db()
    doc = {
        "user_id": user_id,
        "ad_archive_id": data.get("ad_archive_id"),
        "page_id": data.get("page_id"),
        "display_format": data.get("display_format"),
        "media_type": data.get("media_type"),
        "start_date": data.get("start_date"),
        "end_date": data.get("end_date"),
        "original_image_url": data.get("original_image_url"),
        "video_hd_url": data.get("video_hd_url"),
        "raw_data": json.dumps(data, ensure_ascii=False, default=str),
        "created_at": _now(),
    }
    db.ad_library_items.update_one(
        {"user_id": user_id, "ad_archive_id": data.get("ad_archive_id")},
        {"$set": doc},
        upsert=True,
    )


def add_command(user_id, command_type, params=None):
    db = get_db()
    doc = {
        "user_id": user_id,
        "command_type": command_type,
        "params": json.dumps(params or {}, default=str),
        "status": "pending",
        "result": None,
        "created_at": _now(),
        "completed_at": None,
    }
    result = db.command_queue.insert_one(doc)
    return str(result.inserted_id)


def poll_commands(user_id):
    db = get_db()
    cursor = db.command_queue.find(
        {"user_id": user_id, "status": "pending"}
    ).sort("_id", ASCENDING).limit(5)
    results = []
    ids = []
    for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        results.append(doc)
        ids.append(doc["id"])
    if ids:
        from bson import ObjectId
        db.command_queue.update_many(
            {"_id": {"$in": [ObjectId(i) for i in ids]}},
            {"$set": {"status": "processing"}},
        )
    return results


def complete_command(cmd_id, result_data=None):
    from bson import ObjectId
    db = get_db()
    db.command_queue.update_one(
        {"_id": ObjectId(cmd_id)},
        {"$set": {
            "status": "completed",
            "result": json.dumps(result_data or {}, default=str),
            "completed_at": _now(),
        }},
    )


def set_extension_state(user_id, key, value):
    db = get_db()
    val = json.dumps(value, ensure_ascii=False, default=str) if not isinstance(value, str) else value
    db.extension_state.update_one(
        {"user_id": user_id, "key": key},
        {"$set": {"user_id": user_id, "key": key, "value": val, "updated_at": _now()}},
        upsert=True,
    )


def get_extension_state(user_id, key):
    db = get_db()
    doc = db.extension_state.find_one({"user_id": user_id, "key": key})
    if doc:
        try:
            return json.loads(doc["value"])
        except (json.JSONDecodeError, TypeError):
            return doc["value"]
    return None


def upsert_campaign(user_id, account_id, data):
    db = get_db()
    campaign_id = str(data.get("id", ""))
    if not campaign_id:
        return
    doc = {
        "user_id": user_id,
        "account_id": account_id,
        "campaign_id": campaign_id,
        "name": data.get("name", ""),
        "status": data.get("status", ""),
        "effective_status": data.get("effective_status", ""),
        "objective": data.get("objective", ""),
        "daily_budget": data.get("daily_budget", ""),
        "lifetime_budget": data.get("lifetime_budget", ""),
        "budget_remaining": data.get("budget_remaining", ""),
        "buying_type": data.get("buying_type", ""),
        "bid_strategy": data.get("bid_strategy", ""),
        "created_time": data.get("created_time", ""),
        "updated_time": data.get("updated_time", ""),
        "_source": data.get("_source", "published"),
        "updated_at": _now(),
    }
    db.campaigns.update_one(
        {"account_id": account_id, "campaign_id": campaign_id},
        {"$set": doc, "$setOnInsert": {"created_at": _now()}},
        upsert=True,
    )


API_KEY_COLLECTION = "fbhelper_api_key"


def create_api_key(username, name="", expires_days=None, scopes=None):
    """创建 API Key，返回明文 key（仅此一次可见）"""
    db = get_db()
    raw_key = "fbk_" + secrets.token_urlsafe(40)
    doc = {
        "username": username,
        "name": str(name or "").strip() or "Default",
        "key_hash": _token_hash(raw_key),
        "key_prefix": raw_key[:12],
        "scopes": scopes or ["device-control"],
        "status": "active",
        "created_at": _now(),
        "expires_at": _now() + timedelta(days=expires_days) if expires_days else None,
        "last_used_at": None,
    }
    db[API_KEY_COLLECTION].insert_one(doc)
    return {
        "key": raw_key,
        "key_prefix": doc["key_prefix"],
        "name": doc["name"],
        "scopes": doc["scopes"],
        "created_at": doc["created_at"],
        "expires_at": doc["expires_at"],
    }


def list_api_keys(username=None):
    """列出 API Keys（不含 hash），admin 不传 username 则列出全部"""
    db = get_db()
    query = {"key_hash": {"$type": "string"}}
    if username:
        query["username"] = username
    rows = list(db[API_KEY_COLLECTION].find(query).sort("created_at", ASCENDING))
    result = []
    for row in rows:
        row_username = row.get("username", "")
        result.append({
            "id": str(row["_id"]),
            "username": row_username,
            "name": row.get("name", ""),
            "key_prefix": row.get("key_prefix", ""),
            "scopes": row.get("scopes", []),
            "status": row.get("status", "active"),
            "created_at": row.get("created_at"),
            "expires_at": row.get("expires_at"),
            "last_used_at": row.get("last_used_at"),
            "is_legacy_invalid": not bool(row_username and row.get("key_hash")),
        })
    return result


def get_user_by_api_key(raw_key):
    """根据 API Key 查找用户，返回 user_public 或 None"""
    db = get_db()
    if not raw_key:
        return None
    doc = db[API_KEY_COLLECTION].find_one({
        "key_hash": _token_hash(raw_key),
        "status": "active",
    })
    if not doc:
        return None
    if not doc.get("username"):
        return None
    if doc.get("expires_at") and doc["expires_at"] < _now():
        return None
    db[API_KEY_COLLECTION].update_one(
        {"_id": doc["_id"]},
        {"$set": {"last_used_at": _now()}}
    )
    user = get_user_by_username(doc["username"])
    if not user or user.get("status") != "active":
        return None
    pub = get_user_public(doc["username"])
    if pub:
        pub["_api_key_scopes"] = doc.get("scopes", [])
        pub["_api_key_name"] = doc.get("name", "")
    return pub


def revoke_api_key(key_id, username=None):
    """撤销 API Key"""
    from bson import ObjectId
    db = get_db()
    query = {"_id": ObjectId(key_id)}
    if username:
        query["username"] = username
    result = db[API_KEY_COLLECTION].update_one(query, {"$set": {"status": "revoked"}})
    return result.modified_count > 0


def delete_api_key(key_id, username=None):
    """删除 API Key"""
    from bson import ObjectId
    db = get_db()
    query = {"_id": ObjectId(key_id)}
    if username:
        query["username"] = username
    result = db[API_KEY_COLLECTION].delete_one(query)
    return result.deleted_count > 0


def add_action_log(action, details="", user_id=""):
    db = get_db()
    db.action_logs.insert_one({
        "user_id": user_id,
        "action": action,
        "details": details if isinstance(details, str) else json.dumps(details, default=str),
        "created_at": _now(),
    })
