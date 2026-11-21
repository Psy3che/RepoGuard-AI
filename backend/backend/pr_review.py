"""Manual review actions for open pull requests (in addition to automatic Webhooks).

These routes are protected by the local single-operator dashboard token. GitHub
App installation authorization is rechecked for every requested repository.
"""
import logging
import uuid

from fastapi import BackgroundTasks, HTTPException

from backend import storage
from backend.github_api import GitHubApi, validate_repo
from backend.service import process_pr

log = logging.getLogger(__name__)


def _repo(owner: str, repo: str) -> str:
    try:
        validate_repo(owner, repo)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid repository") from exc
    return f"{owner}/{repo}"


def _authorize(api: GitHubApi, owner: str, repo: str):
    """Verify target repository belongs to the requested GitHub App installation."""
    requested = _repo(owner, repo)
    installation = api.request("GET", f"/repos/{owner}/{repo}/installation", api.app_jwt())
    installation_id = int(installation["id"])
    token = api.installation_token(installation_id)
    info = api.request("GET", f"/repos/{owner}/{repo}", token)
    if info.get("full_name", "").lower() != requested.lower():
        raise HTTPException(status_code=403, detail="Repository identity mismatch")
    return info["full_name"], installation_id, token


def open_pull_requests(owner: str, repo: str) -> dict:
    _repo(owner, repo)
    api = GitHubApi()
    try:
        canonical, _, token = _authorize(api, owner, repo)
        pulls = api.request("GET", f"/repos/{owner}/{repo}/pulls", token,
                            params={"state": "open", "per_page": 30})
        return {
            "repository": canonical,
            "pull_requests": [{
                "number": int(p["number"]),
                "title": str(p.get("title") or "")[:180],
                "head_sha": str((p.get("head") or {}).get("sha") or ""),
                "author": str((p.get("user") or {}).get("login") or "")[:80],
                "url": str(p.get("html_url") or ""),
                "draft": bool(p.get("draft", False)),
            } for p in pulls if isinstance(p, dict) and p.get("number")],
        }
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("Could not list PRs for %s/%s: %s", owner, repo, type(exc).__name__)
        raise HTTPException(status_code=503, detail="Cannot list GitHub pull requests") from exc
    finally:
        api.close()


def queue_pull_request_review(owner: str, repo: str, pr_number: int,
                              background_tasks: BackgroundTasks) -> dict:
    _repo(owner, repo)
    if pr_number < 1:
        raise HTTPException(status_code=400, detail="Pull request number must be positive")
    api = GitHubApi()
    try:
        canonical, installation_id, token = _authorize(api, owner, repo)
        pr = api.request("GET", f"/repos/{owner}/{repo}/pulls/{pr_number}", token)
        if pr.get("state") != "open" or int(pr.get("number", 0)) != pr_number:
            raise HTTPException(status_code=409, detail="Only open pull requests can be reviewed")
        # The PR must target the installed repository; head can come from a fork.
        base_repo = (pr.get("base") or {}).get("repo") or {}
        if base_repo.get("full_name", "").lower() != canonical.lower():
            raise HTTPException(status_code=403, detail="Pull request targets another repository")
        sha = (pr.get("head") or {}).get("sha")
        if not isinstance(sha, str) or len(sha) != 40:
            raise HTTPException(status_code=422, detail="Pull request head commit unavailable")
        review_id = str(uuid.uuid4())
        # Manual and Webhook paths share the same processor, report schema and Checks.
        payload = {
            "repository": {"full_name": canonical, "owner": {"login": canonical.split("/")[0]},
                           "name": canonical.split("/")[1]},
            "installation": {"id": installation_id},
            "pull_request": pr,
        }
        storage.new_review(review_id, canonical, pr_number, sha)
        background_tasks.add_task(process_pr, review_id, payload)
        return {"status": "PENDING", "review_id": review_id, "repository": canonical,
                "pr_number": pr_number, "head_sha": sha}
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("Could not queue PR review for %s/%s #%d: %s",
                    owner, repo, pr_number, type(exc).__name__)
        raise HTTPException(status_code=503, detail="Cannot queue GitHub pull request review") from exc
    finally:
        api.close()
