# osscout -- 开源项目深度尽调 Agent

> 面向技术团队的开源项目自动化尽调平台

## 项目简介

输入一个 GitHub 仓库地址，输出一份覆盖社区健康、代码质量、安全风险、技术演进四个维度的结构化尽调报告，并给出明确的推荐评级。

## 当前进展

### Phase 0（基础设施）已完成

后端服务、数据库、缓存、Docker 开发环境均已跑通。

### Phase 1（MVP -- CLI 分析）进行中

**Phase 1.1 已完成**：社区健康度 Agent + CLI 端到端打通。

**Phase 1.2 已完成**：抽出 `github-mcp` Server，通过 MCP 协议调用 GitHub API。

**Phase 1.3 已完成**：代码质量 Agent，新增 filesystem-mcp + code-analysis-mcp。

```bash
# 分析指定仓库，输出文本报告
python -m app.cli analyze https://github.com/psf/requests

# 输出示例（两个维度）
总分 36/55 [#############-------] 65.5%

[community]  22/30 (73.3%)
  Bus Factor: 6/10 (3)          -- 3 人覆盖 50% 贡献
  Issue 响应: 8/8 (0.1 天)       -- 处理极快
  PR 合并率: 2/6 (34%)           -- 偏低
  活跃贡献者: 4/4 (100 人)        -- 社区健康
  Release: 2/2 (0.0 个月前)      -- 维护活跃

[quality]    14/25 (56.0%)
  测试覆盖率: 6/8  (有 tests + CI)
  静态分析漏洞: 7/7 (0 高危)
  文档完整度: 3/5  (2/4 项)
  代码复杂度: 5/5  (平均 2.84，优秀)
```

### 已验证的功能

- FastAPI 后端服务正常运行（`http://localhost:8000/health`）
- PostgreSQL 数据库 4 张核心表已创建（Repository / AnalysisTask / DueDiligenceReport / MetricHistory）
- Redis 缓存服务正常运行，冷热请求差距 40 倍+
- **MCP 协议链路**：github-mcp + filesystem-mcp + code-analysis-mcp 全部打通
- 社区健康度评分引擎（5 项指标规则评分）
- 代码质量评分引擎（4 项指标：测试覆盖 / 静态分析 / 文档 / 复杂度）
- CLI 入口：`python -m app.cli analyze <repo_url>`（输出双维度报告）
- 结构化日志 + 全局异常处理已接入
- Docker Compose 一键启动开发环境

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

### 3. 数据库连接（DataGrip / DBeaver）

- PostgreSQL：`localhost:5432`，用户名 `osscout`，密码 `osscout`
- Redis：`localhost:6379`，无密码

## 项目结构

```
osscout/
├── README.md
├── PROJECT_PLAN.md           # 完整项目规划
├── PROGRESS.md               # 开发进度记录
├── CLAUDE.md                 # 协作规范
├── docker-compose.dev.yml    # 开发环境编排
│
├── backend/                  # FastAPI 后端
│   ├── app/
│   │   ├── main.py           # FastAPI 入口
│   │   ├── config.py         # 配置管理
│   │   ├── cli.py            # CLI 入口
│   │   ├── api/v1/           # REST 接口
│   │   │   └── debug.py      # 调试接口（Phase 0 验证用）
│   │   ├── core/             # 基础设施
│   │   │   ├── models.py     # 数据库模型
│   │   │   ├── database.py   # 异步数据库引擎
│   │   │   ├── cache.py      # Redis 缓存
│   │   │   └── logger.py     # 结构化日志
│   │   ├── agents/           # Agent 层
│   │   │   ├── orchestrator.py   # 协调器（串行调度 community + quality）
│   │   │   ├── community_agent.py
│   │   │   ├── quality_agent.py  # 代码质量 Agent（Phase 1.3）
│   │   │   └── reporter.py       # 报告格式化
│   │   ├── scoring/          # 评分体系
│   │   │   ├── community.py      # 社区健康度评分
│   │   │   └── quality.py        # 代码质量评分（Phase 1.3）
│   │   ├── services/         # 业务逻辑
│   │   │   ├── github_service_legacy.py  # 旧版直接调用（保留调试）
│   │   │   └── mcp_github_service.py     # MCP 版本（Phase 1.2）
│   │   ├── mcp/              # MCP 客户端（Phase 1.2+）
│   │   │   └── client.py         # GitHub / Filesystem / CodeAnalysis Client
│   │   ├── rag/              # RAG 模块（Phase 3）
│   │   └── tasks/            # Celery 任务（Phase 2）
│   ├── tests/
│   └── alembic/              # 数据库迁移
│
├── frontend/                 # React 前端（Phase 2）
│   └── src/{components,pages,api,types}
├── mcp-servers/              # MCP Server 独立包（Phase 1.2+）
│   ├── github-mcp/           # GitHub API 查询
│   ├── filesystem-mcp/       # 仓库克隆 + 文件操作（Phase 1.3）
│   └── code-analysis-mcp/    # 代码静态分析（Phase 1.3）
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
| Phase 1.4 | 安全分析 Agent | 待开始 |
| Phase 1.5 | Orchestrator 并发 + 综合评级 | 待开始 |
| Phase 2 | Web 平台 + 异步任务 + React 前端 | 待开始 |
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

---

*项目规划中，详见 PROJECT_PLAN.md*
