export type RiskLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" | "UNKNOWN";
export type Importance = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type MergeDecision = "PASS" | "REVIEW_REQUIRED" | "BLOCK" | "UNKNOWN";
export type FindingStatus = "VERIFIED" | "SUSPECTED";
export type DiffLineKind = "add" | "remove" | "context";

export interface RepositorySummary {
  owner: string;
  name: string;
  default_branch: string;
  description: string;
  language: string;
  last_analyzed_at: string;
  tracked_files: number;
  analyzed_files: number;
  analysis_coverage: "PARTIAL" | "FULL" | "UNKNOWN";
  architecture_summary?: string;
  architecture_notes?: string[];
  ai_status?: string;
}

export interface RepoModule {
  id: string;
  name: string;
  path: string;
  category: string;
  importance: Importance;
  reason: string;
  protected: boolean;
  position: { x: number; y: number };
}

export interface Dependency {
  source: string;
  target: string;
  label?: string;
}

export interface Finding {
  id: string;
  file: string;
  line: number | null;
  severity: RiskLevel;
  status: FindingStatus;
  title: string;
  explanation: string;
  recommendation: string;
}

export interface DiffLine {
  kind: DiffLineKind;
  code: string;
  line: number | null;
}

export interface PullRequestReview {
  id: string;
  number: number;
  title: string;
  author: string;
  branch: string;
  updated_at: string;
  risk_level: RiskLevel;
  merge_decision: MergeDecision;
  summary: string;
  files_changed: number;
  additions: number;
  deletions: number;
  affected_module_ids: string[];
  findings: Finding[];
  diff_path: string;
  diff: DiffLine[];
}

export interface RepositoryOption {
  id: number;
  full_name: string;
  name: string;
  owner: string;
  private: boolean;
  description: string;
  default_branch: string;
  html_url: string;
}

export interface RepositoryListResponse {
  source: "demo" | "github-public" | "github-app";
  repositories: RepositoryOption[];
}

export interface DashboardPayload {
  mode: "demo" | "live" | "unscanned";
  repository: RepositorySummary;
  modules: RepoModule[];
  dependencies: Dependency[];
  reviews: PullRequestReview[];
}
