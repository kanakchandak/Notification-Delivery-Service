import os
import sqlite3
import tempfile
from unittest.mock import patch

from fastapi.testclient import TestClient

import database
import main


def make_connection_factory(path):
    def connect():
        conn = sqlite3.connect(path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    return connect


def test_authentication_and_reset_seed(monkeypatch):
    handle = tempfile.NamedTemporaryFile(delete=False)
    path = handle.name
    handle.close()
    factory = make_connection_factory(path)
    monkeypatch.setenv("ADMIN_KEY", "test-admin")
    monkeypatch.setenv("SENDER_KEY", "test-sender")
    monkeypatch.setattr(database, "get_connection", factory)
    monkeypatch.setattr(main, "get_connection", factory)
    monkeypatch.setattr(main, "start_worker", lambda: None)
    monkeypatch.setattr(main, "stop_worker", lambda: None)

    try:
        with TestClient(main.app) as client:
            assert client.get("/api/messages").status_code == 401
            assert client.get("/api/messages", headers={"X-Api-Key": "wrong"}).status_code == 403
            initial = client.get("/api/messages", headers={"X-Api-Key": "test-sender"})
            assert initial.status_code == 200
            assert initial.json()["count"] == 5
            assert client.post("/api/admin/reset", headers={"X-Api-Key": "test-sender"}).status_code == 403
            response = client.post("/api/admin/reset", headers={"X-Admin-Key": "test-admin"})
            assert response.status_code == 200
            assert response.json()["messages"] == 5
            assert response.json()["providers"] == 4
            listing = client.get("/api/messages", headers={"X-Api-Key": "test-sender"}).json()
            assert listing["count"] == 5
            assert "***@" in listing["messages"][0]["recipient"] or "*" in listing["messages"][0]["recipient"]
            detail = client.get("/api/messages/1", headers={"X-Api-Key": "test-sender"}).json()
            assert detail["message"]["recipient"] == "ritu@shop.example"
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_idempotency_and_conflict(monkeypatch):
    handle = tempfile.NamedTemporaryFile(delete=False)
    path = handle.name
    handle.close()
    factory = make_connection_factory(path)
    monkeypatch.setenv("ADMIN_KEY", "test-admin")
    monkeypatch.setenv("SENDER_KEY", "test-sender")
    monkeypatch.setattr(database, "get_connection", factory)
    monkeypatch.setattr(main, "get_connection", factory)
    monkeypatch.setattr(main, "start_worker", lambda: None)
    monkeypatch.setattr(main, "stop_worker", lambda: None)
    payload = {"channel":"email","category":"transactional","to":"a@example.com","subject":"Hello","body":"Test","idempotency_key":"same-key"}
    try:
        with TestClient(main.app) as client:
            headers={"X-Api-Key":"test-sender"}
            first=client.post("/api/messages",json=payload,headers=headers)
            second=client.post("/api/messages",json=payload,headers=headers)
            assert first.status_code == 201
            assert second.status_code == 200
            changed={**payload,"body":"Different"}
            assert client.post("/api/messages",json=changed,headers=headers).status_code == 409
    finally:
        if os.path.exists(path):
            os.remove(path)
