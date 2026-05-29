"""
Tool Executor

解析 LLM 返回的 tool_calls，执行对应工具，返回 observation。
是 ReAct Loop 中 Action → Observation 的桥梁。
"""
import asyncio
import functools
import inspect
import json
import time
from typing import Any

from app.core.logger import get_logger

from app.llm.schemas import ToolCall, ToolResult

from .registry import ToolRegistry, get_registry
from .tool import Tool, ToolExecutionResult

logger = get_logger(__name__)


class ToolExecutor:
    """工具执行器

    接收 LLM 的 tool_calls，在 Registry 中查找对应 Tool，
    执行 handler，将结果封装为 ToolExecutionResult 返回。

    支持同步和异步 handler 的自动识别与执行。
    """

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        """
        Args:
            registry: ToolRegistry 实例，默认使用全局单例
        """
        self.registry = registry or get_registry()

    async def execute(self, tool_call: dict) -> ToolExecutionResult:
        """执行单个 tool_call

        Args:
            tool_call: LLM 返回的 tool_call，格式：
                {"id": "call_xxx", "name": "tool_name", "arguments": "{...}"}

        Returns:
            ToolExecutionResult：执行结果（成功或失败）
        """
        tool_call_id = tool_call.get("id", "")
        tool_name = tool_call.get("name", "")
        arguments_str = tool_call.get("arguments", "{}")

        start_time = time.perf_counter()

        # 1. 从 Registry 查找 Tool
        tool = self.registry.get(tool_name)
        if tool is None:
            elapsed = (time.perf_counter() - start_time) * 1000
            logger.warning(
                "Tool 未找到",
                tool_name=tool_name,
                available=list(self.registry.list_tools())[:10],
            )
            return ToolExecutionResult(
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                output=None,
                is_error=True,
                error_message=f"工具 '{tool_name}' 未在 Registry 中注册",
                execution_time_ms=elapsed,
            )

        # 2. 解析参数（JSON 字符串 → dict）
        try:
            args = json.loads(arguments_str) if arguments_str else {}
            if not isinstance(args, dict):
                args = {"value": args}
        except json.JSONDecodeError as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            logger.warning(
                "参数 JSON 解析失败",
                tool_name=tool_name,
                arguments=arguments_str[:200],
                error=str(e),
            )
            return ToolExecutionResult(
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                output=None,
                is_error=True,
                error_message=f"参数 JSON 解析失败: {e}",
                execution_time_ms=elapsed,
            )

        # 3. 执行 handler
        try:
            result = await self._invoke_handler(tool.handler, args)
            elapsed = (time.perf_counter() - start_time) * 1000

            logger.info(
                "工具执行成功",
                tool_name=tool_name,
                execution_time_ms=round(elapsed, 2),
            )
            return ToolExecutionResult(
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                output=result,
                is_error=False,
                execution_time_ms=elapsed,
            )

        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            logger.error(
                "工具执行失败",
                tool_name=tool_name,
                error=str(e),
                error_type=type(e).__name__,
                execution_time_ms=round(elapsed, 2),
            )
            return ToolExecutionResult(
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                output=None,
                is_error=True,
                error_message=f"{type(e).__name__}: {e}",
                execution_time_ms=elapsed,
            )

    async def execute_all(self, tool_calls: list[dict]) -> list[ToolExecutionResult]:
        """并行执行多个 tool_call

        LLM 可能在一轮中请求调用多个工具（如同时获取 metadata 和 contributors）。
        使用 asyncio.gather 实现并行执行。

        Args:
            tool_calls: LLM 返回的 tool_calls 列表

        Returns:
            ToolExecutionResult 列表（顺序与输入一致）
        """
        if not tool_calls:
            return []

        # 并行执行所有 tool_call
        # 注意：execute() 内部已 try/except 所有异常，不会抛出
        tasks = [self.execute(tc) for tc in tool_calls]
        return await asyncio.gather(*tasks)

    async def _invoke_handler(
        self, handler: Any, args: dict[str, Any]
    ) -> Any:
        """调用 handler，自动处理同步/异步函数

        根据函数签名，将 args dict 中的参数按名传递给 handler。
        如果 handler 不接受 **kwargs 且 args 中有未声明的参数，
        则只传递 handler 声明的参数。
        """
        # 获取函数签名，过滤掉 handler 不认识的参数
        sig = inspect.signature(handler)
        valid_params = set(sig.parameters.keys())

        # 如果 handler 接受 **kwargs，直接传全部参数
        accepts_kwargs = any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in sig.parameters.values()
        )

        if accepts_kwargs:
            call_args = args
        else:
            call_args = {k: v for k, v in args.items() if k in valid_params}

        # 判断是同步还是异步函数
        if asyncio.iscoroutinefunction(handler):
            return await handler(**call_args)
        else:
            # 同步函数在线程池中执行（防止阻塞事件循环）
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, functools.partial(handler, **call_args)
            )

    def results_to_messages(
        self, results: list[ToolExecutionResult]
    ) -> list[dict]:
        """将 ToolExecutionResult 列表转换为 LLM 消息格式

        返回的消息可直接追加到对话历史中，让 LLM 看到 observation。

        格式（OpenAI 兼容）：
            [
                {"role": "tool", "tool_call_id": "call_xxx", "content": "..."},
                ...
            ]
        """
        messages = []
        for result in results:
            messages.append({
                "role": "tool",
                "tool_call_id": result.tool_call_id,
                "name": result.tool_name,
                "content": result.to_observation(),
            })
        return messages
