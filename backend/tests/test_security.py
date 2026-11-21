import hashlib
import hmac
from backend.security import verify_signature, safe_source_path, scrub_text


def test_webhook_signature():
    body = b'{"action":"opened"}'
    signature = "sha256=" + hmac.new(b"demo-secret", body, hashlib.sha256).hexdigest()
    assert verify_signature(body, signature, "demo-secret")
    assert not verify_signature(body + b" ", signature, "demo-secret")
    assert not verify_signature(body, "", "demo-secret")
    assert not verify_signature(body, signature, "wrong")


def test_sensitive_files_excluded():
    assert safe_source_path("src/auth.py")
    assert safe_source_path("lib/handler.ts")
    assert not safe_source_path(".env")
    assert not safe_source_path("src/.env.local")
    assert not safe_source_path("../secrets/config.py")
    assert not safe_source_path("node_modules/index.js")
    assert not safe_source_path("config/credentials.json")
    assert not safe_source_path("keys/private.pem")


def test_secret_scrubbing():
    text = 'API_KEY="very-secret-value"\npassword = somethingsecret\nAuthorization: Bearer verylongtokenvaluehere'
    filtered = scrub_text(text)
    assert "very-secret-value" not in filtered
    assert "somethingsecret" not in filtered
    assert "verylongtokenvaluehere" not in filtered
