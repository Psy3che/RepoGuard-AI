# RepoGuard AI — Frontend MVP

RepoGuard AI hackathon dashboard built with **Next.js App Router + React + TypeScript + React Flow**. It does not require GitHub, DeepSeek, or a live backend to demonstrate the UI.

> **Demo-mode disclosure:** All repository findings, counts, dependency edges, PRs and diff snippets in demo mode are simulated. They are illustrative, not observations about a real GitHub repository.

## NEW — Select active GitHub repository

**Active Repository is now a selectable dropdown** in the left sidebar. Selecting a different repository loads independent risk data and resets the PR/module selection.

### Try live public repositories immediately (without FastAPI)

1. Run `npm run dev` and open `http://localhost:3000`.
2. Click **ACTIVE REPOSITORY** in the sidebar.
3. Enter a **GitHub username** and click the search button.
4. Choose one of the real public repositories fetched by the Next.js server from GitHub API.
5. The UI will show **NOT SCANNED** for that real repository — GitHub metadata is real, but DeepSeek has not analyzed it. Demo reports are never reused for another repository.

The public development lookup uses `GET /users/{username}/repos` and displays up to **100** recently updated public repositories. It cannot list private repositories or prove that the user has installed the App. Unauthenticated GitHub API rate limits apply.

### GitHub App — correct backend integration for private/installed repositories

To list **only the repositories authorized for the signed-in user and RepoGuard App**, member A must implement:

```http
GET /api/repositories
Content-Type: application/json
```

Example payload: `examples/repositories-response.json`. Repository fields are:

```json
{
  "source": "github-app",
  "repositories": [
    {
      "id": 123456,
      "full_name": "example-org/repo-one",
      "name": "repo-one",
      "owner": "example-org",
      "private": true,
      "description": "Example only",
      "default_branch": "main",
      "html_url": "https://github.com/example-org/repo-one"
    }
  ]
}
```

For a **single authenticated GitHub App installation**, the backend can use an **installation access token** to call `GET https://api.github.com/installation/repositories` (handle pagination). If multiple App installations belong to different users/orgs, the backend must resolve the current user's allowed installations and enforce per-user authorization; **do not disclose all installation repositories to anonymous visitors**. For OAuth user access, GitHub also offers `GET /user/installations/{installation_id}/repositories`.

When a repository is selected, the frontend requests:

```http
GET /api/dashboard?repository=example-org%2Frepo-one
```

FastAPI **must check authorization for the repository** and return its own `DashboardPayload` (same structure as before) with `repository.owner` and `repository.name` matching the requested repository. The Next.js proxy rejects mismatched results so data from repository A does not appear when viewing repository B.

The two Next.js API endpoints are:

- `/api/repositories`: proxy to FastAPI when configured; otherwise GitHub public-user lookup (or local demo repository before a user is entered).
- `/api/dashboard?repository=owner/repo`: proxy to FastAPI when configured; otherwise real public GitHub metadata with `mode: "unscanned"`, and simulated reports only for the explicit demo repository.

For local development set `REPOGUARD_API_BASE_URL=http://127.0.0.1:8000` in `.env.local` and restart the frontend. Keep App credentials and DeepSeek keys **only on the backend**. Production requires end-user authentication and session-aware authorization on the Next.js ↔ FastAPI boundary; the provided MVP proxy by itself is not a production access-control boundary.

---

## Run locally

Requires **Node.js 20.9+** (Node.js 22 LTS recommended).

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

To check demo data consistency without installing dependencies:

```bash
node scripts/validate-demo.mjs
```

## Pages and interactions

| Workspace | Demo functionality |
|---|---|
| Overview | Metrics, recent PRs, protected modules, navigation |
| Architecture map | Interactive React Flow dependency graph; click nodes, select PR to highlight potential impact |
| Pull requests | Search/filter PRs, select one, inspect severity, findings, impacted modules, diff context; copy summary and download JSON |
| Protection policies | Read-only explanation of AI-recommended protected paths and reasons |

The top-right badge shows **DEMO DATA**, **NOT SCANNED** (real public GitHub repository with no AI analysis), or **LIVE BACKEND**. Refresh triggers another request. If a configured backend is down, the UI reports the error instead of silently inventing results.

## Integration contract for member A (FastAPI)

**Two endpoints are now needed for GitHub App repository selection:**

```
GET /api/dashboard?repository=owner%2Frepo
Content-Type: application/json
```

Return JSON using the **exact structure** in `examples/dashboard-response.json` or the TS definitions in `lib/types.ts`:

```ts
interface DashboardPayload {
  mode: "demo" | "live";
  repository: RepositorySummary;
  modules: RepoModule[];
  dependencies: Dependency[];
  reviews: PullRequestReview[];
}
```

Important field names:

- `repository`: `owner`, `name`, `default_branch`, `description`, `language`, `last_analyzed_at` (ISO 8601), `tracked_files`, `analyzed_files`, `analysis_coverage` (`FULL | PARTIAL | UNKNOWN`).
- `modules[]`: `id`, `name`, `path`, `category`, `importance` (`CRITICAL | HIGH | MEDIUM | LOW`), `reason`, `protected` (boolean), `position` (`{ x, y }`). For quick integration, supply graph positions using a simple layout. Use consistent module IDs.
- `dependencies[]`: each `{ source, target, label? }`, referring to `modules[].id`.
- `reviews[]`: `id` (stable string), `number`, `title`, `author`, `branch`, `updated_at`, `risk_level`, `merge_decision`, `summary`, `files_changed`, `additions`, `deletions`, `affected_module_ids`, `findings`, `diff_path`, `diff`.
- `findings[]`: `id`, `file`, `line` (number/null), `severity`, `status` (`SUSPECTED | VERIFIED`), `title`, `explanation`, `recommendation`.
- `diff[]`: `{ kind: "add" | "remove" | "context", code: string, line: number | null }`.
- `merge_decision`: `PASS | REVIEW_REQUIRED | BLOCK | UNKNOWN`. Never convert an unverified AI guess into an automatic merge-blocking GitHub check without a clear enforced policy and human approval.

### Switch to a real FastAPI backend

Create `frontend/.env.local`:

```env
REPOGUARD_API_BASE_URL=http://127.0.0.1:8000
```

Restart `npm run dev`. The **Next.js server** calls `http://127.0.0.1:8000/api/dashboard` and forwards the result to the browser through its own `/api/dashboard` route. No CORS configuration is required for this flow. This environment variable is server-side only; **never put DeepSeek keys, GitHub app private keys or webhook secrets into `NEXT_PUBLIC_*` variables**.

For a quick placeholder implementation in FastAPI:

```python
import json
from pathlib import Path
from fastapi import FastAPI

app = FastAPI()

@app.get('/api/dashboard')
def dashboard():
    sample = Path('frontend/examples/dashboard-response.json')
    payload = json.loads(sample.read_text(encoding='utf-8'))
    payload['mode'] = 'live'
    return payload
```

Replace the placeholder with member A's scanner and PR risk analyzer. The data contract is deliberately backend-agnostic.

### Displaying real risks responsibly

- A module's importance is not the same as a verified code defect.
- Prefer `SUSPECTED` until a deterministic analyzer or test confirms the specific claim.
- `VERIFIED` means the described evidence has been observed; it does **not** automatically mean an exploit or production failure has been proven.
- Explicitly use `UNKNOWN` for unscanned or unsupported cases; do not label incomplete analysis “safe.”
- Source code and diffs are treated as untrusted data. Render them as text, not as executable HTML.

## Repo layout

```
frontend/
├── app/
│   ├── api/dashboard/route.ts     # Server-side FastAPI proxy; demo fallback when unconfigured
│   ├── globals.css                # Responsive dark UI
│   ├── layout.tsx
│   └── page.tsx
├── components/
│   ├── dashboard.tsx              # Main UI, navigation, review details, policies
│   └── impact-graph.tsx           # React Flow architecture graph
├── lib/
│   ├── demo-data.ts              # Mock data used in demo mode
│   └── types.ts                  # Typed API contract
├── examples/dashboard-response.json
├── scripts/validate-demo.mjs
└── .env.example
```

## Live GitHub integration

The frontend does **not** receive GitHub Webhooks or call DeepSeek itself. Public GitHub repository lookup only retrieves repository metadata, never private source code. Keep that in member A's FastAPI backend. This avoids leaking secrets in the browser. The frontend is purely a risk intelligence dashboard that consumes structured, reviewed API results.

## Development status

- Source files and TypeScript/TSX syntax were checked via the local TypeScript compiler/transpiler.
- Demo JSON passed the contract consistency test.
- Full `npm install` and `next build` could not be run in the artifact environment because its npm registry DNS lookup failed (`EAI_AGAIN`). Run `npm install && npm run build` on a computer with network access before demo deployment.
