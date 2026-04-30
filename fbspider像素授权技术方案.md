# Fbspider 像素授权技术方案

> **文档版本**: v2.0（基于实际代码校验更新）
> **最后更新**: 2026-04-22
> **代码基线**: fbspider v2.2.4 + fbspider-server (当前仓库版本)

---

## 一、项目背景

### 1.1 需求概述
为了减少人工点击操作 Fbspider 进行授权像素操作，需要开发一套简易的系统，使得可以通过 OpenClaw 进行授权像素的操作。

### 1.2 前置条件
- **Fbspider 像素分享 URL**: https://fbspider.com/#/pixel/index
- **Fbspider 账户密码**: liaoyu354@gmail.com / liaoyu59@
- **测试资源**: FB 资产用于测试像素授权等内容
- **协助人员**: 01、ly

### 1.3 当前实现状态

| 模块 | 文件 | 状态 | 说明 |
|------|------|------|------|
| Flask 主应用 | `app.py` | ✅ 已完成 | 蓝图注册、SPA 托管、gzip、WS 启动 |
| 认证体系 | `auth.py` + `models.py` | ✅ 已完成 | Session/Token/API Key 三种方式 |
| WebSocket 中继 | `ws_relay.py` | ✅ 已完成 | 设备管理、指令下发、结果缓存 |
| 像素授权 API | `routes/api_pixel.py` | ✅ 已完成 | authorize / result / devices |
| 开放 API | `routes/api_open.py` | ✅ 已完成 | 广告开关、预算、导航等 |
| Skill 封装 | `fbspider_pixel_authorize.py` | ✅ 已完成 | authorize / poll / format |
| 插件通信框架 | `content/content-pixel.js` | ✅ 已完成 | WS 连接、注册、心跳、指令处理 |
| 插件授权逻辑 | `content/content-pixel.js` | ⚠️ 待填空 | API 地址和选择器需抓包确认 |
| manifest 注册 | `manifest.json` | ⚠️ 待添加 | content-pixel.js 未加入 content_scripts |
| 端到端联调 | - | ❌ 未开始 | 需真实 FB 资产测试 |

---

## 二、系统架构设计

### 2.1 整体架构图

```
┌─────────────┐         HTTP          ┌──────────────┐
│  OpenClaw   │ ──────────────────> │   Skill      │
│   (调用方)   │                       │ (API 封装层)  │
└─────────────┘                       └──────┬───────┘
                                             │ HTTP (X-API-Key)
                                             ↓
┌──────────────────────────────────────────────────────┐
│                fbspider-server                        │
│  ┌──────────────────┐  ┌──────────────────────────┐  │
│  │  Flask HTTP API  │  │  WebSocket 中继服务       │  │
│  │  Port: 7150      │  │  Port: 7671              │  │
│  │  (api_pixel.py)  │←→│  (ws_relay.py)           │  │
│  │  (api_open.py)   │  │  devices: {}             │  │
│  │  (api_keys.py)   │  │  task_results: {}        │  │
│  └──────────────────┘  └──────────┬───────────────┘  │
│                                  │                    │
│  ┌──────────────────┐            │                    │
│  │  MongoDB         │            │                    │
│  │  (plat 数据库)    │            │                    │
│  └──────────────────┘            │                    │
└──────────────────────────────────┼────────────────────┘
                                   │ WebSocket
                                   │ ws://localhost:7671
                                   ↓
                          ┌──────────────────┐
                          │  浏览器插件       │
                          │  fbspider v2.2.4  │
                          │  content-pixel.js │
                          └────────┬─────────┘
                                   │ fetch / DOM 操作
                                   ↓
                          ┌──────────────────┐
                          │  Fbspider 网站    │
                          │  fbspider.com     │
                          └──────────────────┘
```

### 2.2 技术栈选型

| 模块 | 技术栈 | 实际版本 | 说明 |
|------|--------|----------|------|
| HTTP 框架 | Flask | 3.x | `flask>=3.0` |
| WebSocket | websockets | 13.x+ | `websockets>=13.0` |
| 数据库驱动 | pymongo | 4.x+ | `pymongo>=4.0` |
| WSGI 服务器 | gunicorn + gevent | 24.x+ | `gevent>=24.0` |
| 对象存储 | minio | 7.x+ | `minio>=7.0` |
| 浏览器插件 | Chrome Extension | Manifest V3 | MV3 Service Worker |
| Skill 封装 | Python requests | - | 标准库级别 |

### 2.3 端口分配

| 端口 | 协议 | 服务 | 说明 |
|------|------|------|------|
| 7150 | HTTP | Flask API + React SPA | 对外暴露 |
| 7671 | WebSocket | 设备中继 | 监听 0.0.0.0，建议仅本地 |

---

## 三、通信协议设计

### 3.1 WebSocket 协议（插件 ↔ 后端）

#### 3.1.1 设备注册（插件 → 后端）

```json
{
  "type": "register",
  "device_id": "px_abc123def",
  "username": "liaoyu354@gmail.com"
}
```

后端收到后回复 ping 确认：
```json
{
  "action": "ping",
  "task_id": "random8char"
}
```

#### 3.1.2 心跳保活（插件 → 后端，每 30 秒）

```json
{
  "type": "heartbeat",
  "device_id": "px_abc123def",
  "username": "liaoyu354@gmail.com"
}
```

#### 3.1.3 标签页上报（插件 → 后端）

```json
{
  "type": "tab_report",
  "device_id": "px_abc123def",
  "tabs": [
    {"tab_id": 123, "url": "https://fbspider.com/#/pixel/index"}
  ]
}
```

#### 3.1.4 授权指令下发（后端 → 插件）

```json
{
  "action": "authorize_pixel",
  "task_id": "a1b2c3d4",
  "params": {
    "pixel_id": "123456789",
    "target_account_id": "act_123456789"
  }
}
```

#### 3.1.5 任务结果上报（插件 → 后端）

**成功**：
```json
{
  "type": "task_result",
  "task_id": "a1b2c3d4",
  "result": {
    "status": "ok",
    "pixel_id": "123456789",
    "target_account_id": "act_123456789",
    "authorized": true,
    "message": "像素授权成功"
  }
}
```

**失败**：
```json
{
  "type": "task_result",
  "task_id": "a1b2c3d4",
  "result": {
    "status": "error",
    "message": "当前页面不是 fbspider.com"
  }
}
```

### 3.2 HTTP API 协议（Skill ↔ 后端）

#### 3.2.1 发起授权请求

```http
POST /api/open/pixel/authorize
Content-Type: application/json
X-API-Key: fbk_xxxxx
```

请求体：
```json
{
  "pixel_id": "123456789",
  "target_account_id": "act_123456789",
  "username": "liaoyu354@gmail.com",
  "device": "px_abc"
}
```

响应：
```json
{
  "success": true,
  "task_id": "a1b2c3d4",
  "device": "px_abc123def"
}
```

#### 3.2.2 查询任务结果

```http
GET /api/open/pixel/result/{task_id}
X-API-Key: fbk_xxxxx
```

进行中：
```json
{"success": true, "status": "pending"}
```

已完成：
```json
{
  "success": true,
  "status": "done",
  "result": {
    "status": "ok",
    "pixel_id": "123456789",
    "target_account_id": "act_123456789",
    "authorized": true,
    "message": "像素授权成功"
  }
}
```

#### 3.2.3 获取在线设备列表

```http
GET /api/open/pixel/devices
X-API-Key: fbk_xxxxx
```

响应：
```json
{
  "success": true,
  "data": {
    "px_abc123def": {
      "tabs": [],
      "connected_at": "2026-04-22T10:30:00",
      "last_heartbeat": "2026-04-22T10:35:00",
      "username": "liaoyu354@gmail.com"
    }
  }
}
```

---

## 四、设备路由策略

### 4.1 路由优先级（实际代码实现）

`_resolve_device(body)` 函数在 `api_pixel.py` 和 `api_open.py` 中实现，逻辑完全一致：

| 优先级 | 参数 | 路由方式 | 代码位置 |
|--------|------|----------|----------|
| 1 | `device` | 按设备 ID 前缀匹配 `pick_device(body["device"])` | ws_relay.py:pick_device() |
| 2 | `account_id` | ad_accounts.user_id → devices.username → device_id | ws_relay.py:find_device_by_account() |
| 3 | `username` | 直接匹配 devices[did].username | ws_relay.py:find_device_by_username() |
| 4 | 无参数 | 第一个在线设备 | ws_relay.py:pick_device() |

### 4.2 用户名绑定机制

插件 `getUsername()` 通过三种方式提取当前登录用户名：

1. **DOM 元素**：`.user-name`, `.username`, `[class*="user"]`
2. **Cookie**：`username`, `user_email`, `login_email`
3. **localStorage**：键名包含 `user`/`email`/`login` 且值包含 `@` 的条目

### 4.3 设备 ID 生成规则

```javascript
'px_' + Math.random().toString(36).substring(2, 10) + Date.now().toString(36).slice(-4)
// 示例: px_k3j8m2x9m4wg
```

---

## 五、授权执行流程

### 5.1 完整流程图

```
OpenClaw Skill
     │
     │ 1. 调用 FbspiderPixelAuthorize.authorize(pixel_id, target_account_id, username)
     ▼
HTTP API (POST /api/open/pixel/authorize)
     │
     │ 2. api_key_required(scope="device-control") 鉴权
     │ 3. _resolve_device(body) 查找在线设备
     │ 4. send_command(device_id, "authorize_pixel", params) 下发指令
     │    → asyncio.run_coroutine_threadsafe() 线程安全调用
     │    → ws.send({action: "authorize_pixel", task_id, params})
     ▼
浏览器插件 (content-pixel.js → ws.onmessage)
     │
     │ 5. handleAuthorizePixel(params, taskId)
     │    ├─ 检查 location.href 是否包含 fbspider.com
     │    ├─ 检查 location.hash 是否包含 /pixel/index
     │    │   └─ 否则 window.location.hash = '#/pixel/index'，等 1.5s
     │    └─ executeAuthorization(pixelId, targetAccountId)
     │        └─ authorizeViaAPI(pixelId, targetAccountId)
     │            ├─ fetch('https://fbspider.com/api/pixel/authorize', {...})
     │            └─ credentials: 'include'（携带 Cookie）
     │
     │ 6. sendTaskResult(taskId, result)
     │    → ws.send({type: "task_result", task_id, result})
     ▼
WebSocket 中继 (ws_relay.py → _ws_handler)
     │
     │ 7. task_results[task_id] = {result, created_at}
     ▼
Skill 轮询 (GET /api/open/pixel/result/{task_id})
     │
     │ 8. 每 2 秒轮询一次，最长 60 秒
     │ 9. status == "done" 时返回结果
     ▼
OpenClaw 获得最终结果
```

### 5.2 授权实现方案

#### 方案 A: API 调用（推荐，当前默认）

**代码位置**: `content-pixel.js` → `authorizeViaAPI()`

**优点**:
- 稳定可靠，不受页面 DOM 变化影响
- 执行速度快
- 易于调试和错误处理

**当前状态**: ⚠️ TODO — API 地址和请求体需根据抓包结果更新

```javascript
// 当前代码（需要更新 TODO 部分）
var apiUrl = 'https://fbspider.com/api/pixel/authorize';  // TODO: 需抓包确认
var requestBody = {
    pixel_id: pixelId,
    target_account_id: targetAccountId
};
```

**待完成工作**:
1. 打开 fbspider.com，手动操作像素授权
2. F12 Network 抓包确认真实 API
3. 更新 `apiUrl` 和 `requestBody`

#### 方案 B: 模拟点击（备选）

**代码位置**: `content-pixel.js` → `authorizeViaClick()`

**优点**: 不依赖 API 接口
**缺点**: 依赖 DOM 结构，容易受页面更新影响

**当前状态**: ⚠️ TODO — CSS 选择器需根据实际页面确认

```javascript
// 当前代码（需要更新 TODO 部分）
var pixelInputSelector = '#pixel-id-input';          // TODO: 需确认
var accountInputSelector = '#account-id-input';       // TODO: 需确认
var authorizeButtonSelector = '#authorize-button';    // TODO: 需确认
```

---

## 六、错误处理机制

### 6.1 HTTP 错误码

| 状态码 | 场景 | 错误信息 |
|--------|------|----------|
| 400 | 缺少必填参数 | `"缺少 pixel_id"` / `"缺少 target_account_id"` |
| 401 | API Key 无效或缺失 | `"Unauthorized"` |
| 403 | API Key 缺少 scope | `"API Key 缺少 scope: device-control"` |
| 404 | 无在线设备 | `"没有在线设备"` / `"用户 xxx 没有在线设备"` |
| 500 | WebSocket 服务异常 | `"WebSocket 服务未启动"` |

### 6.2 WebSocket 重连机制

**插件端**（content-pixel.js）：
- `ws.onclose` → 5 秒后 `connect()`
- `ws.onerror` → 5 秒后 `connect()`

**服务端**（ws_relay.py）：
- `_ws_thread_target()` 包含 while True 循环
- 异常后 3 秒自动重启 WebSocket Server
- 设备断开时自动清理 `del devices[device_id]`

### 6.3 任务超时

- Skill 默认 60 秒超时
- 轮询间隔 2 秒，最多轮询 `timeout // 2` 次
- 超时返回 `{"success": false, "message": "任务超时或查询失败"}`

---

## 七、安全性设计

### 7.1 API Key 认证

- 请求头 `X-API-Key: fbk_xxxxx`
- Key 格式：`fbk_` + 40 字符随机 token
- 数据库仅存储 SHA256 哈希，明文仅创建时返回一次
- 需具备 `device-control` scope 才能访问像素授权接口
- 支持 `expires_at` 过期时间

### 7.2 WebSocket 安全

- 服务端监听 `0.0.0.0:7671`（Docker 环境需要）
- 建议通过防火墙限制 7671 端口仅内网访问
- 设备 ID 随机生成，防止冲突
- `ping_interval=30s, ping_timeout=30s` 检测死连接

### 7.3 跨域策略

- Flask CORS 配置允许所有来源访问 `/api/*`
- WebSocket `origins=None` 不限制来源

---

## 八、部署架构

### 8.1 服务器配置

| 项目 | 地址 |
|------|------|
| 应用服务器 | `47.129.247.139` |
| HTTP 端口 | `7150` |
| WebSocket 端口 | `7671` |
| MongoDB | `54.179.56.204:27017`（数据库：plat） |
| MinIO | `54.179.56.204:9000`（桶：ad-creatives） |

### 8.2 Docker 部署

```bash
cd fbspider-server
docker compose up -d --build
```

`docker-compose.yml` 配置：
- 端口映射 `7150:7150` 和 `7671:7671`
- 挂载 `callback_logs` 目录
- 环境变量覆盖 `MONGO_URI`
- `restart: unless-stopped`

### 8.3 注意事项

- **gunicorn workers 必须为 1**：WebSocket 共享状态（devices、task_results）是进程内变量
- **Dockerfile 多阶段构建**：先编译 React 前端，再构建 Python 运行时
- **WebSocket 线程模型**：独立守护线程运行 asyncio 事件循环，通过 `run_coroutine_threadsafe` 与 Flask 线程交互

---

## 九、监控与日志

### 9.1 后端日志

```
[WS] WebSocket server listening on ws://0.0.0.0:7671
[WS] 设备注册: px_abc123def (user=liaoyu354@gmail.com)
[WS] --> 已发送 [a1b2c3d4]: authorize_pixel {"pixel_id":"123456789","target_account_id":"act_123456789"}
[WS] 任务结果 [a1b2c3d4]: {"status":"ok","authorized":true,"message":"像素授权成功"}
[WS] 设备断开: px_abc123def
```

### 9.2 插件日志（浏览器 Console，前缀 `[Pixel]`）

```
[Pixel] Content script 已加载, device_id=px_abc123def
[Pixel] WebSocket 已连接
[Pixel] 注册设备: px_abc123def 用户: liaoyu354@gmail.com
[Pixel] 开始授权: pixel_id=123456789, target_account_id=act_123456789
[Pixel] 通过接口授权
[Pixel] 发送任务结果: a1b2c3d4 {status: "ok", ...}
```

---

## 十、风险评估

| 风险项 | 影响 | 概率 | 缓解措施 |
|--------|------|------|----------|
| Fbspider API 变更 | 高 | 中 | 保留模拟点击降级方案 |
| WebSocket 断连 | 中 | 低 | 双端自动重连 |
| content-pixel.js 未注册到 manifest | 高 | 确定 | 需要手动添加 content_scripts 配置 |
| API Key 泄露 | 高 | 低 | 仅存哈希、支持撤销、可设过期时间 |
| 任务结果丢失（内存） | 中 | 中 | 后续可迁移到 MongoDB |

---

## 十一、待办事项清单

### 高优先级

- [ ] 在 `manifest.json` 中添加 `content-pixel.js` 的 content_scripts 注入规则
- [ ] 抓包确认 fbspider.com 像素授权的真实 API，更新 `authorizeViaAPI()`
- [ ] 确认 fbspider.com 像素授权页面的 DOM 选择器，更新 `authorizeViaClick()`
- [ ] 验证 `getUsername()` 能否正确提取登录邮箱
- [ ] 端到端联调测试

### 中优先级

- [ ] 任务结果持久化到 MongoDB（防重启丢失）
- [ ] task_results 过期清理（避免内存泄漏）
- [ ] 批量像素授权支持

### 低优先级

- [ ] 监控面板（设备在线数、任务成功率）
- [ ] 像素权限撤销功能
- [ ] 多设备负载均衡

---

## 十二、相关文档索引

| 文档 | 位置 |
|------|------|
| 后端代码实现文档 | `fbspider-server/后端代码实现文档.md` |
| 浏览器插件开发文档 | `fbspider v2.2.4/浏览器插件开发文档.md` |
| Skill 开发文档 | `fbspider-server/Skill开发文档.md` |
| 技术交接总结 | `技术交接总结.md` |
| 广告控制 API 文档 | `fbspider-server/FbHelper_API.md` |
| 需求概述 | `fbspider像素授权需求概述.txt` |
