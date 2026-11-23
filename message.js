async function loadMessage() {
    const parameters = new URLSearchParams(window.location.search);
    const messageId = parameters.get("id");

    if (!messageId || !/^\d+$/.test(messageId)) {
        showMessage("Please provide a valid message ID.", "danger");
        return;
    }

    try {
        const result = await getData("/api/messages/" + messageId);

        displayMessage(result.message);
        displayAttempts(result.attempts);

    } catch (error) {
        showMessage(error.message, "danger");

        document.getElementById("message-details").innerHTML =
            '<div class="empty-state">Message not found.</div>';
    }
}

function displayMessage(message) {
    document.getElementById("message-details").innerHTML = `
        <div class="card">
            <div class="card-header">
                Message #${message.id}
            </div>

            <div class="card-body">
                <div class="row g-3">

                    <div class="col-md-6">
                        <strong>Status</strong>
                        <p>${getStatusBadge(message.status)}</p>
                    </div>

                    <div class="col-md-6">
                        <strong>Channel</strong>
                        <p>${escapeHTML(message.channel)}</p>
                    </div>

                    <div class="col-md-6">
                        <strong>Category</strong>
                        <p>${escapeHTML(message.category)}</p>
                    </div>

                    <div class="col-md-6">
                        <strong>Recipient</strong>
                        <p>${escapeHTML(message.recipient)}</p>
                    </div>

                    <div class="col-md-6">
                        <strong>Created at</strong>
                        <p>${escapeHTML(formatDate(message.created_at))}</p>
                    </div>

                    <div class="col-md-6">
                        <strong>Sent at</strong>
                        <p>${escapeHTML(formatDate(message.sent_at))}</p>
                    </div>

                    <div class="col-md-6">
                        <strong>Provider</strong>
                        <p>${escapeHTML(message.provider || "-")}</p>
                    </div>

                    <div class="col-md-6">
                        <strong>Total attempts</strong>
                        <p>${message.attempts}</p>
                    </div>

                    <div class="col-12">
                        <strong>Subject</strong>
                        <p>${escapeHTML(message.subject || "-")}</p>
                    </div>

                    <div class="col-12">
                        <strong>Message body</strong>
                        <div class="p-3 bg-light rounded">
                            ${escapeHTML(message.body)}
                        </div>
                    </div>

                    <div class="col-12">
                        <strong>Last error</strong>
                        <p>${escapeHTML(message.last_error || "No error")}</p>
                    </div>

                </div>
            </div>
        </div>
    `;
}

function displayAttempts(attempts) {
    const timeline = document.getElementById("attempt-timeline");

    if (!attempts || attempts.length === 0) {
        timeline.innerHTML = "No delivery attempts have been recorded yet.";
        return;
    }

    timeline.innerHTML = attempts.map(function (attempt) {
        return `
            <div class="timeline-item">
                <h6>Attempt ${attempt.attempt_no}</h6>

                <p class="mb-1">
                    Provider: <strong>${escapeHTML(attempt.provider)}</strong>
                </p>

                <p class="mb-1">
                    Result: ${getStatusBadge(
                        attempt.result === "ok" ? "sent" :
                        attempt.result === "permanent" ? "failed" :
                        "pending"
                    )}
                </p>

                <p class="muted mb-1">
                    Time: ${escapeHTML(formatDate(attempt.at))}
                </p>

                <p class="mb-0">
                    Error: ${escapeHTML(attempt.error || "No error")}
                </p>
            </div>
        `;
    }).join("");
}

loadMessage();
