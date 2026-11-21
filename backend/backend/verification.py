"""Read-only deterministic Python syntax check for changed PR files.

No user code is executed. This is intentionally not a runtime correctness,
security, business-logic or test-suite verification.
"""
import ast
import re

from backend.security import safe_source_path

_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
MAX_PYTHON_FILES = 12
MAX_SOURCE_CHARS = 150_000


def verify_python_syntax(github, owner: str, repo: str, token: str,
                         changed_files: list[dict]) -> dict:
    checked = 0
    passed = 0
    skipped = 0
    findings = []
    candidates = [
        item for item in changed_files
        if str(item.get("filename") or "").endswith(".py")
        and safe_source_path(item.get("filename") or "")
        and item.get("status") != "removed"
    ]
    for item in candidates[:MAX_PYTHON_FILES]:
        path = item["filename"]
        sha = item.get("sha")
        if not isinstance(sha, str) or not _SHA.fullmatch(sha):
            skipped += 1
            continue
        try:
            code = github.blob_text(owner, repo, sha, token)
        except Exception:
            skipped += 1
            continue
        if not code or len(code) > MAX_SOURCE_CHARS:
            skipped += 1
            continue
        checked += 1
        try:
            ast.parse(code, filename=path)
            passed += 1
        except (SyntaxError, ValueError) as exc:
            line = getattr(exc, "lineno", None)
            msg = getattr(exc, "msg", str(exc))
            findings.append({
                "file": path,
                "line": line if isinstance(line, int) and line > 0 else None,
                "severity": "HIGH",
                "status": "VERIFIED",
                "reason": f"Python syntax error: {str(msg)[:240]}",
                "recommendation": "Fix the syntax error, run Python compile checks and rerun CI.",
            })
    skipped += max(0, len(candidates) - MAX_PYTHON_FILES)
    return {
        "python_files_checked": checked,
        "python_files_passed": passed,
        "python_files_skipped": skipped,
        "syntax_errors": len(findings),
        "findings": findings,
        "tests_executed": False,
    }
