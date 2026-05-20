# osscout -- 开源项目深度尽调 Agent

> 面向技术团队的开源项目自动化尽调平台

## 项目简介

输入一个 GitHub 仓库地址，输出一份覆盖社区健康、代码质量、安全风险、技术演进四个维度的结构化尽调报告，并给出明确的推荐评级。

**核心差异化**：规则评分打底 + LLM 推理增强 + RAG 知识库校准 + 综合报告生成。

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

### Phase 3（V2 -- Agent 智能化 + RAG）已完成

**Phase 3.1**：LLM Client 封装
- **Kimi Provider**（Moonshot AI）：`kimi-k2.6` 思考模型，兼容 OpenAI API 格式
- **DeepSeek Provider**：`deepseek-v4-pro`，兼容 OpenAI API 格式
- **统一抽象接口**：`chat()` 通用对话 + `chat_structured()` 结构化 JSON 输出
- **配置化切换**：通过 `DEFAULT_LLM_PROVIDER=kimi|deepseek` 切换

**Phase 3.2**：ChromaDB 向量库 + 知识库文档入库
- 本地 Embedding 模型（`all-MiniLM-L6-v2`，384 维）
- 9 篇知识库文档：4 个失败案例 + 2 个方法论 + 3 个竞品映射
- 语义检索："Bus Factor 低的风险" → 返回 left-pad 等案例

**Phase 3.3**：4 个分析 Agent 接入 LLM 推理
- 规则评分打底（不变），LLM 做补充分析
- 统一增加 `reasoning` 字段，解释评分依据
- LLM 发现规则无法捕捉的跨指标关联问题

**Phase 3.4**：Orchestrator ReAct Loop + RAG 校准 + 冲突消解
- 每个 Agent 分析完成后检索知识库进行基准对比
- 检测维度间矛盾（如"社区活跃但安全漏洞多"）
- ReAct Loop：Thought → Action → Observation → 综合判断

**Phase 3.5**：综合报告 Agent（SynthesisAgent）
- 接收 4 维度结果 + RAG 校准 + 冲突检测，生成结构化综合报告
- 输出：执行摘要 + 风险矩阵（high/medium/low）+ 明确建议 + 数据来源标注

**前端适配**：ReportPage 增加 reasoning 折叠面板、RAG 校准引用、冲突检测提示、综合报告区块

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
- **Orchestrator**：`asyncio.gather` 并行运行 4 个 Agent，错误隔离 + RAG 校准 + 冲突消解
- **LLM Provider**：Kimi (`kimi-k2.6`) + DeepSeek (`deepseek-v4-pro`) 双后端
- **RAG**：ChromaDB + sentence-transformers，9 篇知识库文档
- **前端 React**：Vite 6 + React 19 + TailwindCSS v4 + shadcn/ui + Recharts
- **完整链路**：浏览器提交 → API → Celery → 4 Agent 并行 + LLM 增强 + RAG 校准 → SynthesisAgent 综合报告 → PostgreSQL → 前端展示

## API 接口

```bash
# 提交分析任务（异步，后台 Celery 执行）
POST /api/v1/analyze -d '{"repo_url": "https://github.com/owner/repo"}'
→ {"task_id": 1, "status": "running"}

# 查询任务状态
GET /api/v1/tasks/1
→ {"task_id": 1, "status": "completed", "report_id": 2}

# 获取尽调报告（含 Phase 3 新增字段：reasoning / calibrations / synthesis）
GET /api/v1/reports/2
→ 完整报告 JSON（overall + 4 dimensions + findings + reasoning + calibrations + synthesis）

# 报告列表（分页）
GET /api/v1/reports?page=1&page_size=20

# 仓库历史趋势
GET /api/v1/repos/1/history

# 多仓库对比
POST /api/v1/compare -d '{"repo_urls": ["url1", "url2"]}'
```

## 快速开始

### 1. 启动开发环境（需要 4 个终端，可选第 5 个启动 Flower）

```bash
# 终端 1：数据库 + Redis（Docker）
docker-compose -f docker-compose.dev.yml up db redis

# 终端 2：后端 FastAPI
cd backend
./venv/Scripts/python.exe -m uvicorn app.main:app --reload

# 终端 3：Celery Worker（必须启动，否则任务永远卡在 running！）
cd backend
./venv/Scripts/python.exe -m celery -A app.core.celery_app worker --loglevel=info --pool=solo

# 终端 4：前端 React
cd frontend
npm run dev

# 终端 5（可选）：Flower 监控面板 — 实时查看任务队列和 Worker 状态
# 需要先确保 Redis 已启动，然后访问 http://localhost:5555
cd backend
./venv/Scripts/python.exe -m celery -A app.core.celery_app flower --port=5555
```

### 2. 运行 CLI 分析

```bash
cd backend
python -m app.cli analyze https://github.com/python-poetry/poetry
```

### 3. 数据库连接（DataGrip / DBeaver）

- PostgreSQL：`localhost:5432`，用户名 `osscout`，密码 `ossscout`
- Redis：`localhost:6379`

## 项目结构

```
osscout/
├── README.md
├── PROJECT_PLAN.md           # 完整项目规划
├── PROGRESS.md               # 开发进度记录（含已知问题）
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
│   │   │   ├── orchestrator.py      # 协调器（ReAct + RAG + 冲突消解）
│   │   │   ├── community_agent.py   # 社区健康（+ LLM 增强）
│   │   │   ├── quality_agent.py     # 代码质量（+ LLM 增强）
│   │   │   ├── security_agent.py    # 安全分析（+ LLM 增强）
│   │   │   ├── evolution_agent.py   # 技术演进（+ LLM 增强）
│   │   │   ├── synthesis_agent.py   # 综合报告 Agent
│   │   │   ├── llm_enhancer.py      # 通用 LLM 增强器
│   │   │   └── reporter.py          # 文本报告格式化
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
│   │   ├── llm/              # LLM Provider 封装
│   │   │   ├── base.py
│   │   │   ├── providers.py
│   │   │   ├── factory.py
│   │   │   ├── schemas.py
│   │   │   └── templates.py
│   │   ├── rag/              # RAG 模块（Phase 3.2）
│   │   │   ├── embeddings.py
│   │   │   ├── vector_store.py
│   │   │   └── query.py
│   │   └── tasks/            # Celery 异步任务
│   │       └── analysis_tasks.py
│   ├── tests/
│   └── alembic/              # 数据库迁移
│
├── frontend/                 # React 前端
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── components/       # 通用组件
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
├── knowledge-base/           # RAG 知识库文档（Phase 3.2）
│   ├── case-studies/         # 失败案例
│   ├── methodology/          # 评估方法论
│   └── competitors/          # 竞品映射
│
├── scripts/                  # 工具脚本
│   └── init_kb.py            # 知识库初始化
│
└── tmp/                      # 临时目录（gitignored）
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
| Phase 3.1 | LLM Client 封装（Kimi + DeepSeek） | 已完成 |
| Phase 3.2 | ChromaDB + 知识库文档入库 | 已完成 |
| Phase 3.3 | 4 个 Agent 接入 LLM 推理 | 已完成 |
| Phase 3.4 | Orchestrator ReAct Loop + RAG 校准 + 冲突消解 | 已完成 |
| Phase 3.5 | 综合报告 Agent | 已完成 |
| 前端适配 | ReportPage 展示 reasoning + RAG + 冲突 + 综合报告 | 已完成 |
| Phase 4 | 持续监控 + 预警 | 待开始 |

## 技术栈

- **后端**：Python 3.12 + FastAPI + SQLAlchemy(async)
- **数据库**：PostgreSQL 16 + Redis 7
- **任务队列**：Celery + Redis Broker
- **Agent 编排**：手写 ReAct Loop（不用 LangChain）
- **MCP 协议**：官方 Python SDK（`mcp`）
- **LLM**：Kimi (`kimi-k2.6`) + DeepSeek (`deepseek-v4-pro`)
- **RAG**：ChromaDB + sentence-transformers (`all-MiniLM-L6-v2`)
- **前端**：React 19 + TypeScript 5.8 + TailwindCSS v4 + shadcn/ui + Recharts
- **部署**：Docker Compose + Railway/Render

## 已知限制

| 限制 | 说明 |
|------|------|
| Kimi 并发限制（429） | 免费账户并发上限 3，Synthesis 可能触发 429 重试，延迟 10-60 秒，最终能成功 |
| 分析耗时约 2 分钟 | 完整链路仍有优化空间，Phase 4 计划引入缓存预热和进度反馈 |
| 超大仓库耗时较长 | facebook/react 等 monorepo 依赖查询串行，Phase 4 优化 |
| Windows 控制台乱码 | GBK 编码问题，不影响文件/API，建议用 DataGrip 查看数据库 |

---

*项目规划中，详见 PROJECT_PLAN.md。开发进度见 PROGRESS.md。*
