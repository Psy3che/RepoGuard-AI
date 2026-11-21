"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity, AlertOctagon, AlertTriangle, ArrowDownRight, ArrowRight,
  ArrowUpRight, Bell, Box, Check, CheckCheck, CheckCircle2,
  ChevronDown, ChevronRight, CircleDot, Clipboard, Code2, Database,
  Download, ExternalLink, FileCode2, FileSearch, GitBranch, GitMerge,
  GitPullRequest, GitPullRequestArrow, HelpCircle, Layers3, LayoutDashboard,
  LockKeyhole, Menu, MoreHorizontal, Network, RefreshCw, Search,
  Shield, ShieldAlert, ShieldCheck, ShieldHalf, Sparkles, TerminalSquare,
  X, XCircle, Zap,
} from "lucide-react";
import { ImpactGraph } from "./impact-graph";
import type { DashboardPayload, Finding, Importance, PullRequestReview, RepoModule, RepositoryListResponse, RepositoryOption, RiskLevel } from "@/lib/types";

type View = "overview" | "architecture" | "reviews" | "policies";

type FetchState = { status: "loading" | "ready" | "error"; message?: string };

const riskRanks: Record<RiskLevel, number> = { CRITICAL: 5, HIGH: 4, MEDIUM: 3, UNKNOWN: 2, LOW: 1 };
const riskLabel: Record<RiskLevel, string> = { CRITICAL: "Critical", HIGH: "High", MEDIUM: "Medium", LOW: "Low", UNKNOWN: "Unknown" };

function RiskTag({ risk, compact = false }: { risk: RiskLevel | Importance; compact?: boolean }) {
  return <span className={`risk-tag risk-${risk.toLowerCase()} ${compact ? "risk-tag-sm" : ""}`}><span className="risk-dot" />{riskLabel[risk]}</span>;
}

function StatusTag({ decision }: { decision: PullRequestReview["merge_decision"] }) {
  const values = {
    PASS: { label: "Check passed", Icon: CheckCircle2, css: "status-pass" },
    REVIEW_REQUIRED: { label: "Needs review", Icon: AlertTriangle, css: "status-review" },
    BLOCK: { label: "Block merge", Icon: XCircle, css: "status-block" },
    UNKNOWN: { label: "Not verified", Icon: HelpCircle, css: "status-unknown" },
  };
  const item = values[decision];
  return <span className={`status-tag ${item.css}`}><item.Icon size={14} /> {item.label}</span>;
}

function Time({ value }: { value: string }) {
  const d = new Date(value);
  return <time dateTime={value}>{Number.isNaN(d.getTime()) ? value : d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</time>;
}

function EmptyState({ heading, detail }: { heading: string; detail: string }) {
  return <div className="empty-state"><FileSearch size={26} /><strong>{heading}</strong><span>{detail}</span></div>;
}

function SectionHead({ eyebrow, title, caption, right }: { eyebrow?: string; title: string; caption?: string; right?: React.ReactNode }) {
  return <div className="section-head"><div>{eyebrow && <div className="eyebrow">{eyebrow}</div>}<h2>{title}</h2>{caption && <p>{caption}</p>}</div>{right}</div>;
}

function ReviewRow({ review, active, onClick }: { review: PullRequestReview; active?: boolean; onClick: () => void }) {
  return <button className={`review-row ${active ? "selected" : ""}`} onClick={onClick}>
    <div className="review-icon"><GitPullRequest size={17} /></div>
    <div className="review-body">
      <div className="review-title">{review.title}</div>
      <div className="review-meta"><span>#{review.number}</span><span className="bullet">·</span><span>{review.author}</span><span className="bullet">·</span><span>{review.files_changed} files</span></div>
    </div>
    <RiskTag risk={review.risk_level} compact />
    <ChevronRight className="review-chevron" size={16} />
  </button>;
}

function FindingCard({ finding }: { finding: Finding }) {
  return <div className="finding-card">
    <div className="finding-top"><RiskTag risk={finding.severity} compact /><span className={`evidence-status ${finding.status.toLowerCase()}`}>{finding.status === "VERIFIED" ? "Observed in diff" : "Requires verification"}</span></div>
    <h4>{finding.title}</h4>
    <p>{finding.explanation}</p>
    <div className="finding-code"><FileCode2 size={13} /><span>{finding.file}{finding.line ? `:${finding.line}` : ""}</span></div>
    <div className="finding-fix"><Sparkles size={15} /><span>{finding.recommendation}</span></div>
  </div>;
}

function DiffViewer({ review }: { review: PullRequestReview }) {
  return <div className="diff-wrapper"><div className="diff-header"><div><Code2 size={15} /> {review.diff_path}</div><span>Illustrative patch context</span></div><div className="diff-lines">{review.diff.map((line, i) => <div key={`${i}-${line.code}`} className={`diff-line diff-${line.kind}`}><span className="diff-ln">{line.line ?? ""}</span><span className="diff-marker">{line.kind === "add" ? "+" : line.kind === "remove" ? "−" : " "}</span><code>{line.code}</code></div>)}</div></div>;
}

function RepositoryPicker({ repositories, source, selected, loading, error, open, setOpen, owner, setOwner, onSearch, onSelect }: {
  repositories: RepositoryOption[];
  source: RepositoryListResponse["source"];
  selected: string | null;
  loading: boolean;
  error: string | null;
  open: boolean;
  setOpen: (value: boolean) => void;
  owner: string;
  setOwner: (value: string) => void;
  onSearch: (owner: string) => void;
  onSelect: (repo: string) => void;
}) {
  const current = repositories.find((r) => r.full_name === selected);
  return <div className="repo-picker">
    <button className="sidebar-repo repo-picker-trigger" type="button" aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen(!open)}>
      <div className="repo-avatar"><Database size={18}/></div>
      <div className="sidebar-repo-text"><small>ACTIVE REPOSITORY</small><strong title={selected || "No repository selected"}>{current?.full_name || selected || "Select a repository"}</strong></div>
      <ChevronDown className={open ? "repo-picker-chevron open" : "repo-picker-chevron"} size={15}/>
    </button>
    {open && <div className="repo-picker-panel" role="dialog" aria-label="Select a GitHub repository" onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }}>
      <div className="repo-picker-heading"><strong>Choose repository</strong><span>{source === "github-app" ? "App installations" : source === "github-public" ? "GitHub public repos" : "Demo workspace"}</span></div>
      {source !== "github-app" && <form className="repo-owner-form" onSubmit={(e) => { e.preventDefault(); if (owner.trim()) onSearch(owner.trim()); }}>
        <label htmlFor="github-owner">Find public repositories by GitHub username</label>
        <div className="repo-owner-row"><input id="github-owner" value={owner} onChange={(e) => setOwner(e.target.value)} placeholder="e.g. octocat" spellCheck={false} autoComplete="off" maxLength={39}/><button type="submit" disabled={loading || !owner.trim()} aria-label="Find GitHub repositories"><Search size={16}/></button></div>
      </form>}
      {error && <div className="repo-picker-error" role="alert">{error}</div>}
      {loading ? <div className="repo-picker-state"><RefreshCw className="spinning" size={14}/> Fetching repositories...</div> :
      <div className="repo-picker-list" role="listbox" aria-label="Available repositories">
        {repositories.map((r) => <button key={r.full_name} role="option" aria-selected={r.full_name === selected} className={`repo-picker-option ${r.full_name === selected ? "active" : ""}`} type="button" onClick={() => { onSelect(r.full_name); setOpen(false); }}>
          <span className="repo-picker-option-icon"><GitBranch size={15}/></span>
          <span className="repo-picker-option-details"><strong>{r.name}</strong><small>{r.owner} · {r.private ? "Private" : "Public"}</small></span>
          {r.full_name === selected && <Check size={15} className="repo-selected-check"/>}
        </button>)}
        {!repositories.length && <p className="repo-picker-state">No accessible repositories found. Check App installation permissions or the GitHub username.</p>}
      </div>}
      {source === "demo" && <p className="repo-picker-hint">Demo data is simulated. Search a GitHub username for real public repositories.</p>}
      {source === "github-public" && <p className="repo-picker-hint">Public repos only · up to 100 recently updated. AI scanning requires the FastAPI backend.</p>}
      {source === "github-app" && <p className="repo-picker-hint">Repositories authorized for the connected GitHub App.</p>}
    </div>}
  </div>;
}

function UnscannedRepository({ owner, name }: { owner: string; name: string }) {
  const url = `https://github.com/${encodeURIComponent(owner)}/${encodeURIComponent(name)}`;
  return <section className="unscanned-panel panel">
    <div className="unscanned-symbol"><GitBranch size={32}/></div>
    <span className="eyebrow">REAL GITHUB REPOSITORY</span>
    <h2>{owner}/{name}</h2>
    <p>This repository was fetched from GitHub, but <strong>RepoGuard has not analyzed its code yet.</strong> We deliberately do not show simulated risk scores for a real repository.</p>
    <div className="unscanned-actions"><a href={url} target="_blank" rel="noreferrer" className="secondary-button">Open on GitHub <ExternalLink size={15}/></a></div>
    <div className="unscanned-tip"><ShieldAlert size={17}/><span>To enable live core-module discovery and PR risk reports, install RepoGuard GitHub App and connect the FastAPI <code>/api/dashboard?repository=owner/repo</code> endpoint.</span></div>
  </section>;
}

function Overview({ data, goToReview, goToArchitecture, goToReviews }: { data: DashboardPayload; goToReview: (id: string) => void; goToArchitecture: () => void; goToReviews: () => void }) {
  const { repository, modules, reviews, dependencies } = data;
  const protectedCount = modules.filter((m) => m.protected).length;
  const highCount = reviews.filter((r) => riskRanks[r.risk_level] >= 4).length;
  const latest = [...reviews].sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
  const important = [...modules].sort((a, b) => riskRanks[b.importance] - riskRanks[a.importance]).slice(0, 4);
  return <>
    <div className="hero-panel">
      <div className="hero-glow hero-glow-a" /><div className="hero-glow hero-glow-b" />
      <div className="hero-inner">
        <div className="hero-overline"><Sparkles size={14} /> REPOSITORY INTELLIGENCE <span>•</span> AI-ASSISTED SECURITY</div>
        <h1>See the impact.<br /><span>Merge with confidence.</span></h1>
        <p>A clear picture of what matters in your codebase — and what every change could break.</p>
        <div className="hero-actions"><button className="primary-button" onClick={goToReviews}>Review pull requests <ArrowRight size={16} /></button><button className="ghost-button" onClick={goToArchitecture}>Explore architecture <Network size={16} /></button></div>
      </div>
      <div className="hero-decoration" aria-hidden="true"><div className="dec-node dec-node-one"><Shield size={21} /></div><div className="dec-ring dec-ring-one" /><div className="dec-ring dec-ring-two" /><div className="dec-node dec-node-two"><Code2 size={18} /></div><div className="dec-node dec-node-three"><GitMerge size={18} /></div><div className="dec-line dec-line-one"/><div className="dec-line dec-line-two"/></div>
    </div>
    <div className="metrics-grid">
      <button className="metric-card" onClick={goToArchitecture}><div className="metric-top"><span className="metric-icon purple"><Layers3 size={20}/></span><span className="metric-trend"><ArrowUpRight size={13}/> Repository map</span></div><div className="metric-value">{modules.length.toString().padStart(2, "0")}</div><div className="metric-title">Identified modules</div><div className="metric-sub">Across {repository.analyzed_files} analyzed files</div></button>
      <button className="metric-card" onClick={goToArchitecture}><div className="metric-top"><span className="metric-icon orange"><ShieldAlert size={20}/></span><span className="metric-trend">Guarded paths</span></div><div className="metric-value">{protectedCount.toString().padStart(2, "0")}</div><div className="metric-title">Protected modules</div><div className="metric-sub">High-impact code areas</div></button>
      <button className="metric-card" onClick={goToReviews}><div className="metric-top"><span className="metric-icon blue"><GitPullRequest size={20}/></span><span className="metric-trend">In analysis</span></div><div className="metric-value">{reviews.length.toString().padStart(2, "0")}</div><div className="metric-title">Pull requests tracked</div><div className="metric-sub">{highCount} require close attention</div></button>
      <button className="metric-card" onClick={goToArchitecture}><div className="metric-top"><span className="metric-icon green"><Network size={20}/></span><span className="metric-trend">Dependency map</span></div><div className="metric-value">{dependencies.length.toString().padStart(2, "0")}</div><div className="metric-title">Mapped dependencies</div><div className="metric-sub">Observed architecture links</div></button>
    </div>
    <div className="overview-grid">
      <section className="panel recent-panel"><div className="panel-titlebar"><div><span className="eyebrow">CHANGE MONITOR</span><h3>Recent pull requests</h3></div><button className="text-link" onClick={goToReviews}>View all <ArrowRight size={14}/></button></div><div className="recent-list">{latest.slice(0, 4).map((r) => <ReviewRow review={r} key={r.id} onClick={() => goToReview(r.id)} />)}</div></section>
      <section className="panel critical-panel"><div className="panel-titlebar"><div><span className="eyebrow">PROTECTION MAP</span><h3>Critical components</h3></div><button className="icon-button subtle" onClick={goToArchitecture} title="Open dependency map" aria-label="Open dependency map"><ArrowUpRight size={17}/></button></div><div className="critical-list">{important.map((m, i) => <button className="critical-item" onClick={goToArchitecture} key={m.id}><span className="critical-number">0{i + 1}</span><span className="critical-item-main"><strong>{m.name}</strong><small>{m.path}</small></span><RiskTag risk={m.importance} compact/></button>)}</div><div className="critical-footer"><ShieldCheck size={15} /> Criticality is a recommendation, not a proof of defect.</div></section>
    </div>
    <section className="health-banner"><div className="health-icon"><Activity size={22}/></div><div><strong>Repository scan overview</strong><p>{repository.analyzed_files} of {repository.tracked_files} tracked files included in the current analysis context. Coverage: {repository.analysis_coverage.toLowerCase()}. Unscanned code may contain additional risks.</p></div><button onClick={goToArchitecture}>View map <ArrowRight size={14}/></button></section>
  </>;
}

function Architecture({ data, selectedModule, setSelectedModule, selectedReviewId, onReviewChange }: { data: DashboardPayload; selectedModule: string | null; setSelectedModule: (id: string) => void; selectedReviewId: string; onReviewChange: (id: string) => void }) {
  const selectedReview = data.reviews.find((r) => r.id === selectedReviewId);
  const selected = data.modules.find((m) => m.id === selectedModule) || data.modules[0];
  return <>
    <SectionHead eyebrow="REPOSITORY INTELLIGENCE" title="Architecture & blast radius" caption="Explore high-value modules, their connections, and the possible downstream effect of a PR." right={<div className="field-inline"><span>Highlight PR</span><select aria-label="Highlight pull request" value={selectedReviewId} onChange={(e) => onReviewChange(e.target.value)}><option value="none">No highlight</option>{data.reviews.map((r) => <option value={r.id} key={r.id}>#{r.number} · {riskLabel[r.risk_level]}</option>)}</select><ChevronDown size={14}/></div>}/>
    <div className="graph-layout"><div className="panel graph-panel"><div className="graph-toolbar"><div className="graph-toolbar-left"><span className="live-dot" /> Dependency map <span className="graph-toolbar-divider"/> {data.modules.length} modules · {data.dependencies.length} links</div><div className="graph-legend"><span><i className="legend-dot red"/>Critical</span><span><i className="legend-dot yellow"/>High</span><span><i className="legend-dot cyan"/>Impacted</span></div></div><ImpactGraph modules={data.modules} dependencies={data.dependencies} impactedIds={selectedReview?.affected_module_ids || []} selectedId={selected?.id} onSelect={setSelectedModule}/></div>
      <div className="panel module-detail"><div className="detail-top"><span className="eyebrow">MODULE INSPECTOR</span><Box size={17}/></div>{selected ? <><div className="module-icon"><LockKeyhole size={24}/></div><h3>{selected.name}</h3><div className="module-path">{selected.path}</div><div className="module-tags"><RiskTag risk={selected.importance}/>{selected.protected && <span className="protected-tag"><Shield size={13}/> Guarded</span>}</div><div className="detail-divider"/><div className="detail-caption">WHY IT MATTERS</div><p>{selected.reason}</p><div className="detail-divider"/><div className="detail-caption">MODULE CATEGORY</div><div className="detail-property">{selected.category}</div><div className="detail-caption">OBSERVED CONNECTIONS</div><div className="detail-property">{data.dependencies.filter((d) => d.source === selected.id || d.target === selected.id).length} direct links</div>{selectedReview?.affected_module_ids.includes(selected.id) && <div className="module-warning"><AlertTriangle size={16}/><span>Included in the potential impact scope of PR #{selectedReview.number}.</span></div>}</> : <EmptyState heading="Select a module" detail="Choose any node on the graph" />}</div></div>
    <div className="modules-heading"><h3>Module inventory</h3><span>{data.modules.length} modules mapped</span></div><div className="module-table-wrap"><table className="module-table"><thead><tr><th>MODULE</th><th>CATEGORY</th><th>IMPORTANCE</th><th>PROTECTION</th><th>CONNECTIONS</th></tr></thead><tbody>{data.modules.map((m) => <tr key={m.id} onClick={() => { setSelectedModule(m.id); window.scrollTo({ top: 130, behavior: "smooth" }); }}><td><div className="module-table-primary"><FileCode2 size={17}/><span><strong>{m.name}</strong><small>{m.path}</small></span></div></td><td>{m.category}</td><td><RiskTag risk={m.importance} compact/></td><td>{m.protected ? <span className="protected-inline"><Shield size={14}/> Guarded</span> : <span className="muted">Monitored</span>}</td><td>{data.dependencies.filter((d) => d.source === m.id || d.target === m.id).length}</td></tr>)}</tbody></table></div>
  </>;
}

function Reviews({ data, selectedReviewId, onSelectReview }: { data: DashboardPayload; selectedReviewId: string; onSelectReview: (id: string) => void }) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("ALL");
  const [copied, setCopied] = useState(false);
  const reviews = useMemo(() => data.reviews.filter((r) => (filter === "ALL" || r.risk_level === filter) && `${r.title} ${r.author} ${r.number}`.toLowerCase().includes(query.toLowerCase())).sort((a,b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()), [data.reviews, query, filter]);
  const selected = data.reviews.find((r) => r.id === selectedReviewId) || data.reviews[0];
  const download = () => {
    if (!selected) return;
    const blob = new Blob([JSON.stringify(selected, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `repoguard-pr-${selected.number}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };
  const copySummary = async () => {
    if (!selected) return;
    const text = `RepoGuard AI · PR #${selected.number}\nRisk: ${selected.risk_level}\nDecision: ${selected.merge_decision}\n${selected.summary}\n\nFindings:\n${selected.findings.map((f) => `- ${f.title} (${f.status}): ${f.explanation}`).join("\n")}`;
    try { await navigator.clipboard.writeText(text); setCopied(true); window.setTimeout(() => setCopied(false), 1900); } catch { setCopied(false); }
  };
  return <>
    <SectionHead eyebrow="PULL REQUEST INTELLIGENCE" title="Code review workspace" caption="Investigate change risk, impacted modules, evidence, and merge readiness." right={<div className="counter-chip"><GitPullRequest size={14}/> {data.reviews.length} reviews</div>}/>
    <div className="reviews-layout"><div className="panel reviews-list-panel"><div className="reviews-list-head"><div className="searchbox"><Search size={16}/><input placeholder="Search PRs..." aria-label="Search pull requests" value={query} onChange={(e) => setQuery(e.target.value)}/></div><div className="filter-strip">{["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"].map((type) => <button key={type} className={filter === type ? "filter-active" : ""} onClick={() => setFilter(type)}>{type === "ALL" ? "All" : riskLabel[type as RiskLevel]}</button>)}</div></div><div className="reviews-scroll">{reviews.length ? reviews.map((review) => <ReviewRow key={review.id} review={review} active={selected.id === review.id} onClick={() => onSelectReview(review.id)}/>) : <EmptyState heading="No matching pull requests" detail="Adjust your search or risk filter." />}</div><div className="reviews-list-foot"><CircleDot size={13} /> AI suggestions require independent verification.</div></div>
      <div className="review-content">{selected ? <><div className="review-main-card panel"><div className="review-detail-top"><div className="review-number"><GitPullRequest size={17}/> PULL REQUEST #{selected.number}</div><RiskTag risk={selected.risk_level}/></div><h2>{selected.title}</h2><div className="review-detail-meta"><span><GitBranch size={14}/>{selected.branch}</span><span>by {selected.author}</span><span><Time value={selected.updated_at}/></span></div><div className="summary-box"><div className="summary-head"><Sparkles size={16}/> AI RISK SUMMARY</div><p>{selected.summary}</p></div><div className="merge-bar"><StatusTag decision={selected.merge_decision}/><div>{selected.files_changed} files changed <span className="additions">+{selected.additions}</span><span className="deletions">−{selected.deletions}</span></div></div></div>
      <div className="review-quick-actions"><button onClick={copySummary}><Clipboard size={15}/>{copied ? "Copied" : "Copy summary"}</button><button onClick={download}><Download size={15}/>Export JSON</button></div>
      <div className="risk-head"><div><span className="eyebrow">CHANGE FINDINGS</span><h3>Analysis evidence <span>({selected.findings.length})</span></h3></div><span className="small-note">Suspected ≠ verified</span></div>
      {selected.findings.length ? <div className="findings-grid">{selected.findings.map((f) => <FindingCard finding={f} key={f.id}/>)}</div> : <div className="panel no-findings"><CheckCircle2 size={22}/><div><strong>No material risk found in the available context</strong><p>Checks passing does not guarantee correctness. Unanalyzed files or missing tests may still hide problems.</p></div></div>}
      <div className="risk-head impact-heading"><div><span className="eyebrow">BLAST RADIUS</span><h3>Potentially affected modules <span>({selected.affected_module_ids.length})</span></h3></div></div>
      <div className="impact-chips">{selected.affected_module_ids.map((id) => { const m = data.modules.find((x) => x.id === id); return m ? <span className="impact-chip" key={id}><Network size={14}/>{m.name}<RiskTag risk={m.importance} compact/></span> : <span className="impact-chip" key={id}>{id}</span>; })}</div>
      <div className="risk-head diff-heading"><div><span className="eyebrow">DIFF CONTEXT</span><h3>Code changes</h3></div></div><DiffViewer review={selected}/>
      </> : <EmptyState heading="No PR selected" detail="Select a pull request to inspect its risk report."/>}</div></div>
  </>;
}

function Policies({ data }: { data: DashboardPayload }) {
  const guards = data.modules.filter((m) => m.protected);
  return <><SectionHead eyebrow="REPOSITORY GUARDRAILS" title="Protection policies" caption="See which areas the current analysis recommends for additional review." right={<div className="counter-chip"><ShieldHalf size={14}/> Read-only preview</div>}/>
    <div className="policy-callout"><div className="policy-callout-icon"><LockKeyhole size={23}/></div><div><h3>Review before enforcing</h3><p>RepoGuard recommends protected paths using available evidence. A repository maintainer should confirm them before treating these recommendations as merge gates.</p></div></div>
    <div className="policy-list">{guards.map((m) => <div className="policy-row" key={m.id}><div className="policy-symbol"><Shield size={19}/></div><div><h4>{m.name}</h4><code>{m.path}</code><p>{m.reason}</p></div><div className="policy-level"><RiskTag risk={m.importance}/><span>Review recommended</span></div></div>)}</div>
    <div className="policy-bottom-note"><AlertTriangle size={17}/><p>Protection recommendations do not automatically configure GitHub branch rules, CODEOWNERS, or merge blocks. Those require explicit repository settings and a trusted backend decision process.</p></div>
  </>;
}

export function Dashboard() {
  const [view, setView] = useState<View>("overview");
  const [data, setData] = useState<DashboardPayload | null>(null);
  const [fetchState, setFetchState] = useState<FetchState>({ status: "loading" });
  const [selectedReviewId, setSelectedReviewId] = useState<string>("");
  const [selectedModule, setSelectedModule] = useState<string | null>(null);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [repositories, setRepositories] = useState<RepositoryOption[]>([]);
  const [repositorySource, setRepositorySource] = useState<RepositoryListResponse["source"]>("demo");
  const [selectedRepository, setSelectedRepository] = useState<string | null>(null);
  const [repoPickerOpen, setRepoPickerOpen] = useState(false);
  const [repoLoading, setRepoLoading] = useState(true);
  const [repoError, setRepoError] = useState<string | null>(null);
  const [githubOwner, setGithubOwner] = useState("");
  const requestId = useRef(0);

  const loadRepositories = useCallback(async (owner?: string) => {
    setRepoLoading(true);
    setRepoError(null);
    try {
      const suffix = owner ? `?owner=${encodeURIComponent(owner)}` : "";
      const response = await fetch(`/api/repositories${suffix}`, { cache: "no-store" });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Could not fetch GitHub repositories.");
      const payload = result as RepositoryListResponse;
      if (!Array.isArray(payload.repositories)) throw new Error("Unexpected repository API response.");
      setRepositories(payload.repositories);
      setRepositorySource(payload.source);
      setSelectedRepository((prev) => payload.repositories.some((r) => r.full_name === prev) ? prev : payload.repositories[0]?.full_name || null);
      if (!payload.repositories.length) { setData(null); setFetchState({status: "error", message: "No repositories available. Install RepoGuard App or choose a public GitHub username."}); }
    } catch (err) {
      setRepoError(err instanceof Error ? err.message : "Repository lookup failed.");
      setRepoPickerOpen(true);
    } finally {
      setRepoLoading(false);
    }
  }, []);

  const load = useCallback(async (repository: string) => {
    const current = ++requestId.current;
    setRefreshing(true);
    setData(null); // Never show one repository's risk report under another name.
    setFetchState({ status: "loading" });
    try {
      const response = await fetch(`/api/dashboard?repository=${encodeURIComponent(repository)}`, { cache: "no-store" });
      const json = await response.json();
      if (!response.ok) throw new Error(json.error || "Unable to load dashboard data.");
      const payload = json as DashboardPayload;
      if (`${payload.repository.owner}/${payload.repository.name}`.toLowerCase() !== repository.toLowerCase()) {
        throw new Error("The dashboard returned information for another repository.");
      }
      if (current !== requestId.current) return;
      setData(payload);
      setSelectedReviewId(payload.reviews[0]?.id || "");
      setSelectedModule(payload.modules[0]?.id || null);
      setFetchState({ status: "ready" });
    } catch (err) {
      if (current !== requestId.current) return;
      setFetchState({ status: "error", message: err instanceof Error ? err.message : "Unexpected error" });
    } finally { if (current === requestId.current) setRefreshing(false); }
  }, []);

  useEffect(() => { void loadRepositories(); }, [loadRepositories]);
  useEffect(() => { if (selectedRepository) void load(selectedRepository); }, [selectedRepository, load]);

  const go = (v: View) => { setView(v); setMobileNavOpen(false); window.scrollTo({ top: 0, behavior: "smooth" }); };
  const goToReview = (id: string) => { setSelectedReviewId(id); go("reviews"); };
  const repo = data?.repository;
  const selectedReview = data?.reviews.find((r) => r.id === selectedReviewId);

  const navItems: { id: View; title: string; Icon: typeof LayoutDashboard; count?: number }[] = [
    { id: "overview", title: "Overview", Icon: LayoutDashboard },
    { id: "architecture", title: "Architecture map", Icon: Network },
    { id: "reviews", title: "Pull requests", Icon: GitPullRequest, count: data?.reviews.length },
    { id: "policies", title: "Protection policies", Icon: ShieldCheck },
  ];

  return <div className="app-shell">
    {mobileNavOpen && <button className="mobile-backdrop" aria-label="Close sidebar" onClick={() => setMobileNavOpen(false)}/>}
    <aside className={`sidebar ${mobileNavOpen ? "sidebar-open" : ""}`}>
      <div className="brand"><div className="brand-icon"><ShieldHalf size={22} strokeWidth={2.3}/></div><div className="brand-name">RepoGuard<span>AI</span><small>REPOSITORY INTELLIGENCE</small></div><button className="close-sidebar" onClick={() => setMobileNavOpen(false)} aria-label="Close sidebar"><X size={18}/></button></div>
      <RepositoryPicker repositories={repositories} source={repositorySource} selected={selectedRepository} loading={repoLoading} error={repoError} open={repoPickerOpen} setOpen={setRepoPickerOpen} owner={githubOwner} setOwner={setGithubOwner} onSearch={(owner) => void loadRepositories(owner)} onSelect={setSelectedRepository}/>
      <div className="sidebar-section-label">WORKSPACE</div>
      <nav className="sidebar-nav" aria-label="Main navigation">{navItems.map(({ id, title, Icon, count }) => <button key={id} className={view === id ? "nav-active" : ""} onClick={() => go(id)}><Icon size={18}/><span>{title}</span>{typeof count === "number" && <span className="nav-count">{count}</span>}</button>)}</nav>
      <div className="sidebar-section-label sidebar-second-label">STATUS</div>
      <div className="sidebar-status"><div><span className="sidebar-status-dot"/> Analysis pipeline</div><strong>{fetchState.status === "ready" ? "Ready" : fetchState.status === "loading" ? "Loading" : "Unavailable"}</strong></div>
      <div className="sidebar-bottom"><div className="side-note"><span className="side-note-star"><Zap size={15}/></span><strong>Ship with confidence</strong><p>Understand change impact before pressing merge.</p></div><div className="sidebar-footer"><span className="footer-avatar">RG</span><div><strong>RepoGuard Workspace</strong><small>Hackathon MVP · v0.1</small></div><MoreHorizontal size={18}/></div></div>
    </aside>
    <div className="content-shell"><header className="topbar"><div className="topbar-left"><button className="menu-toggle" onClick={() => setMobileNavOpen(true)} aria-label="Open sidebar"><Menu size={20}/></button><span className="breadcrumb-dim">Workspace</span><ChevronRight size={14} className="breadcrumb-arrow"/><span className="breadcrumb-current">{navItems.find((x) => x.id === view)?.title}</span></div><div className="topbar-right">{data && <span className={`mode-tag ${data.mode === "demo" ? "mode-demo" : data.mode === "unscanned" ? "mode-unscanned" : "mode-live"}`}><span/> {data.mode === "demo" ? "DEMO DATA" : data.mode === "unscanned" ? "NOT SCANNED" : "LIVE BACKEND"}</span>}<button className={`toolbar-button ${refreshing ? "spinning" : ""}`} onClick={() => selectedRepository && void load(selectedRepository)} disabled={refreshing || !selectedRepository} title="Refresh analysis" aria-label="Refresh analysis"><RefreshCw size={17}/></button><span className="topbar-divider"/><span className="topbar-avatar">RG</span></div></header>
      <main className="page-content">
        {fetchState.status === "error" && <div className="load-error"><AlertOctagon size={25}/><div><strong>Backend connection failed</strong><p>{fetchState.message}</p><p>Check your repository permissions, FastAPI endpoints and REPOGUARD_API_BASE_URL.</p></div><button className="secondary-button" onClick={() => selectedRepository ? void load(selectedRepository) : void loadRepositories()}>Retry <RefreshCw size={15}/></button></div>}
        {(fetchState.status === "loading" || repoLoading) && !data && <div className="loading-screen"><div className="spinner"/><h2>Loading repository intelligence</h2><p>Preparing modules and pull request findings...</p></div>}
        {data && <>
          <div className="page-overview"><div className="page-repo-line"><span className="line-badge"><GitBranch size={14}/>{repo?.default_branch || "main"}</span><span className="tiny-divider"/><span>{repo?.owner}/{repo?.name}</span><span className="tiny-divider"/><span>{repo?.last_analyzed_at ? <>Last scan <Time value={repo.last_analyzed_at}/></> : "Not analyzed"}</span></div><span className="analysis-disclaimer"><CircleDot size={12}/>{data.mode === "demo" ? "All results are simulated" : data.mode === "unscanned" ? "GitHub metadata only — no AI scan" : "AI findings may need verification"}</span></div>
          {data.mode === "unscanned" ? <UnscannedRepository owner={data.repository.owner} name={data.repository.name}/> : <>
          {view === "overview" && <Overview data={data} goToReview={goToReview} goToReviews={() => go("reviews")} goToArchitecture={() => go("architecture")}/>}
          {view === "architecture" && <Architecture data={data} selectedModule={selectedModule} setSelectedModule={setSelectedModule} selectedReviewId={selectedReviewId} onReviewChange={(id) => setSelectedReviewId(id)}/>}
          {view === "reviews" && <Reviews data={data} selectedReviewId={selectedReviewId} onSelectReview={setSelectedReviewId}/>}
          {view === "policies" && <Policies data={data}/>}
          </>}
          <footer className="page-footer"><span>RepoGuard AI © 2026</span><span><ShieldCheck size={13}/> Safe merging starts with clear evidence</span><span>{selectedReview ? `Selected PR #${selectedReview.number}` : "Repository intelligence"}</span></footer>
        </>}
      </main>
    </div>
  </div>;
}
