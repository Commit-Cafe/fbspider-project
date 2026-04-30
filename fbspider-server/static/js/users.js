let userModal;
let userRows = [];

function resetUserForm() {
    document.getElementById("formMode").value = "create";
    document.getElementById("editUsername").value = "";
    document.getElementById("userModalTitle").textContent = "新增用户";
    document.getElementById("usernameInput").value = "";
    document.getElementById("usernameInput").disabled = false;
    document.getElementById("displayNameInput").value = "";
    document.getElementById("passwordInput").value = "";
    document.getElementById("roleInput").value = "user";
    document.getElementById("statusInput").value = "active";
    document.getElementById("userFormError").classList.add("d-none");
}

function openEditUser(username) {
    const user = userRows.find(row => row.username === username);
    if (!user) return;
    document.getElementById("formMode").value = "edit";
    document.getElementById("editUsername").value = user.username;
    document.getElementById("userModalTitle").textContent = `编辑用户: ${user.username}`;
    document.getElementById("usernameInput").value = user.username;
    document.getElementById("usernameInput").disabled = true;
    document.getElementById("displayNameInput").value = user.display_name || "";
    document.getElementById("passwordInput").value = "";
    document.getElementById("roleInput").value = user.role || "user";
    document.getElementById("statusInput").value = user.status || "active";
    document.getElementById("userFormError").classList.add("d-none");
    userModal.show();
}

async function loadUsers() {
    const data = await API.get("/api/auth/users");
    if (!data.success) return;
    userRows = data.data;
    const tbody = document.getElementById("usersBody");
    tbody.innerHTML = data.data.map(user => `<tr>
        <td><code>${escapeHtml(user.username)}</code></td>
        <td>${escapeHtml(user.display_name || "")}</td>
        <td>${user.role === "admin" ? '<span class="badge bg-dark">管理员</span>' : '<span class="badge bg-secondary">用户</span>'}</td>
        <td>${user.status === "active" ? '<span class="badge bg-success">启用</span>' : '<span class="badge bg-danger">禁用</span>'}</td>
        <td>${user.summary?.ad_accounts || 0}</td>
        <td>${user.summary?.bm_count || 0}</td>
        <td>${user.summary?.pixel_count || 0}</td>
        <td>${user.summary?.ad_library_count || 0}</td>
        <td>
            <div class="btn-group btn-group-sm">
                <button class="btn btn-outline-primary" onclick="openEditUser('${user.username}')">编辑</button>
                ${user.username !== "admin" ? `<button class="btn btn-outline-danger" onclick="removeUser('${user.username}')">删除</button>` : ""}
            </div>
        </td>
    </tr>`).join("");
}

async function saveUser() {
    const errorEl = document.getElementById("userFormError");
    errorEl.classList.add("d-none");
    const mode = document.getElementById("formMode").value;
    const payload = {
        username: document.getElementById("usernameInput").value.trim(),
        display_name: document.getElementById("displayNameInput").value.trim(),
        password: document.getElementById("passwordInput").value,
        role: document.getElementById("roleInput").value,
        status: document.getElementById("statusInput").value
    };

    const result = mode === "create"
        ? await API.post("/api/auth/users", payload)
        : await API.put(`/api/auth/users/${encodeURIComponent(document.getElementById("editUsername").value)}`, payload);

    if (!result.success) {
        errorEl.textContent = result.message || "保存失败";
        errorEl.classList.remove("d-none");
        return;
    }

    userModal.hide();
    showToast("用户已保存");
    loadUsers();
}

async function removeUser(username) {
    if (!confirm(`确定删除用户 ${username} 吗？该用户数据也会被一并删除。`)) return;
    const result = await API.delete(`/api/auth/users/${encodeURIComponent(username)}`);
    if (!result.success) {
        showToast(result.message || "删除失败", "error");
        return;
    }
    showToast("用户已删除");
    loadUsers();
}

document.addEventListener("DOMContentLoaded", () => {
    userModal = new bootstrap.Modal(document.getElementById("userModal"));
    document.getElementById("userModal").addEventListener("show.bs.modal", () => {
        if (document.getElementById("formMode").value === "create") {
            resetUserForm();
        }
    });
    document.getElementById("saveUserBtn").addEventListener("click", saveUser);
    loadUsers();
});
