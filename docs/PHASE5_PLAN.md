# Phase 5：真正的 Agent 架构重构 — 技术规划

> 版本：v1.0
> 日期：2026-05-29
> 状态：规划中，尚未开始编码
>
> 本文档聚焦 Phase 5 的完整技术方案，Phase 0~4 已完成内容见 `PROJECT_PLAN.md`。

---

## 1. 背景与目标

### 1.1 Phase 3/4 遗留的核心问题

Phase 3 是"伪 Agent"——Orchestrator 硬编码调度 4 个 Agent，工具调用在 Python 代码层完成，LLM 只负责"评分增强"和"写报告"。具体问题：

| # | 问题 | 根因 | 影响 |
|---|------|------|------|
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
│  LAYER 1: Tool 基础设施层（5.1 ~ 5.3）                       │
│  统一 Tool 协议 + Registry + Executor                       │
│  + MCP Adapter + RAG Adapter + LLM Provider 扩展            │
└─────────────────────────────────────────────────────────────┘
```

**设计原则**：
1. **先造枪、再打仗**：5.1~5.3 先建好 Tool 层，5.4~5.7 再构建编排和 Multi-Agent
2. **不预设固定分工**：不硬编码"4 个维度"，LLM 根据项目特点动态决定分析重点
3. **数据只采一次**：Shared Memory 缓存机制，所有 Agent/Tool 共享采集结果
4. **向前兼容**：5.1~5.3 的代码不破坏现有 Orchestrator 流程，5.6 才废弃旧 Agent

---

## 3. 第一层：Tool 基础设施（5.1 ~ 5.3）

### 3.1 核心抽象：Tool 协议

所有能力——本地 Python 函数、MCP Server 的远程工具、RAG 知识库检索——统一抽象为 `Tool` 对象：

```python
@dataclass
class Tool:
    """工具的一等公民抽象

    LLM 看到的就是 {name, description, parameters}，
    不需要关心工具是本地跑的还是远程调用的。
    """
    name: str                    # 唯一标识，如 "github.get_repo_metadata"
    description: str             # LLM 决定"什么时候用"的依据
    parameters: dict             # JSON Schema，描述参数结构
    handler: Callable            # 实际执行函数
    source: ToolSource           # LOCAL / MCP / RAG
```

### 3.2 ToolRegistry + 自动 Schema 生成

```python
class ToolRegistry:
    """工具注册中心

    支持三种注册方式：
    1. @tool 装饰器 — 自动从函数签名生成 JSON Schema
    2. register_mcp_tools() — 从 MCP Server 动态发现
    3. register_rag_tools() — 将 RAG 检索封装为 Tool
    """

# 使用示例：本地工具注册
@tool(description="查询某类项目的行业基准数据")
def get_benchmark(project_type: str, metric_name: str = "") -> list[dict]:
    ...
# → 自动生成 JSON Schema，自动注册到 Registry
```

**自动 Schema 生成**通过 `inspect.signature` + docstring 解析实现，新增工具零配置接入。

### 3.3 ToolExecutor

```python
class ToolExecutor:
    """解析 LLM 返回的 tool_calls，执行对应工具，返回 observation"""

    async def execute(self, tool_call: dict) -> ToolResult:
        # 1. 从 Registry 查找 Tool
        # 2. 解析参数
        # 3. 调用 handler
        # 4. 序列化结果为 observation 字符串
        # 5. 记录调用日志（用于前端展示轨迹）
```

### 3.4 MCP Adapter

将 MCP Server 的工具自动转换为 `Tool` 对象：

```python
class MCPAdapter:
    """连接 MCP Server → list_tools() → 每个工具包装为 Tool"""

    async def discover_tools(self, client: MCPClient) -> list[Tool]:
        tools = await client.list_tools()
        return [self._convert(t) for t in tools]

    def _convert(self, mcp_tool: dict) -> Tool:
        # MCP Tool 的 name/description/inputSchema
        # → Tool 的 name/description/parameters
        # handler 内部调用 client.call_tool()
```

### 3.5 RAG Adapter

将 `RAGQueryEngine` 的检索能力封装为 LLM 可调用的 Tool：

| Tool 名称 | 功能 | 解决 Phase 3/4 的什么问题 |
|-----------|------|------------------------|
| `rag.query_knowledge` | 语义检索知识库 | #1 RAG 内容未进入 LLM Prompt |
| `rag.get_benchmark` | 查询行业基准数据 | #5 基准数据未利用 |
| `rag.get_competitors` | 检索竞品对比信息 | #2 硬编码查询角度 |

**关键改进**：`rag.query_knowledge` 返回**完整文档内容**（不是标题），LLM 自主判断引用哪些段落支撑结论。

### 3.6 LLM Provider 扩展

在 `LLMProvider.chat()` 中新增 `tools` 参数：

```python
async def chat(
    self,
    messages: list[LLMMessage],
    tools: list[Tool] | None = None,   # 新增
    ...
) -> LLMResponse:
    ...
```

`LLMResponse` 扩展 `tool_calls` 字段，承载 LLM 要求的工具调用。

---

## 4. 第二层：编排引擎（5.4 ~ 5.5）

### 4.1 为什么不选纯 ReAct

纯 ReAct 的缺陷：
- **无全局视野**：LLM 每轮只能基于当前观察做下一步决策，容易遗漏关键步骤
- **并行度低**：每次只能做一个 Action，GitHub API 串行太慢
- **易局部循环**：反复调用同一个 Tool 获取相同数据

### 4.2 Plan-and-Execute + ReAct 混合模式

```
用户提交仓库地址
    │
    ▼
┌─────────────────┐     1 轮 LLM
│  Plan 阶段      │     LLM 制定全局分析计划
│  (全局规划)      │     需要哪些数据、调用哪些工具、依赖关系
└─────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Execute 阶段（ReAct Loop + 依赖感知并行）                    │
│                                                              │
│  每轮：                                                       │
│    1. 从 Plan 提取当前可执行的步骤（dependencies 已满足）     │
│    2. 并行调用这些步骤涉及的 Tool（1 轮可能触发 N 个 Tool）   │
│    3. 收集 Observation → 存入 Shared Memory                 │
│    4. LLM Thought：基于新数据，下一轮调用什么？               │
│                                                              │
│  终止：Plan 全部完成 或 max_iterations                       │
└─────────────────────────────────────────────────────────────┘
```

**Plan 数据结构**：

```python
class AnalysisPlan(BaseModel):
    class Step(BaseModel):
        step_id: str
        description: str
        tools: list[str]
        dependencies: list[str]    # 空列表 = 可立即并行执行
        output_key: str
        is_optional: bool = False

    steps: list[Step]
    rationale: str               # LLM 为什么这样规划
```

**依赖感知并行**：`dependencies` 为空的步骤 → 代码层自动识别为可并行 → `asyncio.gather` 同时调用。

### 4.3 数据缓存（Shared Memory）

```python
class SharedMemory:
    """执行过程中的数据缓存

    所有 Tool 调用结果按 "tool_name:serialized_args" 缓存。
    同一数据只采集一次，各步骤共享。
    """
    _cache: dict[str, Any] = {}

    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any) -> None: ...
```

**效果**：Plan 中两个步骤都需要 `github.get_repo_metadata` → 第二次直接从缓存读取，零延迟。

### 4.4 执行上下文

```python
class ExecuteContext:
    """单次分析任务的完整执行状态"""

    plan: AnalysisPlan
    completed_steps: set[str]
    failed_steps: dict[str, str]     # step_id → error
    data_cache: SharedMemory
    trace: list[TraceEvent]          # 执行轨迹（用于前端展示）
```

**错误恢复**：Tool 失败时 → 记录到 `failed_steps` → 依赖该步骤的后续 optional 步骤自动跳过 → LLM 动态调整 Plan。

---

## 5. 第三层：Multi-Agent 协作（5.6 ~ 5.7）

### 5.1 架构：Single Master + Dynamic Specialist Pool

不是"固定 4 个 Agent 永远并行"，而是：

```
Master Agent（Orchestrator）
  │
  ├─ 制定 Plan
  ├─ 调用 Tools 采集数据（通过 Function Calling）
  ├─ 判断是否需要启动 Specialist Agent
  │     │
  │     ├─ 常规分析 → Master Agent 自己推理
  │     └─ 复杂场景 → 启动 Specialist
  │           ├─ Security Specialist（深度安全分析）
  │           ├─ Community Specialist（深度社区分析）
  │           └─ ...
  │
  ├─ Reflection（自我检查）
  └─ Report（生成最终报告）
```

**启动 Specialist 的触发条件**：
- 安全敏感库（密码学、认证）→ 启动 Security Specialist
- 超大型项目（Kubernetes、React）→ 启动 Community Specialist
- 小众技术栈 → 启动 Evolution Specialist
- 个人小项目 → 可能不需要 Specialist

### 5.2 Shared Memory 数据协议

所有 Agent 共享数据缓存：

```python
class SharedMemory:
    raw_data: dict[str, Any]         # Tool 调用结果
    insights: dict[str, list]        # 各 Agent 的分析结论
    messages: list[AgentMessage]     # Agent 间消息
    trace: list[TraceEvent]          # 执行轨迹
```

**数据流**：Master Agent 调 GitHub API → 结果存入 `raw_data` → Specialist 读取分析 → 结论写入 `insights`。

### 5.3 Message Bus（Agent 间通信）

```python
@dataclass
class AgentMessage:
    from_agent: str
    to_agent: str
    type: str           # "attention" / "request" / "response"
    content: str
```

**协作场景**：Community Specialist 发现"核心维护者活跃度下降" → 向 Security Specialist 发送 `attention` 消息："请重点检查该维护者负责模块的安全漏洞修复速度"。

### 5.4 Reflection 机制

```python
class ReflectionEngine:
    """LLM 自我检查分析质量"""

    async def reflect(self, context: ExecuteContext) -> ReflectionResult:
        # 1. 构造反思 Prompt
        # 2. LLM 判断：是否有遗漏？是否有矛盾？
        # 3. 发现遗漏 → 生成补充 Plan → 回到 Execute 层
        # 4. 发现矛盾 → 主动解释 → 修正结论
```

---

## 6. 前端适配（5.8）

| 功能 | 展示内容 |
|------|---------|
| Agent 思维链 | Thought → Action → Observation 折叠面板 |
| 工具调用轨迹 | 时间线形式展示调用了哪些 Tool、参数、返回结果 |
| 反思记录 | 高亮 LLM 自我修正的环节 |
| 动态分析维度 | 显示 LLM 为当前项目选择的分析重点和权重 |
| Plan 可视化 | 展示 LLM 制定的分析计划（步骤 + 依赖关系图） |

---

## 7. 子阶段规划与验收标准

| 子阶段 | 核心目标 | 涉及文件（新增/修改） | 验收标准 |
|--------|---------|---------------------|---------|
| **5.1** | Function Calling 基础设施 | 新增：`tool.py` `registry.py` `executor.py` `mcp_adapter.py` `rag_adapter.py`；修改：`schemas.py` `base.py` `providers.py` `benchmark_tool.py` | ① 定义 Tool，LLM 能自主输出 `tool_call` ② Tool 执行结果正确返回 ③ `@tool` 装饰器自动生成 JSON Schema |
| **5.2** | MCP 工具注册表 | 修改：`mcp_adapter.py` `registry.py` | ① LLM 看到仓库地址后能自主选择调用 `github.get_repo_metadata` ② 工具描述足够清晰，LLM 不会选错 |
| **5.3** | RAG 工具化 | 修改：`rag_adapter.py` `query.py` | ① `rag.query_knowledge` 返回完整 content 进入 LLM Prompt ② LLM 能调用 `rag.get_benchmark` 获取基准数据并引用 |
| **5.4** | Plan-and-Execute | 新增：`plan_engine.py` `execute_engine.py` `shared_memory.py` | ① LLM 制定 Plan 包含步骤和依赖关系 ② 无依赖步骤自动并行执行 ③ 同一 GitHub API 只请求一次 |
| **5.5** | ReAct Loop 升级 | 修改：`execute_engine.py` | ① 单次分析 ReAct 轮次中位数 8~15 轮 ② LLM 不会无意义循环 |
| **5.6** | 动态分析流程 | 新增：`specialists/` 目录；废弃：`community_agent.py` `quality_agent.py` `security_agent.py` `evolution_agent.py` | ① 分析 `openssl` 自动加强安全维度 ② 分析小项目自动简化流程 ③ Synthesis 不再截断信息 |
| **5.7** | Reflection | 新增：`reflection_engine.py` `message_bus.py` | ① 30% 以上任务通过反思发现遗漏 ② 反思日志存入数据库 |
| **5.8** | 前端适配 | 修改：前端报告详情页 | ① 展示思维链 + 工具轨迹 + 反思记录 |

---

## 8. 代码迁移路径

### 8.1 新增文件清单

```
backend/app/agents/
  ├── tools/
  │   ├── tool.py              # Tool 数据模型 + ToolSource 枚举
  │   ├── registry.py          # ToolRegistry + @tool 装饰器
  │   ├── executor.py          # ToolExecutor
  │   ├── mcp_adapter.py       # MCPAdapter：MCP Tool → Tool
  │   └── rag_adapter.py       # RAGToolAdapter：RAG → Tool
  ├── plan_engine.py           # Plan 生成引擎（5.4）
  ├── execute_engine.py        # Execute 执行引擎（5.4~5.5）
  ├── shared_memory.py         # 共享数据缓存（5.4）
  ├── message_bus.py           # Agent 间消息传递（5.7）
  ├── reflection_engine.py     # 反思引擎（5.7）
  └── specialists/             # Specialist Agent 目录（5.6）
      ├── __init__.py
      ├── base.py              # SpecialistAgent 基类
      ├── security_specialist.py
      ├── community_specialist.py
      └── evolution_specialist.py
```

### 8.2 修改文件清单

```
backend/app/llm/schemas.py     # 新增 ToolCall、ToolResult 模型
backend/app/llm/base.py        # chat() 新增 tools 参数
backend/app/llm/providers.py   # 底层传入 tools 到 OpenAI API
backend/app/agents/tools/benchmark_tool.py   # 添加 @tool 装饰器
backend/app/agents/tools/__init__.py         # 导出所有 Tool 相关类
```

### 8.3 废弃文件清单（Phase 5.6 执行）

```
backend/app/agents/community_agent.py    → 功能拆入 Master + Community Specialist
backend/app/agents/quality_agent.py      → 功能拆入 Master + Tool 层
backend/app/agents/security_agent.py     → 功能拆入 Master + Security Specialist
backend/app/agents/evolution_agent.py    → 功能拆入 Master + Evolution Specialist
backend/app/agents/synthesis_agent.py    → 功能合并入 Master Agent 的 Report 阶段
backend/app/agents/llm_enhancer.py       → 功能由 Tool 层替代
```

**注意**：5.1~5.5 阶段**不删除**上述文件，5.6 完成后再统一清理。

---

## 9. 面试叙事框架（Phase 5 完整版）

### 9.1 项目介绍（30 秒）

> "我做了一个开源项目尽调平台，核心是把 VC 做公司尽调的方法论搬到开源项目上。Phase 5 之前是'伪 Agent'——硬编码调度 4 个 Agent，LLM 只负责填空。Phase 5 我重构成真正的 Agent 架构：LLM 自主规划分析路径、自主调用 MCP 工具、自主检索知识库做基准对比、自主反思修正。"

### 9.2 技术亮点（2 分钟）

> "Phase 5 有四个设计值得一提：
> 1. **统一的 Tool 基础设施**：我把本地 Python 函数、远程 MCP Server 工具、RAG 知识库检索抽象为同一套 `Tool` 接口。新增工具只需要加 `@tool` 装饰器，JSON Schema 通过 `inspect.signature` 自动生成，零配置接入。
> 2. **Plan-and-Execute + ReAct 混合编排**：不是纯 ReAct（没有全局视野），也不是纯 Plan（计划一旦制定难以调整）。LLM 先制定全局计划，代码层分析依赖图自动并行化无依赖的步骤，执行过程中 LLM 通过 ReAct 做局部决策。同一数据只采集一次，通过 Shared Memory 共享。
> 3. **Dynamic Specialist Pool**：不硬编码'4 个 Agent 永远并行'，而是 Master Agent 按需启动 Specialist。分析密码学库时自动启动 Security Specialist，分析个人小项目时自动简化流程。Agent 之间通过 Message Bus 协作，一个 Specialist 的发现可以触发另一个 Specialist 的重新验证。
> 4. **RAG 真正参与推理**：Phase 4 的 RAG 只是'检索了→存了→展示了标题'。Phase 5 把 RAG 检索封装为 LLM 可调用的 Tool，检索到的完整文档内容进入 LLM 的上下文窗口，LLM 自主判断引用哪些段落支撑结论。"

### 9.3 量化成果（可验证的指标）

> "重构后：分析完成时间从 2 分钟降到 1.5 分钟（并行度提升 + 数据缓存）；RAG 检索内容 100% 进入 LLM Prompt（Phase 4 是 0%）；GitHub API 重复请求从平均 2.3 次降到 1 次。"

---

*本文档为 Phase 5 的完整技术规划，随着开发进展持续更新。当前下一步：Phase 5.1（Function Calling 基础设施）。*
