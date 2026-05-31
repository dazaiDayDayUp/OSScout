# 项目开发进度记录

> 活文档，只保留当前状态和下一步。详细规划见 [`PROJECT_PLAN.md`](./PROJECT_PLAN.md)，Phase 5 技术方案见 [`PHASE5_PLAN.md`](./PHASE5_PLAN.md)。

---

## 当前状态

**Phase 0~4 全部完成，Phase 5.1~5.5 已完成。当前重点：Phase 5.6（动态分析流程）。**

最近更新：2026-05-31

---

## Phase 5 进度

| 子阶段 | 内容 | 状态 |
|--------|------|------|
| 5.1 | Function Calling 基础设施 | ✅ 已完成 |
| 5.2 | MCP 工具注册表 | ✅ 已完成 |
| 5.3 | RAG 工具化 | ✅ 已完成 |
| 5.4 | Plan-and-Execute 编排引擎 | ✅ 已完成 |
| **5.5** | **ReAct Loop 升级** | **✅ 已完成** |
| 5.6 | 动态分析流程（Master + Specialist） | ⏳ 当前重点 |
| 5.7 | Reflection + Message Bus | ⏳ 待开始 |
| 5.8 | 前端适配 | ⏳ 待开始 |

历史成果详见 [`PHASE5_PLAN.md` 第 6 章](../PHASE5_PLAN.md)。

---

## 2026-05-31 完成内容

### Phase 5.5 ReAct Loop 升级（已完成）

**修改文件**：
- `backend/app/agents/orchestration/execute_engine.py` — 新增 ReAct 决策点（`_react_decision_point`、`_execute_react_tools`、`_build_react_prompt`）

**新增文件**：
- `backend/scripts/verify_phase55.py` — Mock 端到端验证（6/6 通过）
- `backend/scripts/verify_phase55_real_llm.py` — 真实 LLM 验证（3 次跑通）

**验证结果**：
- Mock 测试：6/6 通过
- 5.4 回归测试：6/6 通过
- 真实 LLM 验证：Kimi + DeepSeek 各多次运行，TERMINATE/CONTINUE/tool_calls 均验证成功

---

## 待解决问题

### 高优先级（影响功能）

1. **ReAct Prompt 不够 robust**
   - 问题：LLM 识别数据不足时，有时选择 TERMINATE + 文本说明，而非 tool_calls 补充
   - 表现：Test 2（不完整 Plan）中 DeepSeek 明确说"缺少安全扫描、提交历史"，但没有输出 tool_calls
   - 根因：Prompt 中"二选一"约束（tool_calls 或文本回复）让 LLM 在犹豫时倾向保守的 TERMINATE
   - 解决方向：优化 Prompt，降低 tool_calls 的使用门槛；或把"补充建议"也作为一种合法 ReAct 输出
   - 相关文件：`execute_engine.py` `_build_react_prompt()`

2. **Kimi k2.6 thinking 模式 + ReAct 效率极低**
   - 问题：ReAct 决策点调用 Kimi k2.6（temperature=0.3）时，thinking 模式自动开启，单次响应超过 20 分钟
   - 表现：验证脚本中 Kimi 运行 Test 1 卡死 20 分钟以上未返回
   - 根因：thinking 模式适合做深度推理，但 ReAct 只需要快速决策（继续/终止/调什么 Tool）
   - 解决方向：ReAct 决策点换用非 thinking 模型（kimi-k2 非 thinking 版本），或明确禁用 thinking
   - 相关文件：`execute_engine.py` `_react_decision_point()`、`providers.py`

### 中优先级（影响体验）

3. **Windows 终端中文/Unicode 编码问题**
   - 问题：脚本中的中文日志和特殊 Unicode 字符（✅/❌）在 Windows GBK 终端下显示为乱码或触发 `UnicodeEncodeError`
   - 表现：`verify_phase55_real_llm.py` 汇总时 `gbk codec can't encode character`
   - 根因：Windows 默认终端编码为 GBK，不支持 Unicode 扩展字符
   - 解决方向：脚本中避免使用 Unicode 特殊字符；或设置 `PYTHONIOENCODING=utf-8`
   - 相关文件：`verify_phase55_real_llm.py`

4. **ReAct 触发频率偏高（Mock 场景）**
   - 问题：5.4 回归测试中，Mock LLM 返回空文本（非 TERMINATE），ReAct 触发到 `react_max_iterations` 上限
   - 表现：`verify_phase54.py` Test 4 中 react_iterations=5（达到上限）
   - 根因：终止检查逻辑在 ReAct 有空间时放宽，导致 Plan 完成后仍持续触发 ReAct
   - 解决方向：增加"跳过 ReAct"的启发式规则（如无就绪 data 步骤且数据充足度评分高）
   - 相关文件：`execute_engine.py` `run()`

### 低优先级（架构讨论）

5. **ReAct 在当前项目中的价值定位**
   - 问题：Plan 已覆盖 4 个维度的分析步骤，ReAct 的"动态补充"价值有限
   - 观察：真实 LLM 验证中，ReAct 主要行为是 CONTINUE（按部就班）和 TERMINATE（提前结束），tool_calls 补充只在特定场景触发
   - 结论：ReAct 更适合"开放域探索"场景。osscout 有明确分析框架，ReAct 是"锦上添花"而非核心能力
   - 建议：5.6 引入 Specialist 后，ReAct 的价值可能进一步降低，因为 Specialist 调度更适合放在 Plan 阶段
   - 相关讨论：见 [`PHASE5_PLAN.md` 第 8 节](../PHASE5_PLAN.md)

---

## 下一步

**Phase 5.6：动态分析流程（Single Master + Dynamic Specialist Pool）**

核心任务：
1. 升级 PlanEngine：根据仓库特征智能决定启动哪些 Specialist
2. 实现 Specialist 路由：ExecuteEngine 识别 `step_type="specialist"` 并启动对应 Specialist
3. Specialist 子 Plan：每个 Specialist 自己制定子 Plan，自己调 Tool

详见 [`PHASE5_PLAN.md` 第 5 节](../PHASE5_PLAN.md)。
