// Frontend teammate: import these types into Next.js.
// Call /api/* from a Next.js server-side route with DASHBOARD_TOKEN.
// Never expose DASHBOARD_TOKEN through NEXT_PUBLIC_ variables or browser requests.
export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | 'UNKNOWN';
export type ReviewStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';
export type MergeRecommendation = 'NO_BLOCKING_FINDINGS' | 'REVIEW_SUGGESTED' | 'REVIEW_REQUIRED' | 'UNDETERMINED';

export interface CriticalModule {
  file: string;
  importance: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  reason: string;
  origin?: 'HEURISTIC' | 'AI_SUGGESTED';
}
export interface DependencyEdge {
  source: string;
  target: string;
  kind: 'import';
}
export interface RiskFinding {
  file: string;
  severity: RiskLevel;
  status: 'SUSPECTED' | 'VERIFIED';
  reason: string;
  recommendation: string;
}
export interface RiskReport {
  repository: string;
  review_id?: string;
  pr_number: number;
  head_sha: string;
  risk_level: RiskLevel;
  merge_recommendation: MergeRecommendation;
  summary: string;
  critical_modules: CriticalModule[];
  affected_files: string[];
  changed_files: string[];
  dependency_edges: DependencyEdge[];
  findings: RiskFinding[];
  recommendations: string[];
  coverage: {
    complete: false;
    diff_complete: boolean;
    repository_tree_complete?: boolean;
    semantic_coverage: 'SAMPLED';
    code_tested: false;
    files_received?: number;
    expected_files?: number | null;
    note?: string;
  };
  tests: { status: 'NOT_RUN' };
}
export interface ReviewRecord {
  id: string;
  repo: string;
  pr_number: number;
  head_sha: string;
  status: ReviewStatus;
  report: RiskReport | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}
export type ReviewsResponse = { items: ReviewRecord[] };
