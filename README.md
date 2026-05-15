# osscout — 开源项目深度尽调 Agent

> 面向技术团队的开源项目自动化尽调平台

## 项目简介

输入一个 GitHub 仓库地址，输出一份覆盖社区健康、代码质量、安全风险、技术演进四个维度的结构化尽调报告，并给出明确的推荐评级。

## 当前进展

**Phase 0（基础设施）已完成**，后端服务、数据库、缓存、Docker 开发环境均已跑通。

### 已验证的功能

- FastAPI 后端服务正常运行（`http://localhost:8000/health`）
- PostgreSQL 数据库 4 张核心表已创建（Repository / AnalysisTask / DueDiligenceReport / MetricHistory）
- Redis 缓存服务正常运行
- GitHub API 封装完成（带 Redis 缓存和并发控制）
- 结构化日志 + 全局异常处理已接入
- Docker Compose 一键启动开发环境

## 快速开始

```bash
# 1. 启动开发环境（api + db + redis + web）
docker-compose -f docker-compose.dev.yml up

# 2. 验证服务
open http://localhost:8000/health

# 3. 查看 API 文档
open http://localhost:8000/docs
```

数据库连接（DataGrip / DBeaver）：
- PostgreSQL：`localhost:5432`，用户名 `osscout`，密码 `osscout`
- Redis：`localhost:6379`，无密码

## 项目结构

```
osscout/
├── backend/              # FastAPI 后端
│   ├── app/
│   │   ├── api/v1/       # REST 接口
│   │   ├── core/         # 数据库、缓存、配置、日志
│   │   ├── agents/       # 5 个 Agent + Orchestrator
│   │   ├── mcp/          # MCP 客户端 + 5 个 Server
│   │   ├── rag/          # 向量库、Embedding
│   │   ├── services/     # 业务逻辑（GitHub API 等）
│   │   ├── tasks/        # Celery 异步任务
│   │   └── scoring/      # 评分体系
│   ├── tests/
│   └── alembic/          # 数据库迁移
├── frontend/             # React 前端
│   └── src/{components,pages,api,types}
├── mcp-servers/          # MCP Server 独立包
├── knowledge-base/       # RAG 知识库文档
├── scripts/              # 工具脚本
└── docs/                 # 项目文档
```

## 开发计划

| 阶段 | 目标 | 状态 |
|------|------|------|
| Phase 0 | 基础设施（脚手架、Docker、数据库） | 已完成 |
| Phase 1 | MVP — 单项目 CLI 分析 | 待开始 |
| Phase 2 | Web 平台 + 异步任务 | 待开始 |
| Phase 3 | Agent 智能化 + RAG | 待开始 |
| Phase 4 | 持续监控 + 预警 | 待开始 |

## 技术栈

- **后端**：Python 3.12 + FastAPI
- **数据库**：PostgreSQL 16 + Redis 7
- **Agent 编排**：手写 ReAct Loop（不用 LangChain）
- **LLM**：Claude / GPT
- **前端**：React 18 + TailwindCSS

---

*项目规划中，详见 PROJECT_PLAN.md（内部文档）*
