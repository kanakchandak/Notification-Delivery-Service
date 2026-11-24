const API_URL = window.location.origin;

function getAdminKey() {
    let key = sessionStorage.getItem("dakghar_admin_key");
    if (!key) {
        key = window.prompt("Enter the admin key to use protected controls.");
        if (!key || !key.trim()) throw new Error("Admin key is required for this action.");
        key = key.trim();
        sessionStorage.setItem("dakghar_admin_key", key);
    }
    return key;
}

function clearApiKey() {
    sessionStorage.removeItem("dakghar_admin_key");
    showMessage("Admin key cleared from this browser tab.", "info");
}

async function apiRequest(url, options = {}, role = "sender") {
    const headers = Object.assign({}, options.headers || {});
    if (role === "admin") headers["X-Admin-Key"] = getAdminKey();

    const response = await fetch(API_URL + url, Object.assign({}, options, { headers }));
    let result = {};
    try {
        result = await response.json();
    } catch (_) {
        result = {};
    }

    if (!response.ok) {
        const detail = typeof result.detail === "string"
            ? result.detail
            : (result.detail && result.detail.detail) || result.message || result.error || `Request failed (HTTP ${response.status})`;

        if (role === "admin" && (response.status === 401 || response.status === 403)) {
            sessionStorage.removeItem("dakghar_admin_key");
        }
        throw new Error(detail);
    }
    return result;
}

function getData(url, role = "sender") {
    return apiRequest(url, { method: "GET" }, role);
}

function sendData(url, method, data, role = "sender") {
    const options = { method, headers: {} };
    if (data !== undefined && data !== null) {
        options.headers["Content-Type"] = "application/json";
        options.body = JSON.stringify(data);
    }
    return apiRequest(url, options, role);
}

function showMessage(message, type = "success") {
    const area = document.getElementById("message-area");
    if (!area) {
        window.alert(message);
        return;
    }
    area.innerHTML = `
        <div class="alert alert-${type} alert-dismissible fade show" role="alert">
            ${escapeHTML(message)}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>
    `;
}

function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, function (char) {
        return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char];
    });
}

function formatDate(timestamp) {
    if (!timestamp) return "-";
    return new Date(timestamp * 1000).toLocaleString();
}

function getStatusBadge(status) {
    return `<span class="status-badge status-${escapeHTML(status)}">${escapeHTML(status)}</span>`;
}

function showLoading(elementId) {
    const element = document.getElementById(elementId);
    if (element) element.innerHTML = '<div class="text-center p-4">Loading...</div>';
}
