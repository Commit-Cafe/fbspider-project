async function loadSettings() {
    // DB Stats
    const dbData = await API.get('/api/db-stats');
    if (dbData.success) {
        const stats = dbData.data;
        document.getElementById('dbStats').innerHTML = `<table class="table table-sm mb-0">
            ${Object.entries(stats).map(([k, v]) => `<tr><td class="text-muted">${k}</td><td><strong>${v}</strong></td></tr>`).join('')}
        </table>`;
    }

    // Connection status
    try {
        const [statsData, connData] = await Promise.all([
            API.get('/api/stats'),
            API.get('/api/connection-state')
        ]);
        const conn = connData.success ? (connData.data || {}) : {};
        document.getElementById('connStatus').innerHTML = `
            <table class="table table-sm mb-0">
                <tr><td class="text-muted">服务器状态</td><td><span class="badge bg-success">运行中</span></td></tr>
                <tr><td class="text-muted">系统账号</td><td><code>${getAuthUser()?.username || '-'}</code></td></tr>
                <tr><td class="text-muted">Facebook 用户</td><td><code>${conn.fb_user_id || '-'}</code></td></tr>
                <tr><td class="text-muted">Facebook 名称</td><td>${escapeHtml(conn.fb_user_name || '-')}</td></tr>
                <tr><td class="text-muted">Token 状态</td><td>${conn.has_token ? '<span class="badge bg-success">已获取</span>' : '<span class="badge bg-warning text-dark">未获取</span>'}</td></tr>
                <tr><td class="text-muted">插件心跳</td><td>${conn.heartbeat_ok ? '<span class="badge bg-success">在线</span>' : '<span class="badge bg-secondary">离线</span>'}</td></tr>
                <tr><td class="text-muted">最近 Token 时间</td><td><small>${escapeHtml(conn.last_token_time || '-')}</small></td></tr>
                <tr><td class="text-muted">总账户数</td><td>${statsData.data.total_accounts}</td></tr>
                <tr><td class="text-muted">BM 数量</td><td>${statsData.data.bm_count}</td></tr>
                <tr><td class="text-muted">Pixel 数量</td><td>${statsData.data.pixel_count}</td></tr>
                <tr><td class="text-muted">素材数量</td><td>${statsData.data.ad_library_count}</td></tr>
            </table>
        `;
    } catch {
        document.getElementById('connStatus').innerHTML = '<span class="badge bg-danger">服务器未响应</span>';
    }

    // Token info
    try {
        const connData = await API.get('/api/connection-state');
        const conn = connData.success ? (connData.data || {}) : {};
        document.getElementById('tokenInfo').innerHTML = `
            <table class="table table-sm mb-0">
                <tr><td class="text-muted">是否已获取 Token</td><td>${conn.has_token ? '是' : '否'}</td></tr>
                <tr><td class="text-muted">Facebook 用户 ID</td><td><code>${conn.fb_user_id || '-'}</code></td></tr>
                <tr><td class="text-muted">Facebook 用户名</td><td>${escapeHtml(conn.fb_user_name || '-')}</td></tr>
                <tr><td class="text-muted">最近 Token 时间</td><td><small>${escapeHtml(conn.last_token_time || '-')}</small></td></tr>
                <tr><td class="text-muted">最近心跳</td><td><small>${escapeHtml(conn.last_heartbeat || '-')}</small></td></tr>
            </table>
        `;
    } catch {
        document.getElementById('tokenInfo').innerHTML = `<p class="text-muted small">暂时无法读取 Token 状态。</p>`;
    }

    // Logs
    const logsData = await API.get('/api/logs?per_page=20');
    if (logsData.success) {
        document.getElementById('logsBody').innerHTML = logsData.data.length
            ? logsData.data.map(l => `<tr>
                <td><small>${escapeHtml(l.created_at)}</small></td>
                <td>${escapeHtml(l.action)}</td>
                <td><small>${escapeHtml(l.details)}</small></td>
            </tr>`).join('')
            : '<tr><td colspan="3" class="text-center text-muted">暂无日志</td></tr>';
    }
}

async function changePassword() {
    const currentPassword = document.getElementById('currentPassword').value;
    const newPassword = document.getElementById('newPassword').value;
    const confirmPassword = document.getElementById('confirmPassword').value;

    if (!currentPassword || !newPassword || !confirmPassword) {
        showToast('请完整填写密码信息', 'error');
        return;
    }
    if (newPassword !== confirmPassword) {
        showToast('两次输入的新密码不一致', 'error');
        return;
    }

    const result = await API.post('/api/auth/change-password', {
        current_password: currentPassword,
        new_password: newPassword
    });

    if (!result.success) {
        showToast(result.message || '修改密码失败', 'error');
        return;
    }

    document.getElementById('currentPassword').value = '';
    document.getElementById('newPassword').value = '';
    document.getElementById('confirmPassword').value = '';
    showToast('密码已更新', 'success');
}

async function clearData(table) {
    if (getAuthUser()?.role === 'admin' && !hasSpecificTargetUser()) {
        showToast('请先选择一个具体用户再清空数据', 'error');
        return;
    }
    const result = await API.post('/api/clear-data', { table });
    if (result.success) {
        showToast('数据已清空', 'success');
        loadSettings();
    } else {
        showToast('清空失败', 'error');
    }
}

document.addEventListener('fbhelper-auth-ready', () => {
    loadSettings();
});
