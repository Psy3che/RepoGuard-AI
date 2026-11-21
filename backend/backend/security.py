"""Webhook verification and conservative filtering of repository contents."""
import hashlib
import hmac
import re
from pathlib import PurePosixPath

EXCLUDED_PARTS = {
    ".git", "node_modules", ".venv", "venv", "vendor", "dist",
    "build", ".next", "coverage", "__pycache__", "target",
    ".terraform", "generated", "third_party"
}
SOURCE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go",
    ".rs", ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".rb",
    ".php", ".swift", ".kt", ".sql", ".yaml", ".yml", ".toml",
    ".json"
}
CREDENTIAL_NAME = re.compile(
    r"(^|[._/-])(secret|secrets|credential|credentials|private|id_rsa|id_ed25519|token|keyfile)([._/-]|$)",
    re.IGNORECASE,
)
SECRET_VALUE = re.compile(
    r"(?i)((?:[a-z0-9_]*(?:api[_-]?key|access[_-]?token|secret|password|authorization|private[_-]?key)[a-z0-9_]*)\s*[:=]\s*)"
    r"([^\s,\]\}\"']{6,}|[\"'][^\"'\n]{6,}[\"'])"
)
AUTH_HEADER = re.compile(r"(?i)(Bearer\s+)[a-z0-9._~+/-]{12,}")
TOKEN_LITERAL = re.compile(r"(?i)\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16})\b")
PEM_BLOCK = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL)


def verify_signature(body: bytes, signature: str, secret: str) -> bool:
    if not secret or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def safe_source_path(path: str) -> bool:
    if not path or path.startswith("/") or "\\" in path or "\x00" in path:
        return False
    parts = PurePosixPath(path).parts
    if ".." in parts or any(p in EXCLUDED_PARTS for p in parts):
        return False
    name = parts[-1].lower()
    if name.startswith(".env") or name in {"docker-compose.override.yml", "config.local.json"}:
        return False
    if CREDENTIAL_NAME.search(path):
        return False
    return PurePosixPath(path).suffix.lower() in SOURCE_EXTENSIONS


def scrub_text(text: str) -> str:
    text = PEM_BLOCK.sub("[REDACTED_PRIVATE_KEY]", text)
    text = AUTH_HEADER.sub(r"\1[REDACTED]", text)
    text = SECRET_VALUE.sub(lambda m: m.group(1) + "[REDACTED]", text)
    return TOKEN_LITERAL.sub("[REDACTED_TOKEN]", text)
