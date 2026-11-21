# RepoGuard AI — 后端 MVP

这是一个可以本地运行的 GitHub App 后端，包含：GitHub Webhook 验签、安装令牌认证、PR 文件拉取、仓库重要模块扫描、DeepSeek 风险推理、SQLite 保存、GitHub Checks 回写，以及前端需要的报告 API。

> **MVP 边界**：尚未执行真实测试、没有全量调用图、代码语义只覆盖抽样上下文。不保证找出所有错误，也不会自动合并或拒绝 PR。仅用于演示和继续开发。

## 1. 启动

建议 Python 3.11+。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

编辑 `.env`，填好以下变量：

- `GITHUB_APP_ID`：已注册的 GitHub App App ID（**不是 Client ID**）
- `GITHUB_PRIVATE_KEY_PATH`：在 GitHub App 的 General -> Private keys 下载的 `.pem` 的**绝对路径**，建议放在仓库之外
- `GITHUB_WEBHOOK_SECRET`：GitHub App -> General -> Webhook secret
- `DEEPSEEK_API_KEY`：DeepSeek API 密钥；默认模型 `deepseek-flash`
- `DASHBOARD_TOKEN`：自己生成的较长随机 token，用于前端服务端调用；不要使用 `NEXT_PUBLIC_` 前缀或放进浏览器

**切勿**提交 `.env`、`.pem`、任何 API Key 或数据库到 Git。

```bash
uvicorn backend.main:app --reload --port 8000
```

本地健康检查：

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","app":"RepoGuard AI","version":"0.1.0"}
```

另开终端，模拟有签名的 Webhook ping：

```bash
python examples/send_ping.py
# 202 {"status":"pong"}
```

## 2. 配置 GitHub App

在 GitHub App 的 **Permissions & events** 中设置：

| Repository permissions | 权限 |
|---|---|
| Contents | Read-only |
| Pull requests | Read-only |
| Checks | Read and write |
| Metadata | Read-only（默认） |

勾选 `Pull request` 事件，保存。`General -> Webhook` 设定 Secret 并启用 Active。

本地开发时将 http://localhost:8000 暴露为临时 HTTPS 地址，例如：

```bash
cloudflared tunnel --url http://localhost:8000
```

得到 `https://你的随机域名.trycloudflare.com` 后，将 GitHub App Webhook URL 改为 `https://你的随机域名.trycloudflare.com/webhook`。

接着到 **Install App**，安装到测试仓库（推荐一个专用 `RepoGuard-Demo` 仓库）。创建或更新 PR 即可触发扫描。

接收并处理的事件：`pull_request` 的 `opened`, `reopened`, `synchronize`, `ready_for_review`。第一次 PR 会为**目标分支的 base SHA**生成仓库地图，后续相同 base SHA 会使用缓存。

## 3. 给前端的 API 协议

所有 `/api/*` 接口必须提供 `Authorization: Bearer DASHBOARD_TOKEN`，不要让访问密钥出现在浏览器 bundle 中；请使用 Next.js Server Route 代理 API。

### GET /health
无需鉴权。

### GET /api/reviews?repo=owner/repo&limit=30
按创建时间倒序返回报告列表。

```json
{
  "items": [
    {
      "id": "uuid",
      "repo": "owner/repo",
      "pr_number": 2,
      "head_sha": "commit_sha",
      "status": "COMPLETED",
      "report": {
        "risk_level": "HIGH",
        "merge_recommendation": "REVIEW_REQUIRED",
        "summary": "Potential breaking change",
        "critical_modules": [],
        "affected_files": [],
        "changed_files": [],
        "dependency_edges": [],
        "findings": [],
        "recommendations": [],
        "coverage": {"complete": false, "diff_complete": true, "semantic_coverage": "SAMPLED", "code_tested": false},
        "tests": {"status": "NOT_RUN"}
      }
    }
  ]
}
```

### GET /api/reviews/{review_id}
获取报告详情（`status` 为 `PENDING`, `RUNNING`, `COMPLETED`, `FAILED` 之一）。

### GET /api/repositories/{owner}/{repo}/map
返回最近一次仓库扫描结果，其中 `critical_modules[]` 供核心文件 UI 使用，`dependency_edges[]` 供 React Flow 使用。

前端在没有真实 PR 时可直接加载 `examples/mock_review.json`。这份文件是**演示数据**，不是真实 DeepSeek 结果。

例如：

```bash
curl -H 'Authorization: Bearer 你的DASHBOARD_TOKEN' \
  'http://127.0.0.1:8000/api/reviews'
```

## 4. 按钮手动分析仓库（无需 PR）

本地联调时，Next.js 需要在 `frontend/.env.local` 设置与后端一致的
`REPOGUARD_DASHBOARD_TOKEN` 和 `REPOGUARD_API_BASE_URL`，然后重启两个服务。

1. 在 Dashboard 左侧选择 **GitHub App 已安装**的仓库。
2. 点击 **Analyze Repository**（已有结果则为 **Rescan Repository**）。
3. 后端校验该仓库的 GitHub App 安装状态，定位默认分支最新 commit SHA。
4. 后台使用现有 `build_repo_map()` 分析路径和抽样源代码，并请求 DeepSeek 生成架构摘要与关键模块。
5. 页面每 2.5 秒查询一次状态；成功后自动刷新 Architecture Map。

也可以测试 API（必须使用安全的 Bearer Token）：

```bash
curl -X POST -H "Authorization: Bearer YOUR_DASHBOARD_TOKEN" \
  http://127.0.0.1:8000/api/repositories/Psy3che/RepoGuard-Demo/scan

curl -H "Authorization: Bearer YOUR_DASHBOARD_TOKEN" \
  http://127.0.0.1:8000/api/repositories/Psy3che/RepoGuard-Demo/scan
```

异步状态为 `IDLE / PENDING / RUNNING / COMPLETED / FAILED`。任务状态写入 SQLite，服务器重启会将未完成的任务标记为失败，支持重新运行；同一仓库同时只启动一个手动扫描。

**重要限制：** API 仍使用单一管理员 Token，没有面向多用户的 OAuth 授权控制，因此仅可在本地开发环境中使用。仓库分析只抽样部分代码及显式导入关系，不能代替全面静态分析、测试和安全审计。模型调用失败时任务状态为 FAILED，不展示假的 AI 结果。扫描需要有效的 DeepSeek API Key；当前 PR 分析功能保留。

## 5. 运行测试

```bash
pytest -q
```

测试使用模拟 Webhook/DeepSeek，不会调用真实 API，也不会产生 DeepSeek 费用。

## 6. 风险评估解释

- GitHub PR 只发送经筛选/脱敏、长度受限的 patch 摘要和仓库代码片段到 DeepSeek。
- 文件重要性规则是启发式，模型推荐的关键模块会标记 `AI_SUGGESTED`。
- AI 产生的发现始终标记 `SUSPECTED`，不会伪装成验证通过。
- Diff 缺失、文件数被截断、仓库树截断或模型分析失败，均不能输出无依据的绿色通过结论。
- GitHub Check：风险 `LOW` 且 PR Diff 完整时可 `success`，中高风险的未证实判断以及 `UNKNOWN` 用 `neutral`；后续若真有验证证据才可 `action_required`。
- 即使返回 `LOW`，也**不代表代码已正确、经过测试或绝对安全**。
- 本 MVP **不执行第三方 PR 的代码**，防止将未知代码运行在有 GitHub 私钥和 API Key 的宿主进程里。
- 非所有语言的 import/依赖都支持深层解析；`dependency_edges` 只针对部分常见显式 imports，且源自**抽样文件**。
- FastAPI `BackgroundTasks` 仅适合演示，本地重启会丢失未完成任务。生产环境请换成独立任务队列并设置重试/死信机制。
- 正式用于私有仓库前，需要进一步完善敏感信息检测、组织策略、数据保留和用户授权；正则脱敏无法确保没有任何秘密信息流入第三方模型。

## 7. 代码结构

```text
backend/
  config.py      # 配置
  security.py    # webhook HMAC + 代码过滤脱敏
  github_api.py  # GitHub App JWT/安装令牌/Checks
  storage.py     # SQLite 持久化
  analyzer.py    # 仓库理解/DeepSeek 风险分析
  service.py     # PR 分析任务编排
  main.py        # FastAPI / Webhook / 报告 API
tests/
examples/
```

## 8. 官方接口参考

- DeepSeek API: https://api-docs.deepseek.com/en/
- DeepSeek JSON Output: https://api-docs.deepseek.com/guides/json_mode/
- GitHub App 安装认证: https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation
- GitHub PR 文件接口: https://docs.github.com/en/rest/pulls/pulls
- GitHub Checks API: https://docs.github.com/en/rest/checks/runs
- Webhook 签名: https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries
