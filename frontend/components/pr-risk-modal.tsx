"use client";

import { useEffect, useRef } from "react";
import {
  AlertTriangle, ArrowRight, CheckCircle2, ExternalLink, FileCode2,
  GitPullRequest, RefreshCw, ShieldAlert, ShieldCheck, Sparkles, X, XCircle,
} from "lucide-react";
import type { PullRequestReview } from "@/lib/types";

interface Props {
  repository: string;
  number: number;
  review?: PullRequestReview;
  sample: boolean;
  onClose: () => void;
  onViewDetails?: () => void;
}

export function RiskReviewModal({ repository, number, review, sample, onClose, onViewDetails }: Props) {
  const closeButton = useRef<HTMLButtonElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    const before = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButton.current?.focus();

    const handleKeydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); onCloseRef.current(); }
      if (event.key !== "Tab" || !cardRef.current) return;
      const focusables = Array.from(cardRef.current.querySelectorAll<HTMLElement>(
        'button:not(:disabled), a[href], [tabindex]:not([tabindex="-1"])',
      ));
      if (focusables.length === 0) return;
      const first = focusables[0], last = focusables[focusables.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first.focus();
      }
    };
    document.addEventListener("keydown", handleKeydown);
    return () => {
      document.body.style.overflow = before;
      document.removeEventListener("keydown", handleKeydown);
    };
  }, []);

  const jobStatus = review?.review_status ?? "PENDING";
  const working = !sample && (jobStatus === "PENDING" || jobStatus === "RUNNING");
  const failed = !sample && jobStatus === "FAILED";
  const verified = Boolean(review?.findings.some(f => f.status === "VERIFIED" &&
    (f.severity === "CRITICAL" || f.severity === "HIGH")));
  const low = !working && !failed && review?.risk_level === "LOW" && review.merge_decision === "PASS";
  const high = !working && !failed && (verified ||
    review?.risk_level === "HIGH" || review?.risk_level === "CRITICAL");
  const type = working ? "progress" : failed ? "unknown" :
    verified ? "critical" : low ? "low" : high ? "high" :
      review?.risk_level === "MEDIUM" ? "medium" : "unknown";

  const title = working ? "Pull Request Risk Analysis" : failed ? "Analysis Unavailable" :
    verified ? "Verified Issue · Do Not Merge" :
    low ? "No Blocking Findings" :
    high ? "High-Risk Change Warning" :
    review?.risk_level === "MEDIUM" ? "Review Recommended" : "Risk Could Not Be Determined";
  const description = working
    ? "A new pull request or commit was detected. Checking changed code, repository-critical modules, and possible downstream impact."
    : failed ? "Analysis failed, so the system cannot recommend merging. Check FastAPI logs and retry."
    : low ? "No blocking issues were identified within the reviewed scope. This is not proof of correctness; normal tests and review are still needed."
    : high ? "This change may affect critical logic or introduce a regression. Inspect the affected files and recommendations before merging."
    : "There is incomplete evidence or possible impact. Review the changes manually before merging.";

  const summary = review?.summary || "Waiting for the RepoGuard AI analysis result...";
  const provenance = review?.ai_review;
  const hasDeepSeekResult = provenance?.status === "COMPLETED" && provenance.provider === "DeepSeek";
  const modelVerdict = provenance?.model_risk_level;
  const adjusted = Boolean(modelVerdict && modelVerdict !== review?.risk_level);
  const adjustmentReasons = provenance?.adjustments || [];
  const affected = [...new Set([
    ...(review?.important_touched_files ?? []),
    ...(review?.dependent_files ?? []),
    ...(review?.findings.map(f => f.file) ?? []),
  ])].slice(0, 8);
  const recommendations = (review?.findings ?? [])
    .map(f => f.recommendation).filter(Boolean).slice(0, 3);
  const label = working ? "ANALYSIS RUNNING" : failed ? "FAILED" :
    review?.risk_level || "UNKNOWN";

  const prUrl = /^[-A-Za-z0-9_.]+\/[-A-Za-z0-9_.]+$/.test(repository) && number > 0
    ? `https://github.com/${repository}/pull/${number}` : null;
  const Icon = type === "low" ? ShieldCheck : type === "progress" ? RefreshCw :
    type === "critical" ? XCircle : ShieldAlert;

  return <div className="risk-modal-backdrop" onMouseDown={event => {
    if (event.target === event.currentTarget) onClose();
  }}>
    <div className={`risk-modal-card risk-modal-${type}`} role="dialog"
      aria-modal="true" aria-labelledby="risk-modal-title"
      aria-describedby="risk-modal-description" ref={cardRef}>
      <header className="risk-modal-header">
        <span className="risk-modal-kicker"><GitPullRequest size={15}/>
          PR #{number} · {repository}
        </span>
        <button ref={closeButton} aria-label="Close risk report" className="risk-modal-close"
          type="button" onClick={onClose}><X size={22}/></button>
      </header>
      {sample && <div className="risk-modal-demo-note" role="note">
        <Sparkles size={15}/> DEMO PREVIEW · Illustrative result, not a real DeepSeek scan
      </div>}
      <section className="risk-modal-hero">
        <span className="risk-modal-symbol"><Icon size={40} className={working ? "spinning" : ""}/></span>
        <div className="risk-modal-hero-copy">
          <div className="risk-modal-level">RISK LEVEL · <strong>{label}</strong></div>
          <h2 id="risk-modal-title">{title}</h2>
          <p id="risk-modal-description">{description}</p>
        </div>
      </section>
      <div className="risk-modal-body">
        {working && <div className="risk-modal-loading-note" role="status">
          <span className="risk-modal-progress-bar"/>
          <span>Analyzing code changes with DeepSeek · Dashboard will update automatically.</span>
        </div>}
        <section className="risk-modal-summary">
          <div className="risk-modal-section-heading"><Sparkles size={18}/> AI ANALYSIS SUMMARY</div>
          <p>{summary}</p>
        </section>
        {!sample && !working && !failed && <section className="risk-modal-ai-proof" aria-label="AI verdict provenance">
          <div className="risk-modal-section-heading"><Sparkles size={18}/> MODEL VERDICT & COVERAGE</div>
          {hasDeepSeekResult ? <>
            <div className="risk-modal-ai-proof-row">
              <span>Provider <strong>DeepSeek</strong></span>
              <span>Model <strong>{provenance?.model || "unspecified"}</strong></span>
              <span>DeepSeek risk <strong>{modelVerdict || "UNKNOWN"}</strong></span>
              <span>Final risk <strong>{review?.risk_level || "UNKNOWN"}</strong></span>
              <span>PR diff <strong>{review?.review_coverage?.diff_complete ? "complete" : "partial / unconfirmed"}</strong></span>
            </div>
            {adjusted && <p className="risk-modal-ai-adjustment">The backend adjusted the model verdict after checking critical-path and coverage signals.</p>}
            {adjustmentReasons.map((reason, index) => <p className="risk-modal-ai-adjustment" key={index}>{reason}</p>)}
          </> : <p className="risk-modal-ai-adjustment">
            This review predates DeepSeek provenance tracking. Click Analyze PR again to see
            the actual model verdict and any backend adjustments.
          </p>}
          <small>Change risk and test verification are separate; a LOW-risk verdict does not mean tests passed.</small>
        </section>}
        <div className="risk-modal-grid">
          <section className="risk-modal-info">
            <div className="risk-modal-section-heading"><FileCode2 size={17}/> POSSIBLY AFFECTED FILES</div>
            {affected.length ? <ul>{affected.map(path => <li key={path}><code>{path}</code></li>)}</ul>
              : <p>{working ? "Identifying changed and dependent files..." : "No affected core files identified in the available sample."}</p>}
          </section>
          <section className="risk-modal-info">
            <div className="risk-modal-section-heading"><AlertTriangle size={17}/> RECOMMENDATIONS</div>
            {recommendations.length ? <ul>{recommendations.map((tip, index) => <li key={index}>{tip}</li>)}</ul>
              : <p>{low ? "Continue with normal CI, code review and regression tests." :
                  working ? "Recommendations will appear after analysis." :
                  "Review the diff and run the relevant test suite before merging."}</p>}
          </section>
        </div>
        <section className="risk-modal-verification">
          <span>{review?.files_changed ?? "—"} changed files</span>
          <span>{review?.verification?.python_files_checked ?? 0} Python files syntax checked</span>
          <span>{review?.verification?.syntax_errors ?? 0} syntax errors</span>
          <span>Runtime tests: not executed</span>
        </section>
        {review?.diff_path && <div className="risk-modal-diff"><span>DIFF PREVIEW · {review.diff_path}</span>
          <pre>{review.diff.slice(0, 8).map(line => `${line.kind === "add" ? "+" : line.kind === "remove" ? "-" : " "}${line.code}`).join("\n")}</pre>
        </div>}
      </div>
      <footer className="risk-modal-footer">
        <small>{sample ? "Sample only. Run Analyze PR to see a real risk assessment." :
          "AI findings are advisory; repository maintainers make the final merge decision."}</small>
        <div className="risk-modal-actions">
          {prUrl && <a href={prUrl} target="_blank" rel="noreferrer" className="risk-modal-secondary">
            <ExternalLink size={16}/> Open GitHub PR</a>}
          {!sample && review && onViewDetails && <button className="risk-modal-secondary" onClick={onViewDetails}>
            Full report <ArrowRight size={16}/></button>}
          <button className="risk-modal-primary" onClick={onClose}>
            {working ? "Continue in Dashboard" : "Understood"} <CheckCircle2 size={17}/></button>
        </div>
      </footer>
    </div>
  </div>;
}
