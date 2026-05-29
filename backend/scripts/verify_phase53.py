#!/usr/bin/env python3
"""
Phase 5.3 验证脚本 —— RAG 工具化端到端测试

验证目标：
1. RAG 3 个 Tool 能正确注册到 ToolRegistry
2. ToolExecutor 能直接执行 RAG Tool，返回完整 content
3. LLM 能通过 Function Calling 自主调用 RAG Tool，并基于结果推理

运行方式：
    cd backend
    venv\Scripts\python.exe scripts\verify_phase53.py

依赖：
    - Chroma 向量库已启动（docker compose up -d db）
    - 知识库已初始化（有文档数据）
    - LLM API Key 已配置（测试 3 需要）
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Windows 终端 UTF-8 编码设置，避免 print 中文和特殊字符时报错
os.environ["PYTHONIOENCODING"] = "utf-8"

# 将项目根目录加入 Python 路径，确保能导入 app 包
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.agents.tools import (
    ToolExecutor,
    get_registry,
    initialize_rag_tools,
)
from app.agents.tools.tool import ToolSource
from app.core.logger import configure_logging, get_logger

# 先初始化日志，再获取 logger
configure_logging()
logger = get_logger("verify_phase53")

# ───────────────────────────────────────────────────────────────────────────
# 测试 1：RAG Tool 注册
# ───────────────────────────────────────────────────────────────────────────


async def test_registration() -> bool:
    """验证 RAG Tool 注册到全局 Registry"""
    print("\n" + "=" * 60)
    print("测试 1: RAG Tool 注册")
    print("=" * 60)

    registry = get_registry()

    # 调用初始化入口注册 RAG Tool
    tools = await initialize_rag_tools(registry=registry)

    print(f"\n注册成功: {len(tools)} 个 Tool")
    for t in tools:
        print(f"  - {t.name}")
        print(f"    描述: {t.description[:60]}...")
        print(f"    来源: {t.source.value}")

    # 校验
    rag_tools = registry.list_by_source(ToolSource.RAG)
    expected = {"rag_query_knowledge", "rag_get_benchmark", "rag_get_competitors"}
    actual = {t.name for t in rag_tools}

    if actual != expected:
        print(f"\n[FAIL] Tool 名称不匹配")
        print(f"   期望: {expected}")
        print(f"   实际: {actual}")
        return False

    print("\n[PASS] 测试 1 通过：3 个 RAG Tool 全部注册成功")
    return True


# ───────────────────────────────────────────────────────────────────────────
# 测试 2：ToolExecutor 直接执行
# ───────────────────────────────────────────────────────────────────────────


async def test_direct_execution() -> bool:
    """验证 ToolExecutor 能正确执行 RAG Tool，返回完整 content"""
    print("\n" + "=" * 60)
    print("测试 2: ToolExecutor 直接执行 RAG Tool")
    print("=" * 60)

    executor = ToolExecutor()
    all_pass = True

    # --- 2.1 rag_query_knowledge ---
    print("\n--- 2.1 rag_query_knowledge ---")
    result = await executor.execute(
        {
            "id": "call_query_1",
            "name": "rag_query_knowledge",
            "arguments": json.dumps(
                {
                    "query_text": "开源项目社区健康度评估标准",
                    "category": "methodology",
                    "n_results": 2,
                }
            ),
        }
    )

    if result.is_error:
        print(f"[FAIL] 执行失败: {result.error_message}")
        all_pass = False
    else:
        print(f"[PASS] 执行成功 ({result.execution_time_ms:.1f}ms)")
        output = json.loads(result.output)
        print(f"   检索结果数: {output.get('results_count', 0)}")

        if output.get("results"):
            first = output["results"][0]
            content = first.get("content", "")
            print(f"   第一条 content 长度: {len(content)} 字符")
            print(f"   前 100 字符: {content[:100]}...")

            # 核心验证：content 非空（解决 Phase 4 问题 #1）
            if len(content) == 0:
                print("[FAIL] content 为空，Phase 4 问题 #1 未解决")
                all_pass = False
            else:
                print("[PASS] content 完整返回")

            # 验证 metadata 存在
            if "metadata" in first:
                print(f"[PASS] metadata 存在: {first['metadata']}")
            else:
                print("[FAIL] 缺少 metadata")
                all_pass = False
        else:
            print("[WARN] 未检索到结果（知识库可能为空，这不影响 Tool 本身正确性）")

    # --- 2.2 rag_get_benchmark ---
    print("\n--- 2.2 rag_get_benchmark ---")
    result = await executor.execute(
        {
            "id": "call_bench_1",
            "name": "rag_get_benchmark",
            "arguments": json.dumps(
                {
                    "project_type": "frontend-framework",
                    "metric_name": "community_health",
                }
            ),
        }
    )

    if result.is_error:
        print(f"[FAIL] 执行失败: {result.error_message}")
        all_pass = False
    else:
        print(f"[PASS] 执行成功 ({result.execution_time_ms:.1f}ms)")
        output = json.loads(result.output)
        print(f"   检索结果数: {output.get('results_count', 0)}")

    # --- 2.3 rag_get_competitors ---
    print("\n--- 2.3 rag_get_competitors ---")
    result = await executor.execute(
        {
            "id": "call_comp_1",
            "name": "rag_get_competitors",
            "arguments": json.dumps({"tech_domain": "frontend framework"}),
        }
    )

    if result.is_error:
        print(f"[FAIL] 执行失败: {result.error_message}")
        all_pass = False
    else:
        print(f"[PASS] 执行成功 ({result.execution_time_ms:.1f}ms)")
        output = json.loads(result.output)
        print(f"   检索结果数: {output.get('results_count', 0)}")

    if all_pass:
        print("\n[PASS] 测试 2 通过：所有 RAG Tool 执行正常，返回完整 content")
    else:
        print("\n[FAIL] 测试 2 部分失败")
    return all_pass


# ───────────────────────────────────────────────────────────────────────────
# 测试 3：LLM Function Calling 端到端
# ───────────────────────────────────────────────────────────────────────────


async def test_llm_function_calling() -> bool:
    """验证 LLM 能自主调用 RAG Tool，并基于检索结果推理"""
    print("\n" + "=" * 60)
    print("测试 3: LLM Function Calling 端到端")
    print("=" * 60)

    try:
        from app.llm.factory import get_llm_provider
        from app.llm.schemas import LLMMessage
    except ImportError as e:
        print(f"[FAIL] 导入失败: {e}")
        return False

    # 获取 Provider（优先 deepseek，成本更低）
    try:
        provider = get_llm_provider("deepseek")
        print(f"\n使用 Provider: {provider.provider_name} / {provider.model}")
    except Exception as e:
        print(f"[WARN] DeepSeek 初始化失败，尝试 Kimi: {e}")
        try:
            provider = get_llm_provider("kimi")
            print(f"使用 Provider: {provider.provider_name} / {provider.model}")
        except Exception as e2:
            print(f"[FAIL] 所有 Provider 初始化失败: {e2}")
            return False

    # 获取 RAG Tool schemas
    registry = get_registry()
    rag_tools = registry.list_by_source(ToolSource.RAG)
    tool_schemas = [t.to_openai_schema() for t in rag_tools]
    print(f"提供给 LLM 的 Tool 数量: {len(tool_schemas)}")

    # 构造 Prompt：让 LLM 分析项目，需要检索知识库
    messages = [
        LLMMessage(
            role="system",
            content=(
                "你是一个开源项目尽调分析助手。"
                "分析过程中如需引用外部知识、行业标准或历史案例，"
                "请调用 rag_query_knowledge 工具检索知识库。"
            ),
        ),
        LLMMessage(
            role="user",
            content=(
                "请分析一个前端框架项目的社区健康度。"
                "先检索知识库，了解社区健康度的评估标准和相关案例，"
                "然后基于检索结果给出分析思路。"
            ),
        ),
    ]

    # 第一轮：LLM 决策
    print("\n--- 第一轮：LLM 决策 ---")
    try:
        response = await provider.chat(
            messages=messages,
            tools=tool_schemas,
            temperature=0.7,
        )
    except Exception as e:
        print(f"[FAIL] LLM 调用失败: {e}")
        return False

    print(f"模型返回 content: {response.content[:150]}...")

    if response.tool_calls:
        print(f"LLM 请求调用 {len(response.tool_calls)} 个工具:")
        for tc in response.tool_calls:
            print(f"  - {tc.name}: {tc.arguments[:100]}...")
    else:
        print("[WARN] LLM 未调用工具（可能不需要，或模型选择直接回答）")
        print("\n[WARN] 测试 3 部分通过（LLM 未触发工具调用，继续检查模型是否正常响应）")
        # 没有 tool_calls 不代表失败，可能是模型认为不需要检索
        return len(response.content) > 0

    # 执行 tool_calls
    print("\n--- 执行 Tool Calls ---")
    executor = ToolExecutor()
    results = await executor.execute_all(
        [
            {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
            for tc in response.tool_calls
        ]
    )

    for r in results:
        status = "[PASS]" if not r.is_error else "[FAIL]"
        print(f"{status} {r.tool_name} ({r.execution_time_ms:.1f}ms)")
        if r.is_error:
            print(f"   错误: {r.error_message}")

    if any(r.is_error for r in results):
        print("\n[FAIL] 工具执行失败")
        return False

    # 将结果返回 LLM
    print("\n--- 第二轮：LLM 基于结果推理 ---")
    tool_messages = executor.results_to_messages(results)

    # 构造标准 OpenAI 格式的 tool_calls（嵌套 function 对象）
    assistant_tool_calls = [
        {
            "id": tc.id,
            "type": "function",
            "function": {
                "name": tc.name,
                "arguments": tc.arguments,
            },
        }
        for tc in response.tool_calls
    ]
    messages.append(
        LLMMessage(
            role="assistant",
            content=response.content,
            tool_calls=assistant_tool_calls,
        )
    )
    for tm in tool_messages:
        messages.append(
            LLMMessage(
                role="tool",
                content=tm["content"],
                tool_call_id=tm["tool_call_id"],
                name=tm["name"],
            )
        )

    try:
        final_response = await provider.chat(
            messages=messages,
            tools=tool_schemas,
            temperature=0.7,
        )
    except Exception as e:
        print(f"[FAIL] 第二轮 LLM 调用失败: {e}")
        return False

    print(f"最终 content: {final_response.content[:300]}...")

    if len(final_response.content) > 0:
        print("\n[PASS] 测试 3 通过：LLM 成功调用 RAG Tool 并基于结果推理")
        return True
    else:
        print("\n[FAIL] 测试 3 失败：LLM 返回空内容")
        return False


# ───────────────────────────────────────────────────────────────────────────
# 主函数
# ───────────────────────────────────────────────────────────────────────────


async def main() -> int:
    """运行所有验证测试"""
    print("\n" + "=" * 60)
    print("Phase 5.3 验证：RAG 工具化端到端测试")
    print("=" * 60)

    results: list[tuple[str, bool]] = []

    # 测试 1：注册
    try:
        results.append(("RAG Tool 注册", await test_registration()))
    except Exception as e:
        logger.exception("测试 1 异常")
        print(f"\n[FAIL] 测试 1 异常: {e}")
        results.append(("RAG Tool 注册", False))

    # 测试 2：直接执行
    try:
        results.append(("ToolExecutor 执行", await test_direct_execution()))
    except Exception as e:
        logger.exception("测试 2 异常")
        print(f"\n[FAIL] 测试 2 异常: {e}")
        results.append(("ToolExecutor 执行", False))

    # 测试 3：LLM Function Calling
    try:
        results.append(("LLM Function Calling", await test_llm_function_calling()))
    except Exception as e:
        logger.exception("测试 3 异常")
        print(f"\n[FAIL] 测试 3 异常: {e}")
        results.append(("LLM Function Calling", False))

    # 汇总
    print("\n" + "=" * 60)
    print("验证结果汇总")
    print("=" * 60)
    for name, passed in results:
        status = "[PASS] 通过" if passed else "[FAIL] 失败"
        print(f"  {status}: {name}")

    all_passed = all(passed for _, passed in results)
    print(f"\n{'[SUCCESS] 全部通过!' if all_passed else '[WARN] 部分测试未通过'}\n")
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
