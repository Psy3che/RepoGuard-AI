import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const data = JSON.parse(readFileSync(resolve(root, "examples/dashboard-response.json"), "utf8"));
const assert = (condition, message) => { if (!condition) throw new Error(message); };
const levels = new Set(["LOW", "MEDIUM", "HIGH", "CRITICAL", "UNKNOWN"]);
assert(data.repository && typeof data.repository.name === "string", "Missing repository");
assert(Array.isArray(data.modules) && Array.isArray(data.dependencies) && Array.isArray(data.reviews), "Missing arrays");
const ids = new Set(data.modules.map((m) => m.id));
assert(ids.size === data.modules.length, "Duplicate module IDs");
for (const module of data.modules) {
  assert(levels.has(module.importance), `Bad importance: ${module.id}`);
  assert(Number.isFinite(module.position?.x) && Number.isFinite(module.position?.y), `Bad position: ${module.id}`);
}
for (const link of data.dependencies) {
  assert(ids.has(link.source) && ids.has(link.target), `Unknown dependency: ${link.source} -> ${link.target}`);
}
for (const review of data.reviews) {
  assert(levels.has(review.risk_level), `Unknown risk on PR ${review.number}`);
  assert(["PASS","REVIEW_REQUIRED","BLOCK","UNKNOWN"].includes(review.merge_decision), `Unknown decision on PR ${review.number}`);
  for (const id of review.affected_module_ids) assert(ids.has(id), `PR ${review.number}: unknown module ${id}`);
  for (const finding of review.findings) {
    assert(levels.has(finding.severity), `PR ${review.number}: unknown finding severity`);
    assert(["VERIFIED", "SUSPECTED"].includes(finding.status), `PR ${review.number}: bad finding status`);
  }
}
console.log(`Validated: ${data.modules.length} modules, ${data.dependencies.length} dependencies, ${data.reviews.length} PRs.`);

const repoList = JSON.parse(readFileSync(resolve(root, "examples/repositories-response.json"), "utf8"));
assert(repoList.source === "github-app", "Expected GitHub App repository list");
assert(Array.isArray(repoList.repositories), "Expected repository list");
for (const r of repoList.repositories) {
  assert(r.full_name === `${r.owner}/${r.name}`, `Invalid repository full_name: ${r.full_name}`);
  assert(typeof r.private === "boolean" && typeof r.html_url === "string", `Invalid repository metadata: ${r.full_name}`);
}
console.log(`Validated: ${repoList.repositories.length} repository selector examples.`);
