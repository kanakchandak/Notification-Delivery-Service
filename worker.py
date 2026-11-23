import time
import threading

from database import get_connection, recover_sending_messages
from engine import process_message


POLL_INTERVAL = 1
BATCH_SIZE = 50
LOCK_TIMEOUT = 30

worker_lock = threading.Lock()
stop_event = threading.Event()
worker_thread = None

worker_paused = False
last_tick_at = None
processed_total = 0
recovered_on_start = 0


class WorkerBusyError(Exception):
    """Raised when another worker tick is already running."""
    pass


def get_worker_status():
    return {
        "running": (
            worker_thread is not None
            and worker_thread.is_alive()
        ),
        "paused": worker_paused,
        "last_tick_at": last_tick_at,
        "processed_total": processed_total,
        "recovered_on_start": recovered_on_start
    }


def pause_worker():
    global worker_paused
    worker_paused = True
    return get_worker_status()


def resume_worker():
    global worker_paused
    worker_paused = False
    return get_worker_status()


def run_worker_tick(force=False):
    global last_tick_at, processed_total

    if worker_paused and not force:
        return {
            "processed": 0,
            "sent": 0,
            "failed": 0,
            "retry_scheduled": 0,
            "waiting": 0,
            "paused": True
        }

    if not worker_lock.acquire(blocking=False):
        raise WorkerBusyError(
            "Worker is already processing a batch"
        )

    connection = None

    stats = {
        "processed": 0,
        "sent": 0,
        "failed": 0,
        "retry_scheduled": 0,
        "waiting": 0,
        "paused": worker_paused
    }

    try:
        last_tick_at = time.time()

        connection = get_connection()
        cursor = connection.cursor()

        # Recover messages with expired processing locks.
        old_time = time.time() - LOCK_TIMEOUT

        cursor.execute("""
            UPDATE messages
            SET status = 'pending',
                locked_at = NULL,
                next_attempt_at = ?
            WHERE status = 'sending'
              AND locked_at IS NOT NULL
              AND locked_at <= ?
        """, (time.time(), old_time))

        connection.commit()

        # Transactional messages are processed first.
        cursor.execute("""
            SELECT id
            FROM messages
            WHERE status = 'pending'
              AND next_attempt_at <= ?
            ORDER BY
                CASE category
                    WHEN 'transactional' THEN 1
                    ELSE 2
                END,
                next_attempt_at,
                id
            LIMIT ?
        """, (time.time(), BATCH_SIZE))

        message_ids = [
            row["id"] for row in cursor.fetchall()
        ]

        connection.close()
        connection = None

        for message_id in message_ids:
            try:
                result = process_message(message_id)

                if result == "skipped":
                    continue

                stats["processed"] += 1

                if result == "sent":
                    stats["sent"] += 1
                elif result == "failed":
                    stats["failed"] += 1
                elif result == "pending":
                    stats["retry_scheduled"] += 1
                elif result == "waiting":
                    stats["waiting"] += 1

            except Exception as error:
                print(
                    f"Error processing message "
                    f"{message_id}: {error}"
                )

        processed_total += stats["processed"]
        return stats

    finally:
        if connection is not None:
            connection.close()

        worker_lock.release()


def worker_loop():
    print("DakGhar background worker started")

    while not stop_event.is_set():
        if not worker_paused:
            try:
                run_worker_tick()
            except WorkerBusyError:
                pass
            except Exception as error:
                print(f"Worker error: {error}")

        stop_event.wait(POLL_INTERVAL)

    print("DakGhar background worker stopped")


def start_worker():
    global worker_thread, recovered_on_start

    if worker_thread is not None and worker_thread.is_alive():
        return get_worker_status()

    stop_event.clear()

    recovered_on_start = recover_sending_messages()

    worker_thread = threading.Thread(
        target=worker_loop,
        name="DakGharWorker",
        daemon=True
    )

    worker_thread.start()

    return get_worker_status()


def stop_worker():
    global worker_thread

    stop_event.set()

    if worker_thread is not None:
        worker_thread.join(timeout=5)

        # Keep the reference if the thread has not stopped.
        if worker_thread.is_alive():
            return get_worker_status()

        worker_thread = None

    return get_worker_status()