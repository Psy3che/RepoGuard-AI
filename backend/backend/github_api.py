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
        validate_repo(owner, repo)
        level = report.get("risk_level", "UNKNOWN")
        verified = any(x.get("status") == "VERIFIED" for x in report.get("findings", []))
        # Only verified serious issues should fail a required merge check.
        if verified and level in ("HIGH", "CRITICAL"):
            conclusion = "action_required"
        elif level == "LOW" and report.get("coverage", {}).get("diff_complete"):
            conclusion = "success"
        else:
            conclusion = "neutral"
        findings = report.get("findings", [])[:10]
        details = "\n".join(
            f"- **{x.get('severity','?')} / {x.get('status','SUSPECTED')}** "
            f"`{x.get('file','')}`: {x.get('reason','')}" for x in findings
        )
        summary = (
            f"**Risk:** {level}\n\n"
            f"{report.get('summary','')}\n\n"
            f"**Merge advice:** {report.get('merge_recommendation','UNDETERMINED')}\n\n"
            f"**Tests:** Not run by this MVP\n\n"
            f"**Findings:**\n{details or 'No specific findings'}\n\n"
            "AI suggestions are not proof of correctness or failure."
        )[:60000]
        return self.request(
            "PATCH", f"/repos/{owner}/{repo}/check-runs/{check_id}", token,
            json={
                "status": "completed", "conclusion": conclusion,
                "output": {"title": f"RepoGuard risk: {level}", "summary": summary},
            }
        )

    def close(self):
        self.http.close()
