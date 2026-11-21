"""Tests for the Next.js integration contract (all GitHub calls are mocked)."""
from fastapi.testclient import TestClient
from backend import storage, main
from backend import dashboard_adapter as adapter


def test_dashboard_schema_and_repository_scope(monkeypatch):
    monkeypatch.setattr(adapter, "_metadata", lambda owner, repo: {
        "full_name": f"{owner}/{repo}",
        "owner": {"login": owner},
        "name": repo, "default_branch": "main",
        "description": "Sample repo", "language": "Python",
    })
    monkeypatch.setattr(storage, "get_map", lambda repo: {
        "coverage": {"total_files_indexed": 45, "source_files_sampled": 3},
        "critical_modules": [
            {"file": "src/auth.py", "importance": "CRITICAL", "reason": "Authentication"},
        ],
        "dependency_edges": [
            {"source": "src/payment.py", "target": "src/auth.py", "kind": "import"},
        ],
    })
    monkeypatch.setattr(storage, "list_reviews", lambda repo, limit: [{
        "id": "review-1", "repo": repo, "pr_number": 14, "status": "COMPLETED",
        "created_at": "2026-11-21T10:00:00Z", "updated_at": "2026-11-21T10:01:00Z",
        "report": {
            "risk_level": "HIGH", "merge_recommendation": "REVIEW_REQUIRED",
            "summary": "Potential behavior change", "affected_files": ["src/auth.py"],
            "changed_files": ["src/auth.py"],
            "findings": [{"file": "src/auth.py", "severity": "HIGH", "status": "VERIFIED",
                          "reason": "Return type may have changed", "recommendation": "Run tests"}],
            "coverage": {"expected_files": 1},
            "review_context": {
                "title": "Refactor auth", "author": "demo-user", "branch": "feature/auth",
                "diff_path": "src/auth.py",
                "diff_patch": "@@ -1 +1 @@\n-return True\n+return {'ok': True}\n",
                "additions": 1, "deletions": 1,
            },
        },
    }])
    payload = adapter.dashboard("example-org/repo")
    assert payload["mode"] == "live"
    assert payload["repository"]["owner"] == "example-org"
    assert payload["repository"]["name"] == "repo"
    assert payload["repository"]["analysis_coverage"] == "PARTIAL"
    assert len(payload["modules"]) == 2
    assert len(payload["dependencies"]) == 1
    ids = {m["id"] for m in payload["modules"]}
    assert payload["dependencies"][0]["source"] in ids
    assert payload["dependencies"][0]["target"] in ids
    review = payload["reviews"][0]
    assert review["risk_level"] == "HIGH"
    assert review["merge_decision"] == "REVIEW_REQUIRED"
    assert review["findings"][0]["status"] == "SUSPECTED"  # AI-only evidence
    assert review["diff"][0]["kind"] == "remove"
    assert review["diff"][1]["kind"] == "add"


def test_invalid_repository_name_rejected():
    from fastapi import HTTPException
    try:
        adapter.dashboard("../private")
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("Unsafe repository parameter was accepted")


def test_new_routes_require_bearer(monkeypatch, tmp_path):
    object.__setattr__(storage.settings, "db_path", str(tmp_path / "dashboard-test.db"))
    object.__setattr__(main.settings, "dashboard_token", "dashboard-secret")
    monkeypatch.setattr(main, "build_dashboard", lambda repo: {
        "mode": "unscanned", "repository": {"owner": "demo", "name": "repo"},
        "modules": [], "dependencies": [], "reviews": [],
    })
    monkeypatch.setattr(main, "installed_repositories", lambda: {
        "source": "github-app", "repositories": [],
    })
    with TestClient(main.app) as client:
        assert client.get("/api/dashboard?repository=demo/repo").status_code == 401
        assert client.get("/api/repositories").status_code == 401
        headers = {"Authorization": "Bearer dashboard-secret"}
        assert client.get("/api/dashboard?repository=demo/repo", headers=headers).status_code == 200
        assert client.get("/api/repositories", headers=headers).status_code == 200
