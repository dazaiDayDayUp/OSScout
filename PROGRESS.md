# 项目开发进度记录

> 这份文档是新会话的快速回归入口，记录"做到哪 / 决策是什么 / 下一步动作"。
> 项目完整规划见 `PROJECT_PLAN.md`，协作规范见 `CLAUDE.md`。

---

## 当前状态：Phase 1.1 完成，即将进入 Phase 1.2

**最近更新**：2026-05-16

---

## Phase 0：基础设施（已完成 ✅）

### 已完成文件清单

| 文件路径 | 说明 |
|---------|------|
| `backend/requirements.txt` | Python 依赖清单（Phase 1+ 依赖已注释） |
| `backend/app/config.py` | Pydantic Settings 配置管理 |
| `backend/app/main.py` | FastAPI 入口 + 健康检查 + 日志 + 异常处理 + 路由注册 |
| `backend/app/core/models.py` | 4 张数据库表模型（Repository / AnalysisTask / DueDiligenceReport / MetricHistory） |
| `backend/app/core/database.py` | 异步数据库引擎 + 会话管理 |
| `backend/app/core/cache.py` | Redis 缓存封装（get/set/delete + 默认 24h TTL） |
| `backend/app/core/logger.py` | structlog 结构化日志配置 |
| `backend/app/services/github_service.py` | GitHub API 封装（缓存 + 并发控制） |
| `backend/app/api/v1/debug.py` | **临时调试接口**（Phase 0 验证用，Phase 1 进入正式开发后可考虑移除） |
| `backend/Dockerfile` | 后端容器镜像构建 |
| `backend/alembic.ini` | Alembic 迁移配置 |
| `backend/alembic/env.py` | 迁移环境脚本（异步支持） |
| `backend/alembic/versions/001_init.py` | 初始迁移脚本 |
| `docker-compose.dev.yml` | 开发环境编排（api/web/db/redis/worker） |
| `.env.example` / `.env` | 环境变量模板和本地配置 |
| `.gitignore` | Git 忽略规则（已排除 `PROJECT_PLAN.md`、`CLAUDE.md`、`.env`、venv） |
| `README.md` | 项目说明 |

### 端到端验证记录

通过 `backend/app/api/v1/debug.py` 提供的三个调试端点，在 FastAPI Swagger UI（`/docs`）中实际调用并验证：

| 验证项 | 数据 | 结论 |
|--------|------|------|
| `/all` 冷启动耗时 | ~3000ms | 6 个 GitHub API 并发调用正常（串行会 >6 秒） |
| `/all` 热请求耗时 | ~70ms | Redis 缓存命中，差距 40 倍+ |
| 单接口冷/热对比 | 显著差距 | 缓存层全链路打通 |

**已知问题与解决**：
- ~~GitHub `/stats/commit_activity` 首次请求可能返回 HTTP 202 + 空数组~~ → **已修复**：改用 `/stats/participation` 端点获取提交活动数据，避免后台异步计算导致的空数据问题。`participation` 端点直接返回即时计算结果（含 52 周每周提交总数），与 `commit_activity` 的 `total` 字段等效。
- Swagger UI 渲染大 JSON 会卡死浏览器，`/all` 接口已改为返回摘要而非完整数据。

### 启动命令

```bash
docker-compose -f docker-compose.dev.yml up -d
# 健康检查
curl http://localhost:8000/health
# 文档
open http://localhost:8000/docs
```

---

## Phase 1：MVP — 单项目 CLI 分析

### Phase 1.1：社区健康 Agent + 端到端打通（已完成 ✅）

**决策回顾**：起步策略为"混合方案"——先用已有 `github_service` 直接调用跑通端到端，后续再抽 MCP。

#### 已完成的 5 个文件

| 文件 | 职责 | 行数 |
|------|------|------|
| `backend/app/scoring/community.py` | 社区健康度五项指标评分规则 | 228 |
| `backend/app/agents/community_agent.py` | Agent 主体：采集 → 评分 → 结构化输出 | 123 |
| `backend/app/agents/orchestrator.py` | 串行协调器（调度 community_agent） | 68 |
| `backend/app/agents/reporter.py` | 文本报告格式化（Markdown 风格） | 112 |
| `backend/app/cli.py` | CLI 入口：`python -m app.cli analyze <url>` | 56 |

#### 执行链路（6 层）

```
repo_url 字符串
    ↓ cli.py 解析参数
    ↓ orchestrator.py 调度
    ↓ community_agent.py 解析 URL + 采集数据
    ↓ github_service.py 并发调用 6 个 GitHub API
    ↓ scoring/community.py 计算 5 项指标
    ↓ reporter.py 格式化为文本
    ↓ cli.py print 输出
```

#### 端到端验证结果（python-poetry/poetry）

```bash
$ python -m app.cli analyze https://github.com/python-poetry/poetry
总分 18/30 [############--------] 60.0%
```

| 指标 | 得分 | 原始值 | 说明 |
|------|------|--------|------|
| Bus Factor | 0/10 | 2 | 仅 2 人覆盖 50% 贡献，高风险 |
| Issue 响应速度 | 8/8 | 0.6 天 | 处理极快 |
| PR 合并率 | 4/6 | 66.0% | 良好 |
| 活跃贡献者 | 4/4 | 100 人 | 社区生态健康 |
| Release 稳定性 | 2/2 | 0.2 个月前 | 维护活跃 |

**结论**：链路完整跑通，评分逻辑与 PROJECT_PLAN §7.3 一致。

#### Phase 1.1 剩余问题

- Windows 控制台 GBK 编码导致中文输出乱码（代码本身无问题，终端编码设置问题）
- Reporter 进度条字符已改用 `#` `-` 兼容 GBK

### Phase 1.2：抽出 github-mcp server（待开始）

- [ ] 引入 `mcp` Python SDK 依赖
- [ ] `mcp-servers/github-mcp/server.py` — 独立的 MCP server 进程
- [ ] `backend/app/mcp/client.py` — MCP Client 封装
- [ ] 改造 `community_agent` 通过 MCP 调用而非直接调 service

### Phase 1.3：代码质量 Agent（待开始）

- [ ] `filesystem-mcp` server（仓库克隆 + 文件操作）
- [ ] `code-analysis-mcp` server（Semgrep + radon）
- [ ] `backend/app/scoring/quality.py` + `quality_agent.py`

### Phase 1.4：安全分析 Agent（待开始）

- [ ] `osv-mcp` server（漏洞库查询）
- [ ] `backend/app/scoring/security.py` + `security_agent.py`
- [ ] 许可证风险检查

### Phase 1.5：Orchestrator 升级 + 报告完善（待开始）

- [ ] Orchestrator 升级为并发版本（`asyncio.gather` 三个 Agent）
- [ ] 加入综合评级（A+/A/B+/B/C/D）
- [ ] 5 个热门项目的基准测试（next.js / poetry / fastapi / react / vue）

---

## 下一个具体动作

**Phase 1.2：把 GitHub 数据采集抽成独立的 `github-mcp` server**

需要向用户解释 MCP 是什么、为什么需要它、在本项目中的作用，再开始写代码。

---

## Phase 2 及之后（概述）

详见 `PROJECT_PLAN.md` §10，简要：

| 阶段 | 目标 | 状态 |
|------|------|------|
| Phase 2 | Web 平台 + Celery 异步任务 + React 前端 | 待开始 |
| Phase 3 | Agent 接入 LLM 推理 + ChromaDB RAG 校准 | 待开始 |
| Phase 4 | 持续监控 + 指标趋势 + 异常预警 | 待开始 |
| Phase 5 | Railway/Render 部署 + 公开站点 | 待开始 |
