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

// 支持通过 chrome.storage.local 覆盖 WS 地址
(function resolveWsUrl() {
  try {
    chrome.storage.local.get(['wsUrl'], function (items) {
      if (items && items.wsUrl) {
        WS_URL = items.wsUrl;
        console.log('[PixelShare] WS URL 已覆盖:', WS_URL);
      }
    });
  } catch (e) {}
})();
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
    } else if (msg.action === 'share_pixel_to_ad_account') {
      handleSharePixelToAdAccount(msg.params || {}, msg.task_id);
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
      username: currentUsername || null
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
    // 跳过自己发出的 fbspider 原版请求，避免循环
    if (message._source === 'pixel-share') return false;
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

// BM 间分享
var DOC_ID_SHARE_MUTATION = '9104467643012543';
var FRIENDLY_NAME_SHARE = 'BizKitSettingsAddPartnerToAssetMutation';
var DOC_ID_VALIDATE = '27487406087539832';
var FRIENDLY_NAME_VALIDATE = 'BizKitSettingsAddPartnerToAssetByBusinessIDModalValidationQuery';
var DEFAULT_TASK_IDS = ['187605565181235', '430026361371672', '858333324749217', '213091122906638'];

// 像素分享给广告账户
var DOC_ID_SHARE_TO_AD_ACCOUNT = '26864782103106185';
var FRIENDLY_NAME_SHARE_TO_AD_ACCOUNT = 'BizKitSettingsBulkAddAssetToAssetConnectionMutation';
var CONNECTED_ASSET_TYPES = ['AD_ACCOUNT', 'BUSINESS_RESOURCE_GROUP'];

// 像素搜索（Dataset ID / 名称 → 真实 asset ID）
var DOC_ID_SEARCH_PIXEL = '8487572748017556';
var FRIENDLY_NAME_SEARCH_PIXEL = 'BusinessToolsAssignAssetsToPartnersAssetListContainerQuery';

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

function validateSharePixel(tokens, params) {
  var businessID = params.business_id || tokens.bmId;
  var variables = JSON.stringify({
    businessID: businessID,
    assetID: params.pixel_id,
    surfaceParams: {
      entry_point: 'BIZWEB_SETTINGS_ASSETS_VIEW_DETAILS_HEADER',
      flow_source: 'BIZ_WEB',
      tab: 'EVENTS_DATASET'
    },
    toBusinessID: params.target_account_id
  });

  var formBody = buildFormBody(tokens, FRIENDLY_NAME_VALIDATE, variables, DOC_ID_VALIDATE, businessID);
  return fbGraphqlRequest(tokens, formBody);
}

function sharePixelToBm(tokens, params) {
  if (!tokens.fbDtsg || !tokens.lsd) {
    return Promise.reject(new Error('缺少 fb_dtsg 或 lsd token'));
  }

  var businessID = params.business_id || tokens.bmId;
  if (!businessID) {
    return Promise.reject(new Error('缺少 businessID (BM ID)'));
  }
  console.log('[PixelShare] 使用 businessID=' + businessID + (params.business_id ? ' (指定)' : ' (自动检测)'));

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

// 搜索像素真实 asset ID（Dataset ID 或名称 → Facebook asset ID）
function searchPixelAssetId(tokens, params) {
  var businessID = params.business_id || tokens.bmId;
  if (!businessID) {
    return Promise.reject(new Error('缺少 businessID，无法搜索像素'));
  }

  // searchTerm：优先用 pixel_name，其次用 pixel_id 作为搜索词
  var searchTerm = params.pixel_name || params.pixel_id;
  if (!searchTerm) {
    return Promise.reject(new Error('缺少 pixel_name 或 pixel_id，无法搜索'));
  }

  var variables = JSON.stringify({
    businessID: businessID,
    assetTypes: ['EVENTS_DATASET_NEW'],
    searchTerm: searchTerm,
    assetVariantToFilter: null,
    orderBy: null
  });

  console.log('[PixelShare] 搜索像素 asset ID: searchTerm=' + searchTerm + ', bm=' + businessID);

  var formBody = buildFormBody(tokens, FRIENDLY_NAME_SEARCH_PIXEL, variables, DOC_ID_SEARCH_PIXEL, businessID);
  return fbGraphqlRequest(tokens, formBody)
    .then(function (searchResult) {
      console.log('[PixelShare] 搜索响应:', JSON.stringify(searchResult).substring(0, 800));

      // 从响应中提取像素列表
      var assets = [];
      try {
        var data = searchResult.data || {};
        // 支持的字段名: assets, business_assets, connected_objects
        var collectionNames = ['assets', 'business_assets', 'connected_objects'];
        var keys = Object.keys(data);
        for (var i = 0; i < keys.length; i++) {
          var node = data[keys[i]];
          for (var ci = 0; ci < collectionNames.length; ci++) {
            var coll = node && node[collectionNames[ci]];
            if (coll && coll.edges) {
              for (var j = 0; j < coll.edges.length; j++) {
                if (coll.edges[j].node) {
                  assets.push(coll.edges[j].node);
                }
              }
            }
          }
          // 也检查 node 本身是否包含嵌套对象（如 data.business.connected_objects）
          if (node && typeof node === 'object') {
            var subKeys = Object.keys(node);
            for (var si = 0; si < subKeys.length; si++) {
              var subNode = node[subKeys[si]];
              for (var ci2 = 0; ci2 < collectionNames.length; ci2++) {
                var subColl = subNode && subNode[collectionNames[ci2]];
                if (subColl && subColl.edges) {
                  for (var j2 = 0; j2 < subColl.edges.length; j2++) {
                    if (subColl.edges[j2].node) {
                      assets.push(subColl.edges[j2].node);
                    }
                  }
                }
              }
            }
          }
        }
      } catch (e) {}

      if (assets.length === 0) {
        console.log('[PixelShare] 搜索未找到像素，返回 null');
        return null;
      }

      // 统一取名称字段：business_object_name 优先，其次 name / label
      function getAssetName(a) {
        return a.business_object_name || a.name || a.label || '';
      }

      // 精确匹配：id 或 name 匹配
      var matched = null;
      for (var i = 0; i < assets.length; i++) {
        var a = assets[i];
        var aName = getAssetName(a);
        // id 匹配（用 assetID 或 id 字段）
        var aId = a.assetID || a.id;
        if (String(aId) === String(searchTerm) || String(aId) === String(params.pixel_id)) {
          matched = a;
          break;
        }
        // 名称精确匹配
        if (aName && params.pixel_name && aName === params.pixel_name) {
          matched = a;
          break;
        }
      }

      // 没有精确匹配，取第一个
      if (!matched) {
        matched = assets[0];
      }

      var matchedId = matched.assetID || matched.id;
      var matchedName = getAssetName(matched);
      console.log('[PixelShare] 搜索结果: id=' + matchedId + ', name=' + matchedName);
      return {
        asset_id: matchedId,
        name: matchedName,
        all_assets: assets.map(function (a) { return { id: a.assetID || a.id, name: getAssetName(a) }; })
      };
    });
}

// 像素分享给广告账户（fromAssetID）
function sharePixelToAdAccount(tokens, params) {
  if (!tokens.fbDtsg || !tokens.lsd) {
    return Promise.reject(new Error('缺少 fb_dtsg 或 lsd token'));
  }

  var businessID = params.business_id || tokens.bmId;
  if (!businessID) {
    return Promise.reject(new Error('缺少 businessID (BM ID)'));
  }

  // toAssetIDs 支持数组（批量）和单个字符串
  var targetIds = params.target_account_ids;
  if (!targetIds) {
    // 兼容单个 target_account_id
    if (params.target_account_id) {
      targetIds = [params.target_account_id];
    } else {
      return Promise.reject(new Error('缺少 target_account_id 或 target_account_ids'));
    }
  } else if (typeof targetIds === 'string') {
    targetIds = [targetIds];
  }

  var variables = JSON.stringify({
    businessID: businessID,
    fromAssetID: params.pixel_id,
    toAssetIDs: targetIds,
    connectedAssetTypes: CONNECTED_ASSET_TYPES
  });

  console.log('[PixelShare] 分享像素给广告账户: pixel=' + params.pixel_id + ', accounts=' + JSON.stringify(targetIds) + ', bm=' + businessID);

  var formBody = buildFormBody(tokens, FRIENDLY_NAME_SHARE_TO_AD_ACCOUNT, variables, DOC_ID_SHARE_TO_AD_ACCOUNT, businessID);
  return fbGraphqlRequest(tokens, formBody);
}

// ============ 核心处理流程 ============

// 递归查找 GraphQL 响应中所有 message/error_summary 类字段
function extractFbMessages(obj, depth) {
  var messages = [];
  if (!obj || typeof obj !== 'object') return messages;
  if (depth && depth > 8) return messages;

  if (obj.message && typeof obj.message === 'string' && obj.message.length > 5) {
    messages.push(obj.message);
  }
  if (obj.error_summary && typeof obj.error_summary === 'string') {
    messages.push(obj.error_summary);
  }
  if (obj.title && typeof obj.title === 'string' && obj.title.length > 2) {
    messages.push(obj.title);
  }

  var keys = Object.keys(obj);
  for (var i = 0; i < keys.length; i++) {
    var val = obj[keys[i]];
    if (val && typeof val === 'object') {
      if (Array.isArray(val)) {
        for (var j = 0; j < val.length; j++) {
          var nested = extractFbMessages(val[j], (depth || 0) + 1);
          messages = messages.concat(nested);
        }
      } else {
        var nested = extractFbMessages(val, (depth || 0) + 1);
        messages = messages.concat(nested);
      }
    }
  }
  return messages;
}

// 递归解析 GraphQL 响应，查找所有 error
function parseShareResult(obj, depth) {
  if (!obj || typeof obj !== 'object') {
    return { success: true, message: '分享操作已发送' };
  }
  if (!depth) depth = 0;
  if (depth > 10) return { success: true, message: '分享操作已发送' };

  // 顶层 errors 数组
  if (obj.errors && Array.isArray(obj.errors) && obj.errors.length > 0) {
    return { success: false, message: obj.errors[0].message || JSON.stringify(obj.errors[0]) };
  }
  // error 字段
  if (obj.error) {
    if (typeof obj.error === 'string') return { success: false, message: obj.error };
    if (typeof obj.error === 'object' && Object.keys(obj.error).length > 0) {
      return { success: false, message: obj.error.message || JSON.stringify(obj.error) };
    }
  }
  // result_type 字段（Facebook GraphQL 用 result_type 标识成功/失败）
  if (obj.result_type) {
    if (obj.result_type === 'FAILURE' || obj.result_type === 'FAILED' || obj.result_type === 'ERROR') {
      return { success: false, message: obj.message || obj.error_message || ('操作失败: result_type=' + obj.result_type + ', asset=' + (obj.asset_id || 'unknown')) };
    }
    if (obj.result_type === 'SUCCESS' || obj.result_type === 'OK') {
      return { success: true, message: '分享成功' };
    }
  }
  // status 明确为失败
  if (obj.status === 'error' || obj.status === 'ERROR' || obj.status === 'FAILURE') {
    return { success: false, message: obj.status_message || obj.message || '操作失败' };
  }
  // status 明确为成功
  if (obj.status === 'success' || obj.status === 'SUCCESS' || obj.status === 'OK') {
    return { success: true, message: obj.status_message || obj.message || '分享操作已发送' };
  }

  // 有 data 字段 → 检查每个子节点
  if (obj.data) {
    var keys = Object.keys(obj.data);
    if (keys.length === 0) return { success: true, message: '分享操作已发送' };

    for (var i = 0; i < keys.length; i++) {
      var node = obj.data[keys[i]];
      if (!node || typeof node !== 'object') continue;
      var nested = parseShareResult(node, depth + 1);
      if (!nested.success) return nested;
    }
    // 所有子节点都没报错 → 成功
    return { success: true, message: '分享操作已发送' };
  }

  // 递归检查所有子属性（非 data 层）
  var subKeys = Object.keys(obj);
  for (var i = 0; i < subKeys.length; i++) {
    var val = obj[subKeys[i]];
    if (val && typeof val === 'object' && !Array.isArray(val)) {
      var nested = parseShareResult(val, depth + 1);
      if (!nested.success) return nested;
    }
  }

  // 没找到任何错误 → 成功
  return { success: true, message: '分享操作已发送' };
}

function handleAuthorizePixel(params, taskId) {
  console.log('[PixelShare] 开始授权: pixel_id=' + params.pixel_id + ', target_account_id=' + params.target_account_id);

  // 优先使用 fbspider 原版分享接口（通过 background.js）
  return shareViaFbspider(params, taskId)
    .catch(function (err) {
      console.log('[PixelShare] 原版接口失败，尝试 GraphQL:', err.message);
      // 原版接口失败时，回退到 GraphQL
      return shareViaGraphql(params, taskId);
    });
}

// 处理像素分享给广告账户（支持自动查询真实 asset ID）
function handleSharePixelToAdAccount(params, taskId) {
  console.log('[PixelShare] 开始分享像素给广告账户: pixel_id=' + params.pixel_id +
    ', pixel_name=' + (params.pixel_name || '') +
    ', target_account_ids=' + JSON.stringify(params.target_account_ids || [params.target_account_id]));

  return fetchFbTokensAndCookies()
    .then(function (tokens) {
      if (!tokens.fbDtsg) {
        throw new Error('无法获取 fb_dtsg token，请确认已登录 Facebook');
      }
      if (!tokens.userId) {
        throw new Error('无法获取 Facebook 用户 ID');
      }

      // 判断是否需要查询真实 asset ID
      // 如果传了 pixel_asset_id（已是真实 ID），直接用；否则搜索
      var shareParams = Object.assign({}, params);

      if (params.pixel_asset_id) {
        // 方案 A：用户直接提供了真实 asset ID
        console.log('[PixelShare] 使用提供的 pixel_asset_id=' + params.pixel_asset_id);
        shareParams.pixel_id = params.pixel_asset_id;
        return doShareToAdAccount(tokens, shareParams, taskId);
      } else {
        // 方案 B：搜索真实 asset ID
        return searchPixelAssetId(tokens, params)
          .then(function (searchResult) {
            if (!searchResult) {
              throw new Error('未找到像素的真实 ID，请提供 pixel_name 或 pixel_asset_id');
            }

            if (searchResult.all_assets.length > 1) {
              console.log('[PixelShare] 搜索到多个像素，使用第一个匹配: ' +
                searchResult.asset_id + ' (' + searchResult.name + ')');
            }

            shareParams.pixel_id = searchResult.asset_id;
            console.log('[PixelShare] 使用搜索到的真实 asset ID: ' + searchResult.asset_id +
              ' (' + searchResult.name + ')');

            return doShareToAdAccount(tokens, shareParams, taskId);
          });
      }
    })
    .catch(function (err) {
      var result = {
        status: 'error',
        pixel_id: params.pixel_id,
        target_account_ids: params.target_account_ids || [params.target_account_id],
        message: err.message || '分享给广告账户失败'
      };
      sendTaskResult(taskId, result);
      return result;
    });
}

// 实际执行分享给广告账户
function doShareToAdAccount(tokens, params, taskId) {
  return sharePixelToAdAccount(tokens, params)
    .then(function (shareResult) {
      console.log('[PixelShare] 广告账户分享响应:', JSON.stringify(shareResult).substring(0, 500));

      var parsed = parseShareResult(shareResult);

      var result = {
        status: parsed.success ? 'ok' : 'error',
        pixel_id: params.pixel_id,
        pixel_name: params.pixel_name || '',
        target_account_ids: params.target_account_ids || [params.target_account_id],
        authorized: parsed.success,
        message: parsed.message
      };

      if (!parsed.success) {
        var sourceBm = params.business_id || tokens.bmId || '未知';
        result.message = '像素分享给广告账户失败';
        if (parsed.message) {
          result.message += '：' + parsed.message;
        }
        result.message += ' [像素: ' + params.pixel_id + ', BM: ' + sourceBm + ']';
      } else {
        result.message = '像素已成功分享给广告账户';
      }

      sendTaskResult(taskId, result);
      return result;
    });
}

// 方案一：通过 fbspider 原版分享接口（background.js → fbspider 远程服务器）
function shareViaFbspider(params, taskId) {
  return new Promise(function (resolve, reject) {
    // 原版 content-main.js 调用: {action: 'callSharePixelScript', pixelId, bm}
    chrome.runtime.sendMessage({
      action: 'callSharePixelScript',
      pixelId: params.pixel_id,
      bm: params.target_account_id
    }, function (response) {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      if (!response) {
        reject(new Error('background.js 无响应'));
        return;
      }
      
      console.log('[PixelShare] 原版接口响应:', JSON.stringify(response).substring(0, 500));

      // 判断结果
      var success = false;
      var message = '';

      if (typeof response === 'string') {
        message = response;
        success = response.indexOf('成功') !== -1 || response.indexOf('success') !== -1;
      } else if (typeof response === 'object') {
        message = response.message || response.msg || JSON.stringify(response);
        success = response.success === true || response.status === 'ok' || 
                  (message && message.indexOf('成功') !== -1);
      }

      if (success) {
        resolve({
          status: 'ok',
          pixel_id: params.pixel_id,
          target_account_id: params.target_account_id,
          authorized: true,
          message: message
        });
      } else {
        // 业务失败时 reject，触发 GraphQL 回退
        reject(new Error(message || '原版接口返回失败'));
      }
    });
  });
}

// 方案二：直接调用 Facebook GraphQL API
function shareViaGraphql(params, taskId) {
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

      // 先执行验证查询，获取 Facebook 的预检结果
      return validateSharePixel(tokens, params).then(function (validateResult) {
        var validateStr = JSON.stringify(validateResult);
        console.log('[PixelShare] 验证响应:', validateStr);

        // 从验证响应中提取错误信息（用于辅助翻译）
        var validateError = '';
        var validateParsed = parseShareResult(validateResult);
        if (!validateParsed.success) {
          validateError = validateParsed.message;
        }
        // 也从深层提取 message
        var validateMessages = extractFbMessages(validateResult);
        var allErrorText = validateError + ' ' + validateMessages.join(' ');

        // 执行实际分享
        return sharePixelToBm(tokens, params).then(function (shareResult) {
          var fullStr = JSON.stringify(shareResult);
          console.log('[PixelShare] 分享响应:', fullStr);

          // 提取已有合作伙伴信息
          var alreadyShared = false;
          var partnerNames = [];
          try {
            var conn = shareResult.data &&
              shareResult.data.business_settings_add_partner_to_asset_connection;
            if (conn && conn.business_asset) {
              var lists = [
                conn.business_asset.fullControlPartnerAgencies,
                conn.business_asset.partialAccessPartnerAgencies,
                conn.business_asset.pendingPartnerAgencies
              ];
              for (var li = 0; li < lists.length; li++) {
                var list = lists[li];
                if (list && list.edges) {
                  for (var i = 0; i < list.edges.length; i++) {
                    var node = list.edges[i].node;
                    if (node) {
                      var label = li === 2 ? '[待确认]' : '';
                      partnerNames.push(label + node.name + '(' + node.id + ')');
                      if (String(node.id) === String(params.target_account_id)) {
                        alreadyShared = true;
                      }
                    }
                  }
                }
              }
            }
          } catch (e) {}

          var parsed = parseShareResult(shareResult);

          // 如果 FAILURE 但目标 BM 已在合作伙伴列表中，视为成功
          if (!parsed.success && alreadyShared) {
            console.log('[PixelShare] 虽返回 FAILURE，但目标 BM 已在合作伙伴列表中，视为已授权');
            parsed = {
              success: true,
              message: '目标 BM 已拥有该像素权限（无需重复分享）'
            };
          }

          // 翻译技术错误为友好的中文信息
          if (!parsed.success) {
            var sourceBm = params.business_id || tokens.bmId;

            // 从响应中提取像素名称
            var pixelName = '';
            try {
              var asset = shareResult.data &&
                shareResult.data.business_settings_add_partner_to_asset_connection &&
                shareResult.data.business_settings_add_partner_to_asset_connection.business_asset;
              if (asset && asset.business_object_name) {
                pixelName = asset.business_object_name;
              }
            } catch (e) {}

            // 合并分享响应 + 验证响应的错误文本，用于全面匹配
            var combinedMessage = parsed.message + ' ' + allErrorText;

            // 源BM = 目标BM → 自己分享给自己
            if (String(sourceBm) === String(params.target_account_id)) {
              parsed.message = '所属BM与目标BM相同，无法分享给自己。请检查所输入的业务编号并重试。';
            }
            // GraphQL 返回 missing_required_variable_value / noncoercible_argument_value
            else if (combinedMessage.indexOf('missing_required_variable_value') !== -1 ||
                     combinedMessage.indexOf('noncoercible_argument_value') !== -1) {
              parsed.message = '当前BM受限，该BM的像素无法分享';
              if (pixelName) parsed.message += '（像素: ' + pixelName + '）';
              parsed.message += ' [源BM: ' + sourceBm + ', 目标BM: ' + params.target_account_id + ']';
            }
            // result_type=FAILURE → 统一翻译为 BM 受限
            else {
              parsed.message = '当前BM受限，该BM的像素无法分享';
              if (pixelName) parsed.message += '（像素: ' + pixelName + '）';
              parsed.message += ' [源BM: ' + sourceBm + ', 目标BM: ' + params.target_account_id + ']';
            }

            // 补充合作伙伴信息
            if (partnerNames.length > 0) {
              parsed.message += ' | 当前合作伙伴: ' + partnerNames.join(', ');
            }
          }

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
        });
      });
    })
    .catch(function (err) {
      var result = {
        status: 'error',
        pixel_id: params.pixel_id,
        target_account_id: params.target_account_id,
        message: err.message || '授权失败'
      };
      sendTaskResult(taskId, result);
      // resolve 而非 reject，确保调用者（WS 指令 / content script）能正常处理
      return result;
    });
}

// ============ 启动 ============

deviceId = generateDeviceId();
connectWs();

console.log('[PixelShare] 模块已加载, device_id=' + deviceId);
