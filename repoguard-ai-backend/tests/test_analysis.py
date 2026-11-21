from backend import analyzer


def test_import_edges_and_importance():
    paths = ["src/app.ts", "src/auth.ts", "src/payment.py", "src/auth.py"]
    sources = {
        "src/app.ts": "import { verify } from './auth';",
        "src/payment.py": "from src.auth import verify_token",
    }
    edges = analyzer.approximate_edges(sources, paths)
    assert {"source": "src/app.ts", "target": "src/auth.ts", "kind": "import"} in edges
    assert {"source": "src/payment.py", "target": "src/auth.py", "kind": "import"} in edges
    assert analyzer.importance("src/auth.py")[0] == "CRITICAL"
    assert analyzer.importance("README.md")[0] == "LOW"


def test_risk_review_normalizes_ai_hallucinations(monkeypatch):
    def mock_ai(*_):
        return {
            "risk_level": "HIGH",
            "summary": "Potential breaking change",
            "affected_files": ["src/auth.py", "not/in/repo.py"],
            "findings": [
                {"file": "src/auth.py", "status": "VERIFIED", "severity": "HIGH", "reason": "Potential API change"},
                {"file": "imaginary.py", "severity": "CRITICAL", "reason": "Invented"},
            ],
            "recommendations": ["Review dependent callers"],
        }
    monkeypatch.setattr(analyzer, "ai_json", mock_ai)
    repo_map = {
        "repository": "demo/example", "ai_status": "OK",
        "critical_modules": [{"file": "src/auth.py", "importance": "CRITICAL"}],
        "dependency_edges": [], "coverage": {"tree_truncated": False},
    }
    files = [{"filename": "src/auth.py", "status": "modified", "patch": "@@ -1 +1 @@\n-return True\n+return {'ok': True}"}]
    report = analyzer.analyze_pr(repo_map, files, expected_files=1)
    assert report["risk_level"] == "HIGH"
    assert report["merge_recommendation"] == "REVIEW_REQUIRED"
    assert report["affected_files"] == ["src/auth.py"]
    assert report["findings"][0]["status"] == "SUSPECTED"
    assert len(report["findings"]) == 1
    assert report["coverage"]["diff_complete"] is True
    assert report["coverage"]["complete"] is False
    assert report["tests"]["status"] == "NOT_RUN"


def test_incomplete_review_not_green(monkeypatch):
    monkeypatch.setattr(analyzer, "ai_json", lambda *_: {"risk_level": "LOW", "summary": "No obvious issues"})
    map_ = {"repository":"demo/example", "ai_status":"OK", "critical_modules":[], "coverage":{"tree_truncated":False}}
    files = [{"filename":"docs.txt", "patch": None}]
    report = analyzer.analyze_pr(map_, files, expected_files=2)
    assert report["risk_level"] == "UNKNOWN"
    assert report["coverage"]["diff_complete"] is False
