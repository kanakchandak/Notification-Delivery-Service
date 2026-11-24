import os
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch
import database
import engine

class TestEngine(unittest.TestCase):
    def setUp(self):
        temp_file = tempfile.NamedTemporaryFile(delete=False)
        self.db_path = temp_file.name
        temp_file.close()

        def test_connection():
            connection = sqlite3.connect(self.db_path)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            return connection
        self.test_connection = test_connection
        self.db_patch = patch(
            "database.get_connection",
            side_effect=self.test_connection
        )
        self.db_patch.start()
        database.initialize_database()
        self.engine_patch = patch(
            "engine.get_connection",
            side_effect=self.test_connection
        )
        self.engine_patch.start()
        self.provider_patch = patch("engine.send_message")
        self.mock_provider = self.provider_patch.start()

    def tearDown(self):
        self.provider_patch.stop()
        self.engine_patch.stop()
        self.db_patch.stop()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def create_message(self):
        connection = self.test_connection()
        cursor = connection.cursor()
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
            "email",
            "transactional",
            "demo@example.com",
            "Test subject",
            "Test message",
            "pending",
            0,
            time.time() - 1,
            time.time(),
            "test-key"
        ))

        message_id = cursor.lastrowid

        connection.commit()
        connection.close()
        return message_id

    def get_message(self, message_id):
        connection = self.test_connection()
        cursor = connection.cursor()
        cursor.execute("""
            SELECT *
            FROM messages
            WHERE id = ?
        """, (message_id,))

        message = dict(cursor.fetchone())

        connection.close()
        return message

    def test_successful_delivery(self):
        message_id = self.create_message()
        self.mock_provider.return_value = ("ok", None)
        result = engine.process_message(message_id)
        self.assertEqual(result, "sent")
        message = self.get_message(message_id)
        self.assertEqual(message["status"], "sent")
        self.assertEqual(message["attempts"], 1)

    def test_temporary_failure(self):
        message_id = self.create_message()
        self.mock_provider.return_value = (
            "transient",
            "Temporary failure"
        )

        result = engine.process_message(message_id)
        message = self.get_message(message_id)
        self.assertEqual(result, "pending")
        self.assertEqual(message["status"], "pending")
        self.assertEqual(message["attempts"], 1)

    def test_permanent_failure(self):
        message_id = self.create_message()
        self.mock_provider.return_value = (
            "permanent",
            "Invalid recipient"
        )

        result = engine.process_message(message_id)
        message = self.get_message(message_id)
        self.assertEqual(result, "failed")
        self.assertEqual(message["status"], "failed")

    def test_provider_failover(self):
        message_id = self.create_message()
        self.mock_provider.side_effect = [
            ("transient", "Temporary failure"),
            ("ok", None)
        ]

        first_result = engine.process_message(message_id)
        self.assertEqual(first_result, "pending")

        connection = self.test_connection()
        cursor = connection.cursor()
        cursor.execute("""
            UPDATE messages
            SET next_attempt_at = ?
            WHERE id = ?
        """, (time.time() - 1, message_id))

        connection.commit()
        connection.close()

        second_result = engine.process_message(message_id)
        self.assertEqual(second_result, "sent")
        second_provider = self.mock_provider.call_args_list[1][0][0]
        self.assertEqual(second_provider["name"], "postbird")

    def test_retry_limit(self):
        message_id = self.create_message()
        self.mock_provider.return_value = (
            "transient",
            "Temporary failure"
        )

        for attempt in range(4):
            connection = self.test_connection()
            cursor = connection.cursor()
            cursor.execute("""
                UPDATE messages
                SET next_attempt_at = ?
                WHERE id = ?
            """, (time.time() - 1, message_id))

            connection.commit()
            connection.close()

            result = engine.process_message(message_id)

        self.assertEqual(result, "failed")
        message = self.get_message(message_id)
        self.assertEqual(message["status"], "failed")
        self.assertEqual(message["attempts"], 4)


    def test_manual_retry_keeps_unique_history_numbers(self):
        message_id = self.create_message()
        self.mock_provider.return_value = ("ok", None)
        self.assertEqual(engine.process_message(message_id), "sent")
        connection = self.test_connection()
        connection.execute("UPDATE messages SET status='pending', attempts=0, sent_at=NULL WHERE id=?", (message_id,))
        connection.commit()
        connection.close()
        self.assertEqual(engine.process_message(message_id), "sent")
        connection = self.test_connection()
        numbers = [row[0] for row in connection.execute("SELECT attempt_no FROM attempts WHERE message_id=? ORDER BY id", (message_id,))]
        connection.close()
        self.assertEqual(numbers, [1, 2])

if __name__ == "__main__":
    unittest.main()
