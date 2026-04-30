let currentPage = 1;
let currentSort = 'updated_at';
let currentOrder = 'desc';
let tokenReady = false;

// ========== Extension Communication via content-main.js ==========
// content-main.js is injected into 47.129.247.139:7150/* pages
// It listens for window.postMessage and forwards to background.js via chrome.runtime.sendMessage
// Responses come back via window.postMessage with reply type

function showStatus(msg, type = 'info') {
    const el = document.getElementById('statusAlert');
    el.className = `alert alert-${type} mb-3`;
    el.innerHTML = msg;
    el.classList.remove('d-none');
}

function hideStatus() {
    document.getElementById('statusAlert').classList.add('d-none');
}

// Listen for replies from content-main.js
window.addEventListener('message', function(event) {
    if (event.source !== window) return;

    if (event.data.type === 'contentRefreshTokenReply') {
        if (event.data.message) {
            tokenReady = true;
            document.getElementById('btnInit').classList.replace('btn-warning', 'btn-success');
            document.getElementById('btnInit').innerHTML = '<i class="fas fa-check me-1"></i>已连接';
            document.getElementById('btnFetchAll').disabled = false;
            const d = event.data.data || {};
            // Save user_id from token response (Facebook c_user)
            if (d.id) {
                setCurrentUserId(d.id);
            }
            showStatus(`<i class="fas fa-check-circle me-1"></i>Token 获取成功！用户: <strong>${d.name || d.id || 'Unknown'}</strong>，可以开始获取数据了。`, 'success');
            // Post token info to Flask
            fetch('/api/receive/token-info', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({user_id: getCurrentUserId(), timestamp: new Date().toISOString(), ...d})
            }).catch(() => {});
            // Refresh connection status
            checkConnection();
        } else {
            showStatus('<i class="fas fa-exclamation-triangle me-1"></i>Token 获取失败！请确保你已在 Chrome 中登录了 Facebook。<br>尝试打开 <a href="https://www.facebook.com" target="_blank">facebook.com</a> 登录后重试。', 'danger');
        }
    }

    if (event.data.type === 'contentgetaduserListReply') {
        const resp = event.data.message;
        if (resp && resp.success) {
            showStatus(`<i class="fas fa-check-circle me-1"></i>已获取 ${resp.data ? resp.data.length : 0} 个广告账户！数据正在写入数据库...`, 'success');
            // data is already posted to Flask by background.js postToFlask hook
            setTimeout(() => { loadStats(); loadAccounts(); hideStatus(); }, 3000);
        } else {
            showStatus(`<i class="fas fa-times-circle me-1"></i>获取账户失败: ${resp?.data || resp?.error || '未知错误'}`, 'danger');
        }
    }

    if (event.data.type === 'contentgetBmuserListReply') {
        const resp = event.data.message;
        if (resp && resp.success) {
            showStatus(`<i class="fas fa-check-circle me-1"></i>BM 列表已获取！共 ${resp.data ? resp.data.length : 0} 个 BM。`, 'success');
            setTimeout(hideStatus, 3000);
        } else {
            showStatus(`<i class="fas fa-times-circle me-1"></i>获取BM失败: ${resp?.error || '未知错误'}`, 'danger');
        }
    }

    if (event.data.type === 'contentgetVersionReply') {
        if (event.data.message) {
            tokenReady = true;
            document.getElementById('btnInit').classList.replace('btn-warning', 'btn-success');
            document.getElementById('btnInit').innerHTML = '<i class="fas fa-check me-1"></i>已连接 v' + event.data.message;
            document.getElementById('btnFetchAll').disabled = false;
        }
    }
});

function initConnection() {
    showStatus('<i class="fas fa-spinner fa-spin me-1"></i>正在初始化连接，获取 Facebook Token...（需要几秒钟）', 'warning');
    // First check version to verify extension is loaded
    window.postMessage({ type: 'callGetVersionMethod' }, '*');
    // Then request token refresh - uid "0" is fine, actual extraction uses cookies
    setTimeout(() => {
        window.postMessage({ type: 'callRefreshTokenMethod', uid: '0' }, '*');
    }, 500);
}

async function hydrateStoredConnectionState() {
    try {
        const resp = await API.get('/api/connection-state');
        if (!resp.success) return;
        const state = resp.data || {};
        if (state.fb_user_id) {
            setCurrentUserId(state.fb_user_id);
        }
        const btnInit = document.getElementById('btnInit');
        const btnFetchAll = document.getElementById('btnFetchAll');
        if (!btnInit || !btnFetchAll) return;
        if (state.has_token) {
            tokenReady = true;
            btnInit.classList.remove('btn-warning');
            btnInit.classList.add('btn-success');
            btnInit.innerHTML = `<i class="fas fa-check me-1"></i>已连接${state.fb_user_name ? ` ${state.fb_user_name}` : ''}`;
            btnFetchAll.disabled = false;
        } else {
            tokenReady = false;
            btnInit.classList.remove('btn-success');
            btnInit.classList.add('btn-warning');
            btnInit.innerHTML = '<i class="fas fa-plug me-1"></i>初始化连接';
            btnFetchAll.disabled = true;
        }
    } catch {}
}

function fetchAllAccounts() {
    if (getAuthUser()?.role === 'admin' && !hasSpecificTargetUser()) {
        showStatus('<i class="fas fa-exclamation-triangle me-1"></i>管理员请先选择一个具体用户，再发起采集命令。', 'warning');
        return;
    }
    if (!getCurrentUserId()) {
        showStatus('<i class="fas fa-exclamation-triangle me-1"></i>请先初始化连接获取 Facebook 用户信息', 'warning');
        return;
    }
    showStatus('<i class="fas fa-spinner fa-spin me-1"></i>正在获取所有数据（广告账户 + BM 列表）...这可能需要 30 秒到几分钟。', 'info');
    // Fetch ad accounts
    window.postMessage({ type: 'callGetaduserListMethod' }, '*');
    // Also fetch BM list in parallel
    setTimeout(() => {
        window.postMessage({ type: 'callGetBmuserListMethod' }, '*');
    }, 1000);
}

function fetchBMList() {
    if (getAuthUser()?.role === 'admin' && !hasSpecificTargetUser()) {
        showStatus('<i class="fas fa-exclamation-triangle me-1"></i>管理员请先选择一个具体用户，再发起采集命令。', 'warning');
        return;
    }
    if (!getCurrentUserId()) {
        showStatus('<i class="fas fa-exclamation-triangle me-1"></i>请先初始化连接获取 Facebook 用户信息', 'warning');
        return;
    }
    showStatus('<i class="fas fa-spinner fa-spin me-1"></i>正在获取 BM 列表...', 'info');
    window.postMessage({ type: 'callGetBmuserListMethod' }, '*');
}

// ========== Dashboard Table Logic ==========

async function loadStats() {
    if (!canBrowseData()) return;
    const data = await API.get('/api/stats');
    if (data.success) {
        document.getElementById('statTotal').textContent = data.data.total_accounts;
        document.getElementById('statActive').textContent = data.data.active_accounts;
        document.getElementById('statDisabled').textContent = data.data.disabled_accounts;
        document.getElementById('statBalance').textContent = data.data.total_balance_usd;
    }
}

async function loadAccounts(page) {
    if (!canBrowseData()) return;
    if (page) currentPage = page;
    const search = document.getElementById('searchInput').value;
    const url = `/api/accounts?page=${currentPage}&sort=${currentSort}&order=${currentOrder}&search=${encodeURIComponent(search)}`;
    const data = await API.get(url);
    if (!data.success) return;

    const tbody = document.getElementById('accountsBody');
    if (!data.data.length) {
        tbody.innerHTML = `<tr><td colspan="15" class="text-center text-muted py-4">
            暂无数据。请点击上方「① 初始化连接」然后「② 获取所有账户」来采集数据。
        </td></tr>`;
        document.getElementById('tableInfo').textContent = '';
        return;
    }

    tbody.innerHTML = data.data.map(a => `<tr>
        <td><small>${escapeHtml(a.user_id || '')}</small></td>
        <td><code>${escapeHtml(a.account_id)}</code></td>
        <td>${escapeHtml(a.name)}</td>
        <td>${formatStatus(a.account_status)}</td>
        <td>${escapeHtml(a.balance)}</td>
        <td>${escapeHtml(a.balance_tous)}</td>
        <td>${escapeHtml(a.amount_spent)}</td>
        <td>${escapeHtml(a.amount_spent_tous)}</td>
        <td title="本币: ${escapeHtml(a.adtrust_dsl)}&#10;门槛: ${escapeHtml(a.threshold_amount)}">${escapeHtml(a.adtrust_dsl_tous || a.adtrust_dsl)}</td>
        <td title="${escapeHtml(a.formatted_dsl || '')}">${escapeHtml(a.formatted_dsl_tous || a.formatted_dsl || '')}</td>
        <td><small>${escapeHtml(a.paymentcard)}</small></td>
        <td><small>${escapeHtml(a.account_type)}</small></td>
        <td><small>${escapeHtml(a.ownership)}</small></td>
        <td><small>${escapeHtml(a.bm_id)}</small></td>
        <td>
            <div class="btn-group btn-group-sm">
                <button class="btn btn-outline-primary" onclick="sendCommand('refresh_account',{account_id:'${a.account_id}'})" title="刷新">
                    <i class="fas fa-sync-alt"></i>
                </button>
            </div>
        </td>
    </tr>`).join('');

    document.getElementById('tableInfo').textContent =
        `显示 ${(currentPage-1)*data.per_page+1}-${Math.min(currentPage*data.per_page, data.total)} / 共 ${data.total} 条`;
    renderPagination('pagination', currentPage, data.pages, loadAccounts);
}

// Sort handlers
document.querySelectorAll('th[data-sort]').forEach(th => {
    th.addEventListener('click', () => {
        const sort = th.dataset.sort;
        if (currentSort === sort) {
            currentOrder = currentOrder === 'asc' ? 'desc' : 'asc';
        } else {
            currentSort = sort;
            currentOrder = 'asc';
        }
        loadAccounts(1);
    });
});

document.getElementById('searchInput').addEventListener('keyup', e => {
    if (e.key === 'Enter') loadAccounts(1);
});

document.addEventListener('DOMContentLoaded', () => {
    const exportBtn = document.querySelector('a[href="/api/accounts/export"]');
    const initBanner = document.getElementById('initBanner');
    if (initBanner) {
        initBanner.style.display = 'none';
    }
    if (exportBtn) {
        exportBtn.addEventListener('click', (event) => {
            event.preventDefault();
            window.location.href = appendTargetUser('/api/accounts/export');
        });
    }
});

document.addEventListener('fbhelper-auth-ready', () => {
    hydrateStoredConnectionState();
    loadStats();
    loadAccounts(1);
});

// Auto-refresh stats every 30s
setInterval(() => { loadStats(); loadAccounts(); }, 30000);

// On page load, try to detect if extension is connected
setTimeout(() => {
    window.postMessage({ type: 'callGetVersionMethod' }, '*');
}, 1000);
