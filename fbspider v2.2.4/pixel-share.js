/**
 * pixel-share.js
 * Service Worker 模块 - 像素 BM 间分享 + WebSocket 中继连接
 *
 * 职责:
 * 1. 与后端 WS 中继建立连接 (ws:// 不受 HTTPS 页面限制)
 * 2. 接收 authorize_pixel 指令后调用 Facebook GraphQL API
 * 3. 从 content-pixel.js 获取页面上的 username
 */
'use strict';

// ============ WebSocket 中继连接 ============

var WS_URL = 'ws://127.0.0.1:7671';
var RECONNECT_INTERVAL = 5000;
var ws = null;
var deviceId = null;
var wsRegistered = false;

function generateDeviceId() {
  return 'px_' + Math.random().toString(36).substring(2, 10) + Date.now().toString(36).slice(-4);
}

function sendWs(msg) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(msg));
  }
}

function registerWsDevice(username) {
  sendWs({
    type: 'register',
    device_id: deviceId,
    username: username || null
  });
  wsRegistered = true;
  console.log('[PixelShare] WS 注册设备:', deviceId, '用户:', username);
}

function sendTaskResult(taskId, result) {
  sendWs({
    type: 'task_result',
    task_id: taskId,
    result: result
  });
  console.log('[PixelShare] WS 发送任务结果:', taskId, JSON.stringify(result).substring(0, 200));
}

function connectWs() {
  if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
    return;
  }

  try {
    ws = new WebSocket(WS_URL);
  } catch (e) {
    console.error('[PixelShare] WS 连接失败:', e);
    return;
  }

  ws.onopen = function () {
    console.log('[PixelShare] WS 已连接');
    // 向 content script 请求当前 username
    broadcastToContentScripts({ type: 'request_username' });
    // 先用 null 注册，等 username 回来再更新
    registerWsDevice(null);
  };

  ws.onmessage = function (event) {
    var msg;
    try {
      msg = JSON.parse(event.data);
    } catch (e) {
      return;
    }

    if (msg.action === 'authorize_pixel') {
      handleAuthorizePixel(msg.params || {}, msg.task_id);
    } else if (msg.action === 'ping') {
      // ignore
    }
  };

  ws.onclose = function () {
    console.log('[PixelShare] WS 断开，' + RECONNECT_INTERVAL / 1000 + '秒后重连');
    ws = null;
    wsRegistered = false;
    setTimeout(connectWs, RECONNECT_INTERVAL);
  };

  ws.onerror = function () {
    console.error('[PixelShare] WS 错误');
    ws = null;
    wsRegistered = false;
    setTimeout(connectWs, RECONNECT_INTERVAL);
  };
}

// 心跳
setInterval(function () {
  if (ws && ws.readyState === WebSocket.OPEN) {
    // 请求最新 username
    broadcastToContentScripts({ type: 'request_username' });
    sendWs({
      type: 'heartbeat',
      device_id: deviceId,
      username: null
    });
  }
}, 30000);

// 向 fbspider.com 标签页发送消息（请求 username 等）
function broadcastToContentScripts(msg) {
  try {
    chrome.tabs.query({ url: ['*://fbspider.com/*', '*://*.fbspider.com/*', 'http://localhost:8081/*', 'http://localhost:8082/*'] }, function (tabs) {
      for (var i = 0; i < tabs.length; i++) {
        chrome.tabs.sendMessage(tabs[i].id, msg)
          .then(function (response) {
            // 处理 request_username 的响应
            if (response && response.username) {
              currentUsername = response.username;
              if (ws && ws.readyState === WebSocket.OPEN) {
                registerWsDevice(currentUsername);
              }
            }
          })
          .catch(function () {});
      }
    });
  } catch (e) {}
}

// ============ 消息监听 (content-pixel.js ↔ background) ============

var currentUsername = null;

chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
  // content-pixel.js 上报 username
  if (message.type === 'report_username') {
    currentUsername = message.username;
    // 更新 WS 注册信息
    if (ws && ws.readyState === WebSocket.OPEN && currentUsername) {
      registerWsDevice(currentUsername);
    }
    return false;
  }

  // content-pixel.js 请求分享像素
  if (message.type === 'pixel_share' && message.action === 'share_pixel') {
    var params = message.params || {};
    handleAuthorizePixel(params, 'direct_' + Date.now())
      .then(function (result) {
        sendResponse(result);
      })
      .catch(function (err) {
        sendResponse({
          status: 'error',
          message: err.message || '分享失败',
          pixel_id: params.pixel_id,
          target_account_id: params.target_account_id
        });
      });
    return true; // 异步 sendResponse
  }

  return false;
});

// ============ Facebook GraphQL 常量 ============

var FB_GRAPHQL_URL = 'https://business.facebook.com/api/graphql/';
var DOC_ID_SHARE_MUTATION = '9104467643012543';
var FRIENDLY_NAME_SHARE = 'BizKitSettingsAddPartnerToAssetMutation';
var DOC_ID_VALIDATE = '27487406087539832';
var FRIENDLY_NAME_VALIDATE = 'BizKitSettingsAddPartnerToAssetByBusinessIDModalValidationQuery';
var DEFAULT_TASK_IDS = ['187605565181235', '430026361371672', '858333324749217', '213091122906638'];

// ============ Token 提取 ============

function extractFbTokens(html) {
  var fbDtsg = null;
  var lsd = null;
  var userId = null;
  var bmId = null;

  var dtsgPatterns = [
    /"DTSGInitData"\s*,\s*\[\]\s*,\s*\{\s*"token"\s*:\s*"([^"]+)"/,
    /"async_get_token":"([^"]+)"/,
    /name="fb_dtsg"\s+value="([^"]+)"/,
    /fb_dtsg["']\s*:\s*["']([^"']+)["']/,
    /"token":"([^"]+)".*"async"/
  ];
  for (var i = 0; i < dtsgPatterns.length; i++) {
    var m = html.match(dtsgPatterns[i]);
    if (m) { fbDtsg = m[1]; break; }
  }

  var lsdPatterns = [
    /"LSD"\s*,\s*\[\]\s*,\s*\{\s*"token"\s*:\s*"([^"]+)"/,
    /name="lsd"\s+value="([^"]+)"/,
    /"lsd":"([^"]+)"/
  ];
  for (var i = 0; i < lsdPatterns.length; i++) {
    var m = html.match(lsdPatterns[i]);
    if (m) { lsd = m[1]; break; }
  }

  var userPatterns = [
    /"c_user":(\d+)/,
    /"userID":"(\d+)"/,
    /"CURRENT_USER_ID":"(\d+)"/
  ];
  for (var i = 0; i < userPatterns.length; i++) {
    var m = html.match(userPatterns[i]);
    if (m) { userId = m[1]; break; }
  }

  var bmPatterns = [
    /"businessID":"(\d+)"/,
    /"bizID":"(\d+)"/,
    /"business_id":"(\d+)"/,
    /__bid=([^&"]+)/,
    /"actingAsBusiness":\{"id":"(\d+)"/
  ];
  for (var i = 0; i < bmPatterns.length; i++) {
    var m = html.match(bmPatterns[i]);
    if (m) { bmId = m[1]; break; }
  }

  return { fbDtsg: fbDtsg, lsd: lsd, userId: userId, bmId: bmId };
}

function getFbCookies() {
  return new Promise(function (resolve) {
    chrome.cookies.getAll({ domain: '.facebook.com' }, function (cookies) {
      var result = {};
      for (var i = 0; i < cookies.length; i++) {
        result[cookies[i].name] = cookies[i].value;
      }
      resolve(result);
    });
  });
}

function fetchFbTokensAndCookies() {
  return getFbCookies().then(function (cookies) {
    return fetch('https://business.facebook.com/', {
      method: 'GET',
      credentials: 'include'
    }).then(function (resp) {
      return resp.text();
    }).then(function (html) {
      var tokens = extractFbTokens(html);
      tokens.cookies = cookies;
      // 用 cookies 引用而不是手动拼接（浏览器会自动发送 cookie）
      tokens.cookieStr = '__use_credentials_include__';
      if (!tokens.userId && cookies.c_user) {
        tokens.userId = cookies.c_user;
      }
      console.log('[PixelShare] Token 提取: fb_dtsg=' + (tokens.fbDtsg ? 'OK' : 'FAIL') +
        ', lsd=' + (tokens.lsd ? 'OK' : 'FAIL') +
        ', userId=' + tokens.userId +
        ', bmId=' + tokens.bmId);
      return tokens;
    }).catch(function (err) {
      console.error('[PixelShare] 获取 Facebook 页面失败:', err);
      return {
        fbDtsg: null,
        lsd: null,
        userId: cookies.c_user || null,
        bmId: null,
        cookies: cookies,
        cookieStr: null
      };
    });
  });
}

// ============ Facebook GraphQL 请求 ============

function buildFormBody(tokens, friendlyName, variables, docId, businessID) {
  var params = {
    '__aaid': '0',
    '__usid': 'null',
    '__a': '1',
    '__req': 'h',
    '__hs': 'null',
    'dpr': '2',
    '__ccg': 'EXCELLENT',
    '__rev': 'null',
    '__s': 'null',
    '__hsi': 'null',
    '__dyn': 'null',
    '__csr': 'null',
    '__comet_req': '1',
    'fb_dtsg': tokens.fbDtsg,
    'jazoest': 'null',
    'lsd': tokens.lsd,
    '__spin_r': 'null',
    '__spin_b': 'null',
    '__spin_t': 'null',
    'server_timestamps': 'true',
    'av': tokens.userId,
    '__user': tokens.userId,
    '__bid': businessID,
    'fb_api_caller_class': 'RelayModern',
    'fb_api_req_friendly_name': friendlyName,
    'variables': variables,
    'doc_id': docId
  };

  return Object.keys(params).map(function (k) {
    return encodeURIComponent(k) + '=' + encodeURIComponent(params[k]);
  }).join('&');
}

function fbGraphqlRequest(tokens, formBody) {
  return fetch(FB_GRAPHQL_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'Origin': 'https://business.facebook.com',
      'Referer': 'https://business.facebook.com'
    },
    body: formBody,
    credentials: 'include'
  }).then(function (resp) {
    return resp.text();
  }).then(function (text) {
    var jsonStr = text;
    if (text.indexOf(')]}\\' + 'n') === 0) {
      jsonStr = text.substring(text.indexOf('\n') + 1);
    }
    try {
      return JSON.parse(jsonStr);
    } catch (e) {
      console.error('[PixelShare] JSON 解析失败:', text.substring(0, 500));
      throw new Error('Facebook 响应解析失败');
    }
  });
}

function sharePixelToBm(tokens, params) {
  if (!tokens.fbDtsg || !tokens.lsd) {
    return Promise.reject(new Error('缺少 fb_dtsg 或 lsd token'));
  }

  var businessID = tokens.bmId || params.business_id;
  if (!businessID) {
    return Promise.reject(new Error('缺少 businessID (BM ID)'));
  }

  var variables = JSON.stringify({
    businessID: businessID,
    assetID: params.pixel_id,
    surfaceParams: {
      entry_point: 'BIZWEB_SETTINGS_ASSETS_VIEW_DETAILS_HEADER',
      flow_source: 'BIZ_WEB',
      tab: 'EVENTS_DATASET'
    },
    toBusinessID: params.target_account_id,
    taskIDs: params.task_ids || DEFAULT_TASK_IDS
  });

  var formBody = buildFormBody(tokens, FRIENDLY_NAME_SHARE, variables, DOC_ID_SHARE_MUTATION, businessID);
  return fbGraphqlRequest(tokens, formBody);
}

// ============ 核心处理流程 ============

// 递归解析 GraphQL 响应，查找所有 error
function parseShareResult(obj) {
  if (!obj || typeof obj !== 'object') {
    return { success: false, message: '响应为空或格式异常' };
  }

  // 顶层错误
  if (obj.errors && Array.isArray(obj.errors) && obj.errors.length > 0) {
    return { success: false, message: obj.errors[0].message || JSON.stringify(obj.errors[0]) };
  }
  if (obj.error) {
    if (typeof obj.error === 'string') return { success: false, message: obj.error };
    if (typeof obj.error === 'object') return { success: false, message: obj.error.message || JSON.stringify(obj.error) };
  }

  // 检查 data 层
  if (obj.data) {
    var keys = Object.keys(obj.data);
    if (keys.length === 0) return { success: true, message: '分享操作已发送' };

    var errorMsg = null;
    for (var i = 0; i < keys.length; i++) {
      var node = obj.data[keys[i]];
      if (!node || typeof node !== 'object') continue;

      // 递归查找 status 为非成功的情况
      if (node.status === 'error' || node.status === 'ERROR') {
        errorMsg = node.status_message || node.message || JSON.stringify(node);
        break;
      }
      // 检查嵌套 error
      var nested = parseShareResult(node);
      if (!nested.success) {
        errorMsg = nested.message;
        break;
      }
    }

    if (errorMsg) return { success: false, message: errorMsg };
    return { success: true, message: '分享操作已发送' };
  }

  return { success: false, message: '未知响应格式' };
}

function handleAuthorizePixel(params, taskId) {
  console.log('[PixelShare] 开始授权: pixel_id=' + params.pixel_id + ', target_account_id=' + params.target_account_id);

  return fetchFbTokensAndCookies()
    .then(function (tokens) {
      if (!tokens.fbDtsg) {
        throw new Error('无法获取 fb_dtsg token，请确认已登录 Facebook');
      }
      if (!tokens.userId) {
        throw new Error('无法获取 Facebook 用户 ID');
      }
      if (!tokens.bmId && !params.business_id) {
        throw new Error('无法获取 BM ID，请在参数中指定 business_id');
      }

      console.log('[PixelShare] Token 获取成功: user=' + tokens.userId + ', bm=' + (tokens.bmId || params.business_id));

      return sharePixelToBm(tokens, params);
    })
    .then(function (shareResult) {
      console.log('[PixelShare] 完整响应:', JSON.stringify(shareResult).substring(0, 500));

      var parsed = parseShareResult(shareResult);

      var result = {
        status: parsed.success ? 'ok' : 'error',
        pixel_id: params.pixel_id,
        target_account_id: params.target_account_id,
        authorized: parsed.success,
        message: parsed.message
      };

      // 通过 WS 上报结果
      sendTaskResult(taskId, result);
      return result;
    })
    .catch(function (err) {
      var result = {
        status: 'error',
        pixel_id: params.pixel_id,
        target_account_id: params.target_account_id,
        message: err.message || '授权失败'
      };
      sendTaskResult(taskId, result);
      return Promise.reject(err);
    });
}

// ============ 启动 ============

deviceId = generateDeviceId();
connectWs();

console.log('[PixelShare] 模块已加载, device_id=' + deviceId);
