import { NextRequest, NextResponse } from "next/server";
import { DEMO_DASHBOARD } from "@/lib/demo-data";
import type { DashboardPayload } from "@/lib/types";

export const dynamic = "force-dynamic";

const repoPattern = /^([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+)$/;
const headers = { "Cache-Control": "no-store" };

export async function GET(request: NextRequest) {
  const repository = request.nextUrl.searchParams.get("repository") ||
    `${DEMO_DASHBOARD.repository.owner}/${DEMO_DASHBOARD.repository.name}`;
  const match = repository.match(repoPattern);
  if (!match) return NextResponse.json({ error: "Invalid repository name. Use owner/repo." }, { status: 400 });
  const [, owner, name] = match;
  const base = process.env.REPOGUARD_API_BASE_URL?.trim().replace(/\/+$/, "");

  if (!base) {
    if (repository === `${DEMO_DASHBOARD.repository.owner}/${DEMO_DASHBOARD.repository.name}`) {
      return NextResponse.json(DEMO_DASHBOARD, { headers });
    }

    // Public repository selected, but no AI backend configured: NEVER fabricate its scan.
    try {
      const res = await fetch(`https://api.github.com/repos/${encodeURIComponent(owner)}/${encodeURIComponent(name)}`, {
        cache: "no-store", signal: AbortSignal.timeout(12000),
        headers: { Accept: "application/vnd.github+json", "User-Agent": "RepoGuard-AI-MVP" },
      });
      if (!res.ok) return NextResponse.json({ error: `Cannot read this public repository (GitHub HTTP ${res.status}).` }, { status: res.status === 404 ? 404 : 502 });
      const details = await res.json() as { private?: boolean; default_branch?: string; description?: string | null; language?: string | null; full_name?: string };
      if (details.private || details.full_name?.toLowerCase() !== repository.toLowerCase()) {
        return NextResponse.json({ error: "Repository is not publicly accessible." }, { status: 403 });
      }
      return NextResponse.json({
        mode: "unscanned",
        repository: {
          owner, name,
          default_branch: details.default_branch || "main",
          description: details.description || "",
          language: details.language || "Unknown",
          last_analyzed_at: "",
          tracked_files: 0, analyzed_files: 0, analysis_coverage: "UNKNOWN",
        },
        modules: [], dependencies: [], reviews: [],
      } satisfies DashboardPayload, { headers });
    } catch {
      return NextResponse.json({ error: "Unable to retrieve GitHub repository details." }, { status: 502 });
    }
  }

  try {
    // FastAPI MUST authorize access to the selected repository for the current user.
    const url = new URL(`${base}/api/dashboard`);
    url.searchParams.set("repository", repository);
    const response = await fetch(url, {
      cache: "no-store", signal: AbortSignal.timeout(12000),
      headers: { Accept: "application/json" },
    });
    if (!response.ok) return NextResponse.json(
      { error: `Backend returned HTTP ${response.status} for ${repository}. Check FastAPI /api/dashboard.` },
      { status: 502 },
    );

    const payload = (await response.json()) as DashboardPayload;
    if (!payload?.repository || !Array.isArray(payload.reviews) ||
        !Array.isArray(payload.modules) || !Array.isArray(payload.dependencies)) {
      return NextResponse.json({ error: "Backend response does not match DashboardPayload schema." }, { status: 502 });
    }
    if (`${payload.repository.owner}/${payload.repository.name}`.toLowerCase() !== repository.toLowerCase()) {
      return NextResponse.json({ error: "Backend returned analysis for another repository. Check repository filter." }, { status: 502 });
    }
    return NextResponse.json({ ...payload, mode: payload.mode === "unscanned" ? "unscanned" : "live" }, { headers });
  } catch {
    return NextResponse.json({ error: "Cannot reach the configured FastAPI backend. Confirm REPOGUARD_API_BASE_URL." }, { status: 502 });
  }
}
