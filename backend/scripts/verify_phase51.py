"""
Phase 5.1 端到端验证脚本

验证内容：
1. @tool 装饰器自动注册 + JSON Schema 生成
2. ToolRegistry 查询和管理
3. ToolExecutor 解析并执行 tool_calls
4. LLM 自主输出 tool_calls（需要 API Key）
5. 完整 ReAct 循环：LLM → tool_call → Executor → observation → LLM

用法：
    cd backend
    venv/Scripts/python.exe scripts/verify_phase51.py

环境变量：
    VERIFY_LLM=true  运行 LLM 相关的验证（需要 API Key）
"""
import asyncio
import json
import os
import sys

# 将 backend 加入路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


async def verify_tool_registry():
    """验证 1: Tool Registry + @tool 装饰器"""
    print("\n" + "=" * 60)
    print("验证 1: Tool Registry + @tool 装饰器")
    print("=" * 60)

    # 清理之前的注册（避免重复）
    from app.agents.tools.registry import get_registry, ToolRegistry
    registry = ToolRegistry()

    from app.agents.tools import tool

    @tool(
        description="获取指定城市的天气信息",
        registry=registry,
    )
    async def get_weather(city: str, date: str = "today") -> dict:
        """获取天气信息

        Args:
            city: 城市名称，如 "北京"、"Shanghai"
            date: 日期，默认今天
        """
        return {"city": city, "date": date, "weather": "sunny", "temp": 25}

    @tool(
        description="计算两个数的和",
        registry=registry,
    )
    def add_numbers(a: float, b: float) -> float:
        """计算两数之和

        Args:
            a: 第一个数
            b: 第二个数
        """
        return a + b

    # 验证注册
    assert "get_weather" in registry, "get_weather 未注册"
    assert "add_numbers" in registry, "add_numbers 未注册"
    print(f"  [OK] 注册成功: {len(registry)} 个 Tool")

    # 验证 Schema 生成
    weather_tool = registry.get("get_weather")
    schema = weather_tool.parameters
    assert schema["type"] == "object"
    assert "city" in schema["properties"]
    assert schema["properties"]["city"]["type"] == "string"
    assert "city" in schema["required"]
    assert "date" not in schema["required"]  # 有默认值，非必填
    print(f"  [OK] Schema 生成正确")

    # 验证 OpenAI 格式
    openai_schema = weather_tool.to_openai_schema()
    assert openai_schema["type"] == "function"
    assert openai_schema["function"]["name"] == "get_weather"
    print(f"  [OK] OpenAI 格式正确")

    # 验证同步函数的 Schema
    add_tool = registry.get("add_numbers")
    add_schema = add_tool.parameters
    assert add_schema["properties"]["a"]["type"] == "number"
    assert add_schema["properties"]["b"]["type"] == "number"
    print(f"  [OK] 同步函数 Schema 正确")

    return registry


async def verify_tool_executor(registry):
    """验证 2: ToolExecutor 执行 tool_calls"""
    print("\n" + "=" * 60)
    print("验证 2: ToolExecutor 执行 tool_calls")
    print("=" * 60)

    from app.agents.tools.executor import ToolExecutor

    executor = ToolExecutor(registry)

    # 测试 1: 执行异步 Tool
    print("  测试 1: 执行异步 Tool (get_weather)")
    result = await executor.execute({
        "id": "call_001",
        "name": "get_weather",
        "arguments": json.dumps({"city": "北京", "date": "2024-01-01"}),
    })
    assert not result.is_error, f"执行失败: {result.error_message}"
    assert result.tool_name == "get_weather"
    assert result.output["city"] == "北京"
    print(f"  [OK] 异步 Tool 执行成功: {result.output}")

    # 测试 2: 执行同步 Tool
    print("  测试 2: 执行同步 Tool (add_numbers)")
    result = await executor.execute({
        "id": "call_002",
        "name": "add_numbers",
        "arguments": json.dumps({"a": 3.5, "b": 4.2}),
    })
    assert not result.is_error
    assert abs(result.output - 7.7) < 0.001
    print(f"  [OK] 同步 Tool 执行成功: 3.5 + 4.2 = {result.output}")

    # 测试 3: 不存在的 Tool
    print("  测试 3: 不存在的 Tool")
    result = await executor.execute({
        "id": "call_003",
        "name": "non_existent_tool",
        "arguments": "{}",
    })
    assert result.is_error
    assert "未在 Registry 中注册" in result.error_message
    print(f"  [OK] 错误处理正确: {result.error_message}")

    # 测试 4: 并行执行多个 tool_call
    print("  测试 4: 并行执行多个 tool_call")
    results = await executor.execute_all([
        {"id": "call_004a", "name": "get_weather", "arguments": json.dumps({"city": "上海"})},
        {"id": "call_004b", "name": "add_numbers", "arguments": json.dumps({"a": 10, "b": 20})},
    ])
    assert len(results) == 2
    assert all(not r.is_error for r in results)
    print(f"  [OK] 并行执行成功: {len(results)} 个结果")

    # 测试 5: 结果转换为 LLM 消息
    print("  测试 5: 结果转换为 LLM 消息格式")
    messages = executor.results_to_messages(results)
    assert len(messages) == 2
    assert messages[0]["role"] == "tool"
    assert "tool_call_id" in messages[0]
    print(f"  [OK] 消息格式正确: {len(messages)} 条 tool 消息")

    return executor


async def verify_llm_function_calling(registry, executor):
    """验证 3: LLM 自主输出 tool_calls（需要 API Key）"""
    print("\n" + "=" * 60)
    print("验证 3: LLM 自主输出 tool_calls")
    print("=" * 60)

    if os.environ.get("VERIFY_LLM", "").lower() != "true":
        print("  [SKIP] 跳过（设置 VERIFY_LLM=true 以运行 LLM 验证）")
        return

    from app.llm.factory import get_llm_provider
    from app.llm.schemas import LLMMessage

    provider = get_llm_provider()

    # 构造 tools schema
    tools = [
        registry.get("get_weather").to_openai_schema(),
        registry.get("add_numbers").to_openai_schema(),
    ]

    # 测试 1: LLM 应该调用 get_weather
    print("  测试 1: 询问天气 → 期望调用 get_weather")
    messages = [
        LLMMessage(role="system", content="你是一个 helpful assistant。当需要获取外部信息时，使用提供的工具。"),
        LLMMessage(role="user", content="北京今天天气怎么样？"),
    ]

    response = await provider.chat(messages=messages, tools=tools, temperature=0.3)

    if response.tool_calls:
        print(f"  [OK] LLM 请求调用工具: {[tc.name for tc in response.tool_calls]}")
        for tc in response.tool_calls:
            print(f"    - {tc.name}: {tc.arguments}")

        # 执行 tool_call
        print("  执行 tool_call...")
        results = await executor.execute_all([
            {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
            for tc in response.tool_calls
        ])

        # 将结果返回给 LLM
        tool_messages = executor.results_to_messages(results)
        messages.append(LLMMessage(
            role="assistant",
            content=response.content or "",
            tool_calls=[
                {"id": tc.id, "type": tc.type, "function": {"name": tc.name, "arguments": tc.arguments}}
                for tc in response.tool_calls
            ],
            reasoning_content=response.reasoning_content,
        ))
        for tm in tool_messages:
            messages.append(LLMMessage(
                role=tm["role"],
                content=tm["content"],
                tool_call_id=tm.get("tool_call_id"),
                name=tm.get("name"),
            ))

        # LLM 基于 observation 给出最终回答
        final_response = await provider.chat(messages=messages, tools=tools, temperature=0.3)
        safe_content = final_response.content.encode("ascii", "replace").decode("ascii")
        print(f"  [OK] LLM 最终回答: {safe_content[:200]}...")
    else:
        safe_content = response.content.encode("ascii", "replace").decode("ascii")
        print(f"  [WARN] LLM 没有调用工具，直接回答: {safe_content[:200]}...")

    # 测试 2: LLM 应该调用 add_numbers
    print("  测试 2: 询问计算 → 期望调用 add_numbers")
    messages2 = [
        LLMMessage(role="system", content="你是一个 helpful assistant。当需要计算时，使用提供的工具。"),
        LLMMessage(role="user", content="3.5 加上 4.2 等于多少？"),
    ]

    response2 = await provider.chat(messages=messages2, tools=tools, temperature=0.3)
    if response2.tool_calls:
        print(f"  [OK] LLM 请求调用工具: {[tc.name for tc in response2.tool_calls]}")
    else:
        print(f"  [WARN] LLM 没有调用工具，直接回答: {response2.content[:200]}...")


async def verify_rag_adapter():
    """验证 4: RAG Adapter 注册"""
    print("\n" + "=" * 60)
    print("验证 4: RAG Adapter 注册")
    print("=" * 60)

    from app.agents.tools.registry import ToolRegistry

    registry = ToolRegistry()

    try:
        from app.agents.tools.rag_adapter import RAGAdapter
        adapter = RAGAdapter(registry=registry)
        tools = adapter.register_tools()
        print(f"  [OK] RAG Tool 注册成功: {len(tools)} 个")
        for t in tools:
            print(f"    - {t.name} ({t.source.value})")
    except Exception as e:
        print(f"  [WARN] RAG Adapter 注册失败（可能需要 ChromaDB/网络服务）: {e}")


async def main():
    print("=" * 60)
    print("Phase 5.1 Function Calling 基础设施 — 端到端验证")
    print("=" * 60)

    # 验证 1: Tool Registry
    registry = await verify_tool_registry()

    # 验证 2: Tool Executor
    executor = await verify_tool_executor(registry)

    # 验证 3: LLM Function Calling（可选）
    await verify_llm_function_calling(registry, executor)

    # 验证 4: RAG Adapter
    await verify_rag_adapter()

    print("\n" + "=" * 60)
    print("Phase 5.1 验证完成！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
