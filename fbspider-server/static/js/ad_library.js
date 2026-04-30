let adLibPage = 1;

async function loadAdLibrary(page) {
    if (!canBrowseData()) {
        document.getElementById('galleryGrid').innerHTML = '<div class="text-center text-muted py-5 w-100">请先在 <a href="/dashboard">Dashboard</a> 页初始化连接并获取数据</div>';
        return;
    }
    if (page) adLibPage = page;
    const mediaType = document.getElementById('mediaFilter').value;
    const data = await API.get(`/api/ad-library?page=${adLibPage}&media_type=${mediaType}`);
    const grid = document.getElementById('galleryGrid');

    if (!data.success || !data.data.length) {
        grid.innerHTML = '<div class="text-center text-muted py-5 w-100">暂无素材数据。请在 Facebook 广告素材库页面浏览以采集数据。</div>';
        document.getElementById('adLibPagination').innerHTML = '';
        return;
    }

    grid.innerHTML = data.data.map(item => {
        const isVideo = item.media_type === 'VIDEO';
        const mediaUrl = isVideo ? (item.video_hd_url || '') : (item.original_image_url || '');
        const mediaHtml = isVideo
            ? `<video src="${escapeHtml(mediaUrl)}" muted preload="metadata" onmouseover="this.play()" onmouseout="this.pause()"></video>`
            : `<img src="${escapeHtml(mediaUrl)}" alt="Ad ${item.ad_archive_id}" loading="lazy" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22260%22 height=%22200%22><rect fill=%22%23eee%22 width=%22260%22 height=%22200%22/><text x=%2250%25%22 y=%2250%25%22 dominant-baseline=%22middle%22 text-anchor=%22middle%22 fill=%22%23999%22>No Image</text></svg>'">`;

        const startDate = item.start_date ? new Date(item.start_date).toLocaleDateString() : '';
        const downloadUrl = mediaUrl;

        return `<div class="gallery-card card">
            ${mediaHtml}
            <div class="card-body p-2">
                <div class="d-flex justify-content-between align-items-center">
                    <small class="text-muted">${escapeHtml(item.ad_archive_id)}</small>
                    <span class="badge ${isVideo ? 'bg-info' : 'bg-primary'}">${item.media_type || 'N/A'}</span>
                </div>
                <div class="small text-muted mt-1">${startDate}</div>
                ${downloadUrl ? `<a href="${escapeHtml(downloadUrl)}" target="_blank" class="btn btn-sm btn-outline-primary w-100 mt-2">
                    <i class="fas fa-download me-1"></i>下载</a>` : ''}
            </div>
        </div>`;
    }).join('');

    renderPagination('adLibPagination', adLibPage, data.pages, loadAdLibrary);
}

document.addEventListener('fbhelper-auth-ready', () => {
    loadAdLibrary();
});
