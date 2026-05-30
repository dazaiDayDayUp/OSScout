# osscout — 开源项目深度尽调 Agent

> 面向技术团队的开源项目自动化尽调平台

输入一个 GitHub 仓库地址，LLM 自主规划分析路径、自动调用工具采集数据、检索权威知识库做基准对比，最终输出一份覆盖社区健康、代码质量、安全风险、技术演进四个维度的结构化尽调报告。

**核心差异化**：规则评分打底 + **LLM 自主规划** + **生产级 RAG 知识库** + 综合报告生成 + **分析完成邮件推送**。

---

## 项目文档

| 文档 | 内容 | 什么时候看 |
|------|------|-----------|
| [`docs/PROGRESS.md`](docs/PROGRESS.md) | **当前进度、下一步行动** | 日常开发，看一眼就知道该做什么 |
| [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md) | **完整蓝图**：架构设计、数据模型、评分体系、面试叙事 | 深入理解项目，准备面试 |
| [`docs/PHASE5_PLAN.md`](docs/PHASE5_PLAN.md) | **Phase 5 技术方案**：三层架构、Tool 层、编排引擎、Multi-Agent 协作 | Phase 5 编码实现时查阅 |

---

## 快速开始

```bash
# 1. 启动数据库 + Redis（Docker）
docker-compose -f docker-compose.dev.yml up db redis

# 2. 配置环境变量
cp .env.example backend/.env
# 编辑 backend/.env，填入 API Key（GitHub / Kimi / DeepSeek / QQ 邮箱授权码）

# 3. 启动后端 FastAPI
cd backend && ./venv/Scripts/python.exe -m uvicorn app.main:app --reload

# 4. 启动 Celery Worker（必须启动，否则任务永远卡在 running）
cd backend && ./venv/Scripts/python.exe -m celery -A app.core.celery_app worker --loglevel=info --pool=solo

# 5. 启动前端 React
cd frontend && npm run dev
```

```bash
# CLI 分析（无需启动前后端）
cd backend && python -m app.cli analyze https://github.com/python-poetry/poetry
```

API 文档：`http://localhost:8000/docs`

---

## 技术栈概览

- **后端**：Python 3.12 + FastAPI + SQLAlchemy(async) + PostgreSQL 16 + Redis 7
- **任务队列**：Celery + Redis Broker
- **Agent 编排**：手写 Plan-and-Execute（5.4）+ ReAct Loop（5.5）（不用 LangChain）
- **MCP 协议**：官方 Python SDK
- **LLM**：Kimi (`kimi-k2.6`) + DeepSeek (`deepseek-v4-pro`)
- **RAG**：ChromaDB + sentence-transformers + BM25 + Cross-Encoder Rerank + Self-RAG
- **前端**：React 19 + TypeScript 5.8 + TailwindCSS v4 + shadcn/ui + Recharts
- **邮件推送**：FastAPI-Mail + Celery 异步任务

详细技术选型理由见 [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md) 第 3 章。

---

*开发进度见 [`docs/PROGRESS.md`](docs/PROGRESS.md)，完整规划见 [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md)。*
