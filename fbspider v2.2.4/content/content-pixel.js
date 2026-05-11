(function () {
  'use strict';

  /**
   * content-pixel.js
   * 
   * 职责:
   * 1. 从页面 DOM 获取当前登录用户名
   * 2. 监听 background 请求并回复 username
   * 3. 执行 fbspider.com 的 addAccount API（像素BM间分享）
   */

  function getUsername() {
    try {
      var el = document.querySelector('.user-name, .username, [class*="user"]');
      if (el && el.textContent.trim()) return el.textContent.trim();
    } catch (e) {}
    try {
      var m = document.cookie.match(/(?:username|user_email|login_email)=([^;]+)/);
      if (m) return decodeURIComponent(m[1]);
    } catch (e) {}
    try {
      for (var i = 0; i < localStorage.length; i++) {
        var k = localStorage.key(i);
        if (/user|email|login/i.test(k)) {
          var v = localStorage.getItem(k);
          if (v && v.includes('@')) return v;
        }
      }
    } catch (e) {}
    return null;
  }

  function getUid() {
    try {
      var m = document.cookie.match(/fbspider_uid=(\d+)/);
      if (m) return m[1];
    } catch (e) {}
    try {
      var m2 = document.cookie.match(/(?:uid|user_id|userId)=(\d+)/);
      if (m2) return m2[1];
    } catch (e) {}
    try {
      var v = localStorage.getItem('uid') || localStorage.getItem('userId') || localStorage.getItem('user_id');
      if (v && /^\d+$/.test(v)) return v;
    } catch (e) {}
    return null;
  }

  function getToken() {
    try {
      var v = localStorage.getItem('token') || localStorage.getItem('auth_token') || localStorage.getItem('access_token') || localStorage.getItem('jwt');
      if (v) return v;
    } catch (e) {}
    try {
      var m = document.cookie.match(/(?:token|auth_token|access_token|jwt)=([^;]+)/);
      if (m) return m[1];
    } catch (e) {}
    return null;
  }

  function doAddAccount(params) {
    var uid = params.uid || getUid();
    if (!uid) {
      return Promise.reject(new Error('无法获取 fbspider uid'));
    }

    var token = getToken();
    if (!token) {
      return Promise.reject(new Error('无法获取 fbspider token，请确认已登录 fbspider'));
    }

    var bearerToken = token;
    if (bearerToken.indexOf('Bearer ') === 0) {
      bearerToken = bearerToken.substring(7);
    }

    var payload = {
      uid: uid,
      accountID: params.accountID,
      bmID: params.bmID,
      actionType: 'bmID'
    };

    console.log('[Pixel] 调用 addAccount:', JSON.stringify(payload), 'uid=' + uid, 'token=' + bearerToken.substring(0, 20) + '...');

    var headers = {
      'Content-Type': 'application/json',
      'uid': uid,
      'Authorization': 'Bearer ' + bearerToken
    };

    return fetch('/api/account/addAccount', {
      method: 'POST',
      headers: headers,
      credentials: 'include',
      body: JSON.stringify(payload)
    }).then(function (resp) {
      return resp.text().then(function (text) {
        console.log('[Pixel] addAccount 响应:', resp.status, text.substring(0, 500));
        try {
          var json = JSON.parse(text);
          var businessSuccess = json.status === 1 || json.status === '1';
          return { success: businessSuccess, data: json };
        } catch (e) {
          if (resp.ok) {
            return { success: true, data: text };
          }
          return { success: false, data: text };
        }
      });
    });
  }

  chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
    if (message.type === 'request_username') {
      var username = getUsername();
      var uid = getUid();
      sendResponse({ username: username, uid: uid });
    }

    if (message.type === 'addAccount') {
      doAddAccount(message.params)
        .then(function (result) {
          sendResponse(result);
        })
        .catch(function (err) {
          sendResponse({ success: false, data: err.message || 'addAccount 调用失败' });
        });
      return true;
    }

    return false;
  });

  setTimeout(function () {
    var username = getUsername();
    if (username) {
      chrome.runtime.sendMessage({
        type: 'report_username',
        username: username
      });
    }
  }, 2000);

  console.log('[Pixel] Content script 已加载（轻量模式，WS 在 background 运行）');
})();
