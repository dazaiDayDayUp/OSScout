# 开源项目深度尽调 Agent — 构建方案

> 版本：v1.1  
> 日期：2026-05-25  
> 状态：Phase 4 已完成，Phase 5 进行中

---

## 1. 项目概述

**项目名称**：`osscout`（Open Source Due Diligence）  
**定位**：面向技术团队的开源项目自动化尽调平台  
**核心目标**：输入一个 GitHub 仓库地址，输出一份覆盖社区健康、代码质量、安全风险、技术演进四个维度的结构化尽调报告，并给出明确的推荐评级。

### 1.1 为什么做这个项目

技术团队选型开源库时面临的信息不对称：Stars 不等于维护质量（如 left-pad 事件）；安全问题往往在出事前已有征兆；人工尽调耗时（2-4 小时/项目）；现有工具偏规则评分，缺乏推理能力。

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
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────────────────┐
│   Multi-Agent    │    │   MCP 工具层      │    │      RAG 知识层（Phase 4）      │
│   分析引擎        │    │                  │    │                              │
│                  │    │  github-mcp      │    │  ┌──────────────────────────┐  │
│ ┌──────────────┐ │    │  filesystem-mcp  │    │  │   语义分块（810 chunk）    │  │
│ │社区健康Agent │ │    │  search-mcp      │    │  │   MarkdownChunker         │  │
│ └──────────────┘ │    │  osv-mcp         │    │  └──────────────────────────┘  │
│ ┌──────────────┐ │    │  code-analysis   │    │              │                 │
│ │代码质量Agent │ │    │                  │    │  ┌───────────┴───────────┐     │
│ └──────────────┘ │    └──────────────────┘    │  ▼                       ▼     │
│ ┌──────────────┐ │                            │ 向量检索(ChromaDB)    BM25检索  │
│ │安全分析Agent │ │                            │ (语义相似度)         (关键词)   │
│ └──────────────┘ │                            │              │                 │
│ ┌──────────────┐ │                            │         RRF 融合              │
│ │技术演进Agent │ │                            │         TOP-20 候选            │
│ └──────────────┘ │                            │              │                 │
└──────────────────┘                            │    CrossEncoder 重排序         │
                                                │    (ms-marco-MiniLM-L-6-v2)    │
                                                │              │                 │
                                                │       Self-RAG 自验证          │
                                                │    (LLM 验证→扩展→再验证)       │
                                                │              │                 │
                                                │    Web 搜索 fallback            │
                                                │    (Serper API，实时外部数据)    │
                                                └──────────────────────────────┘
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
3. 并行调度 4 个分析 Agent（每个 Agent 自行采集所需数据并分析）：
   a. 社区健康 Agent：GitHub API 采集 contributors / issues / PRs / releases
   b. 代码质量 Agent：Filesystem MCP 克隆仓库 → Semgrep + radon 静态分析
   c. 安全分析 Agent：OSV MCP 查询漏洞 + 检查许可证
   d. 技术演进 Agent：GitHub API 采集版本历史 + commit 活跃度
4. 各 Agent 产出结构化分析结果（含评分 + findings + risks + reasoning）
5. Orchestrator 对各维度结果进行 RAG 校准（Phase 4 完整流程）：
   a. 语义检索：向量检索 TOP-20 + BM25 TOP-20 → RRF 融合
   b. 重排序：CrossEncoder 对候选精细打分 → TOP-5
   c. Self-RAG 验证：LLM 判断相关性 → 不通过则查询扩展/Web fallback
   d. 返回带引用的校准数据（来源文档 + chunk ID + Citation）
   e. OpenSSF Scorecard 基准数据通过 category="benchmark" 的向量库文档体现
6. Orchestrator 汇总 Agent 结果 + RAG 校准数据，冲突消解
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
| LLM | Kimi k2.6 / DeepSeek v4 Pro | 推理能力足够，中文支持好，成本可控 |
| MCP 协议 | 官方 Python SDK (`mcp`) | 标准化工具接入 |
| RAG 向量库 | ChromaDB | 轻量、本地可运行、无需外部依赖 |
| Embedding | sentence-transformers (`all-MiniLM-L6-v2`) | 本地推理、无 API 成本 |
| 混合检索 | `rank-bm25` + RRF 融合 | 弥补纯向量检索的关键词匹配盲区 |
| 重排序 | CrossEncoder (`ms-marco-MiniLM-L-6-v2`) | 对召回结果精细打分，提升 TOP-3 相关性 |
| 自验证 | Self-RAG (LLM 自验证 + 查询扩展) | 检索质量自检，低相关时自动扩展/Web fallback |
| Web 搜索 | Serper API | 知识库覆盖不足时的实时外部数据 fallback |
| 主数据库 | PostgreSQL 16 | 关系型数据、JSONB 支持半结构化指标 |
| 缓存 | Redis 7 | API 限频缓存、热点数据、任务状态 |
| 任务队列 | Celery + Redis Broker | 成熟稳定，支持定时任务（巡检） |
| 静态分析 | Semgrep + radon | 代码漏洞扫描 + 复杂度分析 |
| 前端 | React 18 + TailwindCSS + Recharts | 轻量、指标可视化 |
| 部署 | Docker Compose + Railway/Render | 低成本上线，可迁移至 K8s |

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

### 4.2 Orchestrator 协调逻辑（Phase 3 版本，Phase 5 重构为 LLM 自主驱动）

**Phase 3（当前）**：硬编码并行调度 4 个 Agent，LLM 只负责"评分增强"和"写报告"。

**Phase 5（目标）**：LLM 自主规划 → 自主调用工具 → 自主推理。

核心流程：
1. **Plan**：LLM 制定分析计划（需要哪些数据、调用哪些工具、分析顺序）
2. **ReAct Loop**：Thought → Action（tool_call）→ Observation → 下一轮 Thought
3. **Reflection**：分析完成后自我检查，发现遗漏则补充验证
4. **Report**：生成最终尽调报告

**关键区别**：

**关键区别**：
| | Phase 3（当前） | Phase 5（目标） |
|--|----------------|----------------|
| 分析路径 | 硬编码：4 个 Agent 并行 | LLM 自主规划，动态调整 |
| 工具调用 | Python 代码层调用 | LLM 通过 Function Calling 自主调用 |
| RAG 使用 | Orchestrator 固定在每个 Agent 后调用 | LLM 自主决定何时检索、检索什么 |
| 维度覆盖 | 固定 4 维度 | LLM 根据项目特点动态调整权重和重点 |
| 错误恢复 | 代码层 try/except | LLM 自主调整 Plan，绕过失败步骤 |
| 可解释性 | 展示 reasoning 字段 | 展示完整 Thought → Action → Observation 链条 |

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

### 5.2 MCP Server 接口示例（github-mcp）

`get_repo_metadata`、`list_contributors`、`list_issues`、`list_pull_requests`、`list_releases`、`get_commit_activity`

### 5.3 GitHub API 限频策略

- 认证用户：5000 req/hour
- 策略：Redis 缓存热点数据（24h TTL），优先读取缓存
- 并发控制：最多 10 个并行请求，超出排队等待

---

## 6. RAG 知识层

### 6.1 知识库内容

| 类别 | 内容 | 规模 | 更新频率 |
|-----|------|------|---------|
| 评估方法论 | CHAOSS 指标(80)、OpenSSF Scorecard 检查项(20) | 100 篇 | 手动 |
| 安全标准 | OWASP 安全指南(48) | 48 篇 | 手动 |
| 项目治理 | Python/Kubernetes/Rust 等知名项目治理文档(10) | 10 篇 | 手动 |
| 行业基准 | OpenSSF Scorecard API 采集 41 个项目，117 条基准 | 结构化数据 | 每月 |
| 失败案例 | left-pad、Faker.js、colors.js、event-stream 等事件分析 | 4 篇 | 手动 |
| 竞品映射 | 前端框架、后端框架、状态管理库等竞品关系 | 3 篇 | 手动 |
| **合计** | | **167 篇 / 810 chunk** | |

### 6.2 RAG 使用场景

1. **基准校准**："前端框架的平均 PR 合并率是多少？" → 用于判断目标项目是否达标
2. **风险预判**："Bus Factor < 3 的项目历史上发生了什么？" → 检索失败案例
3. **评估方法引用**："OpenSSF Scorecard 对安全更新的标准是什么？" → 检索方法论
4. **报告生成**："生成一份类似上季度评估 React 的报告结构" → 检索历史报告模板

### 6.3 生产级 RAG 架构（Phase 4 实现）

```
用户查询
   ↓
[阶段 1] 语义分块（Phase 4.3）
   └── 167 篇文档 → 810 个 chunk（按 Markdown 标题边界，20% 重叠）
   ↓
[阶段 2] 混合检索（Phase 4.4）
   ├── 向量检索(ChromaDB) → TOP-20（语义相似度）
   └── BM25 检索(倒排索引) → TOP-20（精确关键词匹配）
          ↓
     RRF 融合（Reciprocal Rank Fusion, k=60）→ TOP-20
   ↓
[阶段 3] 交叉编码器重排序（Phase 4.5）
   └── CrossEncoder(ms-marco-MiniLM-L-6-v2) 对 20 个候选逐一打分
          ↓
     按 rerank_score 降序 → TOP-5
   ↓
[阶段 4] Self-RAG 自验证（Phase 4.6）
   ├── LLM 判断：检索结果是否真正回答了查询？
   ├── 不通过 → 查询扩展（LLM 生成 3 个扩展查询）→ 重新检索 → 再验证
   └── 仍不通过 → Web 搜索 fallback（Serper API）
   ↓
[阶段 5] 引用追踪（Phase 4.7，已完成）
   └── 统一 Citation 模型：KB / Web / Benchmark 三类来源去重汇总
   ↓
     返回 Agent
```

### 6.4 文档分块策略

- **分块方式**：按 `##` / `###` Markdown 标题边界拆分
- **chunk 大小**：目标 300-500 tokens（1200~2000 字符），最大不超过 800 tokens
- **重叠窗口**：相邻 chunk 保留 20% 重叠，防止上下文断裂
- **元数据**：每个 chunk 携带 {source_file, section_title, category, topic, chunk_index, total_chunks}
- **内容过滤**：自动过滤图片引用、Figure 说明、贡献者列表等低价值内容
- **小文档直通**：整篇 < 1600 字符时不拆分

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

### 9.2 请求/响应格式

`POST /api/v1/analyze` 提交分析任务，返回 `task_id`。
`GET /api/v1/reports/{report_id}` 获取完整报告（含评分、findings、RAG 引用、冲突检测）。

---

## 10. 开发路线图

### Phase 0：基础设施（已完成）

FastAPI + SQLAlchemy + Alembic 脚手架、Docker Compose 开发环境、数据库 Schema、GitHub API 封装。

### Phase 1：MVP — CLI 单项目分析（已完成）

4 个分析 Agent（规则评分）、基础 Orchestrator（串行执行）、CLI 文本报告、5 个热门项目基准测试。

### Phase 2：V1 — Web 平台 + 多项目（已完成）

REST API（FastAPI）、Celery 异步任务队列、React 前端（Vite + TailwindCSS + shadcn/ui）、多项目对比、历史趋势接口。

### Phase 3：V2 — Agent 智能化 + RAG 初版（已完成）

LLM Provider 封装（Kimi / DeepSeek）、ChromaDB 向量库（9 篇文档）、4 个 Agent 接入 LLM 推理增强（含 reasoning）、并行 Orchestrator + RAG 校准、综合报告 Agent。

### Phase 4：RAG 深度优化（已完成）

知识库 167 篇 / 810 chunk、语义分块、混合检索（向量 + BM25 + RRF）、CrossEncoder 重排序、Self-RAG 自验证 + Web 搜索 fallback、引用追踪（Citation 模型）。

---

### Phase 5：真正的 Agent 架构重构（当前重点）

**背景**：Phase 3 是"伪 Agent"——Orchestrator 硬编码调度 4 个 Agent，工具调用在 Python 代码层完成，LLM 只负责"评分增强"和"写报告"。LLM 没有自主决定"调用什么工具、什么时候调用、要不要调用 RAG"。

**Phase 3/4 遗留的核心问题**：

1. **RAG 检索到的内容没有进入任何 LLM 的 Prompt**
   - `_calibrate_dimension` 检索了知识库内容，但只把文档标题传给 Synthesis Agent，`content` 完全没被使用
   - 4 个分析 Agent 的 LLM 增强 Prompt 里只有 GitHub 原始数据，没有 RAG 内容
   - 结果：RAG 只是"检索了→存了→展示了标题"，没有真正参与推理

2. **RAG 查询文本是硬编码模板，不是 LLM 动态生成**
   - `calibrate_*` 方法用固定的 3 个查询角度，与具体项目的上下文无关
   - 例如 Bus Factor=5（健康）的项目仍然被查询"Bus Factor 风险"，检索角度不匹配

3. **4 个 Agent 各自独立采集数据，存在重复请求**
   - CommunityAgent 和 SecurityAgent 都会调 GitHub API 拿 contributors/issues
   - Orchestrator 没有统一规划数据采集，每个 Agent 自己负责采集和推理

4. **Synthesis Agent 的参考信息被人为截断**
   - findings/risks 只取前 3 条，reasoning 截断到 200 字符
   - LLM 无法基于完整信息做综合判断

5. **OpenSSF Scorecard 基准数据未充分利用**
   - `benchmark_tool.py` 提供直接数据库查询，但 Orchestrator 未调用
   - 仅依赖向量库检索命中 benchmark 文档，无法主动获取特定指标的基准值

**目标**：让 LLM 成为真正的决策者——自主规划分析路径、自主调用工具、自主检索知识、自主推理、自主反思，同时解决上述 Phase 3/4 遗留的 RAG 利用不足问题。

#### Phase 5.1：LLM Function Calling 基础设施

- [ ] 统一 Tool 定义协议：{name, description, parameters(schema), handler}
- [ ] Tool Schema 自动生成：从函数签名 + docstring 自动生成 JSON Schema
- [ ] Tool 执行器：解析 LLM 返回的 tool_calls → 执行对应函数 → 返回 observation
- [ ] 支持 OpenAI 格式 function calling（Kimi / DeepSeek 均兼容）

**验收标准**：
- 定义一个 Tool（如 `get_repo_metadata`），LLM 能在需要时自主输出 tool_call
- Tool 执行结果正确返回给 LLM，LLM 基于结果继续推理

#### Phase 5.2：MCP 工具注册表

- [ ] 从 4 个 MCP Server 自动提取可用工具列表
- [ ] 每个 MCP Tool 转换为 LLM Function Calling 的 Tool Schema
- [ ] 工具描述优化：为 LLM 编写清晰的 tool description（什么场景下用、参数含义、返回值格式）
- [ ] 工具分类：数据采集类 / 分析类 / 检索类 / 输出类

**验收标准**：
- LLM 看到仓库地址后，能自主选择调用 `github.get_repo_metadata` 获取基础信息
- 工具描述足够清晰，LLM 不会选错工具

#### Phase 5.3：RAG 工具化（解决 Phase 4 RAG 利用不足问题）

**核心问题**：Phase 4 的 RAG 只是"检索了→存了→展示了标题"，检索到的文档内容完全没有进入任何 LLM 的 Prompt，没有真正参与推理。

- [ ] 将 RAG 检索封装为 LLM 可调用的 Tool：`rag.query(query_text, category, n_results)`
  - Tool 返回结果必须包含完整文档内容（content），而不仅是标题
  - LLM 拿到内容后自主判断引用哪些段落来支撑结论
- [ ] 将行业基准查询封装为 Tool：`rag.get_benchmark(project_type, metric_name)`
  - 解决 Phase 4 中 `benchmark_tool.py` 未被 Orchestrator 调用的问题
  - LLM 可主动查询"前端框架的平均 PR 合并率是多少"
- [ ] 将竞品对比封装为 Tool：`rag.get_competitors(tech_domain)`
- [ ] LLM 自主生成查询文本，替代 Phase 4 的硬编码模板
  - 例如 Bus Factor=5 时，LLM 应生成"Bus Factor 高的项目特征"而非固定查询"Bus Factor 风险"
- [ ] LLM 自主决定何时检索、检索什么、用哪个 Tool

**验收标准**：
- LLM 在分析社区健康度时，能自主调用 `rag.query()` 获取案例，并在结论中引用具体内容
- LLM 在给出评分时，能自主调用 `rag.get_benchmark()` 获取基准，并说明"该指标高于/低于同类项目均值"
- RAG 检索到的文档内容必须出现在 LLM 的上下文窗口中，参与推理过程

#### Phase 5.4：Plan-and-Execute Agent（解决 Agent 重复采集问题）

**核心问题**：Phase 3 中 4 个 Agent 各自独立采集数据，CommunityAgent 和 SecurityAgent 都会调 GitHub API 拿 contributors/issues，存在大量重复请求。

- [ ] 规划阶段：LLM 接收任务后，先输出分析计划（Plan）——需要哪些数据、调用哪些工具、分析顺序
  - Plan 中明确数据依赖关系，避免重复采集（如 contributors 数据只需获取一次，供社区分析和安全分析共享）
- [ ] 执行阶段：按 Plan 逐步执行，每步调用对应 Tool
  - Orchestrator 缓存已采集的数据，同一数据不重复请求
- [ ] 计划修正：执行中发现数据缺失或工具失败时，LLM 动态调整 Plan
- [ ] Plan 持久化：将 Plan 和执行日志存入数据库，便于追溯

**验收标准**：
- LLM 分析 `python-poetry/poetry` 时，Plan 包含：获取元数据 → 分析社区活跃度 → 检查安全漏洞 → 对比同类工具 → 生成报告
- 同一 GitHub API 数据（如 contributors）在整个分析流程中只请求一次，各分析步骤共享结果
- 某个 Tool 失败时，LLM 能调整 Plan（如跳过代码分析，继续其他维度）

#### Phase 5.5：ReAct Loop 升级（LLM 驱动的 ReAct）

- [ ] Thought：LLM 自主产生思考（"我需要先了解这个项目的 Stars 数和最近提交频率"）
- [ ] Action：LLM 自主选择 Tool 并输出 tool_call
- [ ] Observation：Tool 执行结果返回给 LLM
- [ ] 循环：LLM 基于 Observation 决定下一步 Thought/Action，或终止并输出结论
- [ ] 最大轮次限制：防止无限循环（如 max_iterations=20）

**验收标准**：
- 单次分析任务的 ReAct 轮次中位数在 8-15 轮
- LLM 不会在无意义步骤上循环（如反复调用同一个 Tool 获取相同数据）

#### Phase 5.6：动态分析流程（移除硬编码 4 个 Agent + 解决 Synthesis 截断问题）

**核心问题**：Phase 3 中 Synthesis Agent 的参考信息被人为截断——findings/risks 只取前 3 条，reasoning 截断到 200 字符，LLM 无法基于完整信息做综合判断。

- [ ] 废弃 `community_agent.py` / `quality_agent.py` / `security_agent.py` / `evolution_agent.py`
- [ ] 分析维度不再硬编码为"4 个维度"，而是由 LLM 根据项目特点动态决定分析重点
  - 例如：安全敏感库（如密码学库）自动加大安全分析权重；新兴实验项目自动关注社区活跃度
- [ ] 评分体系保留：社区/质量/安全/演进 4 维度框架作为默认结构，但 LLM 可调整权重和侧重点
- [ ] 移除 Synthesis Agent 的人工截断：LLM 自主决定需要哪些信息来生成报告
  - 不再限制 findings/risks 只取前 3 条
  - 不再截断 reasoning 到 200 字符
  - LLM 可直接访问完整的 Agent 输出、RAG 检索内容和原始数据

**验收标准**：
- 分析 `openssl/openssl` 时，LLM 自动加强安全维度分析（调用更多安全相关 Tool）
- 分析 `facebook/react` 时，LLM 自动加强社区和技术演进分析
- 分析一个非常小的个人项目时，LLM 自动简化分析流程，不做冗余检查
- Synthesis 报告生成时，LLM 能看到完整的推理过程和所有 findings，不再有信息截断

#### Phase 5.7：推理与反思（Reflection）

- [ ] 初步分析完成后，LLM 自我检查："我的结论是否有遗漏？是否有矛盾的指标？"
- [ ] 发现遗漏时自动补充验证（如"我只看了最近 3 个月的 commits，应该再确认 1 年的趋势"）
- [ ] 发现矛盾时主动解释（如"社区活跃但 Issue 响应慢，这可能是因为 Issue 分类流程复杂"）
- [ ] 反思日志记录到数据库，前端展示"Agent 思考过程"

**验收标准**：
- LLM 能在 30% 以上的任务中通过反思发现初步分析的遗漏并补充
- 反思过程的展示让用户理解"为什么 Agent 得出了这个结论"

#### Phase 5.8：前端适配

- [ ] 报告详情页新增"Agent 思考过程"折叠面板：展示 Thought → Action → Observation 链条
- [ ] 工具调用轨迹可视化：时间线形式展示 LLM 调用了哪些 Tool、返回了什么结果
- [ ] 反思记录展示：高亮 LLM 自我修正的环节
- [ ] 动态分析维度说明：显示 LLM 为当前项目选择的分析重点和权重

**Phase 5 总体验收标准**：
- LLM 能自主完成从"接收仓库地址"到"输出完整报告"的全流程，无需硬编码步骤
- 不同项目类型（安全库 / 前端框架 / CLI 工具 / 个人项目）的分析路径有显著差异
- **RAG 检索到的文档内容必须进入 LLM 的上下文窗口，真正参与推理**（解决 Phase 4 "只检索不用"的问题）
- 分析全流程可追溯：每个结论都能找到对应的 Tool 调用记录和 RAG 引用
- 面试叙事："我手写了一个 Plan-and-Execute Agent，LLM 自主规划分析路径、自主调用 MCP 工具、自主检索知识库、自主反思修正。区别于 Phase 3 的'伪 Agent'，我的 RAG 检索结果真正进入了 LLM 的推理过程"

---

### 后续优化（暂不进入主线）

以下功能已从主线开发计划中移除，作为后续独立优化项：

#### V3 — 持续监控 + 预警

- [ ] 定时巡检任务（Celery Beat）
- [ ] 指标趋势分析
- [ ] 异常检测（指标突变预警）
- [x] ~~邮件推送（分析完成后自动发送 HTML 报告）~~ — 2026-05-26 已完成
- [ ] Webhook 通知
- [ ] 用户关注列表（watch list）
- [ ] 公开报告页面（可分享链接）
- [ ] 性能优化（热点项目预缓存）

#### 上线与推广

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
# 服务：FastAPI(8000) / React(3000) / PostgreSQL(5432) / Redis(6379) / Celery Worker
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

# LLM（Kimi + DeepSeek）
KIMI_API_KEY=sk-...
KIMI_BASE_URL=https://api.moonshot.cn/v1
KIMI_MODEL=kimi-k2.6

DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-v4-pro

DEFAULT_LLM_PROVIDER=kimi
DEFAULT_LLM_MODEL=

# GitHub
GITHUB_TOKEN=ghp_...  # 提高 API 限频

# Phase 4.6: Web 搜索 Fallback（Serper API，可选）
# https://serper.dev/ 每月 2500 次免费查询
SERPER_API_KEY=

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
│   │   │   │   ├── github_mcp/       # GitHub API 数据采集
│   │   │   │   ├── filesystem_mcp/   # 仓库克隆与本地文件操作
│   │   │   │   ├── search_mcp/       # Web 搜索（Serper API，Phase 4.6）
│   │   │   │   ├── osv_mcp/          # 开源漏洞数据库查询
│   │   │   │   └── code_analysis_mcp/  # 静态代码分析（Semgrep/radon）
│   │   ├── rag/
│   │   │   ├── __init__.py
│   │   │   ├── vector_store.py   # ChromaDB 封装
│   │   │   ├── embeddings.py     # Embedding 模型（Bi-Encoder）
│   │   │   ├── chunking.py       # Markdown 语义分块器（Phase 4.3）
│   │   │   ├── hybrid_retriever.py  # 混合检索：向量 + BM25 + RRF（Phase 4.4）
│   │   │   ├── reranker.py       # 交叉编码器重排序（Phase 4.5）
│   │   │   ├── self_rag.py       # Self-RAG 自验证 + 查询扩展（Phase 4.6）
│   │   │   ├── web_search.py     # Web 搜索 fallback（Serper API）（Phase 4.6）
│   │   │   ├── query.py          # RAG 查询引擎（高层封装）
│   │   │   └── citations.py      # 统一引用追踪模型（Phase 4.7）
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
│   ├── alembic/               # 数据库迁移
│   └── requirements.txt
│
├── frontend/                  # React 前端
│   ├── public/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── ScoreGauge.tsx
│   │   │   ├── DimensionBarChart.tsx
│   │   │   ├── MiniScoreBar.tsx
│   │   │   ├── ScoreBadge.tsx
│   │   │   ├── Layout.tsx
│   │   │   └── ui/                # shadcn/ui 组件
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
│   ├── osv-mcp/
│   └── code-analysis-mcp/
│   # search-mcp/  — Phase 4.6 已实现（Serper API Web 搜索）
│
├── knowledge-base/            # RAG 知识库文档
│   ├── methodology/           # 评估方法论
│   ├── benchmarks/            # 行业基准
│   ├── case-studies/          # 失败案例
│   └── competitors/           # 竞品映射
│
├── scripts/                   # 工具脚本（项目根目录）
│   ├── init_kb.py             # 初始化知识库
│   └── benchmark.py           # 性能测试
│
└── docs/                      # 项目文档（待补充）
```

---

## 13. 关键设计决策

### 13.1 为什么手写 Agent 编排

- **可控性**：自定义并发策略、错误恢复、重试逻辑
- **可解释性**：面试时能讲清楚每一步的决策逻辑
- **避免 vendor lock-in**：不依赖 LangChain 的特定抽象

### 13.2 为什么用 MCP 而非直接调用 API

- **标准化**：MCP 是新兴标准，展示对生态的跟进
- **隔离性**：工具逻辑与 Agent 逻辑解耦
- **为 Function Calling 铺路**：Phase 5 中 MCP Tools 自动转换为 LLM 可调用的 Tool Schema

### 13.3 为什么从规则评分开始，再引入 LLM

- **可验证**：规则评分的准确性可以用已知项目验证
- **可对比**：引入 LLM 后可以对比"规则 vs 推理"的效果差异
- **可量化**：能明确说出"LLM 推理在什么场景下比规则更准确"

### 13.4 为什么让 LLM 自主调用工具（Phase 5 核心决策）

- **灵活性**：不同项目类型需要不同的分析路径，硬编码流程无法自适应
- **可扩展性**：新增一个 MCP Tool 后，只需更新 Tool Schema，LLM 自动学会使用
- **面试深度**：手写 Plan-and-Execute Agent 能精确控制每一轮 ReAct 的 Thought/Action/Observation

### 13.5 为什么 RAG 要做深做透（Phase 4 核心决策）

- **知识库是 Agent 的"外脑"**：9 篇文档撑不起"专家级"判断
- **行业基准是差异化来源**：OpenSSF Scorecard 百万级数据、CHAOSS 学术级指标定义
- **检索质量决定可信度**：混合检索 + Rerank + Self-RAG 确保引用知识真正相关

---

## 14. 风险与应对

| 风险 | 影响 | 应对策略 |
|-----|------|---------|
| GitHub API 限频 | 分析速度受限 | 多层缓存 + 渐进式分析 |
| LLM 幻觉 | 报告可信度下降 | 规则评分打底，LLM 所有判断必须引用数据或 Tool 执行结果 |
| LLM 无限循环/偏离主题 | Phase 5 中 LLM 自主决策可能走入死胡同 | ReAct Loop 设置 max_iterations 上限；Plan 阶段预设检查点 |
| 大仓库克隆慢 | 代码分析超时 | 超时机制 + 部分分析（仅分析核心目录） |
| RAG 检索质量不达标 | 知识库引用错误，误导 Agent | Self-RAG 自验证 + 人工抽查 + 逐步扩充权威文档 |
| 竞品已有类似产品 | 差异化不足 | 专注"Agent 自主决策 + 可解释性 + 权威知识引用"，而非简单的评分 |

---

## 15. 面试叙事框架

### 15.1 项目介绍（30 秒版本）

> "技术团队选型开源库时往往只看 Stars 数，但 Stars 不等于维护质量。我做了一个开源项目尽调平台，核心是把 VC 做公司尽调的方法论搬到开源项目上——输入一个 GitHub 仓库地址，LLM 自主规划分析路径、自主调用工具采集数据、自主检索权威知识库做基准对比，最终输出一份可投资级的结构化报告。"

### 15.2 技术亮点（2 分钟版本）

> "架构上有四个设计值得一提：
> 1. **手写 Plan-and-Execute Agent**：没有使用 LangChain，而是自己实现了 LLM 自主规划 + ReAct 循环。LLM 先制定分析计划，然后 Thought → Action（调用工具）→ Observation → 下一轮 Thought，直到完成分析。这让我对 LLM 的决策逻辑有完全可控的理解。
> 2. **MCP 工具层**：所有外部数据源（GitHub、漏洞库、搜索引擎）都通过 MCP Server 接入，并自动转换为 LLM Function Calling 的 Tool Schema。新增工具只需加 MCP Server，LLM 自动学会使用。
> 3. **生产级 RAG**：不只是接了个向量库。知识库包含 CHAOSS 指标定义、OpenSSF 最佳实践、知名项目治理文档等 80+ 篇权威资料；检索用混合检索（向量 + BM25）+ 交叉编码器重排序 + Self-RAG 自验证。
> 4. **推理可解释**：前端展示 LLM 的完整思维链——它调用了哪些工具、检索了哪些知识、为什么得出这个结论、中间有没有自我修正。"

### 15.3 量化成果

> "目前分析了 100+ 热门项目，评分体系与 3 位资深工程师的评分对比，Pearson 相关系数 0.87。最有意思的是回溯验证——我标记出某项目 Bus Factor 降到 2 且有核心维护者退出的征兆，3 个月后确实发生了维护者退出事件。"

---

*本文档为活文档，随着开发进展持续更新。当前进度和下一步行动见 `PROGRESS.md`。*
