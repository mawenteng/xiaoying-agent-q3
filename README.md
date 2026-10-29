# 小影科技 2027 校招 · 第3题：企业知识问答 Agent

**考生：** 马文腾  
**题号：** 3  
**运行方式：** CLI（Python）  
**决策：** 原生 ReAct 循环（模型/Mock 选择动作 → 执行工具 → 观察 → 再决策或结束）

> 允许使用 AI 辅助；使用范围见 [docs/04-ai-usage.md](docs/04-ai-usage.md)。  
> `--mock` 只验证流程与工具接线，**不证明**真实模型决策效果。

## 快速开始

```bash
cd xiaoying-agent-q3
python3 -m venv .venv && source .venv/bin/activate   # 可选
pip install -r requirements.txt

# 离线 Mock（无需密钥）
python -m src.main --mock --question "报销期限多久？"
python -m src.main --mock --question "小影支持字幕导出吗？"
python -m src.main --mock --question "公司下一轮融资估值是多少？"
python -m src.main --mock --inject-tool-fail search --question "员工年假有多少天？"

# 上下文追问
python -m src.main --mock --question "那期限是多久？" \
  --history '[{"role":"user","content":"我想了解费用报销相关规定"},{"role":"assistant","content":"请问您想了解报销材料、期限还是差旅专项？"}]'

# 测试
pytest -q

# 真实模型（OpenAI 兼容）
export OPENAI_API_KEY=sk-...
# export OPENAI_BASE_URL=https://api.openai.com/v1
# export OPENAI_MODEL=gpt-4o-mini
python -m src.main --question "报销期限多久？"
```

## 项目目录

```text
.
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── data/documents.json          # 合成制度/FAQ（含 D01/D02 冲突）
├── docs/
│   ├── 01-requirements.md
│   ├── 02-solution.md
│   ├── 03-evaluation.md
│   ├── 04-ai-usage.md
│   └── 05-retrospective.md
├── src/
│   ├── main.py                  # CLI
│   ├── agent.py                 # ReAct 循环
│   ├── decision.py              # LLM / Mock 决策器
│   ├── tools.py                 # search_docs / read_chunk
│   ├── corpus.py
│   └── schemas.py
├── tests/test_agent.py
└── examples/
    ├── case-normal/             # 明确答案
    ├── case-conflict/           # 文档冲突
    ├── case-out-of-corpus/      # 资料外
    ├── case-paraphrase/         # 相似问改写
    ├── case-followup/           # 上下文追问
    └── case-tool-fail/          # 工具失败
```

## 评审导航

| 检查项 | 入口 |
|---|---|
| 业务目标与验收 | [docs/01-requirements.md](docs/01-requirements.md) |
| 调用流程与动态决策 | [docs/02-solution.md](docs/02-solution.md) |
| 测试预期与实际结果 | [docs/03-evaluation.md](docs/03-evaluation.md) |
| AI 辅助边界 | [docs/04-ai-usage.md](docs/04-ai-usage.md) |
| 难点与改进 | [docs/05-retrospective.md](docs/05-retrospective.md) |
| 运行记录 | [examples/](examples/) |

## 交付结果字段

每次运行输出 JSON，主要字段：

- `status`: `completed` | `needs_confirmation` | `out_of_scope` | `incomplete`
- `answer`: 回答正文
- `citations`: `{doc_id, chunk_id, quote}` 原文引用
- `gaps`: 资料缺口
- `ask_user`: 需要用户确认时的追问
- `trace`: 逐步动作、参数、返回摘要、rationale

## 提交信息

- 题号：`3`
- GitHub URL：`https://github.com/mawenteng/xiaoying-agent-q3`
- 最终 commit SHA：`672da68ba9cde6d95ee110ef4dbdd12a789f532e`

请勿提交真实密钥或隐私数据。私有仓库须给指定评审账号读权限。
