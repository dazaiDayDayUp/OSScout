# 项目开发进度记录

> 当前进度速查，完整规划见 `PROJECT_PLAN.md`。

---

## 当前状态

**Phase 2.3 完成，即将进入 Phase 2.4。**

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
| Phase 2.3 | 多项目对比 + 历史趋势 + 报告列表分页 | ✅ |

---

## Phase 2.3 新增接口

| 接口 | 方法 | 功能 |
|------|------|------|
| `/api/v1/reports` | GET | 报告列表查询（分页，支持 repo_id 过滤） |
| `/api/v1/repos/{id}/history` | GET | 仓库历史趋势（5 维度时序数据） |
| `/api/v1/compare` | POST | 多仓库对比分析（2-5 个仓库） |

---

## 环境备忘

### 开发规范

- **Phase 1-4 开发阶段**：宿主机 + venv 开发，Docker 只跑 db/redis
- **venv 路径**：`backend/venv/`，Python 3.12.10
- **包安装**：`backend/venv/Scripts/python.exe -m pip install xxx`

### 启动 Celery Worker（宿主机）

```bash
cd backend
export DATABASE_URL="postgresql+asyncpg://osscout:ossscout@localhost:5432/osscout"
venv/Scripts/python.exe -m celery -A app.core.celery_app worker --loglevel=info -P solo
```

> Windows 上使用 `-P solo` 避免多进程池兼容性问题。

### 已知环境问题

| 问题 | 解决方案 |
|------|---------|
| greenlet 3.5.0 DLL 加载失败（Windows） | 降级到 `greenlet==3.1.1` |
| Windows 控制台 GBK 编码 | 避免 Unicode 特殊字符，用 `--output` 导出文件 |
| Celery Worker asyncpg 并发错误 | 每个任务独立创建 engine + NullPool（见 `analysis_tasks.py`） |
| SQLAlchemy session 缓存导致轮询 stale | 轮询前 `await session.rollback()` 清除缓存 |

---

## 技术债务

| 优化项 | 计划解决阶段 |
|--------|-------------|
| 补 Redis 缓存层 | Phase 2 功能完成后统一优化 |
| 超大仓库分析超时 | Phase 2：部分克隆 + 大仓库降级 |
| API 限频计数器 | Phase 4：Redis 分布式限频 |

---

## 下一步

**Phase 2.4：React 前端骨架**

- HTTP 客户端封装（api/client.ts）
- 首页：提交分析表单（输入 repo_url）
- 报告详情页：文本版报告展示
- 路由配置（React Router）
