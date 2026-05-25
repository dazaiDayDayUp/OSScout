# 项目开发进度记录

> 当前进度速查，完整规划见 `PROJECT_PLAN.md`。

---

## 当前状态

**Phase 0~4 全部完成。当前重点：Phase 5（真正的 Agent 架构重构）。**

最近更新：2026-05-25

---

## 已完成阶段速查

| 阶段 | 核心成果 | 状态 |
|------|---------|------|
| Phase 0 | FastAPI + PostgreSQL + Redis + Docker 基础设施 | ✅ |
| Phase 1 | 4 个分析 Agent + Orchestrator 并发调度 + CLI 文本报告 | ✅ |
| Phase 2 | REST API + Celery 异步任务 + React 前端可视化 | ✅ |
| Phase 3 | LLM 推理增强 + ChromaDB RAG 初版 + Synthesis 综合报告 | ✅ |
| Phase 4 | 生产级 RAG：167 篇知识库 / 语义分块 / 混合检索(BM25+RRF) / CrossEncoder 重排序 / Self-RAG 自验证 / Web 搜索 fallback / 引用追踪 | ✅ |

---

## 当前重点

### Phase 5：真正的 Agent 架构重构

| 子任务 | 内容 | 状态 |
|--------|------|------|
| 5.1 | LLM Function Calling 基础设施：统一 Tool 定义协议 + 执行器 | ⏳ |
| 5.2 | MCP 工具注册表：自动提取工具描述，生成 Tool Schema | ⏳ |
| 5.3 | RAG 工具化：将 RAG 检索封装为 LLM 可调用的 Tool | ⏳ |
| 5.4 | Plan-and-Execute Agent：LLM 自主规划分析路径 | ⏳ |
| 5.5 | ReAct Loop 升级：LLM 自主决定 Thought → Action → Observation | ⏳ |
| 5.6 | 动态分析流程：移除硬编码 4 个 Agent，LLM 按需调用工具 | ⏳ |
| 5.7 | 推理与反思（Reflection）：LLM 自我检查、发现遗漏、补充验证 | ⏳ |
| 5.8 | 前端适配：展示 Agent 思维链、工具调用轨迹、反思记录 | ⏳ |

---

## 已知问题

| 优先级 | 问题 | 说明 | 状态 |
|--------|------|------|------|
| **高** | **RAG 检索内容未进入 LLM 上下文** | `_calibrate_dimension` 只把文档标题传给 Synthesis Agent，`content` 完全没被使用；4 个 Agent 的 LLM 增强 Prompt 也没有 RAG 内容。RAG 只是"检索了→存了→展示了标题"，没有真正参与推理 | **Phase 5.3 解决** |
| 中 | Kimi 并发限制（429） | 免费账户并发上限 3，Synthesis 可能触发 429 重试，延迟 10-60 秒 | 自动重试，最终成功 |
| 中 | 分析耗时约 2 分钟 | GitHub API + 4 Agent + RAG + Synthesis 完整链路 | Phase 5 的自主规划可能优化并行度 |
| 中 | 超大仓库分析慢 | monorepo 依赖查询串行 | Phase 5 Agent 可自主跳过非关键步骤 |
| 低 | Windows 控制台 GBK 乱码 | 仅显示问题，不影响文件/API | 低优先级 |
| **解决** | ~~RAG 仅 9 篇文档~~ | ~~数据量太少，检索质量受限~~ | **4.1 完成：已扩充至 167 篇** |
| 低 | 硬编码 4 个 Agent 流程 | LLM 没有自主决策权，只是"高级填空" | **Phase 5 解决** |

## 最近完成（2026-05-25）

| 事项 | 说明 |
|------|------|
| Phase 4.7 引用追踪 | 统一 Citation 模型，覆盖 KB / Web / Benchmark 三类来源；前端按来源类型分组展示；修复 analysis_tasks raw_results 漏存 Bug |

## 最近修复（2026-05-20）

| 问题 | 根因 | 修复方案 |
|------|------|---------|
| MCP Client `bound to a different event loop` | 单例 asyncio.Lock 跨事件循环复用 | 禁用单例，每个 `async with` 创建全新实例 |
| Kimi temperature=1.0 被 API 400 拒绝 | API 端 temperature 限制从 1.0 变为 0.6 | 修正为 0.6 |
| Synthesis 两步 JSON 转换失败 | kimi-k2.6 思考模型返回思考过程而非 JSON | 一步直接生成 JSON + 禁用思考 + 自动归一化 |
| `additional_risks` Schema 校验失败 | 模型返回字符串而非列表 | `base.py` 增加 `_normalize_parsed_data` 自动修复 |

---

## 后续优化（暂不进入主线）

- 持续监控 + 预警（Celery Beat 定时巡检、异常检测）
- 用户关注列表（watch list）
- 邮件/Webhook 通知
- 公开报告页面（可分享链接）
- 部署上线（Railway/Render）

---

## 下一步

**Phase 5.1：LLM Function Calling 基础设施**

- 统一 Tool 定义协议：{name, description, parameters(schema), handler}
- Tool Schema 自动生成：从函数签名 + docstring 自动生成 JSON Schema
- Tool 执行器：解析 LLM 返回的 tool_calls → 执行对应函数 → 返回 observation
- 支持 OpenAI 格式 function calling（Kimi / DeepSeek 均兼容）
