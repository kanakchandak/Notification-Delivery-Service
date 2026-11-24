
let refreshEnabled = true;
let oldestId = null;
let allMessages = [];

async function loadMessages(append = false) {
    const status = document.getElementById("status-filter").value;
    const channel = document.getElementById("channel-filter").value;
    const category = document.getElementById("category-filter").value;

    let url = "/api/messages?limit=50";

    if (status) url += "&status=" + encodeURIComponent(status);
    if (channel) url += "&channel=" + encodeURIComponent(channel);
    if (category) url += "&category=" + encodeURIComponent(category);

    if (append && oldestId) {
        url += "&before_id=" + oldestId;
    }

    try {
        const result = await getData(url);
        const messages = result.messages || [];

        if (append) {
            allMessages = allMessages.concat(messages);
        } else {
            allMessages = messages;
        }

        if (messages.length > 0) {
            oldestId = messages[messages.length - 1].id;
        }

        updateCounts();
        displayMessages();

        document.getElementById("refresh-status").textContent =
            "Last updated: " + new Date().toLocaleTimeString();

    } catch (error) {
        showMessage(error.message, "danger");
    }
}

function updateCounts() {
    const counts = {
        pending: 0,
        sending: 0,
        sent: 0,
        failed: 0
    };

    allMessages.forEach(function (message) {
        if (counts[message.status] !== undefined) {
            counts[message.status]++;
        }
    });

    document.getElementById("pending-count").textContent = counts.pending;
    document.getElementById("sending-count").textContent = counts.sending;
    document.getElementById("sent-count").textContent = counts.sent;
    document.getElementById("failed-count").textContent = counts.failed;
}

function displayMessages() {
    const table = document.getElementById("message-list");

    if (allMessages.length === 0) {
        table.innerHTML = `
            <tr>
                <td colspan="8">
                    <div class="empty-state">
                        <h5>No messages yet</h5>
                        Send your first message to get started.
                    </div>
                </td>
            </tr>
        `;
        return;
    }

    table.innerHTML = allMessages.map(function (message) {
        return `
            <tr>
                <td>
                    <a href="/static/message.html?id=${message.id}">
                        #${message.id}
                    </a>
                </td>
                <td>${escapeHTML(formatDate(message.created_at))}</td>
                <td>${escapeHTML(message.channel)}</td>
                <td>${escapeHTML(message.category)}</td>
                <td>${escapeHTML(message.recipient)}</td>
                <td>${getStatusBadge(message.status)}</td>
                <td>${message.attempts}</td>
                <td>${escapeHTML(message.provider || "-")}</td>
            </tr>
        `;
    }).join("");
}

document.getElementById("refresh-button").addEventListener("click", function () {
    loadMessages();
});

document.getElementById("load-older").addEventListener("click", function () {
    loadMessages(true);
});

document.getElementById("pause-refresh").addEventListener("click", function () {
    refreshEnabled = !refreshEnabled;

    this.textContent = refreshEnabled ? "Pause refresh" : "Resume refresh";
});

["status-filter", "channel-filter", "category-filter"].forEach(function (id) {
    document.getElementById(id).addEventListener("change", function () {
        oldestId = null;
        loadMessages();
    });
});

loadMessages();

setInterval(function () {
    if (refreshEnabled) {
        loadMessages();
    }
}, 2000);
