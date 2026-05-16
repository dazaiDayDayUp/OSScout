#!/usr/bin/env python3
"""
Code Analysis MCP Server

提供代码静态分析能力：
- run_radon：圈复杂度分析（使用 radon Python API）
- run_security_scan：简化安全扫描（检查常见危险模式）

Windows 上 subprocess 与 MCP stdio 有兼容性问题，
故采用纯 Python API 实现，避免命令行调用。
"""

import ast
import json
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from radon.complexity import cc_visit

server = Server("code-analysis-mcp")

# 需要排除的目录（虚拟环境、缓存、测试目录等）
_EXCLUDE_DIRS = {"venv", ".venv", "env", "__pycache__", ".git", "node_modules", ".tox", "build", "dist", "tests", "test"}

# 常见危险函数/模式
_DANGEROUS_PATTERNS = {
    "eval": "使用 eval() 存在代码注入风险",
    "exec": "使用 exec() 存在代码注入风险",
    "compile": "使用 compile() 配合动态执行存在代码注入风险",
    "input": "Python 2 的 input() 等价于 eval(raw_input())，存在注入风险",
    "pickle.loads": "pickle 反序列化不受信任的数据可导致任意代码执行",
    "yaml.load": "PyYAML 的 load() 默认使用不安全加载器，可导致任意代码执行",
    "subprocess.call": "subprocess 调用应显式传递列表参数，避免 shell 注入",
    "os.system": "os.system() 存在命令注入风险，建议使用 subprocess.run",
    "os.popen": "os.popen() 存在命令注入风险，建议使用 subprocess.run",
}

TOOLS = [
    Tool(
        name="run_radon",
        description="使用 radon 分析代码圈复杂度。返回平均复杂度和复杂度分布。",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "待分析的代码目录绝对路径"},
            },
            "required": ["path"],
        },
    ),
    Tool(
        name="run_security_scan",
        description="扫描代码中的常见安全风险（危险函数调用、不安全的反序列化等）。返回漏洞列表。",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "待扫描的代码目录绝对路径"},
            },
            "required": ["path"],
        },
    ),
]


def _should_exclude(path: Path) -> bool:
    """检查路径是否包含需要排除的目录"""
    parts = set(path.parts)
    return not parts.isdisjoint(_EXCLUDE_DIRS)


def _collect_python_files(root: Path) -> list[Path]:
    """收集目录下所有 Python 文件（排除指定目录）"""
    files = []
    for py_file in root.rglob("*.py"):
        if not _should_exclude(py_file):
            files.append(py_file)
    return files


@server.list_tools()
async def list_tools() -> list[Tool]:
    """返回所有可用的代码分析工具"""
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """处理工具调用请求"""
    path = Path(arguments["path"])

    if name == "run_radon":
        total_complexity = 0
        total_blocks = 0
        file_count = 0
        distribution = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "F": 0}

        for py_file in _collect_python_files(path):
            try:
                code = py_file.read_text(encoding="utf-8", errors="replace")
                blocks = cc_visit(code)
                if blocks:
                    file_count += 1
                for block in blocks:
                    total_complexity += block.complexity
                    total_blocks += 1
                    rank = _complexity_to_rank(block.complexity)
                    distribution[rank] = distribution.get(rank, 0) + 1
            except Exception:
                # 忽略解析失败的文件（如语法不完整的文件）
                pass

        avg_complexity = round(total_complexity / total_blocks, 2) if total_blocks > 0 else 0

        return [TextContent(
            type="text",
            text=json.dumps({
                "average_complexity": avg_complexity,
                "total_blocks": total_blocks,
                "file_count": file_count,
                "complexity_distribution": distribution,
            }, ensure_ascii=False)
        )]

    elif name == "run_security_scan":
        findings = []

        for py_file in _collect_python_files(path):
            try:
                code = py_file.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(code)

                for node in ast.walk(tree):
                    # 检查函数调用
                    if isinstance(node, ast.Call):
                        func_name = _get_call_name(node.func)
                        if func_name in _DANGEROUS_PATTERNS:
                            findings.append({
                                "file": str(py_file.relative_to(path)),
                                "line": getattr(node, "lineno", 0),
                                "rule": func_name,
                                "message": _DANGEROUS_PATTERNS[func_name],
                                "severity": "HIGH",
                            })

                    # 检查硬编码密码/密钥模式
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name):
                                name_lower = target.id.lower()
                                if any(kw in name_lower for kw in ["password", "secret", "api_key", "token"]):
                                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                                        findings.append({
                                            "file": str(py_file.relative_to(path)),
                                            "line": getattr(node, "lineno", 0),
                                            "rule": "hardcoded_secret",
                                            "message": f"疑似硬编码敏感信息: {target.id}",
                                            "severity": "HIGH",
                                        })

            except Exception:
                pass

        severity_counts = {}
        for f in findings:
            sev = f.get("severity", "UNKNOWN")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        return [TextContent(
            type="text",
            text=json.dumps({
                "findings": findings,
                "total": len(findings),
                "severity_counts": severity_counts,
            }, ensure_ascii=False)
        )]

    else:
        raise ValueError(f"未知工具: {name}")


def _complexity_to_rank(complexity: int) -> str:
    """将圈复杂度数值映射到 radon 等级"""
    if complexity <= 5:
        return "A"
    elif complexity <= 10:
        return "B"
    elif complexity <= 20:
        return "C"
    elif complexity <= 30:
        return "D"
    elif complexity <= 40:
        return "E"
    return "F"


def _get_call_name(func) -> str:
    """从 AST 节点提取函数调用的完整名称"""
    if isinstance(func, ast.Name):
        return func.id
    elif isinstance(func, ast.Attribute):
        parts = []
        node = func
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


async def main() -> None:
    """启动 MCP Server（stdio 模式）"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
