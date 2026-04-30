# API Key 广告控制接口文档

本文档说明如何通过 `API Key` 调用开放接口，对 Facebook Ads Manager 中的广告对象执行：

- 广告开关
- 预算调整

接口基础路径使用：

```text
http://47.129.247.139:7150/api/open
```

鉴权方式使用请求头：

```http
X-API-Key: fbk_xxxxx
```

接口为异步任务模式：

1. 调用控制接口，返回 `task_id`
2. 使用 `task_id` 查询执行结果


## 1. 认证说明

所有开放接口都要求在 Header 中传入：

```http
X-API-Key: fbk_xxxxx
```

该 API Key 需要具备 `device-control` scope，否则会返回：

```json
{
  "success": false,
  "message": "API Key 缺少 scope: device-control"
}
```


## 2. 自动路由说明

广告开关和预算调整默认走自动路由，不需要指定 `username`。

系统的设备选择优先级如下：

1. `device`
用途：手动指定某台在线设备，传设备 ID 前缀即可

2. `account_id`
用途：按广告账户自动路由到可操作该账户的在线设备

3. `username`
用途：按用户绑定的在线设备路由

4. 不传以上字段
用途：回退到第一台在线设备

对于广告相关接口，推荐只传：

- `account_id`
- `ad_type`
- `ad_id`

这样系统会自动：

1. 选择可操作该账户的在线设备
2. 切换到对应 Ads Manager 账户页
3. 自动定位到对应层级页面
4. 执行广告开关或预算修改


## 3. 支持的广告层级

`ad_type` 支持以下值：

- `ad`
- `ads`
- `adset`
- `adsets`
- `campaign`
- `campaigns`

系统内部会自动标准化为：

- `ads`
- `adsets`
- `campaigns`


## 4. 获取在线设备

用于调试当前有哪些在线设备。

### 请求

```http
GET /api/open/devices
X-API-Key: fbk_xxxxx
```

### 示例

```bash
curl -sS \
  -H "X-API-Key: fbk_xxxxx" \
  http://47.129.247.139:7150/api/open/devices
```

### 响应示例

```json
{
  "success": true,
  "data": {
    "8b76c5a1b0f2d9aa": {
      "username": "alice",
      "tabs": [
        {
          "tab_id": 123,
          "url": "https://adsmanager.facebook.com/adsmanager/manage/ads?act=1131759048702766"
        }
      ]
    }
  }
}
```


## 5. 广告开关接口

用于开启或暂停广告对象。

### 请求

```http
POST /api/open/toggle
X-API-Key: fbk_xxxxx
Content-Type: application/json
```

### 请求体字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `account_id` | string | 是 | 广告账户 ID，同时用于自动路由 |
| `ad_type` | string | 是 | 对象层级：`ad` / `adset` / `campaign` |
| `ad_id` | string | 是 | 目标广告对象 ID |
| `enable` | boolean | 否 | `true` 为开启，`false` 为暂停，默认 `false` |
| `device` | string | 否 | 手动指定设备 ID 前缀；一般不需要 |
| `username` | string | 否 | 指定用户名路由；一般不需要 |

### 开启广告示例

```bash
curl -sS \
  -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: fbk_xxxxx" \
  -d '{
    "account_id": "1131759048702766",
    "ad_type": "ad",
    "ad_id": "120239041899480461",
    "enable": true
  }' \
  http://47.129.247.139:7150/api/open/toggle
```

### 暂停广告示例

```bash
curl -sS \
  -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: fbk_xxxxx" \
  -d '{
    "account_id": "1131759048702766",
    "ad_type": "ad",
    "ad_id": "120239041899480461",
    "enable": false
  }' \
  http://47.129.247.139:7150/api/open/toggle
```

### 响应示例

```json
{
  "success": true,
  "task_id": "54b5d149",
  "device": "8b76c5a1b0f2d9aa"
}
```


## 6. 修改预算接口

用于修改广告、广告组或广告系列预算。

### 请求

```http
POST /api/open/budget
X-API-Key: fbk_xxxxx
Content-Type: application/json
```

### 请求体字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `account_id` | string | 是 | 广告账户 ID，同时用于自动路由 |
| `ad_type` | string | 是 | 对象层级：`ad` / `adset` / `campaign` |
| `ad_id` | string | 是 | 目标对象 ID |
| `budget` | string / number | 是 | 要设置的预算值 |
| `device` | string | 否 | 手动指定设备 ID 前缀；一般不需要 |
| `username` | string | 否 | 指定用户名路由；一般不需要 |

### 请求示例

```bash
curl -sS \
  -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: fbk_xxxxx" \
  -d '{
    "account_id": "1131759048702766",
    "ad_type": "ad",
    "ad_id": "120239041899480461",
    "budget": "35"
  }' \
  http://47.129.247.139:7150/api/open/budget
```

### 响应示例

```json
{
  "success": true,
  "task_id": "e4d272d8",
  "device": "8b76c5a1b0f2d9aa"
}
```


## 7. 查询任务结果

广告控制接口是异步执行的，拿到 `task_id` 后需要轮询结果。

### 请求

```http
GET /api/open/result/<task_id>
X-API-Key: fbk_xxxxx
```

### 查询示例

```bash
curl -sS \
  -H "X-API-Key: fbk_xxxxx" \
  http://47.129.247.139:7150/api/open/result/54b5d149
```

### 未完成示例

```json
{
  "success": true,
  "status": "pending"
}
```

### 完成示例

```json
{
  "success": true,
  "status": "done",
  "result": {
    "status": "ok",
    "data": {
      "ad_id": "120239041899480461",
      "action": "pause",
      "result": "paused",
      "was": "active",
      "now": "paused"
    }
  }
}
```

### 预算修改完成示例

```json
{
  "success": true,
  "status": "done",
  "result": {
    "status": "ok",
    "data": {
      "ad_id": "120239041899480461",
      "action": "set_budget",
      "budget": "35",
      "result": "ok"
    }
  }
}
```


## 8. 常见错误

### 401 未认证

```json
{
  "success": false,
  "message": "Unauthorized"
}
```

原因：

- 没有传 `X-API-Key`
- API Key 不存在或已失效

### 403 无权限

```json
{
  "success": false,
  "message": "API Key 缺少 scope: device-control"
}
```

### 404 无法自动路由

```json
{
  "success": false,
  "message": "没有在线设备"
}
```

或：

```json
{
  "success": false,
  "message": "用户 alice 没有在线设备"
}
```

或：

```json
{
  "success": false,
  "message": "没有匹配 abcd 的在线设备"
}
```

### 400 参数缺失

```json
{
  "success": false,
  "message": "缺少 account_id"
}
```


## 9. 推荐调用方式

对于第三方系统，推荐的最小请求体如下。

### 暂停广告

```json
{
  "account_id": "1131759048702766",
  "ad_type": "ad",
  "ad_id": "120239041899480461",
  "enable": false
}
```

### 开启广告

```json
{
  "account_id": "1131759048702766",
  "ad_type": "ad",
  "ad_id": "120239041899480461",
  "enable": true
}
```

### 调整预算

```json
{
  "account_id": "1131759048702766",
  "ad_type": "ad",
  "ad_id": "120239041899480461",
  "budget": "35"
}
```

默认不需要传：

- `username`
- `device`

只要提供 `account_id`，系统就会优先按广告账户自动路由。


## 10. JavaScript 调用示例

```js
const API_KEY = "fbk_xxxxx";
const BASE = "http://47.129.247.139:7150/api/open";

async function pauseAd() {
  const res = await fetch(`${BASE}/toggle`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": API_KEY,
    },
    body: JSON.stringify({
      account_id: "1131759048702766",
      ad_type: "ad",
      ad_id: "120239041899480461",
      enable: false,
    }),
  });

  const data = await res.json();
  if (!data.success) {
    throw new Error(data.message || "toggle failed");
  }

  return data.task_id;
}

async function waitTask(taskId, maxRetry = 20) {
  for (let i = 0; i < maxRetry; i++) {
    const res = await fetch(`${BASE}/result/${taskId}`, {
      headers: {
        "X-API-Key": API_KEY,
      },
    });
    const data = await res.json();
    if (data.status === "done") {
      return data.result;
    }
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
  throw new Error("task timeout");
}
```


## 11. 注意事项

1. `account_id` 对广告控制接口是必填项。
2. 默认推荐使用自动路由，不要固定写死 `username`。
3. `task_id` 只代表任务已下发，不代表页面操作已经成功。
4. 最终是否执行成功，以 `/api/open/result/<task_id>` 返回内容为准。
5. 预算修改和广告开关依赖在线插件设备，以及该设备当前 Facebook 登录态有效。
