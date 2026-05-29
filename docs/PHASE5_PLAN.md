# Phase 5：真正的 Agent 架构重构 — 技术规划

> 版本：v1.1
> 日期：2026-05-29
> 状态：Phase 5.1~5.3 已完成，5.4 待开始
>
> 本文档聚焦 Phase 5 的完整技术方案，Phase 0~4 已完成内容见 `PROJECT_PLAN.md`。

---

## 1. 背景与目标

### 1.1 Phase 3/4 遗留的核心问题

Phase 3 是"伪 Agent"——Orchestrator 硬编码调度 4 个 Agent，工具调用在 Python 代码层完成，LLM 只负责"评分增强"和"写报告"。具体问题：

| # | 问题 | 根因 | 影响 | 解决状态 |
|---|---|---|---|---|
| 1 | RAG 检索内容未进入 LLM Prompt | `_calibrate_dimension` 只传文档标题，`content` 完全未使用 | RAG 只是"检索了→存了→展示了标题"，未参与推理 | ✅ 5.3 已解决：RAG Tool 返回完整 content |
| 2 | RAG 查询文本硬编码 | `calibrate_*` 方法用固定 3 个查询角度 | 检索角度与项目上下文不匹配 | ⏳ 5.4 解决：LLM 自主决定查询文本 |
| 3 | 4 个 Agent 重复采集数据 | Community 和 Security 都调 `list_contributors` | GitHub API 请求冗余，分析速度慢 | ⏳ 5.4 解决：Shared Memory 全局缓存 |
| 4 | Synthesis 信息被人为截断 | findings/risks 只取前 3 条，reasoning 截断到 200 字符 | LLM 无法基于完整信息做综合判断 | ⏳ 5.5 解决：ReAct Loop 让 LLM 自主决定需要多少数据 |
| 5 | 基准数据未充分利用 | `benchmark_tool.py` 提供查询但 Orchestrator 未调用 | 评分缺乏行业基准支撑 | ✅ 5.3 已解决：`rag_get_benchmark` Tool 已注册 |

### 1.2 Phase 5 总目标

> **让 LLM 成为真正的决策者**——自主规划分析路径、自主调用工具、自主检索知识、自主推理、自主反思。

同时解决上述 5 个遗留问题。

---

## 2. 技术架构总览

Phase 5 采用**三层架构**：

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 3: Multi-Agent 协作层（5.6 ~ 5.7）                    │
│  Single Master Agent + Dynamic Specialist Pool              │
│  + Message Bus + Reflection                                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  LAYER 2: 编排引擎层（5.4 ~ 5.5）                            │
│  Plan-and-Execute + ReAct Loop + 依赖感知并行 + 数据缓存      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1: Tool 基础设施层（5.1 ~ 5.3） ✅ 已完成              │
│  统一 Tool 协议 + Registry + Executor                       │
│  + MCP Adapter + RAG Adapter + LLM Provider 扩展            │
└─────────────────────────────────────────────────────────────┘
```

**设计原则**：
1. **先造枪、再打仗**：5.1~5.3 先建好 Tool 层，5.4~5.7 再构建编排和 Multi-Agent
2. **不破不立**：Phase 5 是架构重构，不兼容旧代码，5.6 果断废弃旧 Agent
3. **数据只采一次**：Shared Memory 缓存机制，所有 Agent/Tool 共享采集结果

---

## 3. 第一层：Tool 基础设施（5.1 ✅ 已完成）

### 3.1 核心抽象：Tool 协议

所有能力——本地 Python 函数、MCP Server 的远程工具、RAG 知识库检索——统一抽象为 `Tool` 对象：

```python
@dataclass
class Tool:
    name: str                    # 唯一标识，如 "github.get_repo_metadata"
    description: str             # LLM 决定"什么时候用"的依据
    parameters: dict             # JSON Schema，描述参数结构
    handler: Callable            # 实际执行函数
    source: ToolSource           # LOCAL / MCP / RAG
```

### 3.2 ToolRegistry + @tool 装饰器

`@tool` 装饰器自动从函数签名 + docstring 生成 JSON Schema，零配置接入：

```python
@tool(description="获取仓库元数据")
async def get_repo_metadata(owner: str, repo: str) -> dict:
    ...
# → 自动生成 JSON Schema，自动注册到 Registry
```

### 3.3 ToolExecutor

解析 LLM 返回的 `tool_calls` → 执行对应 Tool → 返回 observation。支持同步/异步 handler、并行执行、错误隔离。

### 3.4 MCP Adapter

`MCPAdapter.discover_and_register(client)` 自动发现 MCP Server 的工具，转换为 `Tool` 并注册。

### 3.5 RAG Adapter

将 `RAGQueryEngine` 封装为 3 个 LLM 可调用的 Tool：
- `rag_query_knowledge`: 通用语义检索（**返回完整 content**，解决 Phase 4 问题 #1）
- `rag_get_benchmark`: 查询行业基准数据（解决 Phase 4 问题 #5）
- `rag_get_competitors`: 检索竞品对比信息

### 3.6 LLM Provider 扩展

`chat()` 新增 `tools` 参数，`LLMResponse` 扩展 `tool_calls` 字段。Kimi/DeepSeek 均兼容 OpenAI 格式。

## 4. 第二层：编排引擎（5.4 ~ 5.5）

### 4.1 设计原则

**不破不立**：Phase 5.4 是新架构，不兼容旧 Orchestrator。旧代码（`orchestrator.py` 硬编码调度 4 个 Agent）在 5.6 果断废弃，不在新引擎里留兼容逻辑。

**声明式数据需求**：Plan 中不写"调用什么 Tool"，而是写"需要什么数据"。Execute Engine 负责把数据需求映射到 Tool 调用。

**数据只采一次**：同一 Tool + 同一套参数，无论 Master 还是 Specialist 调用，永远只执行一次。结果缓存在 Shared Memory 中。

---

### 4.2 Plan Engine

**职责**：LLM 根据仓库地址制定全局分析计划，输出带依赖关系的**数据需求清单**。

**输出格式（Step 列表）**：

```python
@dataclass
class Step:
    step_id: str              # 唯一标识，如 "step_1"
    step_type: str            # "data"（采集数据）/ "reasoning"（LLM 推理）/ "specialist"（委派专家）
    needs: list[str]          # 需要什么数据，如 ["repo_metadata", "contributor_list"]
    description: str          # 人类可读描述，LLM 制定计划时用
    deps: list[str]           # 依赖哪些 step_id 完成后才能执行
```

**Plan 示例**：

```python
[
    Step(step_id="s1", step_type="data", needs=["repo_metadata"],
         description="获取仓库基本信息", deps=[]),
    Step(step_id="s2", step_type="data", needs=["contributor_list"],
         description="获取贡献者列表", deps=["s1"]),
    Step(step_id="s3", step_type="data", needs=["community_benchmark"],
         description="检索社区健康标准", deps=[]),
    Step(step_id="s4", step_type="reasoning", needs=["community_score"],
         description="综合评估社区健康度", deps=["s2", "s3"]),
]
```

**关键设计**：`needs` 是**数据需求**（如 `"repo_metadata"`），不是 Tool 名。Execute Engine 负责映射到具体 Tool。

---

### 4.3 Shared Memory

**定位**：单次分析执行期间的**进程内临时缓存**（Python dict），不是 Redis。

**为什么不用 Redis？**
- 生命周期：随分析开始而创建，随分析结束而销毁（分钟级）
- 性能：进程内 dict 读写零序列化开销，Specialist 和 Master 在同进程（asyncio 任务）
- Redis 留给跨请求的长期缓存（GitHub API 响应缓存）

**缓存 key 生成**：

```python
cache_key = f"{tool_name}:{canonical_json(args)}"
# 例："github.get_repo_metadata:{"owner":"facebook","repo":"react"}"
```

**缓存命中规则**：同一 Tool + 同一套参数 → 直接返回缓存结果，不重复调 Tool。

---

### 4.4 Execute Engine

**职责**：解析 Plan → 提取当前可执行步骤（deps 已满足）→ 映射到 Tool → 查缓存 → 执行 → 存结果。

**每轮执行流程**：

```
1. 从 Plan 中提取 deps 已满足的步骤
2. 对每个步骤：
   a. 将 needs（数据需求）映射到 Tool 列表
   b. 对每个 Tool：查 Shared Memory → 命中则跳过，未命中则加入执行队列
3. 并行执行队列中的 Tool（asyncio.gather）
4. 结果存入 Shared Memory
5. 标记步骤完成，进入下一轮
```

**依赖感知并行**：无依赖的步骤自动并行，有依赖的按 DAG 顺序执行。

**失败隔离**：单个 Tool 失败只影响当前步骤，Execute Engine 记录失败信息继续执行后续步骤。

---

### 4.5 Specialist 扩展点（5.6 预留）

Plan Engine 在制定计划时，判断是否需要启动 Specialist：

```python
Step(
    step_id="s5",
    step_type="specialist",           # ← 预留类型
    specialist="security",            # ← 专家类型
    task="深度审计供应链安全漏洞",
    deps=["s1", "s4"]
)
```

Execute Engine 遇到 `step_type="specialist"`：
1. 启动 Security Specialist（同进程的 asyncio 任务）
2. Specialist 自己制定子 Plan，自己调 Tool
3. Specialist 通过**同一个 Shared Memory** 读取 Master 已采集的数据，避免重复调用
4. Specialist 执行完成后，结果写回 Shared Memory，Master 继续后续步骤

---

### 4.6 ReAct Loop（5.5）

> **边界说明**：ReAct 是**执行过程中**的局部反思，目的是判断"当前数据是否足够支撑下一步"。与 5.2 的全局 Reflection（分析完成后检查结论质量）不同。

Plan 执行过程中，Master Agent 每轮执行后进入 ReAct：
- **Thought**：分析结果是否充分？有没有遗漏维度？
- **Action**：如有遗漏，生成补充 Plan，Execute Engine 继续执行
- **Observation**：获取补充数据
- 循环直到 Master 认为分析充分，进入 Report 阶段

**终止条件**：max_iterations 上限（防止无限循环）或 Master 主动标记完成。

---

## 5. 第三层：Multi-Agent 协作（5.6 ~ 5.7）

### 5.1 Single Master + Dynamic Specialist Pool

不是"固定 4 个 Agent 永远并行"，而是 Master Agent 按需启动 Specialist：

```
Master Agent（Orchestrator）
  │
  ├─ 制定 Plan
  ├─ 调用 Tools 采集数据（通过 Function Calling）
  ├─ 判断是否需要启动 Specialist Agent
  │     ├─ 常规分析 → Master Agent 自己推理
  │     └─ 复杂场景 → 启动 Specialist
  │           ├─ Security Specialist（密码学/认证库）
  │           ├─ Community Specialist（大型项目）
  │           └─ Evolution Specialist（小众技术栈）
  │
  ├─ Reflection（自我检查）
  └─ Report（生成最终报告）
```

### 5.2 Message Bus + Reflection

> **边界说明**：Reflection 是**分析完成后**的全局反思，目的是检查"四个维度的结论有没有矛盾、有没有遗漏"。与 4.6 的 ReAct（执行过程中局部补充数据）不同。

Specialist 之间通过 Message Bus 协作。全部分析完成后，Reflection Engine 启动：
- 检查各维度结论是否存在矛盾（如"社区活跃但安全评分极低"）
- 检查是否有遗漏维度（如未评估许可证风险）
- 发现问题 → 生成补充 Plan → Execute Engine 执行 → 再次 Reflection
- 无问题 → 进入 Report 阶段

---

## 6. 子阶段规划与验收标准

| 子阶段 | 核心目标 | 状态 | 涉及文件 |
|--------|---------|------|---------|
| **5.1** | Function Calling 基础设施 | ✅ 已完成 | 新增：`tool.py` `registry.py` `executor.py` `mcp_adapter.py` `rag_adapter.py`；修改：`schemas.py` `base.py` `providers.py` |
| **5.2** | MCP 工具注册表 | ✅ 已完成 | 新增：`mcp_registry.py`；修改：`mcp_adapter.py` `__init__.py` `main.py` |
| **5.3** | RAG 工具化 | ✅ 已完成 | 修改：`rag_adapter.py` `query.py` `main.py` |
| **5.4** | Plan-and-Execute 编排引擎 | ⏳ 当前重点 | 新增：`plan_engine.py` `execute_engine.py` `shared_memory.py`；修改：`main.py`（集成新编排入口） |
| **5.5** | ReAct Loop 升级 | ⏳ 待开始 | 修改：`execute_engine.py` |
| **5.6** | 动态分析流程（Master + Specialist） | ⏳ 待开始 | 新增：`specialists/` 目录；废弃旧 Agent 文件 |
| **5.7** | Reflection | ⏳ 待开始 | 新增：`reflection_engine.py` `message_bus.py` |
| **5.8** | 前端适配 | ⏳ 待开始 | 修改：前端报告详情页 |

### 各子阶段验收标准

#### 5.1 Function Calling 基础设施

| # | 验收项 | 判定标准 | 状态 |
|---|--------|---------|------|
| 1 | Tool 协议 | 定义 Tool，LLM 能自主输出 `tool_call` | ✅ |
| 2 | 端到端验证 | Tool 执行结果正确返回给 LLM，LLM 基于结果继续推理 | ✅ |
| 3 | 自动 Schema | `@tool` 装饰器从函数签名自动生成 JSON Schema | ✅ |

#### 5.2 MCP 工具注册表

| # | 验收项 | 判定标准 | 状态 |
|---|--------|---------|------|
| 1 | 批量注册 | 4 个 MCP Server 全部成功注册 | ✅ |
| 2 | 失败隔离 | 单个 Server 连接失败不影响其他 Server | ✅ |
| 3 | 工具数量 | 共 15 个 Tool 正确注册到 Registry | ✅ |

#### 5.3 RAG 工具化

| # | 验收项 | 判定标准 | 状态 |
|---|--------|---------|------|
| 1 | Tool 注册 | 3 个 RAG Tool 启动时自动注册 | ✅ |
| 2 | 完整内容 | Tool 返回完整 content（而非仅标题），解决 Phase 4 问题 #1 | ✅ |
| 3 | LLM 调用 | LLM 能自主调用 RAG Tool 并基于结果推理 | ✅ |

#### 5.4 Plan-and-Execute 编排引擎

| # | 验收项 | 判定标准 | 状态 |
|---|--------|---------|------|
| 1 | Plan Engine | LLM 能根据仓库地址制定合理的分析计划，输出 `Step` 列表 | ⏳ |
| 2 | 声明式数据需求 | Plan 中 `needs` 是数据需求，不是 Tool 名 | ⏳ |
| 3 | Shared Memory | 单次分析内，同一 Tool + 同一参数只执行一次 | ⏳ |
| 4 | 依赖感知并行 | 能正确解析 `deps`，无依赖步骤自动并行 | ⏳ |
| 5 | 失败隔离 | 单个 Tool 失败不阻断整体流程 | ⏳ |
| 6 | Specialist 扩展点 | `Step` 预留 `step_type="specialist"`，Execute Engine 能识别路由 | ⏳ |

---

## 7. 代码迁移路径

### 7.1 已新增文件

```
backend/app/agents/tools/
  ├── tool.py              # Tool 数据模型 ✅ (5.1)
  ├── registry.py          # ToolRegistry + @tool 装饰器 ✅ (5.1)
  ├── executor.py          # ToolExecutor ✅ (5.1)
  ├── mcp_adapter.py       # MCPAdapter ✅ (5.1)
  ├── rag_adapter.py       # RAGToolAdapter ✅ (5.1)
  └── mcp_registry.py      # MCP 批量注册入口 ✅ (5.2)
```

### 7.2 已修改文件

```
# 5.1
backend/app/llm/schemas.py              # 新增 ToolCall、ToolResult、扩展 LLMMessage ✅
backend/app/llm/base.py                 # chat() 新增 tools 参数 ✅
backend/app/llm/providers.py            # 底层传入 tools + 解析 tool_calls ✅
backend/app/agents/tools/benchmark_tool.py  # 添加 @tool 装饰器 ✅
backend/app/mcp/client.py               # 新增 list_tools_detailed() ✅

# 5.2
backend/app/agents/tools/mcp_adapter.py # 修复 handler 生命周期：接收 client_class 而非实例 ✅
backend/app/agents/tools/__init__.py    # 暴露 initialize_mcp_tools / get_mcp_tools_summary ✅
backend/app/main.py                     # lifespan 中集成 MCP 工具自动注册 ✅

# 5.3
backend/app/agents/tools/rag_adapter.py # 新增 initialize_rag_tools() 统一入口 ✅
backend/app/agents/tools/__init__.py    # 暴露 initialize_rag_tools ✅
backend/app/main.py                     # lifespan 中集成 RAG 工具自动注册 ✅
```

### 7.3 待废弃文件（5.6 执行）

```
backend/app/agents/community_agent.py    → 功能拆入 Master + Community Specialist
backend/app/agents/quality_agent.py      → 功能拆入 Master + Tool 层
backend/app/agents/security_agent.py     → 功能拆入 Master + Security Specialist
backend/app/agents/evolution_agent.py    → 功能拆入 Master + Evolution Specialist
backend/app/agents/synthesis_agent.py    → 功能合并入 Master Agent 的 Report 阶段
backend/app/agents/llm_enhancer.py       → 功能由 Tool 层替代
```

---

## 8. 面试叙事框架（Phase 5 完整版）

> "Phase 5 之前是'伪 Agent'——硬编码调度 4 个 Agent，LLM 只负责填空。Phase 5 我重构成真正的 Agent 架构：LLM 自主规划分析路径、自主调用 MCP 工具、自主检索知识库做基准对比、自主反思修正。"
>
> "Phase 5 有四个设计值得一提：
> 1. **统一的 Tool 基础设施**：本地函数、MCP 工具、RAG 检索抽象为同一套 `Tool` 接口。新增工具只需 `@tool` 装饰器，JSON Schema 通过 `inspect.signature` 自动生成。
> 2. **Plan-and-Execute + ReAct 混合编排**：LLM 先制定全局计划，代码层自动并行化无依赖步骤，执行中 LLM 通过 ReAct 做局部决策。
> 3. **Dynamic Specialist Pool**：Master Agent 按需启动 Specialist，分析密码学库时自动启动 Security Specialist，分析个人小项目时自动简化流程。
> 4. **RAG 真正参与推理**：Phase 4 的 RAG 只是'检索了→存了→展示了标题'。Phase 5 把 RAG 检索封装为 LLM 可调用的 Tool，完整文档内容进入 LLM 上下文窗口。"

---

*本文档为 Phase 5 的完整技术规划，随着开发进展持续更新。当前下一步：Phase 5.4（Plan-and-Execute 编排引擎）。*
