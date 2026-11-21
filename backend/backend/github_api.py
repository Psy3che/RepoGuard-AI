"""GitHub App JWT -> installation token -> REST API for PR, tree and Checks."""
import base64
import re
import time
from urllib.parse import quote
import httpx
import jwt
from backend.config import settings

API = "https://api.github.com"
API_VERSION = "2026-03-10"
REPO_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
COMMIT = re.compile(r"^[a-fA-F0-9]{40}$")


def validate_repo(owner: str, repo: str):
    if owner in (".", "..") or repo in (".", "..") or not REPO_NAME.fullmatch(owner) or not REPO_NAME.fullmatch(repo):
        raise ValueError("Invalid owner or repo name")


class GitHubApi:
    def __init__(self):
        self.http = httpx.Client(timeout=25, follow_redirects=False)

    def request(self, method: str, path: str, token: str, *, params=None, json=None):
        response = self.http.request(
            method,
            API + path,
            params=params,
            json=json,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": "RepoGuard-AI-Hackathon",
            },
        )
        response.raise_for_status()
        return response.json()

    def app_jwt(self):
        if not settings.app_id:
            raise RuntimeError("GITHUB_APP_ID is missing")
        ts = int(time.time())
        return jwt.encode(
            {"iat": ts - 60, "exp": ts + 540, "iss": settings.app_id},
            settings.private_key,
            algorithm="RS256",
        )

    def installation_token(self, installation_id: int):
        data = self.request(
            "POST", f"/app/installations/{installation_id}/access_tokens", self.app_jwt()
        )
        return data["token"]

    def repo_tree(self, owner: str, repo: str, base_sha: str, token: str):
        validate_repo(owner, repo)
        if not COMMIT.fullmatch(base_sha):
            raise ValueError("Invalid base sha")
        commit = self.request(
            "GET", f"/repos/{owner}/{repo}/git/commits/{base_sha}", token
        )
        tree_sha = commit["tree"]["sha"]
        return self.request(
            "GET", f"/repos/{owner}/{repo}/git/trees/{tree_sha}", token,
            params={"recursive": "1"},
        )

    def blob_text(self, owner: str, repo: str, blob_sha: str, token: str):
        validate_repo(owner, repo)
        if not COMMIT.fullmatch(blob_sha):
            raise ValueError("Invalid blob sha")
        data = self.request("GET", f"/repos/{owner}/{repo}/git/blobs/{blob_sha}", token)
        if data.get("encoding") != "base64":
            return ""
        raw = base64.b64decode(data.get("content", ""))
        return raw.decode("utf-8", errors="replace")

    def pull_files(self, owner: str, repo: str, number: int, token: str, limit: int):
        validate_repo(owner, repo)
        results = []
        page = 1
        while len(results) < limit:
            batch = self.request(
                "GET", f"/repos/{owner}/{repo}/pulls/{number}/files", token,
                params={"per_page": min(100, limit - len(results)), "page": page},
            )
            results.extend(batch)
            if len(batch) < min(100, limit - (len(results) - len(batch))):
                break
            page += 1
        return results[:limit]

    def create_check(self, owner: str, repo: str, head_sha: str, token: str):
        validate_repo(owner, repo)
        return self.request(
            "POST", f"/repos/{owner}/{repo}/check-runs", token,
            json={
                "name": "RepoGuard AI / Risk Scan",
                "head_sha": head_sha,
                "status": "in_progress",
                "output": {"title": "RepoGuard analysis running", "summary": "Scanning the PR for potential impact."},
            }
        )["id"]

    def complete_check(self, owner: str, repo: str, check_id: int, token: str, report: dict):
        """Publish risk badges and evidence in GitHub Checks, not unverified merge blockers."""
        validate_repo(owner, repo)
        level = report.get("risk_level", "UNKNOWN")
        coverage = report.get("coverage") or {}
        findings = [x for x in (report.get("findings") or []) if isinstance(x, dict)][:20]
        verified = [x for x in findings if x.get("status") == "VERIFIED"]
        has_verified_failure = any(x.get("severity") in ("HIGH", "CRITICAL") for x in verified)
        clear_scope = level == "LOW" and bool(coverage.get("diff_complete"))
        if has_verified_failure:
            conclusion = "action_required"
            title = "❌ Verified issue — changes required"
        elif clear_scope:
            conclusion = "success"
            title = "✅ No blocking findings in reviewed scope"
        elif level in ("HIGH", "CRITICAL"):
            conclusion = "neutral"
            title = f"⚠️ {level} AI risk — human review required"
        elif level == "MEDIUM":
            conclusion = "neutral"
            title = "⚠️ MEDIUM AI risk — review suggested"
        else:
            conclusion = "neutral"
            title = "❔ Incomplete or unknown risk — review required"

        details = "\n".join(
            f"- **{x.get('severity','?')} / {x.get('status','SUSPECTED')}** "
            f"`{x.get('file','')}`: {x.get('reason','')}" for x in findings
        )
        impacted = ", ".join(f"`{p}`" for p in (report.get("dependent_files") or [])[:12])
        touched = ", ".join(f"`{p}`" for p in (report.get("important_touched_files") or [])[:12])
        checks = report.get("verification") or {}
        tests = report.get("tests") or {}
        summary = (
            f"**Risk badge:** {level}\\n\\n"
            f"**Merge advice:** {report.get('merge_recommendation','UNDETERMINED')}\\n\\n"
            f"**AI summary:** {report.get('summary','')}\\n\\n"
            f"**Core modules changed:** {touched or 'None identified in sampled map'}\\n\\n"
            f"**Potential dependent modules:** {impacted or 'None identified in sampled graph'}\\n\\n"
            f"**Python syntax checked:** {checks.get('python_files_checked',0)} files "
            f"({checks.get('syntax_errors',0)} syntax errors); "
            f"**Runtime/unit tests:** {tests.get('status','NOT_RUN')}\\n\\n"
            f"**Diff coverage:** {'complete' if coverage.get('diff_complete') else 'partial/unknown'}\\n\\n"
            f"**Findings:**\\n{details or 'No specific findings in reviewed scope'}\\n\\n"
            "AI findings are suspected until independently verified. "
            "Even a successful check does not prove the code correct or safe."
        )[:60000]
        annotations = []
        for finding in verified[:40]:
            line = finding.get("line")
            path = finding.get("file")
            if not isinstance(line, int) or line < 1 or not isinstance(path, str):
                continue
            annotations.append({
                "path": path, "start_line": line, "end_line": line,
                "annotation_level": "failure" if finding.get("severity") in ("HIGH", "CRITICAL") else "warning",
                "title": "Verified Python syntax error",
                "message": str(finding.get("reason") or "Python parser error")[:500],
            })
        return self.request(
            "PATCH", f"/repos/{owner}/{repo}/check-runs/{check_id}", token,
            json={
                "status": "completed", "conclusion": conclusion,
                "output": {"title": title, "summary": summary, "annotations": annotations},
            }
        )

    def close(self):
        self.http.close()
