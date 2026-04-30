// Listen for BM list reply
window.addEventListener('message', function(event) {
    if (event.source !== window) return;
    if (event.data.type === 'contentgetBmuserListReply') {
        const resp = event.data.message;
        if (resp && resp.success) {
            showToast(`BM 列表已获取 (${resp.data ? resp.data.length : 0} 个)`, 'success');
            setTimeout(loadBMs, 2000);
        } else {
            showToast('获取BM失败', 'error');
        }
    }
});

function refreshBMFromExtension() {
    if (getAuthUser()?.role === 'admin' && !hasSpecificTargetUser()) {
        showToast('管理员请先选择一个具体用户，再发起 BM 采集。', 'error');
        return;
    }
    if (getAuthUser()?.role !== 'admin' && !getCurrentUserId()) {
        showToast('请先在 Dashboard 页初始化 Facebook 连接', 'error');
        return;
    }
    sendCommand('refresh_bm_list').then(result => {
        if (result?.success) {
            showToast('BM 刷新命令已发送，稍后自动刷新列表', 'info');
            setTimeout(loadBMs, 4000);
        }
    });
}

async function loadBMs() {
    if (!canBrowseData()) {
        document.getElementById('bmList').innerHTML = `<div class="text-center py-3">
            <p class="text-muted">请先在 <a href="/dashboard">Dashboard</a> 页初始化连接并获取数据</p>
        </div>`;
        return;
    }
    const data = await API.get('/api/bms');
    const container = document.getElementById('bmList');
    if (!data.success || !data.data.length) {
        container.innerHTML = `<div class="text-center py-3">
            <p class="text-muted">暂无BM数据</p>
            <button class="btn btn-primary btn-sm" onclick="refreshBMFromExtension()">
                <i class="fas fa-download me-1"></i>从 Facebook 获取
            </button>
        </div>`;
        return;
    }
    container.innerHTML = data.data.map(bm => `
        <div class="bm-list-item" onclick="selectBM('${bm.bm_id}', this)">
            <div class="fw-bold">${escapeHtml(bm.name)}</div>
            <div class="d-flex justify-content-between">
                <small class="text-muted">${escapeHtml(bm.bm_id)}</small>
                <small>${bm.is_restricted ? '<span class="badge bg-danger">受限</span>' : '<span class="badge bg-success">正常</span>'}</small>
            </div>
            <small class="text-muted">${bm.account_count || 0} 个广告账户</small>
        </div>
    `).join('');
}

async function selectBM(bmId, el) {
    document.querySelectorAll('.bm-list-item').forEach(e => e.classList.remove('active'));
    if (el) el.classList.add('active');

    const [bmData, accountsData] = await Promise.all([
        API.get(`/api/bms/${bmId}`),
        API.get(`/api/bms/${bmId}/accounts`)
    ]);

    if (!bmData.success) return;
    const bm = bmData.data;
    document.getElementById('bmDetailTitle').textContent = bm.name || bmId;

    let usersHtml = '';
    try {
        const users = JSON.parse(bm.business_users || '{}');
        if (users.data && users.data.length) {
            usersHtml = `<h6 class="mt-3">用户/角色</h6>
                <table class="table table-sm data-table"><thead><tr><th>ID</th><th>名称</th><th>角色</th></tr></thead><tbody>
                ${users.data.map(u => `<tr><td>${escapeHtml(u.id)}</td><td>${escapeHtml(u.name)}</td><td>${escapeHtml(u.role)}</td></tr>`).join('')}
                </tbody></table>`;
        }
    } catch {}

    let accountsHtml = '';
    if (accountsData.success && accountsData.data.length) {
        accountsHtml = `<h6 class="mt-3">旗下广告账户 (${accountsData.data.length})</h6>
            <table class="table table-sm data-table"><thead><tr>
                <th>账户ID</th><th>名称</th><th>状态</th><th>余额</th><th>类型</th>
            </tr></thead><tbody>
            ${accountsData.data.map(a => `<tr>
                <td><code>${escapeHtml(a.account_id)}</code></td>
                <td>${escapeHtml(a.name)}</td>
                <td>${formatStatus(a.account_status)}</td>
                <td>${escapeHtml(a.balance)}</td>
                <td><small>${escapeHtml(a.bm_account_type)}</small></td>
            </tr>`).join('')}
            </tbody></table>`;
    }

    document.getElementById('bmDetail').innerHTML = `
        <div class="row mb-3">
            <div class="col-md-6">
                <table class="table table-sm">
                    <tr><td class="text-muted">BM ID</td><td><code>${escapeHtml(bm.bm_id)}</code></td></tr>
                    <tr><td class="text-muted">类型</td><td>${escapeHtml(bm.bmtype)}</td></tr>
                    <tr><td class="text-muted">状态</td><td>${bm.is_restricted ? '<span class="text-danger">受限</span>' : '<span class="text-success">正常</span>'}</td></tr>
                    <tr><td class="text-muted">验证状态</td><td>${escapeHtml(bm.verification_status)}</td></tr>
                </table>
            </div>
            <div class="col-md-6">
                <table class="table table-sm">
                    <tr><td class="text-muted">创建时间</td><td>${escapeHtml(bm.created_time)}</td></tr>
                    <tr><td class="text-muted">共享资格</td><td>${escapeHtml(bm.sharing_eligibility_status)}</td></tr>
                    <tr><td class="text-muted">可创建广告账户</td><td>${bm.can_create_ad_account ? '是' : '否'}</td></tr>
                </table>
            </div>
        </div>
        ${usersHtml}
        ${accountsHtml}
    `;
}

document.addEventListener('fbhelper-auth-ready', () => {
    loadBMs();
});
