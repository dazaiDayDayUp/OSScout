# osscout -- 开源项目深度尽调 Agent

> 面向技术团队的开源项目自动化尽调平台

输入一个 GitHub 仓库地址，LLM 自主规划分析路径、自主调用工具采集数据、自主检索权威知识库做基准对比，最终输出一份覆盖社区健康、代码质量、安全风险、技术演进四个维度的结构化尽调报告。

**核心差异化**：规则评分打底 + **LLM 自主规划与工具调用** + **生产级 RAG 知识库** + 综合报告生成。

## 当前进展

**Phase 0 ~ Phase 4 全部完成**，涵盖：基础设施 → CLI 单项目分析 → Web 平台 → Agent 智能化 → 生产级 RAG（167 篇知识库 / 语义分块 / 混合检索 + BM25 + RRF / CrossEncoder 重排序 / Self-RAG 自验证 / Web 搜索 fallback / 引用追踪）。

**当前重点**：

- **Phase 5 — 真正的 Agent 架构**：LLM Function Calling、MCP 工具注册表、Plan-and-Execute 自主规划、ReAct 自主循环、Reflection 反思

详见 [PROGRESS.md](PROGRESS.md) 了解已完成内容、已知问题和下一步行动。

## 快速开始

```bash
# 1. 启动数据库 + Redis（Docker）
docker-compose -f docker-compose.dev.yml up db redis

# 2. 启动后端 FastAPI
cd backend && ./venv/Scripts/python.exe -m uvicorn app.main:app --reload

# 3. 启动 Celery Worker（必须启动，否则任务永远卡在 running）
cd backend && ./venv/Scripts/python.exe -m celery -A app.core.celery_app worker --loglevel=info --pool=solo

# 4. 启动前端 React
cd frontend && npm run dev
```

```bash
# CLI 分析（无需启动前后端）
cd backend && python -m app.cli analyze https://github.com/python-poetry/poetry
```

API 文档：`http://localhost:8000/docs`

## 技术栈

- **后端**：Python 3.12 + FastAPI + SQLAlchemy(async) + PostgreSQL 16 + Redis 7
- **任务队列**：Celery + Redis Broker
- **Agent 编排**：手写 Plan-and-Execute + ReAct Loop（不用 LangChain）
- **MCP 协议**：官方 Python SDK（`mcp`）
- **LLM**：Kimi (`kimi-k2.6`) + DeepSeek (`deepseek-v4-pro`)
- **RAG**：ChromaDB + sentence-transformers + BM25 + Cross-Encoder Rerank（Phase 4）
- **前端**：React 19 + TypeScript 5.8 + TailwindCSS v4 + shadcn/ui + Recharts
- **部署**：Docker Compose（后续优化阶段）

## 开发计划

| 阶段 | 目标 | 状态 |
|------|------|------|
| Phase 0 | 基础设施（脚手架、Docker、数据库、GitHub API） | 已完成 |
| Phase 1 | MVP — CLI 单项目分析（4 Agent + 100 分评分） | 已完成 |
| Phase 2 | V1 — Web 平台 + 异步任务 + React 前端可视化 | 已完成 |
| Phase 3 | V2 — Agent 智能化 + RAG 初版（LLM 推理 + 知识库） | 已完成 |
| Phase 4 | RAG 深度优化（知识扩充/分块/混合检索/Rerank/Self-RAG/引用追踪） | 已完成 |
| **Phase 5** | **真正的 Agent 架构（Function Calling/Plan-and-Execute/Reflection）** | **当前重点** |

完整规划、架构设计、数据模型、面试叙事框架见 [PROJECT_PLAN.md](PROJECT_PLAN.md)。

---

*开发进度和已知问题见 [PROGRESS.md](PROGRESS.md)。*
