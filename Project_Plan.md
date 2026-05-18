# 开源项目深度尽调 Agent — 构建方案

> 版本：v1.0  
> 日期：2026-05-15  
> 状态：规划中

---

## 1. 项目概述

**项目名称**：`osscout`（Open Source Due Diligence）  
**定位**：面向技术团队的开源项目自动化尽调平台  
**核心目标**：输入一个 GitHub 仓库地址，输出一份覆盖社区健康、代码质量、安全风险、技术演进四个维度的结构化尽调报告，并给出明确的推荐评级。

### 1.1 为什么做这个项目

技术团队选型开源库时面临的信息不对称：
- Stars 数不等于维护质量（如 `left-pad` 事件前 stars 很高）
- 安全问题往往在出事前几个月已有征兆（依赖老化、核心维护者退出）
- 人工尽调耗时（一个项目需要 2-4 小时），无法覆盖候选库清单
- 现有工具（OpenSSF Scorecard、Snyk）偏规则评分，缺乏推理和上下文判断

### 1.2 核心差异化

| 现有方案 | 本项目 |
|---------|--------|
| OpenSSF Scorecard：静态规则评分 | Agent 推理 + 动态分析 + 可解释判断 |
| Snyk/Dependabot：仅安全扫描 | 四维综合评估 + 趋势预判 |
| GitHub Insights：原始数据统计 | 结构化尽调报告 + 竞品对比 + 明确建议 |
| 人工尽调：耗时、主观 | 自动化、可规模化、指标可追溯 |

---

## 2. 系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              用户交互层                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                      │
│  │   Web UI     │  │   CLI Tool   │  │   API Server │                      │
│  │  (React)     │  │  (Python)    │  │  (FastAPI)   │                      │
│  └──────────────┘  └──────────────┘  └──────────────┘                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            协调层 (Orchestrator)                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  任务拆解 → 并行调度 Agent → 冲突消解 → 综合报告生成                        ││
│  │  (ReAct Loop + Plan-Execute Pattern)                                     ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          ▼                         ▼                         ▼
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│   Multi-Agent    │    │   MCP 工具层      │    │   RAG 知识层      │
│   分析引擎        │    │                  │    │                  │
│                  │    │  github-mcp      │    │  ChromaDB        │
│ ┌──────────────┐ │    │  filesystem-mcp  │    │  历史报告库       │
│ │社区健康Agent │ │    │  search-mcp      │    │  评估方法论       │
│ └──────────────┘ │    │  osv-mcp         │    │  行业基准数据     │
│ ┌──────────────┐ │    │  code-analysis   │    │  失败案例库       │
│ │代码质量Agent │ │    │                  │    │                  │
│ └──────────────┘ │    └──────────────────┘    └──────────────────┘
│ ┌──────────────┐ │
│ │安全分析Agent │ │
│ └──────────────┘ │
│ ┌──────────────┐ │
│ │技术演进Agent │ │
│ └──────────────┘ │
└──────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            基础设施层                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │  PostgreSQL  │  │    Redis     │  │   Celery     │  │   Docker     │    │
│  │  (主数据库)   │  │  (缓存/限频)  │  │  (任务队列)   │  │  (容器编排)   │    │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流

```
1. 用户提交 repo URL
2. Orchestrator 解析仓库标识（owner/repo）
3. 并行触发：
   a. GitHub MCP 采集元数据（stars/forks/issues/PRs/commits/contributors/releases）
   b. Filesystem MCP 克隆仓库到本地
   c. OSV MCP 查询已知漏洞
4. 数据就绪后，并行调度 4 个分析 Agent
5. 各 Agent 产出结构化分析结果
6. Orchestrator 汇总，RAG 检索历史基准进行校准
7. 综合报告 Agent 生成最终尽调报告
8. 报告持久化，推送给用户
```

---

## 3. 技术选型

### 3.1 技术栈总览

| 层级 | 技术选型 | 选型理由 |
|-----|---------|---------|
| 编程语言 | Python 3.12 | Agent 生态成熟，异步支持好 |
| 后端框架 | FastAPI | 原生异步、自动文档、类型安全 |
| Agent 编排 | 手写 ReAct Loop | 避免 LangChain/LangGraph 的过度抽象，核心逻辑可控，面试可深入讲解 |
| LLM | Claude 3.5 Sonnet / GPT-4o | 推理能力足够，成本可控 |
| MCP 协议 | 官方 Python SDK (`mcp`) | 标准化工具接入 |
| RAG 向量库 | ChromaDB | 轻量、本地可运行、无需外部依赖 |
| Embedding | sentence-transformers (`all-MiniLM-L6-v2`) | 本地推理、无 API 成本 |
| 主数据库 | PostgreSQL 16 | 关系型数据、JSONB 支持半结构化指标 |
| 缓存 | Redis 7 | API 限频缓存、热点数据、任务状态 |
| 任务队列 | Celery + Redis Broker | 成熟稳定，支持定时任务（巡检） |
| 静态分析 | Semgrep + radon | 代码漏洞扫描 + 复杂度分析 |
| 前端 | React 18 + TailwindCSS + Recharts | 轻量、指标可视化 |
| 部署 | Docker Compose + Railway/Render | 低成本上线，可迁移至 K8s |

### 3.2 关键依赖

```
# 核心框架
fastapi==0.115.*
uvicorn[standard]
pydantic==2.10.*
pydantic-settings

# Agent & LLM
anthropic>=0.40.0
openai>=1.60.0
httpx>=0.27.0

# MCP
mcp>=1.0.0

# RAG
chromadb>=0.6.0
sentence-transformers>=3.0.0

# 数据库 & 缓存
sqlalchemy[asyncio]>=2.0.0
asyncpg>=0.30.0
alembic>=1.14.0
redis>=5.0.0

# 任务队列
celery[redis]>=5.4.0

# 代码分析
semgrep>=1.100.0
radon>=6.0.0
pygithub>=2.5.0

# 工具
python-dotenv
structlog
pytest
pytest-asyncio
```

### 3.3 为什么不用 LangChain/LangGraph

本项目刻意避开 LangChain 生态，原因如下：

1. **过度抽象**：LangChain 的 `AgentExecutor` 隐藏了核心的 ReAct 循环，不利于理解和调试
2. **面试深度**：手写 Agent 循环能展示对 LLM 交互模式的真正理解，而非框架调用
3. **可控性**：自定义的 Orchestrator 可以精确控制并发策略、错误处理、重试逻辑
4. **MCP 整合**：MCP 是新的标准化协议，直接对接比通过 LangChain 的封装更干净

---

## 4. Multi-Agent 设计

### 4.1 Agent 角色定义

#### 社区健康度 Agent（Community Health Agent）

**输入**：GitHub 仓库元数据（contributors, issues, PRs, commits, releases）  
**输出**：社区健康度评分 + 关键发现列表 + 风险标记

**分析维度**：
| 指标 | 计算方法 | 阈值 |
|-----|---------|------|
| Bus Factor | 贡献度 >50% 的最小贡献者数 | <3 高风险 |
| Contributor 留存率 | 6 个月前首次贡献者中仍在活跃的比例 | <30% 风险 |
| Issue 响应中位数 | 首次回复时间的中位数 | >7 天风险 |
| PR 合并率 | 合并 PR / 提交 PR 总数 | <50% 风险 |
| Release 频率 | 最近 12 个月 release 数 | <2 次风险 |
| 活跃度趋势 | 最近 90 天 commits 同比变化 | 下降 >30% 风险 |

**LLM 推理任务**：
- 判断社区是否健康（不是简单阈值，而是综合判断）
- 识别 "即将放弃维护" 的早期信号
- 对比同类型项目的社区活跃度

#### 代码质量 Agent（Code Quality Agent）

**输入**：本地克隆的仓库代码  
**输出**：代码质量评分 + 具体问题列表

**分析维度**：
| 指标 | 工具 | 阈值 |
|-----|------|------|
| 测试覆盖率 | 读取 CI 产物或本地运行 pytest coverage | <50% 风险 |
| 代码复杂度 | radon（平均圈复杂度）| >15 风险 |
| 静态分析漏洞 | Semgrep（高危规则集）| >0 高危即风险 |
| 文档完整度 | 检查 README/API 文档/CHANGELOG | 缺失即扣分 |
| 类型覆盖率 | TypeScript/Python type hints 比例 | <60% 提醒 |

#### 安全分析 Agent（Security Agent）

**输入**：依赖清单（package.json/requirements.txt/go.mod）、OSV 查询结果  
**输出**：安全评分 + 漏洞清单 + 许可证风险评估

**分析维度**：
| 指标 | 来源 | 阈值 |
|-----|------|------|
| 已知 CVE | OSV / GitHub Security Advisories | 每个高危 -5 分 |
| 依赖漏洞 | Snyk API / Dependabot alerts | 每个 -3 分 |
| 许可证风险 | `licensee` / GitHub API | GPL/AGPL 传染性风险 |
| 安全响应速度 | CVE 披露到补丁发布的平均天数 | >30 天风险 |

#### 技术演进 Agent（Evolution Agent）

**输入**：版本历史、技术栈数据、竞品对比数据  
**输出**：技术演进评分 + 趋势判断

**分析维度**：
| 指标 | 计算方法 | 阈值 |
|-----|---------|------|
| 版本发布频率 | 最近 12 个月 release 数 / 12 | <0.5/月 风险 |
| Breaking Change 密度 | 每个 major 版本的 breaking 变更数 | >10 风险 |
| 技术栈老化度 | 核心依赖的最新版本差距 | >2 个大版本 风险 |
| 竞品对比活跃度 | 与 2-3 个竞品项目的 star/issue 增长对比 | 显著落后 风险 |

### 4.2 Orchestrator 协调逻辑

```python
class DueDiligenceOrchestrator:
    async def analyze(self, repo_url: str) -> DueDiligenceReport:
        # 1. 解析仓库信息
        owner, repo = parse_repo_url(repo_url)

        # 2. 并行数据采集
        metadata, local_repo, security_data = await asyncio.gather(
            self.collect_github_metadata(owner, repo),
            self.clone_and_analyze_code(owner, repo),
            self.collect_security_data(owner, repo),
        )

        # 3. 并行调度 4 个分析 Agent
        results = await asyncio.gather(
            self.community_agent.analyze(metadata),
            self.quality_agent.analyze(local_repo),
            self.security_agent.analyze(security_data),
            self.evolution_agent.analyze(metadata, local_repo),
        )

        # 4. RAG 校准：检索历史基准和类似案例
        calibration = await self.rag_calibrate(results)

        # 5. 综合报告生成
        report = await self.synthesis_agent.generate(
            results, calibration
        )

        return report
```

---

## 5. MCP 工具层

### 5.1 工具清单

| MCP Server | 协议类型 | 功能 | 自研/第三方 |
|-----------|---------|------|-----------|
| `github-mcp` | stdio | 读取 GitHub API 数据（rate limit 处理） | 自研 |
| `filesystem-mcp` | stdio | 克隆仓库、读取文件、运行本地命令 | 自研 |
| `search-mcp` | stdio | 搜索项目相关新闻、社区讨论 | 自研（接入 Serper/Bing） |
| `osv-mcp` | stdio | 查询开源漏洞数据库 | 自研 |
| `code-analysis-mcp` | stdio | 运行 Semgrep、radon、计算覆盖率 | 自研 |

### 5.2 MCP Server 接口设计（以 github-mcp 为例）

```typescript
// tools
- get_repo_metadata(owner: string, repo: string) -> RepoMetadata
- list_contributors(owner: string, repo: string, limit: number) -> Contributor[]
- list_issues(owner: string, repo: string, state: string, since: string) -> Issue[]
- list_pull_requests(owner: string, repo: string, state: string) -> PR[]
- list_releases(owner: string, repo: string) -> Release[]
- get_commit_activity(owner: string, repo: string) -> WeeklyCommitActivity[]  // 实际调用 /stats/participation 端点，避免 /stats/commit_activity 的 202 异步计算问题
```

### 5.3 GitHub API 限频策略

- 认证用户：5000 req/hour
- 策略：Redis 缓存热点数据（24h TTL），优先读取缓存
- 并发控制：最多 10 个并行请求，超出排队等待

---

## 6. RAG 知识层

### 6.1 知识库内容

| 类别 | 内容 | 更新频率 |
|-----|------|---------|
| 评估方法论 | OpenSSF Scorecard 标准、CNCF 毕业标准、Google SRE 最佳实践 | 手动 |
| 行业基准 | 各类型项目（前端框架、后端框架、工具库）的平均指标 | 每月计算 |
| 历史报告 | 过往尽调报告（脱敏后） | 每次分析后 |
| 失败案例 | left-pad、Faker.js、colors.js、event-stream 等事件分析 | 手动 |
| 竞品映射 | 常见技术选型场景下的竞品关系（如 Next.js vs Nuxt） | 手动 |

### 6.2 RAG 使用场景

1. **基准校准**："前端框架的平均 PR 合并率是多少？" → 用于判断目标项目是否达标
2. **风险预判**："Bus Factor < 3 的项目历史上发生了什么？" → 检索失败案例
3. **评估方法引用**："OpenSSF Scorecard 对安全更新的标准是什么？" → 检索方法论
4. **报告生成**："生成一份类似上季度评估 React 的报告结构" → 检索历史报告模板

### 6.3 文档分块策略

- 方法论文档：按章节分块（512 tokens）
- 历史报告：按"项目概述 + 各维度分析 + 结论"分块
- 失败案例：按事件分块（背景 → 征兆 → 影响 → 教训）

---

## 7. 量化评分体系

### 7.1 总分结构（100 分制）

```
综合评级
├── 社区健康度（30 分）
├── 代码质量（25 分）
├── 安全评分（25 分）
└── 技术演进（20 分）
```

### 7.2 评级标准

| 总分 | 评级 | 含义 |
|-----|------|------|
| 90-100 | A+ | 强烈推荐，项目非常健康 |
| 80-89 | A | 推荐，可以安全使用 |
| 70-79 | B+ | 谨慎推荐，存在可接受的小风险 |
| 60-69 | B | 可用，但需要关注特定风险点 |
| 50-59 | C | 谨慎使用，存在明显风险 |
| <50 | D | 不建议使用 |

### 7.3 各维度评分细则

#### 社区健康度（30 分）

| 指标 | 满分 | 评分规则 |
|-----|------|---------|
| Bus Factor | 10 | ≥5 得 10 分；3-4 得 6 分；<3 得 0 分 |
| Issue 响应速度 | 8 | 中位数 <1 天得 8 分；<3 天得 6 分；<7 天得 3 分；≥7 天得 0 分 |
| PR 合并率 | 6 | ≥70% 得 6 分；50-69% 得 4 分；30-49% 得 2 分；<30% 得 0 分 |
| 活跃贡献者 | 4 | ≥10 人得 4 分；5-9 人得 2 分；<5 人得 0 分 |
| Release 稳定性 | 2 | 6 个月内有 release 且频率稳定得 2 分 |

#### 代码质量（25 分）

| 指标 | 满分 | 评分规则 |
|-----|------|---------|
| 测试覆盖率 | 8 | ≥80% 得 8 分；60-79% 得 5 分；40-59% 得 2 分；<40% 得 0 分 |
| 静态分析 | 7 | 0 高危 + 0 中危得 7 分；有高危得 0 分；有中危酌情扣分 |
| 文档完整度 | 5 | README + API 文档 + CONTRIBUTING + CHANGELOG 齐全得 5 分 |
| 代码复杂度 | 5 | 平均圈复杂度 <10 得 5 分；10-15 得 3 分；>15 得 0 分 |

#### 安全评分（25 分）

| 指标 | 满分 | 评分规则 |
|-----|------|---------|
| CVE 记录 | 10 | 近 1 年无 CVE 得 10 分；有低危 -2 分/个；中危 -5 分/个；高危 -10 分/个 |
| 依赖漏洞 | 8 | 0 漏洞得 8 分；每 1 个漏洞 -2 分 |
| 许可证风险 | 5 | MIT/Apache/BSD 得 5 分；GPL 家族得 2 分；无许可证得 0 分 |
| 安全响应速度 | 2 | 历史 CVE 平均响应 <7 天得 2 分；<30 天得 1 分 |

#### 技术演进（20 分）

| 指标 | 满分 | 评分规则 |
|-----|------|---------|
| 发布频率 | 6 | 每月 ≥1 次得 6 分；每 2 月 1 次得 4 分；每季度 1 次得 2 分 |
| 技术栈更新 | 6 | 核心依赖均最新大版本得 6 分；落后 1 个版本得 4 分；落后 ≥2 得 0 分 |
| Breaking Change | 4 | 可控且有文档得 4 分；频繁无文档得 0 分 |
| 竞品对比 | 4 | 活跃度处于前 30% 得 4 分；前 50% 得 2 分；后 50% 得 0 分 |

### 7.4 可验证的量化指标（面试重点）

作为项目 owner，你应该能说出这些数字：

| 指标 | 目标 | 验证方法 |
|-----|------|---------|
| 分析完成时间 | <2 分钟（热点缓存）/ <5 分钟（冷启动） | 计时 |
| 评分与专家一致性 | Pearson r > 0.85 | 与 3 位资深工程师的评分对比 |
| 风险预判准确率 | 提前 3-6 个月标记出衰落项目，准确 >70% | 回溯验证 |
| 报告可用性评分 | 用户认为报告"有用"的比例 >80% | 问卷 |
| API 可用性 | >99% | 监控 |

---

## 8. 数据模型

### 8.1 核心实体

```python
# 仓库基础信息
class Repository(Base):
    id: int
    owner: str
    repo: str
    url: str
    description: str | None
    primary_language: str | None
    created_at: datetime
    updated_at: datetime
    star_count: int
    fork_count: int
    open_issue_count: int
    license: str | None

# 分析任务
class AnalysisTask(Base):
    id: int
    repo_id: int
    status: TaskStatus  # pending / running / completed / failed
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None

# 尽调报告
class DueDiligenceReport(Base):
    id: int
    task_id: int
    repo_id: int
    overall_score: int  # 0-100
    overall_rating: str  # A+/A/B+/B/C/D
    community_score: int
    quality_score: int
    security_score: int
    evolution_score: int
    key_findings: list[Finding]  # JSONB
    recommendations: list[str]  # JSONB
    raw_results: dict  # JSONB，保留各 Agent 原始输出
    created_at: datetime

# 指标历史（用于趋势分析）
class MetricHistory(Base):
    id: int
    repo_id: int
    metric_name: str  # e.g. "bus_factor", "issue_response_median"
    metric_value: float
    recorded_at: datetime
```

### 8.2 时序数据分析

每个仓库的指标历史形成时序数据，支持：
- 趋势分析（"这个项目在过去 6 个月的 Bus Factor 变化"）
- 预警触发（"某指标跌破阈值"）
- 对比分析（"与同类项目的历史轨迹对比"）

---

## 9. API 设计

### 9.1 核心接口

```
POST   /api/v1/analyze              # 提交分析任务
GET    /api/v1/tasks/{task_id}      # 查询任务状态
GET    /api/v1/reports/{report_id}  # 获取尽调报告
GET    /api/v1/repos/{repo_id}/history  # 获取历史指标趋势
POST   /api/v1/compare              # 多项目对比分析
GET    /api/v1/repos/{repo_id}/reports  # 获取某仓库的所有报告
```

### 9.2 分析任务接口

```http
POST /api/v1/analyze
Content-Type: application/json

{
  "repo_url": "https://github.com/vercel/next.js",
  "options": {
    "include_code_analysis": true,
    "include_security_scan": true,
    "compare_with": ["nuxt/nuxt", "remix-run/remix"]
  }
}

Response: 202 Accepted
{
  "task_id": "task_abc123",
  "status": "pending",
  "estimated_seconds": 120
}
```

### 9.3 报告接口

```http
GET /api/v1/reports/report_xyz789

Response: 200 OK
{
  "repo": {
    "owner": "vercel",
    "repo": "next.js",
    "url": "https://github.com/vercel/next.js"
  },
  "overall": {
    "score": 92,
    "rating": "A+",
    "summary": "强烈推荐使用"
  },
  "dimensions": {
    "community": { "score": 28, "max": 30, "findings": [...] },
    "quality": { "score": 23, "max": 25, "findings": [...] },
    "security": { "score": 25, "max": 25, "findings": [...] },
    "evolution": { "score": 16, "max": 20, "findings": [...] }
  },
  "comparison": {
    "vs_nuxt": { "next.js": 92, "nuxt": 85 },
    "vs_remix": { "next.js": 92, "remix": 78 }
  },
  "recommendations": [
    "项目非常健康，社区活跃，可放心使用",
    "关注 v14 到 v15 的迁移成本"
  ],
  "created_at": "2026-05-15T10:30:00Z"
}
```

---

## 10. 开发路线图

### Phase 0：基础设施（Week 1）

- [ ] 项目脚手架搭建（FastAPI + SQLAlchemy + Alembic）
- [ ] Docker Compose 开发环境
- [ ] 数据库 Schema 设计与迁移
- [ ] GitHub API 封装（带限频和缓存）
- [ ] 基础日志和错误处理

### Phase 1：MVP — 单项目分析（Week 2-3）

**目标**：CLI 运行，输入 repo URL，输出文本报告

- [ ] github-mcp server 实现
- [ ] filesystem-mcp server 实现（仓库克隆）
- [ ] 社区健康度 Agent（纯规则评分，无 LLM）
- [ ] 代码质量 Agent（Semgrep + radon 集成）
- [ ] 安全分析 Agent（OSV 查询 + 许可证检查）
- [ ] 基础 Orchestrator（串行执行）
- [ ] 文本格式报告生成
- [ ] 5 个热门项目的基准测试

**验收标准**：
- 能完整分析 `vercel/next.js`、`python-poetry/poetry` 等项目
- 分析时间 <5 分钟
- 输出包含 4 个维度的评分和关键发现

### Phase 2：V1 — Web 平台 + 多项目（Week 4-5）

**目标**：Web UI + API + 异步任务 + 数据持久化

Phase 2 拆分为 5 个小阶段递进执行：

#### Phase 2.1：REST API 骨架 + 数据库持久化

- [x] `POST /api/v1/analyze` — 提交分析任务，返回 task_id
- [x] `GET /api/v1/tasks/{task_id}` — 查询任务状态
- [x] `GET /api/v1/reports/{report_id}` — 获取报告详情
- [x] 分析结果写入 PostgreSQL（AnalysisTask / DueDiligenceReport）
- [x] **此阶段任务同步执行**（类似 CLI），接口已设计成异步风格

**验收标准**：
- curl/Postman 可完整调用：提交 → 查询状态 → 获取报告
- 数据能在 DataGrip 中查到

#### Phase 2.2：Celery 异步任务队列

- [x] Celery 应用配置（Redis broker）
- [x] `run_due_diligence` 异步任务
- [x] `/api/v1/analyze` 改为"提交 Celery 任务 + 立即返回 task_id"
- [ ] docker-compose.dev.yml 启用 worker 服务（Phase 5 统一配置）

**验收标准**：
- 提交任务后立即返回，不阻塞 HTTP 响应
- worker 日志可见任务执行过程
- 超大仓库分析不触发 HTTP 超时

#### Phase 2.3：多项目对比 + 历史趋势接口

- [x] `POST /api/v1/compare` — 批量提交多个仓库，返回对比报告
- [x] `GET /api/v1/repos/{id}/history` — 某仓库历次分析的指标趋势
- [x] 报告列表查询（分页）

**验收标准**：
- 支持同时对比 2-3 个仓库
- 历史趋势接口返回时序数据

#### Phase 2.4：React 前端骨架

- [x] HTTP 客户端封装（Axios + TanStack Query）
- [x] 首页：提交分析表单 + 任务状态轮询
- [x] 报告详情页：四维评分展示
- [x] 报告列表页：分页表格
- [x] 路由配置（React Router v7）
- [x] Vite dev server 代理配置（解决 CORS）

**技术栈**：Vite 6 + React 19 + TypeScript 5.8 + TailwindCSS v4 + shadcn/ui + React Router v7 + TanStack Query v5

**验收标准**：
- 浏览器可提交分析、查看报告
- 前端调用真实 API，非 mock 数据

#### Phase 2.5：前端可视化

- [ ] 评分仪表盘组件（环形图）
- [ ] 各维度评分条形图
- [ ] 对比页面（并排展示多项目）
- [ ] 仓库列表页（历史分析记录）

**验收标准**：
- Web UI 可浏览报告、查看可视化评分
- 对比页面并排展示多项目数据

**Phase 2 总体验收标准**：
- 完整链路：前端提交 → API 接收 → Celery 执行 → 数据库存储 → 前端展示
- 支持批量提交分析任务
- API 响应时间 <200ms（缓存命中）

### Phase 3：V2 — Agent 智能化 + RAG（Week 6-7）

**目标**：引入 LLM 推理和知识库

- [ ] LLM Client 封装（Claude + GPT 双后端）
- [ ] 4 个分析 Agent 接入 LLM 推理
- [ ] Orchestrator 升级为并行 + ReAct Loop
- [ ] ChromaDB 向量库搭建
- [ ] 评估方法论文档入库
- [ ] 历史报告入库（脱敏）
- [ ] RAG 校准模块实现
- [ ] 综合报告 Agent（可解释性推理）

**验收标准**：
- Agent 能给出超越规则的推理判断（如 "Bus Factor=2 是高风险，因为历史案例显示..."）
- RAG 检索准确率 >80%

### Phase 4：V3 — 持续监控 + 预警（Week 8-9）

**目标**：从"一次性分析"升级为"持续监控"

- [ ] 定时巡检任务（Celery Beat）
- [ ] 指标趋势分析
- [ ] 异常检测（指标突变预警）
- [ ] 邮件/Webhook 通知
- [ ] 用户关注列表（watch list）
- [ ] 公开报告页面（可分享链接）
- [ ] 性能优化（热点项目预缓存）

**验收标准**：
- 能提前发现项目健康度恶化（回溯验证）
- 支持 100+ 项目的定时巡检

### Phase 5：上线与推广（Week 10+）

- [ ] Railway/Render 部署
- [ ] 公开演示站点
- [ ] 100 个热门项目的基准数据集发布
- [ ] 技术博客/Show HN 发布
- [ ] 收集用户反馈迭代

---

## 11. 部署方案

### 11.1 开发环境

```bash
# 一键启动
docker-compose -f docker-compose.dev.yml up

# 服务列表
- api: FastAPI 开发服务器 (端口 8000)
- web: React 开发服务器 (端口 3000)
- db: PostgreSQL 16 (端口 5432)
- redis: Redis 7 (端口 6379)
- worker: Celery Worker
```

### 11.2 生产环境

```bash
# 生产部署
docker-compose -f docker-compose.yml up -d
```

| 组件 | 资源配置 | 备注 |
|-----|---------|------|
| API Server | 1 vCPU / 512MB | 无状态，可水平扩展 |
| Celery Worker | 1 vCPU / 1GB | 分析任务执行 |
| PostgreSQL | 1 vCPU / 512MB | 可迁移至 RDS |
| Redis | 共享 256MB | 可迁移至 ElastiCache |
| 预估月成本 | $20-30 | Railway/Render 方案 |

### 11.3 环境变量

```env
# 数据库
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/osscout

# Redis
REDIS_URL=redis://localhost:6379/0

# LLM
ANTHROPIC_API_KEY=sk-...
OPENAI_API_KEY=sk-...
DEFAULT_LLM_PROVIDER=anthropic
DEFAULT_LLM_MODEL=claude-3-5-sonnet-20241022

# GitHub
GITHUB_TOKEN=ghp_...  # 提高 API 限频

# 搜索
SERPER_API_KEY=...  # Google Search API

# 应用
DEBUG=false
LOG_LEVEL=INFO
ANALYSIS_TIMEOUT=300
```

---

## 12. 项目目录结构

```
osscout/
├── README.md
├── PROJECT_PLAN.md          # 本文档
├── docker-compose.yml
├── docker-compose.dev.yml
├── Dockerfile
├── .env.example
├── .gitignore
│
├── backend/                   # FastAPI 后端
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py            # FastAPI 应用入口
│   │   ├── config.py          # Pydantic Settings
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── v1/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── analyze.py    # 分析任务接口
│   │   │   │   ├── reports.py    # 报告接口
│   │   │   │   ├── repos.py      # 仓库接口
│   │   │   │   └── compare.py    # 对比接口
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── models.py         # SQLAlchemy 模型
│   │   │   ├── database.py       # 数据库连接
│   │   │   └── cache.py          # Redis 封装
│   │   ├── agents/
│   │   │   ├── __init__.py
│   │   │   ├── orchestrator.py   # 协调器
│   │   │   ├── community_agent.py
│   │   │   ├── quality_agent.py
│   │   │   ├── security_agent.py
│   │   │   ├── evolution_agent.py
│   │   │   └── synthesis_agent.py
│   │   ├── mcp/
│   │   │   ├── __init__.py
│   │   │   ├── client.py         # MCP Client 封装
│   │   │   ├── servers/          # MCP Server 实现
│   │   │   │   ├── github_mcp/
│   │   │   │   ├── filesystem_mcp/
│   │   │   │   ├── search_mcp/
│   │   │   │   ├── osv_mcp/
│   │   │   │   └── code_analysis_mcp/
│   │   ├── rag/
│   │   │   ├── __init__.py
│   │   │   ├── vector_store.py   # ChromaDB 封装
│   │   │   ├── embeddings.py     # Embedding 模型
│   │   │   ├── ingest.py         # 文档入库
│   │   │   └── query.py          # RAG 查询
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── github_service.py
│   │   │   ├── analysis_service.py
│   │   │   └── report_service.py
│   │   ├── tasks/
│   │   │   ├── __init__.py
│   │   │   └── analysis_tasks.py  # Celery 任务
│   │   └── scoring/
│   │       ├── __init__.py
│   │       ├── community.py
│   │       ├── quality.py
│   │       ├── security.py
│   │       └── evolution.py
│   ├── tests/
│   ├── alembic/               # 数据库迁移
│   └── requirements.txt
│
├── frontend/                  # React 前端
│   ├── public/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── ReportCard.tsx
│   │   │   ├── ScoreGauge.tsx
│   │   │   ├── FindingList.tsx
│   │   │   └── TrendChart.tsx
│   │   ├── pages/
│   │   │   ├── HomePage.tsx
│   │   │   ├── ReportPage.tsx
│   │   │   ├── ComparePage.tsx
│   │   │   └── RepoListPage.tsx
│   │   ├── api/
│   │   │   └── client.ts
│   │   └── types/
│   │       └── index.ts
│   ├── package.json
│   └── vite.config.ts
│
├── mcp-servers/               # MCP Server 独立包
│   ├── github-mcp/
│   │   ├── server.py
│   │   └── pyproject.toml
│   ├── filesystem-mcp/
│   ├── search-mcp/
│   ├── osv-mcp/
│   └── code-analysis-mcp/
│
├── knowledge-base/            # RAG 知识库文档
│   ├── methodology/           # 评估方法论
│   ├── benchmarks/            # 行业基准
│   ├── case-studies/          # 失败案例
│   └── competitors/           # 竞品映射
│
├── scripts/                   # 工具脚本
│   ├── init_kb.py             # 初始化知识库
│   ├── seed_benchmarks.py     # 计算行业基准
│   └── benchmark.py           # 性能测试
│
└── docs/                      # 项目文档
    ├── ARCHITECTURE.md
    ├── AGENT_DESIGN.md
    ├── MCP_PROTOCOL.md
    └── DEPLOYMENT.md
```

---

## 13. 关键设计决策

### 13.1 为什么手写 Agent 编排

- **可控性**：自定义并发策略、错误恢复、重试逻辑
- **可解释性**：面试时能讲清楚每一步的决策逻辑
- **避免 vendor lock-in**：不依赖 LangChain 的特定抽象

### 13.2 为什么用 MCP 而非直接调用 API

- **标准化**：MCP 是 emerging standard，展示对生态的跟进
- **隔离性**：工具逻辑与 Agent 逻辑解耦
- **可扩展性**：新增数据源只需新增 MCP Server，无需修改 Agent 代码

### 13.3 为什么从规则评分开始，再引入 LLM

- **可验证**：规则评分的准确性可以用已知项目验证
- **可对比**：引入 LLM 后可以对比"规则 vs 推理"的效果差异
- **可量化**：能明确说出"LLM 推理在什么场景下比规则更准确"

---

## 14. 风险与应对

| 风险 | 影响 | 应对策略 |
|-----|------|---------|
| GitHub API 限频 | 分析速度受限 | 多层缓存 + 渐进式分析 |
| LLM 幻觉 | 报告可信度下降 | 规则评分打底，LLM 仅做推理增强；所有判断必须引用数据 |
| 大仓库克隆慢 | 代码分析超时 | 超时机制 + 部分分析（仅分析核心目录） |
| 竞品已有类似产品 | 差异化不足 | 专注"尽调报告"的完整性和可解释性，而非简单的评分 |

---

## 15. 面试叙事框架

### 15.1 项目介绍（30 秒版本）

> "技术团队选型开源库时往往只看 Stars 数，但 Stars 不等于维护质量。我做了一个开源项目尽调平台，核心是把 VC 做公司尽调的方法论搬到开源项目上——用 4 个专业 Agent 分别评估社区健康、代码质量、安全、技术演进，最终输出一份可投资级的结构化报告。"

### 15.2 技术亮点（2 分钟版本）

> "架构上有三个设计值得一提：
> 1. **手写 ReAct 编排**：没有使用 LangChain，而是自己实现了 Agent 协调器，支持并行执行、冲突消解和错误恢复。这让我对 LLM 交互模式有了深入理解。
> 2. **MCP 工具层**：所有外部数据源（GitHub、漏洞库、搜索引擎）都通过 MCP Server 接入，Agent 不直接调用 API，实现了工具与逻辑的解耦。
> 3. **RAG 校准**：引入了行业基准数据和历史失败案例，Agent 不是孤立判断，而是能说出'前端框架的平均 PR 合并率是 65%，这个项目是 45%，低于基准'。"

### 15.3 量化成果

> "目前分析了 100+ 热门项目，我对评分体系做了验证：与 3 位资深工程师的评分对比，Pearson 相关系数 0.87。最有意思的是回溯验证——我标记出某项目 Bus Factor 降到 2 且有核心维护者退出的征兆，3 个月后确实发生了维护者退出事件。"

---

## 16. 下一步行动

1. **本周**：搭建项目脚手架，确认 Phase 0 完成
2. **下周**：完成 GitHub API 封装和基础数据采集
3. ** milestone**：Phase 1 MVP 完成，能分析第一个项目并产出报告

---

*本文档为活文档，随着开发进展持续更新。*
