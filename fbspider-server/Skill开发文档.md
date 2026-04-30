
# Fbspider 像素授权 Skill 开发文档

> **文档版本**: v2.0
> **最后更新**: 2026-04-29
> **代码文件**: `fbspider-server/fbspider_pixel_authorize.py`

---

## 一、Skill 概述

### 1.1 什么是 Skill

Skill 是 OpenClaw 调用外部系统能力的封装层。本 Skill 将 fbspider-server 的像素授权 HTTP API 封装为简洁的 Python 类，供 OpenClaw 或其他 Python 程序直接调用。

### 1.2 核心能力

| 方法 | 功能 |
|------|------|
| `authorize()` | 单次像素授权并等待结果 |
| `batch_authorize()` | 批量像素授权（传列表） |
| `authorize_from_file()` | 从文本文件读取并批量授权 |
| `get_online_devices()` | 查询当前在线的浏览器插件设备 |

### 1.3 在系统中的位置

```
OpenClaw / 外部调用方
       │
       │ import FbspiderPixelAuthorize
       │ skill.authorize(pixel_id, target_bm_id, username)
       ▼
  Skill 层 (fbspider_pixel_authorize.py)
       │
       │ HTTP POST + GET 轮询
       ▼
  fbspider-server (Flask API :7150)
       │
       │ WebSocket
       ▼
  WS 中继 (:7671)
       │
       │ authorize_pixel 指令
       ▼
  浏览器插件 (pixel-share.js)
       │
       │ credentials: 'include'
       ▼
  Facebook GraphQL API
       (business.facebook.com/api/graphql/)
       │
       │ BizKitSettingsAddPartnerToAssetMutation
       ▼
  像素 BM 间分享完成
```

### 1.4 用户使用流程

用户（投手）的完整操作流程：

```
1. 准备文本文件 pixel_tasks.txt：
   ┌──────────────────────────────────┐
   │ # 像素ID,目标BM ID              │
   │ 2378488666008834,1295757529414325│
   │ 946926538242800,9876543210001234│
   │ 5555555555555555,6666666666666666│
   └──────────────────────────────────┘

2. 通过 OpenClaw 发起请求（或直接运行 Skill）

3. 系统自动完成：
   - 读取文本文件解析每一行
   - 逐个发送到后端 API
   - 后端通过 WS 转发到浏览器插件
   - 插件调用 Facebook GraphQL 执行像素分享
   - 等待每条结果后继续下一条

4. 返回汇总结果：
   总计 3, 成功 2, 失败 1
   - 第 1 条: ✅ 2378488666008834 → 1295757529414325 分享操作已发送
   - 第 2 条: ❌ 946926538242800 → 9876543210001234 你输入的是自己的业务编号
   - 第 3 条: ✅ 5555555555555555 → 6666666666666666 分享操作已发送
```

### 1.5 各组件职责

| 组件 | 职责 | 通信方式 |
|------|------|---------|
| **用户/投手** | 准备像素-BM对应关系的文本文件 | - |
| **OpenClaw** | 接收用户指令，调用 Skill | HTTP |
| **Skill** | 封装后端 API，提供 authorize/batch 方法 | HTTP → 后端 |
| **Flask 后端** | 接收 HTTP 请求，管理 API Key 认证 | HTTP + WS |
| **WS 中继** | 管理设备连接，转发指令和结果 | WebSocket |
| **浏览器插件** | 调用 Facebook GraphQL 执行实际操作 | fetch (HTTPS) |
| **Facebook** | 执行像素 BM 间分享 | GraphQL API |

---

## 二、类定义

### 2.1 FbspiderPixelAuthorize

```python
class FbspiderPixelAuthorize:
    def __init__(self, api_key: str, base_url: str = "http://47.129.247.139:7150")
```

**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `api_key` | str | 是 | - | 后端 API Key，格式 `fbk_xxxxx`，需具备 `device-control` scope |
| `base_url` | str | 否 | `http://47.129.247.139:7150` | 后端服务地址 |

**示例**：

```python
from fbspider_pixel_authorize import FbspiderPixelAuthorize

skill = FbspiderPixelAuthorize(
    api_key="fbk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    base_url="http://47.129.247.139:7150"
)
```

---

## 三、API 方法详解

### 3.1 authorize() — 单次像素授权

```python
def authorize(
    self,
    pixel_id: str,
    target_account_id: str,
    username: Optional[str] = None,
    device: Optional[str] = None,
    timeout: int = 60
) -> Dict[str, Any]
```

**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `pixel_id` | str | 是 | - | 要分享的 Facebook Pixel ID |
| `target_account_id` | str | 是 | - | 目标 BM ID（接收方） |
| `username` | str | 否 | None | 指定 fbspider 登录用户名，用于设备路由 |
| `device` | str | 否 | None | 手动指定设备 ID 前缀 |
| `timeout` | int | 否 | 60 | 等待结果的最长时间（秒） |

**返回值**：

```python
# 成功
{
    "success": True,
    "pixel_id": "2378488666008834",
    "target_account_id": "1295757529414325",
    "authorized": True,
    "message": "分享操作已发送"
}

# 失败（业务错误）
{
    "success": False,
    "pixel_id": "2378488666008834",
    "target_account_id": "1295757529414325",
    "authorized": False,
    "message": "你输入的是自己的业务编号。请检查所输入的业务编号并重试。"
}
```

### 3.2 batch_authorize() — 批量像素授权

```python
def batch_authorize(
    self,
    tasks: List[Dict[str, str]],
    username: Optional[str] = None,
    device: Optional[str] = None,
    interval: int = 2,
    timeout: int = 300
) -> Dict[str, Any]
```

**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `tasks` | List[Dict] | 是 | - | 任务列表，每项 `{"pixel_id": "xxx", "target_account_id": "yyy"}` |
| `username` | str | 否 | None | 指定用户名路由 |
| `device` | str | 否 | None | 手动指定设备 ID 前缀 |
| `interval` | int | 否 | 2 | 每条任务间隔秒数（避免 Facebook 限流） |
| `timeout` | int | 否 | 300 | 整体超时秒数 |

**返回值**：

```python
{
    "success": True,
    "total": 3,
    "success_count": 2,
    "fail_count": 1,
    "results": [
        {
            "index": 0,
            "pixel_id": "2378488666008834",
            "target_account_id": "1295757529414325",
            "task_id": "a1b2c3d4",
            "success": true,
            "authorized": true,
            "message": "分享操作已发送"
        },
        {
            "index": 1,
            "pixel_id": "946926538242800",
            "target_account_id": "1295757529414325",
            "task_id": "e5f6g7h8",
            "success": false,
            "authorized": false,
            "message": "你输入的是自己的业务编号"
        }
    ]
}
```

### 3.3 authorize_from_file() — 从文件批量授权

```python
def authorize_from_file(
    self,
    file_path: str,
    username: Optional[str] = None,
    device: Optional[str] = None,
    interval: int = 2
) -> Dict[str, Any]
```

**文件格式**：每行一对，用逗号、空格、Tab 或 `|` 分隔，`#` 开头为注释行

```
# 像素ID,目标BM ID
2378488666008834,1295757529414325
946926538242800	9876543210001234
5555555555555555 6666666666666666
```

### 3.4 get_online_devices() — 获取在线设备

```python
def get_online_devices(self) -> Dict[str, Any]
```

**返回值**：

```python
{
    "px_abc123def": {
        "tabs": [],
        "connected_at": "2026-04-29T09:40:00",
        "last_heartbeat": "2026-04-29T09:50:00",
        "username": "liaoyu354@gmail.com"
    }
}
```

---

## 四、HTTP API 端点

### 4.1 后端 API 列表

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/open/pixel/authorize` | POST | 单次像素授权 |
| `/api/open/pixel/batch_authorize` | POST | 批量像素授权 |
| `/api/open/pixel/result/{task_id}` | GET | 查询单次任务结果 |
| `/api/open/pixel/devices` | GET | 获取在线设备列表 |

### 4.2 认证

所有请求需要在 Header 中传入：

```
X-API-Key: fbk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

API Key 需要具备 `device-control` scope。

### 4.3 批量授权请求格式

```json
POST /api/open/pixel/batch_authorize
{
    "tasks": [
        {"pixel_id": "2378488666008834", "target_account_id": "1295757529414325"},
        {"pixel_id": "946926538242800", "target_account_id": "9876543210001234"}
    ],
    "username": "liaoyu354@gmail.com",
    "interval": 2
}
```

### 4.4 curl 批量授权示例

```bash
curl -s -X POST http://47.129.247.139:7150/api/open/pixel/batch_authorize \
  -H "Content-Type: application/json" \
  -H "X-API-Key: fbk_xxxxx" \
  -d '{
    "tasks": [
      {"pixel_id": "2378488666008834", "target_account_id": "1295757529414325"},
      {"pixel_id": "946926538242800", "target_account_id": "9876543210001234"}
    ],
    "interval": 2
  }'
```

---

## 五、内部实现流程

### 5.1 单次授权完整时序

```
Skill.authorize(pixel_id, target_bm_id)
  │
  ├─ POST /api/open/pixel/authorize ──→ Flask 后端
  │                                     │
  │                                     ├─ API Key 认证
  │                                     ├─ 解析设备路由
  │                                     │
  │   ← task_id ─────────────────────── │
  │                                     │
  │                                     ├─ send_command() ──→ WS 中继
  │                                                          │
  │                                                          ├─ WS 转发
  │                                                          ↓
  │                                               浏览器插件 pixel-share.js
  │                                                          │
  │                                                          ├─ fetch fb_dtsg token
  │                                                          ├─ 构造 GraphQL 请求
  │                                                          ├─ POST facebook.com/api/graphql/
  │                                                          ├─ 解析响应（递归检查 error）
  │                                                          │
  │                                                          ├─ WS task_result ──→ 中继
  │                                                                               │
  │  GET /result/{task_id} ──→ Flask ← task_results ───────────────────────────── │
  │                             │
  │  ← {status: done, result} ─│
  │
  └─ 返回格式化结果
```

### 5.2 成功判断逻辑

插件的 `parseShareResult()` 会递归检查 GraphQL 响应：

1. **顶层 `errors` 数组** → 失败
2. **顶层 `error` 对象/字符串** → 失败
3. **`data.*.status === 'error'`** → 失败
4. **`data.*` 嵌套 error** → 递归查找
5. **`data` 为空对象** → 成功（空响应视为成功）
6. **无 error 字段** → 成功

---

## 六、使用示例

### 6.1 单次授权

```python
from fbspider_pixel_authorize import FbspiderPixelAuthorize

skill = FbspiderPixelAuthorize(api_key="fbk_xxxxx")

result = skill.authorize(
    pixel_id="2378488666008834",
    target_account_id="1295757529414325",
    username="liaoyu354@gmail.com"
)

if result["success"]:
    print(f"授权成功: {result['message']}")
else:
    print(f"授权失败: {result['message']}")
```

### 6.2 批量授权

```python
tasks = [
    {"pixel_id": "2378488666008834", "target_account_id": "1295757529414325"},
    {"pixel_id": "946926538242800", "target_account_id": "9876543210001234"},
    {"pixel_id": "5555555555555555", "target_account_id": "6666666666666666"},
]

result = skill.batch_authorize(tasks, username="liaoyu354@gmail.com", interval=2)
print(f"总计: {result['total']}, 成功: {result['success_count']}, 失败: {result['fail_count']}")

for r in result['results']:
    status = "✅" if r['success'] else "❌"
    print(f"  {status} {r['pixel_id']} → {r['target_account_id']}: {r['message']}")
```

### 6.3 从文件批量授权

```python
result = skill.authorize_from_file("pixel_tasks.txt", username="liaoyu354@gmail.com")
print(result)
```

### 6.4 先查设备再授权

```python
devices = skill.get_online_devices()
if not devices:
    print("没有在线设备")
else:
    device_id = list(devices.keys())[0]
    print(f"找到设备: {device_id}, 用户: {devices[device_id]['username']}")
    result = skill.authorize(pixel_id="xxx", target_account_id="yyy", device=device_id[:6])
```

---

## 七、OpenClaw 集成指南

### 7.1 用户如何通过 OpenClaw 使用

用户在 OpenClaw 中可以：

1. **输入文本**：直接输入像素 ID 和 BM ID
2. **上传文件**：上传包含多对像素-BM关系的文本文件
3. **自然语言**：如"把像素 2378488666008834 分享给 BM 1295757529414325"

OpenClaw 解析用户意图后，调用 Skill 的对应方法：

```python
# OpenClaw 内部逻辑（伪代码）
from fbspider_pixel_authorize import FbspiderPixelAuthorize

skill = FbspiderPixelAuthorize(api_key=config.FBSPIDER_API_KEY)

# 场景 1: 用户输入单条
skill.authorize(pixel_id="2378488666008834", target_account_id="1295757529414325")

# 场景 2: 用户上传文件
skill.authorize_from_file("/tmp/uploaded_pixel_tasks.txt")

# 场景 3: 用户输入多行文本
tasks = [parse_line(line) for line in user_input.split('\n')]
skill.batch_authorize(tasks)
```

### 7.2 环境变量

| 变量名 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `FBSPIDER_API_KEY` | 否 | `fbk_xxxxx` | API Key |
| `FBSPIDER_BASE_URL` | 否 | `http://47.129.247.139:7150` | 后端服务地址 |

---

## 八、错误处理

### 8.1 常见错误

| 错误信息 | 原因 | 解决方案 |
|---------|------|---------|
| `Unauthorized` | API Key 无效 | 检查 X-API-Key 是否正确 |
| `API Key 缺少 scope: device-control` | API Key 权限不足 | 创建 Key 时指定 scopes |
| `没有在线设备` | 浏览器插件未连接 | 检查插件是否安装且 WS 已连接 |
| `无法获取 fb_dtsg token` | 未登录 Facebook | 在浏览器中登录 business.facebook.com |
| `缺少 businessID` | 无法自动获取 BM ID | 在参数中指定 business_id |
| `你输入的是自己的业务编号` | 源 BM = 目标 BM | 确认目标 BM 是接收方而非拥有方 |

### 8.2 日志前缀

| 前缀 | 来源 |
|------|------|
| `[Skill]` | Python Skill 层 |
| `[WS]` | WebSocket 中继 |
| `[PixelShare]` | 浏览器插件 |

---

## 九、注意事项

1. **API Key 安全**：不要硬编码，使用环境变量
2. **任务间隔**：批量授权默认 2 秒间隔，避免 Facebook 限流
3. **源 BM ≠ 目标 BM**：像素只能分享给**不同的 BM**
4. **浏览器必须登录**：执行前确保浏览器已登录 business.facebook.com
5. **插件必须在线**：WS 连接正常，设备已注册
6. **幂等性**：重复分享同一像素到同一 BM 不会产生副作用
