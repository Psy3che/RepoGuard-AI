"""DeepSeek-first risk ratings: record actual model verdict separately from guardrails.

All tests mock network calls. The user's real DEEPSEEK_API_KEY remains only on
their local FastAPI machine; no secrets are committed or printed.
"""
from types import SimpleNamespace

from backend import analyzer


REPO_MAP = {
    "repository": "Psy3che/RepoGuard-Demo",
    "ai_status": "OK",
    "project_summary": "Small access-control demo",
    "critical_modules": [{"file": "src/auth.py", "importance": "CRITICAL"}],
    "dependency_edges": [],
    "coverage": {"tree_truncated": False},
}


def _change(path: str, patch: str):
    return [{"filename": path, "status": "modified", "patch": patch}]


def test_docstring_only_change_can_be_low_without_runtime_tests(monkeypatch):
    monkeypatch.setattr(analyzer, "ai_json", lambda *_args, **_kwargs: {
        "risk_level": "LOW",
        "summary": "Only the function docstring changed; execution body is unchanged.",
        "findings": [], "affected_files": [], "recommendations": [],
    })
    patch = (
        '@@ -3,3 +3,3 @@\n def format_name(value):\n'
        '-    """Old description"""\n+    """Updated description"""\n'
        '     return value.strip()'
    )
    report = analyzer.analyze_pr(REPO_MAP, _change("src/formatters.py", patch), expected_files=1)
    assert report["risk_level"] == "LOW"
    assert report["merge_recommendation"] == "NO_BLOCKING_FINDINGS"
    assert report["ai_review"]["provider"] == "DeepSeek"
    assert report["ai_review"]["model_risk_level"] == "LOW"
    assert report["ai_review"]["final_risk_level"] == "LOW"
    assert report["ai_review"]["adjustments"] == []
    assert report["coverage"]["diff_complete"] is True
    assert report["tests"]["status"] == "NOT_RUN"


def test_deepseek_high_permission_risk_is_preserved(monkeypatch):
    monkeypatch.setattr(analyzer, "ai_json", lambda *_args, **_kwargs: {
        "risk_level": "HIGH",
        "summary": "The viewer role can now delete records.",
        "findings": [{"file": "src/auth.py", "severity": "HIGH",
                      "reason": "Authorization boundary widened",
                      "recommendation": "Restore admin-only permission"}],
        "affected_files": ["src/auth.py"], "recommendations": [],
    })
    patch = '@@ -1 +1 @@\n-return role == "admin"\n+return role in ("admin", "viewer")'
    report = analyzer.analyze_pr(REPO_MAP, _change("src/auth.py", patch), expected_files=1)
    assert report["risk_level"] == "HIGH"
    assert report["ai_review"]["model_risk_level"] == "HIGH"
    assert report["findings"][0]["status"] == "SUSPECTED"


def test_insufficient_context_keeps_unknown_and_explains_adjustment(monkeypatch):
    monkeypatch.setattr(analyzer, "ai_json", lambda *_args, **_kwargs: {
        "risk_level": "LOW", "summary": "No issues seen", "findings": [],
        "affected_files": [], "recommendations": [],
    })
    report = analyzer.analyze_pr(REPO_MAP, _change("src/formatters.py", "@@ -1 +1 @@\n-a\n+b"), expected_files=3)
    assert report["risk_level"] == "UNKNOWN"
    assert report["ai_review"]["model_risk_level"] == "LOW"
    assert report["ai_review"]["final_risk_level"] == "UNKNOWN"
    assert any("incomplete" in reason.lower() for reason in report["ai_review"]["adjustments"])
    assert report["coverage"]["diff_complete"] is False


def test_genuine_deepseek_unknown_remains_unknown_with_explanation(monkeypatch):
    monkeypatch.setattr(analyzer, "ai_json", lambda *_args, **_kwargs: {
        "risk_level": "UNKNOWN",
        "summary": "Not enough evidence to assess behavior",
        "findings": [], "affected_files": [], "recommendations": [],
    })
    report = analyzer.analyze_pr(REPO_MAP, _change("src/formatters.py", "@@ -1 +1 @@\n-a\n+b"), expected_files=1)
    assert report["risk_level"] == "UNKNOWN"
    assert "DeepSeek returned UNKNOWN" in report["ai_review"]["adjustments"][0]


def test_ai_client_sends_configured_deepseek_api_key_without_exposing_it(monkeypatch):
    observed = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{
                "finish_reason": "stop",
                "message": {"content": '{"risk_level":"LOW","summary":"Only docs changed"}'},
            }]}

    class Client:
        def __init__(self, timeout):
            observed["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def post(self, url, *, headers, json):
            observed.update(url=url, authorization=headers["Authorization"], body=json)
            return Response()

    monkeypatch.setattr(analyzer, "settings", SimpleNamespace(
        deepseek_api_key="local-test-placeholder", deepseek_model="deepseek-chat",
    ))
    monkeypatch.setattr(analyzer.httpx, "Client", Client)
    result = analyzer.ai_json("review PR", {"diff": "+docstring"})
    assert observed["url"] == "https://api.deepseek.com/chat/completions"
    assert observed["authorization"] == "Bearer local-test-placeholder"
    assert observed["body"]["model"] == "deepseek-chat"
    assert result["risk_level"] == "LOW"
