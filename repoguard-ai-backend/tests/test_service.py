from backend import analyzer, service, storage


class FakeGitHub:
    checks = []

    def installation_token(self, installation_id):
        assert installation_id == 43
        return "fake-installation-token"

    def create_check(self, owner, repo, sha, token):
        assert (owner, repo) == ("demo", "project")
        assert sha == "b" * 40
        return 91

    def repo_tree(self, owner, repo, sha, token):
        assert sha == "a" * 40
        return {"truncated": False, "tree": [
            {"type": "blob", "path": "src/auth.py", "size": 120, "sha": "c" * 40},
            {"type": "blob", "path": "src/order.py", "size": 200, "sha": "d" * 40},
        ]}

    def blob_text(self, owner, repo, sha, token):
        return "def verify_token(t):\n    return bool(t)\n"

    def pull_files(self, owner, repo, number, token, limit):
        assert number == 4
        return [{"filename": "src/auth.py", "status": "modified", "patch": "@@ -1 +1 @@\n-return bool(t)\n+return {'ok': bool(t)}"}]

    def complete_check(self, owner, repo, check_id, token, report):
        self.checks.append((check_id, report["risk_level"]))

    def close(self):
        pass


def test_full_mocked_pr_pipeline(tmp_path, monkeypatch):
    object.__setattr__(storage.settings, "db_path", str(tmp_path / "endtoend.db"))
    storage.init_db()
    FakeGitHub.checks = []
    monkeypatch.setattr(service, "GitHubApi", FakeGitHub)

    def mock_model(_system, payload):
        if "sources" in payload:
            return {"project_summary": "E-commerce backend", "critical_modules": [{"file": "src/auth.py", "importance": "CRITICAL", "reason": "Verifies tokens"}], "architecture_notes": []}
        return {"risk_level": "HIGH", "summary": "Potential incompatible return type", "affected_files": ["src/auth.py"], "findings": [{"file": "src/auth.py", "severity": "HIGH", "reason": "Check API callers", "recommendation": "Run regression tests"}], "recommendations": ["Run tests"]}

    monkeypatch.setattr(analyzer, "ai_json", mock_model)
    payload = {
        "installation": {"id": 43},
        "repository": {"owner": {"login": "demo"}, "name": "project"},
        "pull_request": {"number": 4, "base": {"sha": "a" * 40}, "head": {"sha": "b" * 40}, "changed_files": 1},
    }
    storage.new_review("test-full", "demo/project", 4, "b" * 40)
    service.process_pr("test-full", payload)
    review = storage.get_review("test-full")
    assert review["status"] == "COMPLETED"
    assert review["report"]["risk_level"] == "HIGH"
    assert review["report"]["findings"][0]["status"] == "SUSPECTED"
    assert FakeGitHub.checks == [(91, "HIGH")]
    assert storage.get_map("demo/project", "a" * 40)["ai_status"] == "OK"
