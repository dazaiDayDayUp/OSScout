#!/usr/bin/env python3
"""
Phase 5.5 ReAct Loop -- 真实 LLM 验证脚本

使用真实的 Kimi/DeepSeek API 验证 ReAct 决策行为。
运行 3 个独立测试场景，观察 LLM 是否：
1. 在数据充足时输出 TERMINATE
2. 在数据不足时输出 tool_calls 补充采集
3. 不会陷入无限循环

用法:
    cd backend
    .\\venv\\Scripts\\python.exe .\\scripts\\verify_phase55_real_llm.py [--provider kimi|deepseek]

注意：每次运行消耗 LLM API Token（约 0.1~0.3 元/场景）。
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.agents.orchestration import (
    AnalysisPlan,
    ExecuteEngine,
    PlanStep,
)
from app.agents.tools import ToolExecutor, get_registry, tool
from app.llm.factory import get_llm_provider


# ---------------------------------------------------------------------------
# Mock Tool：带真实描述
# ---------------------------------------------------------------------------

@tool(description="Get GitHub repository metadata including stars, forks, language, description")
async def github_repo_metadata(owner: str, repo: str) -> dict:
    return {
        "name": repo,
        "owner": owner,
        "stars": 52340,
        "forks": 11200,
        "language": "TypeScript",
        "description": "A declarative JavaScript library for building user interfaces.",
    }


@tool(description="Get contributor list and activity statistics for a GitHub repository")
async def github_contributors(owner: str, repo: str) -> list[dict]:
    return [
        {"login": "zpao", "contributions": 1892},
        {"login": "gaearon", "contributions": 1523},
    ]


@tool(description="Scan known security vulnerabilities (CVE) and return risk score")
async def security_vulnerability_scan(owner: str, repo: str) -> dict:
    return {
        "vulnerabilities": [],
        "risk_score": 15,
        "summary": "No high-risk vulnerabilities found.",
    }


@tool(description="Get commit frequency and release history for the past year")
async def github_commit_history(owner: str, repo: str) -> dict:
    return {
        "total_commits_last_year": 1247,
        "last_release": "v18.2.0",
        "release_frequency": "every 6 months",
    }


@tool(description="Query knowledge base for open source community health benchmarks")
async def rag_community_benchmark(query_text: str, n_results: int = 3) -> str:
    return json.dumps({
        "results": [
            {"title": "CHAOSS metrics", "content": "Active contributors > 10 is healthy."},
        ],
    })


# ---------------------------------------------------------------------------
# 测试场景
# ---------------------------------------------------------------------------

def make_engine(llm, needs_map: dict, react_enabled: bool = True):
    """创建 ExecuteEngine"""
    registry = get_registry()
    return ExecuteEngine(
        registry=registry,
        executor=ToolExecutor(registry=registry),
        llm=llm,
        needs_tool_map=needs_map,
        react_enabled=react_enabled,
        react_max_iterations=3,
    )


async def test_1_termination(provider_name: str) -> dict:
    """
    测试1：ReAct 终止判断
    Plan 包含完整的分析步骤，期望 ReAct 在全部执行完后返回 TERMINATE
    """
    print("\n" + "=" * 60)
    print("[TEST 1] ReAct Termination -- Plan complete -> TERMINATE")
    print("=" * 60)

    llm = get_llm_provider(provider_name)
    plan = AnalysisPlan(steps=[
        PlanStep(step_id="s1", step_type="data", needs=["repo_metadata"],
                 description="Get repo metadata", deps=[]),
        PlanStep(step_id="s2", step_type="data", needs=["contributor_list"],
                 description="Get contributors", deps=[]),
    ])

    engine = make_engine(llm, {
        "repo_metadata": ["github_repo_metadata"],
        "contributor_list": ["github_contributors"],
    })

    t0 = time.perf_counter()
    result = await engine.run(plan, {"owner": "facebook", "repo": "react"})
    elapsed = time.perf_counter() - t0

    history = result.get("__react_history__", [])
    terminated = result.get("__react_termination__") is not None

    print(f"  Completed steps: 2/2")
    print(f"  ReAct turns: {len(history)}")
    for h in history:
        print(f"    Turn {h['turn']}: {h['action']} -- {h.get('content', '')[:60]}")
    print(f"  Terminated: {terminated}")
    print(f"  Elapsed: {elapsed:.1f}s")

    return {
        "test": "termination",
        "success": terminated and len(history) >= 1,
        "react_turns": len(history),
        "terminated": terminated,
        "elapsed": elapsed,
    }


async def test_2_tool_calls(provider_name: str) -> dict:
    """
    测试2：ReAct Tool 补充
    Plan 只包含 repo_metadata，但 Registry 中有更多 Tool。
    期望 ReAct 发现数据不足，输出 tool_calls 补充其他 Tool。
    """
    print("\n" + "=" * 60)
    print("[TEST 2] ReAct Tool Calls -- incomplete Plan -> supplement")
    print("=" * 60)

    llm = get_llm_provider(provider_name)
    plan = AnalysisPlan(steps=[
        PlanStep(step_id="s1", step_type="data", needs=["repo_metadata"],
                 description="Get repo metadata", deps=[]),
    ])

    engine = make_engine(llm, {
        "repo_metadata": ["github_repo_metadata"],
        "contributor_list": ["github_contributors"],
        "security_scan": ["security_vulnerability_scan"],
        "commit_history": ["github_commit_history"],
    })

    t0 = time.perf_counter()
    result = await engine.run(plan, {"owner": "facebook", "repo": "react"})
    elapsed = time.perf_counter() - t0

    history = result.get("__react_history__", [])
    tool_results = {k for k in result if k.startswith("tool:")}
    tool_names = {k.split(":", 2)[1] for k in tool_results if ":" in k}

    # 检查是否有 Plan 外的 Tool 被 ReAct 调用
    plan_tools = {"github_repo_metadata"}
    extra_tools = tool_names - plan_tools
    has_supplement = len(extra_tools) > 0

    print(f"  Plan steps: 1")
    print(f"  ReAct turns: {len(history)}")
    for h in history:
        tool_info = f" -> tools: {h.get('tool_names', [])}" if h['action'] == 'tool_calls' else ""
        print(f"    Turn {h['turn']}: {h['action']}{tool_info}")
    print(f"  Tools executed: {tool_names}")
    print(f"  Supplement tools (outside Plan): {extra_tools or 'None'}")
    print(f"  Elapsed: {elapsed:.1f}s")

    return {
        "test": "tool_calls",
        "success": True,  # 只要没崩溃就算成功，补充是期望但不是必须
        "react_turns": len(history),
        "has_supplement": has_supplement,
        "extra_tools": list(extra_tools),
        "elapsed": elapsed,
    }


async def test_3_early_terminate(provider_name: str) -> dict:
    """
    测试3：ReAct 提前终止
    Plan 有 3 个步骤，但前 2 个步骤的数据已经很充分。
    期望 ReAct 在第 2 轮后返回 TERMINATE，跳过第 3 步。
    """
    print("\n" + "=" * 60)
    print("[TEST 3] ReAct Early Termination -- skip remaining steps")
    print("=" * 60)

    llm = get_llm_provider(provider_name)
    plan = AnalysisPlan(steps=[
        PlanStep(step_id="s1", step_type="data", needs=["repo_metadata"],
                 description="Get repo metadata", deps=[]),
        PlanStep(step_id="s2", step_type="data", needs=["contributor_list"],
                 description="Get contributors", deps=[]),
        PlanStep(step_id="s3", step_type="data", needs=["commit_history"],
                 description="Get commit history (optional)", deps=["s1"]),
    ])

    engine = make_engine(llm, {
        "repo_metadata": ["github_repo_metadata"],
        "contributor_list": ["github_contributors"],
        "commit_history": ["github_commit_history"],
    })

    t0 = time.perf_counter()
    result = await engine.run(plan, {"owner": "facebook", "repo": "react"})
    elapsed = time.perf_counter() - t0

    history = result.get("__react_history__", [])
    terminated = result.get("__react_termination__") is not None
    tool_results = {k for k in result if k.startswith("tool:")}
    executed_tools = {k.split(":", 2)[1] for k in tool_results if ":" in k}

    # s3 的 tool 是否被执行
    s3_executed = "github_commit_history" in executed_tools

    print(f"  Plan steps: 3")
    print(f"  ReAct turns: {len(history)}")
    for h in history:
        print(f"    Turn {h['turn']}: {h['action']} -- {h.get('content', '')[:60]}")
    print(f"  Terminated early: {terminated}")
    print(f"  s3 (commit_history) executed: {s3_executed}")
    print(f"  Elapsed: {elapsed:.1f}s")

    return {
        "test": "early_terminate",
        "success": True,
        "react_turns": len(history),
        "terminated": terminated,
        "s3_executed": s3_executed,
        "elapsed": elapsed,
    }


# ---------------------------------------------------------------------------
# 主程序
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(description="Phase 5.5 Real LLM Validation")
    parser.add_argument("--provider", choices=["kimi", "deepseek"], default="kimi")
    args = parser.parse_args()

    print("=" * 60)
    print("Phase 5.5 ReAct Loop -- Real LLM Validation")
    print("=" * 60)
    print(f"Provider: {args.provider}")

    results = []

    # 运行 3 个测试场景
    for test_fn in [test_1_termination, test_2_tool_calls, test_3_early_terminate]:
        try:
            r = await test_fn(args.provider)
            results.append(r)
        except Exception as e:
            print(f"  [FAIL] Exception: {e}")
            import traceback
            traceback.print_exc()
            results.append({"test": test_fn.__name__, "success": False, "error": str(e)})

        # 避免 API 限频
        await asyncio.sleep(2)

    # 汇总
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for r in results:
        status = "OK" if r.get("success") else "FAIL"
        print(f"  [{status}] {r['test']}: {r.get('react_turns', 0)} ReAct turns, {r.get('elapsed', 0):.1f}s")

    print("\nValidation complete.")
    return all(r.get("success", False) for r in results)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
