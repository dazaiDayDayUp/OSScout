#!/usr/bin/env python3
"""
行业基准数据采集脚本

从 OpenSSF Scorecard API 批量查询热门项目的安全评分数据，
按项目类型聚合后存入 benchmark_data 表。

使用方法:
    cd scripts && python collect_benchmarks.py

API 限制: 约 10 req/min，脚本会自动处理速率限制
"""

import asyncio
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import requests

# 添加 backend 到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "backend"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.core.models import BenchmarkData

# =============================================================================
# 项目样本池 —— 按类型分类的代表性开源项目
# =============================================================================

PROJECT_SAMPLES = {
    "frontend-framework": [
        ("facebook", "react"),
        ("vuejs", "core"),
        ("sveltejs", "svelte"),
        ("angular", "angular"),
        ("preactjs", "preact"),
        ("solidjs", "solid"),
    ],
    "backend-framework": [
        ("expressjs", "express"),
        ("tiangolo", "fastapi"),
        ("django", "django"),
        ("pallets", "flask"),
        ("nestjs", "nest"),
        ("gin-gonic", "gin"),
        ("spring-projects", "spring-boot"),
        ("gofiber", "fiber"),
    ],
    "cli-tool": [
        ("vitejs", "vite"),
        ("webpack", "webpack"),
        ("rollup", "rollup"),
        ("evanw", "esbuild"),
        ("vercel", "turbo"),
    ],
    "state-management": [
        ("reduxjs", "redux"),
        ("pmndrs", "zustand"),
        ("vuejs", "pinia"),
        ("mobxjs", "mobx"),
    ],
    "testing-framework": [
        ("jestjs", "jest"),
        ("vitest-dev", "vitest"),
        ("microsoft", "playwright"),
        ("cypress-io", "cypress"),
    ],
    "ai-ml-library": [
        ("pytorch", "pytorch"),
        ("huggingface", "transformers"),
        ("langchain-ai", "langchain"),
        ("scikit-learn", "scikit-learn"),
    ],
    "security-library": [
        ("openssl", "openssl"),
        ("bcrypt", "bcrypt"),
        ("hashicorp", "vault"),
        ("OWASP", "ModSecurity"),
    ],
    "database-driver": [
        ("prisma", "prisma"),
        ("typeorm", "typeorm"),
        ("sqlalchemy", "sqlalchemy"),
        ("Automattic", "mongoose"),
    ],
    "package-manager": [
        ("npm", "cli"),
        ("yarnpkg", "yarn"),
        ("pnpm", "pnpm"),
        ("python-poetry", "poetry"),
    ],
    "utility-library": [
        ("lodash", "lodash"),
        ("axios", "axios"),
        ("moment", "moment"),
        ("date-fns", "date-fns"),
    ],
}

# Scorecard 检查项到统一指标名的映射
# 原始 check name -> 我们的 metric_name
CHECK_NAME_MAPPING = {
    "Code-Review": "code_review_score",
    "Dependency-Update-Tool": "dependency_update_score",
    "Security-Policy": "security_policy_score",
    "Signed-Releases": "signed_releases_score",
    "Branch-Protection": "branch_protection_score",
    "Fuzzing": "fuzzing_score",
    "SAST": "sast_score",
    "Token-Permissions": "token_permissions_score",
    "Binary-Artifacts": "binary_artifacts_score",
    "CI-Tests": "ci_tests_score",
    "CII-Best-Practices": "cii_best_practices_score",
    "Dangerous-Workflow": "dangerous_workflow_score",
    "License": "license_score",
    "Maintained": "maintained_score",
    "Packaging": "packaging_score",
    "Pinned-Dependencies": "pinned_dependencies_score",
    "SBOM": "sbom_score",
    "Vulnerabilities": "vulnerabilities_score",
    "Webhooks": "webhooks_score",
    "Contributors": "contributors_score",
}


def fetch_scorecard(owner: str, repo: str, max_retries: int = 3) -> dict | None:
    """
    查询单个项目的 OpenSSF Scorecard 数据

    Score 为 -1 表示"不适用"或"无法检测"，这类数据不参与聚合。
    """
    url = f"https://api.securityscorecards.dev/projects/github.com/{owner}/{repo}"

    for attempt in range(max_retries):
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                # 速率限制，等待后重试
                wait_time = 10 + attempt * 5
                print(f"    Rate limited, waiting {wait_time}s...")
                time.sleep(wait_time)
            else:
                print(f"    HTTP {resp.status_code} for {owner}/{repo}")
                return None
        except Exception as e:
            print(f"    Error fetching {owner}/{repo}: {e}")
            if attempt < max_retries - 1:
                time.sleep(5)

    return None


def aggregate_scores(all_results: list[dict]) -> dict[str, dict]:
    """
    按项目类型聚合 Scorecard 分数

    对每个指标，计算：平均值、中位数、25分位、75分位
    过滤掉 score 为 -1（无效）的数据点
    """
    # 按 project_type 分组收集所有分数
    type_scores = defaultdict(lambda: defaultdict(list))
    type_projects = defaultdict(list)

    for result in all_results:
        project_type = result["project_type"]
        project_key = result["owner"] + "/" + result["repo"]
        type_projects[project_type].append(project_key)

        for check in result.get("checks", []):
            raw_name = check["name"]
            score = check.get("score")
            # 跳过无效分数
            if score is None or score < 0:
                continue
            metric_name = CHECK_NAME_MAPPING.get(raw_name, raw_name.lower().replace("-", "_"))
            type_scores[project_type][metric_name].append(score)

    # 计算统计量
    import statistics

    aggregated = {}
    for project_type, metrics in type_scores.items():
        aggregated[project_type] = {}
        for metric_name, scores in metrics.items():
            if len(scores) < 2:
                continue
            scores_sorted = sorted(scores)
            n = len(scores)
            aggregated[project_type][metric_name] = {
                "avg": round(statistics.mean(scores), 2),
                "median": round(statistics.median(scores), 2),
                "p25": round(scores_sorted[n // 4], 2),
                "p75": round(scores_sorted[(3 * n) // 4], 2),
                "count": n,
            }

    return aggregated, type_projects


async def save_to_database(aggregated: dict, type_projects: dict) -> int:
    """将聚合结果写入 benchmark_data 表"""
    engine = create_async_engine(settings.database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    count = 0
    async with async_session() as session:
        # 先清空旧数据（同版本的）
        data_version = datetime.now().strftime("%Y-%m")
        # 检查是否已有数据
        result = await session.execute(
            select(BenchmarkData).where(BenchmarkData.data_version == data_version)
        )
        existing = result.scalars().all()
        if existing:
            print(f"\n  发现 {len(existing)} 条 {data_version} 版本数据，将覆盖...")
            for row in existing:
                await session.delete(row)
            await session.commit()

        # 插入新数据
        for project_type, metrics in aggregated.items():
            for metric_name, stats in metrics.items():
                # 构造描述文字，供 LLM 直接引用
                description = (
                    f"在 {len(type_projects.get(project_type, []))} 个样本项目中，"
                    f"{metric_name} 的平均值为 {stats['avg']} 分（满分 10 分），"
                    f"中位数为 {stats['median']} 分，"
                    f"75% 的项目不低于 {stats['p25']} 分，"
                    f"25% 的项目达到 {stats['p75']} 分以上。"
                )

                benchmark = BenchmarkData(
                    project_type=project_type,
                    metric_name=metric_name,
                    metric_source="openssf_scorecard",
                    avg_value=stats["avg"],
                    median_value=stats["median"],
                    p25_value=stats["p25"],
                    p75_value=stats["p75"],
                    sample_count=stats["count"],
                    sample_projects=type_projects.get(project_type, [])[:20],
                    data_version=data_version,
                    description=description,
                )
                session.add(benchmark)
                count += 1

        await session.commit()

    await engine.dispose()
    return count


async def main():
    print("=" * 60)
    print("行业基准数据采集")
    print("=" * 60)

    total_projects = sum(len(v) for v in PROJECT_SAMPLES.values())
    print(f"样本项目总数: {total_projects}")
    print(f"项目类型数: {len(PROJECT_SAMPLES)}")
    print()

    # 采集所有项目的 Scorecard 数据
    all_results = []
    success_count = 0
    fail_count = 0

    for project_type, projects in PROJECT_SAMPLES.items():
        print(f"[{project_type}] ({len(projects)} projects)")
        for owner, repo in projects:
            print(f"  Querying {owner}/{repo}...", end=" ")
            data = fetch_scorecard(owner, repo)
            if data:
                all_results.append({
                    "project_type": project_type,
                    "owner": owner,
                    "repo": repo,
                    "score": data.get("score"),
                    "checks": data.get("checks", []),
                })
                success_count += 1
                print(f"OK (score: {data.get('score', 'N/A')})")
            else:
                fail_count += 1
                print("FAILED")

            # 速率限制保护：每个请求间隔 7 秒（约 8-9 req/min）
            time.sleep(7)
        print()

    print("=" * 60)
    print(f"采集完成: {success_count} 成功, {fail_count} 失败")
    print("=" * 60)

    if not all_results:
        print("没有采集到任何数据，退出")
        return

    # 聚合统计
    print("\n正在聚合统计...")
    aggregated, type_projects = aggregate_scores(all_results)

    # 打印汇总
    print("\n聚合结果预览:")
    for project_type, metrics in aggregated.items():
        print(f"\n  [{project_type}] — {len(type_projects.get(project_type, []))} 个项目")
        for metric_name, stats in list(metrics.items())[:3]:
            print(f"    {metric_name}: avg={stats['avg']}, median={stats['median']}")
        if len(metrics) > 3:
            print(f"    ... 共 {len(metrics)} 个指标")

    # 写入数据库
    print("\n正在写入数据库...")
    saved_count = await save_to_database(aggregated, type_projects)
    print(f"已写入 {saved_count} 条基准数据")

    print("\n完成!")


if __name__ == "__main__":
    asyncio.run(main())
