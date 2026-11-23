import json
import os
import sqlite3
import time
from pathlib import Path

DATABASE_NAME = os.getenv("DATABASE_PATH", str(Path(__file__).with_name("notifications.db")))


def get_connection():
    connection = sqlite3.connect(
        DATABASE_NAME,
        timeout=30
    )

    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")

    return connection


def initialize_database():
    connection = get_connection()

    try:
        cursor = connection.cursor()
        cursor.execute("""
            SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = 'messages'
        """)
        first_initialization = cursor.fetchone() is None

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL,
                category TEXT NOT NULL,
                recipient TEXT NOT NULL,
                subject TEXT,
                body TEXT NOT NULL,
                status TEXT NOT NULL
                    CHECK(status IN (
                        'pending', 'sending', 'sent', 'failed'
                    )),
                attempts INTEGER DEFAULT 0,
                next_attempt_at REAL NOT NULL,
                created_at REAL NOT NULL,
                sent_at REAL,
                provider TEXT,
                last_failed_provider TEXT,
                last_error TEXT,
                locked_at REAL,
                idempotency_key TEXT UNIQUE
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_due
            ON messages(status, next_attempt_at)
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS providers (
                name TEXT PRIMARY KEY,
                channel TEXT NOT NULL
                    CHECK(channel IN ('email', 'sms')),
                priority INTEGER NOT NULL
                    CHECK(priority IN (1, 2)),
                fail_rate REAL NOT NULL
                    CHECK(fail_rate >= 0 AND fail_rate <= 0.5),
                outage INTEGER NOT NULL DEFAULT 0
                    CHECK(outage IN (0, 1)),
                consecutive_failures INTEGER NOT NULL DEFAULT 0,
                open_until REAL
            )
        """)

        cursor.executemany("""
            INSERT OR IGNORE INTO providers
            (name, channel, priority, fail_rate, outage)
            VALUES (?, ?, ?, ?, ?)
        """, [
            ("mailfast", "email", 1, 0.03, 0),
            ("postbird", "email", 2, 0.03, 0),
            ("smsly", "sms", 1, 0.03, 0),
            ("textgo", "sms", 2, 0.03, 0)
        ])

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL
                    REFERENCES messages(id),
                attempt_no INTEGER NOT NULL,
                provider TEXT NOT NULL
                    REFERENCES providers(name),
                at REAL NOT NULL,
                result TEXT NOT NULL
                    CHECK(result IN ('ok', 'transient', 'permanent')),
                error TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL
                    REFERENCES messages(id),
                provider TEXT NOT NULL
                    REFERENCES providers(name),
                recipient TEXT NOT NULL,
                subject TEXT,
                body TEXT NOT NULL,
                delivered_at REAL NOT NULL,
                UNIQUE(provider, message_id)
            )
        """)

        if first_initialization:
            seed_path = Path(__file__).parent / "data" / "sample-data.json"
            with seed_path.open("r", encoding="utf-8") as seed_file:
                seed = json.load(seed_file)
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

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def recover_sending_messages():
    """
    Recover messages left in 'sending' status after a restart.
    """

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            UPDATE messages
            SET status = 'pending',
                next_attempt_at = ?,
                locked_at = NULL
            WHERE status = 'sending'
        """, (time.time(),))

        recovered_count = cursor.rowcount

        connection.commit()

        return recovered_count

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()