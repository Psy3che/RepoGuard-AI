"""Manual repository scans, independent of pull request webhook deliveries.

The dashboard Bearer token gates the routes.  This is a local single-operator
hackathon workflow, not a substitute for per-user GitHub OAuth in production.
"""
import logging
from urllib.parse import quote

from fastapi import BackgroundTasks, HTTPException

from backend import storage
from backend.analyzer import build_repo_map
from backend.github_api import GitHubApi, validate_repo

log = logging.getLogger(__name__)


def _validated(owner: str, repo: str) -> str:
    try:
        validate_repo(owner, repo)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid repository name") from exc
    return f"{owner}/{repo}"


def latest_scan(owner: str, repo: str) -> dict:
    """Read the latest job state; does not expose tokens or internal error text."""
    name = _validated(owner, repo)
    row = storage.get_latest_scan(name)
    if row is None:
        return {"repository": name, "status": "IDLE"}
    return {
        "repository": name, "scan_id": row["id"],
        "status": row["status"], "updated_at": row["updated_at"],
        "error": row.get("error"),
    }


def queue_scan(owner: str, repo: str, background_tasks: BackgroundTasks) -> dict:
    """Authenticate App installation and pin a default-branch commit before queuing."""
    name = _validated(owner, repo)
    api = GitHubApi()
    try:
        installation = api.request(
            "GET", f"/repos/{owner}/{repo}/installation", api.app_jwt()
        )
        installation_id = int(installation["id"])
        token = api.installation_token(installation_id)
        details = api.request("GET", f"/repos/{owner}/{repo}", token)
        if details.get("full_name", "").lower() != name.lower():
            raise HTTPException(status_code=403, detail="Repository identity mismatch")
        name = details["full_name"]
        default_branch = details.get("default_branch") or "main"
        commit = api.request(
            "GET", f"/repos/{owner}/{repo}/commits/{quote(default_branch, safe='')}",
            token,
        )
        base_sha = commit["sha"]
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("Could not start repository scan for %s: %s", name, type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Cannot verify installed repository or resolve its default branch",
        ) from exc
    finally:
        api.close()

    job, created = storage.claim_scan(name, base_sha)
    if created:
        background_tasks.add_task(_run_scan, job["id"], name, base_sha, installation_id)
    return {
        "repository": name, "scan_id": job["id"],
        "status": job["status"], "created": created,
    }


def _run_scan(scan_id: str, repository: str, base_sha: str, installation_id: int) -> None:
    """Build the existing AI + heuristic map and persist it only if AI completed."""
    api = GitHubApi()
    try:
        storage.update_scan(scan_id, "RUNNING")
        owner, repo = repository.split("/", 1)
        token = api.installation_token(installation_id)
        repo_map = build_repo_map(owner, repo, base_sha, api, token)
        if repo_map.get("ai_status") != "OK":
            cause = str(repo_map.get("ai_error_reason") or repo_map.get("ai_error_type") or "UnknownError")[:80]
            storage.update_scan(scan_id, "FAILED", error=f"DeepSeek architecture analysis unavailable ({cause})")
            log.warning("DeepSeek architecture analysis unavailable for %s: %s", repository, cause)
            return
        repo_map["scanned_at"] = storage.now()
        storage.save_map(repository, base_sha, repo_map)
        storage.update_scan(scan_id, "COMPLETED")
        log.info("Repository scan completed: %s (%s)", repository, base_sha[:10])
    except Exception as exc:
        log.exception("Repository scan failed for %s", repository)
        storage.update_scan(scan_id, "FAILED", error=type(exc).__name__)
    finally:
        api.close()
