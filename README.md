# osscout -- 开源项目深度尽调 Agent

> 面向技术团队的开源项目自动化尽调平台

## 项目简介

输入一个 GitHub 仓库地址，输出一份覆盖社区健康、代码质量、安全风险、技术演进四个维度的结构化尽调报告，并给出明确的推荐评级。

## 当前进展

### Phase 0（基础设施）已完成

后端服务、数据库、缓存、Docker 开发环境均已跑通。

### Phase 1（MVP -- CLI 分析）已完成

**Phase 1.1 已完成**：社区健康度 Agent + CLI 端到端打通。

**Phase 1.2 已完成**：抽出 `github-mcp` Server，通过 MCP 协议调用 GitHub API。

**Phase 1.3 已完成**：代码质量 Agent，新增 filesystem-mcp + code-analysis-mcp。

**Phase 1.4 已完成**：安全分析 Agent，新建 `osv-mcp` Server（安全数据采集中心），覆盖 OSV 漏洞查询 + 许可证风险评估。

**Phase 1.5 已完成**：技术演进 Agent + Orchestrator 并发调度。四个维度全部打通，总分覆盖 100/100 分。

```bash
# 分析指定仓库，输出文本报告
python -m app.cli analyze https://github.com/python-poetry/poetry

# 输出示例（四个维度，100/100 分）
总分 58/100 [#############-------] 58.0%

[community]  18/30 (60.0%)
  Bus Factor: 0/10 (2)          -- 2 人覆盖 50% 贡献，集中风险高
  Issue 响应: 8/8 (0.5 天)       -- 处理极快
  PR 合并率: 4/6 (65%)           -- 良好
  活跃贡献者: 4/4 (100 人)        -- 社区健康
  Release: 2/2 (0.2 个月前)      -- 维护活跃

[quality]    21/25 (84.0%)
  测试覆盖率: 6/8  (有 tests + CI)
  静态分析漏洞: 7/7 (0 高危)
  文档完整度: 3/5  (2/4 项)
  代码复杂度: 5/5  (平均 4.12，优秀)

[security]    5/25 (20.0%)
  CVE 记录: 0/10 (6高危, 3中危, 2低危)
  依赖漏洞: 0/8  (17 个依赖漏洞)
  许可证风险: 5/5 (MIT License，商业安全)
  安全响应速度: 0/2 (平均 1666 天)

[evolution]  14/20 (70.0%)
  发布频率: 4/6 (10次/年，约每2月1次)
  技术栈更新: 6/6 (所有依赖均为最新版本)
  Breaking Change: 4/4 (4次 major bump，均有文档说明)
  竞品对比: 0/4 (Phase 2 接入)
```

### 已验证的功能

- FastAPI 后端服务正常运行（`http://localhost:8000/health`）
- PostgreSQL 数据库 4 张核心表已创建（Repository / AnalysisTask / DueDiligenceReport / MetricHistory）
- Redis 缓存服务已就绪（容错降级，Server 未启动时自动跳过）
- **MCP 协议链路**：4 个 Server 全部打通
  - github-mcp：GitHub 元数据查询
  - filesystem-mcp：仓库克隆 + 文件操作
  - code-analysis-mcp：radon 圈复杂度 + AST 安全扫描
  - osv-mcp：SBOM 依赖提取 + OSV 漏洞查询 + 许可证检查
- **Orchestrator 并发调度**：`asyncio.gather` 并行运行 4 个 Agent，错误隔离（单 Agent 失败不影响其他）
- 社区健康度评分引擎（5 项指标：Bus Factor / Issue 响应 / PR 合并率 / 活跃贡献者 / Release）
- 代码质量评分引擎（4 项指标：测试覆盖 / 静态分析 / 文档 / 复杂度）
- 安全评分引擎（4 项指标：CVE 记录 / 依赖漏洞 / 许可证风险 / 响应速度）
- **技术演进评分引擎（3 项指标 + 1 项占位：发布频率 / 技术栈更新 / Breaking Change / 竞品对比）**
- CLI 入口：`python -m app.cli analyze <repo_url>`（输出四维度报告）
- 结构化日志 + 全局异常处理已接入
- Docker Compose 一键启动开发环境

## API 接口（Phase 2.1 + 2.2）

```bash
# 提交分析任务（立即返回，后台 Celery 执行）
POST /api/v1/analyze -d '{"repo_url": "https://github.com/owner/repo"}'
→ {"task_id": 1, "status": "running"}

# 查询任务状态
GET /api/v1/tasks/1
→ {"task_id": 1, "status": "completed", "report_id": 2}

# 获取尽调报告
GET /api/v1/reports/2
→ 完整报告 JSON（overall + 4 dimensions + findings）
```

**启动 Celery Worker（宿主机开发模式）**：

```bash
cd backend
export DATABASE_URL="postgresql+asyncpg://osscout:osscout@localhost:5432/osscout"
venv/Scripts/python.exe -m celery -A app.core.celery_app worker --loglevel=info -P solo
```

## 快速开始

### 1. 启动开发环境

```bash
# 启动所有服务（api + db + redis + web）
docker-compose -f docker-compose.dev.yml up -d

# 验证服务
curl http://localhost:8000/health

# 查看 API 文档
open http://localhost:8000/docs
```

### 2. 运行 CLI 分析

```bash
# 进入后端目录
cd backend

# 安装依赖（首次）
pip install -r requirements.txt

# 分析仓库
python -m app.cli analyze https://github.com/python-poetry/poetry
```

或在 Docker 中运行：

```bash
docker-compose -f docker-compose.dev.yml exec api python -m app.cli analyze https://github.com/python-poetry/poetry
```

### 3. 运行基准测试

对 5 个热门项目进行批量分析，验证评分体系合理性：

```bash
# 只输出到控制台
python ../scripts/benchmark.py

# 同时保存到文件
python ../scripts/benchmark.py --output benchmark_result.txt
```

### 4. 数据库连接（DataGrip / DBeaver）

- PostgreSQL：`localhost:5432`，用户名 `osscout`，密码 `ossscout`
- Redis：`localhost:6379`，无密码

## 项目结构

```
osscout/
├── README.md
├── PROJECT_PLAN.md           # 完整项目规划
├── CLAUDE.md                 # 协作规范
├── PROGRESS.md               # 开发进度记录
├── docker-compose.dev.yml    # 开发环境编排
│
├── backend/                  # FastAPI 后端
│   ├── app/
│   │   ├── main.py           # FastAPI 入口
│   │   ├── config.py         # 配置管理
│   │   ├── cli.py            # CLI 入口
│   │   ├── api/v1/           # REST 接口
│   │   │   ├── analyze.py    # POST /api/v1/analyze（Phase 2.1）
│   │   │   ├── tasks.py      # GET /api/v1/tasks/{id}（Phase 2.1）
│   │   │   ├── reports.py    # GET /api/v1/reports/{id}（Phase 2.1）
│   │   │   └── __init__.py   # 路由聚合
│   │   ├── core/             # 基础设施
│   │   │   ├── models.py     # 数据库模型
│   │   │   ├── database.py   # 异步数据库引擎
│   │   │   ├── cache.py      # Redis 缓存（含降级容错）
│   │   │   ├── celery_app.py # Celery 应用配置（Phase 2.2）
│   │   │   └── logger.py     # 结构化日志
│   │   ├── agents/           # Agent 层
│   │   │   ├── orchestrator.py   # 协调器（asyncio.gather 并发调度 4 个 Agent）
│   │   │   ├── community_agent.py
│   │   │   ├── quality_agent.py
│   │   │   ├── security_agent.py
│   │   │   ├── evolution_agent.py  # 技术演进 Agent（Phase 1.5）
│   │   │   └── reporter.py         # 报告格式化
│   │   ├── scoring/          # 评分体系
│   │   │   ├── community.py      # 社区健康度评分（0-30）
│   │   │   ├── quality.py        # 代码质量评分（0-25）
│   │   │   ├── security.py       # 安全评分（0-25）
│   │   │   └── evolution.py      # 技术演进评分（0-20，Phase 1.5）
│   │   ├── services/         # 业务逻辑
│   │   │   ├── analysis_service.py   # 分析任务生命周期（Phase 2.1）
│   │   │   ├── github_service.py     # GitHub 数据采集（MCP 方式）
│   │   │   ├── security_service.py   # 安全数据采集
│   │   │   └── evolution_service.py  # 技术演进数据采集
│   │   ├── mcp/              # MCP 客户端
│   │   │   └── client.py         # GitHub / Filesystem / CodeAnalysis / OSV Client
│   │   ├── rag/              # RAG 模块（Phase 3）
│   │   └── tasks/            # Celery 异步任务（Phase 2.2）
│   │       └── analysis_tasks.py  # run_due_diligence 任务
│   ├── tests/
│   └── alembic/              # 数据库迁移
│
├── frontend/                 # React 前端（Phase 2）
│   └── src/{components,pages,api,types}
├── mcp-servers/              # MCP Server 独立包
│   ├── github-mcp/           # GitHub 元数据查询
│   ├── filesystem-mcp/       # 仓库克隆 + 文件操作
│   ├── code-analysis-mcp/    # 代码静态分析（radon + AST）
│   └── osv-mcp/              # 安全数据采集中心（SBOM + OSV + license）
├── tmp/                      # 临时目录（MCP Server 克隆的仓库，gitignored）
├── knowledge-base/           # RAG 知识库文档（Phase 3）
├── scripts/                  # 工具脚本
└── docs/                     # 项目文档
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
| Phase 2.3 | 多项目对比 + 历史趋势 | 待开始 |
| Phase 2.4-5 | React 前端 + 可视化 | 待开始 |
| Phase 3 | Agent 智能化 + RAG | 待开始 |
| Phase 4 | 持续监控 + 预警 | 待开始 |

## 技术栈

- **后端**：Python 3.12 + FastAPI
- **数据库**：PostgreSQL 16 + Redis 7
- **Agent 编排**：手写 ReAct Loop（不用 LangChain）
- **MCP 协议**：官方 Python SDK（`mcp`）
- **LLM**：Claude / GPT（Phase 3 接入）
- **前端**：React 18 + TailwindCSS（Phase 2）
- **部署**：Docker Compose + Railway/Render

## 已知限制

| 限制 | 说明 | 计划解决 |
|------|------|----------|
| 超大仓库超时 | `vercel/next.js` 等 monorepo 可能触发 5 分钟超时（git clone 耗时过长） | Phase 2：部分克隆 + 大仓库降级策略 |
| Windows 控制台乱码 | 中文输出在默认 GBK 编码控制台显示为乱码，不影响文件保存 | 建议用 `--output` 参数导出到文件查看 |

---

*项目规划中，详见 PROJECT_PLAN.md*
