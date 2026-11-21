"""Small SQLite persistence layer: survives local restarts for demo reliability."""
import json
import sqlite3
from datetime import datetime, timezone
from threading import RLock
from backend.config import settings

_LOCK = RLock()


def _db():
    conn = sqlite3.connect(settings.db_path, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _LOCK, _db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS deliveries (
            delivery_id TEXT PRIMARY KEY,
            received_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS repo_maps (
            repo TEXT NOT NULL,
            base_sha TEXT NOT NULL,
            data_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (repo, base_sha)
        );
        CREATE TABLE IF NOT EXISTS reviews (
            id TEXT PRIMARY KEY,
            repo TEXT NOT NULL,
            pr_number INTEGER NOT NULL,
            head_sha TEXT NOT NULL,
            status TEXT NOT NULL,
            report_json TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """)


def now():
    return datetime.now(timezone.utc).isoformat()


def first_delivery(delivery_id: str) -> bool:
    with _LOCK, _db() as conn:
        try:
            conn.execute("INSERT INTO deliveries VALUES (?, ?)", (delivery_id, now()))
            return True
        except sqlite3.IntegrityError:
            return False


def save_map(repo: str, base_sha: str, value: dict):
    with _LOCK, _db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO repo_maps VALUES (?, ?, ?, ?)",
            (repo, base_sha, json.dumps(value, ensure_ascii=False), now()),
        )


def get_map(repo: str, base_sha: str | None = None):
    with _db() as conn:
        if base_sha:
            row = conn.execute(
                "SELECT * FROM repo_maps WHERE repo=? AND base_sha=?", (repo, base_sha)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM repo_maps WHERE repo=? ORDER BY updated_at DESC LIMIT 1", (repo,)
            ).fetchone()
    return json.loads(row["data_json"]) if row else None


def new_review(review_id: str, repo: str, pr_number: int, head_sha: str):
    with _LOCK, _db() as conn:
        conn.execute("INSERT INTO reviews VALUES (?,?,?,?,?,?,?,?,?)", (
            review_id, repo, pr_number, head_sha, "PENDING", None, None, now(), now()
        ))


def update_review(review_id: str, status: str, report: dict | None = None, error: str | None = None):
    with _LOCK, _db() as conn:
        conn.execute(
            "UPDATE reviews SET status=?, report_json=?, error=?, updated_at=? WHERE id=?",
            (status, json.dumps(report, ensure_ascii=False) if report else None, error, now(), review_id)
        )


def _serialize(row):
    result = dict(row)
    raw = result.pop("report_json")
    result["report"] = json.loads(raw) if raw else None
    return result


def get_review(review_id: str):
    with _db() as conn:
        row = conn.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone()
    return _serialize(row) if row else None


def list_reviews(repo: str | None, limit: int = 30):
    with _db() as conn:
        if repo:
            rows = conn.execute(
                "SELECT * FROM reviews WHERE repo=? ORDER BY created_at DESC LIMIT ?", (repo, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM reviews ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
    return [_serialize(x) for x in rows]
