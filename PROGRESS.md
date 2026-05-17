# 项目开发进度记录

> 当前进度速查，完整规划见 `PROJECT_PLAN.md`。

---

## 当前状态：Phase 2.1 完成，即将进入 Phase 2.2

**最近更新**：2026-05-17

---

## 已完成阶段摘要

| 阶段 | 核心成果 | 状态 |
|------|---------|------|
| Phase 0 | FastAPI + PostgreSQL + Redis + Docker 基础设施 | ✅ |
| Phase 1.1 | 社区健康 Agent + CLI 端到端打通 | ✅ |
| Phase 1.2 | github-mcp Server（MCP 协议接入 GitHub API） | ✅ |
| Phase 1.3 | 代码质量 Agent（filesystem-mcp + code-analysis-mcp） | ✅ |
| Phase 1.4 | 安全分析 Agent（osv-mcp + OSV 漏洞 + 许可证） | ✅ |
| Phase 1.5 | 技术演进 Agent + Orchestrator 并发调度（四维度 100 分） | ✅ |
| **Phase 2.1** | **REST API + 数据库持久化** | **✅** |

---

## Phase 2.1：REST API 骨架 + 数据库持久化（已完成 ✅）

**新增/修改的文件**：

| 文件 | 行数 | 说明 |
|------|------|------|
| `backend/app/services/analysis_service.py` | ~220 | 核心服务层：仓库获取/创建、任务提交、后台分析执行、报告入库 |
| `backend/app/api/v1/analyze.py` | ~80 | POST /api/v1/analyze |
| `backend/app/api/v1/tasks.py` | ~95 | GET /api/v1/tasks/{task_id} |
| `backend/app/api/v1/reports.py` | ~120 | GET /api/v1/reports/{report_id} |
| `backend/app/api/v1/__init__.py` | ~20 | 路由聚合 |
| `backend/app/main.py` | 改 2 行 | 注册 /api/v1 前缀 |

**端到端验证记录**：

```bash
# 1. 提交分析
POST /api/v1/analyze
→ {"task_id": 1, "status": "running", "estimated_seconds": 120}

# 2. 查询状态（49 秒后）
GET /api/v1/tasks/1
→ {"task_id": 1, "status": "completed", "report_id": 1, "duration_seconds": 49}

# 3. 获取报告
GET /api/v1/reports/1
→ {"overall": {"score": 53, "rating": "C", ...}, "dimensions": {...}}
```

| 维度 | 得分 | 评级 |
|------|------|------|
| community | 22/30 | 健康 |
| quality | 21/25 | 良好 |
| security | 2/25 | 风险高（49 个依赖漏洞，大量 CVE）|
| evolution | 8/20 | 一般 |
| **综合** | **53/100** | **C** |

---

## 技术债务 / 待优化

| 优化项 | 原因 | 计划解决阶段 |
|--------|------|-------------|
| **补 Redis 缓存层** | Phase 1.2 迁移到 MCP 后，`core/cache.py` 未被调用。GitHub API 响应未缓存，每次分析都走实时请求 | **Phase 2 功能完成后统一优化** |
| 超大仓库分析超时 | `vercel/next.js` 等 monorepo git clone 超过 5 分钟 | Phase 2：部分克隆 + 大仓库降级 |
| API 限频计数器 | 未实现 Redis 限频，依赖 GitHubMCPClient 的 Semaphore（进程级）| Phase 4：Redis 分布式限频 |

---

## Phase 2.2：Celery 异步任务队列（待开始）

**目标**：把 `asyncio.create_task()` 换成 Celery 异步任务，实现真正的任务持久化。

| 新增/修改 | 内容 |
|-----------|------|
| `backend/app/core/celery_app.py` | Celery 应用配置（Redis broker） |
| `backend/app/tasks/analysis_tasks.py` | `run_due_diligence` 异步任务 |
| `backend/app/api/v1/analyze.py` | `POST` 改为"提交 Celery 任务 + 立即返回" |

---

## Phase 2.3~2.5（概述）

| 子阶段 | 目标 | 状态 |
|--------|------|------|
| 2.3 | 多项目对比 + 历史趋势接口 | 待开始 |
| 2.4 | React 前端骨架 | 待开始 |
| 2.5 | 前端可视化 | 待开始 |

---

## 环境注意事项

### 开发环境规范（必须遵守）

- **Phase 1-4 开发阶段**：宿主机 + venv 开发，Docker 只跑 db/redis
- **Phase 5 部署阶段**：统一做 Docker 部署
- **venv 路径**：`backend/venv/`，Python 3.12.10
- **包安装**：`backend/venv/Scripts/python.exe -m pip install xxx`

### 已知环境问题

| 问题 | 解决方案 |
|------|---------|
| greenlet 3.5.0 DLL 加载失败（Windows） | 降级到 `greenlet==3.1.1` |
| Windows 控制台 GBK 编码 | 避免 Unicode 特殊字符，用 `--output` 导出文件 |

---

## 下一步动作

**Phase 2.2：Celery 异步任务队列**

1. 创建 `backend/app/core/celery_app.py`
2. 创建 `backend/app/tasks/analysis_tasks.py`
3. 修改 `analyze.py` 接口调用 Celery

---

## Phase 0~1 详细记录

### Phase 0：基础设施（已完成 ✅）

| 文件路径 | 说明 |
|---------|------|
| `backend/requirements.txt` | Python 依赖清单 |
| `backend/app/config.py` | Pydantic Settings 配置管理 |
| `backend/app/main.py` | FastAPI 入口 + 健康检查 + 日志 + 异常处理 |
| `backend/app/core/models.py` | 4 张数据库表模型 |
| `backend/app/core/database.py` | 异步数据库引擎 |
| `backend/app/core/cache.py` | Redis 缓存封装 |
| `backend/app/core/logger.py` | structlog 结构化日志 |
| `backend/Dockerfile` | 后端容器镜像构建 |
| `docker-compose.dev.yml` | 开发环境编排 |
| `.env.example` / `.env` | 环境变量配置 |

端到端验证：6 个 GitHub API 并发调用 ~3000ms，Redis 缓存命中 ~70ms。

### Phase 1.1：社区健康 Agent（已完成 ✅）

新增文件：`scoring/community.py`、`agents/community_agent.py`、`agents/orchestrator.py`、`agents/reporter.py`、`cli.py`

验证结果（python-poetry/poetry）：总分 18/30

### Phase 1.2：抽出 github-mcp Server（已完成 ✅）

新增文件：`mcp-servers/github-mcp/server.py`、`app/mcp/client.py`

MCP 链路验证：CLI → orchestrator → community_agent → github_service → GitHubMCPClient → github-mcp Server → GitHub API

### Phase 1.3：代码质量 Agent（已完成 ✅）

新增文件：`mcp-servers/filesystem-mcp/server.py`、`mcp-servers/code-analysis-mcp/server.py`、`scoring/quality.py`、`agents/quality_agent.py`

关键决策：Windows MCP stdio + subprocess 死锁 → 弃用命令行 semgrep，改用 Python AST 扫描

验证结果（psf/requests）：community 22/30 + quality 14/25 = 36/55

### Phase 1.4：安全分析 Agent（已完成 ✅）

新增文件：`mcp-servers/osv-mcp/server.py`、`scoring/security.py`、`agents/security_agent.py`、`services/security_service.py`

osv-mcp 成为"安全数据采集中心"：SBOM + OSV 漏洞 + License 统一入口

验证结果（pallets/click）：community 14 + quality 14 + security 5 = 33/80

### Phase 1.5：技术演进 Agent + Orchestrator 并发调度（已完成 ✅）

新增文件：`services/evolution_service.py`、`scoring/evolution.py`、`agents/evolution_agent.py`

Orchestrator 从串行改为 `asyncio.gather` 并行调度 4 个 Agent，错误隔离

验证结果（python-poetry/poetry）：总分 58/100
- community 18/30 | quality 21/25 | security 5/25 | evolution 14/20

Phase 1 收尾清理：删除 `api/v1/debug.py`、移除 legacy 代码引用
