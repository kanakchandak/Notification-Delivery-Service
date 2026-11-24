
async function loadProviders() {
    const area = document.getElementById("provider-list");

    try {
        const result = await getData("/api/providers");
        const providers = result.providers || [];

        if (providers.length === 0) {
            area.innerHTML = `
                <div class="col-12 empty-state">
                    No providers found.
                </div>
            `;
            return;
        }

        area.innerHTML = providers.map(function (provider) {
            let state = "Healthy";
            let stateClass = "success";

            if (provider.outage) {
                state = "Outage simulated";
                stateClass = "danger";
            } else if (
                provider.open_until &&
                provider.open_until > Date.now() / 1000
            ) {
                state = "Cooling down";
                stateClass = "warning";
            }

            return `
                <div class="col-lg-6">
                    <div class="card provider-card">
                        <div class="card-body">

                            <div class="d-flex justify-content-between">
                                <div>
                                    <div class="provider-name">
                                        ${escapeHTML(provider.name)}
                                    </div>

                                    <p class="muted">
                                        ${escapeHTML(provider.channel)}
                                        · ${provider.priority === 1 ? "Primary" : "Backup"}
                                    </p>
                                </div>

                                <span class="badge text-bg-${stateClass}">
                                    ${state}
                                </span>
                            </div>

                            <hr>

                            <p>
                                Consecutive failures:
                                <strong>${provider.consecutive_failures}</strong>
                            </p>

                            <p>
                                Failure rate:
                                <strong>${Number(provider.fail_rate * 100).toFixed(0)}%</strong>
                            </p>

                            <label class="form-label">
                                Failure rate: <span id="rate-${provider.name}">
                                    ${Number(provider.fail_rate * 100).toFixed(0)}%
                                </span>
                            </label>

                            <input type="range"
                                class="form-range"
                                min="0"
                                max="0.5"
                                step="0.01"
                                value="${provider.fail_rate}"
                                id="slider-${provider.name}"
                                oninput="updateRateText('${provider.name}')">

                            <div class="form-check form-switch mb-3">
                                <input class="form-check-input"
                                    type="checkbox"
                                    id="outage-${provider.name}"
                                    ${provider.outage ? "checked" : ""}>
                                <label class="form-check-label"
                                    for="outage-${provider.name}">
                                    Simulate outage
                                </label>
                            </div>

                            <button class="btn btn-primary w-100"
                                onclick="saveProvider('${provider.name}')">
                                Save settings
                            </button>

                        </div>
                    </div>
                </div>
            `;
        }).join("");

    } catch (error) {
        showMessage(error.message, "danger");
        area.innerHTML = `
            <div class="col-12 empty-state">
                Could not load providers.
            </div>
        `;
    }
}

function updateRateText(name) {
    const value = document.getElementById("slider-" + name).value;

    document.getElementById("rate-" + name).textContent =
        Math.round(value * 100) + "%";
}

async function saveProvider(name) {
    const failRate = Number(
        document.getElementById("slider-" + name).value
    );

    const outage = document.getElementById("outage-" + name).checked;

    try {
        await sendData("/api/providers/" + name, "PATCH", { fail_rate: failRate, outage: outage }, "admin");

        showMessage(name + " settings updated successfully.");
        loadProviders();

    } catch (error) {
        showMessage(error.message, "danger");
    }
}

loadProviders();

async function loadWorkerStatus() {
    const area = document.getElementById("worker-status");
    if (!area) return;
    try {
        const worker = await getData("/api/worker");
        area.innerHTML = `
            <p class="mb-1">State: <strong>${worker.paused ? "Paused" : "Running"}</strong></p>
            <p class="mb-1">Thread active: <strong>${worker.running ? "Yes" : "No"}</strong></p>
            <p class="mb-1">Messages processed: <strong>${worker.processed_total}</strong></p>
            <p class="mb-0">Recovered at startup: <strong>${worker.recovered_on_start}</strong></p>
        `;
    } catch (error) {
        area.textContent = error.message;
    }
}

async function updateWorker(paused) {
    try {
        await sendData("/api/worker", "PATCH", { paused }, "admin");
        showMessage(paused ? "Worker paused." : "Worker resumed.");
        loadWorkerStatus();
    } catch (error) {
        showMessage(error.message, "danger");
    }
}

async function runWorkerTick() {
    try {
        const result = await sendData("/api/worker/tick", "POST", null, "admin");
        showMessage("Tick completed. Processed: " + result.processed);
        loadWorkerStatus();
    } catch (error) {
        showMessage(error.message, "danger");
    }
}

const pauseWorkerButton = document.getElementById("pause-worker");
const resumeWorkerButton = document.getElementById("resume-worker");
const tickWorkerButton = document.getElementById("worker-tick");
const refreshWorkerButton = document.getElementById("refresh-worker");
if (pauseWorkerButton) pauseWorkerButton.addEventListener("click", () => updateWorker(true));
if (resumeWorkerButton) resumeWorkerButton.addEventListener("click", () => updateWorker(false));
if (tickWorkerButton) tickWorkerButton.addEventListener("click", runWorkerTick);
if (refreshWorkerButton) refreshWorkerButton.addEventListener("click", loadWorkerStatus);
loadWorkerStatus();
