import { NextRequest, NextResponse } from "next/server";
import { DEMO_DASHBOARD } from "@/lib/demo-data";
import type { RepositoryListResponse, RepositoryOption } from "@/lib/types";

export const dynamic = "force-dynamic";

const usernamePattern = /^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,37}[a-zA-Z0-9])?$/;
const repoPattern = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
const noStore = { "Cache-Control": "no-store" };

function isRepo(item: unknown): item is RepositoryOption {
  if (!item || typeof item !== "object") return false;
  const r = item as Record<string, unknown>;
  return typeof r.full_name === "string" && repoPattern.test(r.full_name) &&
    typeof r.name === "string" && typeof r.owner === "string" &&
    r.full_name === `${r.owner}/${r.name}` &&
    typeof r.private === "boolean";
}

export async function GET(request: NextRequest) {
  const base = process.env.REPOGUARD_API_BASE_URL?.trim().replace(/\/+$/, "");
  const owner = request.nextUrl.searchParams.get("owner")?.trim();

  // Production path: backend uses the current authenticated user's GitHub App installations.
  // Do not put GitHub tokens or App private keys in this frontend or browser.
  if (base) {
    try {
      const res = await fetch(`${base}/api/repositories`, {
        cache: "no-store", signal: AbortSignal.timeout(12000),
        headers: { Accept: "application/json" },
      });
      if (!res.ok) return NextResponse.json({ error: `Repository API returned HTTP ${res.status}` }, { status: 502 });
      const result = (await res.json()) as RepositoryListResponse;
      if (!Array.isArray(result.repositories) || !result.repositories.every(isRepo)) {
        return NextResponse.json({ error: "Backend repository list has an invalid format." }, { status: 502 });
      }
      return NextResponse.json({ source: "github-app", repositories: result.repositories }, { headers: noStore });
    } catch {
      return NextResponse.json({ error: "Cannot reach FastAPI /api/repositories." }, { status: 502 });
    }
  }

  // Public-only development mode (no GitHub authentication). Not App installation access.
  if (owner) {
    if (!usernamePattern.test(owner)) return NextResponse.json({ error: "Invalid GitHub username." }, { status: 400 });
    try {
      const res = await fetch(`https://api.github.com/users/${encodeURIComponent(owner)}/repos?sort=updated&per_page=100&type=owner`, {
        cache: "no-store", signal: AbortSignal.timeout(12000),
        headers: { Accept: "application/vnd.github+json", "User-Agent": "RepoGuard-AI-MVP" },
      });
      if (!res.ok) {
        const msg = res.status === 404 ? "GitHub account not found." :
          res.status === 403 ? "GitHub rate limit reached; try later or connect the App backend." :
            `GitHub returned HTTP ${res.status}.`;
        return NextResponse.json({ error: msg }, { status: res.status === 404 ? 404 : 502 });
      }
      const body = (await res.json()) as Array<Record<string, unknown>>;
      if (!Array.isArray(body)) throw new Error("Unexpected GitHub response");
      const repositories: RepositoryOption[] = body.map((item) => ({
        id: Number(item.id),
        full_name: String(item.full_name),
        name: String(item.name),
        owner: (item.owner as { login?: string } | null)?.login || owner,
        private: Boolean(item.private),
        description: typeof item.description === "string" ? item.description : "",
        default_branch: typeof item.default_branch === "string" ? item.default_branch : "main",
        html_url: String(item.html_url),
      })).filter(isRepo);
      return NextResponse.json({ source: "github-public", repositories }, { headers: noStore });
    } catch {
      return NextResponse.json({ error: "Could not fetch public GitHub repositories." }, { status: 502 });
    }
  }

  const r = DEMO_DASHBOARD.repository;
  return NextResponse.json({
    source: "demo",
    repositories: [{
      id: 0, full_name: `${r.owner}/${r.name}`, owner: r.owner, name: r.name,
      description: r.description, default_branch: r.default_branch, private: false,
      html_url: `https://github.com/${r.owner}/${r.name}`,
    }],
  } satisfies RepositoryListResponse, { headers: noStore });
}
