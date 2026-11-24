import os
import time
import sqlite3
import secrets
import json
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import(
    FastAPI,
    HTTPException,
    Header,
    Query,
    Depends
)
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from database import get_connection, initialize_database
from schemas import MessageRequest, ProviderUpdate

from worker import (
    start_worker,
    stop_worker,
    get_worker_status,
    pause_worker,
    resume_worker,
    run_worker_tick,
    WorkerBusyError,
    worker_lock,
    worker_paused
)

STATIC_DIR = Path(__file__).with_name("static")


@asynccontextmanager
async def lifespan(app):
    initialize_database()
    start_worker()
    try:
        yield
    finally:
        stop_worker()


app = FastAPI(
    title="DakGhar Notification Delivery Service",
    description="A mock email and SMS notification delivery service",
    lifespan=lifespan
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def check_key(provided_key, expected_key):
    if not provided_key or not expected_key:
        return False

    return secrets.compare_digest(
        provided_key,
        expected_key
    )


def require_sender(
    x_api_key: str | None = Header(
        default=None,
        alias="X-Api-Key"
    ),
    x_admin_key: str | None = Header(
        default=None,
        alias="X-Admin-Key"
    )
):
    admin_key = os.getenv("ADMIN_KEY")
    sender_key = os.getenv("SENDER_KEY")

    if check_key(x_admin_key, admin_key):
        return "admin"

    if check_key(x_api_key, sender_key):
        return "sender"

    if not x_api_key and not x_admin_key:
        public_access = os.getenv(
            "PUBLIC_SENDER_ACCESS",
            "true"
        ).strip().lower() in ("1", "true", "yes", "on")

        if public_access:
            return "sender"

        raise HTTPException(
            status_code=401,
            detail={
                "error": "missing_api_key",
                "detail": "An API key is required"
            }
        )

    if not admin_key and not sender_key:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "auth_not_configured",
                "detail": "API authentication keys are not configured"
            }
        )

    raise HTTPException(
        status_code=403,
        detail={
            "error": "invalid_api_key",
            "detail": "The API key is incorrect"
        }
    )
def require_admin(
    x_api_key: str | None = Header(
        default=None,
        alias="X-Api-Key"
    ),
    x_admin_key: str | None = Header(
        default=None,
        alias="X-Admin-Key"
    )
):
    admin_key = os.getenv("ADMIN_KEY")
    sender_key = os.getenv("SENDER_KEY")

    if not admin_key:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "auth_not_configured",
                "detail": "Admin API key is not configured"
            }
        )

    if not x_api_key and not x_admin_key:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "missing_api_key",
                "detail": "Admin API key is required"
            }
        )

    if check_key(x_admin_key, admin_key):
        return "admin"

    if check_key(x_api_key, sender_key):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "admin_access_required",
                "detail": "Only an admin can perform this action"
            }
        )

    raise HTTPException(
        status_code=403,
        detail={
            "error": "invalid_api_key",
            "detail": "The admin API key is incorrect"
        }
    )



def mask_recipient(recipient, channel):
    if channel == "email":
        local, separator, domain = recipient.partition("@")
        if not separator:
            return "***"
        visible = local[:1] if local else "*"
        return f"{visible}***@{domain}"
    digits = recipient
    if len(digits) <= 5:
        return "*" * len(digits)
    return digits[:3] + "*" * (len(digits) - 5) + digits[-2:]


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request, exc):
    errors = exc.errors()

    if errors:
        detail = errors[0].get("msg", "Invalid request data")
    else:
        detail = "Invalid request data"

    return JSONResponse(
        status_code=400,
        content={
            "error": "validation_error",
            "detail": detail
        }
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request, exc):
    if isinstance(exc.detail, dict):
        error = exc.detail.get("error", "http_error")
        detail = exc.detail.get("detail", "Request failed")
    else:
        error = "http_error"
        detail = str(exc.detail)

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": error,
            "detail": detail
        },
        headers=exc.headers
    )


@app.get("/")
def home():
    return FileResponse(STATIC_DIR / "send.html")


@app.get("/health")
def health():
    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            SELECT COUNT(*)
            FROM messages
        """)

        total_messages = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*)
            FROM messages
            WHERE status = 'pending'
        """)

        pending = cursor.fetchone()[0]

        worker = get_worker_status()

        return {
            "status": "ok",
            "database": "connected",
            "total_messages": total_messages,
            "pending": pending,
            "worker_running": worker["running"],
            "worker_paused": worker["paused"]
        }

    finally:
        connection.close()


@app.get("/api/tables")
def get_tables(auth=Depends(require_sender)):
    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            AND name NOT LIKE 'sqlite_%'
        """)

        tables = [
            row["name"] for row in cursor.fetchall()
        ]

        return {
            "count": len(tables),
            "tables": tables
        }

    finally:
        connection.close()


@app.post("/api/messages")
def create_message(
    message: MessageRequest,
    auth=Depends(require_sender)
):
    connection = get_connection()

    try:
        cursor = connection.cursor()

        if message.idempotency_key:
            cursor.execute("""
                SELECT *
                FROM messages
                WHERE idempotency_key = ?
            """, (message.idempotency_key,))

            existing = cursor.fetchone()

            if existing:
                same_message = (
                    existing["channel"] == message.channel
                    and existing["category"] == message.category
                    and existing["recipient"] == message.recipient
                    and existing["subject"] == message.subject
                    and existing["body"] == message.body
                )

                if same_message:
                    return JSONResponse(
                        status_code=200,
                        content={
                            "id": existing["id"],
                            "status": existing["status"],
                            "created_at": existing["created_at"],
                            "message": "Original message returned"
                        }
                    )

                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": "idempotency_conflict",
                        "detail": "This key was already used for a different message"
                    }
                )

        cursor.execute("""
            SELECT COUNT(*)
            FROM messages
            WHERE status = 'pending'
        """)

        pending_count = cursor.fetchone()[0]

        if pending_count >= 10000:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "queue_full",
                    "detail": "The pending message queue is full"
                }
            )

        current_time = time.time()

        cursor.execute("""
            INSERT INTO messages (
                channel,
                category,
                recipient,
                subject,
                body,
                status,
                attempts,
                next_attempt_at,
                created_at,
                idempotency_key
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            message.channel,
            message.category,
            message.recipient,
            message.subject,
            message.body,
            "pending",
            0,
            current_time,
            current_time,
            message.idempotency_key
        ))

        message_id = cursor.lastrowid

        connection.commit()

        return JSONResponse(
            status_code=201,
            content={
                "id": message_id,
                "status": "pending",
                "created_at": current_time
            }
        )

    except HTTPException:
        connection.rollback()
        raise

    except sqlite3.IntegrityError:
        connection.rollback()

        raise HTTPException(
            status_code=409,
            detail={
                "error": "idempotency_conflict",
                "detail": "This idempotency key already exists"
            }
        )

    except sqlite3.Error:
        connection.rollback()

        raise HTTPException(
            status_code=500,
            detail={
                "error": "database_error",
                "detail": "Database error while saving message"
            }
        )

    finally:
        connection.close()


@app.get("/api/messages")
def get_messages(
    status: str | None = None,
    channel: str | None = None,
    category: str | None = None,
    before_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    auth=Depends(require_sender)
):
    if status and status not in (
        "pending", "sending", "sent", "failed"
    ):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_status",
                "detail": "Invalid message status"
            }
        )

    if channel and channel not in ("email", "sms"):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_channel",
                "detail": "Channel must be email or sms"
            }
        )

    if category and category not in (
        "transactional", "marketing"
    ):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_category",
                "detail": "Invalid message category"
            }
        )

    connection = get_connection()

    try:
        cursor = connection.cursor()

        query = "SELECT * FROM messages WHERE 1=1"
        values = []

        if status:
            query += " AND status = ?"
            values.append(status)

        if channel:
            query += " AND channel = ?"
            values.append(channel)

        if category:
            query += " AND category = ?"
            values.append(category)

        if before_id:
            query += " AND id < ?"
            values.append(before_id)

        query += " ORDER BY id DESC LIMIT ?"
        values.append(limit)

        cursor.execute(query, values)

        messages = []
        for row in cursor.fetchall():
            item = dict(row)
            item["recipient"] = mask_recipient(item["recipient"], item["channel"])
            messages.append(item)

        cursor.execute("""
            SELECT status, COUNT(*) AS total
            FROM messages
            GROUP BY status
        """)

        counts = {
            "pending": 0,
            "sending": 0,
            "sent": 0,
            "failed": 0
        }

        for row in cursor.fetchall():
            counts[row["status"]] = row["total"]

        return {
            "count": len(messages),
            "counts": counts,
            "messages": messages
        }

    finally:
        connection.close()


@app.get("/api/messages/{message_id}")
def get_message(
    message_id: int,
    auth=Depends(require_sender)
):
    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            SELECT *
            FROM messages
            WHERE id = ?
        """, (message_id,))

        message = cursor.fetchone()

        if message is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "message_not_found",
                    "detail": "Message not found"
                }
            )

        cursor.execute("""
            SELECT *
            FROM attempts
            WHERE message_id = ?
            ORDER BY at
        """, (message_id,))

        attempts = [
            dict(row) for row in cursor.fetchall()
        ]

        return {
            "message": dict(message),
            "attempts": attempts
        }

    finally:
        connection.close()


@app.post("/api/messages/{message_id}/retry")
def retry_message(
    message_id: int,
    auth=Depends(require_admin)
):
    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            SELECT *
            FROM messages
            WHERE id = ?
        """, (message_id,))

        message = cursor.fetchone()

        if message is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "message_not_found",
                    "detail": "Message not found"
                }
            )

        if message["status"] != "failed":
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "retry_not_allowed",
                    "detail": "Only failed messages can be retried"
                }
            )

        error = (message["last_error"] or "").lower()

        if (
            "bounced" in error
            or "permanently rejected" in error
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "permanent_failure",
                    "detail": "This message cannot be retried"
                }
            )

        cursor.execute("""
            UPDATE messages
            SET status = 'pending',
                attempts = 0,
                next_attempt_at = ?,
                last_failed_provider = NULL,
                last_error = NULL,
                locked_at = NULL
            WHERE id = ?
        """, (time.time(), message_id))

        connection.commit()

        return {
            "id": message_id,
            "status": "pending",
            "message": "Message added to the queue again"
        }

    finally:
        connection.close()


@app.get("/api/providers")
def get_providers(auth=Depends(require_sender)):
    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            SELECT *
            FROM providers
            ORDER BY channel, priority
        """)

        providers = []

        for row in cursor.fetchall():
            provider = dict(row)

            if provider["outage"]:
                provider["state"] = "Outage simulated"

            elif (
                provider["open_until"] is not None
                and provider["open_until"] > time.time()
            ):
                provider["state"] = "Cooling down"

            else:
                provider["state"] = "Healthy"

            providers.append(provider)

        return {
            "count": len(providers),
            "providers": providers
        }

    finally:
        connection.close()


@app.patch("/api/providers/{provider_name}")
def update_provider(
    provider_name: str,
    update: ProviderUpdate,
    auth=Depends(require_admin)
):
    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            SELECT *
            FROM providers
            WHERE name = ?
        """, (provider_name,))

        provider = cursor.fetchone()

        if provider is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "provider_not_found",
                    "detail": "Provider not found"
                }
            )

        if update.fail_rate is not None:
            cursor.execute("""
                UPDATE providers
                SET fail_rate = ?
                WHERE name = ?
            """, (update.fail_rate, provider_name))

        if update.outage is not None:
            cursor.execute("""
                UPDATE providers
                SET outage = ?
                WHERE name = ?
            """, (int(update.outage), provider_name))

        connection.commit()

        return {
            "message": "Provider configuration updated",
            "provider": provider_name
        }

    finally:
        connection.close()


class WorkerUpdate(BaseModel):
    paused: bool


@app.get("/api/worker")
def get_worker(auth=Depends(require_sender)):
    return get_worker_status()


@app.patch("/api/worker")
def update_worker(
    update: WorkerUpdate,
    auth=Depends(require_admin)
):
    if update.paused:
        return pause_worker()

    return resume_worker()


@app.post("/api/worker/tick")
def manual_worker_tick(auth=Depends(require_admin)):
    try:
        return run_worker_tick(force=True)

    except WorkerBusyError:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "worker_busy",
                "detail": "Worker is already processing a batch"
            }
        )


@app.get("/api/inbox")
def get_inbox(
    provider: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    auth=Depends(require_sender)
):
    connection = get_connection()

    try:
        cursor = connection.cursor()

        query = """
            SELECT *
            FROM inbox
            WHERE 1=1
        """

        values = []

        if provider:
            query += " AND provider = ?"
            values.append(provider)

        query += " ORDER BY delivered_at DESC LIMIT ?"
        values.append(limit)

        cursor.execute(query, values)

        messages = [
            dict(row) for row in cursor.fetchall()
        ]

        return {
            "count": len(messages),
            "messages": messages
        }

    finally:
        connection.close()


@app.post("/api/admin/reset")
def reset_database(auth=Depends(require_admin)):
    was_paused = get_worker_status()["paused"]

    pause_worker()

    acquired = worker_lock.acquire(timeout=10)

    if not acquired:
        if not was_paused:
            resume_worker()

        raise HTTPException(
            status_code=409,
            detail={
                "error": "worker_busy",
                "detail": "Could not safely reset while the worker is busy"
            }
        )

    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute("DELETE FROM inbox")
        cursor.execute("DELETE FROM attempts")
        cursor.execute("DELETE FROM messages")

        cursor.execute("""
            DELETE FROM sqlite_sequence
            WHERE name IN ('messages', 'attempts', 'inbox')
        """)

        seed_path = Path(__file__).parent / "data" / "sample-data.json"
        with seed_path.open("r", encoding="utf-8") as seed_file:
            seed = json.load(seed_file)

        for provider in seed["providers"]:
            cursor.execute("""
                INSERT INTO providers
                    (name, channel, priority, fail_rate, outage, consecutive_failures, open_until)
                VALUES (?, ?, ?, ?, ?, 0, NULL)
                ON CONFLICT(name) DO UPDATE SET
                    channel = excluded.channel,
                    priority = excluded.priority,
                    fail_rate = excluded.fail_rate,
                    outage = excluded.outage,
                    consecutive_failures = 0,
                    open_until = NULL
            """, (provider["name"], provider["channel"], provider["priority"],
                  provider["fail_rate"], int(provider["outage"])))

        now = time.time()
        for item in seed["messages"]:
            cursor.execute("""
                INSERT INTO messages
                    (channel, category, recipient, subject, body, status, attempts,
                     next_attempt_at, created_at, idempotency_key)
                VALUES (?, ?, ?, ?, ?, 'pending', 0, ?, ?, NULL)
            """, (item["channel"], item["category"], item["recipient"],
                  item["subject"], item["body"], now, now))

        connection.commit()

        return {
            "message": "Database reset successfully",
            "status": "seeded",
            "providers": len(seed["providers"]),
            "messages": len(seed["messages"])
        }

    except Exception:
        if connection is not None:
            connection.rollback()
        raise

    finally:
        if connection is not None:
            connection.close()

        worker_lock.release()

        if not was_paused:
            resume_worker()
