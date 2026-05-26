"""安全数据采集服务：通过 osv-mcp 获取许可证 + SBOM + OSV 漏洞"""

from typing import Any

from app.mcp.client import OSVMCPClient


async def collect_security_data(owner: str, repo: str) -> dict[str, Any]:
    """
    采集安全分析所需的全部数据

    通过 OSVMCPClient 调用 osv-mcp Server 的三个工具：
    1. get_repo_license：获取许可证信息
    2. get_repo_dependencies：获取 SBOM 依赖清单
    3. query_vulnerabilities：查询 OSV 漏洞

    Args:
        owner: 仓库所有者
        repo: 仓库名称

    Returns:
        {  
            "license": {"spdx_id": str, "name": str, "url": str|None},
            "dependencies": [{"name": str, "ecosystem": str, "version": str|None}, ...],
            "vulnerability_count": int,
            "vulnerabilities": [{"id": str, "severity": str, ...}, ...],
        }
    """
    async with OSVMCPClient() as client:
        # 1. 并行获取许可证和依赖清单
        license_result = await client.call_tool(
            "get_repo_license", {"owner": owner, "repo": repo}
        )
        deps_result = await client.call_tool(
            "get_repo_dependencies", {"owner": owner, "repo": repo}
        )

        # 2. 依赖清单不为空时，查询漏洞
        vulnerabilities = []
        if deps_result:
            vuln_result = await client.call_tool(
                "query_vulnerabilities", {"packages": deps_result}
            )
            vulnerabilities = vuln_result if isinstance(vuln_result, list) else []

    return {
        "license": license_result,
        "dependencies": deps_result,
        "vulnerability_count": len(vulnerabilities),
        "vulnerabilities": vulnerabilities,
    }
