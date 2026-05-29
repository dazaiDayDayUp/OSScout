# Phase 5：真正的 Agent 架构重构 — 技术规划

> 版本：v1.1
> 日期：2026-05-29
> 状态：Phase 5.1 已完成，5.2 待开始
>
> 本文档聚焦 Phase 5 的完整技术方案，Phase 0~4 已完成内容见 `PROJECT_PLAN.md`。

---

## 1. 背景与目标

### 1.1 Phase 3/4 遗留的核心问题

Phase 3 是"伪 Agent"——Orchestrator 硬编码调度 4 个 Agent，工具调用在 Python 代码层完成，LLM 只负责"评分增强"和"写报告"。具体问题：

| # | 问题 | 根因 | 影响 |
|---|---|---|---|
| 1 | RAG 检索内容未进入 LLM Prompt | `_calibrate_dimension` 只传文档标题，`content` 完全未使用 | RAG 只是"检索了→存了→展示了标题"，未参与推理 |
| 2 | RAG 查询文本硬编码 | `calibrate_*` 方法用固定 3 个查询角度 | 检索角度与项目上下文不匹配 |
| 3 | 4 个 Agent 重复采集数据 | Community 和 Security 都调 `list_contributors` | GitHub API 请求冗余，分析速度慢 |
| 4 | Synthesis 信息被人为截断 | findings/risks 只取前 3 条，reasoning 截断到 200 字符 | LLM 无法基于完整信息做综合判断 |
| 5 | 基准数据未充分利用 | `benchmark_tool.py` 提供查询但 Orchestrator 未调用 | 评分缺乏行业基准支撑 |

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
│  + Shared Memory + Message Bus + Reflection                 │
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
- `rag.query_knowledge`: 通用语义检索（**返回完整 content**，解决 Phase 4 问题 #1）
- `rag.get_benchmark`: 查询行业基准数据（解决 Phase 4 问题 #5）
- `rag.get_competitors`: 检索竞品对比信息

### 3.6 LLM Provider 扩展

`chat()` 新增 `tools` 参数，`LLMResponse` 扩展 `tool_calls` 字段。Kimi/DeepSeek 均兼容 OpenAI 格式。

**5.1 验收标准（已验证）**：
- ✅ 定义 Tool，LLM 能自主输出 `tool_call`
- ✅ Tool 执行结果正确返回给 LLM，LLM 基于结果继续推理
- ✅ `@tool` 装饰器自动生成 JSON Schema

---

## 4. 第二层：编排引擎（5.4 ~ 5.5）

### 4.1 Plan-and-Execute + ReAct 混合模式

```
用户提交仓库地址
    │
    ▼
┌─────────────────┐
│  Plan 阶段      │  LLM 制定全局分析计划
│  (全局规划)      │
└─────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Execute 阶段（ReAct Loop + 依赖感知并行）                    │
│                                                              │
│  每轮：                                                       │
│    1. 从 Plan 提取当前可执行的步骤（dependencies 已满足）     │
│    2. 并行调用这些步骤涉及的 Tool                             │
│    3. 收集 Observation → 存入 Shared Memory                 │
│    4. LLM Thought：基于新数据，下一轮调用什么？               │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Shared Memory

执行过程中的数据缓存。所有 Tool 调用结果按 "tool_name:serialized_args" 缓存，同一数据只采集一次。

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

Specialist 之间通过 Message Bus 协作。初步分析完成后，Reflection Engine 自我检查——发现遗漏则生成补充 Plan，发现矛盾则修正结论。

---

## 6. 子阶段规划与验收标准

| 子阶段 | 核心目标 | 状态 | 涉及文件 |
|--------|---------|------|---------|
| **5.1** | Function Calling 基础设施 | ✅ 已完成 | 新增：`tool.py` `registry.py` `executor.py` `mcp_adapter.py` `rag_adapter.py`；修改：`schemas.py` `base.py` `providers.py` |
| **5.2** | MCP 工具注册表 | ✅ 已完成 | 新增：`mcp_registry.py`；修改：`mcp_adapter.py` `__init__.py` `main.py` |
| **5.3** | RAG 工具化 | ⏳ 待开始 | 修改：`rag_adapter.py` `query.py` |
| **5.4** | Plan-and-Execute | ⏳ 待开始 | 新增：`plan_engine.py` `execute_engine.py` `shared_memory.py` |
| **5.5** | ReAct Loop 升级 | ⏳ 待开始 | 修改：`execute_engine.py` |
| **5.6** | 动态分析流程（Master + Specialist） | ⏳ 待开始 | 新增：`specialists/` 目录；废弃旧 Agent 文件 |
| **5.7** | Reflection | ⏳ 待开始 | 新增：`reflection_engine.py` `message_bus.py` |
| **5.8** | 前端适配 | ⏳ 待开始 | 修改：前端报告详情页 |

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

*本文档为 Phase 5 的完整技术规划，随着开发进展持续更新。当前下一步：Phase 5.2（MCP 工具注册表）。*
