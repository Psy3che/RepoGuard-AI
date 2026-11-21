"""Manual scan API and persistence tests: no live GitHub or DeepSeek calls."""
from fastapi.testclient import TestClient

from backend import main, manual_scan, storage


class FakeGitHubApi:
    def app_jwt(self):
        return "test-jwt"

    def installation_token(self, installation_id):
        assert installation_id == 42
        return "test-installation-token"

    def request(self, method, path, token, *, params=None, json=None):
        assert method == "GET"
        if path == "/repos/testowner/testrepo/installation":
            return {"id": 42}
        if path == "/repos/testowner/testrepo":
            return {"full_name": "testowner/testrepo", "default_branch": "main"}
        if path == "/repos/testowner/testrepo/commits/main":
            return {"sha": "a" * 40}
        raise AssertionError(f"Unexpected GitHub request: {path}")

    def close(self):
        pass


def _prepare(monkeypatch, tmp_path):
    old_db = storage.settings.db_path
    old_token = main.settings.dashboard_token
    object.__setattr__(storage.settings, "db_path", str(tmp_path / "scan-test.db"))
    object.__setattr__(main.settings, "dashboard_token", "test-dashboard-token")
    monkeypatch.setattr(manual_scan, "GitHubApi", FakeGitHubApi)
    return old_db, old_token


def _restore(old_db, old_token):
    object.__setattr__(storage.settings, "db_path", old_db)
    object.__setattr__(main.settings, "dashboard_token", old_token)


def test_manual_scan_authenticated_and_persisted(monkeypatch, tmp_path):
    old_db, old_token = _prepare(monkeypatch, tmp_path)
    calls = []

    def fake_build_map(owner, repo, base_sha, api, token):
        calls.append((owner, repo, base_sha, token))
        return {
            "ai_status": "OK", "coverage": {"total_files_indexed": 4, "source_files_sampled": 2},
            "critical_modules": [{"file": "src/auth.py", "importance": "CRITICAL",
                                  "reason": "authorization boundary"}],
            "dependency_edges": [],
        }

    monkeypatch.setattr(manual_scan, "build_repo_map", fake_build_map)
    try:
        with TestClient(main.app) as client:
            url = "/api/repositories/testowner/testrepo/scan"
            assert client.get(url).status_code == 401
            assert client.post(url).status_code == 401
            headers = {"Authorization": "Bearer test-dashboard-token"}
            assert client.get(url, headers=headers).json()["status"] == "IDLE"
            result = client.post(url, headers=headers)
            assert result.status_code == 202
            assert result.json()["created"] is True
            assert result.json()["status"] == "PENDING"
            # TestClient runs FastAPI background tasks before returning.
            status = client.get(url, headers=headers).json()
            assert status["status"] == "COMPLETED"
            assert status["scan_id"] == result.json()["scan_id"]
            saved = storage.get_map("testowner/testrepo", "a" * 40)
            assert saved["ai_status"] == "OK"
            assert saved["critical_modules"][0]["file"] == "src/auth.py"
            assert saved["scanned_at"]
            assert calls == [("testowner", "testrepo", "a" * 40, "test-installation-token")]
    finally:
        _restore(old_db, old_token)


def test_failed_ai_scan_does_not_claim_live_map(monkeypatch, tmp_path):
    old_db, old_token = _prepare(monkeypatch, tmp_path)
    monkeypatch.setattr(manual_scan, "build_repo_map", lambda *a, **k: {
        "ai_status": "UNAVAILABLE",
        "coverage": {"source_files_sampled": 1},
    })
    try:
        with TestClient(main.app) as client:
            url = "/api/repositories/testowner/testrepo/scan"
            headers = {"Authorization": "Bearer test-dashboard-token"}
            assert client.post(url, headers=headers).status_code == 202
            status = client.get(url, headers=headers).json()
            assert status["status"] == "FAILED"
            assert status["error"] == "DeepSeek architecture analysis unavailable (UnknownError)"
            assert storage.get_map("testowner/testrepo") is None
    finally:
        _restore(old_db, old_token)


def test_parallel_scan_claims_are_deduplicated(tmp_path):
    old_db = storage.settings.db_path
    object.__setattr__(storage.settings, "db_path", str(tmp_path / "dedup.db"))
    try:
        storage.init_db()
        a, created1 = storage.claim_scan("testowner/testrepo", "a" * 40)
        b, created2 = storage.claim_scan("testowner/testrepo", "a" * 40)
        assert created1
        assert not created2
        assert a["id"] == b["id"]
        storage.update_scan(a["id"], "COMPLETED")
        c, created3 = storage.claim_scan("testowner/testrepo", "a" * 40)
        assert created3
        assert c["id"] != a["id"]
    finally:
        object.__setattr__(storage.settings, "db_path", old_db)
