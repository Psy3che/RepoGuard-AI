"""Sends a locally signed test ping. Launch uvicorn first."""
import hashlib
import hmac
import json
import os
import uuid
import httpx
from dotenv import load_dotenv

load_dotenv()
secret = os.environ["GITHUB_WEBHOOK_SECRET"]
body = json.dumps({"zen": "RepoGuard ping"}).encode()
signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
response = httpx.post("http://127.0.0.1:8000/webhook", content=body, headers={
    "X-Hub-Signature-256": signature,
    "X-GitHub-Event": "ping",
    "X-GitHub-Delivery": str(uuid.uuid4()),
    "Content-Type": "application/json",
})
print(response.status_code, response.text)
