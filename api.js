const API_URL = window.location.origin;

function configureApiKey() {
    let key = sessionStorage.getItem("dakghar_api_key");
    let role = sessionStorage.getItem("dakghar_api_role");

    if (key && (role === "sender" || role === "admin")) {
        return { key, role };
    }

    key = window.prompt(
        "Enter your DakGhar API key. Use the SENDER_KEY for normal access or ADMIN_KEY for full controls."
    );

    if (!key || !key.trim()) {
        throw new Error("API key is required. Use the API key button to try again.");
    }

    role = window.prompt("Enter key type: sender or admin", "sender");
    role = (role || "").trim().toLowerCase();

    if (role !== "sender" && role !== "admin") {
        throw new Error("Key type must be sender or admin.");
    }

    sessionStorage.setItem("dakghar_api_key", key.trim());
    sessionStorage.setItem("dakghar_api_role", role);
    return { key: key.trim(), role };
}

function authHeaders() {
    const credentials = configureApiKey();
    return credentials.role === "admin"
        ? { "X-Admin-Key": credentials.key }
        : { "X-Api-Key": credentials.key };
}

function clearApiKey() {
    sessionStorage.removeItem("dakghar_api_key");
    sessionStorage.removeItem("dakghar_api_role");
    showMessage("API key cleared. The next request will ask for a new key.", "info");
}

async function apiRequest(url, options = {}) {
    const headers = Object.assign({}, authHeaders(), options.headers || {});
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
            : (result.detail && result.detail.detail) || result.message || "Request failed";
        if (response.status === 401 || response.status === 403) {
            if (result.error === "invalid_api_key" || result.error === "missing_api_key") {
                sessionStorage.removeItem("dakghar_api_key");
                sessionStorage.removeItem("dakghar_api_role");
            }
        }
        throw new Error(detail);
    }

    return result;
}

function getData(url) {
    return apiRequest(url, { method: "GET" });
}

function sendData(url, method, data) {
    const options = { method, headers: {} };
    if (data !== undefined && data !== null) {
        options.headers["Content-Type"] = "application/json";
        options.body = JSON.stringify(data);
    }
    return apiRequest(url, options);
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

document.addEventListener("DOMContentLoaded", function () {
    const nav = document.querySelector(".navbar .navbar-nav");
    if (nav && !document.getElementById("api-key-button")) {
        const item = document.createElement("a");
        item.href = "#";
        item.id = "api-key-button";
        item.className = "nav-link";
        item.textContent = sessionStorage.getItem("dakghar_api_key") ? "Change API key" : "Set API key";
        item.addEventListener("click", function (event) {
            event.preventDefault();
            sessionStorage.removeItem("dakghar_api_key");
            sessionStorage.removeItem("dakghar_api_role");
            try {
                configureApiKey();
                item.textContent = "Change API key";
                showMessage("API key saved for this browser tab.");
            } catch (error) {
                showMessage(error.message, "warning");
            }
        });
        nav.appendChild(item);
    }
});
