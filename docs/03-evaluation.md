# 03 · 评估

## 测试方式

```bash
pytest -q
python scripts_gen_examples.py   # 重生成 examples/
```

以下结果均在 **`--mock`** 下得到。Mock 边界见 [02-solution.md](02-solution.md)。

## 验收点 → examples 映射

| 验收点 | 用例目录 | 输入 | 期望 status | 实际结果文件 |
|---|---|---|---|---|
| 明确答案（正常） | `examples/case-normal/` | 小影支持字幕导出吗？ | completed | [output.json](../examples/case-normal/output.json) / [trace.json](../examples/case-normal/trace.json) |
| 文档冲突 | `examples/case-conflict/` | 报销期限多久？ | needs_confirmation | [output.json](../examples/case-conflict/output.json) / [trace.json](../examples/case-conflict/trace.json) |
| 资料外 / 信息不足 | `examples/case-out-of-corpus/` | 公司下一轮融资估值是多少？ | out_of_scope | [output.json](../examples/case-out-of-corpus/output.json) / [trace.json](../examples/case-out-of-corpus/trace.json) |
| 改写相似问 | `examples/case-paraphrase/` | 入职满一年以后，带薪年休假能休几天？ | completed | [output.json](../examples/case-paraphrase/output.json) / [trace.json](../examples/case-paraphrase/trace.json) |
| 上下文追问 | `examples/case-followup/` | 那期限是多久？+ history | needs_confirmation | [output.json](../examples/case-followup/output.json) / [trace.json](../examples/case-followup/trace.json) |
| 工具失败 | `examples/case-tool-fail/` | 年假 + inject search fail | completed（重试成功）或 incomplete | [output.json](../examples/case-tool-fail/output.json) / [trace.json](../examples/case-tool-fail/trace.json) |

汇总：`examples/summary.json`。自动化断言：`tests/test_agent.py`。

## 关键检查（对照题目审核要点）

- 冲突用例回答同时包含 30 与 15，并引用 D01/D02；**未**单方面断言 15 天。  
- 完成态回答均带 `citations`，quote 来自 `data/documents.json` 原文。  
- tool-fail 的 trace 中至少一步 `observation.ok == false`。  
- 冲突路径与明确答案路径读取的 `doc_id` 集合不同（体现依工具结果调整动作）。

## 失败与限制

- Mock 决策器对「报销期限」冲突依赖命中 D01+D02 的启发式；若改语料关键词可能需同步调整。  
- 真实 LLM 路径未在无密钥 CI 中跑通；需本地配置 `OPENAI_API_KEY` 后人工抽检。  
- 检索为轻量词面匹配，非向量检索；长尾改写可能召回变差。
