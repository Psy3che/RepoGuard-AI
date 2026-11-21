import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const repositoryPattern = /^([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+)$/;
const noStore = { "Cache-Control": "no-store" };

async function proxy(request: NextRequest, method: "GET" | "POST") {
  const repository = request.nextUrl.searchParams.get("repository") || "";
  const match = repository.match(repositoryPattern);
  if (!match) {
    return NextResponse.json({ error: "Select a valid owner/repository." }, { status: 400 });
  }

  const base = process.env.REPOGUARD_API_BASE_URL?.trim().replace(/\/+$/, "");
  const token = process.env.REPOGUARD_DASHBOARD_TOKEN;
  if (!base || !token || process.env.NODE_ENV !== "development") {
    return NextResponse.json({
      error: "Manual AI scans require the configured local FastAPI backend.",
    }, { status: 503 });
  }

  const [, owner, name] = match;
  try {
    const response = await fetch(
      `${base}/api/repositories/${encodeURIComponent(owner)}/${encodeURIComponent(name)}/scan`,
      {
        method,
        cache: "no-store",
        signal: AbortSignal.timeout(90000),
        headers: { Accept: "application/json", Authorization: `Bearer ${token}` },
      },
    );
    const body = await response.json() as { detail?: string; error?: string };
    if (!response.ok) {
      return NextResponse.json({
        error: body.detail || body.error || `Backend returned HTTP ${response.status}`,
      }, { status: response.status, headers: noStore });
    }
    return NextResponse.json(body, { status: response.status, headers: noStore });
  } catch {
    return NextResponse.json(
      { error: "Cannot reach FastAPI repository scan endpoint." },
      { status: 502, headers: noStore },
    );
  }
}

export async function GET(request: NextRequest) {
  return proxy(request, "GET");
}

export async function POST(request: NextRequest) {
  return proxy(request, "POST");
}
