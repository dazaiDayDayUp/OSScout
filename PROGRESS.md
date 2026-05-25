# 项目开发进度记录

> 当前进度速查，完整规划见 `PROJECT_PLAN.md`。

---

## 当前状态

**Phase 0~3 全部完成。当前重点：Phase 4（RAG 深度优化）+ Phase 5（真正的 Agent 架构重构）。**

最近更新：2026-05-25

---

## 已完成阶段速查

| 阶段 | 核心成果 | 状态 |
|------|---------|------|
| Phase 0 | FastAPI + PostgreSQL + Redis + Docker 基础设施 | ✅ |
| Phase 1 | 4 个分析 Agent + Orchestrator 并发调度 + CLI 文本报告 | ✅ |
| Phase 2 | REST API + Celery 异步任务 + React 前端可视化 | ✅ |
| Phase 3 | LLM 推理增强 + ChromaDB RAG 初版 + Synthesis 综合报告 | ✅ |

---

## 当前重点

### Phase 4：RAG 深度优化

| 子任务 | 内容 | 状态 |
|--------|------|------|
| 4.1 | 知识库扩充：CHAOSS 指标(80) + OpenSSF 检查项(20) + OWASP 安全(48) + 治理(10) + 案例(4) + 竞品(3) = **167 篇** | ✅ |
| 4.2 | 行业基准数据：OpenSSF Scorecard API 采集 41 个项目，聚合 117 条基准，封装 `get_benchmark` Tool | ✅ |
| 4.3 | 文档分块策略：语义分块 + 重叠窗口 + 元数据保留 | ✅ |
| 4.4 | 混合检索：向量检索 + BM25 关键词检索融合 | ✅ |
| 4.5 | 重排序（Rerank）：交叉编码器精排 | ✅ |
| 4.6 | Self-RAG：检索结果自验证 + fallback Web 搜索 | ✅ |
| 4.7 | 引用追踪：每条结论标注来源文档 ID + 具体段落 | ⏳ |

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
| 中 | Kimi 并发限制（429） | 免费账户并发上限 3，Synthesis 可能触发 429 重试，延迟 10-60 秒 | 自动重试，最终成功 |
| 中 | 分析耗时约 2 分钟 | GitHub API + 4 Agent + RAG + Synthesis 完整链路 | Phase 5 的自主规划可能优化并行度 |
| 中 | 超大仓库分析慢 | monorepo 依赖查询串行 | Phase 5 Agent 可自主跳过非关键步骤 |
| 低 | Windows 控制台 GBK 乱码 | 仅显示问题，不影响文件/API | 低优先级 |
| **解决** | ~~RAG 仅 9 篇文档~~ | ~~数据量太少，检索质量受限~~ | **4.1 完成：已扩充至 167 篇** |
| 低 | 硬编码 4 个 Agent 流程 | LLM 没有自主决策权，只是"高级填空" | **Phase 5 解决** |

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

**Phase 4.7：引用追踪**

- 检索结果与 Agent 结论绑定：每条结论标注引用的文档 ID + chunk ID
- RAGQueryEngine 返回结果中增加 `citations` 字段
- 前端报告详情页展示引用来源（"此结论引用自 CHAOSS-Bus-Factor 定义第 3 段"）
- 引用去重：同一文档被多次引用时合并展示
