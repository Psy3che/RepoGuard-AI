"""Read-only syntax checks and blast-radius tests."""
from backend import analyzer
from backend.verification import verify_python_syntax


class FakeBlobAPI:
    def __init__(self, content):
        self.content = content
        self.seen = []

    def blob_text(self, owner, repo, sha, token):
        self.seen.append(sha)
        return self.content


def test_valid_python_is_not_claimed_as_behavior_verified():
    sha = "b" * 40
    api = FakeBlobAPI("def check(role):\n    return role == 'admin'\n")
    result = verify_python_syntax(api, "demo", "repo", "token", [
        {"filename": "src/auth.py", "sha": sha, "status": "modified"},
    ])
    assert result["python_files_checked"] == 1
    assert result["python_files_passed"] == 1
    assert result["syntax_errors"] == 0
    assert result["tests_executed"] is False
    assert result["findings"] == []


def test_invalid_python_has_verified_line():
    api = FakeBlobAPI("def check(role):\n    if role == 'admin'\n        return True\n")
    result = verify_python_syntax(api, "demo", "repo", "token", [
        {"filename": "src/auth.py", "sha": "a" * 40, "status": "modified"},
    ])
    finding = result["findings"][0]
    assert finding["severity"] == "HIGH"
    assert finding["status"] == "VERIFIED"
    assert finding["file"] == "src/auth.py"
    assert finding["line"] == 2
    assert "syntax error" in finding["reason"].lower()


def test_skip_unsafe_paths_and_no_sha():
    api = FakeBlobAPI("bad source")
    result = verify_python_syntax(api, "demo", "repo", "token", [
        {"filename": ".env", "sha": "a" * 40},
        {"filename": "../src/auth.py", "sha": "a" * 40},
        {"filename": "src/auth.py", "status": "modified"},
    ])
    assert result["python_files_checked"] == 0
    assert result["python_files_skipped"] == 1
    assert not api.seen


def test_dependency_impact_walk_follows_reverse_imports():
    edges = [
        {"source": "src/orders.py", "target": "src/auth.py"},
        {"source": "src/api.py", "target": "src/orders.py"},
        {"source": "src/unrelated.py", "target": "src/other.py"},
    ]
    assert analyzer.downstream_dependents(edges, ["src/auth.py"]) == [
        "src/orders.py", "src/api.py",
    ]


def test_low_ai_risk_promoted_for_possible_downstream_impact(monkeypatch):
    monkeypatch.setattr(analyzer.ai_json, "__name__", "ai_json", raising=False)
    monkeypatch.setattr(analyzer, "ai_json", lambda *a, **k: {
        "risk_level": "LOW", "summary": "No obvious risk", "findings": [],
        "affected_files": [], "recommendations": [],
    })
    repo_map = {
        "repository": "demo/repo", "ai_status": "OK",
        "critical_modules": [],
        "dependency_edges": [{"source": "src/caller.py", "target": "src/helper.py"}],
        "coverage": {"tree_truncated": False},
    }
    report = analyzer.analyze_pr(repo_map, [{
        "filename": "src/helper.py", "status": "modified",
        "patch": "@@ -1 +1 @@\n-return 1\n+return 2",
    }], expected_files=1)
    assert report["risk_level"] == "MEDIUM"
    assert "src/caller.py" in report["dependent_files"]
    assert "src/caller.py" in report["affected_files"]
    assert any(x["kind"] == "DEPENDENCY_IMPACT" for x in report["risk_signals"])
    assert report["tests"]["status"] == "NOT_RUN"
