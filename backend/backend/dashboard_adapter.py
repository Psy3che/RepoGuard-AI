"""Translate stored RepoGuard scans/reviews into the existing Next.js dashboard contract.

Service-level access only: this module does not implement end-user authentication.
The API must be protected by dashboard_auth and should not be exposed by a
public unauthenticated Next.js proxy.
"""
import hashlib
import logging
import re
from pathlib import PurePosixPath

from fastapi import HTTPException
from backend.github_api import GitHubApi, validate_repo
from backend import storage

log = logging.getLogger(__name__)
LEVELS = {"LOW", "MEDIUM", "HIGH", "CRITICAL", "UNKNOWN"}
APPROVALS = {"NO_BLOCKING_FINDINGS", "REVIEW_SUGGESTED", "REVIEW_REQUIRED", "UNDETERMINED"}


def _id(path: str) -> str:
    return "file-" + hashlib.sha1(path.encode("utf-8")).hexdigest()[:12]


def _category(path: str) -> str:
    lower = path.lower()
    if any(term in lower for term in ("auth", "permission", "security", "crypt")):
        return "Security"
    if any(term in lower for term in ("payment", "billing", "checkout")):
        return "Financial"
    if any(term in lower for term in ("database", "schema", "migration", "/db/")):
        return "Persistence"
    if any(term in lower for term in ("api", "route", "gateway")):
        return "API"
    if any(term in lower for term in ("ui", "component", "frontend")):
        return "Interface"
    return "Business logic"


def _metadata(owner: str, repo: str) -> dict:
    """Require the app to be installed on the requested repository."""
    validate_repo(owner, repo)
    api = GitHubApi()
    try:
        installation = api.request(
            "GET", f"/repos/{owner}/{repo}/installation", api.app_jwt()
        )
        token = api.installation_token(int(installation["id"]))
        info = api.request("GET", f"/repos/{owner}/{repo}", token)
        if info.get("full_name", "").lower() != f"{owner}/{repo}".lower():
            raise HTTPException(status_code=403, detail="Repository identity mismatch")
        return info
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("Cannot verify GitHub App repository installation: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Cannot verify repository access through the GitHub App",
        ) from exc
    finally:
        api.close()


def installed_repositories() -> dict:
    """Admin-only list of repos installed for the GitHub App (not current-user scoped)."""
    api = GitHubApi()
    results = []
    try:
        for page in range(1, 6):
            installs = api.request(
                "GET", "/app/installations", api.app_jwt(),
                params={"per_page": 100, "page": page},
            )
            for installation in installs:
                token = api.installation_token(int(installation["id"]))
                for repo_page in range(1, 11):
                    data = api.request(
                        "GET", "/installation/repositories", token,
                        params={"per_page": 100, "page": repo_page},
                    )
                    items = data.get("repositories", [])
                    for item in items:
                        owner = item.get("owner") or {}
                        results.append({
                            "id": int(item["id"]),
                            "full_name": item["full_name"],
                            "name": item["name"],
                            "owner": owner.get("login", ""),
                            "private": bool(item.get("private")),
                            "description": item.get("description") or "",
                            "default_branch": item.get("default_branch") or "main",
                            "html_url": item.get("html_url") or "",
                        })
                    if len(items) < 100:
                        break
            if len(installs) < 100:
                break
    except Exception as exc:
        log.warning("Cannot retrieve installed repositories: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Cannot list GitHub App installations") from exc
    finally:
        api.close()
    dedup = {item["full_name"]: item for item in results}
    return {"source": "github-app", "repositories": list(dedup.values())}


def _diff_lines(patch: str) -> list[dict]:
    lines = []
    old_no = new_no = 0
    inside = False
    for raw in patch.splitlines()[:170]:
        if raw.startswith("@@"):
            match = re.search(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw)
            if match:
                old_no, new_no = map(int, match.groups())
                inside = True
            continue
        if not inside or raw.startswith("\\ No newline"):
            continue
        if raw.startswith("+"):
            lines.append({"kind": "add", "code": raw[1:], "line": new_no})
            new_no += 1
        elif raw.startswith("-"):
            lines.append({"kind": "remove", "code": raw[1:], "line": old_no})
            old_no += 1
        elif raw.startswith(" "):
            lines.append({"kind": "context", "code": raw[1:], "line": new_no})
            old_no += 1
            new_no += 1
    return lines


def _review(row: dict, ids: dict[str, str]) -> dict:
    report = row.get("report") or {}
    context = report.get("review_context") or {}
    risk = report.get("risk_level", "UNKNOWN") if row["status"] == "COMPLETED" else "UNKNOWN"
    if risk not in LEVELS:
        risk = "UNKNOWN"
    advice = report.get("merge_recommendation", "UNDETERMINED")
    if advice not in APPROVALS:
        advice = "UNDETERMINED"
    merge_decision = {
        "NO_BLOCKING_FINDINGS": "PASS",
        "REVIEW_SUGGESTED": "REVIEW_REQUIRED",
        "REVIEW_REQUIRED": "REVIEW_REQUIRED",
        "UNDETERMINED": "UNKNOWN",
    }[advice] if row["status"] == "COMPLETED" else "UNKNOWN"
    findings = []
    for i, finding in enumerate(report.get("findings") or []):
        if not isinstance(finding, dict):
            continue
        reason = str(finding.get("reason") or "Potential change impact")
        severity = finding.get("severity", "UNKNOWN")
        findings.append({
            "id": f"{row['id']}-finding-{i+1}",
            "file": str(finding.get("file") or ""),
            "line": None,
            "severity": severity if severity in LEVELS else "UNKNOWN",
            "status": "SUSPECTED",  # no deterministic verification in MVP
            "title": reason[:110],
            "explanation": reason,
            "recommendation": str(finding.get("recommendation") or ""),
        })
    affected = set(report.get("affected_files") or [])
    changed = report.get("changed_files") or []
    coverage = report.get("coverage") or {}
    patch = context.get("diff_patch") or ""
    path = context.get("diff_path") or (changed[0] if changed else "")
    return {
        "id": row["id"],
        "number": row["pr_number"],
        "title": context.get("title") or f"Pull Request #{row['pr_number']}",
        "author": context.get("author") or "Unknown (not captured)",
        "branch": context.get("branch") or "",
        "updated_at": row.get("updated_at") or row.get("created_at") or "",
        "risk_level": risk,
        "merge_decision": merge_decision,
        "summary": report.get("summary") or (
            "Analysis running" if row["status"] in ("PENDING", "RUNNING") else
            "No completed report. Review status: " + row["status"]
        ),
        "files_changed": coverage.get("expected_files") or len(changed),
        "additions": context.get("additions") or 0,
        "deletions": context.get("deletions") or 0,
        "affected_module_ids": sorted({ids[p] for p in affected if p in ids}),
        "findings": findings,
        "diff_path": path,
        "diff": _diff_lines(patch),
    }


def dashboard(repository: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise HTTPException(status_code=400, detail="Expected owner/repo")
    owner, repo = repository.split("/", 1)
    try:
        validate_repo(owner, repo)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid owner/repo") from exc
    info = _metadata(owner, repo)
    canonical = info["full_name"]
    repo_map = storage.get_map(canonical)
    rows = storage.list_reviews(canonical, limit=40)
    summary = repo_map.get("coverage") or {} if repo_map else {}
    mods = {}
    edges = []
    if repo_map:
        for item in (repo_map.get("critical_modules") or [])[:100]:
            path = item.get("file", "")
            if not path or path in mods:
                continue
            importance = item.get("importance", "MEDIUM")
            mods[path] = {
                "id": _id(path), "name": PurePosixPath(path).name,
                "path": path, "category": _category(path),
                "importance": importance if importance in LEVELS - {"UNKNOWN"} else "MEDIUM",
                "reason": item.get("reason") or "Requires review",
                # AI candidates are recommendations; owner has not confirmed policy.
                "protected": False,
            }
        for edge in (repo_map.get("dependency_edges") or [])[:100]:
            src, dst = edge.get("source"), edge.get("target")
            if not src or not dst:
                continue
            for path in (src, dst):
                if path not in mods and len(mods) < 100:
                    mods[path] = {
                        "id": _id(path), "name": PurePosixPath(path).name,
                        "path": path, "category": _category(path),
                        "importance": "MEDIUM",
                        "reason": "Referenced in sampled import graph",
                        "protected": False,
                    }
            if src in mods and dst in mods:
                edges.append({
                    "source": mods[src]["id"], "target": mods[dst]["id"],
                    "label": edge.get("kind") or "import",
                })
    modules = []
    for i, m in enumerate(mods.values()):
        modules.append({**m, "position": {"x": 90 + (i % 4) * 300, "y": 70 + (i // 4) * 175}})
    ids = {m["path"]: m["id"] for m in modules}
    finished = [row for row in rows if row["status"] == "COMPLETED"]
    last_at = finished[0]["updated_at"] if finished else ""
    return {
        "mode": "live" if repo_map else "unscanned",
        "repository": {
            "owner": info["owner"]["login"],
            "name": info["name"],
            "default_branch": info.get("default_branch") or "main",
            "description": info.get("description") or "",
            "language": info.get("language") or "Unknown",
            "last_analyzed_at": last_at,
            "tracked_files": summary.get("total_files_indexed", 0),
            "analyzed_files": summary.get("source_files_sampled", 0),
            "analysis_coverage": "PARTIAL" if repo_map else "UNKNOWN",
        },
        "modules": modules, "dependencies": edges,
        "reviews": [_review(row, ids) for row in rows],
    }
