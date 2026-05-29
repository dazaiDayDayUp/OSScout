# 项目开发进度记录

> 活文档，只保留当前状态和下一步。详细规划见 [`PROJECT_PLAN.md`](./PROJECT_PLAN.md)，Phase 5 技术方案见 [`PHASE5_PLAN.md`](./PHASE5_PLAN.md)。

---

## 当前状态

**Phase 0~4 全部完成，Phase 5.1 已完成。当前重点：Phase 5.2（MCP 工具注册表）。**

最近更新：2026-05-29

---

## Phase 5 进度

| 子阶段 | 内容 | 状态 |
|--------|------|------|
| 5.1 | Function Calling 基础设施（Tool 协议 / Registry / Executor / MCP Adapter / RAG Adapter） | ✅ 已完成 |
| 5.2 | MCP 工具注册表 | ⏳ 待开始 |
| 5.3 | RAG 工具化 | ⏳ 待开始 |
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

## 下一步

**Phase 5.2：MCP 工具注册表**

将 4 个 MCP Server（github-mcp、filesystem-mcp、osv-mcp、code-analysis-mcp）的工具自动发现并注册为 LLM 可调用的 Tool。

详见 [`PHASE5_PLAN.md`](./PHASE5_PLAN.md) 第 3 章。
