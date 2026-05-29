"""
Phase 5.2 MCP 工具注册表 — 验证脚本

验证内容：
1. 4 个 MCP Server 的工具自动发现并注册
2. 注册的 Tool 信息正确（名称格式、描述、参数 Schema）
3. 注册摘要功能正常
4. ToolExecutor 能正确执行 MCP Tool（可选）

用法：
    cd backend
    venv/Scripts/python.exe scripts/verify_phase52.py

注意：
- 此脚本会启动 4 个 MCP Server 子进程，耗时约 10-30 秒
- 需要所有 MCP Server 的依赖已安装（mcp、httpx、radon 等）
- 部分 Server 依赖外部网络（GitHub API、OSV API），网络问题可能导致注册失败
"""
import asyncio
import os
import sys

# 将 backend 加入路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


async def verify_mcp_tool_registration():
    """验证 1: 4 个 MCP Server 的工具自动注册"""
    print("\n" + "=" * 60)
    print("验证 1: MCP 工具自动注册")
    print("=" * 60)

    from app.agents.tools.registry import ToolRegistry
    from app.agents.tools.mcp_registry import (
        MCP_SERVER_CONFIGS,
        initialize_mcp_tools,
        get_mcp_tools_summary,
    )

    # 使用独立 Registry，避免污染全局状态
    registry = ToolRegistry()

    print(f"  配置 Server 数量: {len(MCP_SERVER_CONFIGS)}")
    for cfg in MCP_SERVER_CONFIGS:
        print(f"    - {cfg.display_name} (namespace={cfg.namespace})")

    # 执行注册
    print("\n  开始并行注册...")
    registered = await initialize_mcp_tools(registry=registry)

    # 验证结果
    total_tools = sum(len(tools) for tools in registered.values())
    print(f"\n  注册成功: {total_tools} 个 Tool")

    for namespace, tools in registered.items():
        print(f"    [{namespace}] {len(tools)} 个:")
        for tool in tools:
            print(f"      - {tool.name}")

    # 验证命名空间格式
    for namespace, tools in registered.items():
        for tool in tools:
            assert tool.name.startswith(f"{namespace}."), \
                f"Tool 名称格式错误: {tool.name}"
            assert tool.source.value == "mcp", \
                f"Tool 来源错误: {tool.source}"
            assert "properties" in tool.parameters or "type" in tool.parameters, \
                f"Tool {tool.name} 参数 Schema 格式异常: {tool.parameters}"

    print("  [OK] 所有 Tool 名称格式、来源、参数 Schema 正确")

    return registry, registered


async def verify_mcp_tools_summary(registry):
    """验证 2: 注册摘要功能"""
    print("\n" + "=" * 60)
    print("验证 2: MCP 工具注册摘要")
    print("=" * 60)

    from app.agents.tools.mcp_registry import get_mcp_tools_summary

    summary = get_mcp_tools_summary(registry=registry)

    print(f"  总工具数: {summary['total']}")
    print(f"  按命名空间分布:")
    for ns, count in summary["by_namespace"].items():
        print(f"    - {ns}: {count} 个")

    assert summary["total"] > 0, "没有注册任何 MCP Tool"
    assert len(summary["by_namespace"]) > 0, "命名空间分布为空"
    assert len(summary["tools"]) == summary["total"], "工具详情数量不匹配"

    print("  [OK] 摘要功能正常")

    return summary


async def verify_tool_executor(registry):
    """验证 3: ToolExecutor 执行 MCP Tool（可选，需要网络）"""
    print("\n" + "=" * 60)
    print("验证 3: ToolExecutor 执行 MCP Tool")
    print("=" * 60)

    from app.agents.tools.executor import ToolExecutor
    import json

    executor = ToolExecutor(registry=registry)

    # 尝试执行一个 GitHub Tool（需要网络）
    github_tools = [t for t in registry.list_tools() if t.name.startswith("github.")]

    if not github_tools:
        print("  [SKIP] 没有注册的 GitHub Tool，跳过执行验证")
        return

    # 选择 get_repo_metadata 测试
    test_tool = next((t for t in github_tools if "metadata" in t.name), github_tools[0])
    print(f"  测试工具: {test_tool.name}")

    try:
        result = await executor.execute({
            "id": "call_test_001",
            "name": test_tool.name,
            "arguments": json.dumps({
                "owner": "python",
                "repo": "cpython",
            }),
        })

        if result.is_error:
            # 网络/API 错误是可接受的，只要错误信息正确即可
            print(f"  [INFO] 工具执行返回错误（可能网络/API原因）: {result.error_message[:100]}")
            assert result.tool_name == test_tool.name
            print("  [OK] 错误处理正确")
        else:
            print(f"  [OK] 工具执行成功")
            print(f"    耗时: {result.execution_time_ms:.1f}ms")
            output_preview = str(result.output)[:200] if result.output else "None"
            print(f"    输出预览: {output_preview}")

    except Exception as e:
        print(f"  [INFO] 执行异常（可能网络原因）: {e}")


async def verify_failure_isolation():
    """验证 4: 失败隔离 — 不存在的 Server 不影响其他"""
    print("\n" + "=" * 60)
    print("验证 4: 失败隔离")
    print("=" * 60)

    from app.agents.tools.registry import ToolRegistry
    from app.agents.tools.mcp_registry import MCPServerConfig, initialize_mcp_tools
    from app.mcp.client import _BaseMCPClient

    # 构造一个永远不存在的 Server
    class FakeMCPClient(_BaseMCPClient):
        SERVER_MODULE = "non-existent-server-xxx"

    registry = ToolRegistry()

    configs = [
        MCPServerConfig(
            client_class=FakeMCPClient,
            namespace="fake",
            display_name="Fake Server",
        ),
    ]

    # 尝试注册不存在的 Server，不应抛异常
    try:
        registered = await initialize_mcp_tools(registry=registry, configs=configs)
        assert len(registered) == 0, "不存在的 Server 不应注册成功"
        print("  [OK] 不存在的 Server 注册失败但未抛异常，应用可继续")
    except Exception as e:
        print(f"  [FAIL] 注册异常传播到上层: {e}")
        raise


async def main():
    print("=" * 60)
    print("Phase 5.2 MCP 工具注册表 — 端到端验证")
    print("=" * 60)

    # 验证 1: 工具注册
    registry, registered = await verify_mcp_tool_registration()

    # 验证 2: 摘要
    await verify_mcp_tools_summary(registry)

    # 验证 3: ToolExecutor 执行（可选）
    await verify_tool_executor(registry)

    # 验证 4: 失败隔离
    await verify_failure_isolation()

    print("\n" + "=" * 60)
    print("Phase 5.2 验证完成！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
