"""
Shared Memory — 单次分析执行期间的进程内临时缓存

Phase 5.4 核心组件之一。

设计要点：
- 生命周期：随分析开始而创建，随分析结束而销毁（分钟级）
- 不使用 Redis：进程内 dict 读写零序列化开销，Master 和 Specialist
  在同进程（asyncio 任务）中共享
- 缓存 key："{tool_name}:{canonical_json(args)}"，确保同一 Tool + 同一参数
  永远只执行一次
- needs 反向索引：支持按数据需求名查找所有相关缓存数据

使用方式：
    memory = SharedMemory()
    memory.set_tool_result("github.get_repo_metadata", {"owner": "a", "repo": "b"}, result)
    if memory.has_tool_result("github.get_repo_metadata", {"owner": "a", "repo": "b"}):
        result = memory.get_tool_result("github.get_repo_metadata", {"owner": "a", "repo": "b"})
    community_data = memory.get_by_need("repo_metadata")
"""

import json
from typing import Any

from app.core.logger import get_logger

logger = get_logger(__name__)

# 内部 key 前缀，避免用户自定义 key 与系统 key 冲突
_PREFIX_TOOL = "tool"
_PREFIX_REASONING = "reasoning"
_PREFIX_CONTEXT = "__context__"


def _canonical_json(value: dict) -> str:
    """将 dict 转为规范的 JSON 字符串（排序键，确保相同的参数生成相同的 key）"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _make_tool_key(tool_name: str, args: dict) -> str:
    """生成 Tool 执行结果的缓存 key"""
    return f"{_PREFIX_TOOL}:{tool_name}:{_canonical_json(args)}"


def _make_reasoning_key(step_id: str) -> str:
    """生成 Reasoning 结果的缓存 key"""
    return f"{_PREFIX_REASONING}:{step_id}"


class SharedMemory:
    """进程内共享缓存

    单次分析执行期间，Master Agent 和所有 Specialist Agent
    共享同一个 SharedMemory 实例，确保同一数据只采集一次。

    属性:
        _data: 原始缓存字典，key → value
        _needs_index: 反向索引，need 名称 → list of cache keys
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._needs_index: dict[str, list[str]] = {}

    # ------------------------------------------------------------------
    # Tool 执行结果缓存
    # ------------------------------------------------------------------

    def set_tool_result(
        self,
        tool_name: str,
        args: dict,
        result: Any,
        needs: list[str] | None = None,
    ) -> None:
        """存储 Tool 执行结果

        Args:
            tool_name: Tool 名称
            args: Tool 调用参数
            result: 执行结果（任意类型）
            needs: 该结果满足的数据需求列表，用于反向索引
        """
        key = _make_tool_key(tool_name, args)
        self._data[key] = result

        if needs:
            for need in needs:
                self._needs_index.setdefault(need, []).append(key)

        logger.debug(
            "SharedMemory: Tool 结果已缓存",
            tool_name=tool_name,
            key=key[:80],
            needs=needs,
        )

    def get_tool_result(self, tool_name: str, args: dict) -> Any:
        """获取 Tool 执行结果

        Returns:
            缓存的结果，如果不存在返回 None
        """
        key = _make_tool_key(tool_name, args)
        return self._data.get(key)

    def has_tool_result(self, tool_name: str, args: dict) -> bool:
        """检查 Tool 执行结果是否已缓存"""
        key = _make_tool_key(tool_name, args)
        return key in self._data

    # ------------------------------------------------------------------
    # Reasoning 结果缓存
    # ------------------------------------------------------------------

    def set_reasoning_result(
        self,
        step_id: str,
        result: Any,
        needs: list[str] | None = None,
    ) -> None:
        """存储 Reasoning（LLM 推理）结果

        Args:
            step_id: Step 的唯一标识
            result: 推理结果（通常是字符串或 dict）
            needs: 该结果满足的数据需求列表
        """
        key = _make_reasoning_key(step_id)
        self._data[key] = result

        if needs:
            for need in needs:
                self._needs_index.setdefault(need, []).append(key)

        logger.debug(
            "SharedMemory: Reasoning 结果已缓存",
            step_id=step_id,
            needs=needs,
        )

    def get_reasoning_result(self, step_id: str) -> Any:
        """获取 Reasoning 结果"""
        key = _make_reasoning_key(step_id)
        return self._data.get(key)

    def has_reasoning_result(self, step_id: str) -> bool:
        """检查 Reasoning 结果是否已缓存"""
        key = _make_reasoning_key(step_id)
        return key in self._data

    # ------------------------------------------------------------------
    # 通用存储（用于存放任意自定义数据）
    # ------------------------------------------------------------------

    def set(self, key: str, value: Any, needs: list[str] | None = None) -> None:
        """通用存储方法

        用于存放非 Tool / Reasoning 的数据，如分析上下文、中间计算结果等。
        """
        self._data[key] = value

        if needs:
            for need in needs:
                self._needs_index.setdefault(need, []).append(key)

    def get(self, key: str) -> Any:
        """通用读取方法"""
        return self._data.get(key)

    def has(self, key: str) -> bool:
        """检查 key 是否存在"""
        return key in self._data

    # ------------------------------------------------------------------
    # 分析上下文
    # ------------------------------------------------------------------

    def set_context(self, context: dict) -> None:
        """存储分析上下文

        上下文包含 owner, repo, repo_url 等基础信息，
        所有 Tool 调用时都可从中提取参数。
        """
        self._data[_PREFIX_CONTEXT] = context
        logger.debug(
            "SharedMemory: 上下文已设置",
            owner=context.get("owner"),
            repo=context.get("repo"),
        )

    def get_context(self) -> dict:
        """获取分析上下文"""
        return self._data.get(_PREFIX_CONTEXT, {})

    def get_context_value(self, key: str, default: Any = None) -> Any:
        """从上下文中获取单个值"""
        ctx = self.get_context()
        return ctx.get(key, default)

    # ------------------------------------------------------------------
    # needs 反向索引查询
    # ------------------------------------------------------------------

    def get_by_need(self, need: str) -> list[Any]:
        """按数据需求名查找所有相关缓存数据

        例如 need="repo_metadata" 会返回所有标记为该 need 的
        Tool 执行结果和 Reasoning 结果。

        Args:
            need: 数据需求名称，如 "repo_metadata", "community_benchmark"

        Returns:
            与该 need 相关的所有缓存值列表（可能为空）
        """
        keys = self._needs_index.get(need, [])
        results = []
        for key in keys:
            if key in self._data:
                results.append(self._data[key])
            else:
                # 索引中引用的 key 已被删除（理论上不应发生）
                logger.warning(
                    "SharedMemory: 索引引用了不存在的 key",
                    need=need,
                    key=key[:80],
                )
        return results

    def get_all_by_needs(self, needs: list[str]) -> dict[str, list[Any]]:
        """批量查询多个 needs 的数据

        Args:
            needs: 数据需求名称列表

        Returns:
            dict: {need_name: [data1, data2, ...], ...}
        """
        return {need: self.get_by_need(need) for need in needs}

    def has_need(self, need: str) -> bool:
        """检查是否有任何数据满足该 need"""
        keys = self._needs_index.get(need, [])
        return any(key in self._data for key in keys)

    # ------------------------------------------------------------------
    # 统计与调试
    # ------------------------------------------------------------------

    def get_all(self) -> dict[str, Any]:
        """获取所有缓存数据（调试用）"""
        return dict(self._data)

    def summary(self) -> dict:
        """返回缓存摘要（用于日志和调试）"""
        tool_keys = [k for k in self._data if k.startswith(f"{_PREFIX_TOOL}:")]
        reasoning_keys = [k for k in self._data if k.startswith(f"{_PREFIX_REASONING}:")]
        return {
            "total_entries": len(self._data),
            "tool_results": len(tool_keys),
            "reasoning_results": len(reasoning_keys),
            "indexed_needs": list(self._needs_index.keys()),
        }

    def __repr__(self) -> str:
        return f"SharedMemory(entries={len(self._data)}, needs={list(self._needs_index.keys())})"
