"""
Tool Registry + @tool 装饰器

核心能力：
1. @tool 装饰器：自动从函数签名生成 JSON Schema，零配置接入
2. ToolRegistry：统一管理所有 Tool 的注册、查询、导出
"""
from __future__ import annotations

import inspect
import json
from typing import Any, Callable, Coroutine, Union, get_args, get_origin

from app.core.logger import get_logger

from .tool import Tool, ToolExecutionResult, ToolSource

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# 全局 Registry 实例（模块级单例）
# ---------------------------------------------------------------------------

_default_registry: "ToolRegistry | None" = None


def get_registry() -> "ToolRegistry":
    """获取全局 ToolRegistry 实例"""
    global _default_registry
    if _default_registry is None:
        _default_registry = ToolRegistry()
    return _default_registry


# ---------------------------------------------------------------------------
# 类型映射：Python 类型 → JSON Schema 类型
# ---------------------------------------------------------------------------

_TYPE_MAP: dict[type, dict] = {
    str: {"type": "string"},
    int: {"type": "integer"},
    float: {"type": "number"},
    bool: {"type": "boolean"},
    list: {"type": "array"},
    dict: {"type": "object"},
}


def _python_type_to_json_schema(py_type: Any) -> dict:
    """将 Python 类型注解转换为 JSON Schema 类型描述

    支持：基础类型、Optional[X]、list[X]、Union[X, Y, ...]
    不支持的类型返回空 dict（表示不限制类型）。
    """
    # None 类型
    if py_type is type(None):
        return {}

    # 处理 Union 类型（如 str | None、Optional[str]）
    origin = get_origin(py_type)
    if origin is Union:
        args = [a for a in get_args(py_type) if a is not type(None)]
        if len(args) == 1:
            return _python_type_to_json_schema(args[0])
        # 多个非 None 类型，取第一个能映射的
        for arg in args:
            schema = _python_type_to_json_schema(arg)
            if schema:
                return schema
        return {}

    # 处理 list[str] 等泛型
    if origin is list:
        item_type_args = get_args(py_type)
        if item_type_args:
            items_schema = _python_type_to_json_schema(item_type_args[0])
            return {"type": "array", "items": items_schema or {}}
        return {"type": "array"}

    # 处理 dict[str, Any] 等泛型
    if origin is dict:
        return {"type": "object"}

    # 基础类型映射
    return _TYPE_MAP.get(py_type, {})


def _extract_param_descriptions(docstring: str | None) -> dict[str, str]:
    """从 docstring 中提取参数描述

    简单解析格式：
        Args:
            param_name: 描述文字
            another_param: 描述
    """
    if not docstring:
        return {}

    descriptions: dict[str, str] = {}
    lines = docstring.split("\n")
    in_args_section = False

    for line in lines:
        stripped = line.strip()

        # 检测 Args: / Parameters: 区块开始
        if stripped.lower() in ("args:", "parameters:", "arguments:"):
            in_args_section = True
            continue

        # 检测其他区块开始（结束 args 解析）
        if stripped.endswith(":") and in_args_section:
            if stripped.lower() not in (
                "args:",
                "parameters:",
                "arguments:",
            ):
                in_args_section = False
                continue

        # 解析参数行："param_name: 描述"
        if in_args_section and ":" in stripped:
            # 跳过空行或缩进过的（属于上一个参数的多行描述）
            if not line.startswith(" ") and not line.startswith("\t"):
                # 可能是下一个区块标题，跳过
                if stripped.endswith(":"):
                    in_args_section = False
                    continue

            parts = stripped.split(":", 1)
            if len(parts) == 2:
                param_name = parts[0].strip()
                desc = parts[1].strip()
                # 过滤掉非标识符的行（如类型注解行）
                if param_name.isidentifier() and desc:
                    descriptions[param_name] = desc

    return descriptions


def _build_json_schema(
    func: Callable,
    description: str,
    param_descriptions: dict[str, str],
) -> dict:
    """从函数签名自动生成 JSON Schema（OpenAI function parameters 格式）"""
    sig = inspect.signature(func)
    properties: dict[str, dict] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        # 跳过 *args, **kwargs
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue

        # 类型映射
        schema: dict = {}
        if param.annotation is not inspect.Parameter.empty:
            schema = _python_type_to_json_schema(param.annotation)

        # 参数描述（从 docstring 提取）
        if param_name in param_descriptions:
            schema["description"] = param_descriptions[param_name]

        properties[param_name] = schema

        # 判断参数是否必填
        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


# ---------------------------------------------------------------------------
# @tool 装饰器
# ---------------------------------------------------------------------------

def tool(
    description: str = "",
    name: str | None = None,
    source: ToolSource = ToolSource.LOCAL,
    metadata: dict | None = None,
    registry: ToolRegistry | None = None,
) -> Callable:
    """将函数注册为 LLM 可调用的 Tool

    自动从函数签名生成 JSON Schema，从 docstring 提取参数描述。

    用法示例：
        @tool(description="获取 GitHub 仓库的元数据信息")
        async def get_repo_metadata(owner: str, repo: str) -> dict:
            \"\"\"
            获取仓库元数据

            Args:
                owner: 仓库所有者用户名
                repo: 仓库名称
            \"\"\"
            ...

    参数:
        description: 工具功能描述（LLM 决定"什么时候用"的依据）
                     如果为空，则尝试从函数 docstring 提取第一句
        name: 工具唯一标识，默认使用函数名
        source: 工具来源，默认 LOCAL
        metadata: 额外元数据
        registry: 目标注册表，None 时使用全局单例
    """

    def decorator(func: Callable) -> Callable:
        nonlocal description, name

        # 如果未提供 description，尝试从 docstring 提取第一句
        if not description and func.__doc__:
            first_line = func.__doc__.strip().split("\n")[0].strip()
            if first_line:
                description = first_line

        # 如果仍未提供，使用函数名作为兜底
        if not description:
            description = f"调用 {func.__name__}"

        # 工具名称
        tool_name = name or func.__name__

        # 提取参数描述
        param_descriptions = _extract_param_descriptions(func.__doc__)

        # 生成 JSON Schema
        parameters = _build_json_schema(func, description, param_descriptions)

        # 创建 Tool 对象
        tool_obj = Tool(
            name=tool_name,
            description=description,
            parameters=parameters,
            handler=func,
            source=source,
            metadata=metadata or {},
        )

        # 注册到指定 Registry（默认全局单例）
        # 注意：不能用 `registry or get_registry()`，因为空 Registry 的 __len__=0 会被视为 falsy
        target_registry = registry if registry is not None else get_registry()
        target_registry.register(tool_obj)

        logger.debug(
            "Tool 已注册",
            name=tool_name,
            source=source.value,
            params=list(parameters.get("properties", {}).keys()),
        )

        # 返回原函数（保持调用方式不变）
        return func

    return decorator


# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------

class ToolRegistry:
    """工具注册中心

    支持三种注册方式：
    1. @tool 装饰器 — 自动从函数签名生成 JSON Schema
    2. register() — 手动注册已有的 Tool 对象
    3. 从 MCP Server / RAG Adapter 动态发现
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """注册一个 Tool"""
        if tool.name in self._tools:
            logger.warning(
                "Tool 重复注册，覆盖旧定义",
                name=tool.name,
                old_source=self._tools[tool.name].source.value,
                new_source=tool.source.value,
            )
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        """按名称获取 Tool"""
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        """获取所有已注册的 Tool"""
        return list(self._tools.values())

    def list_by_source(self, source: ToolSource) -> list[Tool]:
        """按来源过滤 Tool 列表"""
        return [t for t in self._tools.values() if t.source == source]

    def to_openai_schemas(self) -> list[dict]:
        """导出所有 Tool 的 OpenAI 格式 schema 列表

        结果可直接传给 LLMProvider.chat(tools=...)
        """
        return [t.to_openai_schema() for t in self._tools.values()]

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def __repr__(self) -> str:
        sources = {}
        for t in self._tools.values():
            sources[t.source.value] = sources.get(t.source.value, 0) + 1
        return f"ToolRegistry(tools={len(self._tools)}, sources={sources})"
