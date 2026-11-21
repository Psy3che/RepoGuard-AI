"""Pull request analysis orchestration (runs in background after webhook HTTP 202)."""
import logging
from backend import storage
from backend.github_api import GitHubApi
from backend.analyzer import build_repo_map, analyze_pr
from backend.config import settings

log = logging.getLogger(__name__)


def process_pr(review_id: str, payload: dict):
    api = GitHubApi()
    check_id = None
    token = None
    owner = ""
    repo_name = ""
    try:
        storage.update_review(review_id, "RUNNING")
        owner = payload["repository"]["owner"]["login"]
        repo_name = payload["repository"]["name"]
        pr = payload["pull_request"]
        repo_key = f"{owner}/{repo_name}"
        token = api.installation_token(int(payload["installation"]["id"]))
        try:
            check_id = api.create_check(owner, repo_name, pr["head"]["sha"], token)
        except Exception:
            log.exception("Cannot create check run; continuing local analysis")

        base_sha = pr["base"]["sha"]
        repo_map = storage.get_map(repo_key, base_sha)
        if repo_map is None:
            repo_map = build_repo_map(owner, repo_name, base_sha, api, token)
            storage.save_map(repo_key, base_sha, repo_map)
        files = api.pull_files(owner, repo_name, int(pr["number"]), token, settings.max_pr_files)
        report = analyze_pr(repo_map, files, expected_files=pr.get("changed_files"))
        report["pr_number"] = int(pr["number"])
        report["head_sha"] = pr["head"]["sha"]
        report["review_id"] = review_id
        storage.update_review(review_id, "COMPLETED", report=report)
        if check_id is not None:
            try:
                api.complete_check(owner, repo_name, check_id, token, report)
            except Exception:
                log.exception("Review stored but GitHub check update failed")
    except Exception as exc:
        log.exception("PR analysis failed")
        storage.update_review(review_id, "FAILED", error=type(exc).__name__)
        if check_id is not None and token:
            try:
                api.complete_check(owner, repo_name, check_id, token, {
                    "risk_level": "UNKNOWN",
                    "summary": "Analysis could not complete. Re-run required; no safety conclusion.",
                    "merge_recommendation": "UNDETERMINED",
                    "coverage": {"complete": False},
                    "findings": [],
                })
            except Exception:
                log.exception("Could not post failed check")
    finally:
        api.close()
