"""Run a deterministic, isolated queue simulation (default: 10,000 messages)."""
import argparse
import os
import random
import sys
from pathlib import Path
import sqlite3
import statistics
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database
import engine


def connection_factory(path):
    def connect():
        conn = sqlite3.connect(path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn
    return connect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if not 1 <= args.count <= 100000:
        parser.error("--count must be between 1 and 100000")

    rng = random.Random(args.seed)
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    db_path = handle.name
    handle.close()
    factory = connection_factory(db_path)
    started = time.perf_counter()
    failover_candidates = set()
    try:
        with patch.object(database, "get_connection", side_effect=factory), \
             patch.object(engine, "get_connection", side_effect=factory):
            database.initialize_database()
            conn = factory()
            conn.execute("DELETE FROM messages")
            conn.execute("DELETE FROM sqlite_sequence WHERE name='messages'")
            now = time.time()
            rows = []
            for i in range(args.count):
                recipient = f"customer{i}@shop.example"
                if i % 200 == 0:
                    recipient = f"bounce{i}@bounce.example"
                category = "transactional" if rng.random() < 0.67 else "marketing"
                rows.append(("email", category,
                             recipient, "Simulation", f"Notification {i}",
                             "pending", 0, now, now, None))
                if i % 100 == 0 and i % 200 != 0:
                    failover_candidates.add(i + 1)
            conn.executemany("""
                INSERT INTO messages
                (channel, category, recipient, subject, body, status, attempts,
                 next_attempt_at, created_at, idempotency_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, rows)
            conn.commit()
            conn.close()

            original_send = engine.send_message
            def deterministic_send(provider, message):
                recipient = message["recipient"]
                if recipient.endswith("@bounce.example"):
                    return "permanent", "bounced: recipient does not exist"
                if message["id"] in failover_candidates and provider["priority"] == 1:
                    failover_candidates.remove(message["id"])
                    return "transient", "503 provider unavailable"
                return "ok", None

            with patch.object(engine, "send_message", side_effect=deterministic_send):
                conn = factory()
                ids = [r[0] for r in conn.execute("SELECT id FROM messages ORDER BY id")]
                conn.close()
                for message_id in ids:
                    engine.process_message(message_id)
                conn = factory()
                conn.execute("UPDATE messages SET next_attempt_at = ? WHERE status = 'pending'", (time.time() - 1,))
                conn.commit()
                retry_ids = [r[0] for r in conn.execute("SELECT id FROM messages WHERE status = 'pending'")]
                conn.close()
                for message_id in retry_ids:
                    engine.process_message(message_id)

            conn = factory()
            totals = dict(conn.execute("SELECT status, COUNT(*) FROM messages GROUP BY status").fetchall())
            totals = {key: totals.get(key, 0) for key in ("sent", "failed", "pending", "sending")}
            attempt_count = conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
            failover_count = conn.execute("""
                SELECT COUNT(*) FROM attempts a
                WHERE a.result='transient' AND EXISTS (
                    SELECT 1 FROM attempts b
                    WHERE b.message_id=a.message_id AND b.attempt_no>a.attempt_no AND b.result='ok'
                )
            """).fetchone()[0]
            delays = [r[0] for r in conn.execute("SELECT sent_at-created_at FROM messages WHERE status='sent'")]
            conn.close()

        elapsed = time.perf_counter() - started
        delays.sort()
        def percentile(values, p):
            if not values:
                return 0.0
            return values[min(len(values)-1, int((len(values)-1)*p))]
        print(f"DakGhar simulation | seed={args.seed} | submitted={args.count}")
        print("\nReconciliation")
        print("Submitted | Sent | Failed | Pending | Sending")
        print(f"{args.count:9d} | {totals['sent']:4d} | {totals['failed']:6d} | {totals['pending']:7d} | {totals['sending']:7d}")
        print(f"Attempts recorded: {attempt_count}")
        print(f"Messages with transient failure followed by successful failover: {failover_count}")
        print(f"Delivery delay seconds: p50={percentile(delays,.50):.4f}, p95={percentile(delays,.95):.4f}, max={max(delays, default=0):.4f}")
        print(f"Wall-clock simulation time: {elapsed:.2f}s")
        print("Trade-offs: the deterministic mock makes runs reproducible; this is a local SQLite throughput simulation, not a production load test.")
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    main()
