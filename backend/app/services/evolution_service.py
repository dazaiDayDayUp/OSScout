"""技术演进数据采集：releases + SBOM + PyPI/npm 最新版本 + Breaking Change 检测"""

import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.mcp.client import GitHubMCPClient, OSVMCPClient


# ═══════════════════════════════════════════════════════════════
# 版本号解析
# ═══════════════════════════════════════════════════════════════

_RE_SEMVER = re.compile(
    r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:[-+.]?[a-zA-Z0-9]+)?$"
)


class SemVer:
    """简化版语义化版本号解析器"""

    def __init__(self, version_str: str):
        self.raw = version_str.strip()
        self.major = 0
        self.minor = 0
        self.patch = 0
        self._parse()

    def _parse(self) -> None:
        """从版本号字符串提取 major/minor/patch"""
        m = _RE_SEMVER.match(self.raw)
        if m:
            self.major = int(m.group(1)) if m.group(1) else 0
            self.minor = int(m.group(2)) if m.group(2) else 0
            self.patch = int(m.group(3)) if m.group(3) else 0

    def major_gap(self, other: "SemVer") -> int:
        """计算两个版本号之间的 major 版本差距（绝对值）"""
        return abs(self.major - other.major)

    def is_valid(self) -> bool:
        """判断是否成功解析出有效版本号"""
        return self.major > 0 or self.minor > 0 or self.patch > 0

    def __repr__(self) -> str:
        return f"SemVer({self.raw} -> {self.major}.{self.minor}.{self.patch})"


# ═══════════════════════════════════════════════════════════════
# 包管理平台版本查询
# ═══════════════════════════════════════════════════════════════

# 并发控制：避免对包管理平台过多请求
_pkg_semaphore = asyncio.Semaphore(8)


async def _get_pypi_latest(name: str) -> str | None:
    """查询 PyPI 上某个包名的最新版本"""
    async with _pkg_semaphore:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"https://pypi.org/pypi/{name}/json")
                if resp.status_code == 200:
                    return resp.json()["info"]["version"]
        except Exception:
            pass
        return None


async def _get_npm_latest(name: str) -> str | None:
    """查询 npm registry 上某个包名的最新版本"""
    async with _pkg_semaphore:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"https://registry.npmjs.org/{name}")
                if resp.status_code == 200:
                    return resp.json()["dist-tags"]["latest"]
        except Exception:
            pass
        return None


async def _get_latest_version(pkg: dict) -> dict[str, Any] | None:
    """
    查询单个依赖包的最新版本

    Args:
        pkg: {"name": str, "ecosystem": str, "version": str|None}

    Returns:
        {"name": str, "ecosystem": str, "current": str|None, "latest": str|None}
    """
    name = pkg["name"]
    ecosystem = pkg.get("ecosystem", "Unknown")
    current = pkg.get("version")

    latest: str | None = None

    if ecosystem == "PyPI":
        latest = await _get_pypi_latest(name)
    elif ecosystem == "npm":
        latest = await _get_npm_latest(name)
    # 其他生态系统 Phase 1 暂不查询

    if not latest:
        return None

    return {
        "name": name,
        "ecosystem": ecosystem,
        "current": current,
        "latest": latest,
    }


# ═══════════════════════════════════════════════════════════════
# Breaking Change 检测
# ═══════════════════════════════════════════════════════════════

_BREAKING_KEYWORDS = [
    "breaking", "breaking change", "breaking-change",
    "不兼容", "破坏性", "废弃", "deprecated", "removed",
    "v2", "v3", "v4", "v5",  # 版本号暗示 major bump
]


def _detect_breaking_in_text(text: str) -> bool:
    """检查文本中是否包含 Breaking Change 相关关键词"""
    if not text:
        return False
    text_lower = text.lower()
    return any(kw in text_lower for kw in _BREAKING_KEYWORDS)


def _extract_version_from_tag(tag: str) -> SemVer | None:
    """从 release tag 中提取版本号"""
    ver = SemVer(tag)
    return ver if ver.is_valid() else None


def _analyze_breaking_changes(releases: list[dict]) -> dict[str, Any]:
    """
    分析发布历史中的 Breaking Change 指标

    检测两个信号：
    1. release notes / tag_name 中是否出现 breaking change 关键词
    2. 相邻 release 之间是否有 major version 跳变

    Returns:
        {
            "total_releases": int,
            "releases_with_breaking_notes": int,
            "major_bump_count": int,
            "breaking_keywords_found": list[str],
        }
    """
    if not releases:
        return {
            "total_releases": 0,
            "releases_with_breaking_notes": 0,
            "major_bump_count": 0,
            "breaking_keywords_found": [],
        }

    total = len(releases)
    breaking_notes = 0
    keywords_found: set[str] = set()

    # 解析每个 release 的版本号
    versions: list[tuple[int, SemVer | None]] = []
    for i, rel in enumerate(releases):
        tag = rel.get("tag_name", "")
        ver = _extract_version_from_tag(tag)
        versions.append((i, ver))

        # 检查 release notes
        body = rel.get("body") or ""
        name = rel.get("name") or ""
        combined = f"{name} {body}"

        text_lower = combined.lower()
        for kw in _BREAKING_KEYWORDS:
            if kw in text_lower:
                keywords_found.add(kw)

        if _detect_breaking_in_text(combined):
            breaking_notes += 1

    # 检查 major version bump（按发布时间的逆序，即从新到旧）
    major_bump = 0
    valid_versions = [v for _, v in versions if v is not None]
    for i in range(len(valid_versions) - 1):
        current = valid_versions[i]
        previous = valid_versions[i + 1]
        if current.major > previous.major:
            major_bump += 1

    return {
        "total_releases": total,
        "releases_with_breaking_notes": breaking_notes,
        "major_bump_count": major_bump,
        "breaking_keywords_found": sorted(keywords_found),
    }


# ═══════════════════════════════════════════════════════════════
# 发布频率统计
# ═══════════════════════════════════════════════════════════════


def _count_recent_releases(releases: list[dict], months: int = 12) -> int:
    """统计最近 N 个月内的发布数量"""
    if not releases:
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=months * 30)
    count = 0

    for rel in releases:
        published_at = rel.get("published_at", "")
        if not published_at:
            continue
        try:
            # 处理 ISO 8601 格式，如 "2024-01-15T10:30:00Z"
            pub_dt = datetime.fromisoformat(
                published_at.replace("Z", "+00:00")
            )
            if pub_dt >= cutoff:
                count += 1
        except (ValueError, TypeError):
            continue

    return count


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════


async def collect_evolution_data(owner: str, repo: str) -> dict[str, Any]:
    """
    采集技术演进分析所需的全部数据

    流程：
    1. 并行调用 github-mcp（releases）和 osv-mcp（dependencies）
    2. 从 releases 计算发布频率和 Breaking Change 指标
    3. 并行查询每个依赖包的最新版本

    Args:
        owner: 仓库所有者
        repo: 仓库名称

    Returns:
        {
            "releases": [...],  # GitHub releases 原始数据
            "release_count_12m": int,
            "dependencies": [...],  # SBOM 依赖列表
            "dependency_versions": [...],  # 含 latest 的版本对比
            "breaking_change": {...},
        }
    """
    # 1. 并行获取 releases 和 SBOM
    releases: list[dict] = []
    dependencies: list[dict] = []

    async with GitHubMCPClient() as gh_client:
        releases = await gh_client.call_tool(
            "list_releases", {"owner": owner, "repo": repo}
        ) or []

    async with OSVMCPClient() as osv_client:
        dependencies = await osv_client.call_tool(
            "get_repo_dependencies", {"owner": owner, "repo": repo}
        ) or []

    # 2. 计算发布频率（最近12个月）
    release_count_12m = _count_recent_releases(releases)

    # 3. Breaking Change 分析
    breaking = _analyze_breaking_changes(releases)

    # 4. 查询依赖最新版本（限制前 20 个核心依赖，避免请求过多）
    dep_versions: list[dict[str, Any]] = []
    if dependencies:
        # 只查询前 20 个（SBOM 中通常是核心依赖在前）
        to_query = dependencies[:20]
        version_tasks = [_get_latest_version(pkg) for pkg in to_query]
        version_results = await asyncio.gather(*version_tasks, return_exceptions=True)

        for result in version_results:
            if isinstance(result, Exception):
                continue
            if result:
                dep_versions.append(result)

    return {
        "releases": releases,
        "release_count_12m": release_count_12m,
        "dependencies": dependencies,
        "dependency_versions": dep_versions,
        "breaking_change": breaking,
    }
