"""DeepSeek JSON-mode handling: retries are bounded and no raw output is logged."""
import json
from types import SimpleNamespace

import pytest

from backend import analyzer


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        return None

    def json(self):
        if isinstance(self.data, Exception):
            raise self.data
        return self.data


def response(content, finish_reason="stop"):
    return {"choices": [{"message": {"content": content}, "finish_reason": finish_reason}]}


def setup_client(monkeypatch, responses):
    calls = []

    class Client:
        def __init__(self, timeout):
            assert timeout == 75

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, url, *, headers, json):
            assert url == "https://api.deepseek.com/chat/completions"
            assert headers["Authorization"] == "Bearer test-token"
            assert json["response_format"] == {"type": "json_object"}
            calls.append(json)
            return FakeResponse(responses[len(calls) - 1])

    monkeypatch.setattr(analyzer, "settings", SimpleNamespace(
        deepseek_api_key="test-token", deepseek_model="deepseek-flash"
    ))
    monkeypatch.setattr(analyzer.httpx, "Client", Client)
    return calls


def test_truncated_json_retries_with_larger_budget(monkeypatch):
    calls = setup_client(monkeypatch, [
        response('{"project_summary":', "length"),
        response('{"project_summary":"Demo architecture","critical_modules":[],"architecture_notes":[]}'),
    ])
    output = analyzer.ai_json("Return a JSON object", {"files": ["src/auth.py"]})
    assert output["project_summary"] == "Demo architecture"
    assert [call["max_tokens"] for call in calls] == [3200, 5500]


def test_empty_json_retries_and_returns_reason(monkeypatch):
    calls = setup_client(monkeypatch, [response("   "), response("  ")])
    with pytest.raises(analyzer.DeepSeekOutputError, match="empty_json_response"):
        analyzer.ai_json("Return JSON", {"file": "demo.py"})
    assert len(calls) == 2


def test_invalid_json_first_time_can_recover(monkeypatch):
    calls = setup_client(monkeypatch, [
        response('{"project_summary"'),
        response('{"project_summary":"Fixed"}'),
    ])
    assert analyzer.ai_json("Return JSON", {})["project_summary"] == "Fixed"
    assert len(calls) == 2


def test_invalid_http_response_json_retries(monkeypatch):
    calls = setup_client(monkeypatch, [
        json.JSONDecodeError("Invalid JSON", "{", 0),
        response('{"ok":true}'),
    ])
    assert analyzer.ai_json("Return JSON", {})["ok"] is True
    assert len(calls) == 2


def test_filtered_response_does_not_retry(monkeypatch):
    calls = setup_client(monkeypatch, [response("", "content_filter")])
    with pytest.raises(analyzer.DeepSeekOutputError, match="output_filtered"):
        analyzer.ai_json("Return JSON", {})
    assert len(calls) == 1


def test_architecture_scan_returns_safe_error_code(monkeypatch):
    class GitHub:
        def repo_tree(self, owner, repo, base_sha, token):
            return {"truncated": False, "tree": [
                {"type": "blob", "path": "src/auth.py", "size": 100,
                 "sha": "a" * 40}
            ]}

        def blob_text(self, *args):
            return 'def auth(role): return role == "admin"'

    monkeypatch.setattr(analyzer, "ai_json", lambda *a, **k: (
        (_ for _ in ()).throw(analyzer.DeepSeekOutputError("invalid_json_response"))
    ))
    repo_map = analyzer.build_repo_map("demo", "repo", "b" * 40, GitHub(), "token")
    assert repo_map["ai_status"] == "UNAVAILABLE"
    assert repo_map["ai_error_type"] == "DeepSeekOutputError"
    assert repo_map["ai_error_reason"] == "invalid_json_response"
    assert repo_map["coverage"]["source_files_sampled"] == 1
