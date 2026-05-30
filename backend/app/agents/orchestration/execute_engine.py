"""
Execute Engine — 计划执行引擎

Phase 5.4 核心组件之一。

职责：解析 Plan → 提取当前可执行步骤 → 映射到 Tool → 查缓存 → 执行 → 存结果。

设计要点：
- 依赖感知并行：无依赖的步骤自动并行（asyncio.gather）
- 数据只采一次：SharedMemory 缓存，同一 Tool + 参数永远只执行一次
- 声明式数据需求：Plan 中的 needs 是抽象数据需求，Execute Engine 负责映射到 Tool
- 失败隔离：单个 Tool 失败只影响当前步骤，不阻断整体流程
- Specialist 预留：识别 step_type="specialist" 但不执行（Phase 5.6 实现）

使用方式：
    from app.agents.orchestration import ExecuteEngine, PlanEngine, SharedMemory
    from app.agents.tools import ToolExecutor, get_registry
    from app.llm.factory import get_default_llm

    # 制定计划
    plan_engine = PlanEngine()
    plan = await plan_engine.create_plan(repo_url, llm)

    # 执行计划
    execute_engine = ExecuteEngine(
        registry=get_registry(),
        executor=ToolExecutor(),
        llm=llm,
    )
    result = await execute_engine.run(
        plan=plan,
        context={"owner": "facebook", "repo": "react", "repo_url": repo_url}
    )
"""

import asyncio
import json
from typing import Any

from app.agents.tools.executor import ToolExecutor
from app.agents.tools.registry import ToolRegistry, get_registry
from app.agents.tools.tool import Tool, ToolSource
from app.core.logger import get_logger
from app.llm.base import LLMProvider
from app.llm.schemas import LLMMessage

from .plan_engine import AnalysisPlan, PlanStep
from .shared_memory import SharedMemory

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# 默认 needs → Tool 名称映射
# ---------------------------------------------------------------------------
# 覆盖核心 RAG Tool（名称确定）。MCP Tool 通过 Registry 自动发现补充。

_DEFAULT_NEEDS_TOOL_MAP: dict[str, list[str]] = {
    # RAG Tool（名称确定）
    "knowledge_query": ["rag_query_knowledge"],
    "community_benchmark": ["rag_get_benchmark"],
    "quality_benchmark": ["rag_get_benchmark"],
    "security_benchmark": ["rag_get_benchmark"],
    "evolution_benchmark": ["rag_get_benchmark"],
    "competitor_info": ["rag_get_competitors"],
}

# ---------------------------------------------------------------------------
# 模糊匹配规则：Tool name 关键词 → need
# ---------------------------------------------------------------------------
# 用于 Registry 自动发现时，为没有声明 provides 的 Tool 推断映射关系。

_FUZZY_MATCH_RULES: list[tuple[list[str], str]] = [
    # (关键词列表, 对应的 need)
    (["repo", "metadata"], "repo_metadata"),
    (["repo", "info"], "repo_metadata"),
    (["repo", "detail"], "repo_metadata"),
    (["contributor"], "contributor_list"),
    (["issue"], "issue_list"),
    (["pull", "request"], "pull_requests"),
    (["commit"], "commit_history"),
    (["release"], "release_list"),
    (["file", "tree"], "file_tree"),
    (["readme"], "readme_content"),
    (["license"], "license_info"),
    (["dependency"], "dependency_info"),
    (["vulnerability"], "vulnerability_scan"),
    (["cve"], "vulnerability_scan"),
    (["osv"], "vulnerability_scan"),
    (["security", "advisory"], "security_advisories"),
    (["search", "web"], "web_search"),
]

# 编程语言 → 项目类型/技术领域 映射常量
_LANGUAGE_TO_PROJECT_TYPE: dict[str, str] = {
    "javascript": "frontend-framework",
    "typescript": "frontend-framework",
    "python": "backend-framework",
    "go": "backend-framework",
    "rust": "backend-framework",
    "java": "backend-framework",
    "ruby": "backend-framework",
    "php": "backend-framework",
    "c": "database-driver",
    "c++": "database-driver",
    "shell": "cli-tool",
}

_LANGUAGE_TO_TECH_DOMAIN: dict[str, str] = {
    "javascript": "frontend framework",
    "typescript": "frontend framework",
    "python": "backend framework",
    "go": "backend framework",
    "rust": "systems programming",
    "java": "enterprise framework",
    "ruby": "web framework",
    "php": "web framework",
}


class ExecuteEngine:
    """计划执行引擎

    解析 AnalysisPlan，按 DAG 依赖顺序执行，支持并行和缓存。

    属性:
        registry: ToolRegistry 实例
        executor: ToolExecutor 实例
        llm: LLMProvider 实例（用于 reasoning 步骤）
        memory: SharedMemory 实例
        needs_map: needs → Tool 名称列表的映射
    """

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        executor: ToolExecutor | None = None,
        llm: LLMProvider | None = None,
        shared_memory: SharedMemory | None = None,
        needs_tool_map: dict[str, list[str]] | None = None,
    ) -> None:
        """
        Args:
            registry: ToolRegistry，默认全局单例
            executor: ToolExecutor，默认新建
            llm: LLMProvider，用于 reasoning 步骤
            shared_memory: SharedMemory，默认新建
            needs_tool_map: 自定义 needs → Tool 映射，覆盖默认映射
        """
        self.registry = registry or get_registry()
        self.executor = executor or ToolExecutor(registry=self.registry)
        self.llm = llm
        self.memory = shared_memory or SharedMemory()

        # 构建 needs → Tool 映射（默认 + Registry 自动发现 + 自定义）
        self.needs_map = self._build_needs_map(needs_tool_map)

        # 执行期间的临时状态：tool_call_id → {tool_name, args} 映射
        self._pending_calls: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    async def run(self, plan: AnalysisPlan, context: dict) -> dict:
        """执行分析计划

        按 DAG 依赖顺序执行所有步骤，无依赖步骤自动并行。
        所有 Tool 执行结果和 Reasoning 结果存入 SharedMemory。

        Args:
            plan: 分析计划（由 PlanEngine 生成）
            context: 分析上下文，至少包含 owner、repo、repo_url

        Returns:
            SharedMemory 中所有数据的快照
        """
        self.memory.set_context(context)

        completed: set[str] = set()
        failed: set[str] = set()
        iteration = 0
        max_iterations = len(plan.steps) * 2  # 安全上限，防止死循环

        logger.info(
            "ExecuteEngine: 开始执行计划",
            total_steps=len(plan.steps),
            context_keys=list(context.keys()),
        )

        while iteration < max_iterations:
            iteration += 1

            # 找出所有依赖已满足的步骤
            ready_steps = self._get_ready_steps(plan, completed, failed)

            if not ready_steps:
                total_done = len(completed) + len(failed)
                if total_done >= len(plan.steps):
                    # 全部完成或失败
                    break
                # 有步骤永远不满足（死锁）
                remaining = [
                    s.step_id
                    for s in plan.steps
                    if s.step_id not in completed and s.step_id not in failed
                ]
                raise ValueError(
                    f"ExecuteEngine 死锁：以下步骤的依赖永远无法满足: {remaining}"
                )

            logger.info(
                "ExecuteEngine execution round",
                iteration=iteration,
                ready_steps=len(ready_steps),
                step_ids=[s.step_id for s in ready_steps],
            )

            # 并行执行所有就绪步骤
            # return_exceptions=True 实现失败隔离：单个步骤失败不取消其他步骤
            results = await asyncio.gather(
                *[self._execute_step(step) for step in ready_steps],
                return_exceptions=True,
            )

            # 处理执行结果
            for step, result in zip(ready_steps, results):
                if isinstance(result, Exception):
                    logger.error(
                        "步骤执行失败",
                        step_id=step.step_id,
                        step_type=step.step_type,
                        error=str(result),
                        error_type=type(result).__name__,
                    )
                    failed.add(step.step_id)
                else:
                    completed.add(step.step_id)

        # 执行完成，输出摘要
        summary = {
            "completed": len(completed),
            "failed": len(failed),
            "total": len(plan.steps),
            "completed_ids": sorted(completed),
            "failed_ids": sorted(failed),
            "iterations": iteration,
            "memory_summary": self.memory.summary(),
        }
        logger.info(
            "ExecuteEngine plan execution completed",
            completed=len(completed),
            failed=len(failed),
            total=len(plan.steps),
            completed_ids=sorted(completed),
            failed_ids=sorted(failed),
            iterations=iteration,
            memory_summary=self.memory.summary(),
        )

        return self.memory.get_all()

    # ------------------------------------------------------------------
    # 步骤执行
    # ------------------------------------------------------------------

    async def _execute_step(self, step: PlanStep) -> None:
        """执行单个步骤

        根据 step_type 路由到对应的处理逻辑。

        Args:
            step: 分析步骤
        """
        logger.debug(
            "执行步骤",
            step_id=step.step_id,
            step_type=step.step_type,
            needs=step.needs,
            deps=step.deps,
        )

        if step.step_type == "data":
            await self._execute_data_step(step)
        elif step.step_type == "reasoning":
            await self._execute_reasoning_step(step)
        elif step.step_type == "specialist":
            # Phase 5.6 实现，5.4 预留
            logger.info(
                "Specialist 步骤暂不支持，已跳过",
                step_id=step.step_id,
                description=step.description,
            )
        else:
            logger.warning(
                "未知的 step_type，已跳过",
                step_id=step.step_id,
                step_type=step.step_type,
            )

    async def _execute_data_step(self, step: PlanStep) -> None:
        """执行 data 类型步骤：将 needs 映射到 Tool → 查缓存 → 执行 → 存结果

        Args:
            step: data 类型步骤
        """
        # 1. 将 needs 映射到 Tool 名称列表
        tool_names = self._resolve_needs_to_tools(step.needs)

        if not tool_names:
            logger.warning(
                "无法将 needs 映射到任何 Tool",
                step_id=step.step_id,
                needs=step.needs,
            )
            return

        # 2. 对每个 Tool：查缓存 → 命中则跳过，未命中则构建 tool_call
        tool_calls: list[dict] = []
        skipped_tools: list[str] = []

        for tool_name in tool_names:
            tool = self.registry.get(tool_name)
            if tool is None:
                logger.warning(
                    "Tool 未在 Registry 中找到",
                    step_id=step.step_id,
                    tool_name=tool_name,
                )
                continue

            # 推导 Tool 调用参数
            args = self._derive_tool_args(tool, step)
            if args is None:
                logger.warning(
                    "无法推导 Tool 参数，跳过",
                    step_id=step.step_id,
                    tool_name=tool_name,
                )
                continue

            # 查缓存
            if self.memory.has_tool_result(tool_name, args):
                skipped_tools.append(tool_name)
                logger.debug(
                    "缓存命中，跳过执行",
                    step_id=step.step_id,
                    tool_name=tool_name,
                )
                continue

            # 构建 tool_call
            tc_id = f"call_{step.step_id}_{tool_name}"
            self._pending_calls[tc_id] = {
                "tool_name": tool_name,
                "args": args,
                "step_id": step.step_id,
            }
            tool_calls.append({
                "id": tc_id,
                "name": tool_name,
                "arguments": json.dumps(args, ensure_ascii=False),
            })

        if skipped_tools:
            logger.debug(
                "缓存命中跳过",
                step_id=step.step_id,
                skipped=skipped_tools,
            )

        # 3. 并行执行所有未缓存的 Tool
        if tool_calls:
            logger.info(
                "并行执行 Tool",
                step_id=step.step_id,
                tool_count=len(tool_calls),
                tool_names=[tc["name"] for tc in tool_calls],
            )

            results = await self.executor.execute_all(tool_calls)

            # 4. 处理执行结果：成功存入缓存，失败记录日志
            for result in results:
                pending = self._pending_calls.pop(result.tool_call_id, None)
                if pending is None:
                    logger.warning(
                        "未知的 tool_call_id",
                        tool_call_id=result.tool_call_id,
                    )
                    continue

                if result.is_error:
                    logger.error(
                        "Tool 执行失败",
                        step_id=step.step_id,
                        tool_name=result.tool_name,
                        error=result.error_message,
                    )
                else:
                    # 成功：存入 SharedMemory
                    self.memory.set_tool_result(
                        tool_name=pending["tool_name"],
                        args=pending["args"],
                        result=result.output,
                        needs=step.needs,
                    )
                    logger.debug(
                        "Tool 执行成功，已缓存",
                        step_id=step.step_id,
                        tool_name=result.tool_name,
                    )

    async def _execute_reasoning_step(self, step: PlanStep) -> None:
        """执行 reasoning 类型步骤：收集数据 → 调用 LLM → 存结果

        Args:
            step: reasoning 类型步骤
        """
        if self.llm is None:
            logger.warning(
                "未配置 LLM，无法执行 reasoning 步骤",
                step_id=step.step_id,
            )
            return

        # 1. 收集该步骤需要的所有数据
        needs_to_query = step.needs if step.needs else []
        # 如果 needs 为空，从 SharedMemory 中获取所有已缓存的数据作为补充
        data_by_need = self.memory.get_all_by_needs(needs_to_query) if needs_to_query else {}

        # 过滤空值，构建输入数据
        input_data: dict[str, Any] = {}
        for need, values in data_by_need.items():
            if values:
                input_data[need] = values

        # needs 为空时，尝试收集所有已缓存的 Tool 结果
        if not input_data:
            all_data = self.memory.get_all()
            for key, value in all_data.items():
                if key.startswith("tool:") and value is not None:
                    # 从 key 中提取 need（如果有反向索引）
                    input_data[key] = value
            if input_data:
                logger.info(
                    "Reasoning 步骤 needs 为空，自动收集所有 Tool 结果作为输入",
                    step_id=step.step_id,
                    collected=len(input_data),
                )

        if not input_data:
            logger.warning(
                "Reasoning 步骤缺少输入数据",
                step_id=step.step_id,
                needs=step.needs,
            )

        # 2. 构造 Prompt
        prompt = self._build_reasoning_prompt(step, input_data)

        # 3. 调用 LLM
        messages = [LLMMessage(role="user", content=prompt)]
        response = await self.llm.chat(
            messages=messages,
            temperature=0.7,
        )

        # 4. 存储结果
        result = {
            "description": step.description,
            "result": response.content,
            "model": response.model,
            "provider": response.provider,
            "input_needs": step.needs,
            "input_data_summary": {
                need: f"{len(vals)} 条数据"
                for need, vals in input_data.items()
            },
        }
        self.memory.set_reasoning_result(
            step_id=step.step_id,
            result=result,
            needs=step.needs,
        )

        logger.info(
            "Reasoning 步骤完成",
            step_id=step.step_id,
            model=response.model,
            content_length=len(response.content),
        )

    # ------------------------------------------------------------------
    # needs → Tool 映射
    # ------------------------------------------------------------------

    def _build_needs_map(
        self, custom_map: dict[str, list[str]] | None
    ) -> dict[str, list[str]]:
        """构建完整的 needs → Tool 映射

        合并三层来源（优先级从高到低）：
        1. 自定义映射（传入参数）
        2. Registry 自动发现（Tool.metadata["provides"]）
        3. 默认映射表
        4. 模糊匹配（无 provides 的 Tool）

        Returns:
            needs → Tool 名称列表的映射字典
        """
        merged: dict[str, list[str]] = {}

        # Layer 3: 默认映射
        for need, tools in _DEFAULT_NEEDS_TOOL_MAP.items():
            merged[need] = list(tools)

        # Layer 2: Registry 自动发现
        for tool in self.registry.list_tools():
            provides = tool.metadata.get("provides", [])
            if provides:
                for need in provides:
                    merged.setdefault(need, [])
                    if tool.name not in merged[need]:
                        merged[need].append(tool.name)

        # Layer 4: 模糊匹配（补充无 provides 的 Tool）
        for tool in self.registry.list_tools():
            if tool.metadata.get("provides"):
                continue  # 已有 provides，跳过模糊匹配

            tool_name_lower = tool.name.lower()
            for keywords, need in _FUZZY_MATCH_RULES:
                if all(kw in tool_name_lower for kw in keywords):
                    merged.setdefault(need, [])
                    if tool.name not in merged[need]:
                        merged[need].append(tool.name)
                    break  # 一个 Tool 只匹配第一个规则

        # Layer 1: 自定义映射（最高优先级，覆盖前面的）
        if custom_map:
            for need, tools in custom_map.items():
                merged[need] = list(tools)

        logger.debug(
            "needs → Tool 映射构建完成",
            needs_count=len(merged),
            needs=list(merged.keys()),
        )
        return merged

    def _resolve_needs_to_tools(self, needs: list[str]) -> list[str]:
        """将数据需求列表解析为 Tool 名称列表

        去重后返回所有需要调用的 Tool。

        Args:
            needs: 数据需求名称列表

        Returns:
            Tool 名称列表（去重）
        """
        tool_names: list[str] = []
        seen = set()

        for need in needs:
            mapped = self.needs_map.get(need, [])
            if not mapped:
                logger.warning(
                    "未找到 need 对应的 Tool",
                    need=need,
                )
                continue

            for tool_name in mapped:
                if tool_name not in seen:
                    seen.add(tool_name)
                    tool_names.append(tool_name)

        return tool_names

    # ------------------------------------------------------------------
    # 参数推导
    # ------------------------------------------------------------------

    def _derive_tool_args(
        self, tool: Tool, step: PlanStep
    ) -> dict | None:
        """推导 Tool 调用参数

        根据 Tool 的 JSON Schema 参数定义，从以下来源填充参数：
        1. 分析上下文（owner, repo, repo_url）
        2. Step 描述（RAG / Search Tool 的 query）
        3. SharedMemory 中已缓存的数据

        如果必填参数无法推导，返回 None（跳过该 Tool）。

        Args:
            tool: Tool 对象
            step: 当前步骤

        Returns:
            参数字典，或 None（必填参数缺失）
        """
        args: dict[str, Any] = {}
        context = self.memory.get_context()
        properties = tool.parameters.get("properties", {})
        required = tool.parameters.get("required", [])

        for param_name in properties:
            # 1. 从上下文获取（owner, repo, repo_url）
            if param_name in context:
                args[param_name] = context[param_name]
                continue

            # 2. 别名处理：repository → repo
            if param_name == "repository" and "repo" in context:
                args[param_name] = context["repo"]
                continue

            # 3. 特殊参数处理
            derived = self._derive_special_param(param_name, tool, step, context)
            if derived is not None:
                args[param_name] = derived
                continue

            # 4. 尝试从 SharedMemory 查找
            val = self.memory.get(param_name)
            if val is not None:
                args[param_name] = val
                continue

        # 5. 为缺失的参数设置 JSON Schema 中定义的默认值
        for param_name, prop_schema in properties.items():
            if param_name not in args and "default" in prop_schema:
                args[param_name] = prop_schema["default"]

        # 检查必填参数
        missing = [p for p in required if p not in args]
        if missing:
            logger.warning(
                "Tool 调用缺少必填参数",
                tool_name=tool.name,
                missing=missing,
            )
            return None

        return args

    def _derive_special_param(
        self,
        param_name: str,
        tool: Tool,
        step: PlanStep,
        context: dict,
    ) -> Any:
        """推导特殊参数（RAG query、project_type 等）

        Args:
            param_name: 参数名
            tool: Tool 对象
            step: 当前步骤
            context: 分析上下文

        Returns:
            推导出的参数值，或 None（无法推导）
        """
        # RAG / Search Tool 的 query 参数
        if param_name in ("query_text", "query"):
            return step.description

        # Benchmark Tool 的 project_type
        if param_name == "project_type" and tool.source == ToolSource.RAG:
            # 从上下文的 language 推导项目类型
            language = context.get("language", "")
            return self._language_to_project_type(language)

        # Competitor Tool 的 tech_domain
        if param_name == "tech_domain" and tool.source == ToolSource.RAG:
            # 从上下文的 language 推导技术领域
            language = context.get("language", "")
            return self._language_to_tech_domain(language)

        # 搜索结果数量限制（RAG Tool）
        if param_name == "n_results" and tool.source == ToolSource.RAG:
            return 5  # 默认值

        # Benchmark Tool 的 metric_name（可选）
        if param_name == "metric_name" and tool.source == ToolSource.RAG:
            return ""  # 空字符串表示返回所有指标

        return None

    @staticmethod
    def _language_to_project_type(language: str) -> str:
        """将编程语言映射到项目类型标签

        用于 rag_get_benchmark 的 project_type 参数。
        """
        return _LANGUAGE_TO_PROJECT_TYPE.get(language.lower(), "utility-library")

    @staticmethod
    def _language_to_tech_domain(language: str) -> str:
        """将编程语言映射到技术领域

        用于 rag_get_competitors 的 tech_domain 参数。
        """
        return _LANGUAGE_TO_TECH_DOMAIN.get(language.lower(), "software library")

    # ------------------------------------------------------------------
    # Reasoning Prompt
    # ------------------------------------------------------------------

    def _build_reasoning_prompt(
        self, step: PlanStep, input_data: dict[str, Any]
    ) -> str:
        """构造 reasoning 步骤的 Prompt

        Args:
            step: reasoning 步骤
            input_data: 输入数据（need → 数据列表）

        Returns:
            Prompt 字符串
        """
        # 将数据序列化为可读的字符串
        data_sections = []
        for need, values in input_data.items():
            data_sections.append(f"\n=== {need} ===")
            for i, val in enumerate(values, 1):
                if isinstance(val, dict):
                    content = json.dumps(val, ensure_ascii=False, indent=2)[:800]
                elif isinstance(val, str):
                    content = val[:800]
                else:
                    content = str(val)[:800]
                data_sections.append(f"[{i}] {content}")

        data_text = "\n".join(data_sections) if data_sections else "（暂无可用数据）"

        return f"""你正在进行开源项目尽调分析。请基于以下数据完成分析任务。

【任务】{step.description}

【输入数据】{data_text}

【要求】
1. 基于提供的数据进行客观分析
2. 如果数据不足，明确指出缺少哪些信息
3. 给出具体的评分建议（0-100 分）和理由
4. 列出关键发现和风险点

请直接输出分析结论。"""

    # ------------------------------------------------------------------
    # DAG 依赖解析
    # ------------------------------------------------------------------

    @staticmethod
    def _get_ready_steps(
        plan: AnalysisPlan,
        completed: set[str],
        failed: set[str],
    ) -> list[PlanStep]:
        """找出所有依赖已满足的步骤

        一个步骤"就绪"的条件：
        1. 尚未执行（不在 completed 或 failed 中）
        2. 所有依赖步骤都已完成（在 completed 中）

        注意：依赖失败的步骤不会被标记为就绪（保守策略）。
        Phase 5.5 的 ReAct 可以放宽此限制。

        Args:
            plan: 分析计划
            completed: 已完成的步骤 ID 集合
            failed: 失败的步骤 ID 集合

        Returns:
            就绪的步骤列表
        """
        ready: list[PlanStep] = []
        done = completed | failed

        for step in plan.steps:
            if step.step_id in done:
                continue

            # 检查所有依赖是否已完成
            if all(dep in completed for dep in step.deps):
                ready.append(step)

        return ready

    # ------------------------------------------------------------------
    # 统计与调试
    # ------------------------------------------------------------------

    def get_needs_map_summary(self) -> dict:
        """获取 needs → Tool 映射的摘要（用于调试）"""
        return {
            "total_needs": len(self.needs_map),
            "needs": {
                need: tools for need, tools in self.needs_map.items()
            },
        }
