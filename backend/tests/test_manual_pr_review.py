"""End-to-end manual PR review endpoints without live GitHub or DeepSeek calls."""
from fastapi.testclient import TestClient

from backend import main, pr_review, storage


class FakeGitHub:
    def app_jwt(self):
        return "test-jwt"

    def installation_token(self, ident):
        assert ident == 41
        return "test-installation"

    def request(self, method, path, token, *, params=None, json=None):
        assert method == "GET"
        if path == "/repos/example/demo/installation":
            return {"id": 41}
        if path == "/repos/example/demo":
            return {"full_name": "example/demo", "default_branch": "main"}
        if path == "/repos/example/demo/pulls":
            return [{
                "number": 7, "title": "Modify authorization",
                "head": {"sha": "b" * 40}, "user": {"login": "tester"},
                "html_url": "https://github.com/example/demo/pull/7", "draft": False,
            }]
        if path == "/repos/example/demo/pulls/7":
            return {
                "number": 7, "state": "open", "title": "Modify authorization",
                "head": {"sha": "b" * 40}, "base": {
                    "sha": "a" * 40,
                    "repo": {"full_name": "example/demo"},
                }, "user": {"login": "tester"}, "changed_files": 1,
            }
        raise AssertionError(f"Unexpected endpoint {path}")

    def close(self):
        pass


def test_manual_pr_review_api(monkeypatch, tmp_path):
    old_db = storage.settings.db_path
    old_token = main.settings.dashboard_token
    object.__setattr__(storage.settings, "db_path", str(tmp_path / "reviews.db"))
    object.__setattr__(main.settings, "dashboard_token", "test-secret")
    monkeypatch.setattr(pr_review, "GitHubApi", FakeGitHub)
    called = []

    def processor(review_id, payload):
        called.append((review_id, payload["pull_request"]["head"]["sha"]))
        storage.update_review(review_id, "COMPLETED", report={
            "risk_level": "HIGH", "merge_recommendation": "REVIEW_REQUIRED",
            "summary": "Potential permission regression", "findings": [],
        })

    monkeypatch.setattr(pr_review, "process_pr", processor)
    try:
        with TestClient(main.app) as client:
            url = "/api/repositories/example/demo/pulls"
            assert client.get(url).status_code == 401
            assert client.post(url + "/7/analyze").status_code == 401
            headers = {"Authorization": "Bearer test-secret"}
            result = client.get(url, headers=headers)
            assert result.status_code == 200
            assert result.json()["pull_requests"][0]["number"] == 7
            review = client.post(url + "/7/analyze", headers=headers)
            assert review.status_code == 202
            assert review.json()["pr_number"] == 7
            assert called[0][1] == "b" * 40
            assert storage.get_review(review.json()["review_id"])["status"] == "COMPLETED"
    finally:
        object.__setattr__(storage.settings, "db_path", old_db)
        object.__setattr__(main.settings, "dashboard_token", old_token)


def test_bad_pr_number_rejected(monkeypatch, tmp_path):
    old_db = storage.settings.db_path
    old_token = main.settings.dashboard_token
    object.__setattr__(storage.settings, "db_path", str(tmp_path / "invalid.db"))
    object.__setattr__(main.settings, "dashboard_token", "test-secret")
    monkeypatch.setattr(pr_review, "GitHubApi", FakeGitHub)
    try:
        with TestClient(main.app) as client:
            h = {"Authorization": "Bearer test-secret"}
            assert client.post("/api/repositories/example/demo/pulls/0/analyze", headers=h).status_code == 400
    finally:
        object.__setattr__(storage.settings, "db_path", old_db)
        object.__setattr__(main.settings, "dashboard_token", old_token)
