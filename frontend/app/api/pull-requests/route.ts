import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const repoPattern = /^([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+)$/;
const noStore = { "Cache-Control": "no-store" };

async function proxy(request: NextRequest, action: "list" | "analyze") {
  const repo = request.nextUrl.searchParams.get("repository") || "";
  const match = repo.match(repoPattern);
  if (!match) return NextResponse.json({ error: "Expected owner/repository." }, { status: 400 });

  const base = process.env.REPOGUARD_API_BASE_URL?.trim().replace(/\/+$/, "");
  const token = process.env.REPOGUARD_DASHBOARD_TOKEN;
  if (!base || !token || process.env.NODE_ENV !== "development") {
    return NextResponse.json({
      error: "PR reviews require an authenticated local FastAPI backend.",
    }, { status: 503 });
  }

  const numberRaw = request.nextUrl.searchParams.get("number") || "";
  if (action === "analyze" && (!/^[1-9][0-9]{0,7}$/.test(numberRaw))) {
    return NextResponse.json({ error: "Select a valid pull request number." }, { status: 400 });
  }
  const [, owner, name] = match;
  const path = `/api/repositories/${encodeURIComponent(owner)}/${encodeURIComponent(name)}/pulls` +
    (action === "analyze" ? `/${numberRaw}/analyze` : "");

  try {
    const response = await fetch(base + path, {
      method: action === "analyze" ? "POST" : "GET",
      cache: "no-store",
      signal: AbortSignal.timeout(25000),
      headers: { Accept: "application/json", Authorization: `Bearer ${token}` },
    });
    const body = await response.json() as { detail?: string; error?: string };
    if (!response.ok) return NextResponse.json({
      error: body.detail || body.error || `FastAPI HTTP ${response.status}`,
    }, { status: response.status, headers: noStore });
    return NextResponse.json(body, { status: response.status, headers: noStore });
  } catch {
    return NextResponse.json({
      error: "Cannot connect to FastAPI pull request review endpoint.",
    }, { status: 502, headers: noStore });
  }
}

export async function GET(request: NextRequest) {
  return proxy(request, "list");
}

export async function POST(request: NextRequest) {
  return proxy(request, "analyze");
}
