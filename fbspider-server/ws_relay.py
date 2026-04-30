"""
WebSocket 中继服务器
- 管理 auto-click 插件的 WebSocket 连接
- 维护设备列表和标签页信息
- 维护 username ↔ device 映射
- 提供指令下发和结果查询接口
- 与 Flask 主应用共享数据（通过模块级变量）

独立线程运行，不影响 Flask HTTP 服务。
"""
import asyncio
import json
import uuid
import threading
from datetime import datetime

import websockets.exceptions

# ============ 共享状态 ============
# 已连接的设备: device_id -> { ws, tabs, connected_at, username }
devices = {}
# 任务结果缓存: task_id -> { result, created_at }
task_results = {}

_ws_loop = None
_ws_thread = None
_ws_started = False

WS_PORT = 7671


# ============ WebSocket Handler ============

async def _ws_handler(websocket):
    device_id = None
    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if msg.get("type") == "register":
                device_id = msg["device_id"]
                username = msg.get("username") or None
                existing = devices.get(device_id)
                if existing and existing.get("ws") is websocket:
                    # 同一连接重复注册，仅更新 username
                    old_user = existing.get("username")
                    existing["username"] = username
                    if old_user != username:
                        print(f"[WS] 设备 {device_id} 用户变更: {old_user} -> {username}")
                else:
                    devices[device_id] = {
                        "ws": websocket,
                        "tabs": [],
                        "connected_at": datetime.utcnow().isoformat(),
                        "username": username,
                    }
                    print(f"[WS] 设备注册: {device_id} (user={username})")
                await websocket.send(json.dumps({
                    "action": "ping",
                    "task_id": str(uuid.uuid4())[:8],
                }))

            elif msg.get("type") == "heartbeat":
                if device_id and device_id in devices:
                    devices[device_id]["last_heartbeat"] = datetime.utcnow().isoformat()
                    # 心跳也可能携带更新后的 username
                    if msg.get("username"):
                        devices[device_id]["username"] = msg["username"]

            elif msg.get("type") == "tab_report":
                if device_id and device_id in devices:
                    devices[device_id]["tabs"] = msg.get("tabs", [])

            elif msg.get("type") == "task_result":
                task_id = msg.get("task_id")
                result = msg.get("result", {})
                print(f"[WS] 任务结果 [{task_id}]: {json.dumps(result, ensure_ascii=False)}")
                task_results[task_id] = {
                    "result": result,
                    "created_at": datetime.utcnow().isoformat(),
                }

    except websockets.exceptions.ConnectionClosed:
        pass  # normal disconnect, no need to log
    except Exception as e:
        print(f"[WS] 连接异常: {e}")
    finally:
        if device_id and device_id in devices:
            del devices[device_id]
            print(f"[WS] 设备断开: {device_id}")


# ============ 指令发送 ============

def pick_device(device_id_prefix=None):
    """按前缀匹配设备，无前缀则返回第一个"""
    if not devices:
        return None
    if not device_id_prefix:
        return list(devices.keys())[0]
    for did in devices:
        if did.startswith(device_id_prefix):
            return did
    return None


def find_device_by_username(username):
    """根据登录用户名查找设备，返回 device_id 或 None"""
    if not username:
        return None
    for did, dev in devices.items():
        if dev.get("username") == username:
            return did
    return None


def find_device_by_account(account_id):
    """
    根据广告账户 ID 自动查找设备：
    account_id → ad_accounts.user_id → devices[?].username → device_id
    """
    from models import get_db
    db = get_db()
    doc = db.ad_accounts.find_one({"account_id": str(account_id)}, {"user_id": 1})
    if not doc or not doc.get("user_id"):
        return None, None, f"账户 {account_id} 未找到或未绑定用户"

    username = doc["user_id"]
    device_id = find_device_by_username(username)
    if not device_id:
        return None, username, f"用户 {username} 没有在线设备"

    return device_id, username, None


async def _async_send_command(device_id, action, params):
    dev = devices.get(device_id)
    if not dev:
        return None, f"设备 {device_id} 不在线"
    task_id = str(uuid.uuid4())[:8]
    msg = {"action": action, "task_id": task_id, "params": params}
    await dev["ws"].send(json.dumps(msg))
    print(f"[WS] --> 已发送 [{task_id}]: {action} {json.dumps(params, ensure_ascii=False)}")
    return task_id, None


def send_command(device_id, action, params):
    """
    线程安全的指令发送（从 Flask 线程调用）。
    返回 (task_id, error_msg)。
    """
    if _ws_loop is None:
        return None, "WebSocket 服务未启动"
    future = asyncio.run_coroutine_threadsafe(
        _async_send_command(device_id, action, params), _ws_loop
    )
    return future.result(timeout=5)


def get_task_result(task_id):
    """查询任务结果"""
    entry = task_results.get(task_id)
    if entry is None:
        return None
    return entry["result"]


def list_devices():
    """列出所有在线设备及其标签页和绑定用户"""
    result = {}
    for did, dev in devices.items():
        result[did] = {
            "tabs": dev.get("tabs", []),
            "connected_at": dev.get("connected_at"),
            "last_heartbeat": dev.get("last_heartbeat"),
            "username": dev.get("username"),
        }
    return result


# ============ 启动 ============

async def _run_ws_server():
    from websockets.asyncio.server import serve
    async with serve(
        _ws_handler,
        "0.0.0.0",
        WS_PORT,
        origins=None,
        ping_interval=30,
        ping_timeout=30,
        close_timeout=5,
        max_size=2**20,
    ):
        print(f"[WS] WebSocket server listening on ws://0.0.0.0:{WS_PORT}")
        await asyncio.Future()  # run forever


def _ws_thread_target():
    global _ws_loop
    while True:
        try:
            _ws_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_ws_loop)
            _ws_loop.run_until_complete(_run_ws_server())
        except Exception as exc:
            print(f"[WS] server crashed: {exc}")
        finally:
            try:
                if _ws_loop and not _ws_loop.is_closed():
                    _ws_loop.close()
            except Exception:
                pass
            _ws_loop = None
        print("[WS] retrying server startup in 3 seconds")
        threading.Event().wait(3)


def start_ws_server():
    """在独立守护线程中启动 WebSocket 服务"""
    global _ws_thread, _ws_started
    if _ws_started and _ws_thread and _ws_thread.is_alive():
        return
    _ws_thread = threading.Thread(target=_ws_thread_target, name="ws-relay-server", daemon=True)
    _ws_thread.start()
    _ws_started = True
