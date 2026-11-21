import hashlib
import hmac
import json
import uuid
from fastapi.testclient import TestClient

from backend import storage, main


def signed_headers(secret, body, event, delivery=None):
    return {
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": delivery or str(uuid.uuid4()),
        "X-Hub-Signature-256": "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(),
        "Content-Type": "application/json",
    }


def test_webhook_and_dashboard_security(tmp_path, monkeypatch):
    object.__setattr__(storage.settings, "db_path", str(tmp_path / "test.db"))
    object.__setattr__(main.settings, "webhook_secret", "a-test-secret")
    object.__setattr__(main.settings, "dashboard_token", "a-test-dashboard-token")
    handled = []
    monkeypatch.setattr(main, "process_pr", lambda review_id, payload: handled.append(review_id))
    with TestClient(main.app) as client:
        assert client.get("/health").json()["status"] == "ok"
        assert client.get("/api/reviews").status_code == 401
        bad = client.post("/webhook", content=b'{}', headers={"X-GitHub-Event": "ping"})
        assert bad.status_code == 401
        body = json.dumps({"zen": "ok"}).encode()
        response = client.post("/webhook", content=body, headers=signed_headers("a-test-secret", body, "ping"))
        assert response.status_code == 202
        assert response.json()["status"] == "pong"
        payload = {
            "action": "opened", "installation": {"id": 1},
            "repository": {"full_name": "demo/repo"},
            "pull_request": {"number": 4, "head": {"sha": "a"*40}},
        }
        raw = json.dumps(payload).encode()
        headers = signed_headers("a-test-secret", raw, "pull_request")
        result = client.post("/webhook", content=raw, headers=headers)
        assert result.status_code == 202
        assert result.json()["status"] == "accepted"
        assert len(handled) == 1
        assert client.post("/webhook", content=raw, headers=headers).json()["status"] == "duplicate_ignored"
        response = client.get("/api/reviews", headers={"Authorization": "Bearer a-test-dashboard-token"})
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1
