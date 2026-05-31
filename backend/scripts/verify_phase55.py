#!/usr/bin/env python3
"""
Phase 5.5 ReAct Loop 端到端验证脚本

验证 ReAct 执行过程中 LLM 动态决策的 6 个验收标准：
1. ReAct 触发: Plan 执行过程中 LLM 被调用做决策
2. Tool 补充: LLM 输出 tool_calls 采集不在原 Plan 中的数据
3. 结果共享: ReAct 调用的 Tool 结果进入 SharedMemory，可被后续步骤使用
4. 终止判断: LLM 可以主动决定终止分析
5. 失败隔离: ReAct 中 Tool 失败不影响循环继续
6. 兼容 5.4: 关闭 react_enabled 时行为与 5.4 完全一致

用法:
    cd backend
    .\\venv\\Scripts\\python.exe .\\scripts\\verify_phase55.py
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 路径设置：确保能导入 backend/app 下的模块
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent.resolve()
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

# ---------------------------------------------------------------------------
# 导入依赖
# ---------------------------------------------------------------------------
from app.agents.orchestration import (
    AnalysisPlan,
    ExecuteEngine,
    PlanStep,
    SharedMemory,
)
from app.agents.tools import ToolExecutor, get_registry, tool
from app.llm.base import LLMProvider
from app.llm.schemas import LLMMessage, LLMResponse, LLMUsage, ToolCall

# ---------------------------------------------------------------------------
# 测试输出
# ---------------------------------------------------------------------------


def ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def info(msg: str) -> None:
    print(f"  [INFO] {msg}")


# ---------------------------------------------------------------------------
# Mock LLM Provider（支持 ReAct 决策）
# ---------------------------------------------------------------------------

class MockReActLLM(LLMProvider):
    """支持 ReAct 决策的 Mock LLM

    通过 decision_sequence 控制每轮 ReAct 的决策输出。
    每个决策可以是：
    - "continue" / "CONTINUE" — 继续执行
    - "terminate" / "TERMINATE:xxx" — 终止分析
    - list[dict] — tool_calls 列表（LLM 输出工具调用）
    """

    def __init__(
        self,
        decision_sequence: list[Any] | None = None,
        reasoning_response: str = "Mock 推理结果",
    ) -> None:
        super().__init__(provider_name="mock", model="mock-react")
        self.decision_sequence = decision_sequence or []
        self.decision_index = 0
        self.reasoning_response = reasoning_response
        self.chat_calls: list[list[LLMMessage]] = []
        self.structured_calls: list[tuple[list[LLMMessage], type]] = []
        # 记录 ReAct 相关的调用
        self.react_chat_calls: list[dict] = []

    async def chat(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
        **kwargs,
    ) -> LLMResponse:
        self.chat_calls.append(messages)

        # 判断是否是 ReAct 决策调用（有 tools 参数且 temperature=0.3）
        is_react = tools is not None and temperature == 0.3

        if is_react and self.decision_index < len(self.decision_sequence):
            decision = self.decision_sequence[self.decision_index]
            self.decision_index += 1

            if isinstance(decision, list):
                # LLM 输出 tool_calls
                tool_calls = [
                    ToolCall(
                        id=tc.get("id", f"call_{i}"),
                        type="function",
                        name=tc["name"],
                        arguments=json.dumps(tc.get("arguments", {})),
                    )
                    for i, tc in enumerate(decision)
                ]
                self.react_chat_calls.append({
                    "type": "tool_calls",
                    "tools": [tc.name for tc in tool_calls],
                })
                return LLMResponse(
                    content="",
                    usage=LLMUsage(),
                    model=self.model,
                    provider=self.provider_name,
                    tool_calls=tool_calls,
                )
            elif isinstance(decision, str):
                # 文本回复（continue / terminate）
                self.react_chat_calls.append({
                    "type": "text",
                    "content": decision,
                })
                return LLMResponse(
                    content=decision,
                    usage=LLMUsage(),
                    model=self.model,
                    provider=self.provider_name,
                )

        # 默认返回（reasoning 步骤或 ReAct 决策耗尽时）
        return LLMResponse(
            content=self.reasoning_response,
            usage=LLMUsage(),
            model=self.model,
            provider=self.provider_name,
        )

    async def chat_structured(
        self,
        messages: list[LLMMessage],
        output_schema: type,
        temperature: float = 0.3,
        max_tokens: int | None = None,
        **kwargs,
    ) -> Any:
        self.structured_calls.append((messages, output_schema))
        if output_schema == AnalysisPlan:
            return AnalysisPlan(steps=[])
        return output_schema()


# ---------------------------------------------------------------------------
# Mock Tool：记录调用次数
# ---------------------------------------------------------------------------

tool_call_counts: dict[str, int] = {}


def reset_tracking() -> None:
    """重置 Tool 调用追踪"""
    tool_call_counts.clear()


@tool(description="获取仓库元数据")
async def mock_get_repo_metadata(owner: str, repo: str) -> dict:
    """获取仓库元数据"""
    tool_call_counts["mock_get_repo_metadata"] = (
        tool_call_counts.get("mock_get_repo_metadata", 0) + 1
    )
    return {
        "owner": owner,
        "repo": repo,
        "stars": 1000,
        "forks": 200,
        "language": "Python",
    }


@tool(description="获取贡献者列表")
async def mock_list_contributors(owner: str, repo: str) -> list[dict]:
    """获取贡献者列表"""
    tool_call_counts["mock_list_contributors"] = (
        tool_call_counts.get("mock_list_contributors", 0) + 1
    )
    return [
        {"login": "alice", "contributions": 50},
        {"login": "bob", "contributions": 30},
    ]


@tool(description="获取安全漏洞扫描")
async def mock_security_scan(owner: str, repo: str) -> dict:
    """ReAct 可能补充调用的 Tool（不在原 Plan 的 needs 中）"""
    tool_call_counts["mock_security_scan"] = (
        tool_call_counts.get("mock_security_scan", 0) + 1
    )
    return {"vulnerabilities": [], "score": 95}


@tool(description="获取最新 Release 信息")
async def mock_get_releases(owner: str, repo: str) -> list[dict]:
    """ReAct 可能补充调用的 Tool"""
    tool_call_counts["mock_get_releases"] = (
        tool_call_counts.get("mock_get_releases", 0) + 1
    )
    return [{"tag": "v1.0.0", "date": "2024-01-01"}]


@tool(description="模拟 ReAct 中失败的 Tool")
async def mock_react_failing_tool(query: str) -> dict:
    """ReAct 调用时失败的 Tool"""
    tool_call_counts["mock_react_failing_tool"] = (
        tool_call_counts.get("mock_react_failing_tool", 0) + 1
    )
    raise RuntimeError("模拟 ReAct Tool 失败")


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------

async def test_1_react_triggered() -> bool:
    """测试 1: ReAct 触发 — Plan 执行过程中 LLM 被调用做决策"""
    print("\n【测试 1】ReAct 触发")

    reset_tracking()

    plan = AnalysisPlan(steps=[
        PlanStep(
            step_id="s1",
            step_type="data",
            needs=["repo_metadata"],
            description="获取仓库信息",
            deps=[],
        ),
        PlanStep(
            step_id="s2",
            step_type="reasoning",
            needs=["repo_metadata"],
            description="评估",
            deps=["s1"],
        ),
    ])

    # LLM 决策序列：第一轮 continue，第二轮 terminate
    llm = MockReActLLM(decision_sequence=[
        "CONTINUE",
        "TERMINATE: 分析完成",
    ])

    registry = get_registry()
    execute_engine = ExecuteEngine(
        registry=registry,
        executor=ToolExecutor(registry=registry),
        llm=llm,
        needs_tool_map={
            "repo_metadata": ["mock_get_repo_metadata"],
        },
    )

    context = {"owner": "test", "repo": "demo", "repo_url": "https://github.com/test/demo"}
    await execute_engine.run(plan, context)

    # 验证：LLM 的 ReAct 决策被调用了
    if len(llm.react_chat_calls) >= 1:
        ok(f"ReAct 决策被触发，共 {len(llm.react_chat_calls)} 次")
    else:
        fail("ReAct 决策未被触发")
        return False

    # 验证：ReAct 调用传入了 tools 参数
    react_call_with_tools = [
        c for c in llm.chat_calls
        if len(c) >= 1 and c[0].role == "system"
    ]
    if react_call_with_tools:
        ok("ReAct 决策调用包含 system prompt")
    else:
        fail("ReAct 决策调用缺少 system prompt")
        return False

    return True


async def test_2_react_tool_calls() -> bool:
    """测试 2: Tool 补充 — LLM 输出 tool_calls 采集不在原 Plan 中的数据"""
    print("\n【测试 2】Tool 补充")

    reset_tracking()

    plan = AnalysisPlan(steps=[
        PlanStep(
            step_id="s1",
            step_type="data",
            needs=["repo_metadata"],
            description="获取仓库信息",
            deps=[],
        ),
    ])

    # LLM 决策：先 continue 执行 s1，然后 tool_calls 补充安全扫描
    llm = MockReActLLM(decision_sequence=[
        "CONTINUE",
        [
            {
                "id": "react_1",
                "name": "mock_security_scan",
                "arguments": {"owner": "test", "repo": "demo"},
            },
        ],
        "TERMINATE: 数据充足",
    ])

    registry = get_registry()
    execute_engine = ExecuteEngine(
        registry=registry,
        executor=ToolExecutor(registry=registry),
        llm=llm,
        needs_tool_map={
            "repo_metadata": ["mock_get_repo_metadata"],
        },
    )

    context = {"owner": "test", "repo": "demo", "repo_url": "https://github.com/test/demo"}
    await execute_engine.run(plan, context)

    # 验证：mock_security_scan 被 ReAct 调用了
    if tool_call_counts.get("mock_security_scan", 0) >= 1:
        ok(f"ReAct 成功补充调用 mock_security_scan")
    else:
        fail("ReAct 未补充调用 mock_security_scan")
        return False

    # 验证：该 Tool 不在原 Plan 的 needs 中
    all_plan_needs = set()
    for step in plan.steps:
        all_plan_needs.update(step.needs)
    if "security_scan" not in all_plan_needs:
        ok("补充调用的 Tool 不在原 Plan 中")

    return True


async def test_3_shared_memory_integration() -> bool:
    """测试 3: 结果共享 — ReAct Tool 结果进入 SharedMemory"""
    print("\n【测试 3】结果共享")

    reset_tracking()

    plan = AnalysisPlan(steps=[
        PlanStep(
            step_id="s1",
            step_type="data",
            needs=["repo_metadata"],
            description="获取仓库信息",
            deps=[],
        ),
    ])

    llm = MockReActLLM(decision_sequence=[
        "CONTINUE",
        [
            {
                "id": "react_1",
                "name": "mock_get_releases",
                "arguments": {"owner": "test", "repo": "demo"},
            },
        ],
        "TERMINATE: 完成",
    ])

    registry = get_registry()
    execute_engine = ExecuteEngine(
        registry=registry,
        executor=ToolExecutor(registry=registry),
        llm=llm,
        needs_tool_map={
            "repo_metadata": ["mock_get_repo_metadata"],
        },
    )

    context = {"owner": "test", "repo": "demo", "repo_url": "https://github.com/test/demo"}
    await execute_engine.run(plan, context)

    # 验证：ReAct 调用的 Tool 结果在 SharedMemory 中
    result = execute_engine.memory.get_tool_result(
        "mock_get_releases", {"owner": "test", "repo": "demo"}
    )
    if result and isinstance(result, list) and result[0].get("tag") == "v1.0.0":
        ok("ReAct Tool 结果正确存入 SharedMemory")
    else:
        # 备选：从所有数据中查找
        all_data = execute_engine.memory.get_all()
        release_keys = [k for k in all_data if "mock_get_releases" in k]
        if release_keys:
            val = all_data.get(release_keys[0])
            if val and isinstance(val, list) and len(val) > 0:
                ok("ReAct Tool 结果正确存入 SharedMemory（备选查找）")
            else:
                fail(f"ReAct Tool 结果未正确存入 SharedMemory: value={val}")
                return False
        else:
            fail("ReAct Tool 结果未存入 SharedMemory")
            return False

    return True


async def test_4_termination() -> bool:
    """测试 4: 终止判断 — LLM 可以主动决定终止分析"""
    print("\n【测试 4】终止判断")

    reset_tracking()

    plan = AnalysisPlan(steps=[
        PlanStep(
            step_id="s1",
            step_type="data",
            needs=["repo_metadata"],
            description="获取仓库信息",
            deps=[],
        ),
        PlanStep(
            step_id="s2",
            step_type="data",
            needs=["contributor_list"],
            description="获取贡献者",
            deps=[],
        ),
    ])

    # LLM 在第一轮后就决定终止（跳过剩余步骤）
    llm = MockReActLLM(decision_sequence=[
        "TERMINATE: 已有足够数据",
    ])

    registry = get_registry()
    execute_engine = ExecuteEngine(
        registry=registry,
        executor=ToolExecutor(registry=registry),
        llm=llm,
        needs_tool_map={
            "repo_metadata": ["mock_get_repo_metadata"],
            "contributor_list": ["mock_list_contributors"],
        },
    )

    context = {"owner": "test", "repo": "demo", "repo_url": "https://github.com/test/demo"}
    await execute_engine.run(plan, context)

    # 验证：终止信息被记录
    termination_info = execute_engine.memory.get("__react_termination__")
    if termination_info and termination_info.get("reasoning"):
        ok(f"LLM 主动终止分析，结论: {termination_info['reasoning'][:50]}...")
    else:
        fail("终止信息未正确记录")
        return False

    # 验证：Plan 中的步骤可能未全部执行（提前终止是预期行为）
    info("提前终止是预期行为，无需执行全部 Plan 步骤")

    return True


async def test_5_failure_isolation_in_react() -> bool:
    """测试 5: 失败隔离 — ReAct 中 Tool 失败不影响循环继续"""
    print("\n【测试 5】失败隔离")

    reset_tracking()

    plan = AnalysisPlan(steps=[
        PlanStep(
            step_id="s1",
            step_type="data",
            needs=["repo_metadata"],
            description="获取仓库信息",
            deps=[],
        ),
    ])

    # LLM 先请求一个会失败的 Tool，然后 terminate
    llm = MockReActLLM(decision_sequence=[
        "CONTINUE",
        [
            {
                "id": "react_fail",
                "name": "mock_react_failing_tool",
                "arguments": {"query": "test"},
            },
        ],
        "TERMINATE: 尽管有失败，但已有足够数据",
    ])

    registry = get_registry()
    execute_engine = ExecuteEngine(
        registry=registry,
        executor=ToolExecutor(registry=registry),
        llm=llm,
        needs_tool_map={
            "repo_metadata": ["mock_get_repo_metadata"],
        },
    )

    context = {"owner": "test", "repo": "demo", "repo_url": "https://github.com/test/demo"}

    try:
        await execute_engine.run(plan, context)
        ok("ReAct Tool 失败后循环继续，未异常中断")
    except Exception as e:
        fail(f"ReAct Tool 失败导致异常中断: {e}")
        return False

    # 验证：失败的 Tool 被调用了
    if tool_call_counts.get("mock_react_failing_tool", 0) >= 1:
        ok("失败的 Tool 被调用且错误被隔离")

    return True


async def test_6_backward_compatible() -> bool:
    """测试 6: 兼容 5.4 — 关闭 react_enabled 时行为与 5.4 完全一致"""
    print("\n【测试 6】兼容 5.4")

    reset_tracking()

    plan = AnalysisPlan(steps=[
        PlanStep(
            step_id="s1",
            step_type="data",
            needs=["repo_metadata"],
            description="获取仓库信息",
            deps=[],
        ),
        PlanStep(
            step_id="s2",
            step_type="data",
            needs=["contributor_list"],
            description="获取贡献者",
            deps=[],
        ),
    ])

    # 不配置 decision_sequence，因为 react_enabled=False 不会调用 LLM 做 ReAct
    llm = MockReActLLM(decision_sequence=[])

    registry = get_registry()
    execute_engine = ExecuteEngine(
        registry=registry,
        executor=ToolExecutor(registry=registry),
        llm=llm,
        needs_tool_map={
            "repo_metadata": ["mock_get_repo_metadata"],
            "contributor_list": ["mock_list_contributors"],
        },
        react_enabled=False,  # 关闭 ReAct
    )

    context = {"owner": "test", "repo": "demo", "repo_url": "https://github.com/test/demo"}
    result = await execute_engine.run(plan, context)

    # 验证：LLM 未被用于 ReAct 决策
    if len(llm.react_chat_calls) == 0:
        ok("react_enabled=False 时未触发 ReAct")
    else:
        fail("react_enabled=False 时仍触发了 ReAct")
        return False

    # 验证：Plan 正常执行完成
    if result and any(k.startswith("tool:mock_get_repo_metadata") for k in result):
        ok("Plan 正常执行，结果正确")
    else:
        fail("Plan 执行结果异常")
        return False

    # 验证：两个步骤的 Tool 都被执行了
    if tool_call_counts.get("mock_get_repo_metadata", 0) == 1:
        ok("s1 的 Tool 正确执行")
    else:
        fail(f"s1 Tool 执行异常: {tool_call_counts.get('mock_get_repo_metadata', 0)} 次")
        return False

    if tool_call_counts.get("mock_list_contributors", 0) == 1:
        ok("s2 的 Tool 正确执行")
    else:
        fail(f"s2 Tool 执行异常: {tool_call_counts.get('mock_list_contributors', 0)} 次")
        return False

    return True


# ---------------------------------------------------------------------------
# 主程序
# ---------------------------------------------------------------------------

async def main() -> None:
    """运行所有测试"""
    print("=" * 60)
    print("Phase 5.5 ReAct Loop — 端到端验证")
    print("=" * 60)

    tests = [
        ("ReAct 触发", test_1_react_triggered),
        ("Tool 补充", test_2_react_tool_calls),
        ("结果共享", test_3_shared_memory_integration),
        ("终止判断", test_4_termination),
        ("失败隔离", test_5_failure_isolation_in_react),
        ("兼容 5.4", test_6_backward_compatible),
    ]

    passed = 0
    failed_tests = []

    for name, test_fn in tests:
        try:
            result = await test_fn()
            if result:
                passed += 1
            else:
                failed_tests.append(name)
        except Exception as e:
            fail(f"测试异常: {e}")
            import traceback
            traceback.print_exc()
            failed_tests.append(name)

    print("\n" + "=" * 60)
    print(f"验证结果: {passed}/{len(tests)} 通过")
    if failed_tests:
        print(f"失败项: {', '.join(failed_tests)}")
    print("=" * 60)

    return len(failed_tests) == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
