"""
Agent 可调用的 Tool 集合

每个 Tool 是一个异步函数，接收结构化参数，返回结构化结果。
Phase 5 中这些 Tool 会被自动转换为 LLM Function Calling 的 JSON Schema。
"""
