import time

from database import get_connection
from providers import send_message

MAX_ATTEMPTS = 4

RETRY_DELAYS = [2, 4, 8]

CIRCUIT_BREAKER_LIMIT = 2
CIRCUIT_BREAKER_TIME = 30


def get_provider(connection, channel, last_failed_provider):
    cursor = connection.cursor()
    current_time = time.time()

    cursor.execute("""
    SELECT *
    FROM providers
    WHERE channel = ?
    AND outage = 0
    AND (open_until IS NULL OR open_until <= ?)
    ORDER BY priority
    """, (channel, current_time))

    providers = cursor.fetchall()

    if not providers:
        return None

    for provider in providers:
        if provider["name"] != last_failed_provider:
            return provider

    return providers[0]


def process_message(message_id):
    connection = get_connection()

    try:
        cursor = connection.cursor()
        current_time = time.time()

        cursor.execute("""
            SELECT *
            FROM messages
            WHERE id = ?
            AND status = 'pending'
            AND next_attempt_at <= ?
        """, (message_id, current_time))

        message = cursor.fetchone()

        if message is None:
            return "skipped"

        cursor.execute("""
            UPDATE messages
            SET status = 'sending',
                locked_at = ?
            WHERE id = ?
            AND status = 'pending'
        """, (current_time, message_id))

        if cursor.rowcount == 0:
            connection.rollback()
            return "skipped"

        connection.commit()

        provider = get_provider(
            connection,
            message["channel"],
            message["last_failed_provider"]
        )

        if provider is None:
            cursor.execute("""
                SELECT MIN(open_until)
                FROM providers
                WHERE channel = ?
                  AND outage = 0
                  AND open_until > ?
            """, (message["channel"], time.time()))

            next_time = cursor.fetchone()[0]

            if next_time is None:
                next_time = time.time() + 5

            cursor.execute("""
                UPDATE messages
                SET status = 'pending',
                    next_attempt_at = ?,
                    locked_at = NULL
                WHERE id = ?
            """, (next_time, message_id))

            connection.commit()
            return "waiting"

        result, error = send_message(provider, message)

        attempt_number = message["attempts"] + 1
        attempt_time = time.time()
        cursor.execute("""
            SELECT COALESCE(MAX(attempt_no), 0) + 1
            FROM attempts
            WHERE message_id = ?
        """, (message_id,))
        history_attempt_number = cursor.fetchone()[0]

        cursor.execute("""
            INSERT INTO attempts (
                message_id,
                attempt_no,
                provider,
                at,
                result,
                error
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            message_id,
            history_attempt_number,
            provider["name"],
            attempt_time,
            result,
            error
        ))

        if result == "ok":

            cursor.execute("""
                UPDATE messages
                SET status = 'sent',
                    attempts = ?,
                    sent_at = ?,
                    provider = ?,
                    last_error = NULL,
                    locked_at = NULL
                WHERE id = ?
            """, (
                attempt_number,
                attempt_time,
                provider["name"],
                message_id
            ))

            cursor.execute("""
                INSERT OR IGNORE INTO inbox (
                    message_id,
                    provider,
                    recipient,
                    subject,
                    body,
                    delivered_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                message_id,
                provider["name"],
                message["recipient"],
                message["subject"],
                message["body"],
                attempt_time
            ))

            cursor.execute("""
                UPDATE providers
                SET consecutive_failures = 0,
                    open_until = NULL
                WHERE name = ?
            """, (provider["name"],))

            connection.commit()
            return "sent"

        elif result == "permanent":

            cursor.execute("""
                UPDATE messages
                SET status = 'failed',
                    attempts = ?,
                    last_failed_provider = ?,
                    last_error = ?,
                    locked_at = NULL
                WHERE id = ?
            """, (
                attempt_number,
                provider["name"],
                error,
                message_id
            ))

            cursor.execute("""
                UPDATE providers
                SET consecutive_failures = 0,
                    open_until = NULL
                    WHERE name = ?
            """, (provider["name"],))

            connection.commit()
            return "failed"

        elif result == "transient":

            cursor.execute("""
                SELECT consecutive_failures
                FROM providers
                WHERE name = ?
            """, (provider["name"],))

            failures = cursor.fetchone()["consecutive_failures"] + 1

            open_until = None
            if failures >= CIRCUIT_BREAKER_LIMIT:
                open_until = attempt_time + CIRCUIT_BREAKER_TIME

            cursor.execute("""
                UPDATE providers
                SET consecutive_failures = ?,
                    open_until = ?
                WHERE name = ?
            """, (
                failures,
                open_until,
                provider["name"]
            ))

            if attempt_number >= MAX_ATTEMPTS:

                cursor.execute("""
                    UPDATE messages
                    SET status = 'failed',
                        attempts = ?,
                        last_failed_provider = ?,
                        last_error = ?,
                        locked_at = NULL
                    WHERE id = ?
                """, (
                    attempt_number,
                    provider["name"],
                    f"gave up after {MAX_ATTEMPTS} attempts: {error}",
                    message_id
                ))

                connection.commit()
                return "failed"
            
            retry_delay = RETRY_DELAYS[attempt_number - 1]

            cursor.execute("""
                UPDATE messages
                SET status = 'pending',
                    attempts = ?,
                    next_attempt_at = ?,
                    last_failed_provider = ?,
                    last_error = ?,
                    locked_at = NULL
                WHERE id = ?
            """, (
                attempt_number,
                attempt_time + retry_delay,
                provider["name"],
                error,
                message_id
            ))

            connection.commit()
            return "pending"

        else:
            raise ValueError("Unknown provider result")

    except Exception:
        connection.rollback()

        cursor.execute("""
            UPDATE messages
            SET status = 'pending',
                next_attempt_at = ?,
                locked_at = NULL
            WHERE id = ?
            AND status = 'sending'
        """, (time.time() + 5, message_id))

        connection.commit()
        raise

    finally:
        connection.close()
