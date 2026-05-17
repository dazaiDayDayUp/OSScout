"""
公共工具函数

存放项目通用的工具函数，供各模块复用。
"""

from urllib.parse import urlparse


def parse_repo_url(repo_url: str) -> tuple[str, str]:
    """
    从 GitHub 仓库地址中解析 owner 和 repo 名称

    支持的格式：
        - https://github.com/owner/repo
        - https://github.com/owner/repo.git
        - github.com/owner/repo

    Raises:
        ValueError: URL 格式不合法
    """
    url = repo_url.strip().removesuffix(".git")

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split("/") if p]

    if len(path_parts) < 2:
        raise ValueError(
            f"无效的 GitHub 仓库地址：{repo_url}\n"
            "期望格式：https://github.com/owner/repo"
        )

    return path_parts[0], path_parts[1]
