"""
CLI 入口

提供命令行方式运行尽调分析，输出文本报告。

使用方式：
    cd backend
    python -m app.cli analyze https://github.com/python-poetry/poetry

或者在 Docker 中：
    docker-compose -f docker-compose.dev.yml exec api python -m app.cli analyze https://github.com/python-poetry/poetry
"""

import argparse
import asyncio
import sys

from app.agents.orchestrator import Orchestrator
from app.agents.reporter import Reporter


def main():
    """CLI 主入口，解析参数并分发到对应子命令"""
    parser = argparse.ArgumentParser(
        prog="osscout",
        description="开源项目深度尽调 Agent 平台 CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # analyze 子命令
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="分析指定 GitHub 仓库",
    )
    analyze_parser.add_argument(
        "repo_url",
        help="GitHub 仓库地址，例如 https://github.com/python-poetry/poetry",
    )

    args = parser.parse_args()

    if args.command == "analyze":
        asyncio.run(_run_analyze(args.repo_url))
    else:
        parser.print_help()
        sys.exit(1)


async def _run_analyze(repo_url: str):
    """
    执行分析命令的异步流程

    1. 初始化 Orchestrator 和 Reporter
    2. 调用 Orchestrator.analyze() 获取结构化结果
    3. 用 Reporter 格式化为文本
    4. 输出到控制台
    """
    print(f"开始分析仓库: {repo_url}")
    print()

    orchestrator = Orchestrator()
    reporter = Reporter()

    result = await orchestrator.analyze(repo_url)
    report = reporter.format_text(result)

    print(report)


if __name__ == "__main__":
    main()
