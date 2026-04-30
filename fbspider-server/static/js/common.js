// Common utilities for fbhelper local dashboard

let currentUserId = localStorage.getItem("fbhelper_user_id") || localStorage.getItem("fbspider_user_id") || "";
let authUser = null;
let currentTargetUserId = localStorage.getItem("fbhelper_target_user_id") || "";

function setCurrentUserId(uid) {
    currentUserId = String(uid || "");
    localStorage.setItem("fbhelper_user_id", currentUserId);
}

function getCurrentUserId() {
    return currentUserId;
}

function getAuthUser() {
    return authUser;
}

function getCurrentTargetUserId() {
    if (authUser?.role === "admin") {
        return currentTargetUserId || "__all__";
    }
    return authUser?.username || "";
}

function hasSpecificTargetUser() {
    return getCurrentTargetUserId() && getCurrentTargetUserId() !== "__all__";
}

function canBrowseData() {
    if (authUser?.role === "admin") {
        return true;
    }
    return !!getCurrentUserId();
}

function needsFacebookConnection() {
    if (authUser?.role === "admin") {
        return false;
    }
    return true;
}

function appendTargetUser(url) {
    if (authUser?.role !== "admin") return url;
    const target = getCurrentTargetUserId();
    if (!target) return url;
    return url + (url.includes("?") ? "&" : "?") + `target_user_id=${encodeURIComponent(target)}`;
}

const API = {
    async get(url) {
        const resp = await fetch(appendTargetUser(url), { credentials: "same-origin" });
        return resp.json();
    },
    async post(url, data) {
        const payload = { ...(data || {}) };
        if (authUser?.role === "admin" && hasSpecificTargetUser()) {
            payload.target_user_id = getCurrentTargetUserId();
        }
        const resp = await fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        return resp.json();
    },
    async put(url, data) {
        const payload = { ...(data || {}) };
        if (authUser?.role === "admin" && hasSpecificTargetUser()) {
            payload.target_user_id = getCurrentTargetUserId();
        }
        const resp = await fetch(url, {
            method: "PUT",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        return resp.json();
    },
    async delete(url) {
        const resp = await fetch(url, { method: "DELETE", credentials: "same-origin" });
        return resp.json();
    }
};

function showToast(message, type = "success") {
    let container = document.querySelector(".toast-container");
    if (!container) {
        container = document.createElement("div");
        container.className = "toast-container";
        document.body.appendChild(container);
    }
    const toast = document.createElement("div");
    toast.className = `alert alert-${type === "error" ? "danger" : type} alert-dismissible fade show`;
    toast.style.cssText = "min-width:250px;box-shadow:0 4px 12px rgba(0,0,0,.15);";
    toast.innerHTML = `${message}<button type="button" class="btn-close btn-sm" data-bs-dismiss="alert"></button>`;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

function formatStatus(status) {
    const s = String(status).toUpperCase();
    if (s === "ACTIVE" || s === "1") return '<span class="badge bg-success">Active</span>';
    if (s === "DISABLED" || s === "2") return '<span class="badge bg-danger">Disabled</span>';
    if (s.includes("PENDING")) return '<span class="badge bg-warning text-dark">Pending</span>';
    if (s === "CLOSED" || s === "101") return '<span class="badge bg-secondary">Closed</span>';
    return `<span class="badge bg-secondary">${status || "Unknown"}</span>`;
}

function escapeHtml(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

async function sendCommand(commandType, params = {}) {
    if (authUser?.role === "admin" && !hasSpecificTargetUser()) {
        showToast("管理员在“全部用户”视图下不能直接发送命令，请先选择具体用户。", "error");
        return;
    }
    if (authUser?.role !== "admin" && !currentUserId) {
        showToast("请先初始化连接获取 Facebook 用户信息", "error");
        return;
    }
    try {
        const result = await API.post("/api/commands/create", {
            command_type: commandType,
            params
        });
        if (result.success) {
            showToast(`命令已发送: ${commandType}`, "success");
        } else {
            showToast(`命令失败: ${result.message}`, "error");
        }
        return result;
    } catch (e) {
        showToast(`命令发送错误: ${e.message}`, "error");
    }
}

function renderPagination(containerId, currentPage, totalPages, onPageChange) {
    const container = document.getElementById(containerId);
    if (!container || totalPages <= 1) {
        if (container) container.innerHTML = "";
        return;
    }
    let html = '<nav><ul class="pagination pagination-sm mb-0">';
    html += `<li class="page-item ${currentPage <= 1 ? "disabled" : ""}">
        <a class="page-link" href="#" data-page="${currentPage - 1}">&laquo;</a></li>`;
    const start = Math.max(1, currentPage - 2);
    const end = Math.min(totalPages, currentPage + 2);
    for (let i = start; i <= end; i++) {
        html += `<li class="page-item ${i === currentPage ? "active" : ""}">
            <a class="page-link" href="#" data-page="${i}">${i}</a></li>`;
    }
    html += `<li class="page-item ${currentPage >= totalPages ? "disabled" : ""}">
        <a class="page-link" href="#" data-page="${currentPage + 1}">&raquo;</a></li>`;
    html += "</ul></nav>";
    container.innerHTML = html;
    container.querySelectorAll(".page-link").forEach(link => {
        link.addEventListener("click", e => {
            e.preventDefault();
            const page = parseInt(e.target.dataset.page, 10);
            if (page >= 1 && page <= totalPages) onPageChange(page);
        });
    });
}

async function checkConnection() {
    const el = document.getElementById("connection-status");
    if (!el) return;

    try {
        const data = await API.get("/api/connection-state");
        if (!data.success) throw new Error("no connection state");
        const state = data.data || {};
        if (state.fb_user_id) {
            setCurrentUserId(state.fb_user_id);
        } else if (authUser?.role !== "admin") {
            setCurrentUserId("");
        }
        const targetText = authUser?.role === "admin"
            ? `视图: ${getCurrentTargetUserId() === "__all__" ? "全部用户" : getCurrentTargetUserId()}`
            : `用户: ${authUser?.username || "-"}`;
        const tokenText = state.has_token
            ? `FB: ${state.fb_user_name || state.fb_user_id || "已连接"}`
            : "FB Token: 未获取";
        const heartbeatText = state.heartbeat_ok ? "插件在线" : "插件离线";
        el.innerHTML = `<span class="badge ${state.has_token ? "bg-success" : "bg-warning text-dark"}"><i class="fas fa-circle me-1"></i>${state.has_token ? "已连接" : "待初始化"}</span>
            <div class="mt-1 text-muted" style="font-size:11px">${targetText} | ${tokenText} | ${heartbeatText}</div>`;
    } catch {
        el.innerHTML = '<span class="badge bg-danger"><i class="fas fa-circle me-1"></i>未连接</span>';
    }
}

async function loadAuthContext() {
    try {
        const resp = await fetch("/api/auth/me", { credentials: "same-origin" });
        const data = await resp.json();
        if (!data.success) {
            window.location.href = "/login";
            return null;
        }
        authUser = data.user;
        renderAuthHeader();
        return data.user;
    } catch {
        window.location.href = "/login";
        return null;
    }
}

function renderAuthHeader() {
    const userNameEl = document.getElementById("authUserName");
    if (userNameEl && authUser) {
        userNameEl.textContent = `${authUser.display_name || authUser.username} (${authUser.role === "admin" ? "管理员" : "用户"})`;
    }

    const selectorWrap = document.getElementById("targetUserWrap");
    const selector = document.getElementById("targetUserSelect");
    if (!selectorWrap || !selector) return;

    if (authUser?.role !== "admin") {
        selectorWrap.classList.add("d-none");
        return;
    }

    selectorWrap.classList.remove("d-none");
    fetch("/api/auth/users", { credentials: "same-origin" })
        .then(r => r.json())
        .then(data => {
            if (!data.success) return;
            const options = ['<option value="__all__">全部用户</option>']
                .concat(data.data.map(user => `<option value="${escapeHtml(user.username)}">${escapeHtml(user.username)}</option>`));
            selector.innerHTML = options.join("");
            selector.value = getCurrentTargetUserId();
            selector.onchange = () => {
                currentTargetUserId = selector.value;
                localStorage.setItem("fbhelper_target_user_id", currentTargetUserId);
                window.location.reload();
            };
        })
        .catch(() => {});
}

document.addEventListener("DOMContentLoaded", async () => {
    const logoutBtn = document.getElementById("logoutBtn");
    if (logoutBtn) {
        logoutBtn.addEventListener("click", async () => {
            await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" }).catch(() => {});
            window.location.href = "/login";
        });
    }

    await loadAuthContext();
    await checkConnection();
    document.dispatchEvent(new CustomEvent("fbhelper-auth-ready", {
        detail: {
            authUser,
            currentUserId
        }
    }));
});
