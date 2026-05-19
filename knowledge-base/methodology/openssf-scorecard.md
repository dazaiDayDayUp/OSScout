# OpenSSF Scorecard 评估标准

## 概述

OpenSSF Scorecard 是由 Open Source Security Foundation 维护的开源项目安全评分工具。它通过自动化检查 GitHub 仓库的多个安全维度，为项目打出 0-10 分的安全评分。

Scorecard 的设计理念是：安全不应该是"有或没有"的二元判断，而是一系列可测量、可改进的实践集合。

## 检查项与权重

### 1. 代码审查（Code-Review）— 权重最高

- **评分逻辑**：最近 30 个 commit 中，有多少比例经过了除作者外的至少一人审查
- **满分标准**：≥80% 的 commit 经过 PR 审查
- **风险阈值**：
  - 10 分：≥80% 审查
  - 5-9 分：50-80% 审查
  - 0-4 分：<50% 审查

### 2. 依赖更新（Dependency-Update-Tool）

- **检查内容**：是否使用 Dependabot、Renovate 等工具自动更新依赖
- **满分标准**：已配置自动依赖更新
- **风险**：手动更新依赖容易遗漏安全补丁

### 3. 安全策略（Security-Policy）

- **检查内容**：仓库根目录是否有 SECURITY.md
- **满分标准**：存在 SECURITY.md，包含漏洞报告流程
- **意义**：表明项目有成熟的安全响应流程

### 4. 签名提交（Signed-Releases）

- **检查内容**：release 是否使用 GPG/Sigstore 签名
- **满分标准**：最近 5 个 release 全部签名
- **意义**：防止发布流程被攻击者劫持后分发恶意代码

### 5. 分支保护（Branch-Protection）

- **检查内容**：主分支是否启用强制 PR 审查、状态检查等保护
- **满分标准**：启用所有保护规则

### 6. 模糊测试（Fuzzing）

- **检查内容**：是否集成 OSS-Fuzz 或其他模糊测试工具
- **满分标准**：已配置模糊测试

### 7. SAST（静态应用安全测试）

- **检查内容**：是否使用 CodeQL、Semgrep 等静态分析工具
- **满分标准**：CI 中集成 SAST 工具

### 8. 令牌权限（Token-Permissions）

- **检查内容**：GitHub Actions 工作流是否遵循最小权限原则
- **满分标准**：所有工作流显式声明权限范围

## 与 OSScout 的映射

| Scorecard 检查项 | OSScout 维度 | 权重参考 |
|-----------------|-------------|---------|
| Code-Review | 社区健康 + 代码质量 | 高 |
| Dependency-Update-Tool | 安全 + 技术演进 | 中 |
| Security-Policy | 安全 | 中 |
| Signed-Releases | 安全 | 低 |
| Branch-Protection | 社区健康 | 中 |
| Fuzzing | 安全 | 低 |
| SAST | 代码质量 + 安全 | 中 |
| Token-Permissions | 安全 | 低 |

## 局限性

- 仅检查 GitHub 仓库的元数据，无法分析代码本身的质量
- 无法评估社区治理的健康度（如 Bus Factor、贡献者多样性）
- 无法判断项目的长期可持续性（如维护者倦怠、资金状况）
- 所有检查项权重相等，但实际上 Code-Review 比 Token-Permissions 更关键

## 引用

- 官方文档: https://github.com/ossf/scorecard
- 评分标准: https://github.com/ossf/scorecard/blob/main/docs/checks.md
