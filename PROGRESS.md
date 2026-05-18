# 项目开发进度记录

> 当前进度速查，完整规划见 `PROJECT_PLAN.md`。

---

## 当前状态

**Phase 3.1 完成，进入 Phase 3.2。**

最近更新：2026-05-18

---

## 已完成阶段速查

| 阶段 | 核心成果 | 状态 |
|------|---------|------|
| Phase 0 | FastAPI + PostgreSQL + Redis + Docker 基础设施 | ✅ |
| Phase 1.1 | 社区健康 Agent + CLI 端到端打通 | ✅ |
| Phase 1.2 | github-mcp Server（MCP 协议接入 GitHub API） | ✅ |
| Phase 1.3 | 代码质量 Agent（filesystem-mcp + code-analysis-mcp） | ✅ |
| Phase 1.4 | 安全分析 Agent（osv-mcp + OSV 漏洞 + 许可证） | ✅ |
| Phase 1.5 | 技术演进 Agent + Orchestrator 并发调度（四维度 100 分） | ✅ |
| Phase 2.1 | REST API + 数据库持久化 | ✅ |
| Phase 2.2 | Celery 异步任务队列（Redis Broker + Worker） | ✅ |
| Phase 2.3 | 多项目对比 `/compare` + 历史趋势 `/history` + 报告列表分页 | ✅ |
| Phase 2.4 | React 前端骨架（首页/报告列表/报告详情/路由） | ✅ |
| Phase 2.5 | 前端可视化：ScoreGauge 环形仪表盘 + DimensionBarChart 条形图 + ComparePage 对比页 + 全局去 AI 味配色 | ✅ |
| Phase 3.1 | LLM Client 封装（Kimi + DeepSeek 双后端，Prompt 模板，结构化输出） | ✅ |

---

## 技术栈

| 层级 | 选型 | 版本 |
|------|------|------|
| 构建工具 | Vite | 6.x |
| UI 框架 | React | 19 |
| 语言 | TypeScript | 5.8 |
| 路由 | React Router | v7 |
| HTTP | Axios + TanStack Query | v5 |
| 样式 | TailwindCSS | v4 |
| 组件库 | shadcn/ui | latest |
| 图表 | Recharts | latest |

---

## API 接口

| 接口 | 方法 | 功能 |
|------|------|------|
| `/api/v1/analyze` | POST | 提交分析任务（异步，返回 task_id） |
| `/api/v1/tasks/{id}` | GET | 查询任务状态 |
| `/api/v1/reports/{id}` | GET | 获取尽调报告详情 |
| `/api/v1/reports` | GET | 报告列表查询（分页，支持 repo_id 过滤） |
| `/api/v1/repos/{id}/history` | GET | 仓库历史趋势（5 维度时序数据） |
| `/api/v1/compare` | POST | 多仓库对比分析（2-5 个仓库） |

---

## 开发环境

```bash
# 终端 1：数据库 + Redis（Docker）
docker-compose -f docker-compose.dev.yml up db redis

# 终端 2：后端 FastAPI
cd backend && ./venv/Scripts/python.exe -m uvicorn app.main:app --reload

# 终端 3：Celery Worker
cd backend && ./venv/Scripts/python.exe -m celery -A app.core.celery_app worker --loglevel=info --pool=solo

# 终端 4：前端 React
cd frontend && npm run dev
```

---

## 已知问题

| 问题 | 说明 | 计划解决 |
|------|------|----------|
| 数据库中文编码乱码 | Windows 控制台 GBK 编码影响日志输出，API 返回正常 | 低 |
| 超大仓库分析耗时过长 | facebook/react 需 3 分钟（npm 依赖版本查询串行）| Phase 3 |
| 对比分析同步阻塞 | 对比接口等待所有 Celery 任务完成，非异步风格 | Phase 3 |
| 前端配色仍需迭代 | 去 AI 味方向正确，细节可继续打磨 | Phase 3-4 |

---

## 下一步

**Phase 3：V2 — Agent 智能化 + RAG**

- ✅ Phase 3.1：LLM Client 封装（Kimi + DeepSeek 双后端）
- Phase 3.2：ChromaDB 向量库 + 知识库文档入库
- Phase 3.3：4 个分析 Agent 接入 LLM 推理
- Phase 3.4：Orchestrator 并行 ReAct Loop + RAG 校准
- Phase 3.5：综合报告 Agent（可解释性推理）
