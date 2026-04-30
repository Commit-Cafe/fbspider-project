(function () {
  'use strict';

  /**
   * content-pixel.js
   * 
   * 职责:
   * 1. 从页面 DOM 获取当前登录用户名
   * 2. 监听 background 请求并回复 username
   * 3. WebSocket 连接和像素分享逻辑全部由 background (pixel-share.js) 处理
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

  // 监听来自 background 的消息
  chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
    if (message.type === 'request_username') {
      var username = getUsername();
      sendResponse({ username: username });
    }
    return false;
  });

  // 页面加载后立即上报一次 username
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
