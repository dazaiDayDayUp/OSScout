# 项目开发进度记录

> 这份文档是新会话的快速回归入口，记录"做到哪 / 决策是什么 / 下一步动作"。
> 项目完整规划见 `PROJECT_PLAN.md`，协作规范见 `CLAUDE.md`。

---

## 当前状态：Phase 0 完成 + 已端到端验证，即将进入 Phase 1

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

**潜在小坑（已知，先记一笔不改）**：
- GitHub `/stats/commit_activity` 首次请求可能返回 HTTP 202 + 空数组（GitHub 后台异步生成统计），第二次再调才有数据。Phase 1 写 Agent 时如发现影响评分再加重试。
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

## Phase 1：MVP — 单项目 CLI 分析（待开始）

**目标**：CLI 跑通"输入 repo URL → 输出文本报告"端到端流程。

### 起步策略：先用 service 跑通，再回头抽 MCP（混合方案）

完整决策记录见对话上下文。简单说：

- ❌ **不**严格按 `PROJECT_PLAN.md` 第一项先做 `github-mcp`（先学协议成本高，第一份报告会推迟一周）
- ❌ **不**完全跳过 MCP（这是简历核心卖点之一，最后必须有）
- ✅ **先**用 Phase 0 已经写好的 `github_service` 直接调用，把 4 个 Agent + Orchestrator + CLI 跑通，看到第一份报告
- ✅ **后**在 Phase 1.2 把 GitHub 数据采集抽成独立的 `github-mcp` server，Agent 改用 MCP 客户端调用

### Phase 1 任务拆解（按子阶段执行）

#### Phase 1.1：社区健康度 Agent + 端到端打通（下一步）

- [ ] `backend/app/scoring/community.py` — 社区健康度评分规则（PROJECT_PLAN §7.3 五项指标：Bus Factor / Issue 响应 / PR 合并率 / 活跃贡献者 / Release 稳定性）
- [ ] `backend/app/agents/community_agent.py` — Agent 主体：采集数据 → 调评分 → 输出 finding
- [ ] `backend/app/agents/orchestrator.py` — 协调器：串行版本（先简单，Phase 1.4 升级并发）
- [ ] `backend/app/agents/reporter.py` — 文本报告格式化
- [ ] `backend/app/cli.py` — CLI 入口：`python -m app.cli analyze <repo_url>`

**验收**：`docker-compose -f docker-compose.dev.yml exec api python -m app.cli analyze https://github.com/python-poetry/poetry` 能输出含社区健康度评分的文本报告。

#### Phase 1.2：抽出 github-mcp server，Agent 改用 MCP 调用

- [ ] 引入 `mcp` Python SDK 依赖
- [ ] `mcp-servers/github-mcp/server.py` — 独立的 MCP server 进程
- [ ] `backend/app/mcp/client.py` — MCP Client 封装
- [ ] 改造 `community_agent` 通过 MCP 调用而非直接调 service

#### Phase 1.3：代码质量 Agent

- [ ] `filesystem-mcp` server（仓库克隆 + 文件操作）
- [ ] `code-analysis-mcp` server（Semgrep + radon）
- [ ] `backend/app/scoring/quality.py` + `quality_agent.py`

#### Phase 1.4：安全分析 Agent

- [ ] `osv-mcp` server（漏洞库查询）
- [ ] `backend/app/scoring/security.py` + `security_agent.py`
- [ ] 许可证风险检查

#### Phase 1.5：Orchestrator 升级 + 报告完善

- [ ] Orchestrator 升级为并发版本（`asyncio.gather` 三个 Agent）
- [ ] 加入综合评级（A+/A/B+/B/C/D）
- [ ] 5 个热门项目的基准测试（next.js / poetry / fastapi / react / vue）

---

## 下一个具体动作

**写 `backend/app/scoring/community.py`** —— PROJECT_PLAN §7.3 五项指标的纯规则评分函数。

为什么从这里起步：
1. 没有任何外部依赖（只接收已经采集好的 GitHub 数据字典）
2. 是 4 个 Agent 共用的模式样板，写好这个第二个、第三个就容易了
3. 一个文件完整闭环，符合"分步推进、紧凑汇报"原则

---

## Phase 2 及之后（概述）

详见 `PROJECT_PLAN.md` §10，简要：

| 阶段 | 目标 | 状态 |
|------|------|------|
| Phase 2 | Web 平台 + Celery 异步任务 + React 前端 | 待开始 |
| Phase 3 | Agent 接入 LLM 推理 + ChromaDB RAG 校准 | 待开始 |
| Phase 4 | 持续监控 + 指标趋势 + 异常预警 | 待开始 |
| Phase 5 | Railway/Render 部署 + 公开站点 | 待开始 |
