# DakGhar — Notification Delivery Service

DakGhar is a mock email and SMS notification delivery service built with FastAPI, SQLite, a background worker, and a Bootstrap/vanilla JavaScript frontend. It simulates queueing, provider selection, retries, failover, circuit breaking, and a fake delivered-message inbox. It does not send real email or SMS.

## Run on Windows

1. Extract the ZIP.
2. Open the extracted `DakGhar` folder.
3. Double-click `start.bat`.
4. On the first run, wait while Python creates the virtual environment and installs packages.
5. Open `http://127.0.0.1:8000` in your browser.
6. Open the app. Public sender access is enabled by default, so no sender key is needed. The admin key is requested only when using protected provider or worker controls.

The first run creates a local `.env` file with randomly generated keys. Public sender access is enabled by default through `PUBLIC_SENDER_ACCESS=true`. The browser requests the admin key only when an admin-only action is selected; it is stored in `sessionStorage` for the current tab.

## Run manually

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env`, replace `ADMIN_KEY` and `SENDER_KEY` with long random keys, keep `PUBLIC_SENDER_ACCESS=true` for key-free sender access, then run:

```bash
uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1
```

Open http://127.0.0.1:8000. Use one Uvicorn worker because the background worker is an in-process thread and SQLite is the shared queue database.

## API roles

- Public sender access (enabled by `PUBLIC_SENDER_ACCESS=true`): create and inspect messages, providers, worker status, and fake inbox without a key.
- `X-Api-Key` using `SENDER_KEY`: optional keyed sender access when public sender access is disabled.
- `X-Admin-Key` using `ADMIN_KEY`: sender permissions plus provider configuration, worker controls, manual retry, and demo reset.
- Admin-only operations always require `X-Admin-Key` using `ADMIN_KEY`; public sender access does not grant admin permissions. Set `PUBLIC_SENDER_ACCESS=false` to require `SENDER_KEY` for sender endpoints.

## Message rules

- Channels: `email`, `sms`; categories: `transactional`, `marketing`.
- Email requires a valid recipient and a 1–150 character subject; body maximum 2,000 characters.
- SMS uses international `+` phone format, has no subject, and body maximum 480 characters.
- Optional idempotency keys return the original message for an identical payload and 409 for a different payload.
- Pending queue capacity: 10,000 messages. List endpoints return at most 200 records.
- Outbox recipient values are masked; message detail shows the full recipient.

## Delivery behavior

- Transactional messages are selected before marketing messages; within each class the oldest due item is selected first.
- Each channel has two mock providers. Healthy providers are selected by priority; a failed provider is avoided when an alternate is available.
- Temporary failures retry after 2, 4, and 8 seconds, for up to four attempts per retry cycle.
- Two consecutive temporary failures open a provider circuit for 30 seconds.
- If no eligible provider is available, the message remains pending until a provider can be retried.
- Permanent bounce examples (`@bounce.example` and SMS numbers beginning `+91900000`) fail without retry.
- Successful simulated delivery is added to the fake inbox. Startup recovers messages left in `sending` state.

## Included frontend

The supplied six-page frontend is installed in `static/`: Send, Outbox, Message Details, Providers & Worker, Fake Inbox, and How it works. The shared API helper sends the required authentication header and handles API errors. The Providers & Worker page includes pause, resume, status refresh, and manual tick controls.

## Tests

```bash
python -m pytest -q
python -m compileall -q main.py database.py engine.py providers.py schemas.py worker.py scripts tests
```

The included tests cover delivery behavior, retries, failover, API authentication, idempotency, privacy masking, and demo reset. Run `python scripts/simulate_sends.py --count 10000 --seed 42` for a deterministic isolated queue simulation.

## Safety and deployment

All providers are mocks; no real messages are sent. Do not commit `.env` or a live database. Deploy as a single process with `uvicorn main:app --workers 1`, set `ADMIN_KEY` and `SENDER_KEY` as environment variables, and use persistent storage for `notifications.db`.
