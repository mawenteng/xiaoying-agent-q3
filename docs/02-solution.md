# 02 · 方案

## 总体架构

原生轻量 **ReAct 循环**（未使用 LangGraph / AgentScope 等框架，降低依赖、便于评审本地复现）：

```
用户问题 (+ history)
    ↓
DecisionMaker.decide(question, history, observations, actions, step, max_steps)
    ↓  structured action
search | read | ask_user | finish
    ↓（search/read）
ToolBox 执行 → Observation 写入轨迹
    ↓
再次 decide … 直到 finish / ask_user / 步数或工具上限
```

## 动态决策（非固定脚本）

决策接口输入：**问题、历史、observation 轨迹、可用动作列表**；输出：**结构化动作 + rationale**。

- **LLMDecisionMaker**：OpenAI 兼容 Chat Completions；由模型根据轨迹选下一步。  
- **MockDecisionMaker**：离线分支逻辑，**根据 observation 内容**决定下一步，例如：
  - 检索命中 D01+D02 且问题涉报销期限 → 依次 `read` 两篇 → `finish` 报告冲突；
  - 检索为空 → 改写 query 再 `search`，仍空则 `out_of_scope`；
  - 工具失败 → 同工具重试一次，再失败则 `incomplete`；
  - 单一清晰命中 → `read` → 带引用 `completed`。

Mock **边界**：只证明控制流、工具接线与验收路径可复现；**不能**替代真实模型决策质量评估。

## 调用流程示例

**路径 A（冲突）**  
`search("报销期限多久")` → hits[D01,D02] → `read(D01)` → `read(D02)` → `finish(needs_confirmation)`

**路径 B（明确答案）**  
`search("字幕导出")` → hits[P01] → `read(P01)` → `finish(completed)`

两条路径的 trace 见 `examples/case-conflict/trace.json` 与 `examples/case-normal/trace.json`。

## 上限与未完成

- `--max-steps`：决策轮次上限  
- `--max-tool-calls`：工具调用次数上限  
达上限 → `status=incomplete`，answer 明确说明未完成原因。

## 技术取舍

| 选项 | 选择 | 理由 |
|---|---|---|
| 语言 | Python 3.10+ | 与校招示例一致，评审易跑 |
| 框架 | 原生循环 | 框架名不加分；逻辑透明 |
| 检索 | 本地词/字 bigram | 无外部服务，合成语料足够 |
| 模型 | OpenAI 兼容可选 | 缺密钥时用 `--mock` |
| 运行 | CLI | 满足「三选一」且命令可复制 |
