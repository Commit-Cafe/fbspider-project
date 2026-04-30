async function loadPixels() {
    if (!canBrowseData()) {
        document.getElementById('pixelBody').innerHTML = '<tr><td colspan="5" class="text-center text-muted py-4">请先在 <a href="/dashboard">Dashboard</a> 页初始化连接并获取数据</td></tr>';
        return;
    }
    const data = await API.get('/api/pixels');
    const tbody = document.getElementById('pixelBody');
    if (!data.success || !data.data.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted py-4">暂无Pixel数据</td></tr>';
        return;
    }
    tbody.innerHTML = data.data.map(p => `<tr>
        <td><code>${escapeHtml(p.pixel_id)}</code></td>
        <td>${escapeHtml(p.name)}</td>
        <td>${escapeHtml(p.owner_bm_id)}</td>
        <td>${escapeHtml(p.status)}</td>
        <td>
            <button class="btn btn-outline-primary btn-sm" onclick="showPixelDetail('${p.pixel_id}')">
                <i class="fas fa-eye me-1"></i>详情
            </button>
        </td>
    </tr>`).join('');
}

async function refreshPixelsFromExtension() {
    if (getAuthUser()?.role === 'admin' && !hasSpecificTargetUser()) {
        showToast('管理员请先选择一个具体用户，再发起 Pixel 刷新。', 'error');
        return;
    }
    if (getAuthUser()?.role !== 'admin' && !getCurrentUserId()) {
        showToast('请先在 Dashboard 页初始化 Facebook 连接', 'error');
        return;
    }
    const result = await sendCommand('refresh_pixels');
    if (result?.success) {
        showToast('Pixel 刷新命令已发送，稍后自动刷新列表', 'info');
        setTimeout(() => {
            loadPixels();
        }, 7000);
    }
}

async function showPixelDetail(pixelId) {
    const [pixelData, purchaseData] = await Promise.all([
        API.get(`/api/pixels/${pixelId}`),
        API.get(`/api/pixels/${pixelId}/purchases`)
    ]);

    if (!pixelData.success) return;
    const p = pixelData.data;
    document.getElementById('pixelModalTitle').textContent = `Pixel: ${p.name || pixelId}`;

    // Associations tabs
    const assocs = p.associations || [];
    const users = assocs.filter(a => a.assoc_type === 'user');
    const partners = assocs.filter(a => a.assoc_type === 'partner');
    const adaccounts = assocs.filter(a => a.assoc_type === 'adaccount');

    function renderAssocTable(items, type) {
        if (!items.length) return '<p class="text-muted">无数据</p>';
        return `<table class="table table-sm"><thead><tr><th>ID</th><th>名称</th><th>操作</th></tr></thead><tbody>
            ${items.map(a => `<tr><td><code>${escapeHtml(a.assoc_id)}</code></td><td>${escapeHtml(a.assoc_name)}</td>
            <td><button class="btn btn-outline-danger btn-sm" onclick="sendCommand('remove_pixel_${type}',{pixel_id:'${pixelId}',${type}_id:'${a.assoc_id}'})">
                <i class="fas fa-trash"></i></button></td></tr>`).join('')}
        </tbody></table>`;
    }

    let purchaseHtml = '<p class="text-muted">无购买事件数据</p>';
    if (purchaseData.success && purchaseData.data) {
        purchaseHtml = `<pre class="bg-light p-2 rounded" style="max-height:300px;overflow:auto;font-size:12px">${
            JSON.stringify(purchaseData.data.event_data, null, 2)}</pre>`;
    }

    document.getElementById('pixelModalBody').innerHTML = `
        <ul class="nav nav-tabs" role="tablist">
            <li class="nav-item"><a class="nav-link active" data-bs-toggle="tab" href="#tabUsers">用户 (${users.length})</a></li>
            <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#tabPartners">合作伙伴 (${partners.length})</a></li>
            <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#tabAdAccounts">广告账户 (${adaccounts.length})</a></li>
            <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#tabPurchases">购买事件</a></li>
        </ul>
        <div class="tab-content pt-3">
            <div class="tab-pane fade show active" id="tabUsers">${renderAssocTable(users, 'user')}</div>
            <div class="tab-pane fade" id="tabPartners">${renderAssocTable(partners, 'partner')}</div>
            <div class="tab-pane fade" id="tabAdAccounts">${renderAssocTable(adaccounts, 'adaccount')}</div>
            <div class="tab-pane fade" id="tabPurchases">${purchaseHtml}</div>
        </div>
    `;

    new bootstrap.Modal(document.getElementById('pixelModal')).show();
}

document.addEventListener('fbhelper-auth-ready', () => {
    loadPixels();
});
