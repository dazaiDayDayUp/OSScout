#!/usr/bin/env python3
"""
OSV MCP Server

安全数据采集中心，通过 MCP 协议暴露安全分析所需的全部工具：
- get_repo_license：获取仓库许可证信息
- get_repo_dependencies：获取仓库 SBOM 依赖清单
- query_vulnerabilities：调用 OSV API 批量查询漏洞

通信方式：stdio（标准输入输出），JSON-RPC 2.0 格式。
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# ═══════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════

GITHUB_API_BASE = "https://api.github.com"
OSV_API_BASE = "https://api.osv.dev"

_GITHUB_HEADERS = {
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "osscout-osv-mcp",
}
if token := os.environ.get("GITHUB_TOKEN"):
    _GITHUB_HEADERS["Authorization"] = f"token {token}"

# 并发控制
_github_semaphore = asyncio.Semaphore(6)
_osv_semaphore = asyncio.Semaphore(10)

# OSV 支持的生态系统白名单
_OSV_SUPPORTED_ECOSYSTEMS = {
    "PyPI", "npm", "Go", "Maven", "NuGet", "crates.io",
    "Packagist", "RubyGems", "Linux", "Alpine", "Debian",
    "Ubuntu", "Android", "OSS-Fuzz", "Hex", "Pub",
}

_PURL_ECOSYSTEM_MAP = {
    "pypi": "PyPI",
    "npm": "npm",
    "golang": "Go",
    "maven": "Maven",
    "nuget": "NuGet",
    "cargo": "crates.io",
    "composer": "Packagist",
    "gem": "RubyGems",
}


# ═══════════════════════════════════════════════════════════════
# 底层 HTTP 请求
# ═══════════════════════════════════════════════════════════════


async def _github_get(path: str, extra_headers: dict | None = None) -> dict | list:
    """发送 GitHub API GET 请求"""
    headers = {**_GITHUB_HEADERS, **(extra_headers or {})}
    async with _github_semaphore:
        async with httpx.AsyncClient(headers=headers, timeout=30, follow_redirects=True) as client:
            url = f"{GITHUB_API_BASE}{path}"
            response = await client.get(url)
            if response.status_code == 404:
                return {}
            response.raise_for_status()
            return response.json()


async def _osv_post(path: str, payload: dict) -> dict:
    """发送 OSV API POST 请求"""
    async with _osv_semaphore:
        async with httpx.AsyncClient(timeout=30) as client:
            url = f"{OSV_API_BASE}{path}"
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()


async def _osv_get(path: str) -> dict:
    """发送 OSV API GET 请求"""
    async with _osv_semaphore:
        async with httpx.AsyncClient(timeout=30) as client:
            url = f"{OSV_API_BASE}{path}"
            response = await client.get(url)
            response.raise_for_status()
            return response.json()


# ═══════════════════════════════════════════════════════════════
# Tool 定义
# ═══════════════════════════════════════════════════════════════


TOOLS = [
    Tool(
        name="get_repo_license",
        description="获取 GitHub 仓库的许可证信息，包括 SPDX ID、许可证名称等",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "仓库所有者"},
                "repo": {"type": "string", "description": "仓库名称"},
            },
            "required": ["owner", "repo"],
        },
    ),
    Tool(
        name="get_repo_dependencies",
        description="获取仓库的 SBOM（软件物料清单）依赖列表，通过 GitHub Dependency Graph API",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "仓库所有者"},
                "repo": {"type": "string", "description": "仓库名称"},
            },
            "required": ["owner", "repo"],
        },
    ),
    Tool(
        name="query_vulnerabilities",
        description="调用 OSV API 批量查询指定依赖包的已知安全漏洞。返回去重后的漏洞列表，包含 severity、published、fixed_versions 等",
        inputSchema={
            "type": "object",
            "properties": {
                "packages": {
                    "type": "array",
                    "description": "依赖包列表，每个包包含 name、ecosystem、version（可选）",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "ecosystem": {"type": "string"},
                            "version": {"type": ["string", "null"]},
                        },
                        "required": ["name", "ecosystem"],
                    },
                },
            },
            "required": ["packages"],
        },
    ),
]


# ═══════════════════════════════════════════════════════════════
# MCP Server 初始化
# ═══════════════════════════════════════════════════════════════


server = Server("osv-mcp")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """返回所有可用的安全分析工具"""
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """处理工具调用请求"""

    if name == "get_repo_license":
        data = await _get_repo_license(arguments["owner"], arguments["repo"])

    elif name == "get_repo_dependencies":
        data = await _get_repo_dependencies(arguments["owner"], arguments["repo"])

    elif name == "query_vulnerabilities":
        data = await _query_vulnerabilities(arguments["packages"])

    else:
        raise ValueError(f"未知工具: {name}")

    return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]


# ═══════════════════════════════════════════════════════════════
# 工具实现
# ═══════════════════════════════════════════════════════════════


async def _get_repo_license(owner: str, repo: str) -> dict:
    """获取仓库许可证信息"""
    metadata = await _github_get(f"/repos/{owner}/{repo}")
    license_info = metadata.get("license") or {}
    return {
        "spdx_id": license_info.get("spdx_id", "NOASSERTION"),
        "name": license_info.get("name", "Unknown"),
        "url": license_info.get("url"),
    }


async def _get_repo_dependencies(owner: str, repo: str) -> list[dict]:
    """
    获取仓库依赖列表

    通过 GitHub SBOM API 获取，过滤掉 OSV 不支持的生态系统
    """
    headers = {"Accept": "application/vnd.github+json"}
    data = await _github_get(
        f"/repos/{owner}/{repo}/dependency-graph/sbom",
        extra_headers=headers,
    )

    if not data or "sbom" not in data:
        return []

    packages = []
    for pkg in data["sbom"].get("packages", []):
        name = pkg.get("name", "")
        # 跳过仓库本身和根包
        if name in (f"{owner}/{repo}", repo, ".", ""):
            continue

        # 从 externalRefs 提取 PURL
        ecosystem = None
        version = None
        for ref in pkg.get("externalRefs", []):
            if ref.get("referenceType") == "purl":
                purl = ref.get("referenceLocator", "")
                ecosystem, version = _parse_purl(purl)
                break

        # 只保留 OSV 支持的生态系统
        eco = ecosystem or "Unknown"
        if eco not in _OSV_SUPPORTED_ECOSYSTEMS:
            continue

        packages.append({
            "name": name,
            "ecosystem": eco,
            "version": version,
        })

    return packages


def _parse_purl(purl: str) -> tuple[str | None, str | None]:
    """解析 PURL 提取生态系统和版本"""
    if not purl.startswith("pkg:"):
        return None, None
    try:
        rest = purl[4:]
        ecosystem_raw = rest.split("/")[0]
        ecosystem = _PURL_ECOSYSTEM_MAP.get(ecosystem_raw, ecosystem_raw)
        version = None
        if "@" in rest:
            version = rest.split("@")[-1]
        return ecosystem, version
    except Exception:
        return None, None


async def _query_vulnerabilities(packages: list[dict]) -> list[dict]:
    """
    调用 OSV API 批量查询漏洞

    流程：
    1. querybatch 获取漏洞 ID 列表
    2. 并行获取每个漏洞的完整详情
    3. 标准化并去重
    """
    if not packages:
        return []

    # 第一步：querybatch 获取漏洞 ID
    vuln_ids = await _osv_query_batch(packages)
    if not vuln_ids:
        return []

    # 第二步：并行获取漏洞详情
    detail_tasks = [_fetch_vuln_detail(vid) for vid in vuln_ids]
    details = await asyncio.gather(*detail_tasks, return_exceptions=True)

    # 标准化并去重
    unique: list[dict] = []
    seen: set[str] = set()
    for d in details:
        if isinstance(d, Exception):
            continue
        if d["id"] not in seen:
            seen.add(d["id"])
            unique.append(d)

    return unique


async def _osv_query_batch(packages: list[dict]) -> list[str]:
    """OSV querybatch 获取漏洞 ID 列表"""
    batch_size = 100
    all_ids: list[str] = []

    for i in range(0, len(packages), batch_size):
        batch = packages[i:i + batch_size]
        queries = []
        for pkg in batch:
            query: dict[str, Any] = {
                "package": {
                    "name": pkg["name"],
                    "ecosystem": pkg["ecosystem"],
                }
            }
            if pkg.get("version"):
                query["version"] = pkg["version"]
            queries.append(query)

        result = await _osv_post("/v1/querybatch", {"queries": queries})
        for resp in result.get("results", []):
            for vuln in resp.get("vulns", []):
                all_ids.append(vuln["id"])

    return list(dict.fromkeys(all_ids))


async def _fetch_vuln_detail(vuln_id: str) -> dict:
    """获取单个漏洞的完整详情"""
    data = await _osv_get(f"/v1/vulns/{vuln_id}")
    return _normalize_vuln(data)


def _normalize_vuln(vuln: dict) -> dict:
    """标准化 OSV 漏洞数据，支持 CVSS_V3 和 CVSS_V4"""
    severity = "UNKNOWN"
    for sev in vuln.get("severity", []):
        if sev.get("type") in ("CVSS_V4", "CVSS_V3"):
            score_str = sev.get("score", "")
            try:
                score_val = float(score_str)
                severity = _cvss_score_to_level(score_val)
                break
            except ValueError:
                severity = _cvss_vector_to_level(score_str)
                break

    published = vuln.get("published", "")
    response_days = None
    if published:
        try:
            pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            response_days = (datetime.now(timezone.utc) - pub_dt).days
        except ValueError:
            pass

    fixed_versions: list[str] = []
    for affected in vuln.get("affected", []):
        for rng in affected.get("ranges", []):
            for event in rng.get("events", []):
                if "fixed" in event:
                    fixed_versions.append(event["fixed"])

    return {
        "id": vuln.get("id", ""),
        "summary": vuln.get("summary", ""),
        "details": vuln.get("details", ""),
        "severity": severity,
        "published": published,
        "fixed_versions": fixed_versions,
        "response_days": response_days,
        "aliases": vuln.get("aliases", []),
    }


def _cvss_score_to_level(score: float) -> str:
    """CVSS 数值分数转等级"""
    if score >= 7.0:
        return "HIGH"
    elif score >= 4.0:
        return "MEDIUM"
    return "LOW"


def _cvss_vector_to_level(vector: str) -> str:
    """从 CVSS 向量字符串推断严重程度"""
    vector_upper = vector.upper()
    if "AV:N" in vector_upper and "AC:L" in vector_upper and "PR:N" in vector_upper:
        return "HIGH"
    elif "AV:N" in vector_upper:
        return "MEDIUM"
    return "LOW"


# ═══════════════════════════════════════════════════════════════
# 启动入口
# ═══════════════════════════════════════════════════════════════


async def main() -> None:
    """启动 MCP Server（stdio 模式）"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
