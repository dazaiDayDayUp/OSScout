# 项目开发进度记录

> 这份文档是新会话的快速回归入口，记录"做到哪 / 决策是什么 / 下一步动作"。
> 项目完整规划见 `PROJECT_PLAN.md`，协作规范见 `CLAUDE.md`。

---

## 当前状态：Phase 1.4 完成，即将进入 Phase 1.5

**最近更新**：2026-05-16

---

## Phase 0：基础设施（已完成 ✅）

### 已完成文件清单

| 文件路径 | 说明 |
|---------|------|
| `backend/requirements.txt` | Python 依赖清单（Phase 1+ 依赖已注释） |
| `backend/app/config.py` | Pydantic Settings 配置管理 |
| `backend/app/main.py` | FastAPI 入口 + 健康检查 + 日志 + 异常处理 + 路由注册 |
| `backend/app/core/models.py` | 4 张数据库表模型（Repository / AnalysisTask / DueDiligenceReport / MetricHistory） |
| `backend/app/core/database.py` | 异步数据库引擎 + 会话管理 |
| `backend/app/core/cache.py` | Redis 缓存封装（get/set/delete + 默认 24h TTL + **降级容错**） |
| `backend/app/core/logger.py` | structlog 结构化日志配置 |
| `backend/app/services/github_service.py` | GitHub API 封装（缓存 + 并发控制） |
| `backend/app/api/v1/debug.py` | **临时调试接口**（Phase 0 验证用，Phase 1 进入正式开发后可考虑移除） |
| `backend/Dockerfile` | 后端容器镜像构建 |
| `backend/alembic.ini` | Alembic 迁移配置 |
| `backend/alembic/env.py` | 迁移环境脚本（异步支持） |
| `backend/alembic/versions/001_init.py` | 初始迁移脚本 |
| `docker-compose.dev.yml` | 开发环境编排（api/web/db/redis/worker） |
| `.env.example` / `.env` | 环境变量模板和本地配置 |
| `.gitignore` | Git 忽略规则（已排除 `PROJECT_PLAN.md`、`CLAUDE.md`、`.env`、venv） |
| `README.md` | 项目说明 |

### 端到端验证记录

通过 `backend/app/api/v1/debug.py` 提供的三个调试端点，在 FastAPI Swagger UI（`/docs`）中实际调用并验证：

| 验证项 | 数据 | 结论 |
|--------|------|------|
| `/all` 冷启动耗时 | ~3000ms | 6 个 GitHub API 并发调用正常（串行会 >6 秒） |
| `/all` 热请求耗时 | ~70ms | Redis 缓存命中，差距 40 倍+ |
| 单接口冷/热对比 | 显著差距 | 缓存层全链路打通 |

**已知问题与解决**：
- ~~GitHub `/stats/commit_activity` 首次请求可能返回 HTTP 202 + 空数组~~ → **已修复**：改用 `/stats/participation` 端点获取提交活动数据，避免后台异步计算导致的空数据问题。`participation` 端点直接返回即时计算结果（含 52 周每周提交总数），与 `commit_activity` 的 `total` 字段等效。
- Swagger UI 渲染大 JSON 会卡死浏览器，`/all` 接口已改为返回摘要而非完整数据。

### 启动命令

```bash
docker-compose -f docker-compose.dev.yml up -d
# 健康检查
curl http://localhost:8000/health
# 文档
open http://localhost:8000/docs
```

---

## Phase 1：MVP — 单项目 CLI 分析

### Phase 1.1：社区健康 Agent + 端到端打通（已完成 ✅）

**决策回顾**：起步策略为"混合方案"——先用已有 `github_service` 直接调用跑通端到端，后续再抽 MCP。

#### 已完成的 5 个文件

| 文件 | 职责 | 行数 |
|------|------|------|
| `backend/app/scoring/community.py` | 社区健康度五项指标评分规则 | 228 |
| `backend/app/agents/community_agent.py` | Agent 主体：采集 → 评分 → 结构化输出 | 123 |
| `backend/app/agents/orchestrator.py` | 串行协调器（调度 community_agent） | 68 |
| `backend/app/agents/reporter.py` | 文本报告格式化（Markdown 风格） | 112 |
| `backend/app/cli.py` | CLI 入口：`python -m app.cli analyze <url>` | 56 |

#### 执行链路（6 层）

```
repo_url 字符串
    ↓ cli.py 解析参数
    ↓ orchestrator.py 调度
    ↓ community_agent.py 解析 URL + 采集数据
    ↓ github_service.py 并发调用 6 个 GitHub API
    ↓ scoring/community.py 计算 5 项指标
    ↓ reporter.py 格式化为文本
    ↓ cli.py print 输出
```

#### 端到端验证结果（python-poetry/poetry）

```bash
$ python -m app.cli analyze https://github.com/python-poetry/poetry
总分 18/30 [############--------] 60.0%
```

| 指标 | 得分 | 原始值 | 说明 |
|------|------|--------|------|
| Bus Factor | 0/10 | 2 | 仅 2 人覆盖 50% 贡献，高风险 |
| Issue 响应速度 | 8/8 | 0.6 天 | 处理极快 |
| PR 合并率 | 4/6 | 66.0% | 良好 |
| 活跃贡献者 | 4/4 | 100 人 | 社区生态健康 |
| Release 稳定性 | 2/2 | 0.2 个月前 | 维护活跃 |

**结论**：链路完整跑通，评分逻辑与 PROJECT_PLAN §7.3 一致。

#### Phase 1.1 剩余问题

- Windows 控制台 GBK 编码导致中文输出乱码（代码本身无问题，终端编码设置问题）
- Reporter 进度条字符已改用 `#` `-` 兼容 GBK

### Phase 1.2：抽出 github-mcp server（已完成 ✅）

**决策回顾**：MCP Server 职责尽量"薄"——只做协议转换 + GitHub API 调用，缓存留在上层。

#### 新增/修改的文件

| 文件 | 职责 | 行数 |
|------|------|------|
| `mcp-servers/github-mcp/server.py` | MCP Server 主进程（stdio 模式，6 个 tools） | 211 |
| `mcp-servers/github-mcp/pyproject.toml` | 独立包配置，入口命令 `github-mcp` | 18 |
| `backend/app/mcp/client.py` | MCP Client 封装（生命周期管理 + JSON 解析） | 118 |
| `backend/app/services/mcp_github_service.py` | 兼容层：接口同 `github_service.py`，内部走 MCP | 47 |
| `backend/app/agents/community_agent.py` | 修改 1 行 import，切到 MCP 版本 | 改 1 行 |
| `backend/requirements.txt` | 启用 `mcp>=1.0.0` 依赖 | 改 1 行 |

#### MCP 链路验证

```
CLI → orchestrator → community_agent → mcp_github_service
                                              ↓
                                    GitHubMCPClient (stdio)
                                              ↓
                                    github-mcp Server (子进程)
                                              ↓
                                          GitHub API
```

- `list_tools()` 返回 6 个 tool，名称和描述正确
- `call_tool("get_repo_metadata", ...)` 返回真实数据（python-poetry/poetry，34274 stars）
- CLI 端到端分析结果与 Phase 1.1 完全一致（总分 18/30）

### Phase 1.3：代码质量 Agent（已完成 ✅）

**决策回顾**：
- code-analysis-mcp 原本计划用 subprocess 调用 semgrep/radon 命令行，但 Windows 上 MCP stdio + subprocess 有深层死锁问题
- 最终方案：radon 用 Python API（`cc_visit`），安全扫描用 AST 静态分析（简化版），避开命令行调用
- filesystem-mcp 保持命令行调用（git clone），因为需要在独立进程中执行

#### 新增文件

| 文件 | 职责 | 行数 |
|------|------|------|
| `mcp-servers/filesystem-mcp/server.py` | MCP Server：仓库克隆、文件读取、目录遍历 | 178 |
| `mcp-servers/code-analysis-mcp/server.py` | MCP Server：radon 复杂度分析 + AST 安全扫描 | 212 |
| `backend/app/mcp/client.py` | 重构为基类模式，新增 FilesystemMCPClient、CodeAnalysisMCPClient | 115 |
| `backend/app/scoring/quality.py` | 代码质量四项指标评分规则 | 189 |
| `backend/app/agents/quality_agent.py` | Agent 主体：克隆 → 采集 → 评分 → 输出 | 132 |
| `backend/app/agents/orchestrator.py` | 新增 quality_agent 调度 | 改 |
| `backend/app/agents/reporter.py` | 新增 quality 维度显示 | 改 |
| `backend/requirements.txt` | 启用 semgrep、radon 依赖 | 改 |

#### 端到端验证结果（psf/requests）

```bash
$ python -m app.cli analyze https://github.com/psf/requests
总分 36/55 [#############-------] 65.5%

[community]  22/30 (73.3%)
  Bus Factor: 6/10 (3)
  Issue 响应: 8/8 (0.1 天)
  PR 合并率: 2/6 (34.0%)
  活跃贡献者: 4/4 (100 人)
  Release: 2/2 (0.0 个月前)

[quality]    14/25 (56.0%)
  测试覆盖率: 6/8  (有 tests + CI)
  静态分析漏洞: 7/7 (0 高危)
  文档完整度: 3/5  (2/4 项)
  代码复杂度: 5/5  (平均 2.84，优秀)
```

#### 遇到的坑与解决

| 问题 | 原因 | 解决 |
|------|------|------|
| git clone 网络超时 | GitHub 访问慢 | `git config --global http.https://github.com.proxy socks5://127.0.0.1:10808` |
| WinError 5 拒绝访问 | `.git` 文件只读，`shutil.rmtree` 删不掉 | `os.chmod(path, stat.S_IWRITE)` 改权限后删除 |
| MCP stdio 卡死 | git 子进程继承 Server 的 stdin | `subprocess.run(stdin=subprocess.DEVNULL, ...)` |
| 安全扫描 8 个误报 | 扫描了 `tests/` 目录 | `_EXCLUDE_DIRS` 添加 `tests`, `test` |
| radon `-a` 抑制 JSON | Windows 上 radon `-a` 参数不兼容 JSON 输出 | 去掉 `-a`，自己计算平均值 |
| semgrep subprocess 死锁 | Windows 上 MCP stdio + subprocess 冲突 | 改用 Python AST 自研扫描（简化版） |

### Phase 1.4：安全分析 Agent（已完成 ✅）

**决策回顾**：
- 原本计划把 SBOM / OSV 分散在 github-mcp 和 osv-mcp，但用户提出 Security Agent 应该只依赖一个 Server
- 最终方案：**osv-mcp 成为"安全数据采集中心"**，内部同时调用 GitHub SBOM API + OSV API + GitHub License API，Security Agent 只需启动一个 OSVMCPClient
- 直接 HTTP 调用重构为 MCP 模式：security_service.py 从 ~500 行直接 HTTP 逻辑简化为 ~40 行 MCP Client 调用，HTTP 逻辑全部下沉到 osv-mcp Server

#### 新增文件

| 文件 | 职责 | 行数 |
|------|------|------|
| `mcp-servers/osv-mcp/server.py` | MCP Server：SBOM 提取 + OSV 漏洞查询 + 许可证获取 | 350 |
| `mcp-servers/osv-mcp/pyproject.toml` | 独立包配置 | 18 |
| `mcp-servers/osv-mcp/__init__.py` | 包标记 | 1 |
| `backend/app/scoring/security.py` | 安全评分引擎（CVE 记录 / 依赖漏洞 / 许可证 / 响应速度） | 285 |
| `backend/app/agents/security_agent.py` | Agent 主体：采集 → 评分 → 输出 | 115 |
| `backend/app/services/security_service.py` | MCP 模式安全数据采集（通过 OSVMCPClient） | 40 |
| `backend/app/mcp/client.py` | 新增 OSVMCPClient | +3 行 |
| `backend/app/agents/orchestrator.py` | 新增 security_agent 调度，总分 55→80 | 改 |
| `backend/app/agents/reporter.py` | 新增 security 维度显示 | 改 |

#### 端到端验证结果（pallets/click）

```bash
$ python -m app.cli analyze https://github.com/pallets/click
总分 33/80 [########------------] 41.2%

[community]  14/30 (46.7%)
  Bus Factor: 0/10 (2)
  Issue 响应: 8/8 (0.0 天)
  PR 合并率: 0/6 (21.0%)
  活跃贡献者: 4/4 (100 人)
  Release: 2/2 (0.8 个月前)

[quality]    14/25 (56.0%)
  测试覆盖率: 6/8
  静态分析漏洞: 0/7 (3 高危)
  文档完整度: 3/5
  代码复杂度: 5/5 (3.21)

[security]    5/25 (20.0%)
  CVE 记录: 0/10 (46高危, 2中危, 19低危)
  依赖漏洞: 0/8 (122 个)
  许可证风险: 5/5 (BSD-3-Clause)
  安全响应速度: 0/2 (平均 1873 天)
```

#### 遇到的坑与解决

| 问题 | 原因 | 解决 |
|------|------|------|
| OSV 400 Bad Request | SBOM 返回了 `githubactions` 生态系统，OSV 不认识 | 添加 `_OSV_SUPPORTED_ECOSYSTEMS` 白名单过滤 |
| 漏洞 severity 全为 UNKNOWN | OSV `querybatch` 只返回 `id` + `modified`，severity 在详情端点 | 两阶段查询：querybatch → 并行 `GET /v1/vulns/{id}` |
| 输入验证错误 | `version` 字段为 `None`，JSON Schema 要求 `string` | Schema 改为 `{"type": ["string", "null"]}` |
| osv-mcp 缺少 pyproject.toml | 只有 server.py，和其他 Server 目录结构不一致 | 补全 `pyproject.toml` + `__init__.py` |

#### MCP 架构统一

4 个 Server 目录结构完全一致，职责单一：

| Server | 职责 | 使用方 |
|--------|------|--------|
| github-mcp | GitHub 元数据 | Community Agent |
| filesystem-mcp | 文件系统操作 | Quality Agent |
| code-analysis-mcp | 静态分析 | Quality Agent |
| osv-mcp | 安全数据采集 | Security Agent |

### Phase 1.5：技术演进 Agent + Orchestrator 并发调度（待开始）

- [ ] `backend/app/scoring/evolution.py` — 技术演进评分引擎（0-20 分）
- [ ] `backend/app/agents/evolution_agent.py` — 技术演进 Agent
- [ ] Orchestrator 升级为 `asyncio.gather` 并发调度 4 个 Agent
- [ ] 加入综合评级计算（A+/A/B+/B/C/D）
- [ ] 总分覆盖 100/100 分

---

## 环境注意事项（重要）

### 宿主机 vs Docker 环境隔离

**关键事实**：宿主机上 `pip install` 安装的包，Docker 容器内**默认看不到**。

```
宿主机 Windows Python
  └── pip install mcp semgrep radon  → 只在这里

Docker 容器 Linux Python
  └── 只认 Dockerfile / requirements.txt 构建时装的包
```

**当前状态**：
- 宿主机已安装：`mcp`、`httpx`（Phase 1.2 开发时装的）
- Docker 镜像里有：`fastapi`、`sqlalchemy`、`redis` 等（Phase 0 构建时装入的）
- **Docker 里没有**：`mcp` — Phase 1.2 代码在 Docker 内运行会报 `ModuleNotFoundError`

**开发策略**：
- **Phase 1 阶段**：宿主机开发为主，快速迭代，每次 Phase 完成后再统一更新 requirements.txt + 重建镜像
- **Phase 2 及之后**：进入 Docker 开发，确保和生产环境一致

**重建 Docker 镜像命令**：
```bash
# 每完成一个 Phase，更新 requirements.txt 后执行
docker-compose -f docker-compose.dev.yml build api
docker-compose -f docker-compose.dev.yml up -d
```

### Phase 1.4 需要的新依赖

```bash
# 宿主机安装（开发用）
# osv-mcp 依赖同 github-mcp：mcp + httpx，已安装

# 已确保 requirements.txt 包含：
mcp>=1.0.0
httpx>=0.27.0
```

---

## 下一个具体动作

**Phase 1.5：技术演进 Agent + Orchestrator 并发调度**

1. `backend/app/scoring/evolution.py` — 技术演进评分引擎（0-20 分）
   - 发布频率评分
   - 技术栈更新评分
   - Breaking Change 评分
   - 竞品对比评分（简化版）
2. `backend/app/agents/evolution_agent.py` — 技术演进 Agent
3. Orchestrator 串行改并行：`asyncio.gather(community, quality, security, evolution)`
4. 综合评级算法：总分 → A+/A/B+/B/C/D
5. 4 个热门项目基准测试

---

## Phase 2 及之后（概述）

详见 `PROJECT_PLAN.md` §10，简要：

| 阶段 | 目标 | 状态 |
|------|------|------|
| Phase 2 | Web 平台 + Celery 异步任务 + React 前端 | 待开始 |
| Phase 3 | Agent 接入 LLM 推理 + ChromaDB RAG 校准 | 待开始 |
| Phase 4 | 持续监控 + 指标趋势 + 异常预警 | 待开始 |
| Phase 5 | Railway/Render 部署 + 公开站点 | 待开始 |
