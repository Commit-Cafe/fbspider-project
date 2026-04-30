// API layer — replaces common.js
// Auth user & target user state is managed here as a simple module singleton.

let authUser = null;
let currentUserId = localStorage.getItem('fbhelper_user_id') || '';
let currentTargetUserId = localStorage.getItem('fbhelper_target_user_id') || '';
let authToken = localStorage.getItem('fbhelper_auth_token') || '';

export function isManagerRole(role) {
  return role === 'admin' || role === 'leader';
}

// --- getters / setters ---

export function getAuthUser() { return authUser; }
export function setAuthUser(u) { authUser = u; }
export function getAuthToken() { return authToken; }
export function setAuthToken(token) {
  authToken = String(token || '');
  if (authToken) {
    localStorage.setItem('fbhelper_auth_token', authToken);
  } else {
    localStorage.removeItem('fbhelper_auth_token');
  }
}

export function getCurrentUserId() { return currentUserId; }
export function setCurrentUserId(uid) {
  currentUserId = String(uid || '');
  localStorage.setItem('fbhelper_user_id', currentUserId);
}

export function getCurrentTargetUserId() {
  if (isManagerRole(authUser?.role)) return currentTargetUserId || '__all__';
  return authUser?.username || '';
}
export function setCurrentTargetUserId(id) {
  currentTargetUserId = id;
  localStorage.setItem('fbhelper_target_user_id', id);
}

export function hasSpecificTargetUser() {
  const t = getCurrentTargetUserId();
  return t && t !== '__all__';
}

export function canBrowseData() {
  if (isManagerRole(authUser?.role)) return true;
  return !!currentUserId;
}

export function needsFacebookConnection() {
  return !isManagerRole(authUser?.role);
}

// --- URL helper ---

function appendTargetUser(url) {
  if (!isManagerRole(authUser?.role)) return url;
  const target = getCurrentTargetUserId();
  if (!target) return url;
  return url + (url.includes('?') ? '&' : '?') + `target_user_id=${encodeURIComponent(target)}`;
}

// --- Fetch wrapper ---

async function request(method, url, data, _retries = 2) {
  const opts = { method, credentials: 'include', headers: {} };
  if (authToken) {
    opts.headers.Authorization = `Bearer ${authToken}`;
  }
  let finalUrl = url;
  if (method === 'GET') {
    finalUrl = appendTargetUser(url);
  } else if (data !== undefined) {
    const payload = { ...(data || {}) };
    if (isManagerRole(authUser?.role) && hasSpecificTargetUser()) {
      payload.target_user_id = getCurrentTargetUserId();
    }
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(payload);
  }
  try {
    const resp = await fetch(finalUrl, opts);
    return await resp.json();
  } catch (err) {
    // Retry on network errors (ERR_CONTENT_LENGTH_MISMATCH, etc.)
    if (_retries > 0) {
      await new Promise(r => setTimeout(r, 300));
      return request(method, url, data, _retries - 1);
    }
    throw err;
  }
}

const API = {
  get: (url) => request('GET', url),
  post: (url, data) => request('POST', url, data),
  put: (url, data) => request('PUT', url, data),
  delete: (url) => request('DELETE', url),
};

export default API;

// --- Extension command helper ---

export async function sendCommand(commandType, params = {}) {
  if (isManagerRole(authUser?.role) && !hasSpecificTargetUser()) {
    throw new Error('管理员/组长在"全部用户"视图下不能直接发送命令，请先选择具体用户。');
  }
  if (!isManagerRole(authUser?.role) && !currentUserId) {
    throw new Error('请先初始化连接获取 Facebook 用户信息');
  }
  return API.post('/api/commands/create', { command_type: commandType, params });
}

// --- Export URL helper for CSV download etc. ---
export { appendTargetUser };
