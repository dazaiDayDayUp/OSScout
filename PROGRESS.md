# 项目开发进度记录

> 当前进度速查，完整规划见 `PROJECT_PLAN.md`。

---

## 当前状态

**Phase 3 全部完成（3.1-3.5），前端适配完成。**

最近更新：2026-05-19

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
| Phase 3.2 | ChromaDB 向量库 + 知识库文档入库（9 篇文档） | ✅ |
| Phase 3.3 | 4 个分析 Agent 接入 LLM 推理（规则评分 + LLM 增强，统一 reasoning 字段） | ✅ |
| Phase 3.4 | Orchestrator ReAct Loop + RAG 校准 + 冲突消解 | ✅ |
| Phase 3.5 | 综合报告 Agent（SynthesisAgent：执行摘要/风险矩阵/明确建议/数据来源标注） | ✅ |
| 前端适配 | ReportPage 展示 reasoning + RAG 校准 + 冲突检测 + 综合报告 | ✅ |

---

## Phase 3 新增文件/模块

```
backend/app/rag/                    # RAG 模块（Phase 3.2）
├── embeddings.py                   # all-MiniLM-L6-v2 封装
├── vector_store.py                 # ChromaDB 持久化封装
└── query.py                        # RAGQueryEngine 查询引擎

backend/app/agents/
├── llm_enhancer.py                 # 通用 LLM 推理增强器（Phase 3.3）
├── synthesis_agent.py              # 综合报告 Agent（Phase 3.5）
├── community_agent.py              # 增加 reasoning 字段
├── quality_agent.py                # 增加 reasoning 字段
├── security_agent.py               # 增加 reasoning 字段
├── evolution_agent.py              # 增加 reasoning 字段
├── orchestrator.py                 # 重构：RAG 校准 + 冲突消解 + ReAct Loop
└── reporter.py                     # 增加 synthesis 展示

backend/app/llm/base.py             # 修复 chat_structured() 消息顺序（Kimi 兼容）

knowledge-base/                     # 知识库文档（Phase 3.2）
├── case-studies/                   # 失败案例（left-pad / faker-js / event-stream）
├── methodology/                    # 评估方法论（OpenSSF / CNCF）
└── competitors/                    # 竞品映射（前端框架/后端框架/状态管理）

scripts/init_kb.py                  # 知识库初始化脚本
```

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
| LLM | Kimi k2.6 + DeepSeek v4-pro | OpenAI 兼容 API |
| RAG | ChromaDB + sentence-transformers | all-MiniLM-L6-v2 |

---

## API 接口

| 接口 | 方法 | 功能 |
|------|------|------|
| `/api/v1/analyze` | POST | 提交分析任务（异步，返回 task_id） |
| `/api/v1/tasks/{id}` | GET | 查询任务状态 |
| `/api/v1/reports/{id}` | GET | 获取尽调报告详情（含 reasoning / calibrations / synthesis） |
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

# 终端 3：Celery Worker（必须启动！否则任务永远卡在 running）
cd backend && ./venv/Scripts/python.exe -m celery -A app.core.celery_app worker --loglevel=info --pool=solo

# 终端 4：前端 React
cd frontend && npm run dev
```

---

## 已知问题（2026-05-19 更新）

| 优先级 | 问题 | 说明 | 计划解决 |
|--------|------|------|----------|
| **高** | Kimi 并发限制导致 LLM 降级 | Moonshot 免费账户并发上限 3，4 个 Agent 并行时第 4 个触发 429，LLM 增强降级 | 增加重试/退避机制，或限制 LLM 并发数 |
| **高** | 前端提交后分析耗时过长 | 完整分析需 3-5 分钟（GitHub API + 4xAgent + RAG + Synthesis），用户体验差 | 增加进度反馈 / 预热缓存 / 优化超时 |
| **高** | 旧报告无 Phase 3 数据 | Phase 2 生成的报告 `raw_results` 中无 reasoning/calibrations/synthesis | 正常，重新分析即可生成完整数据 |
| **中** | Windows 控制台 GBK 乱码 | 中文日志/API 返回正常，仅控制台显示乱码 | 低优先级 |
| **中** | 超大仓库分析耗时过长 | facebook/react 需 3 分钟（npm 依赖版本查询串行） | Phase 4 |
| **低** | 对比分析同步阻塞 | 对比接口同步等待所有 Celery 任务完成 | Phase 4 |

---

## 下一步

**Phase 4：V3 — 持续监控 + 预警**

- Celery Beat 定时巡检
- 指标趋势分析 + 异常检测
- 用户关注列表（watch list）
- 邮件/Webhook 通知
