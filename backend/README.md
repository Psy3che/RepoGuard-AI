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

## 5. Pull Request 合并风险评估（自动 + 手动）

**自动触发：** GitHub App 勾选 `Pull requests` Webhook 事件并配置可访问
`/webhook` 的 HTTPS URL。用户创建 PR、重新打开 PR、将 Draft 转为 Ready
或继续向已有 PR 分支 push 提交（`synchronize`）时，RepoGuard 会重新评估
PR 的代码 diff，生成 GitHub Check `RepoGuard AI / Risk Scan`。**单纯向无 PR 的分支
push 不会自动触发此版本的 PR 合并评估**，需先创建 PR。

**手动回退演示（无需 Webhook Tunnel）：** Dashboard → `Pull requests` → 选择
GitHub App 已安装的仓库 → 在 Open GitHub Pull Requests 中点 `Analyze PR`。
同一条 FastAPI + DeepSeek 分析流水线会运行并回写 GitHub Check。
前端每隔数秒读取最新结果，并为新完成的 PR 提示合并风险。

后端 API（均需 `Authorization: Bearer DASHBOARD_TOKEN`）：
- `GET /api/repositories/{owner}/{repo}/pulls`：列出前 30 条开放 PR
- `POST /api/repositories/{owner}/{repo}/pulls/{number}/analyze`：手动提交 PR 检查任务
- `GET /api/dashboard?repository=owner/repo`：查看风险等级、候选影响范围、验证结果

GitHub Check / Dashboard 风险提示：
- **LOW + 已获取完整 PR diff**：未发现已检查范围内的阻断项；显示绿色通过，但不等于无风险或代码测试通过
- **MEDIUM / HIGH / CRITICAL 的纯 AI 推断**：风险警告，需人工复核；不伪装成已验证错误，也不自动拒绝合并
- **确定性 Python 语法错误**：`VERIFIED`、附具体文件/行号的 GitHub annotation，并提示先修复再合并
- **UNKNOWN / diff 不完整 / DeepSeek 失败**：不给绿色通过结论；提示未验证/需重新分析

重要限制：不执行陌生 PR 的代码，不验证业务逻辑正确性；仅对本次改动的少量 Python
文件进行语法解析，对其他语言和语义影响主要为抽样 AI 判断。风险依赖图是有限的显式 import
抽样；建议人工核对、运行 CI 和功能测试，并由维护者做最终合并决定。GitHub Check
只有在 GitHub 仓库设置为 required status check 后才能参与合并门禁，RepoGuard
本身**不会自动合并或拒绝合并 PR**。不使用 GitHub Issues Write 权限，所以目前的
风险“标签”以 Check 名称/状态和 Dashboard 徽章呈现，而不是自动写入 GitHub Label。

## 6. 屏幕中央的 PR 风险弹窗（黑客松演示）

最新 Dashboard 在检测到选定仓库中有**新的 PR 审查任务**后，会自动在屏幕
正中央显示一个较大的风险弹窗（约 940px 宽）。GitHub `pull_request.opened` 或
`synchronize` Webhook 必须能够投递到正在运行的 FastAPI，才能在创建/更新 PR
时真正自动触发。DeepSeek 是异步的，**提交 PR 的瞬间不能保证得出风险等级**，
所以先显示 `ANALYSIS RUNNING`，完成后刷新为对应的风险结论。

浏览器无法通过 GitHub App 向 GitHub.com 网页直接插入弹窗：该弹窗仅显示在
**保持打开并选中该仓库的 RepoGuard Dashboard**。GitHub PR 页面会显示
RepoGuard AI / Risk Scan 的 Checks 状态。Dashboard 通过约 3.5 秒一次的轮询
获取更新，属于接近实时的提示而不是 WebSocket 推送。

**两条真实 GitHub PR 样例：**
- 低风险候选：`Psy3che/RepoGuard-Demo#2`，只调整 `src/formatters.py` 的
  docstring，功能逻辑不变；模型实际等级仍以运行结果为准。
- 高风险候选：`Psy3che/RepoGuard-Demo#1`，将删除权限从 admin 扩大至
  admin + viewer，模型应识别潜在权限退化；必须人工验证。

**弹窗演示预览：** Dashboard → 选择 `Psy3che/RepoGuard-Demo` →
`Pull requests` → `Preview Low Risk` 或 `Preview High Risk`。预览有
`DEMO PREVIEW` 标记，采用固定的**模拟报告**，**不是实际 DeepSeek 的分析结论**。

**真实测试：** 保持 Dashboard 和后端运行，在 GitHub 对打开的 PR 分支继续提交
代码；如果 Webhook 已经配置和启用，Dashboard 识别到新审查就会弹窗。
如果 Webhook 尚未就绪，点击 PR 行的 `Analyze PR` 手动排队亦会马上显示分析中，
再自动更新成真实报告。弹窗里的低风险结论只能说明“已检查范围内未发现阻断项”，
不能保证代码正确性或批准合并。

## 7. 运行测试

```bash
pytest -q
```

测试使用模拟 Webhook/DeepSeek，不会调用真实 API，也不会产生 DeepSeek 费用。

## 8. 风险评估解释

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

## 9. 代码结构

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

## 10. 官方接口参考

- DeepSeek API: https://api-docs.deepseek.com/en/
- DeepSeek JSON Output: https://api-docs.deepseek.com/guides/json_mode/
- GitHub App 安装认证: https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation
- GitHub PR 文件接口: https://docs.github.com/en/rest/pulls/pulls
- GitHub Checks API: https://docs.github.com/en/rest/checks/runs
- Webhook 签名: https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries
