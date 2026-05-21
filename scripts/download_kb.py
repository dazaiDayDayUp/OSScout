#!/usr/bin/env python3
"""
权威知识库文档批量下载脚本

从以下来源自动拉取原始文档：
- CHAOSS 指标定义（Linux Foundation）
- OpenSSF Scorecard 检查项文档
- 知名开源项目治理文档（GOVERNANCE.md）
- CNCF / Apache 基金会相关文档

使用方法:
    cd scripts && python download_kb.py
"""

import os
import re
import requests
from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
KB_DIR = PROJECT_ROOT / "knowledge-base"

# 请求配置
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "OSScout-KB-Downloader/1.0 (osscout project)"
})

def ensure_dir(path: Path) -> None:
    """确保目录存在"""
    path.mkdir(parents=True, exist_ok=True)

def add_frontmatter(content: str, title: str, source_url: str, category: str) -> str:
    """
    给文档添加 YAML frontmatter 元数据

    包含：标题、来源 URL、类别、下载日期
    这样后续分块和检索时知道每段内容的出处
    """
    frontmatter = f"""---
title: {title}
source: {source_url}
category: {category}
downloaded_at: {datetime.now().strftime("%Y-%m-%d")}
---

"""
    return frontmatter + content

def download_file(url: str, timeout: int = 15) -> str | None:
    """下载文件内容，失败返回 None"""
    try:
        resp = SESSION.get(url, timeout=timeout)
        if resp.status_code == 200:
            return resp.text
        else:
            print(f"  [WARN] HTTP {resp.status_code}: {url}")
            return None
    except Exception as e:
        print(f"  [ERR] {e}: {url}")
        return None

def slugify(name: str) -> str:
    """把指标名转成文件名安全的格式"""
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s-]+", "-", s)
    return s[:80]

# =============================================================================
# 1. OpenSSF Scorecard 检查项（20 篇）
# =============================================================================
def download_openssf_checks() -> int:
    """
    下载 OpenSSF Scorecard 检查项文档

    来源: https://github.com/ossf/scorecard/blob/main/docs/checks.md
    这个文件包含 20 个检查项，按 ## 标题拆分为独立文档
    """
    print("=" * 60)
    print("[1/4] 下载 OpenSSF Scorecard 检查项文档")
    print("=" * 60)

    url = "https://raw.githubusercontent.com/ossf/scorecard/main/docs/checks.md"
    content = download_file(url)
    if not content:
        print("  [FAIL] 无法下载 checks.md")
        return 0

    out_dir = KB_DIR / "methodology" / "openssf-checks"
    ensure_dir(out_dir)

    # 拆分文档：找到 ## 开头的检查项章节
    # 每个检查项格式: ## Check-Name
    pattern = r"^## ([A-Za-z-]+)\s*\n"
    sections = list(re.finditer(pattern, content, re.MULTILINE))

    count = 0
    for i, match in enumerate(sections):
        check_name = match.group(1)
        start = match.start()
        end = sections[i + 1].start() if i + 1 < len(sections) else len(content)
        section_content = content[start:end].strip()

        # 添加 frontmatter
        doc = add_frontmatter(
            section_content,
            f"OpenSSF Scorecard: {check_name}",
            f"https://github.com/ossf/scorecard/blob/main/docs/checks.md#{check_name.lower()}",
            "methodology/openssf-checks"
        )

        filename = slugify(check_name) + ".md"
        filepath = out_dir / filename
        filepath.write_text(doc, encoding="utf-8")
        count += 1
        print(f"  [{count:2d}] {check_name} -> {filepath.name}")

    print(f"  总计: {count} 篇")
    return count

# =============================================================================
# 2. CHAOSS 指标定义（多个 Working Group）
# =============================================================================

def download_chaoss_metrics() -> int:
    """
    下载 CHAOSS (Community Health Analytics Open Source Software) 指标定义文档

    CHAOSS 是 Linux Foundation 下属项目，定义了开源社区健康度的标准指标。
    指标分散在多个 working group 仓库中。
    """
    print()
    print("=" * 60)
    print("[2/4] 下载 CHAOSS 指标定义文档")
    print("=" * 60)

    # 定义要抓取的 working group 和 focus areas
    # 格式: (working_group_name, focus_area, area_display_name)
    wg_areas = [
        # wg-common: 通用社区指标
        ("wg-common", "contributions", "Contributions"),
        ("wg-common", "people", "People"),
        ("wg-common", "time", "Time"),
        # wg-risk: 风险评估指标
        ("wg-risk", "business-risk", "Business Risk"),
        ("wg-risk", "code-quality", "Code Quality"),
        ("wg-risk", "dependency-risk-assessment", "Dependency Risk"),
        ("wg-risk", "licensing", "Licensing"),
        ("wg-risk", "security", "Security"),
        # wg-evolution: 项目演进指标
        ("wg-evolution", "code-development-activity", "Code Development Activity"),
        ("wg-evolution", "issue-resolution", "Issue Resolution"),
        ("wg-evolution", "community-growth", "Community Growth"),
        # wg-value: 项目价值指标
        ("wg-value", "academic-value", "Academic Value"),
        ("wg-value", "communal-value", "Communal Value"),
        ("wg-value", "individual-value", "Individual Value"),
        ("wg-value", "organizational-value", "Organizational Value"),
        # wg-diversity-inclusion: 多样性与包容性
        ("wg-dei", "event-diversity", "Event Diversity"),
        ("wg-dei", "governance", "Governance"),
        ("wg-dei", "leadership", "Leadership"),
        ("wg-dei", "project-and-community", "Project and Community"),
    ]

    out_dir = KB_DIR / "methodology" / "chaoss-metrics"
    ensure_dir(out_dir)

    total_count = 0
    seen_names = set()  # 去重

    for wg, area, area_name in wg_areas:
        print(f"\n  [{wg}] {area_name}:")

        # 先获取 focus area 的 README，里面列出了所有指标文件
        readme_url = f"https://raw.githubusercontent.com/chaoss/{wg}/main/focus-areas/{area}/README.md"
        readme = download_file(readme_url)
        if not readme:
            continue

        # 从 README 中提取指标文件名
        # 格式: [Metric Name](metric-file-name.md)
        metrics = re.findall(r"\[([^\]]+)\]\(([^)]+\.md)\)", readme)

        for metric_name, metric_path in metrics:
            # 去重：同名指标只保留一份
            if metric_name in seen_names:
                print(f"    [SKIP] {metric_name} (duplicate)")
                continue
            seen_names.add(metric_name)

            # 构造指标文件的完整 URL
            # metric_path 可能是相对路径如 "technical-fork.md" 或 "../some-file.md"
            base_url = f"https://raw.githubusercontent.com/chaoss/{wg}/main/focus-areas/{area}/"
            metric_url = urljoin(base_url, metric_path)

            metric_content = download_file(metric_url)
            if not metric_content:
                continue

            # 添加 frontmatter
            doc = add_frontmatter(
                metric_content,
                f"CHAOSS: {metric_name}",
                metric_url,
                f"methodology/chaoss-metrics/{area}"
            )

            filename = slugify(metric_name) + ".md"
            filepath = out_dir / filename
            filepath.write_text(doc, encoding="utf-8")
            total_count += 1
            print(f"    [{total_count:2d}] {metric_name}")

    print(f"\n  CHAOSS 总计: {total_count} 篇")
    return total_count

# =============================================================================
# 3. 开源项目治理文档
# =============================================================================

def download_governance_docs() -> int:
    """
    下载知名开源项目的治理文档

    治理模式直接影响项目的长期健康度。
    这些文档来自项目自身的仓库，是官方权威来源。
    """
    print()
    print("=" * 60)
    print("[3/4] 下载开源项目治理文档")
    print("=" * 60)

    # 定义要下载的治理文档
    # 格式: (项目名, 文件名显示名称, raw URL, 类别标签)
    governance_files = [
        # Python 生态
        ("python", "Python Governance (PEP 8016)",
         "https://raw.githubusercontent.com/python/peps/main/peps/pep-8016.rst",
         "governance/python"),
        ("python", "Python Steering Council",
         "https://raw.githubusercontent.com/python/steering-council/main/README.md",
         "governance/python"),
        # Node.js
        ("nodejs", "Node.js GOVERNANCE",
         "https://raw.githubusercontent.com/nodejs/node/main/GOVERNANCE.md",
         "governance/nodejs"),
        ("nodejs", "Node.js TSC Charter",
         "https://raw.githubusercontent.com/nodejs/TSC/main/TSC-Charter.md",
         "governance/nodejs"),
        # Kubernetes
        ("kubernetes", "Kubernetes Governance",
         "https://raw.githubusercontent.com/kubernetes/community/master/governance.md",
         "governance/kubernetes"),
        ("kubernetes", "Kubernetes Community Membership",
         "https://raw.githubusercontent.com/kubernetes/community/master/community-membership.md",
         "governance/kubernetes"),
        # Rust
        ("rust", "Rust RFC Process",
         "https://raw.githubusercontent.com/rust-lang/rfcs/master/README.md",
         "governance/rust"),
        ("rust", "Rust Governance",
         "https://raw.githubusercontent.com/rust-lang/rust-forge/master/src/governance/index.md",
         "governance/rust"),
        # Django
        ("django", "Django Governance",
         "https://raw.githubusercontent.com/django/deps/main/final/0010-governance.rst",
         "governance/django"),
        # Apache 基金会
        ("apache", "Apache Foundation Governance",
         "https://raw.githubusercontent.com/apache/comdev-site/main/source/_pages/how-the-apache-way-works.md",
         "governance/apache"),
        # Debian
        ("debian", "Debian Constitution",
         "https://salsa.debian.org/debian/constitution/-/raw/master/constitution.md",
         "governance/debian"),
        # CNCF
        ("cncf", "CNCF Graduation Criteria",
         "https://raw.githubusercontent.com/cncf/toc/main/process/graduation_criteria.adoc",
         "governance/cncf"),
        ("cncf", "CNCF Project Lifecycle",
         "https://raw.githubusercontent.com/cncf/toc/main/process/project-lifecycle.md",
         "governance/cncf"),
        # Linux Kernel
        ("linux", "Linux Kernel Code of Conduct",
         "https://raw.githubusercontent.com/torvalds/linux/master/CodeOfConduct.rst",
         "governance/linux"),
        ("linux", "Linux Kernel Maintainer Entry Profile",
         "https://raw.githubusercontent.com/torvalds/linux/master/Documentation/process/maintainer-entry-profile.rst",
         "governance/linux"),
        # React
        ("react", "React Governance",
         "https://raw.githubusercontent.com/reactjs/react.dev/main/CONTRIBUTING.md",
         "governance/react"),
        # Vue.js
        ("vuejs", "Vue.js Governance",
         "https://raw.githubusercontent.com/vuejs/governance/main/README.md",
         "governance/vuejs"),
    ]

    out_dir = KB_DIR / "governance"
    ensure_dir(out_dir)

    count = 0
    for project, display_name, url, category in governance_files:
        content = download_file(url)
        if not content:
            continue

        doc = add_frontmatter(
            content,
            display_name,
            url,
            category
        )

        filename = slugify(display_name) + ".md"
        filepath = out_dir / filename
        filepath.write_text(doc, encoding="utf-8")
        count += 1
        print(f"  [{count:2d}] {display_name} ({project})")

    print(f"  总计: {count} 篇")
    return count

# =============================================================================
# 4. 权威安全案例与最佳实践
# =============================================================================

def download_security_docs() -> int:
    """
    下载安全相关的权威文档

    来源: OpenSSF Best Practices Badge、Snyk、GitHub Security Lab
    """
    print()
    print("=" * 60)
    print("[4/4] 下载安全相关权威文档")
    print("=" * 60)

    # 这些文档来自权威安全机构的公开资料
    security_docs = [
        ("OpenSSF Best Practices Badge - 快速通过指南",
         "https://raw.githubusercontent.com/coreinfrastructure/best-practices-badge/main/doc/criteria.md",
         "security/best-practices"),
        ("OpenSSF Best Practices - 安全标准",
         "https://raw.githubusercontent.com/coreinfrastructure/best-practices-badge/main/doc/security.md",
         "security/best-practices"),
        ("OpenSSF Security Guides - 安全开发基础",
         "https://raw.githubusercontent.com/ossf/education/main/openssf-security-guides/guide1.md",
         "security/guides"),
    ]

    out_dir = KB_DIR / "security"
    ensure_dir(out_dir)

    count = 0
    for display_name, url, category in security_docs:
        content = download_file(url)
        if not content:
            continue

        doc = add_frontmatter(
            content,
            display_name,
            url,
            category
        )

        filename = slugify(display_name) + ".md"
        filepath = out_dir / filename
        filepath.write_text(doc, encoding="utf-8")
        count += 1
        print(f"  [{count:2d}] {display_name}")

    print(f"  总计: {count} 篇")
    return count

# =============================================================================
# 主函数
# =============================================================================

def main():
    print("=" * 60)
    print("OSScout 知识库权威文档批量下载")
    print(f"输出目录: {KB_DIR}")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 确保 knowledge-base 目录存在
    ensure_dir(KB_DIR)

    # 执行下载
    total = 0
    total += download_openssf_checks()
    total += download_chaoss_metrics()
    total += download_governance_docs()
    total += download_security_docs()

    print()
    print("=" * 60)
    print("下载完成!")
    print(f"总计下载: {total} 篇文档")
    print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 输出目录结构摘要
    print("\n知识库目录结构:")
    for subdir in sorted(KB_DIR.rglob("*.md")):
        rel = subdir.relative_to(KB_DIR)
        print(f"  {rel}")

if __name__ == "__main__":
    main()
