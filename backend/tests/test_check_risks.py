"""GitHub Check risk badge semantics. No real GitHub calls."""
from backend.github_api import GitHubApi


class CaptureAPI(GitHubApi):
    def __init__(self):
        self.sent = []

    def request(self, method, path, token, *, params=None, json=None):
        self.sent.append((method, path, json))
        return {"id": 10}

    def close(self):
        pass


def _check(report):
    api = CaptureAPI()
    api.complete_check("example", "demo", 10, "token", report)
    return api.sent[-1][2]


def test_suspected_critical_risk_is_warning_not_verified_failure():
    sent = _check({
        "risk_level": "CRITICAL", "summary": "May impact authorization",
        "merge_recommendation": "REVIEW_REQUIRED",
        "coverage": {"diff_complete": True},
        "findings": [{"file": "src/auth.py", "status": "SUSPECTED",
                      "severity": "CRITICAL", "reason": "Permission broadening"}],
    })
    assert sent["conclusion"] == "neutral"
    assert "CRITICAL" in sent["output"]["title"]
    assert sent["output"]["annotations"] == []


def test_low_risk_complete_diff_signals_no_blocking_findings_only():
    sent = _check({
        "risk_level": "LOW", "summary": "No high risk findings",
        "merge_recommendation": "NO_BLOCKING_FINDINGS",
        "coverage": {"diff_complete": True},
        "findings": [],
    })
    assert sent["conclusion"] == "success"
    assert "reviewed scope" in sent["output"]["title"].lower()
    assert "does not prove" in sent["output"]["summary"]


def test_verified_syntax_error_is_action_required_with_line_annotation():
    sent = _check({
        "risk_level": "HIGH", "summary": "Actual syntax error",
        "merge_recommendation": "REVIEW_REQUIRED",
        "coverage": {"diff_complete": True},
        "findings": [{"file": "src/auth.py", "line": 3, "status": "VERIFIED",
                      "severity": "HIGH", "reason": "Python syntax error: expected ':'"}],
    })
    assert sent["conclusion"] == "action_required"
    assert sent["output"]["annotations"][0]["path"] == "src/auth.py"
    assert sent["output"]["annotations"][0]["start_line"] == 3
    assert sent["output"]["annotations"][0]["annotation_level"] == "failure"
