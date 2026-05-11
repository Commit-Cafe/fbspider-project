import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from urllib import error, request

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from config import (
    ACCOUNT_DSL_CALLBACK_BATCH_SIZE,
    ACCOUNT_DSL_CALLBACK_ENABLED,
    ACCOUNT_DSL_CALLBACK_INTERVAL_MINUTES,
    ACCOUNT_DSL_CALLBACK_LOG_DIR,
    ACCOUNT_DSL_CALLBACK_LOG_FULL,
    ACCOUNT_DSL_CALLBACK_SECRET,
    ACCOUNT_DSL_STARTUP_REFRESH_WAIT_SECONDS,
    ACCOUNT_DSL_CALLBACK_URL,
    CURRENCY_OFFSETS,
)
from models import add_action_log, get_db
from logger import logger

_scheduler_started = False
_scheduler_lock = threading.Lock()
_instance_id = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
_account_dsl_job_id = "account_dsl_callback"
_refresh_job_id = "plugin_refresh_all_accounts"
_startup_refresh_job_id = "startup_bootstrap_refresh"
_startup_callback_job_id = "startup_bootstrap_callback"


def _is_enabled():
    return str(ACCOUNT_DSL_CALLBACK_ENABLED).strip().lower() not in {"0", "false", "no", "off"}


def _is_full_callback_log_enabled():
    return str(ACCOUNT_DSL_CALLBACK_LOG_FULL).strip().lower() not in {"0", "false", "no", "off"}


def _utc_now():
    return datetime.now(timezone.utc)


def _callback_interval_minutes():
    return max(int(ACCOUNT_DSL_CALLBACK_INTERVAL_MINUTES or 10), 1)


def _get_offset(currency):
    return CURRENCY_OFFSETS.get(str(currency or "").upper(), 100)


def _current_slot_key(now=None):
    return _current_interval_slot_key(_callback_interval_minutes(), now)


def _current_interval_slot_key(minutes, now=None):
    now = now or _utc_now()
    minute = (now.minute // minutes) * minutes
    slot = now.replace(minute=minute, second=0, microsecond=0)
    return slot.strftime("%Y-%m-%dT%H:%M:%SZ")


def _seconds_until_next_interval(minutes, now=None):
    now = now or _utc_now()
    next_run = now.replace(second=0, microsecond=0)
    remainder = now.minute % minutes
    if remainder == 0 and now.second == 0 and now.microsecond == 0:
        next_run = next_run + timedelta(minutes=minutes)
    else:
        add_minutes = minutes - remainder if remainder else minutes
        next_run = next_run + timedelta(minutes=add_minutes)
        next_run = next_run.replace(second=0, microsecond=0)
    wait_seconds = (next_run - now).total_seconds()
    return max(wait_seconds, 1)


def _parse_iso_dt(value):
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _extract_numeric(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    if text in {"不限额", "unlimited", "UNLIMITED"}:
        return -1.0
    match = re.search(r"-?\d[\d,]*\.?\d*", text)
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _normalize_account_dsl(doc):
    """Extract DSL value, preferring formatted_dsl (临时限额) over adtrust_dsl (单日限额)."""
    # Priority: formatted_dsl_tous > formatted_dsl > account_dsl > adtrust_dsl_tous > adtrust_dsl
    for field in ("formatted_dsl_tous", "formatted_dsl", "account_dsl", "adtrust_dsl_tous", "adtrust_dsl"):
        value = _extract_numeric(doc.get(field))
        if value is not None:
            return round(value, 2)

    raw_data = doc.get("raw_data")
    if raw_data:
        try:
            raw = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            raw = None
        if isinstance(raw, dict):
            # Try formatted_dsl from raw_data first
            raw_fdsl = _extract_numeric(raw.get("formatted_dsl"))
            if raw_fdsl is not None:
                return round(raw_fdsl, 2)
            raw_dsl = _extract_numeric(raw.get("adtrust_dsl"))
            if raw_dsl is not None:
                if raw_dsl == -1:
                    return -1.0
                return round(raw_dsl / _get_offset(doc.get("currency")), 2)
    return 0.0


def _load_payload():
    db = get_db()
    cursor = db.fbhelper_acc.find({}, {
        "_id": 0,
        "account_id": 1,
        "account_dsl": 1,
        "currency": 1,
        "raw_data": 1,
        "formatted_dsl": 1,
        "formatted_dsl_tous": 1,
        "adtrust_dsl": 1,
        "adtrust_dsl_tous": 1,
    })
    payload = []
    for doc in cursor:
        account_id = str(doc.get("account_id") or "").strip()
        if not account_id:
            continue
        payload.append({
            "account_id": account_id,
            "account_dsl": _normalize_account_dsl(doc),
        })
    return payload


def _post_payload(items):
    body = json.dumps({"data": items}).encode("utf-8")
    req = request.Request(
        ACCOUNT_DSL_CALLBACK_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Api-Secret": ACCOUNT_DSL_CALLBACK_SECRET,
        },
        method="POST",
    )
    with request.urlopen(req, timeout=30) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


def _safe_slot_filename(slot_key):
    return re.sub(r"[^0-9A-Za-z._-]+", "_", str(slot_key or "unknown"))


_CALLBACK_LOG_MAX_AGE_DAYS = 7
_CALLBACK_LOG_MAX_FILES = 2000
_CALLBACK_LOG_CLEANUP_INTERVAL = 20
_callback_log_write_counter = 0


def _cleanup_old_callback_logs():
    global _callback_log_write_counter
    _callback_log_write_counter += 1
    if _callback_log_write_counter % _CALLBACK_LOG_CLEANUP_INTERVAL != 0:
        return
    if not os.path.isdir(ACCOUNT_DSL_CALLBACK_LOG_DIR):
        return
    try:
        now = time.time()
        cutoff = now - _CALLBACK_LOG_MAX_AGE_DAYS * 86400
        files = []
        for fname in os.listdir(ACCOUNT_DSL_CALLBACK_LOG_DIR):
            fpath = os.path.join(ACCOUNT_DSL_CALLBACK_LOG_DIR, fname)
            if not os.path.isfile(fpath):
                continue
            try:
                mtime = os.path.getmtime(fpath)
            except OSError:
                continue
            if mtime < cutoff:
                try:
                    os.remove(fpath)
                except OSError:
                    pass
            else:
                files.append((mtime, fpath))

        if len(files) > _CALLBACK_LOG_MAX_FILES:
            files.sort(key=lambda x: x[0])
            remove_count = len(files) - _CALLBACK_LOG_MAX_FILES
            for _, fpath in files[:remove_count]:
                try:
                    os.remove(fpath)
                except OSError:
                    pass
    except Exception as exc:
        logger.error("日志清理异常: %s", exc)


def _persist_callback_log(log_data):
    if not _is_full_callback_log_enabled():
        return ""

    os.makedirs(ACCOUNT_DSL_CALLBACK_LOG_DIR, exist_ok=True)
    stamp = _utc_now().strftime("%Y%m%dT%H%M%S.%fZ")
    slot_part = _safe_slot_filename(log_data.get("slot"))
    stage_part = re.sub(r"[^0-9A-Za-z._-]+", "_", str(log_data.get("stage") or "unknown"))
    filename = f"{slot_part}_{stage_part}_{stamp}.json"
    filepath = os.path.join(ACCOUNT_DSL_CALLBACK_LOG_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2, default=str)

    _cleanup_old_callback_logs()
    return filepath


def _persist_scheduler_event(event, fields):
    os.makedirs(ACCOUNT_DSL_CALLBACK_LOG_DIR, exist_ok=True)
    stamp = _utc_now().strftime("%Y%m%dT%H%M%S.%fZ")
    event_part = re.sub(r"[^0-9A-Za-z._-]+", "_", str(event or "unknown"))
    filename = f"scheduler_{event_part}_{stamp}.json"
    filepath = os.path.join(ACCOUNT_DSL_CALLBACK_LOG_DIR, filename)
    payload = {
        "stage": f"scheduler:{event}",
        "logged_at": _utc_now().isoformat(),
        **fields,
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    return filepath


def _log_scheduler(event, **fields):
    payload = {"event": event, "instance": _instance_id}
    payload.update(fields)
    if event in {
        "started",
        "scheduler_loop_started",
        "callback_tick",
        "callback_lock_skipped",
        "callback_started",
        "scheduler_loop_error",
    }:
        try:
            payload["log_file"] = _persist_scheduler_event(event, payload)
        except Exception as exc:
            payload["log_persist_error"] = str(exc)
    logger.info("%s", json.dumps(payload, ensure_ascii=False, default=str))


def _log_callback_upload(stage, slot_key, items=None, status_code=None, response_text=None, error_text=None):
    preview = []
    if items:
        preview = items[:5]
    log_data = {
        "stage": stage,
        "slot": slot_key,
        "count": len(items or []),
        "preview": preview,
        "logged_at": _utc_now().isoformat(),
    }
    if items is not None and _is_full_callback_log_enabled():
        log_data["items"] = items
    if status_code is not None:
        log_data["status_code"] = status_code
    if response_text:
        log_data["response"] = response_text if _is_full_callback_log_enabled() else response_text[:500]
    if error_text:
        log_data["error"] = error_text if _is_full_callback_log_enabled() else error_text[:1000]

    log_file = _persist_callback_log(log_data)
    summary = dict(log_data)
    if "items" in summary:
        summary.pop("items", None)
    if log_file:
        summary["log_file"] = log_file
    logger.info("%s", json.dumps(summary, ensure_ascii=False, default=str))
    return log_file


def _acquire_slot(job_id, slot_key):
    db = get_db()
    now = _utc_now()
    lock_until = now + timedelta(minutes=25)
    try:
        doc = db.scheduled_jobs.find_one_and_update(
            {
                "_id": job_id,
                "$and": [
                    {
                        "$or": [
                            {"last_run_slot": {"$ne": slot_key}},
                            {"last_run_slot": {"$exists": False}},
                        ]
                    },
                    {
                        "$or": [
                            {"lock_until": {"$lte": now}},
                            {"lock_until": {"$exists": False}},
                        ]
                    },
                ],
            },
            {
                "$set": {
                    "last_run_slot": slot_key,
                    "lock_until": lock_until,
                    "lock_owner": _instance_id,
                    "updated_at": now,
                }
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        return False
    return bool(doc and doc.get("lock_owner") == _instance_id and doc.get("last_run_slot") == slot_key)


def _finish_slot(job_id, status, details):
    db = get_db()
    now = _utc_now()
    db.scheduled_jobs.update_one(
        {"_id": job_id, "lock_owner": _instance_id},
        {
            "$set": {
                "last_status": status,
                "last_details": details,
                "last_finished_at": now,
                "updated_at": now,
                "lock_until": now,
            }
        },
    )


def run_account_dsl_callback_job(slot_key=None, job_id=None, success_action="account_dsl_callback_success",
                                 skipped_action="account_dsl_callback_skipped",
                                 error_action="account_dsl_callback_error"):
    slot_key = slot_key or _current_slot_key()
    job_id = job_id or _account_dsl_job_id
    if not _acquire_slot(job_id, slot_key):
        _log_scheduler("callback_lock_skipped", job_id=job_id, slot=slot_key)
        return

    try:
        _log_scheduler("callback_started", job_id=job_id, slot=slot_key)
        payload = _load_payload()
        if not payload:
            details = {"slot": slot_key, "count": 0, "message": "no accounts to sync"}
            log_file = _log_callback_upload("skipped", slot_key, [])
            _finish_slot(job_id, "skipped", details)
            add_action_log(skipped_action, {**details, "log_file": log_file})
            return

        start_log_file = _log_callback_upload("start", slot_key, payload)
        batch_size = max(int(ACCOUNT_DSL_CALLBACK_BATCH_SIZE or 200), 1)
        total_sent = 0
        responses = []
        for start in range(0, len(payload), batch_size):
            batch = payload[start:start + batch_size]
            status_code, response_text = _post_payload(batch)
            total_sent += len(batch)
            batch_log_file = _log_callback_upload("batch_success", slot_key, batch, status_code=status_code, response_text=response_text)
            responses.append({
                "status_code": status_code,
                "count": len(batch),
                "response": response_text if _is_full_callback_log_enabled() else response_text[:500],
                "log_file": batch_log_file,
            })

        details = {"slot": slot_key, "count": total_sent, "batches": len(responses), "responses": responses, "start_log_file": start_log_file}
        _finish_slot(job_id, "success", details)
        add_action_log(success_action, details)
    except error.HTTPError as exc:
        error_text = exc.read().decode("utf-8", errors="replace")
        log_file = _log_callback_upload("http_error", slot_key, error_text=error_text)
        details = {
            "slot": slot_key,
            "status_code": exc.code,
            "error": error_text if _is_full_callback_log_enabled() else error_text[:1000],
            "log_file": log_file,
        }
        _finish_slot(job_id, "error", details)
        add_action_log(error_action, details)
    except Exception as exc:
        log_file = _log_callback_upload("exception", slot_key, error_text=str(exc))
        details = {"slot": slot_key, "error": str(exc), "log_file": log_file}
        _finish_slot(job_id, "error", details)
        add_action_log(error_action, details)


def _scheduler_loop():
    interval_minutes = _callback_interval_minutes()
    _log_scheduler(
        "scheduler_loop_started",
        interval_minutes=interval_minutes,
        next_tick_seconds=_seconds_until_next_interval(interval_minutes),
    )
    while True:
        try:
            interval_minutes = _callback_interval_minutes()
            wait = _seconds_until_next_interval(interval_minutes)
            _log_scheduler(
                "scheduler_sleeping",
                interval_minutes=interval_minutes,
                seconds=round(wait, 1),
                next_slot=_current_slot_key(),
            )
            time.sleep(wait)
            if _is_enabled():
                _log_scheduler("callback_tick", interval_minutes=interval_minutes, slot=_current_slot_key())
                run_account_dsl_callback_job()
        except Exception as exc:
            _log_scheduler("scheduler_loop_error", error=str(exc))
            time.sleep(60)  # prevent tight loop on persistent errors


def _list_online_users():
    db = get_db()
    now = _utc_now()
    users = []
    for doc in db.extension_state.find({"key": "heartbeat"}, {"user_id": 1, "value": 1, "_id": 0}):
        user_id = str(doc.get("user_id") or "").strip()
        if not user_id:
            continue
        try:
            heartbeat = json.loads(doc.get("value") or "{}")
        except (json.JSONDecodeError, TypeError):
            heartbeat = {}
        heartbeat_dt = _parse_iso_dt(heartbeat.get("timestamp"))
        if heartbeat_dt and (now - heartbeat_dt).total_seconds() <= 120:
            users.append(user_id)
    return users


def _has_pending_refresh_command(user_id):
    db = get_db()
    return db.command_queue.count_documents({
        "user_id": user_id,
        "command_type": "refresh_all_accounts",
        "status": {"$in": ["pending", "processing"]},
    }) > 0


def _enqueue_refresh_command(user_id, slot_key):
    db = get_db()
    now = _utc_now()
    db.command_queue.insert_one({
        "user_id": user_id,
        "command_type": "refresh_all_accounts",
        "params": json.dumps({"source": "scheduler", "slot": slot_key}, default=str),
        "status": "pending",
        "result": None,
        "created_at": now,
        "completed_at": None,
    })


def _run_refresh_all_accounts_for_slot(slot_key, job_id, success_action, error_action):
    try:
        online_users = _list_online_users()
        _log_scheduler("refresh_started", job_id=job_id, slot=slot_key, online_users=online_users)
        queued_for = []
        skipped_busy = []
        for user_id in online_users:
            if _has_pending_refresh_command(user_id):
                skipped_busy.append(user_id)
                continue
            _enqueue_refresh_command(user_id, slot_key)
            queued_for.append(user_id)

        details = {
            "slot": slot_key,
            "online_users": len(online_users),
            "queued_count": len(queued_for),
            "queued_for": queued_for,
            "skipped_busy": skipped_busy,
        }
        _finish_slot(job_id, "success", details)
        add_action_log(success_action, details)
        return details
    except Exception as exc:
        details = {"slot": slot_key, "error": str(exc)}
        _finish_slot(job_id, "error", details)
        add_action_log(error_action, details)
        return details


def run_refresh_all_accounts_job():
    slot_key = _current_interval_slot_key(10)
    if not _acquire_slot(_refresh_job_id, slot_key):
        _log_scheduler("refresh_lock_skipped", job_id=_refresh_job_id, slot=slot_key)
        return
    _run_refresh_all_accounts_for_slot(
        slot_key,
        _refresh_job_id,
        "plugin_refresh_scheduler",
        "plugin_refresh_scheduler_error",
    )


def _refresh_scheduler_loop():
    while True:
        time.sleep(_seconds_until_next_interval(10))
        if _is_enabled():
            _log_scheduler("refresh_tick", slot=_current_interval_slot_key(10))
            run_refresh_all_accounts_job()


def run_startup_bootstrap_job():
    slot_key = f"startup-{_utc_now().strftime('%Y-%m-%dT%H:%M:%SZ')}"
    if not _acquire_slot(_startup_refresh_job_id, slot_key):
        _log_scheduler("startup_lock_skipped", slot=slot_key)
        return

    _log_scheduler("startup_bootstrap_started", slot=slot_key)
    refresh_details = _run_refresh_all_accounts_for_slot(
        slot_key,
        _startup_refresh_job_id,
        "startup_refresh_scheduler",
        "startup_refresh_scheduler_error",
    )
    if refresh_details.get("error"):
        return

    wait_seconds = max(int(ACCOUNT_DSL_STARTUP_REFRESH_WAIT_SECONDS or 20), 0)
    _log_scheduler("startup_wait_before_callback", slot=slot_key, wait_seconds=wait_seconds)
    if wait_seconds:
        time.sleep(wait_seconds)

    run_account_dsl_callback_job(
        slot_key=slot_key,
        job_id=_startup_callback_job_id,
        success_action="startup_account_dsl_callback_success",
        skipped_action="startup_account_dsl_callback_skipped",
        error_action="startup_account_dsl_callback_error",
    )


def start_scheduler():
    global _scheduler_started
    if not _is_enabled():
        _log_scheduler("disabled")
        return

    with _scheduler_lock:
        if _scheduler_started:
            return
        dsl_thread = threading.Thread(target=_scheduler_loop, name="account-dsl-callback-scheduler", daemon=True)
        refresh_thread = threading.Thread(target=_refresh_scheduler_loop, name="plugin-refresh-scheduler", daemon=True)
        startup_thread = threading.Thread(target=run_startup_bootstrap_job, name="startup-bootstrap-scheduler", daemon=True)
        dsl_thread.start()
        refresh_thread.start()
        startup_thread.start()
        _scheduler_started = True
        _log_scheduler("started")
