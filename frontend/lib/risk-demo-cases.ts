import type { PullRequestReview } from "@/lib/types";

/** Fully synthetic presentation fixtures. Never saved as genuine backend reviews. */
export const RISK_DEMO_CASES: Record<"low" | "high", PullRequestReview> = {
  low: {
    id: "demo-low-risk", number: 2,
    title: "Demo LOW RISK: documentation-only formatter update",
    author: "Psy3che", branch: "demo/low-risk-documentation",
    updated_at: "2026-11-21T15:17:09Z",
    head_sha: "sample-not-analyzed",
    review_status: "COMPLETED",
    risk_level: "LOW", merge_decision: "PASS",
    summary: "Only a Python function docstring was changed. The function body, return value, permissions, and observable behavior remain unchanged in this example. No blocking findings are shown in the illustrated review scope.",
    files_changed: 1, additions: 3, deletions: 1,
    affected_module_ids: [], dependent_files: [],
    important_touched_files: [],
    verification: { python_files_checked: 1, python_files_passed: 1, syntax_errors: 0, tests_executed: false },
    findings: [],
    diff_path: "src/formatters.py",
    diff: [
      { kind: "remove", code: '    """Join a first and last name for display without changing either value."""', line: 5 },
      { kind: "add", code: '    """Return a display-friendly full name.', line: 5 },
      { kind: "add", code: "    This documentation-only update does not change runtime behavior.", line: 7 },
    ],
  },
  high: {
    id: "demo-high-risk", number: 1,
    title: "Test: Detect risky authorization change",
    author: "Psy3che", branch: "test/authorization-risk",
    updated_at: "2026-11-21T14:25:12Z",
    head_sha: "sample-not-analyzed",
    review_status: "COMPLETED",
    risk_level: "HIGH", merge_decision: "REVIEW_REQUIRED",
    summary: "The deletion permission check is broadened from administrators only to administrators or viewers. This is a potentially serious authorization regression: a read-only account may gain the ability to delete records.",
    files_changed: 1, additions: 1, deletions: 1,
    affected_module_ids: [], dependent_files: ["Callers that rely on can_delete_record"],
    important_touched_files: ["src/auth.py"],
    verification: { python_files_checked: 1, python_files_passed: 1, syntax_errors: 0, tests_executed: false },
    findings: [{
      id: "demo-permission-change", file: "src/auth.py", line: 6,
      severity: "HIGH", status: "SUSPECTED",
      title: "Deletion authorization expanded to viewer role",
      explanation: "A user with the viewer role would now pass the deletion authorization function. This may expose destructive operations to read-only users.",
      recommendation: "Keep deletion restricted to admin, and add tests for admin, viewer, and anonymous roles.",
    }],
    diff_path: "src/auth.py",
    diff: [
      { kind: "remove", code: '    return user.get("role") == "admin"', line: 6 },
      { kind: "add", code: '    return user.get("role") in {"admin", "viewer"}', line: 6 },
    ],
  },
};
