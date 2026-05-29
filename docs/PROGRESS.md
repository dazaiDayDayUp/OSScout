# 项目开发进度记录

> 活文档，只保留当前状态和下一步。详细规划见 [`PROJECT_PLAN.md`](./PROJECT_PLAN.md)，Phase 5 技术方案见 [`PHASE5_PLAN.md`](./PHASE5_PLAN.md)。

---

## 当前状态

**Phase 0~4 全部完成，Phase 5.1、5.2 已完成。当前重点：Phase 5.3（RAG 工具化）。**

最近更新：2026-05-29

---

## Phase 5 进度

| 子阶段 | 内容 | 状态 |
|--------|------|------|
| 5.1 | Function Calling 基础设施（Tool 协议 / Registry / Executor / MCP Adapter / RAG Adapter） | ✅ 已完成 |
| **5.2** | **MCP 工具注册表** | **✅ 已完成** |
| **5.3** | **RAG 工具化** | **⏳ 当前重点** |
| 5.4 | Plan-and-Execute 编排引擎 | ⏳ 待开始 |
| 5.5 | ReAct Loop 升级 | ⏳ 待开始 |
| 5.6 | 动态分析流程（Single Master + Dynamic Specialist Pool） | ⏳ 待开始 |
| 5.7 | Reflection + Message Bus | ⏳ 待开始 |
| 5.8 | 前端适配 | ⏳ 待开始 |

---

## Phase 5.1 成果摘要

- **新增 6 个文件**：`tool.py`、`registry.py`、`executor.py`、`mcp_adapter.py`、`rag_adapter.py`、`verify_phase51.py`
- **修改 5 个文件**：`schemas.py`、`base.py`、`providers.py`、`benchmark_tool.py`、`mcp/client.py`
- **核心能力**：`@tool` 装饰器自动生成 JSON Schema、ToolExecutor 执行 tool_calls、LLM 端到端 Function Calling 验证通过
- **发现 3 个真问题**（仅通过 LLM 调用才发现）：kimi-k2.6 temperature 限制更新为 1.0、tool_calls 消息需要 reasoning_content、LLMMessage 需要扩展字段

---

## 当前阻塞

无。

---

## Phase 5.2 成果摘要

- **修复 `mcp_adapter.py` 的 handler 生命周期问题**：`discover_and_register` 改为接收 `client_class`（类）而非实例，handler 闭包捕获类并在每次调用时新建连接，与"每个 async with 独立实例"设计一致
- **新增 `mcp_registry.py`**：统一批量注册入口
  - `MCP_SERVER_CONFIGS`：声明式配置 4 个 Server
  - `initialize_mcp_tools()`：并行注册，失败隔离
  - `get_mcp_tools_summary()`：注册摘要查询
- **修改 `main.py`**：应用启动时自动初始化 MCP 工具注册
- **验证结果**：4/4 Server 全部成功，15 个 Tool 正确注册

## 下一步

**Phase 5.3：RAG 工具化**

将 RAG 检索能力（`rag.query_knowledge`、`rag.get_benchmark`、`rag.get_competitors`）在应用启动时自动注册到 ToolRegistry。

详见 [`PHASE5_PLAN.md`](./PHASE5_PLAN.md) 第 3 章。
