"""
Plan Engine — 分析计划制定引擎

Phase 5.4 核心组件之一。

职责：LLM 根据仓库地址制定全局分析计划，输出带依赖关系的 Step 列表。

设计要点：
- 声明式数据需求：Plan 中不写"调用什么 Tool"，而是写"需要什么数据"
- needs 是抽象数据需求（如 "repo_metadata"），不是 Tool 名
- deps 定义步骤间的依赖关系，Execute Engine 据此做并行调度
- 使用 chat_structured() 让 LLM 输出结构化 Plan

使用方式：
    from app.llm.factory import get_llm_provider
    from app.agents.orchestration.plan_engine import PlanEngine

    llm = get_llm_provider()
    engine = PlanEngine()
    plan = await engine.create_plan("https://github.com/facebook/react", llm)
    for step in plan.steps:
        print(f"{step.step_id}: {step.description}")
"""

from pydantic import BaseModel, Field

from app.core.logger import get_logger
from app.core.utils import parse_repo_url
from app.llm.base import LLMProvider
from app.llm.schemas import LLMMessage

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# 默认可用的数据需求目录
# ---------------------------------------------------------------------------
# PlanEngine 内置核心数据需求列表。
# 调用方可通过 available_needs 参数扩展。
# Execute Engine 负责将这些抽象 needs 映射到具体 Tool。

_DEFAULT_AVAILABLE_NEEDS = [
    # 基础仓库信息
    "repo_metadata",        # 仓库 stars/forks/language/description 等元数据
    "contributor_list",     # 贡献者列表及活跃度
    "issue_list",           # Issue 状态分布
    "pull_requests",        # PR 合并率及状态
    "commit_history",       # 提交频率及最近提交时间
    "release_list",         # Release 列表及发布频率
    "file_tree",            # 文件结构
    "readme_content",       # README 内容
    "license_info",         # 许可证信息
    # 安全
    "vulnerability_scan",   # 已知漏洞扫描结果
    "security_advisories",  # 安全公告
    # 知识库基准
    "community_benchmark",  # 社区健康度行业基准（CHAOSS 指标等）
    "quality_benchmark",    # 代码质量行业基准
    "security_benchmark",   # 安全评估行业基准
    "evolution_benchmark",  # 技术演进行业基准
    "knowledge_query",      # 通用知识检索
    "competitor_info",      # 竞品对比信息
    # 外部补充
    "web_search",           # 网络搜索补充信息
]


# ---------------------------------------------------------------------------
# 结构化输出模型
# ---------------------------------------------------------------------------

class PlanStep(BaseModel):
    """单个分析步骤"""

    step_id: str = Field(
        ...,
        description="唯一标识符，如 s1、s2。格式：字母+数字，如 s1、s2_community",
    )
    step_type: str = Field(
        ...,
        description="步骤类型：data（采集数据）、reasoning（推理分析）、specialist（委派专家，预留）",
    )
    needs: list[str] = Field(
        default_factory=list,
        description="该步骤需要的数据类型列表，从可用数据需求目录中选择",
    )
    description: str = Field(
        ...,
        description="人类可读的步骤描述，说明该步骤要做什么",
    )
    deps: list[str] = Field(
        default_factory=list,
        description="依赖的 step_id 列表，这些步骤完成后才能执行本步骤",
    )


class AnalysisPlan(BaseModel):
    """LLM 输出的分析计划"""

    steps: list[PlanStep] = Field(
        ...,
        description="分析步骤列表，按依赖关系组织",
    )


# ---------------------------------------------------------------------------
# Plan Engine
# ---------------------------------------------------------------------------

class PlanEngine:
    """分析计划制定引擎

    使用 LLM 根据仓库信息制定结构化分析计划。

    属性:
        available_needs: 可用的数据需求列表，Plan 中的 needs 必须来自此列表
    """

    def __init__(self, available_needs: list[str] | None = None) -> None:
        """
        Args:
            available_needs: 可用的数据需求列表，None 时使用默认列表
        """
        self.available_needs = available_needs or _DEFAULT_AVAILABLE_NEEDS

    async def create_plan(self, repo_url: str, llm: LLMProvider) -> AnalysisPlan:
        """为指定仓库制定分析计划

        Args:
            repo_url: GitHub 仓库地址
            llm: LLM Provider 实例

        Returns:
            AnalysisPlan: 结构化分析计划

        Raises:
            ValueError: 仓库地址解析失败或 Plan 校验失败
        """
        owner, repo = parse_repo_url(repo_url)

        # 构造 Prompt
        needs_text = "\n".join(f"- {need}" for need in self.available_needs)

        prompt = self._build_prompt(owner, repo, needs_text)

        messages = [
            LLMMessage(
                role="system",
                content=(
                    "你是一名资深开源项目尽调分析师。"
                    "你的任务是将尽调分析拆解为结构化的执行步骤。"
                ),
            ),
            LLMMessage(role="user", content=prompt),
        ]

        logger.info(
            "PlanEngine: 开始制定分析计划",
            owner=owner,
            repo=repo,
            available_needs=len(self.available_needs),
        )

        # 使用结构化输出让 LLM 生成 Plan
        plan = await llm.chat_structured(
            messages=messages,
            output_schema=AnalysisPlan,
            temperature=0.3,  # 计划制定需要较高的确定性
        )

        # 校验 Plan 的合理性
        self._validate_plan(plan)

        logger.info(
            "PlanEngine: 分析计划制定完成",
            owner=owner,
            repo=repo,
            total_steps=len(plan.steps),
            data_steps=sum(1 for s in plan.steps if s.step_type == "data"),
            reasoning_steps=sum(1 for s in plan.steps if s.step_type == "reasoning"),
        )

        return plan

    def _build_prompt(
        self, owner: str, repo: str, needs_text: str
    ) -> str:
        """构造给 LLM 的 Prompt

        包含仓库信息、分析目标、可用数据需求和输出规则。
        """
        return f"""请为 GitHub 仓库 {owner}/{repo} 制定一个结构化的尽调分析计划。

分析目标：从社区健康、代码质量、安全风险、技术演进四个维度综合评估该开源项目。

可用数据需求（每个步骤的 needs 必须从以下列表中选择）：
{needs_text}

步骤类型说明：
- data: 采集某种数据（工具自动获取）
- reasoning: 基于已采集的数据进行推理分析
- specialist: 需要启动专家 Agent（预留，暂不使用）

规则：
1. 先执行 data 步骤采集数据，后执行 reasoning 步骤做分析推理
2. 无依赖的 data 步骤可以并行（deps 为空）
3. 每个 reasoning 步骤应覆盖一个分析维度（社区健康/代码质量/安全/技术演进）
4. 最后加一个综合 reasoning 步骤，汇总四个维度的结论
5. step_id 使用简短标识符，如 s1、s2_community、s3_final
6. 依赖声明要准确：不要声明不存在的 step_id，不要产生循环依赖

请输出严格符合 JSON Schema 的结果。"""

    def _validate_plan(self, plan: AnalysisPlan) -> None:
        """校验 Plan 的合理性

        检查项：
        1. step_id 唯一性
        2. deps 引用的 step_id 是否存在
        3. 是否有循环依赖
        4. step_type 合法性
        5. needs 中的数据需求是否在可用列表中（放宽为警告，不报错）

        Args:
            plan: LLM 生成的分析计划

        Raises:
            ValueError: 校验失败
        """
        step_ids = {step.step_id for step in plan.steps}
        valid_types = {"data", "reasoning", "specialist"}

        # 1. 检查 step_id 唯一性
        seen_ids = set()
        for step in plan.steps:
            if step.step_id in seen_ids:
                raise ValueError(f"Plan 校验失败：step_id '{step.step_id}' 重复")
            seen_ids.add(step.step_id)

        # 2. 检查 deps 引用的 step_id 是否存在
        for step in plan.steps:
            for dep in step.deps:
                if dep not in step_ids:
                    raise ValueError(
                        f"Plan 校验失败：步骤 '{step.step_id}' 依赖的步骤 '{dep}' 不存在"
                    )

        # 3. 检查循环依赖（拓扑排序）
        self._check_cycle(plan)

        # 4. 检查 step_type 合法性
        for step in plan.steps:
            if step.step_type not in valid_types:
                logger.warning(
                    "Plan 校验警告：未知的 step_type",
                    step_id=step.step_id,
                    step_type=step.step_type,
                    valid_types=list(valid_types),
                )

        # 5. 检查 needs（放宽为警告）
        available_set = set(self.available_needs)
        for step in plan.steps:
            for need in step.needs:
                if need not in available_set:
                    logger.warning(
                        "Plan 校验警告：needs 中包含未知的数据需求",
                        step_id=step.step_id,
                        need=need,
                    )

        logger.debug("Plan 校验通过", steps=len(plan.steps))

    def _check_cycle(self, plan: AnalysisPlan) -> None:
        """检查 Plan 中是否存在循环依赖

        使用 DFS 检测有向图中的环。

        Args:
            plan: 分析计划

        Raises:
            ValueError: 存在循环依赖
        """
        # 构建邻接表
        adj: dict[str, list[str]] = {}
        for step in plan.steps:
            adj[step.step_id] = list(step.deps)

        # DFS 检测环：0=未访问, 1=访问中, 2=已访问
        state: dict[str, int] = {sid: 0 for sid in adj}
        path: list[str] = []

        def dfs(node: str) -> None:
            state[node] = 1
            path.append(node)
            for neighbor in adj.get(node, []):
                if state[neighbor] == 1:
                    # 发现环
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    raise ValueError(
                        f"Plan 校验失败：存在循环依赖 {' -> '.join(cycle)}"
                    )
                if state[neighbor] == 0:
                    dfs(neighbor)
            path.pop()
            state[node] = 2

        for sid in adj:
            if state[sid] == 0:
                dfs(sid)

    def get_plan_summary(self, plan: AnalysisPlan) -> dict:
        """生成 Plan 的摘要信息（用于日志和调试）

        Args:
            plan: 分析计划

        Returns:
            摘要字典
        """
        data_steps = [s for s in plan.steps if s.step_type == "data"]
        reasoning_steps = [s for s in plan.steps if s.step_type == "reasoning"]
        specialist_steps = [s for s in plan.steps if s.step_type == "specialist"]

        # 统计每个步骤的依赖数
        dep_counts = [len(s.deps) for s in plan.steps]
        max_deps = max(dep_counts) if dep_counts else 0

        return {
            "total_steps": len(plan.steps),
            "data_steps": len(data_steps),
            "reasoning_steps": len(reasoning_steps),
            "specialist_steps": len(specialist_steps),
            "max_dependencies": max_deps,
            "step_ids": [s.step_id for s in plan.steps],
        }
