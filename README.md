# osscout -- 开源项目深度尽调 Agent

> 面向技术团队的开源项目自动化尽调平台

## 项目简介

输入一个 GitHub 仓库地址，输出一份覆盖社区健康、代码质量、安全风险、技术演进四个维度的结构化尽调报告，并给出明确的推荐评级。

## 当前进展

### Phase 0（基础设施）已完成

后端服务、数据库、缓存、Docker 开发环境均已跑通。

### Phase 1（MVP -- CLI 分析）已完成

四个分析 Agent（社区健康 / 代码质量 / 安全 / 技术演进）+ Orchestrator 并发调度 + CLI 文本报告输出，总分覆盖 100/100 分。

```bash
# 分析指定仓库，输出文本报告
python -m app.cli analyze https://github.com/python-poetry/poetry
```

### Phase 2（V1 -- Web 平台 + 多项目）已完成

**Phase 2.1-2.2 已完成**：REST API + Celery 异步任务队列。提交分析后后台执行，前端轮询状态。

**Phase 2.3 已完成**：多仓库对比分析 `/compare` + 历史趋势 `/history` + 报告列表分页。

**Phase 2.4-2.5 已完成**：React 前端 + 可视化。包含：
- 首页：提交分析表单 + 任务状态轮询
- 报告列表页：分页表格 + 迷你评分条
- 报告详情页：ScoreGauge 环形仪表盘 + DimensionBarChart 维度条形图 + 维度卡片
- 对比页：综合排名 + 堆叠对比图 + 关键差异高亮
- 全局去 AI 味配色（低饱和度专业风）

## 已验证的功能

- **FastAPI 后端**：`http://localhost:8000/health` + 自动 API 文档 `/docs`
- **PostgreSQL**：4 张核心表（Repository / AnalysisTask / DueDiligenceReport / MetricHistory）
- **Redis**：缓存 + Celery Broker
- **Celery Worker**：异步执行分析任务，solo pool（Windows 兼容）
- **MCP 协议链路**：4 个 Server 全部打通
  - github-mcp：GitHub 元数据查询
  - filesystem-mcp：仓库克隆 + 文件操作
  - code-analysis-mcp：radon 圈复杂度 + AST 安全扫描
  - osv-mcp：SBOM 依赖提取 + OSV 漏洞查询 + 许可证检查
- **Orchestrator**：`asyncio.gather` 并行运行 4 个 Agent，错误隔离
- **前端 React**：Vite 6 + React 19 + TailwindCSS v4 + shadcn/ui + Recharts
- **完整链路**：浏览器提交 → API → Celery → 4 Agent 并行 → PostgreSQL → 前端展示

## API 接口

```bash
# 提交分析任务（异步，后台 Celery 执行）
POST /api/v1/analyze -d '{"repo_url": "https://github.com/owner/repo"}'
→ {"task_id": 1, "status": "running"}

# 查询任务状态
GET /api/v1/tasks/1
→ {"task_id": 1, "status": "completed", "report_id": 2}

# 获取尽调报告
GET /api/v1/reports/2
→ 完整报告 JSON（overall + 4 dimensions + findings）

# 报告列表（分页）
GET /api/v1/reports?page=1&page_size=20

# 仓库历史趋势
GET /api/v1/repos/1/history

# 多仓库对比
POST /api/v1/compare -d '{"repo_urls": ["url1", "url2"]}'
```

## 快速开始

### 1. 启动开发环境

```bash
# 数据库 + Redis（Docker）
docker-compose -f docker-compose.dev.yml up db redis

# 后端 FastAPI
cd backend
./venv/Scripts/python.exe -m uvicorn app.main:app --reload

# Celery Worker
cd backend
./venv/Scripts/python.exe -m celery -A app.core.celery_app worker --loglevel=info --pool=solo

# 前端 React
cd frontend
npm run dev
```

### 2. 运行 CLI 分析

```bash
cd backend
python -m app.cli analyze https://github.com/python-poetry/poetry
```

### 3. 数据库连接（DataGrip / DBeaver）

- PostgreSQL：`localhost:5432`，用户名 `osscout`，密码 `osscout`
- Redis：`localhost:6379`

## 项目结构

```
osscout/
├── README.md
├── PROJECT_PLAN.md           # 完整项目规划
├── PROGRESS.md               # 开发进度记录
├── docker-compose.dev.yml    # 开发环境编排
│
├── backend/                  # FastAPI 后端
│   ├── app/
│   │   ├── main.py           # FastAPI 入口
│   │   ├── config.py         # 配置管理
│   │   ├── cli.py            # CLI 入口
│   │   ├── api/v1/           # REST 接口
│   │   │   ├── analyze.py    # 提交分析
│   │   │   ├── tasks.py      # 任务状态
│   │   │   ├── reports.py    # 报告详情/列表
│   │   │   ├── repos.py      # 历史趋势
│   │   │   ├── compare.py    # 多仓库对比
│   │   │   └── __init__.py   # 路由聚合
│   │   ├── core/             # 基础设施
│   │   │   ├── models.py     # 数据库模型
│   │   │   ├── database.py   # 异步数据库引擎
│   │   │   ├── cache.py      # Redis 缓存
│   │   │   ├── celery_app.py # Celery 配置
│   │   │   └── logger.py     # 结构化日志
│   │   ├── agents/           # Agent 层
│   │   │   ├── orchestrator.py
│   │   │   ├── community_agent.py
│   │   │   ├── quality_agent.py
│   │   │   ├── security_agent.py
│   │   │   ├── evolution_agent.py
│   │   │   └── reporter.py
│   │   ├── scoring/          # 评分体系
│   │   │   ├── community.py
│   │   │   ├── quality.py
│   │   │   ├── security.py
│   │   │   └── evolution.py
│   │   ├── services/         # 业务逻辑
│   │   │   ├── analysis_service.py
│   │   │   ├── github_service.py
│   │   │   ├── security_service.py
│   │   │   └── evolution_service.py
│   │   ├── mcp/              # MCP 客户端
│   │   │   └── client.py
│   │   ├── rag/              # RAG 模块（Phase 3）
│   │   └── tasks/            # Celery 异步任务
│   │       └── analysis_tasks.py
│   ├── tests/
│   └── alembic/              # 数据库迁移
│
├── frontend/                 # React 前端（Phase 2）
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── components/       # 通用组件（ScoreGauge / ScoreBadge / DimensionBarChart）
│       ├── pages/            # 页面（Home / ReportList / Report / Compare）
│       ├── api/              # HTTP 客户端 + Hooks
│       └── types/            # TypeScript 类型定义
│
├── mcp-servers/              # MCP Server 独立包
│   ├── github-mcp/
│   ├── filesystem-mcp/
│   ├── code-analysis-mcp/
│   └── osv-mcp/
│
├── tmp/                      # 临时目录（MCP Server 克隆的仓库，gitignored）
├── knowledge-base/           # RAG 知识库文档（Phase 3）
└── scripts/                  # 工具脚本
```

## 开发计划

| 阶段 | 目标 | 状态 |
|------|------|------|
| Phase 0 | 基础设施（脚手架、Docker、数据库、GitHub API） | 已完成 |
| Phase 1.1 | 社区健康 Agent + CLI 端到端打通 | 已完成 |
| Phase 1.2 | 抽出 github-mcp server | 已完成 |
| Phase 1.3 | 代码质量 Agent | 已完成 |
| Phase 1.4 | 安全分析 Agent（osv-mcp + 漏洞 + 许可证） | 已完成 |
| Phase 1.5 | 技术演进 Agent + Orchestrator 并发调度 | 已完成 |
| Phase 2.1 | REST API + 数据库持久化 | 已完成 |
| Phase 2.2 | Celery 异步任务队列 | 已完成 |
| Phase 2.3 | 多项目对比 + 历史趋势 | 已完成 |
| Phase 2.4-2.5 | React 前端 + 可视化 | 已完成 |
| Phase 3 | Agent 智能化 + RAG | 待开始 |
| Phase 4 | 持续监控 + 预警 | 待开始 |

## 技术栈

- **后端**：Python 3.12 + FastAPI + SQLAlchemy(async)
- **数据库**：PostgreSQL 16 + Redis 7
- **任务队列**：Celery + Redis Broker
- **Agent 编排**：手写 ReAct Loop（不用 LangChain）
- **MCP 协议**：官方 Python SDK（`mcp`）
- **LLM**：Claude / GPT（Phase 3 接入）
- **前端**：React 19 + TypeScript 5.8 + TailwindCSS v4 + shadcn/ui + Recharts
- **部署**：Docker Compose + Railway/Render

## 已知限制

| 限制 | 说明 | 计划解决 |
|------|------|----------|
| 超大仓库超时 | facebook/react 等 monorepo 分析需 3 分钟（git clone + npm 依赖查询串行） | Phase 3 |
| Windows 控制台乱码 | 中文输出在默认 GBK 编码控制台显示为乱码，不影响文件/API | 建议用 DataGrip 查看数据库 |
| 对比分析同步阻塞 | 对比接口同步等待所有 Celery 任务完成 | Phase 3 |

---

*项目规划中，详见 PROJECT_PLAN.md*
