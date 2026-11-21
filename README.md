RepoGuard AI

An AI pre-reviewer for GitHub pull requests that catches secrets, missing tests and unclear changes before a human reviewer has to.

Track: Open Innovation and Developer Productivity
For: student teams, open-source maintainers and small dev teams where reviewer time is scarce
What it does

When a pull request is opened, RepoGuard AI (installed as a GitHub App) receives the webhook, reads the changed files plus a few related source files for context, and asks an LLM to produce a structured review:

a risk level (low / medium / high)
comments with file, line, severity (must fix / suggestion / nit) and category (testing, security, bug risk, naming, description)
a "what a human should look at" list, so reviewers spend their time on design and logic, not trivia

Reports are stored locally and shown in a token-protected dashboard.

How it works
GitHub PR event --> Webhook (signature verified) --> Fetch diff + context files
      --> LLM review agent (DeepSeek) --> Validated JSON report --> SQLite --> Dashboard

Budget limits keep each request cheap and predictable: MAX_PR_FILES and MAX_REPO_SOURCE_FILES.

Setup

TODO (team): replace the commands below with your real ones.

bash
git clone <your-repo-url>
cd RepoGuard-AI
cp .env.example .env        # fill in the values below
<install dependencies>
<start the server>          # serves on http://localhost:8000
Environment variables
Variable	Where to get it
GITHUB_APP_ID	GitHub App -> General -> App ID
GITHUB_PRIVATE_KEY_PATH	Path to the downloaded .pem file (keep it outside the repo)
GITHUB_WEBHOOK_SECRET	GitHub App -> General -> Webhook secret
DEEPSEEK_API_KEY	DeepSeek Platform -> API Keys
DEEPSEEK_MODEL	Model name from the DeepSeek docs
DASHBOARD_TOKEN	Any long random string; protects private repo reports
DATABASE_PATH	Default ./repoguard.db
ALLOWED_ORIGINS	Default http://localhost:8000
MAX_PR_FILES / MAX_REPO_SOURCE_FILES	Per-request budget limits

Never commit .env or any .pem file.

Tools, APIs and AI assistants used
GitHub Apps API + webhooks to receive PR events and read PR files
DeepSeek API as the review model at runtime
SQLite for report storage
Claude (Anthropic) as an AI assistant for brainstorming, prompt and schema design, starter code and the pitch material
<list any other frameworks, templates or assistants your team used>
Limitations and next steps
LLM reviews can produce false positives, so RepoGuard AI assists reviewers and does not approve or reject PRs
Next: post inline review comments on the PR, a "mark as unhelpful" feedback loop, and flaky-test triage
