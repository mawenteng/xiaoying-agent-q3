#!/usr/bin/env python3
"""Generate examples/*/input.json, output.json, trace.json under mock mode."""

from __future__ import annotations

import json
from pathlib import Path

from src.agent import KnowledgeQAAgent
from src.decision import MockDecisionMaker
from src.tools import ToolBox

ROOT = Path(__file__).resolve().parent
EX = ROOT / "examples"


CASES = [
    {
        "name": "case-normal",
        "acceptance": ["明确答案"],
        "question": "小影支持字幕导出吗？",
        "history": [],
        "inject": None,
    },
    {
        "name": "case-conflict",
        "acceptance": ["文档冲突"],
        "question": "报销期限多久？",
        "history": [],
        "inject": None,
    },
    {
        "name": "case-out-of-corpus",
        "acceptance": ["资料外问题", "信息或资料不足"],
        "question": "公司下一轮融资估值是多少？",
        "history": [],
        "inject": None,
    },
    {
        "name": "case-paraphrase",
        "acceptance": ["改写后的相似问题", "明确答案"],
        "question": "入职满一年以后，带薪年休假能休几天？",
        "history": [],
        "inject": None,
    },
    {
        "name": "case-followup",
        "acceptance": ["上下文追问", "文档冲突"],
        "question": "那期限是多久？",
        "history": [
            {"role": "user", "content": "我想了解费用报销相关规定"},
            {
                "role": "assistant",
                "content": "请问您想了解报销材料、期限还是差旅专项？",
            },
        ],
        "inject": None,
    },
    {
        "name": "case-tool-fail",
        "acceptance": ["工具失败", "明确答案"],
        "question": "员工年假有多少天？",
        "history": [],
        "inject": "search",
    },
]


def main() -> None:
    EX.mkdir(parents=True, exist_ok=True)
    summary = []
    for case in CASES:
        d = EX / case["name"]
        d.mkdir(parents=True, exist_ok=True)
        inp = {
            "question": case["question"],
            "history": case["history"],
            "mock": True,
            "inject_tool_fail": case["inject"],
            "acceptance_points": case["acceptance"],
        }
        (d / "input.json").write_text(
            json.dumps(inp, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        agent = KnowledgeQAAgent(
            decision_maker=MockDecisionMaker(),
            toolbox=ToolBox(inject_fail_on=case["inject"], fail_times=1),
            max_steps=8,
        )
        result = agent.run(case["question"], case["history"])
        out = result.to_dict()
        out["acceptance_points"] = case["acceptance"]
        (d / "output.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (d / "trace.json").write_text(
            json.dumps(out["trace"], ensure_ascii=False, indent=2), encoding="utf-8"
        )
        summary.append(
            {
                "case": case["name"],
                "status": out["status"],
                "steps": out["steps_used"],
                "acceptance": case["acceptance"],
            }
        )
        print(f"wrote {case['name']}: status={out['status']} steps={out['steps_used']}")

    (EX / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
