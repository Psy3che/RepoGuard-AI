"""RepoGuard AI: GitHub App webhook receiver and frontend report API."""
import json
import logging
import hmac
import uuid
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from backend.config import settings
from backend.security import verify_signature
from backend import storage
from backend.service import process_pr
from backend.dashboard_adapter import dashboard as build_dashboard, installed_repositories
from backend.manual_scan import queue_scan, latest_scan
from backend.pr_review import open_pull_requests, queue_pull_request_review

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("repoguard")


@asynccontextmanager
async def lifespan(_):
    storage.init_db()
    yield


app = FastAPI(title="RepoGuard AI Backend", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in settings.allowed_origins.split(",") if x.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

bearer = HTTPBearer(auto_error=False)


def dashboard_auth(auth: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if not settings.dashboard_token or auth is None or not hmac.compare_digest(
        auth.credentials, settings.dashboard_token
    ):
        raise HTTPException(status_code=401, detail="Valid dashboard bearer token required")


@app.get("/health")
def health():
    return {"status": "ok", "app": "RepoGuard AI", "version": "0.1.0"}


@app.post("/webhook", status_code=202)
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    body = await request.body()
    if len(body) > 2_000_000:
        raise HTTPException(status_code=413, detail="Webhook payload too large")
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_signature(body, signature, settings.webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Invalid JSON")
    event = request.headers.get("X-GitHub-Event", "")
    delivery_id = request.headers.get("X-GitHub-Delivery", "")
    if not delivery_id or len(delivery_id) > 120:
        raise HTTPException(status_code=400, detail="Missing delivery ID")
    if not storage.first_delivery(delivery_id):
        return {"status": "duplicate_ignored"}
    if event == "ping":
        return {"status": "pong"}
    action = payload.get("action", "")
    if event != "pull_request" or action not in {
        "opened", "reopened", "synchronize", "ready_for_review"
    }:
        return {"status": "ignored", "event": event, "action": action}
    try:
        repo = payload["repository"]["full_name"]
        pr_number = int(payload["pull_request"]["number"])
        head_sha = payload["pull_request"]["head"]["sha"]
        installation_id = int(payload["installation"]["id"])
        assert installation_id > 0 and pr_number > 0
    except (KeyError, TypeError, ValueError, AssertionError):
        raise HTTPException(status_code=400, detail="Webhook missing required PR or installation fields")
    review_id = str(uuid.uuid4())
    storage.new_review(review_id, repo, pr_number, head_sha)
    background_tasks.add_task(process_pr, review_id, payload)
    logger.info("Queued PR review %s for %s #%s", review_id, repo, pr_number)
    return {"status": "accepted", "review_id": review_id, "repository": repo, "pr_number": pr_number}


@app.get("/api/reviews", dependencies=[Depends(dashboard_auth)])
def list_reviews(repo: str | None = None, limit: int = Query(30, ge=1, le=100)):
    return {"items": storage.list_reviews(repo, limit)}


@app.get("/api/reviews/{review_id}", dependencies=[Depends(dashboard_auth)])
def review_detail(review_id: str):
    result = storage.get_review(review_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Review not found")
    return result


@app.get("/api/repositories/{owner}/{repo}/map", dependencies=[Depends(dashboard_auth)])
def repository_map(owner: str, repo: str):
    result = storage.get_map(f"{owner}/{repo}")
    if result is None:
        raise HTTPException(status_code=404, detail="Repo scan not found; create a PR first")
    return result


@app.get("/api/dashboard", dependencies=[Depends(dashboard_auth)])
def dashboard_view(repository: str = Query(..., min_length=3, max_length=201)):
    """Exact Next.js dashboard contract, repository-scoped and App-installation checked."""
    return build_dashboard(repository)


@app.get("/api/repositories", dependencies=[Depends(dashboard_auth)])
def installed_repository_list():
    """Single-operator/admin access only; no per-user OAuth sessions in MVP."""
    return installed_repositories()



@app.post("/api/repositories/{owner}/{repo}/scan", status_code=202,
          dependencies=[Depends(dashboard_auth)])
def trigger_manual_scan(owner: str, repo: str, background_tasks: BackgroundTasks):
    """Queue an on-demand architecture scan; never require a Pull Request."""
    return queue_scan(owner, repo, background_tasks)


@app.get("/api/repositories/{owner}/{repo}/scan",
         dependencies=[Depends(dashboard_auth)])
def manual_scan_status(owner: str, repo: str):
    """Status polling endpoint for the local Next.js dashboard."""
    return latest_scan(owner, repo)



@app.get("/api/repositories/{owner}/{repo}/pulls",
         dependencies=[Depends(dashboard_auth)])
def available_open_pulls(owner: str, repo: str):
    """List open PRs available for an on-demand local review."""
    return open_pull_requests(owner, repo)


@app.post("/api/repositories/{owner}/{repo}/pulls/{pr_number}/analyze",
          status_code=202, dependencies=[Depends(dashboard_auth)])
def analyze_open_pull(owner: str, repo: str, pr_number: int,
                      background_tasks: BackgroundTasks):
    """Start a review of an open PR; webhook events still auto-review normally."""
    return queue_pull_request_review(owner, repo, pr_number, background_tasks)
