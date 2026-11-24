let inboxMessages = [];

async function loadInbox() {
    const area = document.getElementById("inbox-list");

    try {
        const result = await getData("/api/inbox");
        inboxMessages = result.messages || [];

        displayInbox();

    } catch (error) {
        showMessage(error.message, "danger");
        area.innerHTML = `
            <div class="empty-state">
                Could not load inbox.
            </div>
        `;
    }
}

function displayInbox() {
    const area = document.getElementById("inbox-list");
    const selectedProvider =
        document.getElementById("provider-filter").value;

    let messages = inboxMessages;

    if (selectedProvider) {
        messages = messages.filter(function (message) {
            return message.provider === selectedProvider;
        });
    }

    if (messages.length === 0) {
        area.innerHTML = `
            <div class="empty-state">
                <h5>No delivered messages yet</h5>
                <p>Successfully delivered messages will appear here.</p>
            </div>
        `;
        return;
    }

    area.innerHTML = messages.map(function (message) {
        return `
            <div class="card">
                <div class="card-body">

                    <div class="d-flex justify-content-between flex-wrap">
                        <h5>Message #${message.message_id}</h5>

                        <span class="badge text-bg-success">
                            Delivered
                        </span>
                    </div>

                    <p class="muted mb-2">
                        Provider: ${escapeHTML(message.provider)}
                    </p>

                    <p class="mb-1">
                        <strong>Recipient:</strong>
                        ${escapeHTML(message.recipient)}
                    </p>

                    <p class="mb-1">
                        <strong>Subject:</strong>
                        ${escapeHTML(message.subject || "SMS message")}
                    </p>

                    <div class="bg-light rounded p-3 my-3">
                        ${escapeHTML(message.body)}
                    </div>

                    <p class="muted mb-2">
                        Delivered at:
                        ${escapeHTML(formatDate(message.delivered_at))}
                    </p>

                    <a href="/static/message.html?id=${message.message_id}">
                        View message details
                    </a>

                </div>
            </div>
        `;
    }).join("");
}

document.getElementById("refresh-inbox").addEventListener(
    "click",
    loadInbox
);

document.getElementById("provider-filter").addEventListener(
    "change",
    displayInbox
);

loadInbox();
